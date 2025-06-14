"""
MarketPrism 统一会话管理器

整合原有session_manager.py和optimized_session_manager.py的功能：
1. 保留优化版本的资源管理特性
2. 整合基础版本的代理配置功能
3. 提供统一的API接口
4. 解决功能重复问题

主要特性：
- 自动会话清理和资源泄漏检测
- 统一代理配置管理
- 智能重试机制
- 连接池复用
- 性能监控和健康检查
"""

from datetime import datetime, timezone
import asyncio
import logging
import time
import weakref
from contextlib import asynccontextmanager
from typing import Dict, Optional, Set, Any, Union
from dataclasses import dataclass
import aiohttp
import ssl
import structlog
from urllib.parse import urlparse

# 尝试相对导入，失败则使用绝对导入
try:
    from .proxy_manager import ProxyConfig, proxy_manager
except ImportError:
    try:
        from core.networking.proxy_manager import ProxyConfig, proxy_manager
    except ImportError:
        # 创建虚拟的代理类（最终后备）
        class ProxyConfig:
            def __init__(self):
                pass
            def has_proxy(self):
                return False
            def to_aiohttp_proxy(self):
                return None
        
        class ProxyManager:
            def initialize(self):
                pass
            def get_proxy_config(self, config=None):
                return ProxyConfig()
        
        proxy_manager = ProxyManager()

logger = logging.getLogger(__name__)


@dataclass
class UnifiedSessionConfig:
    """统一会话配置 - 整合两个版本的配置选项"""
    
    # 连接配置
    connection_timeout: float = 10.0
    read_timeout: float = 30.0
    total_timeout: float = 60.0
    
    # 连接池配置
    connector_limit: int = 100
    connector_limit_per_host: int = 30
    keepalive_timeout: int = 60
    
    # 重试配置
    max_retries: int = 3
    retry_backoff: float = 1.0
    retry_delay: float = 1.0
    
    # SSL配置
    verify_ssl: bool = True
    enable_ssl: bool = True
    ssl_context: Optional[ssl.SSLContext] = None
    
    # 代理配置（整合原session_manager的代理功能）
    proxy_url: Optional[str] = None
    proxy_auth: Optional[aiohttp.BasicAuth] = None
    trust_env: bool = True
    
    # 会话配置（整合原session_manager功能）
    headers: Optional[Dict[str, str]] = None
    cookies: Optional[Dict[str, str]] = None
    
    # 其他配置
    enable_compression: bool = True
    follow_redirects: bool = True
    max_field_size: int = 8192
    
    # 清理配置
    cleanup_interval: int = 30  # 秒
    enable_auto_cleanup: bool = True


class UnifiedSessionManager:
    """
    统一会话管理器 - 整合原有重复功能
    
    核心特性：
    1. 资源泄漏检测和自动清理（来自optimized版本）
    2. 代理配置管理（来自session_manager版本）
    3. 统一的API接口
    4. 智能重试机制
    5. 性能监控
    """
    
    def __init__(self, config: Optional[UnifiedSessionConfig] = None):
        self.config = config or UnifiedSessionConfig()
        self.logger = structlog.get_logger(__name__)
        
        # 会话管理（来自optimized版本）
        self._sessions: Dict[str, aiohttp.ClientSession] = {}
        self._session_configs: Dict[str, UnifiedSessionConfig] = {}
        self._session_refs: Set[weakref.ref] = set()
        self._connectors: Dict[str, aiohttp.TCPConnector] = {}
        
        # 运行状态
        self._closed = False
        self._cleanup_task: Optional[asyncio.Task] = None
        self._initialized = False
        
        # 统计信息（增强版本）
        self.stats = {
            'sessions_created': 0,
            'sessions_closed': 0,
            'requests_made': 0,
            'requests_failed': 0,
            'cleanup_runs': 0,
            'proxy_requests': 0,
            'direct_requests': 0,
            'start_time': time.time()
        }
        
        # 启动清理任务
        if self.config.enable_auto_cleanup:
            self._start_cleanup_task()
        
        self.logger.info("统一会话管理器已初始化")
    
    async def initialize(self):
        """初始化会话管理器（API接口兼容性方法）"""
        if self._initialized:
            self.logger.debug("会话管理器已经初始化")
            return
        
        try:
            # 初始化代理管理器
            if hasattr(proxy_manager, 'initialize'):
                await proxy_manager.initialize()
            
            # 启动清理任务（如果还没有启动）
            if self._cleanup_task is None and self.config.enable_auto_cleanup:
                try:
                    self._cleanup_task = asyncio.create_task(self._cleanup_loop())
                except RuntimeError:
                    # 没有运行中的事件循环，稍后启动
                    pass
            
            self._initialized = True
            self.logger.info("统一会话管理器初始化完成")
            
        except Exception as e:
            self.logger.error("统一会话管理器初始化失败", error=str(e))
            raise
    
    def _start_cleanup_task(self):
        """启动清理任务"""
        try:
            # 检查是否有运行中的事件循环
            loop = asyncio.get_running_loop()
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        except RuntimeError:
            # 没有运行中的事件循环，延迟启动清理任务
            self._cleanup_task = None
            self.logger.debug("延迟启动清理任务（无运行中的事件循环）")
    
    async def _cleanup_loop(self):
        """清理循环任务"""
        while not self._closed:
            try:
                await asyncio.sleep(self.config.cleanup_interval)
                await self._cleanup_expired_sessions()
                self.stats['cleanup_runs'] += 1
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("会话清理任务失败", error=str(e))
    
    async def _cleanup_expired_sessions(self):
        """清理过期会话"""
        expired_refs = set()
        expired_sessions = []
        
        for ref in self._session_refs:
            session = ref()
            if session is None or session.closed:
                expired_refs.add(ref)
        
        # 清理会话字典中的过期项
        for session_name, session in list(self._sessions.items()):
            if session.closed:
                expired_sessions.append(session_name)
        
        # 执行清理
        self._session_refs -= expired_refs
        for session_name in expired_sessions:
            del self._sessions[session_name]
            if session_name in self._session_configs:
                del self._session_configs[session_name]
        
        if expired_refs or expired_sessions:
            self.logger.debug("清理过期会话", 
                            refs_cleaned=len(expired_refs),
                            sessions_cleaned=len(expired_sessions))
    
    def _create_connector(self, key: str) -> aiohttp.TCPConnector:
        """创建TCP连接器"""
        if key in self._connectors:
            return self._connectors[key]
        
        connector = aiohttp.TCPConnector(
            limit=self.config.connector_limit,
            limit_per_host=self.config.connector_limit_per_host,
            keepalive_timeout=self.config.keepalive_timeout,
            enable_cleanup_closed=True,
            ssl=self.config.ssl_context if self.config.ssl_context else self.config.verify_ssl
        )
        
        self._connectors[key] = connector
        return connector
    
    def _create_timeout(self) -> aiohttp.ClientTimeout:
        """创建超时配置"""
        return aiohttp.ClientTimeout(
            total=self.config.total_timeout,
            connect=self.config.connection_timeout,
            sock_read=self.config.read_timeout
        )
    
    async def get_session(self, 
                         session_name: str = "default",
                         config: Optional[UnifiedSessionConfig] = None,
                         proxy_config: Optional[ProxyConfig] = None,
                         exchange_config: Optional[Dict[str, Any]] = None) -> aiohttp.ClientSession:
        """
        获取或创建HTTP会话（整合原session_manager API）
        
        Args:
            session_name: 会话名称，用于复用
            config: 会话配置
            proxy_config: 代理配置
            exchange_config: 交易所配置
        """
        if self._closed:
            raise RuntimeError("会话管理器已关闭")
        
        # 懒启动清理任务
        if self._cleanup_task is None and self.config.enable_auto_cleanup:
            try:
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            except RuntimeError:
                # 仍然没有事件循环，继续不启动清理任务
                pass
        
        try:
            # 检查是否已存在有效会话
            if session_name in self._sessions:
                session = self._sessions[session_name]
                if not session.closed:
                    return session
                else:
                    # 会话已关闭，清理并重新创建
                    del self._sessions[session_name]
                    if session_name in self._session_configs:
                        del self._session_configs[session_name]
            
            # 使用提供的配置或默认配置
            session_config = config or self.config
            
            # 获取代理配置（整合原session_manager功能）
            if proxy_config is None:
                proxy_config = proxy_manager.get_proxy_config(exchange_config)
            
            # 创建新会话
            session = await self._create_session(session_config, proxy_config)
            
            # 缓存会话和配置
            self._sessions[session_name] = session
            self._session_configs[session_name] = session_config
            
            # 添加弱引用（优化版本特性）
            self._session_refs.add(weakref.ref(session))
            
            self.stats['sessions_created'] += 1
            
            self.logger.info("HTTP会话已创建", 
                           session_name=session_name,
                           has_proxy=proxy_config.has_proxy(),
                           timeout=session_config.total_timeout)
            
            return session
            
        except Exception as e:
            self.logger.error("创建HTTP会话失败", error=str(e), session_name=session_name)
            raise
    
    async def _create_session(self, 
                             config: UnifiedSessionConfig, 
                             proxy_config: ProxyConfig) -> aiohttp.ClientSession:
        """创建aiohttp会话（整合两个版本的功能）"""
        try:
            # 创建连接器
            connector = aiohttp.TCPConnector(
                limit=config.connector_limit,
                limit_per_host=config.connector_limit_per_host,
                keepalive_timeout=config.keepalive_timeout,
                enable_cleanup_closed=True,
                ssl=config.ssl_context if config.ssl_context else config.verify_ssl
            )
            
            # 创建超时配置
            timeout = aiohttp.ClientTimeout(
                total=config.total_timeout,
                connect=config.connection_timeout,
                sock_read=config.read_timeout
            )
            
            # 会话参数
            session_kwargs = {
                'connector': connector,
                'timeout': timeout,
                'headers': {
                    'User-Agent': 'MarketPrism/1.0 (Unified Session Manager)'
                }
            }
            
            # 添加自定义头部和cookies（原session_manager功能）
            if config.headers:
                session_kwargs['headers'].update(config.headers)
            
            if config.cookies:
                session_kwargs['cookies'] = config.cookies
            
            # 检查aiohttp版本兼容性
            try:
                session_kwargs['trust_env'] = config.trust_env
            except TypeError:
                # 旧版本aiohttp不支持trust_env参数
                pass
            
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
        发送HTTP请求（整合原session_manager API）
        """
        try:
            session = await self.get_session(session_name)
            
            # 代理配置（整合原功能）
            if proxy_override:
                kwargs['proxy'] = proxy_override
                self.stats['proxy_requests'] += 1
            elif session_name in self._session_configs:
                # 使用会话关联的代理配置
                session_proxy_config = proxy_manager.get_proxy_config()
                if session_proxy_config.has_proxy():
                    kwargs['proxy'] = session_proxy_config.to_aiohttp_proxy()
                    self.stats['proxy_requests'] += 1
                else:
                    self.stats['direct_requests'] += 1
            
            # 发送请求
            response = await session.request(method, url, **kwargs)
            self.stats['requests_made'] += 1
            return response
            
        except Exception as e:
            self.stats['requests_failed'] += 1
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
        """带重试的HTTP请求（整合原session_manager功能）"""
        config = self._session_configs.get(session_name, self.config)
        attempts = max_attempts or config.max_retries
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
    
    async def close(self):
        """关闭管理器"""
        self._closed = True
        
        # 停止清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # 关闭所有会话
        for session in self._sessions.values():
            if not session.closed:
                await session.close()
        
        # 关闭连接器
        for connector in self._connectors.values():
            await connector.close()
        
        self._sessions.clear()
        self._session_configs.clear()
        self._connectors.clear()
        self._session_refs.clear()
        
        self.logger.info("统一会话管理器已关闭")
    
    def get_session_stats(self) -> Dict[str, Any]:
        """获取会话统计"""
        return {
            'total_sessions': len(self._sessions),
            'active_sessions': len([s for s in self._sessions.values() if not s.closed]),
            'closed_sessions': len([s for s in self._sessions.values() if s.closed]),
            'session_names': list(self._sessions.keys()),
            **self.stats
        }
    
    # 缺失的方法补充
    async def close_session(self, session_name: str):
        """关闭指定会话（整合原功能）"""
        if session_name in self._sessions:
            session = self._sessions[session_name]
            if not session.closed:
                await session.close()
            del self._sessions[session_name]
            
            if session_name in self._session_configs:
                del self._session_configs[session_name]
            
            self.stats['sessions_closed'] += 1
            self.logger.info("会话已关闭", session_name=session_name)
    
    async def close_all_sessions(self):
        """关闭所有会话（整合原功能）"""
        for session_name in list(self._sessions.keys()):
            await self.close_session(session_name)
        
        # 关闭连接器
        for connector in self._connectors.values():
            await connector.close()
        self._connectors.clear()
        
        self.logger.info("所有会话已关闭")
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态（来自优化版本）"""
        stats = self.get_session_stats()
        
        # 计算健康评分
        health_score = 100
        issues = []
        
        # 检查失败率
        total_requests = self.stats['requests_made']
        if total_requests > 0:
            success_rate = ((total_requests - self.stats['requests_failed']) / total_requests) * 100
            if success_rate < 95:
                health_score -= 20
                issues.append("高失败率")
        
        # 检查会话状态
        if stats['closed_sessions'] > stats['active_sessions']:
            health_score -= 10
            issues.append("过多关闭会话")
        
        # 检查管理器状态
        if self._closed:
            health_score = 0
            issues.append("管理器已关闭")
        
        return {
            'healthy': health_score >= 80,
            'health_score': health_score,
            'status': 'healthy' if health_score >= 80 else 'degraded' if health_score >= 50 else 'unhealthy',
            'issues': issues,
            'stats': stats
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取详细统计（来自优化版本）"""
        uptime = time.time() - self.stats['start_time']
        session_stats = self.get_session_stats()
        
        return {
            'uptime_seconds': uptime,
            # 将会话统计提升到顶层
            'total_sessions': session_stats['total_sessions'],
            'active_sessions': session_stats['active_sessions'],
            'closed_sessions': session_stats['closed_sessions'],
            'session_names': session_stats['session_names'],
            'session_stats': session_stats,
            'request_stats': {
                'total_requests': self.stats['requests_made'],
                'failed_requests': self.stats['requests_failed'],
                'success_rate': (
                    (self.stats['requests_made'] - self.stats['requests_failed']) / 
                    max(self.stats['requests_made'], 1)
                ) * 100,
                'proxy_requests': self.stats['proxy_requests'],
                'direct_requests': self.stats['direct_requests']
            },
            'cleanup_stats': {
                'cleanup_runs': self.stats['cleanup_runs'],
                'active_refs': len(self._session_refs)
            }
        }
    
    async def cleanup_closed_sessions(self):
        """手动清理关闭的会话（整合原功能）"""
        await self._cleanup_expired_sessions()
    
    async def refresh_session(self, session_name: str):
        """刷新会话（整合原功能）"""
        if session_name in self._sessions:
            await self.close_session(session_name)
        # 下次调用get_session时会自动创建新会话
        self.logger.info("会话已标记为刷新", session_name=session_name)
    
    # 便捷方法（来自优化版本）
    async def get(self, url: str, session_name: str = "default", **kwargs):
        """GET请求"""
        return await self.request('GET', url, session_name, **kwargs)
    
    async def post(self, url: str, session_name: str = "default", **kwargs):
        """POST请求"""
        return await self.request('POST', url, session_name, **kwargs)

    async def create_session(self, name: str = "default", config: Optional[UnifiedSessionConfig] = None, timeout: Optional[float] = None) -> str:
        """创建新会话并返回会话ID"""
        session_config = config or self.config
        
        # 如果提供了timeout参数，更新配置
        if timeout is not None:
            session_config = UnifiedSessionConfig(
                connection_timeout=timeout,
                read_timeout=session_config.read_timeout,
                total_timeout=session_config.total_timeout,
                **{k: v for k, v in session_config.__dict__.items() 
                   if k not in ['connection_timeout', 'read_timeout', 'total_timeout']}
            )
        
        proxy_config = proxy_manager.get_proxy_config()
        
        # 创建会话
        session = await self._create_session(session_config, proxy_config)
        
        # 存储会话
        self._sessions[name] = session
        self._session_configs[name] = session_config
        
        # 更新统计
        self.stats['sessions_created'] += 1
        
        self.logger.info(f"创建会话: {name}")
        return name
    
    @property
    def sessions(self) -> Dict[str, aiohttp.ClientSession]:
        """获取所有会话"""
        return self._sessions.copy()

    def cleanup_sessions(self) -> int:
        """清理关闭的会话，返回清理的会话数量"""
        cleaned_count = 0
        closed_sessions = []
        
        for name, session in self._sessions.items():
            if session.closed:
                closed_sessions.append(name)
        
        for name in closed_sessions:
            del self._sessions[name]
            if name in self._session_configs:
                del self._session_configs[name]
            cleaned_count += 1
        
        self.stats['sessions_closed'] += cleaned_count
        self.logger.info(f"清理了 {cleaned_count} 个关闭的会话")
        return cleaned_count


# 向后兼容性支持
HTTPSessionManager = UnifiedSessionManager  # 兼容原session_manager
SessionManager = UnifiedSessionManager      # 兼容优化版本
SessionConfig = UnifiedSessionConfig        # 统一配置类

# 创建默认实例
unified_session_manager = UnifiedSessionManager()