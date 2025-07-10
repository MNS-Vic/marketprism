"""
OrderBook Manager集成测试

测试OrderBook Manager与实际数据源和NATS的集成
"""

import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone
from decimal import Decimal
import pytest

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from collector.orderbook_manager import OrderBookManager, OrderBookState
from collector.data_types import Exchange, ExchangeConfig, PriceLevel
from collector.normalizer import DataNormalizer


class TestOrderBookIntegration:
    """OrderBook Manager集成测试"""
    
    @pytest.fixture
    def integration_config(self):
        """集成测试配置"""
        return ExchangeConfig(
            exchange=Exchange.BINANCE,
            symbols=["BTCUSDT", "ETHUSDT"],
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
            'bids': [PriceLevel(price=Decimal("50000"), quantity=Decimal("1.0"))],
            'asks': [PriceLevel(price=Decimal("50001"), quantity=Decimal("1.0"))],
            'timestamp': datetime.now(timezone.utc),
            'last_update_id': 12345
        })
        return normalizer
    
    @pytest.fixture
    def mock_nats_client(self):
        """模拟NATS客户端"""
        client = Mock()
        client.publish = AsyncMock()
        return client
    
    @pytest.fixture
    def orderbook_manager(self, integration_config, mock_normalizer, mock_nats_client):
        """创建集成测试用的OrderBook Manager"""
        return OrderBookManager(integration_config, mock_normalizer, mock_nats_client)
    
    @pytest.mark.asyncio
    async def test_full_orderbook_lifecycle(self, orderbook_manager):
        """测试完整的订单簿生命周期"""
        symbol = "BTCUSDT"
        
        # 1. 启动订单簿管理
        await orderbook_manager.start_symbol_management(symbol)
        
        # 验证状态初始化
        assert symbol in orderbook_manager.orderbook_states
        state = orderbook_manager.orderbook_states[symbol]
        assert state.symbol == symbol
        assert state.exchange == "binance"
        assert not state.is_synced
        
        # 2. 模拟快照同步
        mock_snapshot_data = {
            "lastUpdateId": 12345,
            "bids": [["50000.00", "1.0"], ["49999.00", "2.0"]],
            "asks": [["50001.00", "1.5"], ["50002.00", "2.5"]]
        }
        
        with patch.object(orderbook_manager, '_fetch_binance_snapshot') as mock_fetch:
            mock_snapshot = orderbook_manager._parse_binance_snapshot(symbol, mock_snapshot_data)
            mock_fetch.return_value = mock_snapshot
            
            # 执行同步
            success = await orderbook_manager._sync_orderbook(symbol)
            assert success
            
            # 验证同步状态
            assert state.is_synced
            assert state.local_orderbook is not None
            assert state.local_orderbook.last_update_id == 12345
        
        # 3. 模拟增量更新处理
        update_data = {
            "e": "depthUpdate",
            "E": int(datetime.now(timezone.utc).timestamp() * 1000),
            "s": symbol,
            "U": 12346,
            "u": 12346,
            "b": [["50000.00", "1.5"]],  # 买单更新
            "a": [["50001.00", "2.0"]]   # 卖单更新
        }
        
        # 处理更新
        result = await orderbook_manager.process_update(symbol, update_data)
        
        # 验证更新结果
        assert result is not None
        assert result.symbol_name == symbol
        assert result.last_update_id == 12346
        
        # 4. 清理
        if symbol in orderbook_manager.snapshot_tasks:
            orderbook_manager.snapshot_tasks[symbol].cancel()
    
    @pytest.mark.asyncio
    async def test_nats_integration(self, orderbook_manager, mock_nats_client):
        """测试NATS集成"""
        symbol = "BTCUSDT"
        
        # 初始化订单簿状态
        orderbook_manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange="binance"
        )
        
        # 创建测试订单簿快照
        snapshot_data = {
            "lastUpdateId": 12345,
            "bids": [["50000.00", "1.0"]],
            "asks": [["50001.00", "1.0"]]
        }
        
        snapshot = orderbook_manager._parse_binance_snapshot(symbol, snapshot_data)
        state = orderbook_manager.orderbook_states[symbol]
        state.local_orderbook = snapshot
        state.is_synced = True
        
        # 创建增量更新
        update_data = {
            "e": "depthUpdate",
            "E": int(datetime.now(timezone.utc).timestamp() * 1000),
            "s": symbol,
            "U": 12346,
            "u": 12346,
            "b": [["50000.00", "1.5"]],
            "a": [["50001.00", "2.0"]]
        }
        
        # 处理更新（会触发NATS发布）
        result = await orderbook_manager.process_update(symbol, update_data)
        
        # 验证NATS发布
        assert mock_nats_client.publish.called
        call_args = mock_nats_client.publish.call_args
        
        # 验证发布的主题
        subject = call_args[0][0]
        assert "orderbook-data.binance.BTCUSDT" in subject
        
        # 验证发布的数据
        message_data = json.loads(call_args[0][1].decode())
        assert message_data['exchange'] == 'binance'
        assert message_data['symbol'] == 'BTCUSDT'
        assert 'bids' in message_data
        assert 'asks' in message_data
        assert 'timestamp' in message_data
    
    @pytest.mark.asyncio
    async def test_error_recovery(self, orderbook_manager):
        """测试错误恢复机制"""
        symbol = "BTCUSDT"
        
        # 初始化状态
        orderbook_manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange="binance"
        )
        state = orderbook_manager.orderbook_states[symbol]
        
        # 模拟连续错误
        initial_error_count = state.error_count
        
        # 增加错误计数
        for i in range(3):
            state.error_count += 1
        
        assert state.error_count == initial_error_count + 3
        
        # 测试错误重置
        await orderbook_manager._reset_orderbook_state(symbol)
        
        # 验证状态重置
        reset_state = orderbook_manager.orderbook_states[symbol]
        assert reset_state.error_count == 0
        assert not reset_state.is_synced
        assert reset_state.local_orderbook is None
    
    @pytest.mark.asyncio
    async def test_multiple_symbols_management(self, orderbook_manager):
        """测试多交易对管理"""
        symbols = ["BTCUSDT", "ETHUSDT"]
        
        # 启动多个交易对的管理
        for symbol in symbols:
            await orderbook_manager.start_symbol_management(symbol)
        
        # 验证所有交易对都已初始化
        for symbol in symbols:
            assert symbol in orderbook_manager.orderbook_states
            state = orderbook_manager.orderbook_states[symbol]
            assert state.symbol == symbol
            assert state.exchange == "binance"
        
        # 验证任务创建
        for symbol in symbols:
            assert symbol in orderbook_manager.snapshot_tasks
        
        # 清理任务
        for symbol in symbols:
            if symbol in orderbook_manager.snapshot_tasks:
                orderbook_manager.snapshot_tasks[symbol].cancel()
    
    @pytest.mark.asyncio
    async def test_data_consistency_validation(self, orderbook_manager):
        """测试数据一致性验证"""
        symbol = "BTCUSDT"
        
        # 创建测试快照
        snapshot_data = {
            "lastUpdateId": 12345,
            "bids": [["50000.00", "1.0"], ["49999.00", "2.0"]],
            "asks": [["50001.00", "1.5"], ["50002.00", "2.5"]]
        }
        
        snapshot = orderbook_manager._parse_binance_snapshot(symbol, snapshot_data)
        
        # 验证数据一致性
        assert len(snapshot.bids) == 2
        assert len(snapshot.asks) == 2
        
        # 验证价格排序
        assert snapshot.bids[0].price > snapshot.bids[1].price  # 买单从高到低
        assert snapshot.asks[0].price < snapshot.asks[1].price  # 卖单从低到高
        
        # 验证买卖价差
        best_bid = snapshot.bids[0].price
        best_ask = snapshot.asks[0].price
        spread = best_ask - best_bid
        assert spread > 0, "买卖价差必须为正数"
    
    @pytest.mark.asyncio
    async def test_performance_under_load(self, orderbook_manager):
        """测试负载下的性能"""
        symbol = "BTCUSDT"
        
        # 初始化订单簿
        orderbook_manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange="binance"
        )
        
        snapshot_data = {
            "lastUpdateId": 12345,
            "bids": [["50000.00", "1.0"]],
            "asks": [["50001.00", "1.0"]]
        }
        
        snapshot = orderbook_manager._parse_binance_snapshot(symbol, snapshot_data)
        state = orderbook_manager.orderbook_states[symbol]
        state.local_orderbook = snapshot
        state.is_synced = True
        
        # 模拟高频更新
        num_updates = 100
        start_time = asyncio.get_event_loop().time()
        
        for i in range(num_updates):
            update_data = {
                "e": "depthUpdate",
                "E": int(datetime.now(timezone.utc).timestamp() * 1000),
                "s": symbol,
                "U": 12346 + i,
                "u": 12346 + i,
                "b": [["50000.00", f"{1.0 + i * 0.1}"]],
                "a": [["50001.00", f"{1.0 + i * 0.1}"]]
            }
            
            result = await orderbook_manager.process_update(symbol, update_data)
            assert result is not None
        
        end_time = asyncio.get_event_loop().time()
        total_time = end_time - start_time
        
        # 验证性能（100个更新应该在1秒内完成）
        assert total_time < 1.0, f"处理时间过长: {total_time:.4f}s"
        
        # 验证统计信息
        assert orderbook_manager.stats['updates_processed'] >= num_updates


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
