"""
MarketPrism 优化的会话管理器

解决以下问题：
1. aiohttp会话泄漏
2. 连接池管理不当
3. 超时配置不统一
4. 资源清理不完整
"""

import asyncio
import logging
import time
import weakref
from contextlib import asynccontextmanager
from typing import Dict, Optional, Set, Any, Union
from dataclasses import dataclass
import aiohttp
import ssl
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class SessionConfig:
    """会话配置"""
    # 连接配置
    connection_timeout: float = 10.0
    read_timeout: float = 30.0
    total_timeout: float = 60.0
    
    # 连接池配置
    connector_limit: int = 100
    connector_limit_per_host: int = 10
    keepalive_timeout: int = 60
    
    # 重试配置
    max_retries: int = 3
    retry_backoff: float = 1.0
    
    # SSL配置
    verify_ssl: bool = True
    ssl_context: Optional[ssl.SSLContext] = None
    
    # 代理配置
    proxy_url: Optional[str] = None
    proxy_auth: Optional[aiohttp.BasicAuth] = None
    
    # 其他配置
    enable_compression: bool = True
    follow_redirects: bool = True
    max_field_size: int = 8192


class SessionManager:
    """优化的会话管理器
    
    特性：
    1. 自动会话清理
    2. 连接池复用
    3. 智能重试机制
    4. 资源泄漏检测
    5. 性能监控
    """
    
    def __init__(self, config: Optional[SessionConfig] = None):
        self.config = config or SessionConfig()
        
        # 会话管理
        self._sessions: Dict[str, aiohttp.ClientSession] = {}
        self._session_refs: Set[weakref.ref] = set()
        self._connectors: Dict[str, aiohttp.TCPConnector] = {}
        
        # 运行状态
        self._closed = False
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # 统计信息
        self.stats = {
            'sessions_created': 0,
            'sessions_closed': 0,
            'requests_made': 0,
            'requests_failed': 0,
            'cleanup_runs': 0,
            'start_time': time.time()
        }
        
        # 启动清理任务
        self._start_cleanup_task()
        
        logger.info("优化会话管理器已初始化")
    
    def _start_cleanup_task(self):
        """启动清理任务"""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def _cleanup_loop(self):
        """清理循环任务"""
        while not self._closed:
            try:
                await asyncio.sleep(30)  # 每30秒清理一次
                await self._cleanup_expired_sessions()
                self.stats['cleanup_runs'] += 1
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"会话清理任务失败: {e}")
    
    async def _cleanup_expired_sessions(self):
        """清理过期会话"""
        expired_refs = set()
        
        for ref in self._session_refs:
            session = ref()
            if session is None or session.closed:
                expired_refs.add(ref)
        
        self._session_refs -= expired_refs
        
        if expired_refs:
            logger.debug(f"清理了 {len(expired_refs)} 个过期会话引用")
    
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
    
    def get_session(self, key: str = "default", **kwargs) -> aiohttp.ClientSession:
        """获取会话实例
        
        Args:
            key: 会话标识符
            **kwargs: 额外的会话配置
        """
        if self._closed:
            raise RuntimeError("会话管理器已关闭")
        
        if key in self._sessions and not self._sessions[key].closed:
            return self._sessions[key]
        
        # 创建新会话
        connector = self._create_connector(key)
        timeout = self._create_timeout()
        
        session_kwargs = {
            'connector': connector,
            'timeout': timeout,
            'headers': {
                'User-Agent': 'MarketPrism/1.0 (Optimized Session Manager)'
            }
        }
        
        # 合并配置
        session_kwargs.update(kwargs)
        
        session = aiohttp.ClientSession(**session_kwargs)
        self._sessions[key] = session
        
        # 添加弱引用
        self._session_refs.add(weakref.ref(session))
        
        self.stats['sessions_created'] += 1
        logger.debug(f"创建新会话: {key}")
        
        return session
    
    @asynccontextmanager
    async def request(self, method: str, url: str, session_key: str = "default", 
                     max_retries: Optional[int] = None, proxy: Optional[str] = None, **kwargs):
        """发送HTTP请求（带重试和资源管理）
        
        Args:
            method: HTTP方法
            url: 请求URL
            session_key: 会话标识符
            max_retries: 最大重试次数
            proxy: 代理URL（可覆盖配置文件中的代理）
            **kwargs: 请求参数
        """
        max_retries = max_retries or self.config.max_retries
        retry_count = 0
        last_error = None
        
        while retry_count <= max_retries:
            try:
                session = self.get_session(session_key)
                
                # 设置代理（优先级：参数传入 > 配置文件 > 无代理）
                effective_proxy = proxy or self.config.proxy_url
                if effective_proxy and 'proxy' not in kwargs:
                    kwargs['proxy'] = effective_proxy
                    if self.config.proxy_auth:
                        kwargs['proxy_auth'] = self.config.proxy_auth
                
                async with session.request(method, url, **kwargs) as response:
                    self.stats['requests_made'] += 1
                    yield response
                    return
                    
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = e
                retry_count += 1
                self.stats['requests_failed'] += 1
                
                if retry_count <= max_retries:
                    backoff_time = self.config.retry_backoff * (2 ** (retry_count - 1))
                    logger.warning(f"请求失败，{backoff_time:.1f}秒后重试 ({retry_count}/{max_retries}): {e}")
                    await asyncio.sleep(backoff_time)
                else:
                    logger.error(f"请求最终失败: {e}")
                    raise last_error
            except Exception as e:
                self.stats['requests_failed'] += 1
                logger.error(f"请求异常: {e}")
                raise
        
        # 如果到这里说明重试用尽了
        raise last_error if last_error else RuntimeError("请求失败，原因未知")
    
    async def get(self, url: str, session_key: str = "default", **kwargs):
        """GET请求"""
        async with self.request('GET', url, session_key, **kwargs) as response:
            return response
    
    async def post(self, url: str, session_key: str = "default", **kwargs):
        """POST请求"""
        async with self.request('POST', url, session_key, **kwargs) as response:
            return response
    
    async def close_session(self, key: str):
        """关闭指定会话"""
        if key in self._sessions:
            session = self._sessions.pop(key)
            if not session.closed:
                await session.close()
                self.stats['sessions_closed'] += 1
                logger.debug(f"关闭会话: {key}")
    
    async def close_all_sessions(self):
        """关闭所有会话"""
        for key in list(self._sessions.keys()):
            await self.close_session(key)
        
        # 关闭连接器
        for connector in self._connectors.values():
            await connector.close()
        self._connectors.clear()
        
        logger.info("所有会话已关闭")
    
    async def close(self):
        """关闭会话管理器"""
        if self._closed:
            return
        
        self._closed = True
        
        # 取消清理任务
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # 关闭所有会话
        await self.close_all_sessions()
        
        logger.info("会话管理器已关闭")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        uptime = time.time() - self.stats['start_time']
        
        return {
            'uptime_seconds': uptime,
            'active_sessions': len([s for s in self._sessions.values() if not s.closed]),
            'total_sessions_created': self.stats['sessions_created'],
            'total_sessions_closed': self.stats['sessions_closed'],
            'total_requests': self.stats['requests_made'],
            'failed_requests': self.stats['requests_failed'],
            'success_rate': (self.stats['requests_made'] - self.stats['requests_failed']) / max(1, self.stats['requests_made']),
            'requests_per_second': self.stats['requests_made'] / max(1, uptime),
            'cleanup_runs': self.stats['cleanup_runs'],
            'active_connectors': len(self._connectors),
            'session_refs': len(self._session_refs),
            'is_closed': self._closed
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        stats = self.get_statistics()
        
        # 健康检查
        healthy = True
        issues = []
        
        if stats['success_rate'] < 0.9:
            healthy = False
            issues.append(f"请求成功率过低: {stats['success_rate']:.2%}")
        
        if stats['active_sessions'] > self.config.connector_limit:
            healthy = False
            issues.append(f"活跃会话过多: {stats['active_sessions']}")
        
        if len(self._session_refs) > stats['active_sessions'] * 2:
            issues.append("可能存在会话引用泄漏")
        
        return {
            'healthy': healthy,
            'issues': issues,
            'stats': stats
        }
    
    def __del__(self):
        """析构函数，确保资源清理"""
        if not self._closed and self._sessions:
            logger.warning("会话管理器在未正确关闭的情况下被销毁，可能存在资源泄漏")


# 全局会话管理器实例
_global_session_manager: Optional[SessionManager] = None


def get_session_manager(config: Optional[SessionConfig] = None) -> SessionManager:
    """获取全局会话管理器实例"""
    global _global_session_manager
    if _global_session_manager is None or _global_session_manager._closed:
        _global_session_manager = SessionManager(config)
    return _global_session_manager


async def close_global_session_manager():
    """关闭全局会话管理器"""
    global _global_session_manager
    if _global_session_manager:
        await _global_session_manager.close()
        _global_session_manager = None


# 便捷函数
async def get(url: str, session_key: str = "default", **kwargs):
    """全局GET请求"""
    manager = get_session_manager()
    async with manager.request('GET', url, session_key, **kwargs) as response:
        return await response.json()


async def post(url: str, session_key: str = "default", **kwargs):
    """全局POST请求"""
    manager = get_session_manager()
    async with manager.request('POST', url, session_key, **kwargs) as response:
        return await response.json()


# 上下文管理器
@asynccontextmanager
async def managed_session_manager(config: Optional[SessionConfig] = None):
    """会话管理器上下文管理器"""
    manager = SessionManager(config)
    try:
        yield manager
    finally:
        await manager.close()