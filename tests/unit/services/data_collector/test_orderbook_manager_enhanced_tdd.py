"""
订单簿管理器增强TDD测试
专注于提升覆盖率到40%+，测试未覆盖的边缘情况和核心功能
"""

import pytest
import asyncio
import aiohttp
import json
import time
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, Optional, List
from collections import deque

try:
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), '../../../../services/data-collector/src'))

    from marketprism_collector.orderbook_manager import (
        OrderBookManager, OrderBookSnapshot, OrderBookUpdate, OrderBookState
    )
    from marketprism_collector.data_types import (
        Exchange, PriceLevel, EnhancedOrderBook, OrderBookDelta,
        OrderBookUpdateType, ExchangeConfig
    )
    from marketprism_collector.normalizer import DataNormalizer
    HAS_ORDERBOOK_MODULES = True
except ImportError as e:
    print(f"Import error: {e}")
    HAS_ORDERBOOK_MODULES = False


@pytest.mark.skipif(not HAS_ORDERBOOK_MODULES, reason="订单簿管理器模块不可用")
class TestOrderBookStateEdgeCases:
    """测试订单簿状态边缘情况"""
    
    def test_orderbook_state_post_init_with_existing_buffer(self):
        """测试：OrderBookState的__post_init__方法，已有缓冲区"""
        # 创建已有缓冲区的状态
        existing_buffer = deque([1, 2, 3])
        state = OrderBookState(
            symbol="BTCUSDT",
            exchange="binance",
            update_buffer=existing_buffer
        )
        
        # 验证缓冲区保持不变
        assert state.update_buffer is existing_buffer
        assert len(state.update_buffer) == 3
        assert list(state.update_buffer) == [1, 2, 3]
    
    def test_orderbook_state_post_init_without_buffer(self):
        """测试：OrderBookState的__post_init__方法，无缓冲区"""
        # 创建无缓冲区的状态
        state = OrderBookState(
            symbol="BTCUSDT",
            exchange="binance"
        )
        
        # 验证缓冲区被创建
        assert state.update_buffer is not None
        assert isinstance(state.update_buffer, deque)
        assert state.update_buffer.maxlen == 1000
        assert len(state.update_buffer) == 0


@pytest.mark.skipif(not HAS_ORDERBOOK_MODULES, reason="订单簿管理器模块不可用")
class TestOrderBookManagerInitialization:
    """测试订单簿管理器初始化"""
    
    @pytest.fixture
    def mock_config(self):
        """创建模拟配置"""
        config = Mock(spec=ExchangeConfig)
        config.exchange = Exchange.BINANCE
        config.snapshot_interval = 60
        return config
    
    @pytest.fixture
    def mock_normalizer(self):
        """创建模拟数据标准化器"""
        return Mock(spec=DataNormalizer)
    
    def test_orderbook_manager_initialization_binance(self, mock_config, mock_normalizer):
        """测试：Binance订单簿管理器初始化"""
        mock_config.exchange = Exchange.BINANCE
        
        manager = OrderBookManager(mock_config, mock_normalizer)
        
        # 验证基本属性
        assert manager.config is mock_config
        assert manager.normalizer is mock_normalizer
        assert manager.snapshot_interval == 60
        assert manager.depth_limit == 400
        assert manager.max_error_count == 5
        assert manager.sync_timeout == 30
        
        # 验证状态管理字典
        assert isinstance(manager.orderbook_states, dict)
        assert isinstance(manager.snapshot_tasks, dict)
        assert isinstance(manager.update_tasks, dict)
        
        # 验证统计信息
        assert manager.stats['snapshots_fetched'] == 0
        assert manager.stats['updates_processed'] == 0
        assert manager.stats['sync_errors'] == 0
        assert manager.stats['resync_count'] == 0
    
    def test_orderbook_manager_initialization_okx(self, mock_config, mock_normalizer):
        """测试：OKX订单簿管理器初始化"""
        mock_config.exchange = Exchange.OKX
        
        manager = OrderBookManager(mock_config, mock_normalizer)
        
        # 验证OKX特定配置
        assert hasattr(manager, 'okx_snapshot_sync_interval')
        assert manager.okx_snapshot_sync_interval == 300
        assert hasattr(manager, 'okx_ws_client')
        assert manager.okx_ws_client is None
        assert hasattr(manager, 'okx_snapshot_sync_tasks')
        assert isinstance(manager.okx_snapshot_sync_tasks, dict)
    
    def test_orderbook_manager_initialization_api_limits(self, mock_config, mock_normalizer):
        """测试：订单簿管理器API限制初始化"""
        manager = OrderBookManager(mock_config, mock_normalizer)
        
        # 验证API频率限制配置
        assert isinstance(manager.last_snapshot_request, dict)
        assert manager.min_snapshot_interval == 30.0
        assert manager.api_weight_used == 0
        assert manager.api_weight_limit == 1200
        assert isinstance(manager.weight_reset_time, datetime)
        assert manager.consecutive_errors == 0
        assert manager.backoff_multiplier == 1.0
        
        # 验证HTTP客户端初始化
        assert manager.session is None


@pytest.mark.skipif(not HAS_ORDERBOOK_MODULES, reason="订单簿管理器模块不可用")
class TestOrderBookManagerStartStop:
    """测试订单簿管理器启动和停止"""
    
    @pytest.fixture
    def mock_config(self):
        """创建模拟配置"""
        config = Mock(spec=ExchangeConfig)
        config.exchange = Exchange.BINANCE
        config.snapshot_interval = 60
        return config
    
    @pytest.fixture
    def mock_normalizer(self):
        """创建模拟数据标准化器"""
        return Mock(spec=DataNormalizer)
    
    @pytest.fixture
    def manager(self, mock_config, mock_normalizer):
        """创建测试用的订单簿管理器"""
        return OrderBookManager(mock_config, mock_normalizer)
    
    @pytest.mark.asyncio
    async def test_start_binance_without_proxy(self, manager):
        """测试：启动Binance订单簿管理器（无代理）"""
        symbols = ["BTCUSDT", "ETHUSDT"]
        
        with patch.dict('os.environ', {}, clear=True):
            with patch('aiohttp.TCPConnector') as mock_connector:
                with patch('aiohttp.ClientSession') as mock_session:
                    with patch.object(manager, 'start_symbol_management') as mock_start_symbol:
                        mock_connector.return_value = Mock()
                        mock_session.return_value = Mock()
                        
                        result = await manager.start(symbols)
                        
                        # 验证启动成功
                        assert result is True
                        
                        # 验证HTTP客户端创建
                        mock_connector.assert_called_once_with(limit=100)
                        mock_session.assert_called_once()
                        
                        # 验证代理设置
                        assert manager.proxy is None
                        
                        # 验证每个交易对都启动了管理
                        assert mock_start_symbol.call_count == len(symbols)
                        mock_start_symbol.assert_any_call("BTCUSDT")
                        mock_start_symbol.assert_any_call("ETHUSDT")
    
    @pytest.mark.asyncio
    async def test_start_binance_with_proxy(self, manager):
        """测试：启动Binance订单簿管理器（有代理）"""
        symbols = ["BTCUSDT"]
        proxy_url = "http://proxy.example.com:8080"
        
        with patch.dict('os.environ', {'https_proxy': proxy_url}):
            with patch('aiohttp.TCPConnector') as mock_connector:
                with patch('aiohttp.ClientSession') as mock_session:
                    with patch.object(manager, 'start_symbol_management') as mock_start_symbol:
                        mock_connector.return_value = Mock()
                        mock_session.return_value = Mock()
                        
                        result = await manager.start(symbols)
                        
                        # 验证启动成功
                        assert result is True
                        
                        # 验证代理设置
                        assert manager.proxy == proxy_url
    
    @pytest.mark.asyncio
    async def test_start_okx_mode(self, mock_config, mock_normalizer):
        """测试：启动OKX订单簿管理器"""
        mock_config.exchange = Exchange.OKX
        manager = OrderBookManager(mock_config, mock_normalizer)
        symbols = ["BTC-USDT", "ETH-USDT"]
        
        with patch.dict('os.environ', {}, clear=True):
            with patch('aiohttp.TCPConnector') as mock_connector:
                with patch('aiohttp.ClientSession') as mock_session:
                    with patch.object(manager, '_start_okx_management') as mock_start_okx:
                        mock_connector.return_value = Mock()
                        mock_session.return_value = Mock()
                        
                        result = await manager.start(symbols)
                        
                        # 验证启动成功
                        assert result is True
                        
                        # 验证OKX管理模式被调用
                        mock_start_okx.assert_called_once_with(symbols)
    
    @pytest.mark.asyncio
    async def test_start_exception_handling(self, manager):
        """测试：启动时异常处理"""
        symbols = ["BTCUSDT"]
        
        with patch('aiohttp.TCPConnector', side_effect=Exception("Connection error")):
            result = await manager.start(symbols)
            
            # 验证启动失败
            assert result is False
    
    @pytest.mark.asyncio
    async def test_stop_with_tasks(self, manager):
        """测试：停止订单簿管理器（有任务）"""
        # 创建真正的协程任务
        async def dummy_task():
            await asyncio.sleep(0.1)

        # 创建真正的asyncio任务
        task1 = asyncio.create_task(dummy_task())
        task2 = asyncio.create_task(dummy_task())
        task3 = asyncio.create_task(dummy_task())

        # 立即取消task2，模拟已完成的任务
        task2.cancel()
        try:
            await task2
        except asyncio.CancelledError:
            pass

        manager.snapshot_tasks = {'task1': task1}
        manager.update_tasks = {'task2': task2}
        manager.okx_snapshot_sync_tasks = {'task3': task3}

        # 模拟HTTP客户端
        mock_session = AsyncMock()
        manager.session = mock_session

        # 模拟OKX WebSocket客户端
        mock_okx_ws = AsyncMock()
        manager.okx_ws_client = mock_okx_ws

        await manager.stop()

        # 验证OKX WebSocket客户端被停止
        mock_okx_ws.stop.assert_called_once()

        # 验证HTTP客户端被关闭
        mock_session.close.assert_called_once()

        # 验证所有任务都被取消
        assert task1.cancelled() or task1.done()
        assert task2.done()  # 已经完成
        assert task3.cancelled() or task3.done()
    
    @pytest.mark.asyncio
    async def test_stop_without_tasks(self, manager):
        """测试：停止订单簿管理器（无任务）"""
        # 无任务和客户端
        manager.okx_ws_client = None
        manager.session = None
        
        with patch('asyncio.gather') as mock_gather:
            await manager.stop()
            
            # 验证gather没有被调用（因为没有任务）
            mock_gather.assert_not_called()


@pytest.mark.skipif(not HAS_ORDERBOOK_MODULES, reason="订单簿管理器模块不可用")
class TestOrderBookManagerSymbolManagement:
    """测试订单簿管理器交易对管理"""
    
    @pytest.fixture
    def mock_config(self):
        """创建模拟配置"""
        config = Mock(spec=ExchangeConfig)
        config.exchange = Exchange.BINANCE
        config.snapshot_interval = 60
        return config
    
    @pytest.fixture
    def mock_normalizer(self):
        """创建模拟数据标准化器"""
        return Mock(spec=DataNormalizer)
    
    @pytest.fixture
    def manager(self, mock_config, mock_normalizer):
        """创建测试用的订单簿管理器"""
        return OrderBookManager(mock_config, mock_normalizer)
    
    @pytest.mark.asyncio
    async def test_start_symbol_management(self, manager):
        """测试：启动单个交易对的订单簿管理"""
        symbol = "BTCUSDT"
        
        with patch('asyncio.create_task') as mock_create_task:
            mock_task = Mock()
            mock_create_task.return_value = mock_task
            
            await manager.start_symbol_management(symbol)
            
            # 验证状态被创建
            assert symbol in manager.orderbook_states
            state = manager.orderbook_states[symbol]
            assert isinstance(state, OrderBookState)
            assert state.symbol == symbol
            assert state.exchange == Exchange.BINANCE.value
            
            # 验证任务被创建和存储
            mock_create_task.assert_called_once()
            assert manager.snapshot_tasks[symbol] is mock_task


@pytest.mark.skipif(not HAS_ORDERBOOK_MODULES, reason="订单簿管理器模块不可用")
class TestOrderBookManagerOKXManagement:
    """测试订单簿管理器OKX管理功能"""

    @pytest.fixture
    def mock_config(self):
        """创建模拟配置"""
        config = Mock(spec=ExchangeConfig)
        config.exchange = Exchange.OKX
        config.snapshot_interval = 60
        return config

    @pytest.fixture
    def mock_normalizer(self):
        """创建模拟数据标准化器"""
        return Mock(spec=DataNormalizer)

    @pytest.fixture
    def manager(self, mock_config, mock_normalizer):
        """创建测试用的订单簿管理器"""
        return OrderBookManager(mock_config, mock_normalizer)

    @pytest.mark.asyncio
    async def test_start_okx_management(self, manager):
        """测试：启动OKX订单簿管理"""
        symbols = ["BTC-USDT", "ETH-USDT"]

        with patch.object(manager, '_initialize_okx_orderbook') as mock_init:
            with patch('asyncio.create_task') as mock_create_task:
                with patch('marketprism_collector.okx_websocket.OKXWebSocketClient') as mock_ws_client_class:
                    mock_ws_client = Mock()
                    mock_ws_client_class.return_value = mock_ws_client
                    mock_task = Mock()
                    mock_create_task.return_value = mock_task

                    await manager._start_okx_management(symbols)

                    # 验证所有交易对状态被初始化
                    for symbol in symbols:
                        assert symbol in manager.orderbook_states
                        state = manager.orderbook_states[symbol]
                        assert isinstance(state, OrderBookState)
                        assert state.symbol == symbol
                        assert state.exchange == Exchange.OKX.value

                    # 验证初始化被调用
                    assert mock_init.call_count == len(symbols)
                    mock_init.assert_any_call("BTC-USDT")
                    mock_init.assert_any_call("ETH-USDT")

                    # 验证WebSocket客户端被创建
                    mock_ws_client_class.assert_called_once_with(
                        symbols=symbols,
                        on_orderbook_update=manager._handle_okx_websocket_update
                    )
                    assert manager.okx_ws_client is mock_ws_client

                    # 验证任务被创建
                    assert mock_create_task.call_count == len(symbols) + 1  # WebSocket + 每个交易对的同步任务

    @pytest.mark.asyncio
    async def test_handle_okx_websocket_update_unmanaged_symbol(self, manager):
        """测试：处理未管理交易对的OKX WebSocket更新"""
        symbol = "UNKNOWN-USDT"
        update = Mock()

        # 不添加状态，模拟未管理的交易对
        await manager._handle_okx_websocket_update(symbol, update)

        # 应该没有异常，只是记录警告

    @pytest.mark.asyncio
    async def test_handle_okx_websocket_update_not_synced(self, manager):
        """测试：处理OKX WebSocket更新（未同步状态）"""
        symbol = "BTC-USDT"
        update = Mock()
        update.last_update_id = 12345

        # 创建未同步的状态
        manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange=Exchange.OKX.value,
            is_synced=False
        )

        await manager._handle_okx_websocket_update(symbol, update)

        # 验证更新被忽略（因为未同步）
        state = manager.orderbook_states[symbol]
        assert state.total_updates == 0

    @pytest.mark.asyncio
    async def test_handle_okx_websocket_update_synced(self, manager):
        """测试：处理OKX WebSocket更新（已同步状态）"""
        symbol = "BTC-USDT"
        update = Mock()
        update.last_update_id = 12345

        # 创建已同步的状态
        mock_orderbook = Mock()
        manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange=Exchange.OKX.value,
            is_synced=True,
            local_orderbook=mock_orderbook
        )

        with patch.object(manager, '_apply_okx_update') as mock_apply:
            mock_enhanced_orderbook = Mock()
            mock_apply.return_value = mock_enhanced_orderbook

            await manager._handle_okx_websocket_update(symbol, update)

            # 验证更新被应用
            mock_apply.assert_called_once_with(symbol, update)

            # 验证统计被更新
            state = manager.orderbook_states[symbol]
            assert state.total_updates == 1
            assert state.last_update_id == 12345
            assert manager.stats['updates_processed'] == 1

    @pytest.mark.asyncio
    async def test_handle_okx_websocket_update_exception(self, manager):
        """测试：处理OKX WebSocket更新异常"""
        symbol = "BTC-USDT"
        update = Mock()

        # 创建会导致异常的状态
        manager.orderbook_states[symbol] = None  # 这会导致异常

        # 应该捕获异常而不抛出
        await manager._handle_okx_websocket_update(symbol, update)

    @pytest.mark.asyncio
    async def test_apply_okx_update_no_local_book(self, manager):
        """测试：应用OKX更新但无本地订单簿"""
        symbol = "BTC-USDT"
        update = Mock()

        # 创建无本地订单簿的状态
        manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange=Exchange.OKX.value,
            local_orderbook=None
        )

        result = await manager._apply_okx_update(symbol, update)

        # 验证返回None
        assert result is None

    @pytest.mark.asyncio
    async def test_apply_okx_update_with_changes(self, manager):
        """测试：应用OKX更新并处理价位变化"""
        symbol = "BTC-USDT"

        # 创建模拟的本地订单簿
        local_bids = [
            PriceLevel(price=Decimal('50000'), quantity=Decimal('1.0')),
            PriceLevel(price=Decimal('49999'), quantity=Decimal('2.0'))
        ]
        local_asks = [
            PriceLevel(price=Decimal('50001'), quantity=Decimal('1.5')),
            PriceLevel(price=Decimal('50002'), quantity=Decimal('2.5'))
        ]

        local_orderbook = OrderBookSnapshot(
            symbol=symbol,
            exchange=Exchange.OKX.value,
            last_update_id=100,
            bids=local_bids,
            asks=local_asks,
            timestamp=datetime.now(timezone.utc)
        )

        # 创建状态
        manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange=Exchange.OKX.value,
            local_orderbook=local_orderbook
        )

        # 创建更新数据
        update_bids = [
            PriceLevel(price=Decimal('50000'), quantity=Decimal('0')),  # 删除
            PriceLevel(price=Decimal('49998'), quantity=Decimal('3.0'))  # 新增
        ]
        update_asks = [
            PriceLevel(price=Decimal('50001'), quantity=Decimal('2.0')),  # 更新
            PriceLevel(price=Decimal('50003'), quantity=Decimal('1.0'))   # 新增
        ]

        update = Mock()
        update.bids = update_bids
        update.asks = update_asks
        update.first_update_id = 101
        update.last_update_id = 102
        update.prev_update_id = 100
        update.timestamp = datetime.now(timezone.utc)

        result = await manager._apply_okx_update(symbol, update)

        # 验证返回增强订单簿
        assert result is not None
        assert isinstance(result, EnhancedOrderBook)
        assert result.symbol_name == symbol
        assert result.last_update_id == 102

        # 验证本地订单簿被更新
        state = manager.orderbook_states[symbol]
        assert state.local_orderbook.last_update_id == 102

        # 验证买单变化：删除50000，添加49998
        bid_prices = [level.price for level in state.local_orderbook.bids]
        assert Decimal('50000') not in bid_prices
        assert Decimal('49998') in bid_prices

        # 验证卖单变化：更新50001，添加50003
        ask_prices = [level.price for level in state.local_orderbook.asks]
        assert Decimal('50001') in ask_prices
        assert Decimal('50003') in ask_prices

    @pytest.mark.asyncio
    async def test_apply_okx_update_exception(self, manager):
        """测试：应用OKX更新异常处理"""
        symbol = "BTC-USDT"
        update = Mock()

        # 创建会导致异常的状态（无效的订单簿）
        manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange=Exchange.OKX.value,
            local_orderbook="invalid"  # 无效类型
        )

        result = await manager._apply_okx_update(symbol, update)

        # 验证异常被捕获，返回None
        assert result is None


@pytest.mark.skipif(not HAS_ORDERBOOK_MODULES, reason="订单簿管理器模块不可用")
class TestOrderBookManagerSnapshotSync:
    """测试订单簿管理器快照同步功能"""

    @pytest.fixture
    def mock_config(self):
        """创建模拟配置"""
        config = Mock(spec=ExchangeConfig)
        config.exchange = Exchange.OKX
        config.snapshot_interval = 60
        return config

    @pytest.fixture
    def mock_normalizer(self):
        """创建模拟数据标准化器"""
        return Mock(spec=DataNormalizer)

    @pytest.fixture
    def manager(self, mock_config, mock_normalizer):
        """创建测试用的订单簿管理器"""
        return OrderBookManager(mock_config, mock_normalizer)

    @pytest.mark.asyncio
    async def test_okx_snapshot_sync_loop_cancelled(self, manager):
        """测试：OKX快照同步循环被取消"""
        symbol = "BTC-USDT"

        with patch('asyncio.sleep', side_effect=asyncio.CancelledError):
            # 应该捕获CancelledError并退出循环
            await manager._okx_snapshot_sync_loop(symbol)

    @pytest.mark.asyncio
    async def test_okx_snapshot_sync_loop_exception(self, manager):
        """测试：OKX快照同步循环异常处理"""
        symbol = "BTC-USDT"

        call_count = 0
        async def mock_sleep(duration):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # 第一次调用模拟正常间隔
                pass
            elif call_count == 2:
                # 第二次调用模拟错误后的短暂等待
                pass
            else:
                # 第三次调用时取消，避免无限循环
                raise asyncio.CancelledError

        with patch('asyncio.sleep', side_effect=mock_sleep):
            with patch.object(manager, '_sync_okx_snapshot', side_effect=Exception("Sync error")):
                await manager._okx_snapshot_sync_loop(symbol)

                # 验证至少尝试了一次同步
                assert call_count >= 2  # 正常间隔 + 错误后等待

    @pytest.mark.asyncio
    async def test_sync_okx_snapshot_no_snapshot(self, manager):
        """测试：同步OKX快照但获取失败"""
        symbol = "BTC-USDT"

        with patch.object(manager, '_fetch_okx_snapshot', return_value=None):
            # 应该直接返回，不做任何操作
            await manager._sync_okx_snapshot(symbol)

    @pytest.mark.asyncio
    async def test_sync_okx_snapshot_newer_snapshot(self, manager):
        """测试：同步OKX快照（快照比WebSocket状态新）"""
        symbol = "BTC-USDT"

        # 创建状态
        manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange=Exchange.OKX.value
        )

        # 创建模拟快照
        snapshot_time = datetime.now(timezone.utc)
        mock_snapshot = OrderBookSnapshot(
            symbol=symbol,
            exchange=Exchange.OKX.value,
            last_update_id=200,
            bids=[],
            asks=[],
            timestamp=snapshot_time
        )

        # 模拟WebSocket客户端状态
        mock_okx_ws = Mock()
        mock_okx_ws.orderbook_states = {
            symbol: {
                'last_seq_id': 150,
                'last_timestamp': int((snapshot_time - timedelta(seconds=10)).timestamp() * 1000)
            }
        }
        manager.okx_ws_client = mock_okx_ws

        with patch.object(manager, '_fetch_okx_snapshot', return_value=mock_snapshot):
            await manager._sync_okx_snapshot(symbol)

            # 验证本地订单簿被更新
            state = manager.orderbook_states[symbol]
            assert state.local_orderbook is mock_snapshot
            assert state.last_update_id == 200
            assert state.last_snapshot_time == snapshot_time

    @pytest.mark.asyncio
    async def test_sync_okx_snapshot_older_snapshot(self, manager):
        """测试：同步OKX快照（快照比WebSocket状态旧）"""
        symbol = "BTC-USDT"

        # 创建状态
        manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange=Exchange.OKX.value
        )

        # 创建模拟快照
        snapshot_time = datetime.now(timezone.utc)
        mock_snapshot = OrderBookSnapshot(
            symbol=symbol,
            exchange=Exchange.OKX.value,
            last_update_id=100,
            bids=[],
            asks=[],
            timestamp=snapshot_time
        )

        # 模拟WebSocket客户端状态（更新的时间戳）
        mock_okx_ws = Mock()
        mock_okx_ws.orderbook_states = {
            symbol: {
                'last_seq_id': 150,
                'last_timestamp': int((snapshot_time + timedelta(seconds=10)).timestamp() * 1000)
            }
        }
        manager.okx_ws_client = mock_okx_ws

        with patch.object(manager, '_fetch_okx_snapshot', return_value=mock_snapshot):
            await manager._sync_okx_snapshot(symbol)

            # 验证本地订单簿没有被更新
            state = manager.orderbook_states[symbol]
            assert state.local_orderbook is None

    @pytest.mark.asyncio
    async def test_sync_okx_snapshot_exception(self, manager):
        """测试：同步OKX快照异常处理"""
        symbol = "BTC-USDT"

        with patch.object(manager, '_fetch_okx_snapshot', side_effect=Exception("Fetch error")):
            # 应该捕获异常而不抛出
            await manager._sync_okx_snapshot(symbol)

    @pytest.mark.asyncio
    async def test_initialize_okx_orderbook_success(self, manager):
        """测试：成功初始化OKX订单簿"""
        symbol = "BTC-USDT"

        # 创建状态
        manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange=Exchange.OKX.value
        )

        # 创建模拟快照
        mock_snapshot = OrderBookSnapshot(
            symbol=symbol,
            exchange=Exchange.OKX.value,
            last_update_id=100,
            bids=[PriceLevel(price=Decimal('50000'), quantity=Decimal('1.0'))],
            asks=[PriceLevel(price=Decimal('50001'), quantity=Decimal('1.0'))],
            timestamp=datetime.now(timezone.utc)
        )

        with patch.object(manager, '_fetch_okx_snapshot', return_value=mock_snapshot):
            await manager._initialize_okx_orderbook(symbol)

            # 验证状态被正确设置
            state = manager.orderbook_states[symbol]
            assert state.local_orderbook is mock_snapshot
            assert state.last_update_id == 100
            assert state.is_synced is True

    @pytest.mark.asyncio
    async def test_initialize_okx_orderbook_failure(self, manager):
        """测试：初始化OKX订单簿失败"""
        symbol = "BTC-USDT"

        # 创建状态
        manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange=Exchange.OKX.value
        )

        with patch.object(manager, '_fetch_okx_snapshot', return_value=None):
            await manager._initialize_okx_orderbook(symbol)

            # 验证状态保持未同步
            state = manager.orderbook_states[symbol]
            assert state.local_orderbook is None
            assert state.is_synced is False

    @pytest.mark.asyncio
    async def test_initialize_okx_orderbook_exception(self, manager):
        """测试：初始化OKX订单簿异常处理"""
        symbol = "BTC-USDT"

        # 创建状态
        manager.orderbook_states[symbol] = OrderBookState(
            symbol=symbol,
            exchange=Exchange.OKX.value
        )

        with patch.object(manager, '_fetch_okx_snapshot', side_effect=Exception("Init error")):
            # 应该捕获异常而不抛出
            await manager._initialize_okx_orderbook(symbol)
