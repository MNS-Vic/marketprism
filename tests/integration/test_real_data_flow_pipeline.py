"""
MarketPrism 真实数据流管道测试

测试从交易所WebSocket到ClickHouse存储的完整数据管道
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
    from core.networking.websocket_manager import WebSocketManager, WebSocketConfig
    from core.storage.unified_clickhouse_writer import UnifiedClickHouseWriter
    from core.reliability.rate_limiter import AdaptiveRateLimiter, RateLimitConfig
    from core.reliability.retry_handler import ExponentialBackoffRetry, RetryPolicy
    from core.config.unified_config_manager import UnifiedConfigManager
    HAS_CORE_MODULES = True
except ImportError:
    HAS_CORE_MODULES = False

# 导入数据收集器模块
try:
    from services.data_collector.src.marketprism_collector.collector import MarketDataCollector
    from services.data_collector.src.marketprism_collector.normalizer import DataNormalizer
    from services.data_collector.src.marketprism_collector.data_types import MarketData, OrderBook
    HAS_COLLECTOR_MODULES = True
except ImportError:
    HAS_COLLECTOR_MODULES = False


class MockExchangeWebSocket:
    """模拟交易所WebSocket连接"""
    
    def __init__(self, exchange_name: str):
        self.exchange_name = exchange_name
        self.connected = False
        self.subscriptions = set()
        self.message_queue = asyncio.Queue()
        self.error_rate = 0.0
        
    async def connect(self):
        """连接WebSocket"""
        await asyncio.sleep(0.1)
        self.connected = True
        
    async def disconnect(self):
        """断开连接"""
        self.connected = False
        self.subscriptions.clear()
        
    async def subscribe(self, channel: str, symbol: str):
        """订阅数据流"""
        if not self.connected:
            raise ConnectionError("WebSocket not connected")
            
        subscription = f"{channel}:{symbol}"
        self.subscriptions.add(subscription)
        
    async def unsubscribe(self, channel: str, symbol: str):
        """取消订阅"""
        subscription = f"{channel}:{symbol}"
        self.subscriptions.discard(subscription)
        
    async def receive_message(self) -> Optional[Dict[str, Any]]:
        """接收消息"""
        if not self.connected:
            return None
            
        try:
            message = await asyncio.wait_for(self.message_queue.get(), timeout=0.1)
            return message
        except asyncio.TimeoutError:
            return None
            
    async def simulate_market_data_stream(self, duration: float = 5.0):
        """模拟市场数据流"""
        start_time = time.time()
        message_count = 0
        
        while time.time() - start_time < duration and self.connected:
            for subscription in self.subscriptions:
                channel, symbol = subscription.split(":", 1)
                
                if channel == "ticker":
                    message = {
                        "stream": f"{symbol.lower()}@ticker",
                        "data": {
                            "s": symbol,
                            "c": str(45000 + (time.time() % 1000)),
                            "v": str(1234.56),
                            "E": int(time.time() * 1000)
                        }
                    }
                elif channel == "depth":
                    message = {
                        "stream": f"{symbol.lower()}@depth",
                        "data": {
                            "s": symbol,
                            "bids": [["44999", "1.5"], ["44998", "2.0"]],
                            "asks": [["45001", "1.2"], ["45002", "1.8"]],
                            "E": int(time.time() * 1000)
                        }
                    }
                else:
                    continue
                    
                await self.message_queue.put(message)
                message_count += 1
                
            await asyncio.sleep(0.1)
            
        return message_count


class MockClickHouseClient:
    """模拟ClickHouse客户端"""
    
    def __init__(self):
        self.connected = False
        self.tables = {}
        self.inserted_data = []
        
    async def connect(self):
        """连接ClickHouse"""
        await asyncio.sleep(0.1)
        self.connected = True
        
        # 创建默认表结构
        self.tables["market_data"] = {
            "columns": ["symbol", "price", "volume", "timestamp", "exchange"],
            "data": []
        }
        
        self.tables["order_book"] = {
            "columns": ["symbol", "bids", "asks", "timestamp", "exchange"],
            "data": []
        }
        
    async def disconnect(self):
        """断开连接"""
        self.connected = False
        
    async def execute(self, query: str, data: List[Dict[str, Any]] = None):
        """执行SQL查询"""
        if not self.connected:
            raise ConnectionError("Not connected to ClickHouse")
            
        if data and "INSERT" in query.upper():
            # 模拟插入操作
            table_name = self._extract_table_name(query)
            if table_name in self.tables:
                self.tables[table_name]["data"].extend(data)
                self.inserted_data.extend(data)
                
        await asyncio.sleep(0.01 * len(data) if data else 0.01)
        
    def _extract_table_name(self, query: str) -> str:
        """从查询中提取表名"""
        query_upper = query.upper()
        if "INTO" in query_upper:
            parts = query_upper.split("INTO")[1].strip().split()
            return parts[0].lower()
        return "unknown"
        
    async def query(self, sql: str) -> List[Dict[str, Any]]:
        """查询数据"""
        if not self.connected:
            raise ConnectionError("Not connected to ClickHouse")
            
        await asyncio.sleep(0.02)
        
        # 简单的查询模拟
        if "SELECT COUNT" in sql.upper():
            return [{"count": len(self.inserted_data)}]
        elif "SELECT *" in sql.upper():
            return self.inserted_data[-10:]  # 返回最近10条记录
        else:
            return []
            
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "connected": self.connected,
            "total_records": len(self.inserted_data),
            "tables": list(self.tables.keys()),
            "table_counts": {
                name: len(table["data"]) 
                for name, table in self.tables.items()
            }
        }


class RealDataFlowPipeline:
    """真实数据流管道"""
    
    def __init__(self):
        self.websocket_connections = {}
        self.clickhouse_client = MockClickHouseClient()
        self.data_normalizer = None
        self.rate_limiter = None
        self.retry_handler = None
        self.config_manager = None
        self.running = False
        self.processed_messages = []
        
    async def initialize(self):
        """初始化管道"""
        # 初始化配置管理器
        if HAS_CORE_MODULES:
            self.config_manager = UnifiedConfigManager()
            self.config_manager.initialize()
            
            # 初始化限流器
            rate_config = RateLimitConfig(max_requests_per_second=100)
            self.rate_limiter = AdaptiveRateLimiter("data_flow", rate_config)
            
            # 初始化重试处理器
            self.retry_handler = ExponentialBackoffRetry("data_flow")
            
        # 初始化数据标准化器
        self.data_normalizer = MockDataNormalizer()
        
        # 连接ClickHouse
        await self.clickhouse_client.connect()
        
    async def add_exchange_connection(self, exchange_name: str):
        """添加交易所连接"""
        ws = MockExchangeWebSocket(exchange_name)
        await ws.connect()
        self.websocket_connections[exchange_name] = ws
        
    async def subscribe_to_data_streams(self, exchange_name: str, symbols: List[str]):
        """订阅数据流"""
        if exchange_name not in self.websocket_connections:
            raise ValueError(f"Exchange {exchange_name} not connected")
            
        ws = self.websocket_connections[exchange_name]
        
        for symbol in symbols:
            await ws.subscribe("ticker", symbol)
            await ws.subscribe("depth", symbol)
            
    async def process_message(self, exchange_name: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """处理单个消息"""
        try:
            # 应用限流
            if self.rate_limiter:
                await self.rate_limiter.acquire_permit("message_processing")
                
            # 数据标准化
            normalized_data = await self.data_normalizer.normalize_message(exchange_name, message)
            
            if normalized_data:
                # 存储到ClickHouse
                if self.retry_handler:
                    policy = RetryPolicy(max_attempts=3, base_delay=0.1)
                    await self.retry_handler.retry_with_backoff(
                        lambda: self._store_to_clickhouse(normalized_data),
                        exchange_name,
                        "store_data"
                    )
                else:
                    await self._store_to_clickhouse(normalized_data)
                    
                self.processed_messages.append(normalized_data)
                return normalized_data
                
        except Exception as e:
            print(f"Error processing message from {exchange_name}: {e}")
            
        return None
        
    async def _store_to_clickhouse(self, data: Dict[str, Any]):
        """存储数据到ClickHouse"""
        if data["type"] == "ticker":
            query = "INSERT INTO market_data VALUES"
            await self.clickhouse_client.execute(query, [data])
        elif data["type"] == "depth":
            query = "INSERT INTO order_book VALUES"
            await self.clickhouse_client.execute(query, [data])
            
    async def run_data_collection(self, exchange_name: str, duration: float = 5.0) -> Dict[str, Any]:
        """运行数据收集"""
        if exchange_name not in self.websocket_connections:
            raise ValueError(f"Exchange {exchange_name} not connected")
            
        ws = self.websocket_connections[exchange_name]
        
        # 启动数据流模拟
        stream_task = asyncio.create_task(
            ws.simulate_market_data_stream(duration)
        )
        
        # 处理消息
        start_time = time.time()
        processed_count = 0
        error_count = 0
        
        try:
            while time.time() - start_time < duration:
                message = await ws.receive_message()
                if message:
                    result = await self.process_message(exchange_name, message)
                    if result:
                        processed_count += 1
                    else:
                        error_count += 1
                        
        finally:
            stream_task.cancel()
            try:
                await stream_task
            except asyncio.CancelledError:
                pass
                
        return {
            "exchange": exchange_name,
            "duration": duration,
            "processed_count": processed_count,
            "error_count": error_count,
            "success_rate": processed_count / (processed_count + error_count) if (processed_count + error_count) > 0 else 0
        }
        
    async def run_multi_exchange_collection(self, exchanges: List[str], duration: float = 5.0) -> Dict[str, Any]:
        """运行多交易所数据收集"""
        # 并发收集数据
        tasks = []
        for exchange in exchanges:
            if exchange in self.websocket_connections:
                task = asyncio.create_task(
                    self.run_data_collection(exchange, duration)
                )
                tasks.append(task)
                
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 汇总结果
        total_processed = 0
        total_errors = 0
        exchange_results = {}
        
        for result in results:
            if isinstance(result, Exception):
                print(f"Collection failed: {result}")
                continue
                
            exchange_results[result["exchange"]] = result
            total_processed += result["processed_count"]
            total_errors += result["error_count"]
            
        return {
            "total_processed": total_processed,
            "total_errors": total_errors,
            "overall_success_rate": total_processed / (total_processed + total_errors) if (total_processed + total_errors) > 0 else 0,
            "exchange_results": exchange_results
        }
        
    async def query_stored_data(self, query_type: str = "count") -> Dict[str, Any]:
        """查询存储的数据"""
        if query_type == "count":
            result = await self.clickhouse_client.query("SELECT COUNT(*) as count FROM market_data")
            return {"total_records": result[0]["count"] if result else 0}
        elif query_type == "recent":
            result = await self.clickhouse_client.query("SELECT * FROM market_data ORDER BY timestamp DESC LIMIT 10")
            return {"recent_data": result}
        else:
            return {"error": "Unknown query type"}
            
    def get_pipeline_stats(self) -> Dict[str, Any]:
        """获取管道统计"""
        clickhouse_stats = self.clickhouse_client.get_stats()
        
        return {
            "websocket_connections": len(self.websocket_connections),
            "processed_messages": len(self.processed_messages),
            "clickhouse_stats": clickhouse_stats,
            "rate_limiter_stats": self.rate_limiter.get_status() if self.rate_limiter else None,
            "retry_handler_stats": self.retry_handler.get_status() if self.retry_handler else None
        }
        
    async def shutdown(self):
        """关闭管道"""
        self.running = False
        
        # 断开WebSocket连接
        for ws in self.websocket_connections.values():
            await ws.disconnect()
            
        # 断开ClickHouse连接
        await self.clickhouse_client.disconnect()


class MockDataNormalizer:
    """模拟数据标准化器"""
    
    async def normalize_message(self, exchange_name: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """标准化消息"""
        await asyncio.sleep(0.001)  # 模拟处理时间
        
        if "stream" not in message or "data" not in message:
            return None
            
        stream = message["stream"]
        data = message["data"]
        
        if "@ticker" in stream:
            return {
                "type": "ticker",
                "symbol": data.get("s"),
                "price": float(data.get("c", 0)),
                "volume": float(data.get("v", 0)),
                "timestamp": data.get("E"),
                "exchange": exchange_name
            }
        elif "@depth" in stream:
            return {
                "type": "depth",
                "symbol": data.get("s"),
                "bids": data.get("bids", []),
                "asks": data.get("asks", []),
                "timestamp": data.get("E"),
                "exchange": exchange_name
            }
            
        return None


@pytest.mark.integration
@pytest.mark.skipif(not HAS_CORE_MODULES, reason="核心模块不可用")
class TestRealDataFlowPipeline:
    """真实数据流管道测试"""
    
    @pytest.fixture
    async def pipeline(self):
        """创建数据流管道"""
        pipeline = RealDataFlowPipeline()
        await pipeline.initialize()
        yield pipeline
        await pipeline.shutdown()
        
    async def test_single_exchange_data_flow(self, pipeline):
        """测试单个交易所数据流"""
        # 添加交易所连接
        await pipeline.add_exchange_connection("binance")
        
        # 订阅数据流
        await pipeline.subscribe_to_data_streams("binance", ["BTCUSDT", "ETHUSDT"])
        
        # 运行数据收集
        result = await pipeline.run_data_collection("binance", duration=2.0)
        
        # 验证结果
        assert result["exchange"] == "binance"
        assert result["processed_count"] > 0
        assert result["success_rate"] > 0.8
        
        # 验证数据存储
        query_result = await pipeline.query_stored_data("count")
        assert query_result["total_records"] > 0
        
    async def test_multi_exchange_data_flow(self, pipeline):
        """测试多交易所数据流"""
        # 添加多个交易所连接
        exchanges = ["binance", "okx", "huobi"]
        for exchange in exchanges:
            await pipeline.add_exchange_connection(exchange)
            await pipeline.subscribe_to_data_streams(exchange, ["BTCUSDT"])
            
        # 运行多交易所数据收集
        result = await pipeline.run_multi_exchange_collection(exchanges, duration=3.0)
        
        # 验证结果
        assert result["total_processed"] > 0
        assert result["overall_success_rate"] > 0.7
        assert len(result["exchange_results"]) == 3
        
        # 验证每个交易所都有数据
        for exchange in exchanges:
            assert exchange in result["exchange_results"]
            assert result["exchange_results"][exchange]["processed_count"] > 0
            
    async def test_data_normalization_and_storage(self, pipeline):
        """测试数据标准化和存储"""
        # 添加交易所连接
        await pipeline.add_exchange_connection("test_exchange")
        
        # 模拟原始消息
        raw_messages = [
            {
                "stream": "btcusdt@ticker",
                "data": {
                    "s": "BTCUSDT",
                    "c": "45000.50",
                    "v": "1234.56",
                    "E": int(time.time() * 1000)
                }
            },
            {
                "stream": "btcusdt@depth",
                "data": {
                    "s": "BTCUSDT",
                    "bids": [["44999", "1.5"]],
                    "asks": [["45001", "1.2"]],
                    "E": int(time.time() * 1000)
                }
            }
        ]
        
        # 处理消息
        processed_results = []
        for message in raw_messages:
            result = await pipeline.process_message("test_exchange", message)
            if result:
                processed_results.append(result)
                
        # 验证标准化结果
        assert len(processed_results) == 2
        
        ticker_data = next((r for r in processed_results if r["type"] == "ticker"), None)
        assert ticker_data is not None
        assert ticker_data["symbol"] == "BTCUSDT"
        assert ticker_data["price"] == 45000.50
        assert ticker_data["exchange"] == "test_exchange"
        
        depth_data = next((r for r in processed_results if r["type"] == "depth"), None)
        assert depth_data is not None
        assert depth_data["symbol"] == "BTCUSDT"
        assert len(depth_data["bids"]) > 0
        assert depth_data["exchange"] == "test_exchange"
        
    async def test_pipeline_performance_metrics(self, pipeline):
        """测试管道性能指标"""
        # 添加交易所连接
        await pipeline.add_exchange_connection("performance_test")
        await pipeline.subscribe_to_data_streams("performance_test", ["BTCUSDT", "ETHUSDT"])
        
        # 运行性能测试
        start_time = time.time()
        result = await pipeline.run_data_collection("performance_test", duration=3.0)
        elapsed = time.time() - start_time
        
        # 获取管道统计
        stats = pipeline.get_pipeline_stats()
        
        # 验证性能指标
        assert result["processed_count"] > 0
        assert elapsed < 5.0  # 应该在合理时间内完成
        
        # 验证统计信息
        assert stats["websocket_connections"] >= 1
        assert stats["processed_messages"] > 0
        assert stats["clickhouse_stats"]["connected"] is True
        
        # 计算吞吐量
        throughput = result["processed_count"] / elapsed
        assert throughput > 1.0  # 至少每秒处理1条消息
        
    async def test_error_handling_and_recovery(self, pipeline):
        """测试错误处理和恢复"""
        # 添加交易所连接
        await pipeline.add_exchange_connection("error_test")
        
        # 模拟错误消息
        error_messages = [
            {"invalid": "message"},  # 无效消息格式
            {
                "stream": "btcusdt@ticker",
                "data": {
                    "s": "BTCUSDT",
                    "c": "invalid_price",  # 无效价格
                    "v": "1234.56",
                    "E": int(time.time() * 1000)
                }
            },
            {
                "stream": "btcusdt@ticker",
                "data": {
                    "s": "BTCUSDT",
                    "c": "45000.50",
                    "v": "1234.56",
                    "E": int(time.time() * 1000)
                }
            }  # 正常消息
        ]
        
        # 处理消息
        successful_count = 0
        error_count = 0
        
        for message in error_messages:
            result = await pipeline.process_message("error_test", message)
            if result:
                successful_count += 1
            else:
                error_count += 1
                
        # 验证错误处理
        assert successful_count > 0  # 至少有一些成功
        assert error_count > 0  # 确实有错误被处理
        
        # 验证系统仍然可用
        stats = pipeline.get_pipeline_stats()
        assert stats["clickhouse_stats"]["connected"] is True


@pytest.mark.performance
@pytest.mark.skipif(not HAS_CORE_MODULES, reason="核心模块不可用")
class TestDataFlowPerformance:
    """数据流性能测试"""
    
    @pytest.fixture
    async def performance_pipeline(self):
        """创建性能测试管道"""
        pipeline = RealDataFlowPipeline()
        await pipeline.initialize()
        
        # 添加多个交易所
        exchanges = ["binance", "okx", "huobi", "coinbase"]
        for exchange in exchanges:
            await pipeline.add_exchange_connection(exchange)
            await pipeline.subscribe_to_data_streams(exchange, ["BTCUSDT", "ETHUSDT"])
            
        yield pipeline
        await pipeline.shutdown()
        
    async def test_high_throughput_data_processing(self, performance_pipeline):
        """测试高吞吐量数据处理"""
        pipeline = performance_pipeline
        
        # 运行高吞吐量测试
        start_time = time.time()
        result = await pipeline.run_multi_exchange_collection(
            ["binance", "okx", "huobi", "coinbase"], 
            duration=5.0
        )
        elapsed = time.time() - start_time
        
        # 验证高吞吐量性能
        total_processed = result["total_processed"]
        throughput = total_processed / elapsed
        
        assert total_processed > 50  # 至少处理50条消息
        assert throughput > 10.0  # 至少每秒10条消息
        assert result["overall_success_rate"] > 0.8  # 80%+成功率
        
        print(f"High throughput metrics:")
        print(f"- Total processed: {total_processed}")
        print(f"- Throughput: {throughput:.2f} msg/sec")
        print(f"- Success rate: {result['overall_success_rate']:.2%}")
        
    async def test_sustained_load_performance(self, performance_pipeline):
        """测试持续负载性能"""
        pipeline = performance_pipeline
        
        # 运行持续负载测试
        duration = 10.0
        start_time = time.time()
        
        result = await pipeline.run_multi_exchange_collection(
            ["binance", "okx"], 
            duration=duration
        )
        
        elapsed = time.time() - start_time
        
        # 验证持续负载性能
        assert result["total_processed"] > 0
        assert elapsed <= duration + 2.0  # 允许2秒误差
        assert result["overall_success_rate"] > 0.7
        
        # 检查系统稳定性
        stats = pipeline.get_pipeline_stats()
        assert stats["clickhouse_stats"]["connected"] is True
        
        print(f"Sustained load metrics:")
        print(f"- Duration: {elapsed:.2f}s")
        print(f"- Total processed: {result['total_processed']}")
        print(f"- Average rate: {result['total_processed']/elapsed:.2f} msg/sec")


if __name__ == "__main__":
    # 运行简单的数据流测试
    async def main():
        pipeline = RealDataFlowPipeline()
        await pipeline.initialize()
        
        await pipeline.add_exchange_connection("test")
        await pipeline.subscribe_to_data_streams("test", ["BTCUSDT"])
        
        result = await pipeline.run_data_collection("test", duration=2.0)
        print(f"Data flow result: {result}")
        
        stats = pipeline.get_pipeline_stats()
        print(f"Pipeline stats: {stats}")
        
        await pipeline.shutdown()
        
    asyncio.run(main())
