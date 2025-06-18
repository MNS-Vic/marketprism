"""
MarketPrism 网络和存储集成测试

测试网络连接、数据传输和存储系统的集成
"""

import asyncio
import pytest
import time
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, List, Any, Optional

# 导入核心模块
try:
    from core.reliability.rate_limiter import AdaptiveRateLimiter, RateLimitConfig
    from core.reliability.retry_handler import ExponentialBackoffRetry, RetryPolicy
    from core.config.unified_config_manager import UnifiedConfigManager
    HAS_CORE_MODULES = True
except ImportError:
    HAS_CORE_MODULES = False


class MockWebSocketConnection:
    """模拟WebSocket连接"""
    
    def __init__(self, url: str):
        self.url = url
        self.connected = False
        self.message_queue = asyncio.Queue()
        self.error_rate = 0.0  # 错误率
        self.latency = 0.01  # 延迟（秒）
        
    async def connect(self):
        """连接WebSocket"""
        await asyncio.sleep(self.latency)
        if self.error_rate > 0 and time.time() % 1 < self.error_rate:
            raise ConnectionError("WebSocket connection failed")
        self.connected = True
        
    async def disconnect(self):
        """断开连接"""
        self.connected = False
        
    async def send_message(self, message: Dict[str, Any]):
        """发送消息"""
        if not self.connected:
            raise ConnectionError("WebSocket not connected")
            
        await asyncio.sleep(self.latency)
        
        # 模拟发送错误
        if self.error_rate > 0 and time.time() % 1 < self.error_rate:
            raise TimeoutError("Message send timeout")
            
    async def receive_message(self) -> Optional[Dict[str, Any]]:
        """接收消息"""
        if not self.connected:
            raise ConnectionError("WebSocket not connected")
            
        try:
            # 等待消息，带超时
            message = await asyncio.wait_for(
                self.message_queue.get(), 
                timeout=1.0
            )
            return message
        except asyncio.TimeoutError:
            return None
            
    async def simulate_market_data_stream(self, symbols: List[str]):
        """模拟市场数据流"""
        if not self.connected:
            return
            
        for symbol in symbols:
            message = {
                "type": "ticker",
                "symbol": symbol,
                "price": 45000.0 + (time.time() % 1000),
                "volume": 1234.56,
                "timestamp": int(time.time() * 1000)
            }
            await self.message_queue.put(message)
            await asyncio.sleep(0.1)


class MockHTTPSession:
    """模拟HTTP会话"""
    
    def __init__(self):
        self.request_count = 0
        self.error_rate = 0.0
        self.latency = 0.05
        
    async def get(self, url: str, **kwargs) -> Dict[str, Any]:
        """GET请求"""
        self.request_count += 1
        await asyncio.sleep(self.latency)
        
        # 模拟HTTP错误
        if self.error_rate > 0 and time.time() % 1 < self.error_rate:
            raise Exception("HTTP request failed")
            
        # 模拟API响应
        if "market_data" in url:
            return {
                "status": "success",
                "data": {
                    "symbol": "BTC/USDT",
                    "price": 45000.0,
                    "volume": 1234.56,
                    "timestamp": int(time.time() * 1000)
                }
            }
        elif "symbols" in url:
            return {
                "status": "success", 
                "data": ["BTC/USDT", "ETH/USDT", "ADA/USDT"]
            }
            
        return {"status": "success", "data": {}}
        
    async def post(self, url: str, data: Any = None, **kwargs) -> Dict[str, Any]:
        """POST请求"""
        self.request_count += 1
        await asyncio.sleep(self.latency)
        
        if self.error_rate > 0 and time.time() % 1 < self.error_rate:
            raise Exception("HTTP POST failed")
            
        return {"status": "success", "message": "Data posted"}


class MockStorageBackend:
    """模拟存储后端"""
    
    def __init__(self, backend_type: str = "clickhouse"):
        self.backend_type = backend_type
        self.connected = False
        self.stored_data = []
        self.error_rate = 0.0
        self.write_latency = 0.02
        self.read_latency = 0.01
        
    async def connect(self):
        """连接存储后端"""
        await asyncio.sleep(0.1)
        if self.error_rate > 0 and time.time() % 1 < self.error_rate:
            raise ConnectionError(f"Failed to connect to {self.backend_type}")
        self.connected = True
        
    async def disconnect(self):
        """断开连接"""
        self.connected = False
        
    async def write_batch(self, data: List[Dict[str, Any]]):
        """批量写入数据"""
        if not self.connected:
            raise ConnectionError(f"Not connected to {self.backend_type}")
            
        await asyncio.sleep(self.write_latency * len(data))
        
        if self.error_rate > 0 and time.time() % 1 < self.error_rate:
            raise Exception("Write operation failed")
            
        # 添加写入时间戳
        for item in data:
            item["written_at"] = datetime.utcnow().isoformat()
            
        self.stored_data.extend(data)
        
    async def read_data(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """读取数据"""
        if not self.connected:
            raise ConnectionError(f"Not connected to {self.backend_type}")
            
        await asyncio.sleep(self.read_latency)
        
        if self.error_rate > 0 and time.time() % 1 < self.error_rate:
            raise Exception("Read operation failed")
            
        # 简单的查询过滤
        results = self.stored_data.copy()
        if "symbol" in query:
            results = [item for item in results if item.get("symbol") == query["symbol"]]
        if "exchange" in query:
            results = [item for item in results if item.get("exchange") == query["exchange"]]
            
        return results
        
    def get_stats(self) -> Dict[str, Any]:
        """获取存储统计"""
        return {
            "backend_type": self.backend_type,
            "connected": self.connected,
            "total_records": len(self.stored_data),
            "error_rate": self.error_rate
        }


class NetworkingStorageIntegrator:
    """网络和存储集成器"""
    
    def __init__(self):
        self.http_session = MockHTTPSession()
        self.websocket_connections = {}
        self.storage_backends = {}
        self.rate_limiter = None
        self.retry_handler = None
        
    async def initialize(self):
        """初始化集成器"""
        if HAS_CORE_MODULES:
            # 初始化限流器
            rate_config = RateLimitConfig(max_requests_per_second=20)
            self.rate_limiter = AdaptiveRateLimiter("integrator", rate_config)
            
            # 初始化重试处理器
            self.retry_handler = ExponentialBackoffRetry("integrator")
            
    async def add_websocket_connection(self, name: str, url: str):
        """添加WebSocket连接"""
        ws = MockWebSocketConnection(url)
        await ws.connect()
        self.websocket_connections[name] = ws
        
    async def add_storage_backend(self, name: str, backend_type: str = "clickhouse"):
        """添加存储后端"""
        storage = MockStorageBackend(backend_type)
        await storage.connect()
        self.storage_backends[name] = storage
        
    async def fetch_rest_data(self, exchange: str, endpoint: str) -> Dict[str, Any]:
        """通过REST API获取数据"""
        url = f"https://api.{exchange}.com/{endpoint}"
        
        # 应用限流
        if self.rate_limiter:
            await self.rate_limiter.acquire_permit("rest_api")
            
        # 带重试的请求
        if self.retry_handler:
            policy = RetryPolicy(max_attempts=3, base_delay=0.1)
            return await self.retry_handler.retry_with_backoff(
                lambda: self.http_session.get(url),
                exchange,
                f"rest_{endpoint}"
            )
        else:
            return await self.http_session.get(url)
            
    async def stream_websocket_data(self, connection_name: str, symbols: List[str], duration: float = 5.0):
        """流式获取WebSocket数据"""
        if connection_name not in self.websocket_connections:
            raise ValueError(f"WebSocket connection {connection_name} not found")
            
        ws = self.websocket_connections[connection_name]
        
        # 启动数据流模拟
        stream_task = asyncio.create_task(
            ws.simulate_market_data_stream(symbols)
        )
        
        collected_data = []
        start_time = time.time()
        
        try:
            while time.time() - start_time < duration:
                message = await ws.receive_message()
                if message:
                    message["connection"] = connection_name
                    message["received_at"] = datetime.utcnow().isoformat()
                    collected_data.append(message)
                    
        finally:
            stream_task.cancel()
            try:
                await stream_task
            except asyncio.CancelledError:
                pass
                
        return collected_data
        
    async def store_data_to_backend(self, backend_name: str, data: List[Dict[str, Any]]):
        """存储数据到后端"""
        if backend_name not in self.storage_backends:
            raise ValueError(f"Storage backend {backend_name} not found")
            
        storage = self.storage_backends[backend_name]
        
        # 分批存储
        batch_size = 100
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            
            if self.retry_handler:
                policy = RetryPolicy(max_attempts=3, base_delay=0.1)
                await self.retry_handler.retry_with_backoff(
                    lambda: storage.write_batch(batch),
                    backend_name,
                    "write_batch"
                )
            else:
                await storage.write_batch(batch)
                
    async def query_data_from_backend(self, backend_name: str, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从后端查询数据"""
        if backend_name not in self.storage_backends:
            raise ValueError(f"Storage backend {backend_name} not found")
            
        storage = self.storage_backends[backend_name]
        
        if self.retry_handler:
            policy = RetryPolicy(max_attempts=3, base_delay=0.1)
            return await self.retry_handler.retry_with_backoff(
                lambda: storage.read_data(query),
                backend_name,
                "read_data"
            )
        else:
            return await storage.read_data(query)
            
    async def shutdown(self):
        """关闭集成器"""
        # 断开WebSocket连接
        for ws in self.websocket_connections.values():
            await ws.disconnect()
            
        # 断开存储后端
        for storage in self.storage_backends.values():
            await storage.disconnect()


@pytest.mark.integration
@pytest.mark.skipif(not HAS_CORE_MODULES, reason="核心模块不可用")
class TestNetworkingStorageIntegration:
    """网络和存储集成测试"""
    
    @pytest.fixture
    async def integrator(self):
        """创建集成器"""
        integrator = NetworkingStorageIntegrator()
        await integrator.initialize()
        yield integrator
        await integrator.shutdown()
        
    async def test_rest_api_integration(self, integrator):
        """测试REST API集成"""
        # 获取市场数据
        market_data = await integrator.fetch_rest_data("binance", "market_data")
        
        # 验证数据
        assert market_data["status"] == "success"
        assert "data" in market_data
        assert "symbol" in market_data["data"]
        
        # 获取交易对列表
        symbols_data = await integrator.fetch_rest_data("binance", "symbols")
        assert symbols_data["status"] == "success"
        assert len(symbols_data["data"]) > 0
        
    async def test_websocket_streaming_integration(self, integrator):
        """测试WebSocket流式集成"""
        # 添加WebSocket连接
        await integrator.add_websocket_connection("binance_ws", "wss://stream.binance.com")
        
        # 流式获取数据
        symbols = ["BTC/USDT", "ETH/USDT"]
        stream_data = await integrator.stream_websocket_data("binance_ws", symbols, duration=2.0)
        
        # 验证流式数据
        assert len(stream_data) > 0
        assert all("connection" in item for item in stream_data)
        assert all("received_at" in item for item in stream_data)
        assert all(item["type"] == "ticker" for item in stream_data)
        
    async def test_storage_backend_integration(self, integrator):
        """测试存储后端集成"""
        # 添加存储后端
        await integrator.add_storage_backend("primary_db", "clickhouse")
        
        # 准备测试数据
        test_data = [
            {
                "symbol": "BTC/USDT",
                "price": 45000.0,
                "volume": 1234.56,
                "exchange": "binance",
                "timestamp": int(time.time() * 1000)
            },
            {
                "symbol": "ETH/USDT", 
                "price": 3000.0,
                "volume": 5678.90,
                "exchange": "binance",
                "timestamp": int(time.time() * 1000)
            }
        ]
        
        # 存储数据
        await integrator.store_data_to_backend("primary_db", test_data)
        
        # 查询数据
        query_result = await integrator.query_data_from_backend(
            "primary_db", 
            {"symbol": "BTC/USDT"}
        )
        
        # 验证查询结果
        assert len(query_result) == 1
        assert query_result[0]["symbol"] == "BTC/USDT"
        assert "written_at" in query_result[0]
        
    async def test_end_to_end_data_flow(self, integrator):
        """测试端到端数据流"""
        # 设置基础设施
        await integrator.add_websocket_connection("test_ws", "wss://test.com")
        await integrator.add_storage_backend("test_db", "clickhouse")
        
        # 1. 通过REST API获取初始数据
        rest_data = await integrator.fetch_rest_data("test_exchange", "market_data")
        
        # 2. 通过WebSocket获取实时数据
        symbols = ["BTC/USDT"]
        stream_data = await integrator.stream_websocket_data("test_ws", symbols, duration=1.0)
        
        # 3. 合并数据
        all_data = []
        if rest_data.get("data"):
            rest_item = rest_data["data"].copy()
            rest_item["source"] = "rest"
            all_data.append(rest_item)
            
        for item in stream_data:
            item["source"] = "websocket"
            all_data.append(item)
            
        # 4. 存储所有数据
        await integrator.store_data_to_backend("test_db", all_data)
        
        # 5. 验证存储结果
        stored_data = await integrator.query_data_from_backend("test_db", {})
        
        assert len(stored_data) == len(all_data)
        sources = {item["source"] for item in stored_data}
        assert "rest" in sources or "websocket" in sources
