#!/usr/bin/env python3
"""
MarketPrism 连接池管理系统 - 第二阶段优化第三天实施

企业级连接池管理，支持WebSocket和HTTP连接的高效复用、健康检查和故障切换。
"""

import asyncio
import time
import threading
import weakref
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, TypeVar, Generic, Callable, Union
import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException
import logging

# 设置日志
logger = logging.getLogger(__name__)

# 泛型类型定义
T = TypeVar('T')


class ConnectionState(Enum):
    """连接状态枚举"""
    IDLE = "idle"           # 空闲状态
    ACTIVE = "active"       # 活跃使用中
    CHECKING = "checking"   # 健康检查中
    FAILED = "failed"       # 连接失败
    CLOSED = "closed"       # 已关闭


class ConnectionType(Enum):
    """连接类型枚举"""
    WEBSOCKET = "websocket"
    HTTP = "http"
    TCP = "tcp"


@dataclass
class ConnectionInfo:
    """连接信息"""
    connection_id: str
    connection_type: ConnectionType
    created_at: float
    last_used_at: float
    use_count: int = 0
    state: ConnectionState = ConnectionState.IDLE
    health_check_count: int = 0
    error_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def age_seconds(self) -> float:
        """连接年龄（秒）"""
        return time.time() - self.created_at
    
    @property
    def idle_time_seconds(self) -> float:
        """空闲时间（秒）"""
        return time.time() - self.last_used_at
    
    def mark_used(self):
        """标记连接被使用"""
        self.last_used_at = time.time()
        self.use_count += 1
        self.state = ConnectionState.ACTIVE


@dataclass
class ConnectionPoolStatistics:
    """连接池统计信息"""
    pool_name: str
    connection_type: ConnectionType
    max_size: int
    current_size: int
    active_connections: int
    idle_connections: int
    failed_connections: int
    total_created: int = 0
    total_acquired: int = 0
    total_returned: int = 0
    total_reused: int = 0
    total_health_checks: int = 0
    total_failures: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    creation_time_total: float = 0.0
    health_check_time_total: float = 0.0
    
    @property
    def hit_rate(self) -> float:
        """缓存命中率"""
        total_requests = self.cache_hits + self.cache_misses
        return self.cache_hits / total_requests if total_requests > 0 else 0.0
    
    @property
    def utilization_rate(self) -> float:
        """池利用率"""
        return self.active_connections / self.max_size if self.max_size > 0 else 0.0
    
    @property
    def reuse_rate(self) -> float:
        """连接复用率"""
        return self.total_reused / self.total_created if self.total_created > 0 else 0.0
    
    @property
    def failure_rate(self) -> float:
        """连接失败率"""
        return self.total_failures / self.total_created if self.total_created > 0 else 0.0
    
    @property
    def average_creation_time(self) -> float:
        """平均连接创建时间"""
        return self.creation_time_total / self.total_created if self.total_created > 0 else 0.0


class ConnectionPool(Generic[T], ABC):
    """泛型连接池基类"""
    
    def __init__(
        self,
        name: str,
        connection_type: ConnectionType,
        max_size: int = 50,
        min_size: int = 5,
        max_idle_time: float = 300.0,  # 5分钟
        max_lifetime: float = 3600.0,  # 1小时
        health_check_interval: float = 60.0,  # 1分钟
        health_check_timeout: float = 5.0,
        retry_attempts: int = 3
    ):
        self.name = name
        self.connection_type = connection_type
        self.max_size = max_size
        self.min_size = min_size
        self.max_idle_time = max_idle_time
        self.max_lifetime = max_lifetime
        self.health_check_interval = health_check_interval
        self.health_check_timeout = health_check_timeout
        self.retry_attempts = retry_attempts
        
        # 连接存储
        self._pool: deque = deque()
        self._active_connections: Dict[str, T] = {}
        self._connection_info: Dict[str, ConnectionInfo] = {}
        
        # 线程安全
        self._lock = asyncio.Lock()
        self._thread_lock = threading.RLock()
        
        # 统计信息
        self.stats = ConnectionPoolStatistics(
            pool_name=name,
            connection_type=connection_type,
            max_size=max_size,
            current_size=0,
            active_connections=0,
            idle_connections=0,
            failed_connections=0
        )
        
        # 健康检查任务
        self._health_check_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(f"✅ 创建连接池: {name} ({connection_type.value}, 最大: {max_size})")
    
    async def start(self):
        """启动连接池"""
        if self._running:
            return
        
        self._running = True
        
        # 预创建最小连接数
        await self._ensure_min_connections()
        
        # 启动后台任务
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info(f"🚀 连接池 {self.name} 已启动")
    
    async def stop(self):
        """停止连接池"""
        if not self._running:
            return
        
        self._running = False
        
        # 取消后台任务
        if self._health_check_task:
            self._health_check_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()
        
        # 关闭所有连接
        await self._close_all_connections()
        
        logger.info(f"⏹️ 连接池 {self.name} 已停止")
    
    async def acquire(self, timeout: float = 10.0) -> T:
        """获取连接"""
        start_time = time.time()
        
        async with self._lock:
            # 尝试从池中获取连接
            connection = await self._get_from_pool()
            
            if connection:
                self.stats.cache_hits += 1
                self.stats.total_reused += 1
                self.stats.total_acquired += 1
                return connection
            
            # 池为空，创建新连接
            self.stats.cache_misses += 1
            connection = await self._create_new_connection(start_time)
            
            if connection:
                self.stats.total_acquired += 1
                return connection
            
            raise RuntimeError(f"无法获取连接，池 {self.name} 已达到最大容量")
    
    async def release(self, connection: T) -> bool:
        """归还连接到池"""
        if connection is None:
            return False
        
        async with self._lock:
            connection_id = self._get_connection_id(connection)
            
            # 检查连接是否来自此池
            if connection_id not in self._active_connections:
                logger.warning(f"尝试归还不属于池 {self.name} 的连接: {connection_id}")
                return False
            
            # 从活跃连接中移除
            del self._active_connections[connection_id]
            
            # 检查连接健康状态
            if await self._is_connection_healthy(connection):
                # 连接健康，归还到池
                if len(self._pool) < self.max_size:
                    info = self._connection_info[connection_id]
                    info.state = ConnectionState.IDLE
                    info.last_used_at = time.time()
                    
                    self._pool.append(connection)
                    self.stats.total_returned += 1
                    self._update_stats()
                    return True
                else:
                    # 池已满，关闭连接
                    await self._close_connection(connection)
                    return False
            else:
                # 连接不健康，关闭连接
                await self._close_connection(connection)
                return False
    
    async def _get_from_pool(self) -> Optional[T]:
        """从池中获取连接"""
        while self._pool:
            connection = self._pool.popleft()
            connection_id = self._get_connection_id(connection)
            
            # 检查连接是否仍然有效
            if connection_id in self._connection_info:
                info = self._connection_info[connection_id]
                
                # 检查连接是否过期
                if info.age_seconds > self.max_lifetime:
                    await self._close_connection(connection)
                    continue
                
                # 检查连接健康状态
                if await self._is_connection_healthy(connection):
                    info.mark_used()
                    info.state = ConnectionState.ACTIVE
                    self._active_connections[connection_id] = connection
                    self._update_stats()
                    return connection
                else:
                    await self._close_connection(connection)
                    continue
        
        return None
    
    async def _create_new_connection(self, start_time: float) -> Optional[T]:
        """创建新连接"""
        if self.stats.current_size >= self.max_size:
            return None
        
        try:
            connection = await self._create_connection()
            connection_id = self._get_connection_id(connection)
            
            # 创建连接信息
            info = ConnectionInfo(
                connection_id=connection_id,
                connection_type=self.connection_type,
                created_at=time.time(),
                last_used_at=time.time(),
                state=ConnectionState.ACTIVE
            )
            
            self._connection_info[connection_id] = info
            self._active_connections[connection_id] = connection
            
            # 更新统计
            creation_time = time.time() - start_time
            self.stats.total_created += 1
            self.stats.creation_time_total += creation_time
            self._update_stats()
            
            logger.debug(f"✅ 创建新连接: {connection_id} (耗时: {creation_time:.3f}s)")
            return connection
            
        except Exception as e:
            self.stats.total_failures += 1
            logger.error(f"❌ 创建连接失败: {e}")
            return None
    
    async def _ensure_min_connections(self):
        """确保最小连接数"""
        while len(self._pool) + len(self._active_connections) < self.min_size:
            try:
                connection = await self._create_connection()
                connection_id = self._get_connection_id(connection)
                
                info = ConnectionInfo(
                    connection_id=connection_id,
                    connection_type=self.connection_type,
                    created_at=time.time(),
                    last_used_at=time.time(),
                    state=ConnectionState.IDLE
                )
                
                self._connection_info[connection_id] = info
                self._pool.append(connection)
                self.stats.total_created += 1
                
            except Exception as e:
                logger.error(f"❌ 预创建连接失败: {e}")
                break
        
        self._update_stats()
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while self._running:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self._perform_health_checks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 健康检查循环错误: {e}")
    
    async def _cleanup_loop(self):
        """清理循环"""
        while self._running:
            try:
                await asyncio.sleep(60)  # 每分钟清理一次
                await self._cleanup_expired_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 清理循环错误: {e}")
    
    async def _perform_health_checks(self):
        """执行健康检查"""
        async with self._lock:
            # 检查空闲连接
            connections_to_check = list(self._pool)
            
            for connection in connections_to_check:
                connection_id = self._get_connection_id(connection)
                if connection_id in self._connection_info:
                    info = self._connection_info[connection_id]
                    info.state = ConnectionState.CHECKING
                    
                    start_time = time.time()
                    is_healthy = await self._is_connection_healthy(connection)
                    check_time = time.time() - start_time
                    
                    info.health_check_count += 1
                    self.stats.total_health_checks += 1
                    self.stats.health_check_time_total += check_time
                    
                    if is_healthy:
                        info.state = ConnectionState.IDLE
                    else:
                        info.state = ConnectionState.FAILED
                        info.error_count += 1
                        self._pool.remove(connection)
                        await self._close_connection(connection)
    
    async def _cleanup_expired_connections(self):
        """清理过期连接"""
        async with self._lock:
            current_time = time.time()
            connections_to_remove = []
            
            # 检查空闲连接
            for connection in list(self._pool):
                connection_id = self._get_connection_id(connection)
                if connection_id in self._connection_info:
                    info = self._connection_info[connection_id]
                    
                    # 检查是否过期
                    if (info.age_seconds > self.max_lifetime or 
                        info.idle_time_seconds > self.max_idle_time):
                        connections_to_remove.append(connection)
            
            # 移除过期连接
            for connection in connections_to_remove:
                self._pool.remove(connection)
                await self._close_connection(connection)
            
            # 确保最小连接数
            await self._ensure_min_connections()
    
    async def _close_connection(self, connection: T):
        """关闭连接"""
        connection_id = self._get_connection_id(connection)
        
        try:
            await self._do_close_connection(connection)
        except Exception as e:
            logger.error(f"❌ 关闭连接失败 {connection_id}: {e}")
        finally:
            # 清理连接信息
            if connection_id in self._connection_info:
                del self._connection_info[connection_id]
            if connection_id in self._active_connections:
                del self._active_connections[connection_id]
            
            self._update_stats()
    
    async def _close_all_connections(self):
        """关闭所有连接"""
        # 关闭空闲连接
        while self._pool:
            connection = self._pool.popleft()
            await self._close_connection(connection)
        
        # 关闭活跃连接
        for connection in list(self._active_connections.values()):
            await self._close_connection(connection)
    
    def _update_stats(self):
        """更新统计信息"""
        self.stats.current_size = len(self._pool) + len(self._active_connections)
        self.stats.active_connections = len(self._active_connections)
        self.stats.idle_connections = len(self._pool)
        
        # 计算失败连接数
        failed_count = 0
        for info in self._connection_info.values():
            if info.state == ConnectionState.FAILED:
                failed_count += 1
        self.stats.failed_connections = failed_count
    
    def get_statistics(self) -> ConnectionPoolStatistics:
        """获取池统计信息"""
        with self._thread_lock:
            self._update_stats()
            return self.stats
    
    def get_connection_details(self) -> List[Dict[str, Any]]:
        """获取连接详细信息"""
        details = []
        for connection_id, info in self._connection_info.items():
            details.append({
                'connection_id': connection_id,
                'type': info.connection_type.value,
                'state': info.state.value,
                'age_seconds': info.age_seconds,
                'idle_time_seconds': info.idle_time_seconds,
                'use_count': info.use_count,
                'health_check_count': info.health_check_count,
                'error_count': info.error_count,
                'metadata': info.metadata
            })
        return details
    
    # 抽象方法，子类必须实现
    @abstractmethod
    async def _create_connection(self) -> T:
        """创建新连接"""
        pass
    
    @abstractmethod
    async def _is_connection_healthy(self, connection: T) -> bool:
        """检查连接健康状态"""
        pass
    
    @abstractmethod
    async def _do_close_connection(self, connection: T):
        """关闭连接的具体实现"""
        pass
    
    @abstractmethod
    def _get_connection_id(self, connection: T) -> str:
        """获取连接ID"""
        pass


class WebSocketConnectionPool(ConnectionPool[websockets.WebSocketServerProtocol]):
    """WebSocket连接池"""
    
    def __init__(
        self,
        name: str,
        uri: str,
        max_size: int = 20,
        min_size: int = 2,
        **kwargs
    ):
        super().__init__(
            name=name,
            connection_type=ConnectionType.WEBSOCKET,
            max_size=max_size,
            min_size=min_size,
            **kwargs
        )
        self.uri = uri
        self.connect_kwargs = kwargs.get('connect_kwargs', {})
        
        # WebSocket特定配置
        self.ping_interval = kwargs.get('ping_interval', 20)
        self.ping_timeout = kwargs.get('ping_timeout', 10)
        self.close_timeout = kwargs.get('close_timeout', 10)
    
    async def _create_connection(self) -> websockets.WebSocketServerProtocol:
        """创建WebSocket连接"""
        try:
            # 设置WebSocket连接参数
            connect_kwargs = {
                'ping_interval': self.ping_interval,
                'ping_timeout': self.ping_timeout,
                'close_timeout': self.close_timeout,
                **self.connect_kwargs
            }
            
            connection = await websockets.connect(self.uri, **connect_kwargs)
            logger.debug(f"✅ WebSocket连接已建立: {self.uri}")
            return connection
            
        except Exception as e:
            logger.error(f"❌ WebSocket连接失败 {self.uri}: {e}")
            raise
    
    async def _is_connection_healthy(self, connection: websockets.WebSocketServerProtocol) -> bool:
        """检查WebSocket连接健康状态"""
        try:
            if connection.closed:
                return False
            
            # 发送ping检查连接
            pong_waiter = await connection.ping()
            await asyncio.wait_for(pong_waiter, timeout=self.health_check_timeout)
            return True
            
        except (ConnectionClosed, WebSocketException, asyncio.TimeoutError):
            return False
        except Exception as e:
            logger.warning(f"⚠️ WebSocket健康检查异常: {e}")
            return False
    
    async def _do_close_connection(self, connection: websockets.WebSocketServerProtocol):
        """关闭WebSocket连接"""
        try:
            if not connection.closed:
                await connection.close()
        except Exception as e:
            logger.warning(f"⚠️ 关闭WebSocket连接异常: {e}")
    
    def _get_connection_id(self, connection: websockets.WebSocketServerProtocol) -> str:
        """获取WebSocket连接ID"""
        return f"ws_{id(connection)}"


class HTTPConnectionPool(ConnectionPool[aiohttp.ClientSession]):
    """HTTP连接池"""
    
    def __init__(
        self,
        name: str,
        base_url: str = "",
        max_size: int = 50,
        min_size: int = 5,
        **kwargs
    ):
        # 提取HTTP特定参数
        http_kwargs = {
            k: v for k, v in kwargs.items() 
            if k in ['max_idle_time', 'max_lifetime', 'health_check_interval', 'health_check_timeout', 'retry_attempts']
        }
        
        super().__init__(
            name=name,
            connection_type=ConnectionType.HTTP,
            max_size=max_size,
            min_size=min_size,
            **http_kwargs
        )
        self.base_url = base_url
        
        # HTTP特定配置
        self.timeout = aiohttp.ClientTimeout(
            total=kwargs.get('total_timeout', 30),
            connect=kwargs.get('connect_timeout', 10),
            sock_read=kwargs.get('read_timeout', 10)
        )
        
        # TCP连接器配置
        self.connector_kwargs = {
            'limit': max_size,
            'limit_per_host': max_size // 2,
            'ttl_dns_cache': kwargs.get('dns_cache_ttl', 300),
            'use_dns_cache': True,
            'keepalive_timeout': kwargs.get('keepalive_timeout', 30),
            'enable_cleanup_closed': True,
            **kwargs.get('connector_kwargs', {})
        }
    
    async def _create_connection(self) -> aiohttp.ClientSession:
        """创建HTTP连接"""
        try:
            import os
            
            # 获取代理设置
            proxy = None
            http_proxy = os.getenv('http_proxy') or os.getenv('HTTP_PROXY')
            https_proxy = os.getenv('https_proxy') or os.getenv('HTTPS_PROXY')
            
            if https_proxy or http_proxy:
                proxy = https_proxy or http_proxy
                logger.debug(f"使用代理创建HTTP连接: {proxy}")
            
            connector = aiohttp.TCPConnector(**self.connector_kwargs)
            session = aiohttp.ClientSession(
                connector=connector,
                timeout=self.timeout,
                base_url=self.base_url
            )
            
            # 如果有代理，将其保存到session中以便后续使用
            if proxy:
                session._proxy = proxy
            
            logger.debug(f"✅ HTTP会话已创建: {self.base_url}")
            return session
            
        except Exception as e:
            logger.error(f"❌ HTTP会话创建失败: {e}")
            raise
    
    async def _is_connection_healthy(self, connection: aiohttp.ClientSession) -> bool:
        """检查HTTP连接健康状态"""
        try:
            if connection.closed:
                return False
            
            # 检查连接器状态
            if connection.connector.closed:
                return False
            
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ HTTP连接健康检查异常: {e}")
            return False
    
    async def _do_close_connection(self, connection: aiohttp.ClientSession):
        """关闭HTTP连接"""
        try:
            if not connection.closed:
                await connection.close()
        except Exception as e:
            logger.warning(f"⚠️ 关闭HTTP会话异常: {e}")
    
    def _get_connection_id(self, connection: aiohttp.ClientSession) -> str:
        """获取HTTP连接ID"""
        return f"http_{id(connection)}"


class ConnectionPoolManager:
    """连接池管理器"""
    
    def __init__(self):
        self._pools: Dict[str, ConnectionPool] = {}
        self._lock = threading.RLock()
        
        logger.info("✅ 连接池管理器已初始化")
    
    def create_websocket_pool(
        self,
        name: str,
        uri: str,
        max_size: int = 20,
        min_size: int = 2,
        **kwargs
    ) -> WebSocketConnectionPool:
        """创建WebSocket连接池"""
        with self._lock:
            if name in self._pools:
                raise ValueError(f"连接池 {name} 已存在")
            
            pool = WebSocketConnectionPool(
                name=name,
                uri=uri,
                max_size=max_size,
                min_size=min_size,
                **kwargs
            )
            
            self._pools[name] = pool
            return pool
    
    def create_http_pool(
        self,
        name: str,
        base_url: str = "",
        max_size: int = 50,
        min_size: int = 5,
        **kwargs
    ) -> HTTPConnectionPool:
        """创建HTTP连接池"""
        with self._lock:
            if name in self._pools:
                raise ValueError(f"连接池 {name} 已存在")
            
            # 过滤参数，只传递有效的参数
            valid_kwargs = {
                k: v for k, v in kwargs.items() 
                if k in ['max_idle_time', 'max_lifetime', 'health_check_interval', 'health_check_timeout', 'retry_attempts']
            }
            
            pool = HTTPConnectionPool(
                name=name,
                base_url=base_url,
                max_size=max_size,
                min_size=min_size,
                **valid_kwargs
            )
            
            # 将HTTP特定参数保存到pool中
            for key in ['total_timeout', 'connect_timeout', 'read_timeout', 'dns_cache_ttl', 'keepalive_timeout', 'connector_kwargs']:
                if key in kwargs:
                    setattr(pool, f'_{key}', kwargs[key])
            
            self._pools[name] = pool
            return pool
    
    def get_pool(self, name: str) -> Optional[ConnectionPool]:
        """获取连接池"""
        with self._lock:
            return self._pools.get(name)
    
    def remove_pool(self, name: str) -> bool:
        """移除连接池"""
        with self._lock:
            if name in self._pools:
                del self._pools[name]
                return True
            return False
    
    async def start_all_pools(self):
        """启动所有连接池"""
        for pool in self._pools.values():
            await pool.start()
        
        logger.info(f"🚀 已启动 {len(self._pools)} 个连接池")
    
    async def stop_all_pools(self):
        """停止所有连接池"""
        for pool in self._pools.values():
            await pool.stop()
        
        logger.info(f"⏹️ 已停止 {len(self._pools)} 个连接池")
    
    def get_all_statistics(self) -> Dict[str, ConnectionPoolStatistics]:
        """获取所有池的统计信息"""
        with self._lock:
            return {name: pool.get_statistics() for name, pool in self._pools.items()}
    
    def get_summary_statistics(self) -> Dict[str, Any]:
        """获取汇总统计信息"""
        all_stats = self.get_all_statistics()
        
        if not all_stats:
            return {
                'pools_count': 0,
                'total_connections': 0,
                'total_active': 0,
                'total_created': 0,
                'overall_hit_rate': 0.0,
                'overall_utilization': 0.0,
                'overall_reuse_rate': 0.0
            }
        
        total_connections = sum(stats.current_size for stats in all_stats.values())
        total_active = sum(stats.active_connections for stats in all_stats.values())
        total_created = sum(stats.total_created for stats in all_stats.values())
        total_reused = sum(stats.total_reused for stats in all_stats.values())
        
        avg_hit_rate = sum(stats.hit_rate for stats in all_stats.values()) / len(all_stats)
        avg_utilization = sum(stats.utilization_rate for stats in all_stats.values()) / len(all_stats)
        
        return {
            'pools_count': len(self._pools),
            'total_connections': total_connections,
            'total_active_connections': total_active,
            'total_idle_connections': total_connections - total_active,
            'total_connections_created': total_created,
            'total_connections_reused': total_reused,
            'overall_reuse_rate': total_reused / total_created if total_created > 0 else 0,
            'overall_hit_rate': avg_hit_rate,
            'overall_utilization_rate': avg_utilization,
            'connection_efficiency': {
                'reuse_improvement': min(total_reused / max(total_created - total_reused, 1) * 100, 500),
                'estimated_connection_savings': total_reused,
                'estimated_time_savings_seconds': total_reused * 0.1  # 假设每次连接建立节省100ms
            }
        }


# 全局连接池管理器实例
_connection_pool_manager: Optional[ConnectionPoolManager] = None


def get_connection_pool_manager() -> ConnectionPoolManager:
    """获取全局连接池管理器"""
    global _connection_pool_manager
    if _connection_pool_manager is None:
        _connection_pool_manager = ConnectionPoolManager()
    return _connection_pool_manager


# 便捷函数
async def create_websocket_pool(name: str, uri: str, **kwargs) -> WebSocketConnectionPool:
    """创建WebSocket连接池的便捷函数"""
    manager = get_connection_pool_manager()
    return manager.create_websocket_pool(name, uri, **kwargs)


async def create_http_pool(name: str, base_url: str = "", **kwargs) -> HTTPConnectionPool:
    """创建HTTP连接池的便捷函数"""
    manager = get_connection_pool_manager()
    return manager.create_http_pool(name, base_url, **kwargs)


async def get_websocket_connection(pool_name: str, timeout: float = 10.0):
    """获取WebSocket连接的便捷函数"""
    manager = get_connection_pool_manager()
    pool = manager.get_pool(pool_name)
    if pool and isinstance(pool, WebSocketConnectionPool):
        return await pool.acquire(timeout)
    raise ValueError(f"WebSocket连接池 {pool_name} 不存在")


async def get_http_connection(pool_name: str, timeout: float = 10.0):
    """获取HTTP连接的便捷函数"""
    manager = get_connection_pool_manager()
    pool = manager.get_pool(pool_name)
    if pool and isinstance(pool, HTTPConnectionPool):
        return await pool.acquire(timeout)
    raise ValueError(f"HTTP连接池 {pool_name} 不存在")


def get_connection_pool_summary() -> Dict[str, Any]:
    """获取连接池汇总信息的便捷函数"""
    manager = get_connection_pool_manager()
    return manager.get_summary_statistics()