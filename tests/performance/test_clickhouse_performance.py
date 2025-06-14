"""
MarketPrism ClickHouse性能测试

测试ClickHouse数据库在高负载下的性能表现
"""
from datetime import datetime, timezone
import sys
import os
import json
import time
import asyncio
import pytest
import statistics
import concurrent.futures
from pathlib import Path
from typing import Dict, List, Any, Optional

# 添加项目根目录到系统路径
project_root = Path(__file__).parent.parent.parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 导入测试辅助工具    
from tests.utils.data_factory import data_factory
from tests.utils.test_helpers import test_helpers

# 如果存在实际的存储服务模块，则导入它
try:
    from services.data_archiver.storage import ClickHouseStorage
    HAS_STORAGE_MODULE = True
except ImportError:
    HAS_STORAGE_MODULE = False
    # 创建模拟的存储类用于测试
    class ClickHouseStorage:
        def __init__(self, host='localhost', port=9000, user='default', password='', database='default'):
            pass
            
        def connect(self):
            pass
            
        def disconnect(self):
            pass
            
        def execute(self, query, params=None):
            pass
            
        def insert_trade(self, trade_data):
            pass
            
        def insert_trades_batch(self, trades_data):
            pass
            
        def get_trades(self, exchange=None, symbol=None, start_time=None, end_time=None, limit=1000):
            pass

# ClickHouse性能测试配置
PERFORMANCE_CONFIG = {
    "batch_sizes": [1, 10, 100, 1000, 10000],
    "iterations": 5,
    "query_sizes": [100, 1000, 10000],
    "concurrent_inserts": [1, 5, 10, 20, 50]
}

# 性能测试基类
@pytest.mark.performance
class ClickHousePerformanceTestBase:
    """ClickHouse性能测试基类"""
    
    @staticmethod
    def generate_test_trades(count: int) -> List[Dict]:
        """生成测试交易数据"""
        return data_factory.create_batch(data_factory.create_trade, count)
    
    @staticmethod
    def calculate_performance_metrics(durations: List[float], record_count: int) -> Dict:
        """计算性能指标"""
        total_time = sum(durations)
        avg_time = total_time / len(durations)
        records_per_second = record_count / total_time if total_time > 0 else 0
        
        metrics = {
            "total_time_seconds": total_time,
            "average_time_seconds": avg_time,
            "records_per_second": records_per_second,
            "min_time_seconds": min(durations),
            "max_time_seconds": max(durations),
            "std_dev_seconds": statistics.stdev(durations) if len(durations) > 1 else 0
        }
        
        return metrics
    
    @staticmethod
    def print_performance_report(test_name: str, metrics: Dict, config: Dict) -> None:
        """打印性能报告"""
        print(f"\n=== {test_name} 性能报告 ===")
        print(f"配置: {json.dumps(config, indent=2)}")
        print(f"指标: {json.dumps(metrics, indent=2)}")
        print("=" * 50)


# ClickHouse插入性能测试
@pytest.mark.skipif(not test_helpers.is_clickhouse_available(), reason="ClickHouse服务不可用")
@pytest.mark.performance
class TestClickHouseInsertPerformance(ClickHousePerformanceTestBase):
    """测试ClickHouse数据插入性能"""
    
    @pytest.fixture
    def clickhouse_storage(self):
        """创建ClickHouse存储实例"""
        if not HAS_STORAGE_MODULE:
            pytest.skip("存储模块不可用")
            
        storage = ClickHouseStorage(
            host='localhost',
            port=9000,
            user='default',
            password='',
            database='default'
        )
        
        try:
            storage.connect()
            yield storage
        finally:
            storage.disconnect()
    
    @pytest.mark.parametrize("batch_size", PERFORMANCE_CONFIG["batch_sizes"])
    def test_batch_insert_performance(self, clickhouse_storage, batch_size):
        """测试批量插入性能"""
        if batch_size > 10000:
            pytest.skip("批量大小超过10000，跳过测试")
            
        # 准备测试数据
        iterations = PERFORMANCE_CONFIG["iterations"]
        trades_data = self.generate_test_trades(batch_size)
        
        # 执行批量插入测试
        durations = []
        
        for _ in range(iterations):
            start_time = time.time()
            clickhouse_storage.insert_trades_batch(trades_data)
            end_time = time.time()
            durations.append(end_time - start_time)
        
        # 计算性能指标
        metrics = self.calculate_performance_metrics(durations, batch_size * iterations)
        config = {
            "batch_size": batch_size,
            "iterations": iterations
        }
        
        # 打印性能报告
        self.print_performance_report("批量插入性能", metrics, config)
        
        # 验证最低性能要求
        assert metrics["records_per_second"] > 100, "批量插入性能低于预期"
    
    @pytest.mark.parametrize("concurrency", PERFORMANCE_CONFIG["concurrent_inserts"])
    def test_concurrent_insert_performance(self, clickhouse_storage, concurrency):
        """测试并发插入性能"""
        if concurrency > 20:
            pytest.skip("并发级别超过20，跳过测试")
            
        # 准备测试数据
        batch_size = 100  # 每个并发任务插入的记录数
        trades_data = self.generate_test_trades(batch_size * concurrency)
        
        # 创建并发插入任务
        def insert_batch(batch_index):
            start_idx = batch_index * batch_size
            end_idx = start_idx + batch_size
            batch = trades_data[start_idx:end_idx]
            
            start_time = time.time()
            clickhouse_storage.insert_trades_batch(batch)
            end_time = time.time()
            
            return end_time - start_time
        
        # 执行并发插入测试
        durations = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(insert_batch, i) for i in range(concurrency)]
            for future in concurrent.futures.as_completed(futures):
                durations.append(future.result())
        
        # 计算性能指标
        metrics = self.calculate_performance_metrics(durations, batch_size * concurrency)
        config = {
            "concurrency": concurrency,
            "batch_size_per_thread": batch_size,
            "total_records": batch_size * concurrency
        }
        
        # 打印性能报告
        self.print_performance_report("并发插入性能", metrics, config)
        
        # 验证最低性能要求
        assert metrics["records_per_second"] > 500, "并发插入性能低于预期"


# ClickHouse查询性能测试
@pytest.mark.skipif(not test_helpers.is_clickhouse_available(), reason="ClickHouse服务不可用")
@pytest.mark.performance
class TestClickHouseQueryPerformance(ClickHousePerformanceTestBase):
    """测试ClickHouse数据查询性能"""
    
    @pytest.fixture
    def clickhouse_storage(self):
        """创建ClickHouse存储实例"""
        if not HAS_STORAGE_MODULE:
            pytest.skip("存储模块不可用")
            
        storage = ClickHouseStorage(
            host='localhost',
            port=9000,
            user='default',
            password='',
            database='default'
        )
        
        try:
            storage.connect()
            
            # 准备测试数据
            max_records = max(PERFORMANCE_CONFIG["query_sizes"])
            test_trades = self.generate_test_trades(max_records)
            
            # 插入测试数据
            storage.insert_trades_batch(test_trades)
            
            yield storage
        finally:
            storage.disconnect()
    
    @pytest.mark.parametrize("query_size", PERFORMANCE_CONFIG["query_sizes"])
    def test_query_performance(self, clickhouse_storage, query_size):
        """测试查询性能"""
        if query_size > 10000:
            pytest.skip("查询大小超过10000，跳过测试")
            
        # 准备测试查询
        iterations = PERFORMANCE_CONFIG["iterations"]
        exchange = "binance"
        symbol = "BTC/USDT"
        end_time = time.time()
        start_time = end_time - (3600 * 24)  # 过去24小时
        
        # 执行查询测试
        durations = []
        
        for _ in range(iterations):
            query_start_time = time.time()
            results = clickhouse_storage.get_trades(
                exchange=exchange,
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                limit=query_size
            )
            query_end_time = time.time()
            durations.append(query_end_time - query_start_time)
        
        # 计算性能指标
        metrics = self.calculate_performance_metrics(durations, query_size * iterations)
        config = {
            "query_size": query_size,
            "iterations": iterations,
            "exchange": exchange,
            "symbol": symbol,
            "time_range_hours": 24
        }
        
        # 打印性能报告
        self.print_performance_report("查询性能", metrics, config)
        
        # 验证最低性能要求
        assert metrics["records_per_second"] > 1000, "查询性能低于预期"
    
    def test_aggregation_performance(self, clickhouse_storage):
        """测试聚合查询性能"""
        # 准备测试查询
        iterations = PERFORMANCE_CONFIG["iterations"]
        
        # 执行聚合查询测试
        durations = []
        
        for _ in range(iterations):
            query_start_time = time.time()
            # 执行聚合查询
            # 这里假设存储服务有execute方法可以直接执行SQL查询
            # 实际测试中需要根据存储服务的API调整
            results = clickhouse_storage.execute("""
                SELECT 
                    exchange,
                    symbol,
                    toDate(timestamp) as date,
                    count() as trade_count,
                    avg(price) as avg_price,
                    sum(amount) as total_volume,
                    min(price) as min_price,
                    max(price) as max_price
                FROM trades
                GROUP BY exchange, symbol, date
                ORDER BY date DESC, exchange, symbol
                LIMIT 100
            """)
            query_end_time = time.time()
            durations.append(query_end_time - query_start_time)
        
        # 计算性能指标
        metrics = self.calculate_performance_metrics(durations, iterations)
        config = {
            "iterations": iterations,
            "query_type": "聚合查询(GROUP BY)"
        }
        
        # 打印性能报告
        self.print_performance_report("聚合查询性能", metrics, config)
        
        # 验证最低性能要求
        assert metrics["average_time_seconds"] < 1.0, "聚合查询性能低于预期"


# ClickHouse综合负载测试
@pytest.mark.skipif(not test_helpers.is_clickhouse_available(), reason="ClickHouse服务不可用")
@pytest.mark.performance
class TestClickHouseMixedLoadPerformance(ClickHousePerformanceTestBase):
    """测试ClickHouse混合负载性能（同时插入和查询）"""
    
    @pytest.fixture
    def clickhouse_storage(self):
        """创建ClickHouse存储实例"""
        if not HAS_STORAGE_MODULE:
            pytest.skip("存储模块不可用")
            
        storage = ClickHouseStorage(
            host='localhost',
            port=9000,
            user='default',
            password='',
            database='default'
        )
        
        try:
            storage.connect()
            
            # 准备初始测试数据
            initial_records = 10000
            test_trades = self.generate_test_trades(initial_records)
            
            # 插入初始测试数据
            storage.insert_trades_batch(test_trades)
            
            yield storage
        finally:
            storage.disconnect()
    
    def test_mixed_load_performance(self, clickhouse_storage):
        """测试混合负载性能"""
        # 测试配置
        insert_threads = 5
        query_threads = 5
        duration_seconds = 10
        batch_size = 100
        
        # 用于收集性能指标的容器
        insert_durations = []
        query_durations = []
        
        # 结束标志
        end_time = time.time() + duration_seconds
        
        # 插入任务
        def insert_task():
            local_insert_durations = []
            while time.time() < end_time:
                trades_data = self.generate_test_trades(batch_size)
                
                start_time = time.time()
                clickhouse_storage.insert_trades_batch(trades_data)
                task_end_time = time.time()
                
                local_insert_durations.append(task_end_time - start_time)
            
            return local_insert_durations
        
        # 查询任务
        def query_task():
            local_query_durations = []
            while time.time() < end_time:
                exchange = "binance"
                symbol = "BTC/USDT"
                query_end = time.time()
                query_start = query_end - (3600 * 24)  # 过去24小时
                
                start_time = time.time()
                clickhouse_storage.get_trades(
                    exchange=exchange,
                    symbol=symbol,
                    start_time=query_start,
                    end_time=query_end,
                    limit=1000
                )
                task_end_time = time.time()
                
                local_query_durations.append(task_end_time - start_time)
            
            return local_query_durations
        
        # 执行混合负载测试
        with concurrent.futures.ThreadPoolExecutor(max_workers=insert_threads + query_threads) as executor:
            # 提交插入任务
            insert_futures = [executor.submit(insert_task) for _ in range(insert_threads)]
            
            # 提交查询任务
            query_futures = [executor.submit(query_task) for _ in range(query_threads)]
            
            # 收集结果
            for future in concurrent.futures.as_completed(insert_futures):
                insert_durations.extend(future.result())
                
            for future in concurrent.futures.as_completed(query_futures):
                query_durations.extend(future.result())
        
        # 计算插入性能指标
        insert_metrics = self.calculate_performance_metrics(insert_durations, batch_size * len(insert_durations))
        
        # 计算查询性能指标
        query_metrics = self.calculate_performance_metrics(query_durations, len(query_durations))
        
        # 配置
        config = {
            "insert_threads": insert_threads,
            "query_threads": query_threads,
            "duration_seconds": duration_seconds,
            "insert_batch_size": batch_size
        }
        
        # 打印性能报告
        self.print_performance_report("插入性能(混合负载)", insert_metrics, config)
        self.print_performance_report("查询性能(混合负载)", query_metrics, config)
        
        # 验证最低性能要求
        assert insert_metrics["records_per_second"] > 100, "混合负载下的插入性能低于预期"
        assert query_metrics["average_time_seconds"] < 1.0, "混合负载下的查询性能低于预期"


if __name__ == "__main__":
    pytest.main(["-v", __file__])