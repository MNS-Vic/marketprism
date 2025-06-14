"""
统一REST客户端和大户持仓比数据收集器集成测试

测试统一REST API模块的功能，包括：
1. REST客户端的基本功能
2. 大户持仓比数据收集
3. 限流和重试机制
4. 错误处理
"""

import asyncio
import pytest
from datetime import datetime, timezone
from decimal import Decimal

# 添加项目路径
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/python-collector/src'))

from marketprism_collector.rest_client import (
    RestClientManager, RestClientConfig, ExchangeRestClient
)
from marketprism_collector.top_trader_collector import TopTraderDataCollector
from marketprism_collector.data_types import Exchange


class TestUnifiedRestClient:
    """统一REST客户端测试"""
    
    @pytest.fixture
    async def rest_manager(self):
        """创建REST客户端管理器"""
        manager = RestClientManager()
        yield manager
        await manager.stop_all()
    
    @pytest.fixture
    async def binance_client(self, rest_manager):
        """创建Binance REST客户端"""
        config = RestClientConfig(
            base_url="https://fapi.binance.com",
            timeout=10,
            max_retries=2,
            rate_limit_per_minute=60  # 测试用较低限制
        )
        
        client = rest_manager.create_exchange_client(Exchange.BINANCE, config)
        await client.start()
        return client
    
    @pytest.fixture
    async def okx_client(self, rest_manager):
        """创建OKX REST客户端"""
        config = RestClientConfig(
            base_url="https://www.okx.com",
            timeout=10,
            max_retries=2,
            rate_limit_per_second=2  # 测试用较低限制
        )
        
        client = rest_manager.create_exchange_client(Exchange.OKX, config)
        await client.start()
        return client
    
    @pytest.mark.asyncio
    async def test_binance_client_basic(self, binance_client):
        """测试Binance客户端基本功能"""
        # 测试获取服务器时间
        response = await binance_client.get('/fapi/v1/time')
        
        assert 'serverTime' in response
        assert isinstance(response['serverTime'], int)
        
        # 检查统计信息
        stats = binance_client.get_stats()
        assert stats['total_requests'] >= 1
        assert stats['successful_requests'] >= 1
        assert stats['success_rate'] > 0
    
    @pytest.mark.asyncio
    async def test_okx_client_basic(self, okx_client):
        """测试OKX客户端基本功能"""
        # 测试获取服务器时间
        response = await okx_client.get('/api/v5/public/time')
        
        assert 'code' in response
        assert response['code'] == '0'
        assert 'data' in response
        
        # 检查统计信息
        stats = okx_client.get_stats()
        assert stats['total_requests'] >= 1
        assert stats['successful_requests'] >= 1
        assert stats['success_rate'] > 0
    
    @pytest.mark.asyncio
    async def test_rate_limiting(self, binance_client):
        """测试限流功能"""
        import time
        
        # 快速发送多个请求，测试限流
        start_time = time.time()
        
        tasks = []
        for _ in range(5):
            task = asyncio.create_task(
                binance_client.get('/fapi/v1/time')
            )
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # 由于限流，应该花费一定时间
        # 这里只是简单验证没有立即完成
        assert duration > 0.1  # 至少100ms
        
        # 检查统计信息
        stats = binance_client.get_stats()
        assert stats['total_requests'] >= 5
    
    @pytest.mark.asyncio
    async def test_error_handling(self, binance_client):
        """测试错误处理"""
        # 测试404错误
        with pytest.raises(Exception):
            await binance_client.get('/fapi/v1/nonexistent')
        
        # 检查错误统计
        stats = binance_client.get_stats()
        assert stats['failed_requests'] >= 1


class TestTopTraderDataCollector:
    """大户持仓比数据收集器测试"""
    
    @pytest.fixture
    async def rest_manager(self):
        """创建REST客户端管理器"""
        manager = RestClientManager()
        yield manager
        await manager.stop_all()
    
    @pytest.fixture
    async def top_trader_collector(self, rest_manager):
        """创建大户持仓比数据收集器"""
        collector = TopTraderDataCollector(rest_manager)
        yield collector
        await collector.stop()
    
    @pytest.mark.asyncio
    async def test_collector_initialization(self, top_trader_collector):
        """测试收集器初始化"""
        assert top_trader_collector.rest_client_manager is not None
        assert not top_trader_collector.is_running
        assert len(top_trader_collector.callbacks) == 0
        assert len(top_trader_collector.symbols) > 0
    
    @pytest.mark.asyncio
    async def test_callback_registration(self, top_trader_collector):
        """测试回调函数注册"""
        callback_called = False
        received_data = None
        
        def test_callback(data):
            nonlocal callback_called, received_data
            callback_called = True
            received_data = data
        
        top_trader_collector.register_callback(test_callback)
        assert len(top_trader_collector.callbacks) == 1
    
    @pytest.mark.asyncio
    async def test_manual_collection(self, top_trader_collector):
        """测试手动数据收集"""
        # 设置较少的交易对进行测试
        test_symbols = ["BTC-USDT"]
        
        # 手动收集一次数据
        results = await top_trader_collector.collect_once()
        
        # 验证结果
        assert isinstance(results, list)
        
        # 如果有数据返回，验证数据格式
        for result in results:
            assert hasattr(result, 'exchange_name')
            assert hasattr(result, 'symbol_name')
            assert hasattr(result, 'long_short_ratio')
            assert hasattr(result, 'timestamp')
            
            # 验证数据类型
            assert isinstance(result.long_short_ratio, Decimal)
            assert isinstance(result.timestamp, datetime)
    
    @pytest.mark.asyncio
    async def test_binance_data_collection(self, top_trader_collector):
        """测试Binance数据收集"""
        # 设置客户端
        await top_trader_collector._setup_exchange_clients()
        
        # 测试收集Binance数据
        binance_client = top_trader_collector.clients.get(Exchange.BINANCE)
        if binance_client:
            result = await top_trader_collector._collect_binance_data(
                binance_client, "BTC-USDT"
            )
            
            if result:  # 如果成功获取数据
                assert result.exchange_name == "binance"
                assert result.symbol_name == "BTC-USDT"
                assert isinstance(result.long_short_ratio, Decimal)
                assert isinstance(result.timestamp, datetime)
    
    @pytest.mark.asyncio
    async def test_okx_data_collection(self, top_trader_collector):
        """测试OKX数据收集"""
        # 设置客户端
        await top_trader_collector._setup_exchange_clients()
        
        # 测试收集OKX数据
        okx_client = top_trader_collector.clients.get(Exchange.OKX)
        if okx_client:
            result = await top_trader_collector._collect_okx_data(
                okx_client, "BTC-USDT"
            )
            
            if result:  # 如果成功获取数据
                assert result.exchange_name == "okx"
                assert result.symbol_name == "BTC-USDT"
                assert isinstance(result.long_short_ratio, Decimal)
                assert isinstance(result.timestamp, datetime)
    
    @pytest.mark.asyncio
    async def test_stats_collection(self, top_trader_collector):
        """测试统计信息收集"""
        stats = top_trader_collector.get_stats()
        
        # 验证统计信息结构
        assert 'is_running' in stats
        assert 'symbols' in stats
        assert 'collection_interval' in stats
        assert 'total_collections' in stats
        assert 'successful_collections' in stats
        assert 'failed_collections' in stats
        assert 'success_rate' in stats
        assert 'data_points_collected' in stats
        assert 'exchanges' in stats
        assert 'rest_clients' in stats
        
        # 验证数据类型
        assert isinstance(stats['is_running'], bool)
        assert isinstance(stats['symbols'], list)
        assert isinstance(stats['collection_interval'], (int, float))
        assert isinstance(stats['total_collections'], int)


class TestIntegration:
    """集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_integration(self):
        """测试完整集成流程"""
        # 创建REST客户端管理器
        rest_manager = RestClientManager()
        
        try:
            # 创建大户持仓比数据收集器
            collector = TopTraderDataCollector(rest_manager)
            
            # 注册回调函数
            collected_data = []
            
            def data_callback(data):
                collected_data.append(data)
            
            collector.register_callback(data_callback)
            
            # 手动收集一次数据
            results = await collector.collect_once()
            
            # 验证结果
            print(f"收集到 {len(results)} 条数据")
            
            for result in results:
                print(f"交易所: {result.exchange_name}")
                print(f"交易对: {result.symbol_name}")
                print(f"多空比: {result.long_short_ratio}")
                print(f"时间: {result.timestamp}")
                print("---")
            
            # 获取统计信息
            stats = collector.get_stats()
            print(f"统计信息: {stats}")
            
            # 获取REST客户端统计
            rest_stats = rest_manager.get_all_stats()
            print(f"REST客户端统计: {rest_stats}")
            
        finally:
            # 清理资源
            await rest_manager.stop_all()


if __name__ == "__main__":
    # 运行集成测试
    async def run_integration_test():
        test = TestIntegration()
        await test.test_full_integration()
    
    print("开始运行大户持仓比数据收集器集成测试...")
    asyncio.run(run_integration_test())
    print("测试完成！") 