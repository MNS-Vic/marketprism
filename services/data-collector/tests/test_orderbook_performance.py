"""
OrderBook Manager性能测试

测试OrderBook Manager在高频数据更新下的性能表现
"""

import asyncio
import time
import statistics
from unittest.mock import Mock, AsyncMock
from datetime import datetime, timezone
from decimal import Decimal
import pytest

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from collector.orderbook_manager import OrderBookManager, OrderBookState, OrderBookSnapshot, OrderBookUpdate
from collector.data_types import Exchange, ExchangeConfig, PriceLevel
from collector.normalizer import DataNormalizer


class TestOrderBookPerformance:
    """OrderBook Manager性能测试"""
    
    @pytest.fixture
    def performance_config(self):
        """性能测试配置"""
        return ExchangeConfig(
            exchange=Exchange.BINANCE,
            symbols=["BTCUSDT"],
            snapshot_interval=10,
            depth_limit=200
        )
    
    @pytest.fixture
    def mock_normalizer(self):
        """模拟标准化器"""
        normalizer = Mock(spec=DataNormalizer)
        normalizer.normalize_orderbook = Mock(return_value={
            'exchange_name': 'binance',
            'symbol_name': 'BTCUSDT',
            'bids': [],
            'asks': [],
            'timestamp': datetime.now(timezone.utc)
        })
        return normalizer
    
    @pytest.fixture
    def mock_nats_client(self):
        """模拟NATS客户端"""
        client = Mock()
        client.publish = AsyncMock()
        return client
    
    @pytest.fixture
    def orderbook_manager(self, performance_config, mock_normalizer, mock_nats_client):
        """创建性能测试用的OrderBook Manager"""
        return OrderBookManager(performance_config, mock_normalizer, mock_nats_client)
    
    def create_test_snapshot(self, symbol: str, depth: int = 200) -> OrderBookSnapshot:
        """创建测试用订单簿快照"""
        base_price = Decimal("50000")
        
        # 创建买单（价格递减）
        bids = []
        for i in range(depth // 2):
            price = base_price - Decimal(str(i))
            quantity = Decimal("1.0") + Decimal(str(i * 0.1))
            bids.append(PriceLevel(price=price, quantity=quantity))
        
        # 创建卖单（价格递增）
        asks = []
        for i in range(depth // 2):
            price = base_price + Decimal(str(i + 1))
            quantity = Decimal("1.0") + Decimal(str(i * 0.1))
            asks.append(PriceLevel(price=price, quantity=quantity))
        
        return OrderBookSnapshot(
            symbol=symbol,
            exchange="binance",
            last_update_id=12345,
            bids=bids,
            asks=asks,
            timestamp=datetime.now(timezone.utc)
        )
    
    def create_test_update(self, symbol: str, update_id: int, num_changes: int = 10) -> OrderBookUpdate:
        """创建测试用增量更新"""
        base_price = Decimal("50000")
        
        # 创建买单更新
        bid_updates = []
        for i in range(num_changes // 2):
            price = base_price - Decimal(str(i))
            quantity = Decimal("1.5") + Decimal(str(i * 0.1))
            bid_updates.append(PriceLevel(price=price, quantity=quantity))
        
        # 创建卖单更新
        ask_updates = []
        for i in range(num_changes // 2):
            price = base_price + Decimal(str(i + 1))
            quantity = Decimal("1.5") + Decimal(str(i * 0.1))
            ask_updates.append(PriceLevel(price=price, quantity=quantity))
        
        return OrderBookUpdate(
            symbol=symbol,
            exchange="binance",
            first_update_id=update_id,
            last_update_id=update_id,
            bids=bid_updates,
            asks=ask_updates,
            timestamp=datetime.now(timezone.utc)
        )
    
    @pytest.mark.asyncio
    async def test_snapshot_processing_performance(self, orderbook_manager):
        """测试快照处理性能"""
        symbol = "BTCUSDT"
        
        # 创建测试快照
        snapshot = self.create_test_snapshot(symbol, depth=200)
        
        # 测试快照处理时间
        start_time = time.time()
        
        # 初始化状态
        orderbook_manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange="binance"
        )
        
        # 设置快照
        state = orderbook_manager.orderbook_states[symbol]
        state.local_orderbook = snapshot
        state.is_synced = True
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # 验证性能（应该在10ms内完成）
        assert processing_time < 0.01, f"快照处理时间过长: {processing_time:.4f}s"
        assert len(state.local_orderbook.bids) == 100
        assert len(state.local_orderbook.asks) == 100
    
    @pytest.mark.asyncio
    async def test_incremental_update_performance(self, orderbook_manager):
        """测试增量更新性能"""
        symbol = "BTCUSDT"
        
        # 初始化订单簿
        snapshot = self.create_test_snapshot(symbol, depth=200)
        orderbook_manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange="binance"
        )
        state = orderbook_manager.orderbook_states[symbol]
        state.local_orderbook = snapshot
        state.is_synced = True
        
        # 创建多个增量更新
        updates = []
        for i in range(100):
            update = self.create_test_update(symbol, 12346 + i, num_changes=10)
            updates.append(update)
        
        # 测试批量更新性能
        start_time = time.time()
        
        for update in updates:
            enhanced_orderbook = await orderbook_manager._apply_update(symbol, update)
            assert enhanced_orderbook is not None
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # 验证性能（100个更新应该在100ms内完成）
        assert processing_time < 0.1, f"增量更新处理时间过长: {processing_time:.4f}s"
        
        # 计算平均每个更新的处理时间
        avg_time_per_update = processing_time / len(updates)
        assert avg_time_per_update < 0.001, f"单个更新平均时间过长: {avg_time_per_update:.6f}s"
    
    @pytest.mark.asyncio
    async def test_high_frequency_updates(self, orderbook_manager):
        """测试高频更新性能"""
        symbol = "BTCUSDT"
        
        # 初始化订单簿
        snapshot = self.create_test_snapshot(symbol, depth=200)
        orderbook_manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange="binance"
        )
        state = orderbook_manager.orderbook_states[symbol]
        state.local_orderbook = snapshot
        state.is_synced = True
        
        # 模拟高频更新（1000个更新）
        num_updates = 1000
        processing_times = []
        
        for i in range(num_updates):
            update = self.create_test_update(symbol, 12346 + i, num_changes=5)
            
            start_time = time.time()
            enhanced_orderbook = await orderbook_manager._apply_update(symbol, update)
            end_time = time.time()
            
            processing_times.append(end_time - start_time)
            assert enhanced_orderbook is not None
        
        # 统计分析
        total_time = sum(processing_times)
        avg_time = statistics.mean(processing_times)
        median_time = statistics.median(processing_times)
        max_time = max(processing_times)
        
        # 性能验证
        assert total_time < 1.0, f"总处理时间过长: {total_time:.4f}s"
        assert avg_time < 0.001, f"平均处理时间过长: {avg_time:.6f}s"
        assert max_time < 0.01, f"最大处理时间过长: {max_time:.6f}s"
        
        print(f"高频更新性能统计:")
        print(f"  总更新数: {num_updates}")
        print(f"  总时间: {total_time:.4f}s")
        print(f"  平均时间: {avg_time:.6f}s")
        print(f"  中位数时间: {median_time:.6f}s")
        print(f"  最大时间: {max_time:.6f}s")
        print(f"  吞吐量: {num_updates/total_time:.0f} updates/s")
    
    @pytest.mark.asyncio
    async def test_memory_usage_under_load(self, orderbook_manager):
        """测试负载下的内存使用"""
        symbol = "BTCUSDT"
        
        # 初始化订单簿
        snapshot = self.create_test_snapshot(symbol, depth=200)
        orderbook_manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange="binance"
        )
        state = orderbook_manager.orderbook_states[symbol]
        state.local_orderbook = snapshot
        state.is_synced = True
        
        # 测试缓冲区大小限制
        initial_buffer_size = len(state.update_buffer)
        
        # 添加大量更新到缓冲区
        for i in range(2000):  # 超过maxlen=1000的限制
            update = self.create_test_update(symbol, i, num_changes=5)
            state.update_buffer.append(update)
        
        # 验证缓冲区大小不超过限制
        assert len(state.update_buffer) == 1000, f"缓冲区大小超过限制: {len(state.update_buffer)}"
        
        # 验证最新的更新被保留
        latest_update = state.update_buffer[-1]
        assert latest_update.last_update_id >= 1999
    
    @pytest.mark.asyncio
    async def test_nats_publishing_performance(self, orderbook_manager, mock_nats_client):
        """测试NATS发布性能"""
        symbol = "BTCUSDT"
        
        # 初始化订单簿
        snapshot = self.create_test_snapshot(symbol, depth=200)
        orderbook_manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange="binance"
        )
        state = orderbook_manager.orderbook_states[symbol]
        state.local_orderbook = snapshot
        state.is_synced = True
        
        # 测试NATS发布性能
        num_publishes = 100
        start_time = time.time()
        
        for i in range(num_publishes):
            update = self.create_test_update(symbol, 12346 + i, num_changes=10)
            enhanced_orderbook = await orderbook_manager._apply_update(symbol, update)
            # _apply_update内部会调用_publish_to_nats
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # 验证NATS发布调用
        assert mock_nats_client.publish.call_count == num_publishes
        
        # 验证性能（包含NATS发布的总时间）
        avg_time_with_nats = total_time / num_publishes
        assert avg_time_with_nats < 0.01, f"包含NATS发布的平均时间过长: {avg_time_with_nats:.6f}s"
        
        print(f"NATS发布性能统计:")
        print(f"  发布次数: {num_publishes}")
        print(f"  总时间: {total_time:.4f}s")
        print(f"  平均时间: {avg_time_with_nats:.6f}s")
        print(f"  发布吞吐量: {num_publishes/total_time:.0f} publishes/s")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
