"""
🔗 ConnectionPoolManager - 连接池管理器

数据库和HTTP连接池优化
提供连接池管理、健康检查、动态调整、监控统计等功能
"""

import asyncio
import time
import weakref
from typing import Dict, Any, Optional, List, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
import logging
from collections import defaultdict, deque
import aiohttp
import threading

logger = logging.getLogger(__name__)


class ConnectionType(Enum):
    """连接类型枚举"""
    HTTP = "http"
    HTTPS = "https"
    DATABASE = "database"
    REDIS = "redis"
    WEBSOCKET = "websocket"
    CUSTOM = "custom"


class ConnectionState(Enum):
    """连接状态枚举"""
    IDLE = "idle"              # 空闲
    ACTIVE = "active"          # 活跃
    BUSY = "busy"              # 忙碌
    ERROR = "error"            # 错误
    CLOSED = "closed"          # 已关闭
    CONNECTING = "connecting"   # 连接中


@dataclass
class ConnectionConfig:
    """连接配置"""
    min_size: int = 5                    # 最小连接数
    max_size: int = 100                  # 最大连接数
    max_idle_time: float = 300.0         # 最大空闲时间(秒)
    connect_timeout: float = 10.0        # 连接超时(秒)
    request_timeout: float = 30.0        # 请求超时(秒)
    health_check_interval: float = 60.0  # 健康检查间隔(秒)
    retry_attempts: int = 3              # 重试次数
    retry_delay: float = 1.0            # 重试延迟(秒)
    enable_monitoring: bool = True       # 启用监控
    enable_auto_scaling: bool = True     # 启用自动扩展


@dataclass
class ConnectionInfo:
    """连接信息"""
    id: str
    type: ConnectionType
    state: ConnectionState
    created_at: float
    last_used_at: float
    total_requests: int = 0
    failed_requests: int = 0
    response_times: deque = field(default_factory=lambda: deque(maxlen=100))
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def age(self) -> float:
        """连接年龄"""
        return time.time() - self.created_at
    
    @property
    def idle_time(self) -> float:
        """空闲时间"""
        return time.time() - self.last_used_at
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 1.0
        return (self.total_requests - self.failed_requests) / self.total_requests
    
    @property
    def avg_response_time(self) -> float:
        """平均响应时间"""
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)


@dataclass
class PoolStats:
    """连接池统计"""
    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    failed_connections: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_response_time: float = 0.0
    peak_connections: int = 0
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests
    
    @property
    def utilization_rate(self) -> float:
        """利用率"""
        if self.total_connections == 0:
            return 0.0
        return self.active_connections / self.total_connections


class Connection:
    """连接包装器"""
    
    def __init__(self, connection_id: str, conn_type: ConnectionType, 
                 raw_connection: Any, pool_manager: 'ConnectionPoolManager'):
        self.info = ConnectionInfo(
            id=connection_id,
            type=conn_type,
            state=ConnectionState.IDLE,
            created_at=time.time(),
            last_used_at=time.time()
        )
        self.raw_connection = raw_connection
        self.pool_manager = weakref.ref(pool_manager)
        self.lock = asyncio.Lock()
    
    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """执行操作"""
        async with self.lock:
            start_time = time.time()
            self.info.state = ConnectionState.ACTIVE
            self.info.last_used_at = start_time
            
            try:
                result = await func(self.raw_connection, *args, **kwargs)
                self.info.total_requests += 1
                response_time = time.time() - start_time
                self.info.response_times.append(response_time)
                self.info.state = ConnectionState.IDLE
                return result
            except Exception as e:
                self.info.failed_requests += 1
                self.info.total_requests += 1
                self.info.state = ConnectionState.ERROR
                raise e
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            if hasattr(self.raw_connection, 'ping'):
                await self.raw_connection.ping()
            elif hasattr(self.raw_connection, 'execute'):
                await self.raw_connection.execute("SELECT 1")
            return True
        except:
            self.info.state = ConnectionState.ERROR
            return False
    
    async def close(self):
        """关闭连接"""
        self.info.state = ConnectionState.CLOSED
        if hasattr(self.raw_connection, 'close'):
            await self.raw_connection.close()


class ConnectionPool:
    """连接池"""
    
    def __init__(self, name: str, conn_type: ConnectionType, 
                 config: ConnectionConfig, creator: Callable):
        self.name = name
        self.type = conn_type
        self.config = config
        self.creator = creator
        self.connections: Dict[str, Connection] = {}
        self.available: deque = deque()
        self.stats = PoolStats()
        self.lock = asyncio.Lock()
        self.is_running = False
        self.health_check_task: Optional[asyncio.Task] = None
        self.auto_scale_task: Optional[asyncio.Task] = None
        
        logger.info(f"连接池创建: {name}, type={conn_type.value}")
    
    async def start(self):
        """启动连接池"""
        if self.is_running:
            return
        
        self.is_running = True
        
        # 创建最小连接数
        await self._ensure_min_connections()
        
        # 启动健康检查
        if self.config.health_check_interval > 0:
            self.health_check_task = asyncio.create_task(self._health_check_loop())
        
        # 启动自动扩展
        if self.config.enable_auto_scaling:
            self.auto_scale_task = asyncio.create_task(self._auto_scale_loop())
        
        logger.info(f"连接池启动: {self.name}")
    
    async def stop(self):
        """停止连接池"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # 取消任务
        if self.health_check_task:
            self.health_check_task.cancel()
        if self.auto_scale_task:
            self.auto_scale_task.cancel()
        
        # 关闭所有连接
        for connection in list(self.connections.values()):
            await connection.close()
        
        self.connections.clear()
        self.available.clear()
        
        logger.info(f"连接池停止: {self.name}")
    
    async def acquire(self, timeout: Optional[float] = None) -> Connection:
        """获取连接"""
        timeout = timeout or self.config.connect_timeout
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            async with self.lock:
                # 检查可用连接
                while self.available:
                    conn_id = self.available.popleft()
                    if conn_id in self.connections:
                        connection = self.connections[conn_id]
                        if connection.info.state in [ConnectionState.IDLE, ConnectionState.ACTIVE]:
                            self.stats.active_connections += 1
                            self.stats.idle_connections -= 1
                            return connection
                        else:
                            # 移除无效连接
                            await self._remove_connection(conn_id)
                
                # 如果没有可用连接且未达到最大连接数，创建新连接
                if len(self.connections) < self.config.max_size:
                    connection = await self._create_connection()
                    if connection:
                        self.stats.active_connections += 1
                        return connection
            
            # 等待一小段时间后重试
            await asyncio.sleep(0.1)
        
        raise TimeoutError(f"获取连接超时: pool={self.name}, timeout={timeout}")
    
    async def release(self, connection: Connection):
        """释放连接"""
        async with self.lock:
            if connection.info.id in self.connections:
                if connection.info.state != ConnectionState.ERROR:
                    connection.info.state = ConnectionState.IDLE
                    self.available.append(connection.info.id)
                    self.stats.active_connections -= 1
                    self.stats.idle_connections += 1
                else:
                    # 移除错误连接
                    await self._remove_connection(connection.info.id)
    
    async def _create_connection(self) -> Optional[Connection]:
        """创建新连接"""
        try:
            raw_conn = await self.creator()
            conn_id = f"{self.name}_{len(self.connections)}_{time.time()}"
            connection = Connection(conn_id, self.type, raw_conn, None)
            
            self.connections[conn_id] = connection
            self.stats.total_connections += 1
            self.stats.peak_connections = max(self.stats.peak_connections, self.stats.total_connections)
            
            logger.debug(f"创建连接: pool={self.name}, id={conn_id}")
            return connection
        except Exception as e:
            logger.error(f"创建连接失败: pool={self.name}, error={e}")
            self.stats.failed_connections += 1
            return None
    
    async def _remove_connection(self, conn_id: str):
        """移除连接"""
        if conn_id in self.connections:
            connection = self.connections[conn_id]
            await connection.close()
            del self.connections[conn_id]
            self.stats.total_connections -= 1
            
            if connection.info.state == ConnectionState.ACTIVE:
                self.stats.active_connections -= 1
            elif connection.info.state == ConnectionState.IDLE:
                self.stats.idle_connections -= 1
            
            logger.debug(f"移除连接: pool={self.name}, id={conn_id}")
    
    async def _ensure_min_connections(self):
        """确保最小连接数"""
        while len(self.connections) < self.config.min_size:
            connection = await self._create_connection()
            if connection:
                self.available.append(connection.info.id)
                self.stats.idle_connections += 1
            else:
                break
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while self.is_running:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                await self._health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查失败: pool={self.name}, error={e}")
    
    async def _health_check(self):
        """健康检查"""
        async with self.lock:
            unhealthy_connections = []
            
            for conn_id, connection in self.connections.items():
                if not await connection.health_check():
                    unhealthy_connections.append(conn_id)
            
            # 移除不健康的连接
            for conn_id in unhealthy_connections:
                await self._remove_connection(conn_id)
            
            # 确保最小连接数
            await self._ensure_min_connections()
            
            if unhealthy_connections:
                logger.info(f"健康检查完成: pool={self.name}, removed={len(unhealthy_connections)}")
    
    async def _auto_scale_loop(self):
        """自动扩展循环"""
        while self.is_running:
            try:
                await asyncio.sleep(30)  # 每30秒检查一次
                await self._auto_scale()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"自动扩展失败: pool={self.name}, error={e}")
    
    async def _auto_scale(self):
        """自动扩展"""
        async with self.lock:
            # 清理空闲超时的连接
            idle_timeout_connections = []
            current_time = time.time()
            
            for conn_id, connection in self.connections.items():
                if (connection.info.state == ConnectionState.IDLE and 
                    connection.info.idle_time > self.config.max_idle_time and
                    len(self.connections) > self.config.min_size):
                    idle_timeout_connections.append(conn_id)
            
            for conn_id in idle_timeout_connections:
                await self._remove_connection(conn_id)
                if conn_id in self.available:
                    self.available.remove(conn_id)
            
            # 根据负载动态调整连接数
            utilization = self.stats.utilization_rate
            
            if utilization > 0.8 and len(self.connections) < self.config.max_size:
                # 高利用率，增加连接
                new_connections = min(5, self.config.max_size - len(self.connections))
                for _ in range(new_connections):
                    connection = await self._create_connection()
                    if connection:
                        self.available.append(connection.info.id)
                        self.stats.idle_connections += 1
            
            if idle_timeout_connections:
                logger.debug(f"自动扩展完成: pool={self.name}, "
                           f"removed={len(idle_timeout_connections)}, utilization={utilization:.2f}")


class ConnectionPoolManager:
    """
    🔗 连接池管理器
    
    管理多个连接池，提供连接获取、释放、监控、动态调整等功能
    """
    
    def __init__(self):
        self.pools: Dict[str, ConnectionPool] = {}
        self.default_config = ConnectionConfig()
        self.global_stats = {
            "total_pools": 0,
            "total_connections": 0,
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0
        }
        self.monitoring_task: Optional[asyncio.Task] = None
        self.is_running = False
        
        logger.info("ConnectionPoolManager初始化完成")
    
    async def start(self):
        """启动连接池管理器"""
        if self.is_running:
            return
        
        self.is_running = True
        
        # 启动所有连接池
        for pool in self.pools.values():
            await pool.start()
        
        # 启动监控任务
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        logger.info("ConnectionPoolManager已启动")
    
    async def stop(self):
        """停止连接池管理器"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # 取消监控任务
        if self.monitoring_task:
            self.monitoring_task.cancel()
        
        # 停止所有连接池
        for pool in self.pools.values():
            await pool.stop()
        
        logger.info("ConnectionPoolManager已停止")
    
    def create_pool(self, name: str, conn_type: ConnectionType, 
                   creator: Callable, config: Optional[ConnectionConfig] = None) -> ConnectionPool:
        """创建连接池"""
        if name in self.pools:
            raise ValueError(f"连接池已存在: {name}")
        
        pool_config = config or self.default_config
        pool = ConnectionPool(name, conn_type, pool_config, creator)
        self.pools[name] = pool
        self.global_stats["total_pools"] += 1
        
        if self.is_running:
            asyncio.create_task(pool.start())
        
        logger.info(f"连接池创建: {name}, type={conn_type.value}")
        return pool
    
    async def remove_pool(self, name: str):
        """移除连接池"""
        if name not in self.pools:
            return
        
        pool = self.pools[name]
        await pool.stop()
        del self.pools[name]
        self.global_stats["total_pools"] -= 1
        
        logger.info(f"连接池移除: {name}")
    
    async def get_connection(self, pool_name: str, timeout: Optional[float] = None) -> Connection:
        """获取连接"""
        if pool_name not in self.pools:
            raise ValueError(f"连接池不存在: {pool_name}")
        
        pool = self.pools[pool_name]
        connection = await pool.acquire(timeout)
        self.global_stats["total_connections"] += 1
        
        return connection
    
    async def release_connection(self, pool_name: str, connection: Connection):
        """释放连接"""
        if pool_name not in self.pools:
            return
        
        pool = self.pools[pool_name]
        await pool.release(connection)
    
    def get_pool_stats(self, pool_name: Optional[str] = None) -> Dict[str, Any]:
        """获取连接池统计"""
        if pool_name:
            if pool_name not in self.pools:
                return {}
            
            pool = self.pools[pool_name]
            return {
                "name": pool_name,
                "type": pool.type.value,
                "total_connections": pool.stats.total_connections,
                "active_connections": pool.stats.active_connections,
                "idle_connections": pool.stats.idle_connections,
                "failed_connections": pool.stats.failed_connections,
                "utilization_rate": pool.stats.utilization_rate,
                "success_rate": pool.stats.success_rate,
                "peak_connections": pool.stats.peak_connections
            }
        else:
            return {
                pool_name: {
                    "type": pool.type.value,
                    "total_connections": pool.stats.total_connections,
                    "active_connections": pool.stats.active_connections,
                    "idle_connections": pool.stats.idle_connections,
                    "utilization_rate": pool.stats.utilization_rate,
                    "success_rate": pool.stats.success_rate
                }
                for pool_name, pool in self.pools.items()
            }
    
    def get_global_stats(self) -> Dict[str, Any]:
        """获取全局统计"""
        total_connections = sum(pool.stats.total_connections for pool in self.pools.values())
        active_connections = sum(pool.stats.active_connections for pool in self.pools.values())
        total_requests = sum(pool.stats.total_requests for pool in self.pools.values())
        successful_requests = sum(pool.stats.successful_requests for pool in self.pools.values())
        
        return {
            "total_pools": len(self.pools),
            "total_connections": total_connections,
            "active_connections": active_connections,
            "idle_connections": total_connections - active_connections,
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "success_rate": successful_requests / total_requests if total_requests > 0 else 1.0,
            "avg_utilization": sum(pool.stats.utilization_rate for pool in self.pools.values()) / len(self.pools) if self.pools else 0
        }
    
    def get_optimization_suggestions(self) -> List[str]:
        """获取优化建议"""
        suggestions = []
        
        for name, pool in self.pools.items():
            utilization = pool.stats.utilization_rate
            success_rate = pool.stats.success_rate
            
            if utilization > 0.9:
                suggestions.append(f"连接池 {name} 利用率过高 ({utilization:.1%})，建议增加最大连接数")
            elif utilization < 0.3:
                suggestions.append(f"连接池 {name} 利用率偏低 ({utilization:.1%})，可以考虑减少最小连接数")
            
            if success_rate < 0.95:
                suggestions.append(f"连接池 {name} 成功率偏低 ({success_rate:.1%})，建议检查连接健康状态")
            
            if pool.stats.failed_connections > pool.stats.total_connections * 0.1:
                suggestions.append(f"连接池 {name} 失败连接过多，建议检查网络和配置")
        
        return suggestions
    
    async def _monitoring_loop(self):
        """监控循环"""
        while self.is_running:
            try:
                await asyncio.sleep(60)  # 每分钟更新一次
                await self._update_global_stats()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控更新失败: {e}")
    
    async def _update_global_stats(self):
        """更新全局统计"""
        stats = self.get_global_stats()
        self.global_stats.update(stats)
        
        # 记录关键指标
        logger.debug(f"连接池监控: pools={stats['total_pools']}, "
                    f"connections={stats['total_connections']}, "
                    f"utilization={stats['avg_utilization']:.2f}")


# 工具函数

async def create_http_connection() -> aiohttp.ClientSession:
    """创建HTTP连接"""
    return aiohttp.ClientSession()


async def create_database_connection() -> Any:
    """创建数据库连接（示例）"""
    # 这里应该根据实际数据库类型实现
    pass


# 使用示例装饰器
def with_connection(pool_name: str):
    """连接装饰器"""
    def decorator(func):
        async def wrapper(self, *args, **kwargs):
            connection = await self.connection_manager.get_connection(pool_name)
            try:
                return await func(self, connection, *args, **kwargs)
            finally:
                await self.connection_manager.release_connection(pool_name, connection)
        return wrapper
    return decorator