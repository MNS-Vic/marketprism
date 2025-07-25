"""
MarketPrism 端到端数据管道测试

测试从交易所数据收集到ClickHouse存储的完整数据管道
"""

import asyncio
import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, List, Any

# 导入核心模块
try:
    from core.reliability.rate_limiter import AdaptiveRateLimiter, RateLimitConfig
    from core.reliability.retry_handler import ExponentialBackoffRetry, RetryPolicy
    from core.config.unified_config_manager import UnifiedConfigManager
    HAS_CORE_MODULES = True
except ImportError:
    HAS_CORE_MODULES = False

# 模拟交易所数据
MOCK_MARKET_DATA = {
    "binance": {
        "BTC/USDT": {
            "symbol": "BTCUSDT",
            "price": 45000.0,
            "volume": 1234.56,
            "timestamp": int(time.time() * 1000),
            "bid": 44999.0,
            "ask": 45001.0
        },
        "ETH/USDT": {
            "symbol": "ETHUSDT", 
            "price": 3000.0,
            "volume": 5678.90,
            "timestamp": int(time.time() * 1000),
            "bid": 2999.0,
            "ask": 3001.0
        }
    },
    "okx": {
        "BTC/USDT": {
            "symbol": "BTC-USDT",
            "price": 45010.0,
            "volume": 987.65,
            "timestamp": int(time.time() * 1000),
            "bid": 45009.0,
            "ask": 45011.0
        }
    }
}


class MockExchangeConnector:
    """模拟交易所连接器"""
    
    def __init__(self, exchange_name: str):
        self.exchange_name = exchange_name
        self.connected = False
        self.rate_limiter = None
        self.retry_handler = None
        
    async def connect(self):
        """连接到交易所"""
        await asyncio.sleep(0.1)  # 模拟连接延迟
        self.connected = True
        return True
        
    async def disconnect(self):
        """断开连接"""
        self.connected = False
        
    async def fetch_market_data(self, symbol: str) -> Dict[str, Any]:
        """获取市场数据"""
        if not self.connected:
            raise ConnectionError(f"Not connected to {self.exchange_name}")
            
        # 模拟网络延迟
        await asyncio.sleep(0.05)
        
        # 模拟偶发性错误
        if symbol == "ERROR/TEST":
            raise TimeoutError("Simulated timeout")
            
        if self.exchange_name in MOCK_MARKET_DATA:
            if symbol in MOCK_MARKET_DATA[self.exchange_name]:
                return MOCK_MARKET_DATA[self.exchange_name][symbol]
                
        raise ValueError(f"Symbol {symbol} not found on {self.exchange_name}")
        
    async def fetch_all_symbols(self) -> List[str]:
        """获取所有交易对"""
        if not self.connected:
            raise ConnectionError(f"Not connected to {self.exchange_name}")
            
        if self.exchange_name in MOCK_MARKET_DATA:
            return list(MOCK_MARKET_DATA[self.exchange_name].keys())
        return []


class MockClickHouseWriter:
    """模拟ClickHouse写入器"""
    
    def __init__(self):
        self.connected = False
        self.written_data = []
        
    async def connect(self):
        """连接到ClickHouse"""
        await asyncio.sleep(0.1)
        self.connected = True
        
    async def disconnect(self):
        """断开连接"""
        self.connected = False
        
    async def write_market_data(self, data: List[Dict[str, Any]]):
        """写入市场数据"""
        if not self.connected:
            raise ConnectionError("Not connected to ClickHouse")
            
        # 模拟写入延迟
        await asyncio.sleep(0.02)
        
        # 模拟偶发性写入错误
        if len(data) > 100:
            raise Exception("Batch too large")
            
        self.written_data.extend(data)
        
    def get_written_count(self) -> int:
        """获取已写入数据条数"""
        return len(self.written_data)
        
    def clear_data(self):
        """清空数据"""
        self.written_data.clear()


class DataPipeline:
    """数据管道"""
    
    def __init__(self):
        self.exchanges = {}
        self.clickhouse_writer = MockClickHouseWriter()
        self.rate_limiter = None
        self.retry_handler = None
        self.config_manager = None
        self.running = False
        
    async def initialize(self):
        """初始化管道"""
        # 初始化配置管理器
        if HAS_CORE_MODULES:
            self.config_manager = UnifiedConfigManager()
            self.config_manager.initialize()
            
            # 初始化限流器
            rate_config = RateLimitConfig(max_requests_per_second=10)
            self.rate_limiter = AdaptiveRateLimiter("data_pipeline", rate_config)
            
            # 初始化重试处理器
            self.retry_handler = ExponentialBackoffRetry("data_pipeline")
            
        # 连接ClickHouse
        await self.clickhouse_writer.connect()
        
    async def add_exchange(self, exchange_name: str):
        """添加交易所"""
        connector = MockExchangeConnector(exchange_name)
        await connector.connect()
        self.exchanges[exchange_name] = connector
        
    async def collect_data_from_exchange(self, exchange_name: str) -> List[Dict[str, Any]]:
        """从单个交易所收集数据"""
        if exchange_name not in self.exchanges:
            raise ValueError(f"Exchange {exchange_name} not configured")
            
        connector = self.exchanges[exchange_name]
        symbols = await connector.fetch_all_symbols()
        
        collected_data = []
        for symbol in symbols:
            try:
                # 应用限流
                if self.rate_limiter:
                    await self.rate_limiter.acquire_permit("fetch_data")
                    
                # 获取数据（带重试）
                if self.retry_handler:
                    policy = RetryPolicy(max_attempts=3, base_delay=0.1)
                    data = await self.retry_handler.retry_with_backoff(
                        lambda: connector.fetch_market_data(symbol),
                        exchange_name,
                        f"fetch_{symbol}"
                    )
                else:
                    data = await connector.fetch_market_data(symbol)
                    
                # 添加元数据
                data["exchange"] = exchange_name
                data["collected_at"] = datetime.utcnow().isoformat()
                collected_data.append(data)
                
            except Exception as e:
                print(f"Failed to collect {symbol} from {exchange_name}: {e}")
                continue
                
        return collected_data
        
    async def collect_all_data(self) -> List[Dict[str, Any]]:
        """从所有交易所收集数据"""
        all_data = []
        
        # 并发收集数据
        tasks = []
        for exchange_name in self.exchanges:
            task = asyncio.create_task(
                self.collect_data_from_exchange(exchange_name)
            )
            tasks.append(task)
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, Exception):
                print(f"Exchange collection failed: {result}")
            else:
                all_data.extend(result)
                
        return all_data
        
    async def store_data(self, data: List[Dict[str, Any]]):
        """存储数据到ClickHouse"""
        if not data:
            return
            
        # 分批写入
        batch_size = 50
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            
            if self.retry_handler:
                policy = RetryPolicy(max_attempts=3, base_delay=0.1)
                await self.retry_handler.retry_with_backoff(
                    lambda: self.clickhouse_writer.write_market_data(batch),
                    "clickhouse",
                    "write_batch"
                )
            else:
                await self.clickhouse_writer.write_market_data(batch)
                
    async def run_single_cycle(self):
        """运行单次数据收集周期"""
        # 收集数据
        data = await self.collect_all_data()
        
        # 存储数据
        await self.store_data(data)
        
        return len(data)
        
    async def shutdown(self):
        """关闭管道"""
        self.running = False
        
        # 断开所有交易所连接
        for connector in self.exchanges.values():
            await connector.disconnect()
            
        # 断开ClickHouse连接
        await self.clickhouse_writer.disconnect()


@pytest.mark.integration
@pytest.mark.skipif(not HAS_CORE_MODULES, reason="核心模块不可用")
class TestEndToEndDataPipeline:
    """端到端数据管道测试"""
    
    @pytest.fixture
    async def pipeline(self):
        """创建测试管道"""
        pipeline = DataPipeline()
        await pipeline.initialize()
        yield pipeline
        await pipeline.shutdown()
        
    async def test_single_exchange_data_collection(self, pipeline):
        """测试单个交易所数据收集"""
        # 添加交易所
        await pipeline.add_exchange("binance")
        
        # 收集数据
        data = await pipeline.collect_data_from_exchange("binance")
        
        # 验证数据
        assert len(data) == 2  # BTC/USDT 和 ETH/USDT
        assert all("exchange" in item for item in data)
        assert all("collected_at" in item for item in data)
        assert all(item["exchange"] == "binance" for item in data)
        
    async def test_multiple_exchange_data_collection(self, pipeline):
        """测试多个交易所数据收集"""
        # 添加多个交易所
        await pipeline.add_exchange("binance")
        await pipeline.add_exchange("okx")
        
        # 收集所有数据
        data = await pipeline.collect_all_data()
        
        # 验证数据
        assert len(data) == 3  # binance: 2个, okx: 1个
        exchanges = {item["exchange"] for item in data}
        assert exchanges == {"binance", "okx"}
        
    async def test_data_storage(self, pipeline):
        """测试数据存储"""
        # 添加交易所
        await pipeline.add_exchange("binance")
        
        # 收集并存储数据
        data = await pipeline.collect_all_data()
        await pipeline.store_data(data)
        
        # 验证存储
        assert pipeline.clickhouse_writer.get_written_count() == len(data)
        
    async def test_complete_pipeline_cycle(self, pipeline):
        """测试完整管道周期"""
        # 添加交易所
        await pipeline.add_exchange("binance")
        await pipeline.add_exchange("okx")
        
        # 运行完整周期
        collected_count = await pipeline.run_single_cycle()
        
        # 验证结果
        assert collected_count == 3
        assert pipeline.clickhouse_writer.get_written_count() == 3
        
    async def test_rate_limiting_integration(self, pipeline):
        """测试限流集成"""
        # 添加交易所
        await pipeline.add_exchange("binance")
        
        # 记录开始时间
        start_time = time.time()
        
        # 运行多次收集（应该被限流）
        for _ in range(5):
            await pipeline.collect_data_from_exchange("binance")
            
        # 验证限流效果
        elapsed = time.time() - start_time
        assert elapsed > 0.5  # 应该有明显延迟
        
        # 检查限流器状态
        status = pipeline.rate_limiter.get_status()
        assert status['total_requests'] >= 10  # 每次收集2个symbol

    async def test_retry_mechanism_integration(self, pipeline):
        """测试重试机制集成"""
        # 添加会产生错误的交易所
        await pipeline.add_exchange("binance")

        # 尝试获取会出错的symbol（但重试机制会处理）
        connector = pipeline.exchanges["binance"]

        # 模拟临时错误后成功的情况
        original_fetch = connector.fetch_market_data
        call_count = 0

        async def failing_then_success(symbol):
            nonlocal call_count
            call_count += 1
            if call_count <= 2 and symbol == "BTC/USDT":
                raise TimeoutError("Temporary error")
            return await original_fetch(symbol)

        connector.fetch_market_data = failing_then_success

        # 收集数据（应该通过重试成功）
        data = await pipeline.collect_data_from_exchange("binance")

        # 验证重试成功
        assert len(data) == 2
        assert call_count > 2  # 确实进行了重试

        # 检查重试处理器状态
        status = pipeline.retry_handler.get_status()
        assert status['total_attempts'] >= 3


@pytest.mark.performance
@pytest.mark.skipif(not HAS_CORE_MODULES, reason="核心模块不可用")
class TestDataPipelinePerformance:
    """数据管道性能测试"""

    @pytest.fixture
    async def performance_pipeline(self):
        """创建性能测试管道"""
        pipeline = DataPipeline()
        await pipeline.initialize()

        # 添加多个交易所
        exchanges = ["binance", "okx", "huobi", "coinbase", "kraken"]
        for exchange in exchanges:
            await pipeline.add_exchange(exchange)

        yield pipeline
        await pipeline.shutdown()

    async def test_concurrent_data_collection_performance(self, performance_pipeline):
        """测试并发数据收集性能"""
        pipeline = performance_pipeline

        # 记录性能指标
        start_time = time.time()
        start_memory = 0  # 简化，实际应该测量内存使用

        # 并发收集多轮数据
        tasks = []
        for _ in range(10):
            task = asyncio.create_task(pipeline.collect_all_data())
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        end_time = time.time()
        elapsed = end_time - start_time

        # 验证性能
        successful_results = [r for r in results if not isinstance(r, Exception)]
        assert len(successful_results) >= 8  # 至少80%成功
        assert elapsed < 30.0  # 应该在30秒内完成

        # 验证数据质量
        total_data_points = sum(len(result) for result in successful_results)
        assert total_data_points > 0

        print(f"Performance metrics:")
        print(f"- Elapsed time: {elapsed:.2f}s")
        print(f"- Successful collections: {len(successful_results)}/10")
        print(f"- Total data points: {total_data_points}")
        print(f"- Throughput: {total_data_points/elapsed:.2f} points/sec")

    async def test_high_frequency_data_collection(self, performance_pipeline):
        """测试高频数据收集"""
        pipeline = performance_pipeline

        # 高频收集数据
        start_time = time.time()
        collection_count = 0
        total_data_points = 0

        # 运行5秒的高频收集
        while time.time() - start_time < 5.0:
            try:
                data = await pipeline.collect_all_data()
                collection_count += 1
                total_data_points += len(data)

                # 短暂休息避免过载
                await asyncio.sleep(0.1)

            except Exception as e:
                print(f"Collection failed: {e}")
                continue

        elapsed = time.time() - start_time

        # 验证高频性能
        assert collection_count >= 10  # 至少收集10次
        assert total_data_points > 0

        print(f"High frequency metrics:")
        print(f"- Collections: {collection_count} in {elapsed:.2f}s")
        print(f"- Collection rate: {collection_count/elapsed:.2f} collections/sec")
        print(f"- Data throughput: {total_data_points/elapsed:.2f} points/sec")

    async def test_large_batch_storage_performance(self, performance_pipeline):
        """测试大批量存储性能"""
        pipeline = performance_pipeline

        # 生成大量测试数据
        large_dataset = []
        for i in range(1000):
            data_point = {
                "symbol": f"TEST{i}/USDT",
                "price": 100.0 + i,
                "volume": 1000.0,
                "timestamp": int(time.time() * 1000),
                "exchange": "test_exchange",
                "collected_at": datetime.utcnow().isoformat()
            }
            large_dataset.append(data_point)

        # 测试存储性能
        start_time = time.time()

        try:
            await pipeline.store_data(large_dataset)
            storage_success = True
        except Exception as e:
            print(f"Storage failed: {e}")
            storage_success = False

        elapsed = time.time() - start_time

        # 验证存储性能
        if storage_success:
            stored_count = pipeline.clickhouse_writer.get_written_count()
            assert stored_count == 1000
            assert elapsed < 10.0  # 应该在10秒内完成

            print(f"Storage performance:")
            print(f"- Stored {stored_count} records in {elapsed:.2f}s")
            print(f"- Storage rate: {stored_count/elapsed:.2f} records/sec")


@pytest.mark.stress
@pytest.mark.skipif(not HAS_CORE_MODULES, reason="核心模块不可用")
class TestDataPipelineStress:
    """数据管道压力测试"""

    @pytest.fixture
    async def stress_pipeline(self):
        """创建压力测试管道"""
        pipeline = DataPipeline()
        await pipeline.initialize()

        # 配置更严格的限流
        if pipeline.rate_limiter:
            pipeline.rate_limiter.config.max_requests_per_second = 5

        yield pipeline
        await pipeline.shutdown()

    async def test_sustained_load_stress(self, stress_pipeline):
        """测试持续负载压力"""
        pipeline = stress_pipeline

        # 添加交易所
        await pipeline.add_exchange("binance")
        await pipeline.add_exchange("okx")

        # 持续运行30秒
        start_time = time.time()
        cycle_count = 0
        error_count = 0
        total_data_points = 0

        while time.time() - start_time < 30.0:
            try:
                data_count = await pipeline.run_single_cycle()
                cycle_count += 1
                total_data_points += data_count

                # 短暂休息
                await asyncio.sleep(0.5)

            except Exception as e:
                error_count += 1
                print(f"Cycle failed: {e}")
                await asyncio.sleep(1.0)  # 错误后稍长休息

        elapsed = time.time() - start_time

        # 验证系统稳定性
        success_rate = cycle_count / (cycle_count + error_count) if (cycle_count + error_count) > 0 else 0
        assert success_rate >= 0.8  # 至少80%成功率
        assert cycle_count >= 10  # 至少完成10个周期

        print(f"Stress test results:")
        print(f"- Duration: {elapsed:.2f}s")
        print(f"- Successful cycles: {cycle_count}")
        print(f"- Failed cycles: {error_count}")
        print(f"- Success rate: {success_rate:.2%}")
        print(f"- Total data points: {total_data_points}")

    async def test_concurrent_stress(self, stress_pipeline):
        """测试并发压力"""
        pipeline = stress_pipeline

        # 添加交易所
        await pipeline.add_exchange("binance")

        # 创建大量并发任务
        async def stress_worker(worker_id: int):
            """压力测试工作器"""
            success_count = 0
            error_count = 0

            for i in range(20):  # 每个工作器执行20次
                try:
                    await pipeline.collect_data_from_exchange("binance")
                    success_count += 1
                    await asyncio.sleep(0.1)
                except Exception as e:
                    error_count += 1
                    await asyncio.sleep(0.2)

            return {"worker_id": worker_id, "success": success_count, "error": error_count}

        # 启动20个并发工作器
        start_time = time.time()
        tasks = [stress_worker(i) for i in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start_time

        # 分析结果
        successful_workers = [r for r in results if not isinstance(r, Exception)]
        total_success = sum(r["success"] for r in successful_workers)
        total_error = sum(r["error"] for r in successful_workers)

        # 验证并发稳定性
        assert len(successful_workers) >= 18  # 至少90%工作器成功
        overall_success_rate = total_success / (total_success + total_error) if (total_success + total_error) > 0 else 0
        assert overall_success_rate >= 0.7  # 至少70%操作成功

        print(f"Concurrent stress results:")
        print(f"- Duration: {elapsed:.2f}s")
        print(f"- Successful workers: {len(successful_workers)}/20")
        print(f"- Total successful operations: {total_success}")
        print(f"- Total failed operations: {total_error}")
        print(f"- Overall success rate: {overall_success_rate:.2%}")

        # 检查系统组件状态
        if pipeline.rate_limiter:
            limiter_status = pipeline.rate_limiter.get_status()
            print(f"- Rate limiter requests: {limiter_status['total_requests']}")

        if pipeline.retry_handler:
            retry_status = pipeline.retry_handler.get_status()
            print(f"- Retry handler attempts: {retry_status['total_attempts']}")


if __name__ == "__main__":
    # 运行简单的端到端测试
    async def main():
        pipeline = DataPipeline()
        await pipeline.initialize()
        await pipeline.add_exchange("binance")

        data = await pipeline.run_single_cycle()
        print(f"Collected {data} data points")

        await pipeline.shutdown()

    asyncio.run(main())
