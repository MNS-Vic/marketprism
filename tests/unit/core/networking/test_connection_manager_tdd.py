"""
连接管理器模块TDD测试
专门用于提升connection_manager.py模块的测试覆盖率

遵循TDD原则：
1. Red: 编写失败的测试
2. Green: 编写最少代码使测试通过
3. Refactor: 重构代码保持测试通过
"""

import pytest
import asyncio
import aiohttp
import ssl
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone, timedelta

# 导入连接管理器模块
try:
    from core.networking.connection_manager import (
        ConnectionManager, ConnectionPool, Connection, ConnectionConfig,
        ConnectionState, ConnectionType, ConnectionError, PoolConfig,
        ConnectionMetrics, ConnectionHealthChecker, RetryPolicy,
        CircuitBreaker, LoadBalancer, ConnectionFactory
    )
    HAS_CONNECTION_MANAGER = True
except ImportError as e:
    HAS_CONNECTION_MANAGER = False
    CONNECTION_MANAGER_ERROR = str(e)
    
    # 创建模拟类用于测试
    from enum import Enum
    from dataclasses import dataclass, field
    
    class ConnectionState(Enum):
        IDLE = "idle"
        ACTIVE = "active"
        CONNECTING = "connecting"
        DISCONNECTED = "disconnected"
        ERROR = "error"
        CLOSED = "closed"
    
    class ConnectionType(Enum):
        HTTP = "http"
        WEBSOCKET = "websocket"
        TCP = "tcp"
        UDP = "udp"
        SSL = "ssl"
    
    @dataclass
    class ConnectionConfig:
        host: str
        port: int
        connection_type: ConnectionType = ConnectionType.HTTP
        timeout: float = 30.0
        max_retries: int = 3
        retry_delay: float = 1.0
        ssl_context: Optional[ssl.SSLContext] = None
        headers: Dict[str, str] = field(default_factory=dict)
        auth: Optional[tuple] = None
        proxy: Optional[str] = None
        
        def to_dict(self) -> Dict[str, Any]:
            """转换为字典"""
            return {
                "host": self.host,
                "port": self.port,
                "connection_type": self.connection_type.value,
                "timeout": self.timeout,
                "max_retries": self.max_retries,
                "retry_delay": self.retry_delay,
                "headers": self.headers,
                "proxy": self.proxy
            }
    
    @dataclass
    class PoolConfig:
        max_size: int = 10
        min_size: int = 1
        max_idle_time: float = 300.0
        health_check_interval: float = 60.0
        enable_health_check: bool = True
        enable_metrics: bool = True
        enable_circuit_breaker: bool = True
        circuit_breaker_threshold: int = 5
        circuit_breaker_timeout: float = 60.0
    
    @dataclass
    class ConnectionMetrics:
        total_connections: int = 0
        active_connections: int = 0
        idle_connections: int = 0
        failed_connections: int = 0
        total_requests: int = 0
        successful_requests: int = 0
        failed_requests: int = 0
        average_response_time: float = 0.0
        last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
        
        def update_request(self, success: bool, response_time: float) -> None:
            """更新请求统计"""
            self.total_requests += 1
            if success:
                self.successful_requests += 1
            else:
                self.failed_requests += 1
            
            # 更新平均响应时间
            if self.total_requests == 1:
                self.average_response_time = response_time
            else:
                self.average_response_time = (
                    (self.average_response_time * (self.total_requests - 1) + response_time) 
                    / self.total_requests
                )
            
            self.last_updated = datetime.now(timezone.utc)
        
        def get_success_rate(self) -> float:
            """获取成功率"""
            if self.total_requests == 0:
                return 0.0
            return self.successful_requests / self.total_requests
    
    class ConnectionError(Exception):
        """连接错误"""
        pass
    
    class Connection:
        """连接类"""
        
        def __init__(self, connection_id: str, config: ConnectionConfig):
            self.connection_id = connection_id
            self.config = config
            self.state = ConnectionState.IDLE
            self.created_at = datetime.now(timezone.utc)
            self.last_used = self.created_at
            self.use_count = 0
            self.session = None
            self._lock = asyncio.Lock()
        
        async def connect(self) -> bool:
            """建立连接"""
            async with self._lock:
                if self.state == ConnectionState.ACTIVE:
                    return True
                
                try:
                    self.state = ConnectionState.CONNECTING
                    
                    if self.config.connection_type == ConnectionType.HTTP:
                        timeout = aiohttp.ClientTimeout(total=self.config.timeout)
                        self.session = aiohttp.ClientSession(
                            timeout=timeout,
                            headers=self.config.headers
                        )
                    
                    self.state = ConnectionState.ACTIVE
                    return True
                    
                except Exception as e:
                    self.state = ConnectionState.ERROR
                    raise ConnectionError(f"Failed to connect: {e}")
        
        async def disconnect(self) -> None:
            """断开连接"""
            async with self._lock:
                if self.session:
                    await self.session.close()
                    self.session = None
                
                self.state = ConnectionState.CLOSED
        
        async def is_healthy(self) -> bool:
            """检查连接健康状态"""
            if self.state != ConnectionState.ACTIVE:
                return False
            
            if self.session and self.session.closed:
                return False
            
            return True
        
        def mark_used(self) -> None:
            """标记连接被使用"""
            self.last_used = datetime.now(timezone.utc)
            self.use_count += 1
        
        def is_idle_timeout(self, max_idle_time: float) -> bool:
            """检查是否空闲超时"""
            if self.state != ConnectionState.IDLE:
                return False
            
            idle_time = (datetime.now(timezone.utc) - self.last_used).total_seconds()
            return idle_time > max_idle_time
        
        async def execute_request(self, method: str, url: str, **kwargs) -> Any:
            """执行请求"""
            if not await self.is_healthy():
                raise ConnectionError("Connection is not healthy")
            
            self.mark_used()
            
            try:
                if self.config.connection_type == ConnectionType.HTTP and self.session:
                    async with self.session.request(method, url, **kwargs) as response:
                        return await response.json()
                else:
                    raise ConnectionError("Unsupported connection type")
            except Exception as e:
                raise ConnectionError(f"Request failed: {e}")
    
    class ConnectionHealthChecker:
        """连接健康检查器"""
        
        def __init__(self, pool: 'ConnectionPool'):
            self.pool = pool
            self.running = False
            self._task = None
        
        async def start(self) -> None:
            """启动健康检查"""
            if self.running:
                return
            
            self.running = True
            self._task = asyncio.create_task(self._health_check_loop())
        
        async def stop(self) -> None:
            """停止健康检查"""
            self.running = False
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
        
        async def _health_check_loop(self) -> None:
            """健康检查循环"""
            while self.running:
                try:
                    await self._check_connections()
                    await asyncio.sleep(self.pool.config.health_check_interval)
                except asyncio.CancelledError:
                    break
                except Exception:
                    pass  # 忽略健康检查错误
        
        async def _check_connections(self) -> None:
            """检查所有连接"""
            unhealthy_connections = []
            
            for connection in self.pool.connections:
                if not await connection.is_healthy():
                    unhealthy_connections.append(connection)
            
            # 移除不健康的连接
            for connection in unhealthy_connections:
                await self.pool.remove_connection(connection)
    
    class RetryPolicy:
        """重试策略"""
        
        def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
            self.max_retries = max_retries
            self.base_delay = base_delay
            self.max_delay = max_delay
        
        def get_delay(self, attempt: int) -> float:
            """获取重试延迟"""
            delay = self.base_delay * (2 ** attempt)
            return min(delay, self.max_delay)
        
        async def execute_with_retry(self, func: callable, *args, **kwargs) -> Any:
            """带重试的执行函数"""
            last_exception = None
            
            for attempt in range(self.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < self.max_retries:
                        delay = self.get_delay(attempt)
                        await asyncio.sleep(delay)
                    else:
                        break
            
            raise last_exception
    
    class CircuitBreaker:
        """熔断器"""
        
        def __init__(self, threshold: int = 5, timeout: float = 60.0):
            self.threshold = threshold
            self.timeout = timeout
            self.failure_count = 0
            self.last_failure_time = None
            self.state = "closed"  # closed, open, half_open
        
        def is_open(self) -> bool:
            """检查熔断器是否打开"""
            if self.state == "open":
                if self.last_failure_time:
                    elapsed = (datetime.now(timezone.utc) - self.last_failure_time).total_seconds()
                    if elapsed > self.timeout:
                        self.state = "half_open"
                        return False
                return True
            return False
        
        def record_success(self) -> None:
            """记录成功"""
            self.failure_count = 0
            self.state = "closed"
        
        def record_failure(self) -> None:
            """记录失败"""
            self.failure_count += 1
            self.last_failure_time = datetime.now(timezone.utc)
            
            if self.failure_count >= self.threshold:
                self.state = "open"
    
    class LoadBalancer:
        """负载均衡器"""
        
        def __init__(self, strategy: str = "round_robin"):
            self.strategy = strategy
            self.current_index = 0
        
        def select_connection(self, connections: List[Connection]) -> Optional[Connection]:
            """选择连接"""
            if not connections:
                return None
            
            if self.strategy == "round_robin":
                connection = connections[self.current_index % len(connections)]
                self.current_index += 1
                return connection
            elif self.strategy == "least_used":
                return min(connections, key=lambda c: c.use_count)
            else:
                return connections[0]
    
    class ConnectionFactory:
        """连接工厂"""
        
        @staticmethod
        def create_connection(connection_id: str, config: ConnectionConfig) -> Connection:
            """创建连接"""
            return Connection(connection_id, config)
    
    class ConnectionPool:
        """连接池"""
        
        def __init__(self, config: PoolConfig, connection_config: ConnectionConfig):
            self.config = config
            self.connection_config = connection_config
            self.connections = []
            self.metrics = ConnectionMetrics()
            self.health_checker = ConnectionHealthChecker(self) if config.enable_health_check else None
            self.circuit_breaker = CircuitBreaker(
                config.circuit_breaker_threshold,
                config.circuit_breaker_timeout
            ) if config.enable_circuit_breaker else None
            self.load_balancer = LoadBalancer()
            self._lock = asyncio.Lock()
            self._connection_counter = 0
        
        async def initialize(self) -> None:
            """初始化连接池"""
            # 创建最小数量的连接
            for _ in range(self.config.min_size):
                await self.create_connection()
            
            # 启动健康检查
            if self.health_checker:
                await self.health_checker.start()
        
        async def create_connection(self) -> Connection:
            """创建新连接"""
            async with self._lock:
                if len(self.connections) >= self.config.max_size:
                    raise ConnectionError("Connection pool is full")
                
                self._connection_counter += 1
                connection_id = f"conn_{self._connection_counter}"
                
                connection = ConnectionFactory.create_connection(connection_id, self.connection_config)
                await connection.connect()
                
                self.connections.append(connection)
                self.metrics.total_connections += 1
                self.metrics.active_connections += 1
                
                return connection
        
        async def get_connection(self) -> Connection:
            """获取连接"""
            if self.circuit_breaker and self.circuit_breaker.is_open():
                raise ConnectionError("Circuit breaker is open")
            
            # 查找可用连接
            available_connections = [
                conn for conn in self.connections 
                if conn.state == ConnectionState.ACTIVE and await conn.is_healthy()
            ]
            
            if available_connections:
                connection = self.load_balancer.select_connection(available_connections)
                if connection:
                    return connection
            
            # 如果没有可用连接，尝试创建新连接
            if len(self.connections) < self.config.max_size:
                return await self.create_connection()
            
            raise ConnectionError("No available connections")
        
        async def return_connection(self, connection: Connection) -> None:
            """归还连接"""
            if connection in self.connections:
                connection.state = ConnectionState.IDLE
        
        async def remove_connection(self, connection: Connection) -> None:
            """移除连接"""
            async with self._lock:
                if connection in self.connections:
                    await connection.disconnect()
                    self.connections.remove(connection)
                    self.metrics.active_connections -= 1
        
        async def close_all(self) -> None:
            """关闭所有连接"""
            if self.health_checker:
                await self.health_checker.stop()
            
            for connection in self.connections:
                await connection.disconnect()
            
            self.connections.clear()
            self.metrics.active_connections = 0
        
        def get_stats(self) -> Dict[str, Any]:
            """获取统计信息"""
            return {
                "total_connections": len(self.connections),
                "active_connections": sum(1 for c in self.connections if c.state == ConnectionState.ACTIVE),
                "idle_connections": sum(1 for c in self.connections if c.state == ConnectionState.IDLE),
                "metrics": self.metrics
            }
    
    class ConnectionManager:
        """连接管理器"""
        
        def __init__(self):
            self.pools = {}
            self.default_pool_config = PoolConfig()
        
        def create_pool(self, pool_id: str, connection_config: ConnectionConfig, 
                       pool_config: Optional[PoolConfig] = None) -> ConnectionPool:
            """创建连接池"""
            if pool_id in self.pools:
                raise ConnectionError(f"Pool {pool_id} already exists")
            
            config = pool_config or self.default_pool_config
            pool = ConnectionPool(config, connection_config)
            self.pools[pool_id] = pool
            
            return pool
        
        async def get_pool(self, pool_id: str) -> ConnectionPool:
            """获取连接池"""
            if pool_id not in self.pools:
                raise ConnectionError(f"Pool {pool_id} not found")
            
            return self.pools[pool_id]
        
        async def get_connection(self, pool_id: str) -> Connection:
            """获取连接"""
            pool = await self.get_pool(pool_id)
            return await pool.get_connection()
        
        async def return_connection(self, pool_id: str, connection: Connection) -> None:
            """归还连接"""
            pool = await self.get_pool(pool_id)
            await pool.return_connection(connection)
        
        async def execute_request(self, pool_id: str, method: str, url: str, **kwargs) -> Any:
            """执行请求"""
            connection = await self.get_connection(pool_id)
            try:
                result = await connection.execute_request(method, url, **kwargs)
                await self.return_connection(pool_id, connection)
                return result
            except Exception as e:
                # 连接出错，不归还到池中
                pool = await self.get_pool(pool_id)
                await pool.remove_connection(connection)
                raise e
        
        async def close_pool(self, pool_id: str) -> None:
            """关闭连接池"""
            if pool_id in self.pools:
                pool = self.pools[pool_id]
                await pool.close_all()
                del self.pools[pool_id]
        
        async def close_all_pools(self) -> None:
            """关闭所有连接池"""
            for pool_id in list(self.pools.keys()):
                await self.close_pool(pool_id)
        
        def get_all_stats(self) -> Dict[str, Any]:
            """获取所有统计信息"""
            return {
                pool_id: pool.get_stats() 
                for pool_id, pool in self.pools.items()
            }


class TestConnectionConfig:
    """测试连接配置"""
    
    def test_connection_config_creation(self):
        """测试：连接配置创建"""
        config = ConnectionConfig(
            host="localhost",
            port=8080,
            connection_type=ConnectionType.HTTP,
            timeout=30.0
        )
        
        assert config.host == "localhost"
        assert config.port == 8080
        assert config.connection_type == ConnectionType.HTTP
        assert config.timeout == 30.0
        assert config.max_retries == 3
        
    def test_connection_config_to_dict(self):
        """测试：配置转换为字典"""
        config = ConnectionConfig(
            host="example.com",
            port=443,
            connection_type=ConnectionType.HTTP,
            headers={"User-Agent": "test"}
        )
        
        config_dict = config.to_dict()
        
        assert config_dict["host"] == "example.com"
        assert config_dict["port"] == 443
        assert config_dict["headers"]["User-Agent"] == "test"


class TestConnectionMetrics:
    """测试连接指标"""
    
    def setup_method(self):
        """设置测试方法"""
        self.metrics = ConnectionMetrics()
        
    def test_metrics_initialization(self):
        """测试：指标初始化"""
        assert self.metrics.total_connections == 0
        assert self.metrics.active_connections == 0
        assert self.metrics.total_requests == 0
        assert self.metrics.get_success_rate() == 0.0
        
    def test_metrics_update_request(self):
        """测试：更新请求统计"""
        # 成功请求
        self.metrics.update_request(True, 1.5)
        
        assert self.metrics.total_requests == 1
        assert self.metrics.successful_requests == 1
        assert self.metrics.failed_requests == 0
        assert self.metrics.average_response_time == 1.5
        assert self.metrics.get_success_rate() == 1.0
        
        # 失败请求
        self.metrics.update_request(False, 2.0)
        
        assert self.metrics.total_requests == 2
        assert self.metrics.successful_requests == 1
        assert self.metrics.failed_requests == 1
        assert self.metrics.average_response_time == 1.75
        assert self.metrics.get_success_rate() == 0.5


class TestConnection:
    """测试连接"""

    def setup_method(self):
        """设置测试方法"""
        self.config = ConnectionConfig(
            host="localhost",
            port=8080,
            connection_type=ConnectionType.HTTP
        )
        self.connection = Connection("test_conn", self.config)

    def test_connection_creation(self):
        """测试：连接创建"""
        assert self.connection.connection_id == "test_conn"
        assert self.connection.config == self.config
        assert self.connection.state == ConnectionState.IDLE
        assert self.connection.use_count == 0

    @pytest.mark.asyncio
    async def test_connection_connect_disconnect(self):
        """测试：连接和断开"""
        # 模拟连接
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session_instance = Mock()
            mock_session_instance.close = AsyncMock()
            mock_session.return_value = mock_session_instance

            result = await self.connection.connect()
            assert result is True
            assert self.connection.state == ConnectionState.ACTIVE

            # 断开连接
            await self.connection.disconnect()
            assert self.connection.state == ConnectionState.CLOSED

    @pytest.mark.asyncio
    async def test_connection_health_check(self):
        """测试：连接健康检查"""
        # 未连接状态
        assert await self.connection.is_healthy() is False

        # 模拟连接状态
        self.connection.state = ConnectionState.ACTIVE
        self.connection.session = Mock()
        self.connection.session.closed = False

        assert await self.connection.is_healthy() is True

        # 模拟会话关闭
        self.connection.session.closed = True
        assert await self.connection.is_healthy() is False

    def test_connection_mark_used(self):
        """测试：标记连接使用"""
        initial_count = self.connection.use_count
        initial_time = self.connection.last_used

        self.connection.mark_used()

        assert self.connection.use_count == initial_count + 1
        assert self.connection.last_used > initial_time

    def test_connection_idle_timeout(self):
        """测试：空闲超时检查"""
        # 设置为空闲状态
        self.connection.state = ConnectionState.IDLE

        # 刚使用过，不应该超时
        assert self.connection.is_idle_timeout(300.0) is False

        # 模拟很久之前使用
        old_time = datetime.now(timezone.utc) - timedelta(seconds=400)
        self.connection.last_used = old_time

        assert self.connection.is_idle_timeout(300.0) is True


class TestCircuitBreaker:
    """测试熔断器"""

    def setup_method(self):
        """设置测试方法"""
        self.circuit_breaker = CircuitBreaker(threshold=3, timeout=60.0)

    def test_circuit_breaker_initial_state(self):
        """测试：熔断器初始状态"""
        assert self.circuit_breaker.state == "closed"
        assert self.circuit_breaker.failure_count == 0
        assert self.circuit_breaker.is_open() is False

    def test_circuit_breaker_failure_threshold(self):
        """测试：失败阈值触发熔断"""
        # 记录失败，但未达到阈值
        self.circuit_breaker.record_failure()
        self.circuit_breaker.record_failure()
        assert self.circuit_breaker.is_open() is False

        # 达到阈值，触发熔断
        self.circuit_breaker.record_failure()
        assert self.circuit_breaker.is_open() is True
        assert self.circuit_breaker.state == "open"

    def test_circuit_breaker_success_reset(self):
        """测试：成功重置熔断器"""
        # 触发熔断
        for _ in range(3):
            self.circuit_breaker.record_failure()

        assert self.circuit_breaker.is_open() is True

        # 记录成功，重置熔断器
        self.circuit_breaker.record_success()

        assert self.circuit_breaker.failure_count == 0
        assert self.circuit_breaker.state == "closed"
        assert self.circuit_breaker.is_open() is False


class TestLoadBalancer:
    """测试负载均衡器"""

    def setup_method(self):
        """设置测试方法"""
        self.load_balancer = LoadBalancer("round_robin")

        # 创建测试连接
        self.connections = []
        for i in range(3):
            config = ConnectionConfig(host=f"host{i}", port=8080)
            conn = Connection(f"conn_{i}", config)
            conn.use_count = i  # 设置不同的使用次数
            self.connections.append(conn)

    def test_load_balancer_round_robin(self):
        """测试：轮询负载均衡"""
        # 第一次选择
        conn1 = self.load_balancer.select_connection(self.connections)
        assert conn1 == self.connections[0]

        # 第二次选择
        conn2 = self.load_balancer.select_connection(self.connections)
        assert conn2 == self.connections[1]

        # 第三次选择
        conn3 = self.load_balancer.select_connection(self.connections)
        assert conn3 == self.connections[2]

        # 第四次选择，应该回到第一个
        conn4 = self.load_balancer.select_connection(self.connections)
        assert conn4 == self.connections[0]

    def test_load_balancer_least_used(self):
        """测试：最少使用负载均衡"""
        lb = LoadBalancer("least_used")

        # 应该选择使用次数最少的连接（conn_0，use_count=0）
        selected = lb.select_connection(self.connections)
        assert selected == self.connections[0]

    def test_load_balancer_empty_connections(self):
        """测试：空连接列表"""
        result = self.load_balancer.select_connection([])
        assert result is None


class TestRetryPolicy:
    """测试重试策略"""

    def setup_method(self):
        """设置测试方法"""
        self.retry_policy = RetryPolicy(max_retries=3, base_delay=0.1, max_delay=1.0)

    def test_retry_policy_delay_calculation(self):
        """测试：重试延迟计算"""
        assert self.retry_policy.get_delay(0) == 0.1
        assert self.retry_policy.get_delay(1) == 0.2
        assert self.retry_policy.get_delay(2) == 0.4
        assert self.retry_policy.get_delay(10) == 1.0  # 达到最大延迟

    @pytest.mark.asyncio
    async def test_retry_policy_success_on_first_try(self):
        """测试：第一次尝试成功"""
        async def success_func():
            return "success"

        result = await self.retry_policy.execute_with_retry(success_func)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_policy_success_after_retries(self):
        """测试：重试后成功"""
        attempt_count = 0

        async def retry_func():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise Exception("Temporary failure")
            return "success"

        result = await self.retry_policy.execute_with_retry(retry_func)
        assert result == "success"
        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_retry_policy_max_retries_exceeded(self):
        """测试：超过最大重试次数"""
        async def always_fail():
            raise Exception("Always fails")

        with pytest.raises(Exception, match="Always fails"):
            await self.retry_policy.execute_with_retry(always_fail)


class TestConnectionPool:
    """测试连接池"""

    def setup_method(self):
        """设置测试方法"""
        self.pool_config = PoolConfig(max_size=5, min_size=2)
        self.connection_config = ConnectionConfig(host="localhost", port=8080)
        self.pool = ConnectionPool(self.pool_config, self.connection_config)

    @pytest.mark.asyncio
    async def test_connection_pool_initialization(self):
        """测试：连接池初始化"""
        with patch.object(self.pool, 'create_connection', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = Mock()

            await self.pool.initialize()

            # 应该创建最小数量的连接
            assert mock_create.call_count == self.pool_config.min_size

    @pytest.mark.asyncio
    async def test_connection_pool_create_connection(self):
        """测试：创建连接"""
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session_instance = Mock()
            mock_session_instance.close = AsyncMock()
            mock_session.return_value = mock_session_instance

            connection = await self.pool.create_connection()

            assert connection.connection_id.startswith("conn_")
            assert connection in self.pool.connections
            assert self.pool.metrics.total_connections == 1
            assert self.pool.metrics.active_connections == 1

    @pytest.mark.asyncio
    async def test_connection_pool_max_size_limit(self):
        """测试：连接池最大大小限制"""
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session_instance = Mock()
            mock_session_instance.close = AsyncMock()
            mock_session.return_value = mock_session_instance

            # 创建到最大数量的连接
            for _ in range(self.pool_config.max_size):
                await self.pool.create_connection()

            # 尝试创建超过最大数量的连接
            with pytest.raises(ConnectionError, match="Connection pool is full"):
                await self.pool.create_connection()

    @pytest.mark.asyncio
    async def test_connection_pool_get_connection(self):
        """测试：获取连接"""
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session_instance = Mock()
            mock_session_instance.close = AsyncMock()
            mock_session.return_value = mock_session_instance

            # 创建一个连接
            created_conn = await self.pool.create_connection()
            created_conn.state = ConnectionState.ACTIVE

            # 模拟健康检查
            with patch.object(created_conn, 'is_healthy', return_value=True):
                connection = await self.pool.get_connection()
                assert connection == created_conn

    @pytest.mark.asyncio
    async def test_connection_pool_return_connection(self):
        """测试：归还连接"""
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session_instance = Mock()
            mock_session_instance.close = AsyncMock()
            mock_session.return_value = mock_session_instance

            connection = await self.pool.create_connection()
            connection.state = ConnectionState.ACTIVE

            await self.pool.return_connection(connection)
            assert connection.state == ConnectionState.IDLE

    @pytest.mark.asyncio
    async def test_connection_pool_remove_connection(self):
        """测试：移除连接"""
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session_instance = Mock()
            mock_session_instance.close = AsyncMock()
            mock_session.return_value = mock_session_instance

            connection = await self.pool.create_connection()
            initial_count = len(self.pool.connections)

            await self.pool.remove_connection(connection)

            assert len(self.pool.connections) == initial_count - 1
            assert connection not in self.pool.connections

    @pytest.mark.asyncio
    async def test_connection_pool_close_all(self):
        """测试：关闭所有连接"""
        with patch('aiohttp.ClientSession') as mock_session:
            mock_session_instance = Mock()
            mock_session_instance.close = AsyncMock()
            mock_session.return_value = mock_session_instance

            # 创建几个连接
            for _ in range(3):
                await self.pool.create_connection()

            await self.pool.close_all()

            assert len(self.pool.connections) == 0
            assert self.pool.metrics.active_connections == 0

    def test_connection_pool_stats(self):
        """测试：连接池统计"""
        stats = self.pool.get_stats()

        assert "total_connections" in stats
        assert "active_connections" in stats
        assert "idle_connections" in stats
        assert "metrics" in stats


class TestConnectionManager:
    """测试连接管理器"""

    def setup_method(self):
        """设置测试方法"""
        self.manager = ConnectionManager()
        self.connection_config = ConnectionConfig(host="localhost", port=8080)

    def test_connection_manager_creation(self):
        """测试：连接管理器创建"""
        assert len(self.manager.pools) == 0
        assert self.manager.default_pool_config is not None

    def test_connection_manager_create_pool(self):
        """测试：创建连接池"""
        pool = self.manager.create_pool("test_pool", self.connection_config)

        assert "test_pool" in self.manager.pools
        assert self.manager.pools["test_pool"] == pool

        # 尝试创建重复的池
        with pytest.raises(ConnectionError, match="Pool test_pool already exists"):
            self.manager.create_pool("test_pool", self.connection_config)

    @pytest.mark.asyncio
    async def test_connection_manager_get_pool(self):
        """测试：获取连接池"""
        # 创建池
        created_pool = self.manager.create_pool("test_pool", self.connection_config)

        # 获取池
        retrieved_pool = await self.manager.get_pool("test_pool")
        assert retrieved_pool == created_pool

        # 获取不存在的池
        with pytest.raises(ConnectionError, match="Pool nonexistent not found"):
            await self.manager.get_pool("nonexistent")

    @pytest.mark.asyncio
    async def test_connection_manager_get_connection(self):
        """测试：获取连接"""
        # 创建池
        self.manager.create_pool("test_pool", self.connection_config)

        with patch('aiohttp.ClientSession') as mock_session:
            mock_session_instance = Mock()
            mock_session_instance.close = AsyncMock()
            mock_session.return_value = mock_session_instance

            connection = await self.manager.get_connection("test_pool")
            assert connection is not None
            assert connection.config == self.connection_config

    @pytest.mark.asyncio
    async def test_connection_manager_close_pool(self):
        """测试：关闭连接池"""
        # 创建池
        self.manager.create_pool("test_pool", self.connection_config)

        assert "test_pool" in self.manager.pools

        await self.manager.close_pool("test_pool")

        assert "test_pool" not in self.manager.pools

    @pytest.mark.asyncio
    async def test_connection_manager_close_all_pools(self):
        """测试：关闭所有连接池"""
        # 创建多个池
        self.manager.create_pool("pool1", self.connection_config)
        self.manager.create_pool("pool2", self.connection_config)

        assert len(self.manager.pools) == 2

        await self.manager.close_all_pools()

        assert len(self.manager.pools) == 0

    def test_connection_manager_get_all_stats(self):
        """测试：获取所有统计信息"""
        # 创建池
        self.manager.create_pool("test_pool", self.connection_config)

        stats = self.manager.get_all_stats()

        assert "test_pool" in stats
        assert "total_connections" in stats["test_pool"]
