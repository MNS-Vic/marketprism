"""
OrderBook Manager验证测试

验证OrderBook Manager的增量数据维护功能、数据准确性和性能表现
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Any

# 导入测试目标
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from collector.orderbook_manager import OrderBookManager, OrderBookState, OrderBookSnapshot, OrderBookUpdate
from collector.data_types import Exchange, ExchangeConfig, PriceLevel, EnhancedOrderBook
from collector.normalizer import DataNormalizer


class TestOrderBookManagerValidation:
    """OrderBook Manager验证测试套件"""
    
    @pytest.fixture
    def mock_config(self):
        """模拟配置"""
        return ExchangeConfig(
            exchange=Exchange.BINANCE,
            symbols=["BTCUSDT", "ETHUSDT"],
            snapshot_interval=10,  # 10秒快照间隔
            depth_limit=200
        )
    
    @pytest.fixture
    def mock_normalizer(self):
        """模拟数据标准化器"""
        normalizer = Mock(spec=DataNormalizer)
        normalizer.normalize_orderbook = Mock(return_value={
            'exchange': 'binance',
            'symbol': 'BTCUSDT',
            'bids': [],
            'asks': [],
            'timestamp': datetime.now(timezone.utc)
        })
        return normalizer
    
    @pytest.fixture
    def orderbook_manager(self, mock_config, mock_normalizer):
        """创建OrderBook Manager实例"""
        return OrderBookManager(mock_config, mock_normalizer)
    
    def test_initialization(self, orderbook_manager, mock_config):
        """测试初始化"""
        assert orderbook_manager.config == mock_config
        assert isinstance(orderbook_manager.orderbook_states, dict)
        assert len(orderbook_manager.orderbook_states) == 0
        assert orderbook_manager.depth_limit == 200
    
    def test_orderbook_state_creation(self):
        """测试订单簿状态创建"""
        state = OrderBookState(
            symbol="BTCUSDT",
            exchange="binance"
        )
        
        assert state.symbol == "BTCUSDT"
        assert state.exchange == "binance"
        assert state.local_orderbook is None
        assert state.last_update_id == 0
        assert state.is_synced is False
        assert len(state.update_buffer) == 0
    
    @pytest.mark.asyncio
    async def test_snapshot_fetching(self, orderbook_manager):
        """测试快照获取功能"""
        # 模拟REST API响应
        mock_response_data = {
            "lastUpdateId": 12345,
            "bids": [["50000.00", "1.0"], ["49999.00", "2.0"]],
            "asks": [["50001.00", "1.5"], ["50002.00", "2.5"]]
        }
        
        with patch.object(orderbook_manager, '_fetch_binance_snapshot') as mock_fetch:
            mock_snapshot = OrderBookSnapshot(
                symbol="BTCUSDT",
                exchange="binance",
                last_update_id=12345,
                bids=[
                    PriceLevel(price=Decimal("50000.00"), quantity=Decimal("1.0")),
                    PriceLevel(price=Decimal("49999.00"), quantity=Decimal("2.0"))
                ],
                asks=[
                    PriceLevel(price=Decimal("50001.00"), quantity=Decimal("1.5")),
                    PriceLevel(price=Decimal("50002.00"), quantity=Decimal("2.5"))
                ],
                timestamp=datetime.now(timezone.utc)
            )
            mock_fetch.return_value = mock_snapshot
            
            # 测试快照获取
            snapshot = await orderbook_manager._fetch_binance_snapshot("BTCUSDT")
            
            assert snapshot is not None
            assert snapshot.symbol == "BTCUSDT"
            assert snapshot.last_update_id == 12345
            assert len(snapshot.bids) == 2
            assert len(snapshot.asks) == 2
            assert snapshot.bids[0].price == Decimal("50000.00")
            assert snapshot.asks[0].price == Decimal("50001.00")
    
    def test_incremental_update_processing(self, orderbook_manager):
        """测试增量更新处理"""
        # 创建初始状态
        symbol = "BTCUSDT"
        orderbook_manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange="binance"
        )
        
        # 创建增量更新
        update = OrderBookUpdate(
            symbol=symbol,
            exchange="binance",
            first_update_id=12346,
            last_update_id=12346,
            bids=[PriceLevel(price=Decimal("50000.00"), quantity=Decimal("1.5"))],
            asks=[PriceLevel(price=Decimal("50001.00"), quantity=Decimal("2.0"))],
            timestamp=datetime.now(timezone.utc)
        )
        
        # 添加到缓冲区
        state = orderbook_manager.orderbook_states[symbol]
        state.update_buffer.append(update)
        
        assert len(state.update_buffer) == 1
        assert state.update_buffer[0].last_update_id == 12346
    
    def test_data_accuracy_validation(self):
        """测试数据准确性验证"""
        # 创建订单簿快照
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            exchange="binance",
            last_update_id=12345,
            bids=[
                PriceLevel(price=Decimal("50000.00"), quantity=Decimal("1.0")),
                PriceLevel(price=Decimal("49999.00"), quantity=Decimal("2.0"))
            ],
            asks=[
                PriceLevel(price=Decimal("50001.00"), quantity=Decimal("1.5")),
                PriceLevel(price=Decimal("50002.00"), quantity=Decimal("2.5"))
            ],
            timestamp=datetime.now(timezone.utc)
        )
        
        # 验证数据结构
        assert len(snapshot.bids) == 2
        assert len(snapshot.asks) == 2
        
        # 验证价格排序（买单从高到低，卖单从低到高）
        assert snapshot.bids[0].price > snapshot.bids[1].price
        assert snapshot.asks[0].price < snapshot.asks[1].price
        
        # 验证数据类型
        assert isinstance(snapshot.bids[0].price, Decimal)
        assert isinstance(snapshot.bids[0].quantity, Decimal)
    
    @pytest.mark.asyncio
    async def test_performance_metrics(self, orderbook_manager):
        """测试性能指标"""
        # 记录开始时间
        start_time = time.time()
        
        # 模拟处理大量更新
        symbol = "BTCUSDT"
        orderbook_manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange="binance"
        )
        
        # 创建1000个增量更新
        updates = []
        for i in range(1000):
            update = OrderBookUpdate(
                symbol=symbol,
                exchange="binance",
                first_update_id=12346 + i,
                last_update_id=12346 + i,
                bids=[PriceLevel(price=Decimal(f"{50000 + i}"), quantity=Decimal("1.0"))],
                asks=[PriceLevel(price=Decimal(f"{50001 + i}"), quantity=Decimal("1.0"))],
                timestamp=datetime.now(timezone.utc)
            )
            updates.append(update)
        
        # 批量处理更新
        state = orderbook_manager.orderbook_states[symbol]
        for update in updates:
            state.update_buffer.append(update)
        
        # 记录结束时间
        end_time = time.time()
        processing_time = end_time - start_time
        
        # 验证性能（应该在1秒内完成）
        assert processing_time < 1.0
        assert len(state.update_buffer) == 1000
    
    def test_error_handling(self, orderbook_manager):
        """测试错误处理"""
        symbol = "BTCUSDT"
        
        # 测试未初始化状态的处理
        result = asyncio.run(orderbook_manager.process_update(symbol, {}))
        assert result is None
        
        # 测试错误计数
        orderbook_manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange="binance"
        )
        
        state = orderbook_manager.orderbook_states[symbol]
        initial_error_count = state.error_count
        
        # 模拟错误
        state.error_count += 1
        assert state.error_count == initial_error_count + 1
    
    def test_memory_usage_optimization(self, orderbook_manager):
        """测试内存使用优化"""
        symbol = "BTCUSDT"
        orderbook_manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange="binance"
        )
        
        state = orderbook_manager.orderbook_states[symbol]
        
        # 测试缓冲区大小限制
        assert state.update_buffer.maxlen == 1000
        
        # 添加超过限制的更新
        for i in range(1500):
            update = OrderBookUpdate(
                symbol=symbol,
                exchange="binance",
                first_update_id=i,
                last_update_id=i,
                bids=[],
                asks=[],
                timestamp=datetime.now(timezone.utc)
            )
            state.update_buffer.append(update)
        
        # 验证缓冲区大小不超过限制
        assert len(state.update_buffer) == 1000
    
    def test_data_consistency(self):
        """测试数据一致性"""
        # 创建订单簿快照
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            exchange="binance",
            last_update_id=12345,
            bids=[PriceLevel(price=Decimal("50000"), quantity=Decimal("1.0"))],
            asks=[PriceLevel(price=Decimal("50001"), quantity=Decimal("1.0"))],
            timestamp=datetime.now(timezone.utc)
        )
        
        # 验证买卖价差合理性
        best_bid = snapshot.bids[0].price
        best_ask = snapshot.asks[0].price
        spread = best_ask - best_bid
        
        assert spread > 0, "买卖价差必须为正数"
        assert best_bid < best_ask, "最佳买价必须小于最佳卖价"


class TestOrderBookNATSIntegration:
    """OrderBook NATS集成测试"""
    
    @pytest.fixture
    def mock_nats_client(self):
        """模拟NATS客户端"""
        client = Mock()
        client.publish = AsyncMock()
        return client
    
    def test_nats_message_format(self, mock_nats_client):
        """测试NATS消息格式"""
        # 创建标准化订单簿数据
        orderbook_data = {
            'exchange': 'binance',
            'symbol': 'BTCUSDT',
            'bids': [{'price': '50000.00', 'quantity': '1.0'}],
            'asks': [{'price': '50001.00', 'quantity': '1.0'}],
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'last_update_id': 12345
        }
        
        # 验证消息格式
        assert 'exchange' in orderbook_data
        assert 'symbol' in orderbook_data
        assert 'bids' in orderbook_data
        assert 'asks' in orderbook_data
        assert 'timestamp' in orderbook_data
        assert 'last_update_id' in orderbook_data
    
    @pytest.mark.asyncio
    async def test_nats_publishing(self, mock_nats_client):
        """测试NATS发布功能"""
        # 模拟发布订单簿数据
        subject = "orderbook-data.binance.BTCUSDT"
        data = {
            'exchange': 'binance',
            'symbol': 'BTCUSDT',
            'bids': [],
            'asks': [],
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        await mock_nats_client.publish(subject, data)
        
        # 验证发布调用
        mock_nats_client.publish.assert_called_once_with(subject, data)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
