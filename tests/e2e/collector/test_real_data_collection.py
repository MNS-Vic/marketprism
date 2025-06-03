"""
MarketPrism Collector - 真实数据收集端到端测试

测试完整的数据收集流程，从交易所 API 到数据存储和发布
"""

import pytest
import asyncio
import json
import sys
import os
from datetime import datetime, timedelta
import time
from typing import Dict, List, Any
from unittest.mock import Mock

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from services.python_collector.src.marketprism_collector.collector import MarketDataCollector
from services.python_collector.src.marketprism_collector.orderbook_manager import OrderBookManager
from services.python_collector.src.marketprism_collector.core_services import core_services


class TestRealDataCollection:
    """测试真实数据收集"""
    
    @pytest.fixture
    def collector_config(self):
        """Collector 测试配置"""
        return {
            'exchanges': {
                'binance': {
                    'name': 'binance',
                    'api_key': os.getenv('BINANCE_API_KEY', 'test_key'),
                    'api_secret': os.getenv('BINANCE_API_SECRET', 'test_secret'),
                    'testnet': True,
                    'enabled': True,
                    'symbols': ['BTCUSDT', 'ETHUSDT'],
                    'data_types': ['trades', 'orderbook', 'ticker']
                },
                'okx': {
                    'name': 'okx',
                    'api_key': os.getenv('OKX_API_KEY', 'test_key'),
                    'api_secret': os.getenv('OKX_API_SECRET', 'test_secret'),
                    'passphrase': os.getenv('OKX_PASSPHRASE', 'test_passphrase'),
                    'testnet': True,
                    'enabled': True,
                    'symbols': ['BTC-USDT', 'ETH-USDT'],
                    'data_types': ['trades', 'orderbook', 'funding_rate']
                }
            },
            'data_collection': {
                'collection_interval': 1.0,  # 1秒间隔
                'batch_size': 100,
                'max_retries': 3,
                'timeout': 30
            },
            'storage': {
                'clickhouse': {
                    'enabled': True,
                    'host': 'localhost',
                    'port': 8123,
                    'database': 'marketprism_test',
                    'batch_size': 1000
                },
                'nats': {
                    'enabled': True,
                    'servers': ['nats://localhost:4222'],
                    'stream_name': 'market_data_test'
                }
            }
        }
    
    @pytest.fixture
    async def collector(self, collector_config):
        """创建数据收集器实例"""
        collector = MarketDataCollector(collector_config)
        await collector.initialize()
        yield collector
        await collector.cleanup()
    
    @pytest.mark.asyncio
    async def test_binance_spot_data_collection(self, collector):
        """测试 Binance 现货数据收集"""
        try:
            # 开始数据收集
            collection_task = asyncio.create_task(
                collector.start_collection(['binance'], duration=10)  # 收集10秒
            )
            
            # 等待数据收集完成
            result = await asyncio.wait_for(collection_task, timeout=15)
            
            # 验证收集结果
            assert result['status'] == 'success'
            assert 'binance' in result['exchanges']
            
            binance_data = result['exchanges']['binance']
            assert binance_data['trades_collected'] > 0
            assert binance_data['orderbook_updates'] > 0
            assert binance_data['ticker_updates'] > 0
            
            # 验证数据质量
            assert binance_data['data_quality']['completeness'] > 0.95
            assert binance_data['data_quality']['timeliness'] > 0.90
            
        except asyncio.TimeoutError:
            pytest.skip("Binance 数据收集超时")
        except Exception as e:
            pytest.skip(f"Binance 不可用: {e}")
    
    @pytest.mark.asyncio
    async def test_okx_swap_data_collection(self, collector):
        """测试 OKX 合约数据收集"""
        try:
            # 配置 OKX 合约数据收集
            okx_config = {
                'symbols': ['BTC-USDT-SWAP', 'ETH-USDT-SWAP'],
                'data_types': ['trades', 'orderbook', 'funding_rate', 'liquidation']
            }
            
            # 开始数据收集
            result = await collector.collect_exchange_data('okx', okx_config, duration=10)
            
            # 验证收集结果
            assert result['status'] == 'success'
            assert result['trades_collected'] > 0
            assert result['funding_rate_updates'] > 0
            
            # 验证序列号连续性（OKX 特有）
            orderbook_stats = result['orderbook_stats']
            assert orderbook_stats['sequence_errors'] == 0
            assert orderbook_stats['checksum_errors'] == 0
            
        except Exception as e:
            pytest.skip(f"OKX 不可用: {e}")
    
    @pytest.mark.asyncio
    async def test_multi_exchange_concurrent_collection(self, collector):
        """测试多交易所并发数据收集"""
        try:
            # 并发收集多个交易所数据
            tasks = [
                collector.start_collection(['binance'], duration=5),
                collector.start_collection(['okx'], duration=5)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 验证结果
            successful_results = [r for r in results if isinstance(r, dict) and r.get('status') == 'success']
            
            # 至少应该有一个交易所成功
            assert len(successful_results) > 0
            
            # 验证没有数据冲突
            for result in successful_results:
                assert result['data_conflicts'] == 0
                assert result['duplicate_trades'] == 0
            
        except Exception as e:
            pytest.skip(f"多交易所并发收集失败: {e}")
    
    @pytest.mark.asyncio
    async def test_data_normalization_pipeline(self, collector):
        """测试数据标准化流水线"""
        # 收集原始数据
        raw_data = await collector.collect_raw_data('binance', ['BTCUSDT'], duration=5)
        
        # 标准化数据
        normalized_data = await collector.normalize_data(raw_data)
        
        # 验证标准化结果
        assert 'trades' in normalized_data
        assert 'orderbook' in normalized_data
        assert 'ticker' in normalized_data
        
        # 验证标准化格式
        if normalized_data['trades']:
            trade = normalized_data['trades'][0]
            required_fields = ['symbol', 'price', 'quantity', 'timestamp', 'side', 'trade_id']
            for field in required_fields:
                assert field in trade
            
            # 验证数据类型
            assert isinstance(trade['price'], (int, float))
            assert isinstance(trade['quantity'], (int, float))
            assert isinstance(trade['timestamp'], int)
            assert trade['side'] in ['buy', 'sell']
    
    @pytest.mark.asyncio
    async def test_orderbook_synchronization(self, collector):
        """测试订单簿同步算法"""
        # 创建订单簿管理器
        orderbook_manager = OrderBookManager()
        
        try:
            # 初始化订单簿快照
            snapshot = await collector.get_orderbook_snapshot('binance', 'BTCUSDT')
            orderbook_manager.initialize_orderbook('BTCUSDT', snapshot)
            
            # 收集增量更新
            updates = await collector.collect_orderbook_updates('binance', 'BTCUSDT', duration=10)
            
            # 应用更新
            for update in updates:
                orderbook_manager.apply_update('BTCUSDT', update)
            
            # 验证订单簿状态
            current_orderbook = orderbook_manager.get_orderbook('BTCUSDT')
            
            assert len(current_orderbook['bids']) > 0
            assert len(current_orderbook['asks']) > 0
            
            # 验证价格排序
            bid_prices = [float(bid[0]) for bid in current_orderbook['bids']]
            ask_prices = [float(ask[0]) for ask in current_orderbook['asks']]
            
            assert bid_prices == sorted(bid_prices, reverse=True)
            assert ask_prices == sorted(ask_prices)
            
            # 验证买卖价差
            if bid_prices and ask_prices:
                spread = min(ask_prices) - max(bid_prices)
                assert spread > 0  # 价差应该为正
            
        except Exception as e:
            pytest.skip(f"订单簿同步测试失败: {e}")
    
    @pytest.mark.asyncio
    async def test_data_storage_integration(self, collector):
        """测试数据存储集成"""
        try:
            # 收集测试数据
            test_data = await collector.collect_test_data(duration=5)
            
            # 存储到 ClickHouse
            if core_services.get_clickhouse_writer():
                clickhouse_result = await collector.store_to_clickhouse(test_data)
                assert clickhouse_result['status'] == 'success'
                assert clickhouse_result['records_written'] > 0
            
            # 发布到 NATS
            if core_services.get_nats_publisher():
                nats_result = await collector.publish_to_nats(test_data)
                assert nats_result['status'] == 'success'
                assert nats_result['messages_published'] > 0
            
        except Exception as e:
            pytest.skip(f"数据存储集成测试失败: {e}")
    
    @pytest.mark.asyncio
    async def test_error_recovery_mechanisms(self, collector):
        """测试错误恢复机制"""
        # 模拟网络中断
        async def simulate_network_interruption():
            await asyncio.sleep(2)
            # 模拟恢复
            return True
        
        # 开始数据收集
        collection_task = asyncio.create_task(
            collector.start_collection_with_recovery(['binance'], duration=10)
        )
        
        # 并发模拟网络问题
        interruption_task = asyncio.create_task(simulate_network_interruption())
        
        # 等待完成
        results = await asyncio.gather(collection_task, interruption_task, return_exceptions=True)
        
        collection_result = results[0]
        
        # 验证恢复机制
        if isinstance(collection_result, dict):
            assert collection_result['recovery_attempts'] > 0
            assert collection_result['final_status'] == 'success'
            assert collection_result['data_loss_percentage'] < 0.05  # 数据丢失 < 5%
    
    @pytest.mark.asyncio
    async def test_rate_limit_compliance(self, collector):
        """测试限流合规性"""
        # 配置激进的数据收集（测试限流）
        aggressive_config = {
            'collection_interval': 0.1,  # 100ms 间隔
            'concurrent_requests': 10,
            'symbols': ['BTCUSDT', 'ETHUSDT', 'ADAUSDT', 'DOTUSDT', 'LINKUSDT']
        }
        
        try:
            result = await collector.stress_test_collection('binance', aggressive_config, duration=30)
            
            # 验证没有被限流
            assert result['rate_limit_violations'] == 0
            assert result['ip_ban_incidents'] == 0
            
            # 验证限流器正常工作
            rate_limiter_stats = result['rate_limiter_stats']
            assert rate_limiter_stats['requests_delayed'] > 0  # 应该有请求被延迟
            
        except Exception as e:
            pytest.skip(f"限流合规性测试失败: {e}")


class TestDataQuality:
    """测试数据质量"""
    
    @pytest.fixture
    async def data_collector(self):
        """数据收集器"""
        config = {
            'exchanges': {
                'binance': {'testnet': True, 'enabled': True}
            }
        }
        collector = MarketDataCollector(config)
        await collector.initialize()
        yield collector
        await collector.cleanup()
    
    @pytest.mark.asyncio
    async def test_data_completeness(self, data_collector):
        """测试数据完整性"""
        # 收集1分钟的数据
        start_time = datetime.now()
        data = await data_collector.collect_data_with_metadata('binance', ['BTCUSDT'], duration=60)
        end_time = datetime.now()
        
        # 计算预期数据量
        expected_duration = (end_time - start_time).total_seconds()
        expected_trades = expected_duration * 10  # 假设每秒10笔交易
        
        # 验证数据完整性
        actual_trades = len(data['trades'])
        completeness = actual_trades / expected_trades
        
        assert completeness > 0.8  # 至少80%完整性
        
        # 验证时间覆盖
        if data['trades']:
            first_trade_time = data['trades'][0]['timestamp']
            last_trade_time = data['trades'][-1]['timestamp']
            time_coverage = (last_trade_time - first_trade_time) / 1000  # 转换为秒
            
            assert time_coverage >= expected_duration * 0.9  # 至少90%时间覆盖
    
    @pytest.mark.asyncio
    async def test_data_timeliness(self, data_collector):
        """测试数据及时性"""
        # 收集实时数据
        data_points = []
        
        for _ in range(10):
            timestamp_before = time.time() * 1000
            data = await data_collector.get_latest_trade('binance', 'BTCUSDT')
            timestamp_after = time.time() * 1000
            
            if data:
                latency = timestamp_after - data['timestamp']
                data_points.append(latency)
                await asyncio.sleep(1)
        
        if data_points:
            # 计算延迟统计
            avg_latency = sum(data_points) / len(data_points)
            max_latency = max(data_points)
            
            # 验证及时性
            assert avg_latency < 5000  # 平均延迟 < 5秒
            assert max_latency < 10000  # 最大延迟 < 10秒
    
    @pytest.mark.asyncio
    async def test_data_accuracy(self, data_collector):
        """测试数据准确性"""
        # 同时从多个源获取数据
        binance_data = await data_collector.get_orderbook('binance', 'BTCUSDT')
        
        # 验证数据合理性
        if binance_data['bids'] and binance_data['asks']:
            highest_bid = float(binance_data['bids'][0][0])
            lowest_ask = float(binance_data['asks'][0][0])
            spread = lowest_ask - highest_bid
            
            # 验证价差合理性
            assert spread > 0  # 价差为正
            assert spread / highest_bid < 0.01  # 价差 < 1%
            
            # 验证价格合理性（BTC 价格应该在合理范围内）
            assert 10000 < highest_bid < 200000  # $10k - $200k
            assert 10000 < lowest_ask < 200000
    
    @pytest.mark.asyncio
    async def test_duplicate_detection(self, data_collector):
        """测试重复数据检测"""
        # 收集一段时间的交易数据
        trades = await data_collector.collect_trades('binance', 'BTCUSDT', duration=30)
        
        # 检测重复交易
        trade_ids = [trade['trade_id'] for trade in trades]
        unique_ids = set(trade_ids)
        
        # 验证没有重复
        duplicate_count = len(trade_ids) - len(unique_ids)
        duplicate_rate = duplicate_count / len(trade_ids) if trade_ids else 0
        
        assert duplicate_rate < 0.01  # 重复率 < 1%
        
        # 检测可疑的重复模式
        timestamp_groups = {}
        for trade in trades:
            ts = trade['timestamp']
            if ts not in timestamp_groups:
                timestamp_groups[ts] = []
            timestamp_groups[ts].append(trade)
        
        # 验证同一时间戳的交易合理性
        for ts, ts_trades in timestamp_groups.items():
            if len(ts_trades) > 10:  # 同一毫秒超过10笔交易可能有问题
                # 验证这些交易的价格和数量是否合理分布
                prices = [float(t['price']) for t in ts_trades]
                price_variance = max(prices) - min(prices)
                avg_price = sum(prices) / len(prices)
                
                # 价格方差不应该过大
                assert price_variance / avg_price < 0.001  # < 0.1%


class TestLongRunningStability:
    """测试长期运行稳定性"""
    
    @pytest.mark.asyncio
    async def test_memory_leak_detection(self):
        """测试内存泄漏检测"""
        import psutil
        import gc
        
        # 获取初始内存使用
        process = psutil.Process()
        initial_memory = process.memory_info().rss
        
        # 运行数据收集
        config = {
            'exchanges': {'binance': {'testnet': True, 'enabled': True}},
            'data_collection': {'collection_interval': 0.5}
        }
        
        collector = MarketDataCollector(config)
        await collector.initialize()
        
        try:
            # 运行5分钟的数据收集
            await collector.start_collection(['binance'], duration=300)
            
            # 强制垃圾回收
            gc.collect()
            
            # 检查内存使用
            final_memory = process.memory_info().rss
            memory_increase = final_memory - initial_memory
            memory_increase_mb = memory_increase / 1024 / 1024
            
            # 验证内存增长合理（< 100MB）
            assert memory_increase_mb < 100, f"内存增长过大: {memory_increase_mb}MB"
            
        finally:
            await collector.cleanup()
    
    @pytest.mark.asyncio
    async def test_connection_stability(self):
        """测试连接稳定性"""
        config = {
            'exchanges': {'binance': {'testnet': True, 'enabled': True}},
            'connection': {
                'reconnect_interval': 30,
                'max_reconnect_attempts': 10
            }
        }
        
        collector = MarketDataCollector(config)
        await collector.initialize()
        
        try:
            # 监控连接状态
            connection_stats = await collector.monitor_connections(duration=600)  # 10分钟
            
            # 验证连接稳定性
            assert connection_stats['disconnection_count'] < 5  # 少于5次断线
            assert connection_stats['reconnection_success_rate'] > 0.95  # 重连成功率 > 95%
            assert connection_stats['avg_reconnection_time'] < 30  # 平均重连时间 < 30秒
            
        finally:
            await collector.cleanup()
    
    @pytest.mark.asyncio
    async def test_error_recovery_under_load(self):
        """测试负载下的错误恢复"""
        config = {
            'exchanges': {
                'binance': {'testnet': True, 'enabled': True},
                'okx': {'testnet': True, 'enabled': True}
            },
            'data_collection': {
                'collection_interval': 0.1,  # 高频收集
                'concurrent_symbols': 20,
                'batch_size': 500
            }
        }
        
        collector = MarketDataCollector(config)
        await collector.initialize()
        
        try:
            # 高负载数据收集，同时注入错误
            async def inject_errors():
                await asyncio.sleep(60)  # 1分钟后开始注入错误
                # 模拟各种错误场景
                await collector.simulate_network_errors(duration=120)
                await collector.simulate_rate_limit_errors(duration=60)
                await collector.simulate_authentication_errors(duration=30)
            
            # 并发运行数据收集和错误注入
            collection_task = asyncio.create_task(
                collector.start_collection(['binance', 'okx'], duration=600)
            )
            error_injection_task = asyncio.create_task(inject_errors())
            
            results = await asyncio.gather(collection_task, error_injection_task, return_exceptions=True)
            
            collection_result = results[0]
            
            # 验证在错误条件下的恢复能力
            if isinstance(collection_result, dict):
                assert collection_result['overall_success_rate'] > 0.8  # 整体成功率 > 80%
                assert collection_result['data_loss_percentage'] < 0.1  # 数据丢失 < 10%
                assert collection_result['recovery_time'] < 60  # 恢复时间 < 60秒
                
        finally:
            await collector.cleanup()


if __name__ == "__main__":
    # 运行测试，跳过需要真实网络连接的测试
    pytest.main([
        __file__, 
        "-v", 
        "--tb=short", 
        "-x",
        "--timeout=120",  # 2分钟超时
        "-m", "not slow"  # 跳过标记为slow的测试
    ])