"""
统一HTTP会话管理器

提供：
- 统一的aiohttp会话管理
- 自动代理配置
- 连接池管理
- 重试机制
- 会话复用和清理
"""

import asyncio
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass
import aiohttp
import structlog

from .proxy_manager import ProxyConfig, proxy_manager


@dataclass
class SessionConfig:
    """HTTP会话配置"""
    timeout: int = 30
    connector_limit: int = 100
    connector_limit_per_host: int = 30
    trust_env: bool = True
    enable_ssl: bool = True
    ssl_context: Optional[Any] = None
    headers: Optional[Dict[str, str]] = None
    cookies: Optional[Dict[str, str]] = None
    
    # 重试配置
    retry_attempts: int = 3
    retry_delay: float = 1.0
    retry_backoff: float = 2.0


class HTTPSessionManager:
    """HTTP会话管理器"""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        self.sessions: Dict[str, aiohttp.ClientSession] = {}
        self.session_configs: Dict[str, SessionConfig] = {}
    
    async def get_session(self, 
                         session_name: str = "default",
                         config: Optional[SessionConfig] = None,
                         proxy_config: Optional[ProxyConfig] = None,
                         exchange_config: Optional[Dict[str, Any]] = None) -> aiohttp.ClientSession:
        """
        获取或创建HTTP会话
        
        Args:
            session_name: 会话名称，用于复用
            config: 会话配置
            proxy_config: 代理配置
            exchange_config: 交易所配置
        """
        try:
            # 检查是否已存在会话
            if session_name in self.sessions:
                session = self.sessions[session_name]
                if not session.closed:
                    return session
                else:
                    # 会话已关闭，清理并重新创建
                    del self.sessions[session_name]
                    if session_name in self.session_configs:
                        del self.session_configs[session_name]
            
            # 使用默认配置或提供的配置
            if config is None:
                config = SessionConfig()
            
            # 获取代理配置
            if proxy_config is None:
                proxy_config = proxy_manager.get_proxy_config(exchange_config)
            
            # 创建新会话
            session = await self._create_session(config, proxy_config)
            
            # 缓存会话和配置
            self.sessions[session_name] = session
            self.session_configs[session_name] = config
            
            self.logger.info("HTTP会话已创建", 
                           session_name=session_name,
                           has_proxy=proxy_config.has_proxy(),
                           timeout=config.timeout)
            
            return session
            
        except Exception as e:
            self.logger.error("创建HTTP会话失败", error=str(e), session_name=session_name)
            raise
    
    async def _create_session(self, 
                             config: SessionConfig, 
                             proxy_config: ProxyConfig) -> aiohttp.ClientSession:
        """创建aiohttp会话"""
        try:
            # 超时配置
            timeout = aiohttp.ClientTimeout(total=config.timeout)
            
            # 连接器配置
            connector_kwargs = {
                'limit': config.connector_limit,
                'limit_per_host': config.connector_limit_per_host,
                'ssl': config.ssl_context if config.enable_ssl else False
            }
            
            # 代理配置
            if proxy_config.has_proxy():
                # 注意：aiohttp的代理配置在连接时指定，不在connector中
                pass
            
            connector = aiohttp.TCPConnector(**connector_kwargs)
            
            # 会话参数
            session_kwargs = {
                'connector': connector,
                'timeout': timeout
            }
            
            # 检查aiohttp版本兼容性
            try:
                session_kwargs['trust_env'] = config.trust_env
            except TypeError:
                # 旧版本aiohttp不支持trust_env参数
                pass
            
            # 添加默认头部和cookies
            if config.headers:
                session_kwargs['headers'] = config.headers
            
            if config.cookies:
                session_kwargs['cookies'] = config.cookies
            
            # 创建会话
            session = aiohttp.ClientSession(**session_kwargs)
            
            return session
            
        except Exception as e:
            self.logger.error("创建aiohttp会话失败", error=str(e))
            raise
    
    async def request(self,
                     method: str,
                     url: str,
                     session_name: str = "default",
                     proxy_override: Optional[str] = None,
                     **kwargs) -> aiohttp.ClientResponse:
        """
        发送HTTP请求
        
        Args:
            method: HTTP方法
            url: 请求URL
            session_name: 使用的会话名称
            proxy_override: 覆盖默认代理配置
            **kwargs: 其他aiohttp请求参数
        """
        try:
            session = await self.get_session(session_name)
            
            # 代理配置
            if proxy_override:
                kwargs['proxy'] = proxy_override
            elif session_name in self.session_configs:
                # 使用会话关联的代理配置
                session_proxy_config = proxy_manager.get_proxy_config()
                if session_proxy_config.has_proxy():
                    kwargs['proxy'] = session_proxy_config.to_aiohttp_proxy()
            
            # 发送请求
            response = await session.request(method, url, **kwargs)
            return response
            
        except Exception as e:
            self.logger.error("HTTP请求失败", 
                            method=method, 
                            url=url, 
                            error=str(e))
            raise
    
    async def request_with_retry(self,
                                method: str,
                                url: str,
                                session_name: str = "default",
                                max_attempts: Optional[int] = None,
                                **kwargs) -> aiohttp.ClientResponse:
        """
        带重试的HTTP请求
        
        Args:
            method: HTTP方法
            url: 请求URL 
            session_name: 使用的会话名称
            max_attempts: 最大重试次数，None表示使用配置中的值
            **kwargs: 其他aiohttp请求参数
        """
        config = self.session_configs.get(session_name, SessionConfig())
        attempts = max_attempts or config.retry_attempts
        delay = config.retry_delay
        
        last_exception = None
        
        for attempt in range(attempts):
            try:
                response = await self.request(method, url, session_name, **kwargs)
                
                # 检查HTTP状态码
                if response.status < 500:  # 非服务器错误不重试
                    return response
                
                # 服务器错误，记录并准备重试
                self.logger.warning("HTTP请求服务器错误，准备重试",
                                  method=method,
                                  url=url,
                                  status=response.status,
                                  attempt=attempt + 1,
                                  max_attempts=attempts)
                
                response.close()
                
            except Exception as e:
                last_exception = e
                self.logger.warning("HTTP请求失败，准备重试",
                                  method=method,
                                  url=url, 
                                  error=str(e),
                                  attempt=attempt + 1,
                                  max_attempts=attempts)
            
            # 如果不是最后一次尝试，等待后重试
            if attempt < attempts - 1:
                await asyncio.sleep(delay)
                delay *= config.retry_backoff  # 指数退避
        
        # 所有重试都失败了
        error_msg = f"HTTP请求重试{attempts}次后仍然失败"
        if last_exception:
            self.logger.error(error_msg, error=str(last_exception))
            raise last_exception
        else:
            self.logger.error(error_msg)
            raise Exception(error_msg)
    
    async def close_session(self, session_name: str):
        """关闭指定会话"""
        if session_name in self.sessions:
            session = self.sessions[session_name]
            if not session.closed:
                await session.close()
            del self.sessions[session_name]
            
            if session_name in self.session_configs:
                del self.session_configs[session_name]
            
            self.logger.info("HTTP会话已关闭", session_name=session_name)
    
    async def close_all_sessions(self):
        """关闭所有会话"""
        for session_name, session in list(self.sessions.items()):
            if not session.closed:
                await session.close()
        
        self.sessions.clear()
        self.session_configs.clear()
        
        self.logger.info("所有HTTP会话已关闭")
    
    def get_session_stats(self) -> Dict[str, Any]:
        """获取会话统计"""
        active_sessions = 0
        total_sessions = len(self.sessions)
        
        for session in self.sessions.values():
            if not session.closed:
                active_sessions += 1
        
        return {
            'total_sessions': total_sessions,
            'active_sessions': active_sessions,
            'session_names': list(self.sessions.keys())
        }
    
    async def cleanup_closed_sessions(self):
        """清理已关闭的会话"""
        closed_sessions = []
        
        for session_name, session in self.sessions.items():
            if session.closed:
                closed_sessions.append(session_name)
        
        for session_name in closed_sessions:
            del self.sessions[session_name]
            if session_name in self.session_configs:
                del self.session_configs[session_name]
        
        if closed_sessions:
            self.logger.info("已清理关闭的会话", count=len(closed_sessions))
    
    async def refresh_session(self, session_name: str):
        """刷新会话（关闭并重新创建）"""
        config = self.session_configs.get(session_name)
        
        # 关闭旧会话
        await self.close_session(session_name)
        
        # 创建新会话
        if config:
            await self.get_session(session_name, config)
            self.logger.info("会话已刷新", session_name=session_name)


# 全局HTTP会话管理器实例
session_manager = HTTPSessionManager()