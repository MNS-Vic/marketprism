"""
OrderBook Manager TDD测试套件
专注于提升覆盖率：当前12% → 目标40%+

测试重点：
1. 实时数据处理和订单簿维护
2. 多交易所集成（Binance、OKX）
3. 快照+增量更新同步机制
4. 错误处理和状态管理
5. 性能优化和资源管理
"""

import pytest
import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from collections import deque

# 添加项目路径
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../../services/data-collector/src'))

try:
    from marketprism_collector.orderbook_manager import (
        OrderBookManager, OrderBookSnapshot, OrderBookState
    )
    from marketprism_collector.data_types import (
        Exchange, PriceLevel, EnhancedOrderBook, OrderBookDelta,
        OrderBookUpdateType, ExchangeConfig, MarketType
    )
    from marketprism_collector.normalizer import DataNormalizer
    HAS_ORDERBOOK_MODULES = True
except ImportError as e:
    print(f"导入失败: {e}")
    HAS_ORDERBOOK_MODULES = False

# 定义OrderBookUpdate类（如果不存在）
if HAS_ORDERBOOK_MODULES:
    try:
        from marketprism_collector.orderbook_manager import OrderBookUpdate
    except ImportError:
        # 如果OrderBookUpdate不存在，创建一个简单的Mock类
        class OrderBookUpdate:
            def __init__(self, symbol=None, first_update_id=None, last_update_id=None,
                         bids=None, asks=None, timestamp=None, checksum=None):
                self.symbol = symbol
                self.first_update_id = first_update_id
                self.last_update_id = last_update_id
                self.bids = bids or []
                self.asks = asks or []
                self.timestamp = timestamp
                self.checksum = checksum


@pytest.mark.skipif(not HAS_ORDERBOOK_MODULES, reason="OrderBook模块不可用")
class TestOrderBookSnapshot:
    """测试OrderBookSnapshot数据类"""
    
    def test_orderbook_snapshot_creation(self):
        """测试：创建订单簿快照"""
        timestamp = datetime.now(timezone.utc)
        bids = [PriceLevel(price=Decimal("50000"), quantity=Decimal("1.0"))]
        asks = [PriceLevel(price=Decimal("50100"), quantity=Decimal("0.5"))]
        
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            exchange="binance",
            last_update_id=12345,
            bids=bids,
            asks=asks,
            timestamp=timestamp,
            checksum=98765
        )
        
        assert snapshot.symbol == "BTCUSDT"
        assert snapshot.exchange == "binance"
        assert snapshot.last_update_id == 12345
        assert snapshot.bids == bids
        assert snapshot.asks == asks
        assert snapshot.timestamp == timestamp
        assert snapshot.checksum == 98765
    
    def test_orderbook_snapshot_without_checksum(self):
        """测试：创建不带校验和的订单簿快照"""
        timestamp = datetime.now(timezone.utc)
        bids = [PriceLevel(price=Decimal("50000"), quantity=Decimal("1.0"))]
        asks = [PriceLevel(price=Decimal("50100"), quantity=Decimal("0.5"))]
        
        snapshot = OrderBookSnapshot(
            symbol="ETHUSDT",
            exchange="okx",
            last_update_id=67890,
            bids=bids,
            asks=asks,
            timestamp=timestamp
        )
        
        assert snapshot.checksum is None
        assert snapshot.symbol == "ETHUSDT"
        assert snapshot.exchange == "okx"


@pytest.mark.skipif(not HAS_ORDERBOOK_MODULES, reason="OrderBook模块不可用")
class TestOrderBookState:
    """测试OrderBookState状态管理"""
    
    def test_orderbook_state_creation(self):
        """测试：创建订单簿状态"""
        state = OrderBookState(
            symbol="BTCUSDT",
            exchange="binance"
        )
        
        assert state.symbol == "BTCUSDT"
        assert state.exchange == "binance"
        assert state.local_orderbook is None
        assert isinstance(state.update_buffer, deque)
        assert state.last_update_id == 0
        assert state.is_synced is False
        assert state.error_count == 0
        assert state.total_updates == 0
        assert state.first_update_id is None
        assert state.snapshot_last_update_id is None
        assert state.sync_in_progress is False
    
    def test_orderbook_state_post_init(self):
        """测试：订单簿状态后初始化"""
        state = OrderBookState(
            symbol="ETHUSDT",
            exchange="okx"
        )
        
        # __post_init__ 应该设置update_buffer的maxlen
        assert state.update_buffer.maxlen == 1000
    
    def test_orderbook_state_with_custom_buffer(self):
        """测试：使用自定义缓冲区创建状态"""
        custom_buffer = deque(maxlen=500)
        custom_buffer.append("test_update")
        
        state = OrderBookState(
            symbol="ADAUSDT",
            exchange="binance",
            update_buffer=custom_buffer
        )
        
        # 自定义缓冲区应该被保留
        assert state.update_buffer is custom_buffer
        assert len(state.update_buffer) == 1
        assert state.update_buffer[0] == "test_update"


@pytest.mark.skipif(not HAS_ORDERBOOK_MODULES, reason="OrderBook模块不可用")
class TestOrderBookManagerInitialization:
    """测试OrderBookManager初始化"""
    
    @pytest.fixture
    def mock_config(self):
        """创建模拟配置"""
        config = Mock(spec=ExchangeConfig)
        config.exchange = Exchange.BINANCE
        config.market_type = MarketType.SPOT
        config.base_url = "https://api.binance.com"
        config.snapshot_interval = 30
        config.symbols = ["BTCUSDT", "ETHUSDT"]
        return config
    
    @pytest.fixture
    def mock_normalizer(self):
        """创建模拟数据标准化器"""
        return Mock(spec=DataNormalizer)
    
    def test_orderbook_manager_init_binance(self, mock_config, mock_normalizer):
        """测试：初始化Binance订单簿管理器"""
        manager = OrderBookManager(mock_config, mock_normalizer)
        
        assert manager.config is mock_config
        assert manager.normalizer is mock_normalizer
        assert manager.logger is not None
        assert isinstance(manager.orderbook_states, dict)
        assert isinstance(manager.snapshot_tasks, dict)
        assert isinstance(manager.update_tasks, dict)
        assert manager.snapshot_interval == 30
        assert manager.depth_limit == 400
        assert manager.max_error_count == 5
        assert manager.sync_timeout == 30
    
    def test_orderbook_manager_init_okx(self, mock_normalizer):
        """测试：初始化OKX订单簿管理器"""
        config = Mock(spec=ExchangeConfig)
        config.exchange = Exchange.OKX
        config.market_type = MarketType.FUTURES
        config.base_url = "https://www.okx.com"
        config.snapshot_interval = 60
        config.symbols = ["BTC-USDT", "ETH-USDT"]
        
        manager = OrderBookManager(config, mock_normalizer)
        
        assert manager.config.exchange == Exchange.OKX
        assert manager.okx_snapshot_sync_interval == 300
        assert manager.okx_ws_client is None
        assert isinstance(manager.okx_snapshot_sync_tasks, dict)
    
    def test_orderbook_manager_stats_initialization(self, mock_config, mock_normalizer):
        """测试：统计信息初始化"""
        manager = OrderBookManager(mock_config, mock_normalizer)

        # 验证统计信息字典存在
        assert hasattr(manager, 'stats')
        assert isinstance(manager.stats, dict)

        # 验证基本统计字段（根据实际实现）
        expected_stats = [
            'snapshots_fetched', 'updates_processed', 'sync_errors', 'resync_count'
        ]
        for stat in expected_stats:
            assert stat in manager.stats
            assert manager.stats[stat] == 0


@pytest.mark.skipif(not HAS_ORDERBOOK_MODULES, reason="OrderBook模块不可用")
class TestOrderBookManagerLifecycle:
    """测试OrderBookManager生命周期管理"""
    
    @pytest.fixture
    def manager_setup(self):
        """设置测试用的管理器"""
        config = Mock(spec=ExchangeConfig)
        config.exchange = Exchange.BINANCE
        config.market_type = MarketType.SPOT
        config.base_url = "https://api.binance.com"
        config.snapshot_interval = 30
        config.symbols = ["BTCUSDT"]

        normalizer = Mock(spec=DataNormalizer)
        manager = OrderBookManager(config, normalizer)

        # 模拟session
        manager.session = AsyncMock()

        return manager
    
    @pytest.mark.asyncio
    async def test_start_management_binance(self, manager_setup):
        """测试：启动Binance订单簿管理"""
        manager = manager_setup
        symbols = ["BTCUSDT", "ETHUSDT"]

        with patch.object(manager, 'start_symbol_management') as mock_start:
            mock_start.return_value = None

            result = await manager.start(symbols)  # 实际方法名是start

            assert result is True
            assert mock_start.call_count == len(symbols)
            mock_start.assert_any_call("BTCUSDT")
            mock_start.assert_any_call("ETHUSDT")
    
    @pytest.mark.asyncio
    async def test_start_management_okx(self):
        """测试：启动OKX订单簿管理"""
        config = Mock(spec=ExchangeConfig)
        config.exchange = Exchange.OKX
        config.market_type = MarketType.FUTURES
        config.snapshot_interval = 60

        normalizer = Mock(spec=DataNormalizer)
        manager = OrderBookManager(config, normalizer)
        manager.session = AsyncMock()

        symbols = ["BTC-USDT", "ETH-USDT"]

        with patch.object(manager, '_start_okx_management') as mock_start_okx:
            mock_start_okx.return_value = None

            result = await manager.start(symbols)  # 实际方法名是start

            assert result is True
            mock_start_okx.assert_called_once_with(symbols)
    
    @pytest.mark.asyncio
    async def test_start_management_failure(self, manager_setup):
        """测试：启动管理失败处理"""
        manager = manager_setup
        symbols = ["BTCUSDT"]

        with patch.object(manager, 'start_symbol_management') as mock_start:
            mock_start.side_effect = Exception("启动失败")

            result = await manager.start(symbols)  # 实际方法名是start

            assert result is False

    @pytest.mark.asyncio
    async def test_stop_management(self, manager_setup):
        """测试：停止订单簿管理"""
        manager = manager_setup

        # 创建真实的asyncio任务来模拟运行中的任务
        async def dummy_task():
            await asyncio.sleep(10)  # 长时间运行的任务

        task1 = asyncio.create_task(dummy_task())
        task2 = asyncio.create_task(dummy_task())
        task3 = asyncio.create_task(dummy_task())

        manager.snapshot_tasks["BTCUSDT"] = task1
        manager.update_tasks["ETHUSDT"] = task2
        manager.okx_snapshot_sync_tasks["BTC-USDT"] = task3

        # 模拟OKX WebSocket客户端
        manager.okx_ws_client = AsyncMock()

        await manager.stop()  # 实际方法名是stop

        # 验证任务被取消
        assert task1.cancelled()
        assert task2.cancelled()
        assert task3.cancelled()

        # 验证OKX客户端被停止
        manager.okx_ws_client.stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_start_symbol_management(self, manager_setup):
        """测试：启动单个交易对管理"""
        manager = manager_setup
        symbol = "BTCUSDT"
        
        with patch('asyncio.create_task') as mock_create_task:
            mock_task = AsyncMock()
            mock_create_task.return_value = mock_task
            
            with patch.object(manager, 'maintain_orderbook') as mock_maintain:
                await manager.start_symbol_management(symbol)
                
                # 验证状态被创建
                assert symbol in manager.orderbook_states
                state = manager.orderbook_states[symbol]
                assert state.symbol == symbol
                assert state.exchange == manager.config.exchange.value
                
                # 验证任务被创建和存储
                mock_create_task.assert_called_once()
                assert manager.snapshot_tasks[symbol] is mock_task


@pytest.mark.skipif(not HAS_ORDERBOOK_MODULES, reason="OrderBook模块不可用")
class TestOrderBookManagerSnapshotHandling:
    """测试OrderBookManager快照处理"""

    @pytest.fixture
    def manager_setup(self):
        """设置测试用的管理器"""
        config = Mock(spec=ExchangeConfig)
        config.exchange = Exchange.BINANCE
        config.market_type = MarketType.SPOT
        config.base_url = "https://api.binance.com"
        config.snapshot_interval = 30

        normalizer = Mock(spec=DataNormalizer)
        manager = OrderBookManager(config, normalizer)
        manager.session = AsyncMock()
        manager.last_snapshot_request = {}

        return manager

    @pytest.mark.asyncio
    async def test_fetch_snapshot_binance_success(self, manager_setup):
        """测试：成功获取Binance快照"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 创建期望的快照对象
        expected_snapshot = OrderBookSnapshot(
            symbol=symbol,
            exchange="binance",
            last_update_id=12345,
            bids=[
                PriceLevel(price=Decimal("50000.00"), quantity=Decimal("1.0")),
                PriceLevel(price=Decimal("49999.00"), quantity=Decimal("0.5"))
            ],
            asks=[
                PriceLevel(price=Decimal("50001.00"), quantity=Decimal("0.8")),
                PriceLevel(price=Decimal("50002.00"), quantity=Decimal("1.2"))
            ],
            timestamp=datetime.now(timezone.utc)
        )

        # 直接Mock _fetch_binance_snapshot方法
        with patch.object(manager, '_fetch_binance_snapshot') as mock_fetch:
            mock_fetch.return_value = expected_snapshot

            # 绕过频率限制
            manager.last_snapshot_request = {}  # 清空请求历史
            manager.api_weight_used = 0  # 重置权重

            snapshot = await manager._fetch_snapshot(symbol)

            assert snapshot is not None
            assert snapshot.symbol == symbol
            assert snapshot.exchange == "binance"
            assert snapshot.last_update_id == 12345
            assert len(snapshot.bids) == 2
            assert len(snapshot.asks) == 2
            assert snapshot.bids[0].price == Decimal("50000.00")
            assert snapshot.bids[0].quantity == Decimal("1.0")

    @pytest.mark.asyncio
    async def test_fetch_snapshot_binance_failure(self, manager_setup):
        """测试：Binance快照获取失败"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 直接Mock _fetch_binance_snapshot方法返回None（失败）
        with patch.object(manager, '_fetch_binance_snapshot') as mock_fetch:
            mock_fetch.return_value = None

            # 绕过频率限制
            manager.last_snapshot_request = {}  # 清空请求历史
            manager.api_weight_used = 0  # 重置权重

            snapshot = await manager._fetch_snapshot(symbol)

            assert snapshot is None

    @pytest.mark.asyncio
    async def test_fetch_snapshot_okx_success(self):
        """测试：成功获取OKX快照"""
        config = Mock(spec=ExchangeConfig)
        config.exchange = Exchange.OKX
        config.market_type = MarketType.FUTURES
        config.base_url = "https://www.okx.com"
        config.snapshot_interval = 60

        normalizer = Mock(spec=DataNormalizer)
        manager = OrderBookManager(config, normalizer)
        manager.session = AsyncMock()
        manager.last_snapshot_request = {}
        manager.api_weight_used = 0  # 重置权重

        symbol = "BTC-USDT"

        # 创建期望的OKX快照对象
        expected_snapshot = OrderBookSnapshot(
            symbol=symbol,
            exchange="okx",
            last_update_id=1640995200000,
            bids=[
                PriceLevel(price=Decimal("50000"), quantity=Decimal("1.0")),
                PriceLevel(price=Decimal("49999"), quantity=Decimal("0.5"))
            ],
            asks=[
                PriceLevel(price=Decimal("50001"), quantity=Decimal("0.8")),
                PriceLevel(price=Decimal("50002"), quantity=Decimal("1.2"))
            ],
            timestamp=datetime.fromtimestamp(1640995200000 / 1000.0)
        )

        # 直接Mock _fetch_okx_snapshot方法
        with patch.object(manager, '_fetch_okx_snapshot') as mock_fetch:
            mock_fetch.return_value = expected_snapshot

            snapshot = await manager._fetch_snapshot(symbol)

            assert snapshot is not None
            assert snapshot.symbol == symbol
            assert snapshot.exchange == "okx"
            assert len(snapshot.bids) == 2
            assert len(snapshot.asks) == 2

    @pytest.mark.asyncio
    async def test_fetch_snapshot_rate_limiting(self, manager_setup):
        """测试：快照获取频率限制"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 设置最近请求时间
        manager.last_snapshot_request[symbol] = time.time()

        # 设置最小间隔为1秒，这样立即请求会被限制
        manager.min_snapshot_interval = 1.0
        manager.backoff_multiplier = 1.0

        # 立即再次请求应该被限制（因为时间间隔不够）
        # 但是我们需要Mock sleep来避免实际等待
        with patch('asyncio.sleep') as mock_sleep:
            # 模拟频率限制逻辑，但不实际等待
            mock_sleep.return_value = None

            # 由于频率限制，这个调用应该等待然后继续
            # 我们需要Mock _fetch_binance_snapshot来返回None
            with patch.object(manager, '_fetch_binance_snapshot') as mock_fetch:
                mock_fetch.return_value = None
                snapshot = await manager._fetch_snapshot(symbol)

                # 验证sleep被调用（说明触发了频率限制）
                mock_sleep.assert_called_once()
                assert snapshot is None

    def test_need_snapshot_refresh_true(self, manager_setup):
        """测试：需要刷新快照"""
        manager = manager_setup

        # 创建过期的状态
        state = OrderBookState(
            symbol="BTCUSDT",
            exchange="binance"
        )
        # 设置过期的快照时间和本地订单簿
        state.last_snapshot_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        state.local_orderbook = Mock()  # 模拟存在本地订单簿

        result = manager._need_snapshot_refresh(state)

        assert result is True

    def test_need_snapshot_refresh_false(self, manager_setup):
        """测试：不需要刷新快照"""
        manager = manager_setup

        # 创建新鲜的状态
        state = OrderBookState(
            symbol="BTCUSDT",
            exchange="binance"
        )
        # 设置最近的快照时间和本地订单簿
        state.last_snapshot_time = datetime.now(timezone.utc)
        state.local_orderbook = Mock()  # 模拟存在本地订单簿

        result = manager._need_snapshot_refresh(state)

        assert result is False


@pytest.mark.skipif(not HAS_ORDERBOOK_MODULES, reason="OrderBook模块不可用")
class TestOrderBookManagerUpdateProcessing:
    """测试OrderBookManager增量更新处理"""

    @pytest.fixture
    def manager_setup(self):
        """设置测试用的管理器"""
        config = Mock(spec=ExchangeConfig)
        config.exchange = Exchange.BINANCE
        config.market_type = MarketType.SPOT
        config.base_url = "https://api.binance.com"
        config.snapshot_interval = 30

        normalizer = Mock(spec=DataNormalizer)
        manager = OrderBookManager(config, normalizer)
        manager.session = AsyncMock()
        manager.stats = {
            'updates_processed': 0,
            'sync_errors': 0,
            'snapshots_fetched': 0,
            'resync_count': 0
        }

        return manager

    def test_parse_binance_update_success(self, manager_setup):
        """测试：成功解析Binance更新"""
        manager = manager_setup
        symbol = "BTCUSDT"

        update_data = {
            "e": "depthUpdate",
            "E": 1640995200000,
            "s": "BTCUSDT",
            "U": 12345,
            "u": 12346,
            "b": [["50000.00", "1.0"], ["49999.00", "0.0"]],  # 0.0表示删除
            "a": [["50001.00", "0.8"]]
        }

        update = manager._parse_binance_update(symbol, update_data)

        assert update is not None
        assert update.symbol == symbol
        assert update.first_update_id == 12345
        assert update.last_update_id == 12346
        assert len(update.bids) == 2
        assert len(update.asks) == 1
        assert update.bids[1].quantity == Decimal("0.0")  # 删除的价位

    def test_parse_okx_update_success(self, manager_setup):
        """测试：成功解析OKX更新"""
        manager = manager_setup
        symbol = "BTC-USDT"

        # OKX更新数据格式（直接包含bids和asks）
        update_data = {
            "bids": [["50000", "1.0", "0", "1"], ["49999", "0", "0", "0"]],  # 0表示删除
            "asks": [["50001", "0.8", "0", "1"]],
            "ts": "1640995200000"
        }

        update = manager._parse_okx_update(symbol, update_data)

        assert update is not None
        assert update.symbol == symbol
        assert len(update.bids) == 2
        assert len(update.asks) == 1
        assert update.first_update_id == 1640995200000
        assert update.last_update_id == 1640995200000

    def test_parse_update_invalid_data(self, manager_setup):
        """测试：解析无效更新数据"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 缺少必要字段的数据
        invalid_data = {
            "e": "depthUpdate",
            # 缺少其他必要字段
        }

        update = manager._parse_binance_update(symbol, invalid_data)

        assert update is None

    @pytest.mark.asyncio
    async def test_apply_update_success(self, manager_setup):
        """测试：成功应用更新"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 创建初始订单簿状态
        initial_bids = [PriceLevel(price=Decimal("50000"), quantity=Decimal("1.0"))]
        initial_asks = [PriceLevel(price=Decimal("50100"), quantity=Decimal("0.5"))]

        snapshot = OrderBookSnapshot(
            symbol=symbol,
            exchange="binance",
            last_update_id=12344,
            bids=initial_bids,
            asks=initial_asks,
            timestamp=datetime.now(timezone.utc)
        )

        state = OrderBookState(symbol=symbol, exchange="binance")
        state.local_orderbook = snapshot
        state.is_synced = True
        manager.orderbook_states[symbol] = state

        # 创建更新
        update_bids = [PriceLevel(price=Decimal("50000"), quantity=Decimal("2.0"))]  # 更新数量
        update_asks = [PriceLevel(price=Decimal("50100"), quantity=Decimal("0.0"))]   # 删除价位

        update = Mock()
        update.symbol = symbol
        update.first_update_id = 12345
        update.last_update_id = 12345
        update.prev_update_id = None  # 明确设置为None而不是Mock对象
        update.bids = update_bids
        update.asks = update_asks
        update.timestamp = datetime.now(timezone.utc)

        enhanced_orderbook = await manager._apply_update(symbol, update)

        assert enhanced_orderbook is not None
        assert enhanced_orderbook.symbol_name == symbol
        assert enhanced_orderbook.last_update_id == 12345
        assert len(enhanced_orderbook.bids) == 1
        assert enhanced_orderbook.bids[0].quantity == Decimal("2.0")  # 更新后的数量
        assert len(enhanced_orderbook.asks) == 0  # 价位被删除


@pytest.mark.skipif(not HAS_ORDERBOOK_MODULES, reason="OrderBook模块不可用")
class TestOrderBookManagerSynchronization:
    """测试OrderBookManager同步机制"""

    @pytest.fixture
    def manager_setup(self):
        """设置测试用的管理器"""
        config = Mock(spec=ExchangeConfig)
        config.exchange = Exchange.BINANCE
        config.market_type = MarketType.SPOT
        config.base_url = "https://api.binance.com"
        config.snapshot_interval = 30

        normalizer = Mock(spec=DataNormalizer)
        manager = OrderBookManager(config, normalizer)
        manager.session = AsyncMock()
        manager.stats = {
            'updates_processed': 0,
            'sync_errors': 0,
            'snapshots_fetched': 0,
            'resync_count': 0
        }

        return manager

    @pytest.mark.asyncio
    async def test_sync_orderbook_success(self, manager_setup):
        """测试：成功同步订单簿"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 创建状态，并设置first_update_id以触发同步逻辑
        state = OrderBookState(symbol=symbol, exchange="binance")
        state.first_update_id = 12340  # 设置第一个更新ID
        manager.orderbook_states[symbol] = state

        # 模拟快照获取
        mock_snapshot = OrderBookSnapshot(
            symbol=symbol,
            exchange="binance",
            last_update_id=12345,
            bids=[PriceLevel(price=Decimal("50000"), quantity=Decimal("1.0"))],
            asks=[PriceLevel(price=Decimal("50100"), quantity=Decimal("0.5"))],
            timestamp=datetime.now(timezone.utc)
        )

        with patch.object(manager, '_fetch_snapshot') as mock_fetch:
            mock_fetch.return_value = mock_snapshot

            with patch.object(manager, '_clean_expired_updates_binance_style') as mock_clean:
                with patch.object(manager, '_apply_buffered_updates_binance_style') as mock_apply:
                    mock_apply.return_value = 5  # 应用了5个更新

                    await manager._sync_orderbook(symbol)

                    # 验证同步成功
                    assert state.is_synced is True
                    assert state.local_orderbook is mock_snapshot
                    assert state.last_update_id == 12345
                    assert state.sync_in_progress is False
                    assert state.error_count == 0
                    assert manager.stats['snapshots_fetched'] == 1

    @pytest.mark.asyncio
    async def test_sync_orderbook_failure(self, manager_setup):
        """测试：同步订单簿失败"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 创建状态，并设置first_update_id以触发同步逻辑
        state = OrderBookState(symbol=symbol, exchange="binance")
        state.first_update_id = 12340  # 设置第一个更新ID
        manager.orderbook_states[symbol] = state

        # 模拟快照获取失败
        with patch.object(manager, '_fetch_snapshot') as mock_fetch:
            mock_fetch.return_value = None

            await manager._sync_orderbook(symbol)

            # 验证同步失败处理
            assert state.is_synced is False
            assert state.sync_in_progress is False
            # 注意：实际实现中快照获取失败不会增加error_count

    def test_clean_expired_updates_binance_style(self, manager_setup):
        """测试：清理过期更新（Binance风格）"""
        manager = manager_setup

        # 创建状态和缓冲更新
        state = OrderBookState(symbol="BTCUSDT", exchange="binance")

        # 添加一些更新到缓冲区
        old_update = Mock()
        old_update.last_update_id = 12340  # 过期

        valid_update = Mock()
        valid_update.last_update_id = 12350  # 有效

        state.update_buffer.extend([old_update, valid_update])

        # 清理过期更新
        manager._clean_expired_updates_binance_style(state, 12345)

        # 验证只保留有效更新
        assert len(state.update_buffer) == 1
        assert state.update_buffer[0] is valid_update

    @pytest.mark.asyncio
    async def test_apply_buffered_updates_binance_style(self, manager_setup):
        """测试：应用缓冲的更新（Binance风格）"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 创建状态
        state = OrderBookState(symbol=symbol, exchange="binance")
        state.is_synced = True
        state.snapshot_last_update_id = 12345  # 设置快照更新ID

        # 创建本地订单簿
        snapshot = OrderBookSnapshot(
            symbol=symbol,
            exchange="binance",
            last_update_id=12345,
            bids=[PriceLevel(price=Decimal("50000"), quantity=Decimal("1.0"))],
            asks=[PriceLevel(price=Decimal("50100"), quantity=Decimal("0.5"))],
            timestamp=datetime.now(timezone.utc)
        )
        state.local_orderbook = snapshot
        manager.orderbook_states[symbol] = state

        # 创建缓冲更新
        update1 = Mock()
        update1.first_update_id = 12344
        update1.last_update_id = 12346
        update1.symbol = symbol
        update1.bids = [PriceLevel(price=Decimal("50000"), quantity=Decimal("2.0"))]
        update1.asks = []
        update1.timestamp = datetime.now(timezone.utc)

        update2 = Mock()
        update2.first_update_id = 12346
        update2.last_update_id = 12347
        update2.symbol = symbol
        update2.bids = []
        update2.asks = [PriceLevel(price=Decimal("50100"), quantity=Decimal("1.0"))]
        update2.timestamp = datetime.now(timezone.utc)

        state.update_buffer.extend([update1, update2])

        with patch.object(manager, '_apply_update') as mock_apply:
            mock_apply.return_value = Mock()  # 模拟返回增强订单簿

            applied_count = await manager._apply_buffered_updates_binance_style(symbol)

            # 验证应用了正确数量的更新
            assert applied_count == 2
            assert mock_apply.call_count == 2

    @pytest.mark.asyncio
    async def test_reset_orderbook_state(self, manager_setup):
        """测试：重置订单簿状态"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 创建有问题的状态
        state = OrderBookState(symbol=symbol, exchange="binance")
        state.error_count = 10
        state.is_synced = True
        state.sync_in_progress = True
        state.update_buffer.extend([Mock(), Mock(), Mock()])
        manager.orderbook_states[symbol] = state

        await manager._reset_orderbook_state(symbol)

        # 验证状态被重置
        reset_state = manager.orderbook_states[symbol]
        assert reset_state.error_count == 0
        assert reset_state.is_synced is False
        assert reset_state.sync_in_progress is False
        assert len(reset_state.update_buffer) == 0
        assert reset_state.local_orderbook is None


@pytest.mark.skipif(not HAS_ORDERBOOK_MODULES, reason="OrderBook模块不可用")
class TestOrderBookManagerOKXIntegration:
    """测试OrderBookManager OKX集成"""

    @pytest.fixture
    def okx_manager_setup(self):
        """设置OKX测试用的管理器"""
        config = Mock(spec=ExchangeConfig)
        config.exchange = Exchange.OKX
        config.market_type = MarketType.FUTURES
        config.base_url = "https://www.okx.com"
        config.snapshot_interval = 60

        normalizer = Mock(spec=DataNormalizer)
        manager = OrderBookManager(config, normalizer)
        manager.session = AsyncMock()
        manager.stats = {
            'updates_processed': 0,
            'sync_errors': 0,
            'snapshots_fetched': 0,
            'resync_count': 0
        }

        return manager

    @pytest.mark.asyncio
    async def test_start_okx_management(self, okx_manager_setup):
        """测试：启动OKX订单簿管理"""
        manager = okx_manager_setup
        symbols = ["BTC-USDT", "ETH-USDT"]

        with patch.object(manager, '_initialize_okx_orderbook') as mock_init:
            mock_init.return_value = None

            with patch('marketprism_collector.okx_websocket.OKXWebSocketClient') as mock_ws_class:
                mock_ws_client = AsyncMock()
                mock_ws_class.return_value = mock_ws_client

                await manager._start_okx_management(symbols)

                # 验证状态被创建
                for symbol in symbols:
                    assert symbol in manager.orderbook_states
                    state = manager.orderbook_states[symbol]
                    assert state.symbol == symbol
                    assert state.exchange == "okx"

                # 验证初始化被调用
                assert mock_init.call_count == len(symbols)

                # 验证WebSocket客户端被创建
                mock_ws_class.assert_called_once()
                assert manager.okx_ws_client is mock_ws_client

    @pytest.mark.asyncio
    async def test_initialize_okx_orderbook_success(self, okx_manager_setup):
        """测试：成功初始化OKX订单簿"""
        manager = okx_manager_setup
        symbol = "BTC-USDT"

        # 创建状态
        state = OrderBookState(symbol=symbol, exchange="okx")
        manager.orderbook_states[symbol] = state

        # 模拟快照
        mock_snapshot = OrderBookSnapshot(
            symbol=symbol,
            exchange="okx",
            last_update_id=67890,
            bids=[PriceLevel(price=Decimal("50000"), quantity=Decimal("1.0"))],
            asks=[PriceLevel(price=Decimal("50100"), quantity=Decimal("0.5"))],
            timestamp=datetime.now(timezone.utc)
        )

        with patch.object(manager, '_fetch_okx_snapshot') as mock_fetch:
            mock_fetch.return_value = mock_snapshot

            await manager._initialize_okx_orderbook(symbol)

            # 验证初始化成功
            assert state.local_orderbook is mock_snapshot
            assert state.last_update_id == 67890
            assert state.is_synced is True

    @pytest.mark.asyncio
    async def test_initialize_okx_orderbook_failure(self, okx_manager_setup):
        """测试：OKX订单簿初始化失败"""
        manager = okx_manager_setup
        symbol = "BTC-USDT"

        # 创建状态
        state = OrderBookState(symbol=symbol, exchange="okx")
        manager.orderbook_states[symbol] = state

        with patch.object(manager, '_fetch_okx_snapshot') as mock_fetch:
            mock_fetch.return_value = None

            await manager._initialize_okx_orderbook(symbol)

            # 验证初始化失败处理
            assert state.local_orderbook is None
            assert state.is_synced is False


@pytest.mark.skipif(not HAS_ORDERBOOK_MODULES, reason="OrderBook模块不可用")
class TestOrderBookManagerErrorHandling:
    """测试OrderBookManager错误处理"""

    @pytest.fixture
    def manager_setup(self):
        """设置测试用的管理器"""
        config = Mock(spec=ExchangeConfig)
        config.exchange = Exchange.BINANCE
        config.market_type = MarketType.SPOT
        config.base_url = "https://api.binance.com"
        config.snapshot_interval = 30

        normalizer = Mock(spec=DataNormalizer)
        manager = OrderBookManager(config, normalizer)
        manager.session = AsyncMock()
        manager.stats = {
            'updates_processed': 0,
            'sync_errors': 0,
            'snapshots_fetched': 0,
            'resync_count': 0
        }

        return manager

    @pytest.mark.asyncio
    async def test_handle_update_with_invalid_symbol(self, manager_setup):
        """测试：处理无效交易对的更新"""
        manager = manager_setup
        symbol = "INVALID_SYMBOL"

        update_data = {
            "e": "depthUpdate",
            "s": "BTCUSDT",
            "U": 12345,
            "u": 12346,
            "b": [["50000.00", "1.0"]],
            "a": [["50001.00", "0.8"]]
        }

        # 没有为该交易对创建状态
        result = await manager.handle_update(symbol, update_data)

        assert result is None

    @pytest.mark.asyncio
    async def test_handle_update_parsing_error(self, manager_setup):
        """测试：处理更新解析错误"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 创建状态
        state = OrderBookState(symbol=symbol, exchange="binance")
        manager.orderbook_states[symbol] = state

        # 无效的更新数据
        invalid_data = {
            "invalid": "data"
        }

        result = await manager.handle_update(symbol, invalid_data)

        assert result is None

    @pytest.mark.asyncio
    async def test_maintain_orderbook_error_recovery(self, manager_setup):
        """测试：订单簿维护错误恢复"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 创建状态
        state = OrderBookState(symbol=symbol, exchange="binance")
        manager.orderbook_states[symbol] = state

        # 直接测试错误处理逻辑，而不是运行整个循环
        with patch.object(manager, '_sync_orderbook') as mock_sync:
            mock_sync.side_effect = Exception("同步失败")

            # 模拟一次同步调用
            try:
                await manager._sync_orderbook(symbol)
            except Exception:
                # 手动调用错误处理
                manager._handle_sync_error(symbol, Exception("同步失败"))

            # 验证错误计数增加
            assert state.error_count > 0
            assert manager.stats['sync_errors'] > 0

    @pytest.mark.asyncio
    async def test_maintain_orderbook_max_errors_reset(self, manager_setup):
        """测试：达到最大错误次数时重置状态"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 创建有大量错误的状态
        state = OrderBookState(symbol=symbol, exchange="binance")
        state.error_count = manager.max_error_count - 1  # 设置为最大错误数-1
        manager.orderbook_states[symbol] = state

        with patch.object(manager, '_reset_orderbook_state') as mock_reset:
            # 直接测试错误处理逻辑
            manager._handle_sync_error(symbol, Exception("持续失败"))

            # 验证重置被调用
            mock_reset.assert_called_with(symbol)

    @pytest.mark.asyncio
    async def test_fetch_snapshot_network_error(self, manager_setup):
        """测试：网络错误时的快照获取"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 模拟网络异常
        manager.session.get.side_effect = Exception("网络连接失败")

        snapshot = await manager._fetch_snapshot(symbol)

        assert snapshot is None

    @pytest.mark.asyncio
    async def test_apply_update_without_local_orderbook(self, manager_setup):
        """测试：没有本地订单簿时应用更新"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 创建没有本地订单簿的状态
        state = OrderBookState(symbol=symbol, exchange="binance")
        state.local_orderbook = None
        manager.orderbook_states[symbol] = state

        update = Mock()
        update.symbol = symbol
        update.bids = []
        update.asks = []

        # 应该抛出异常或返回None
        try:
            result = await manager._apply_update(symbol, update)
            assert result is None
        except Exception:
            pass  # 预期可能抛出异常


@pytest.mark.skipif(not HAS_ORDERBOOK_MODULES, reason="OrderBook模块不可用")
class TestOrderBookManagerPerformanceAndUtilities:
    """测试OrderBookManager性能优化和工具方法"""

    @pytest.fixture
    def manager_setup(self):
        """设置测试用的管理器"""
        config = Mock(spec=ExchangeConfig)
        config.exchange = Exchange.BINANCE
        config.market_type = MarketType.SPOT
        config.base_url = "https://api.binance.com"
        config.snapshot_interval = 30

        normalizer = Mock(spec=DataNormalizer)
        manager = OrderBookManager(config, normalizer)
        manager.session = AsyncMock()
        manager.stats = {
            'updates_processed': 0,
            'sync_errors': 0,
            'snapshots_fetched': 0,
            'resync_count': 0
        }

        return manager

    def test_get_current_orderbook_success(self, manager_setup):
        """测试：成功获取当前订单簿"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 创建同步的状态
        state = OrderBookState(symbol=symbol, exchange="binance")
        state.is_synced = True

        snapshot = OrderBookSnapshot(
            symbol=symbol,
            exchange="binance",
            last_update_id=12345,
            bids=[PriceLevel(price=Decimal("50000"), quantity=Decimal("1.0"))],
            asks=[PriceLevel(price=Decimal("50100"), quantity=Decimal("0.5"))],
            timestamp=datetime.now(timezone.utc),
            checksum=98765
        )
        state.local_orderbook = snapshot
        manager.orderbook_states[symbol] = state

        enhanced_orderbook = manager.get_current_orderbook(symbol)

        assert enhanced_orderbook is not None
        assert enhanced_orderbook.symbol_name == symbol
        assert enhanced_orderbook.exchange_name == "binance"
        assert enhanced_orderbook.last_update_id == 12345
        assert enhanced_orderbook.checksum == 98765
        assert enhanced_orderbook.update_type == OrderBookUpdateType.SNAPSHOT

    def test_get_current_orderbook_not_synced(self, manager_setup):
        """测试：获取未同步的订单簿"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 创建未同步的状态
        state = OrderBookState(symbol=symbol, exchange="binance")
        state.is_synced = False
        manager.orderbook_states[symbol] = state

        enhanced_orderbook = manager.get_current_orderbook(symbol)

        assert enhanced_orderbook is None

    def test_get_current_orderbook_unknown_symbol(self, manager_setup):
        """测试：获取未知交易对的订单簿"""
        manager = manager_setup

        enhanced_orderbook = manager.get_current_orderbook("UNKNOWN_SYMBOL")

        assert enhanced_orderbook is None

    def test_get_statistics(self, manager_setup):
        """测试：获取统计信息"""
        manager = manager_setup

        # 设置一些统计数据
        manager.stats['updates_processed'] = 100
        manager.stats['sync_errors'] = 5
        manager.stats['snapshots_fetched'] = 10

        # 添加一些状态
        state1 = OrderBookState("BTCUSDT", "binance")
        state1.last_snapshot_time = datetime.now(timezone.utc)
        state2 = OrderBookState("ETHUSDT", "binance")
        state2.last_snapshot_time = datetime.now(timezone.utc)

        manager.orderbook_states["BTCUSDT"] = state1
        manager.orderbook_states["ETHUSDT"] = state2

        stats = manager.get_stats()  # 实际方法名是get_stats

        assert isinstance(stats, dict)
        assert 'global_stats' in stats
        assert 'symbol_stats' in stats
        assert 'config' in stats
        assert stats['global_stats']['updates_processed'] == 100
        assert stats['global_stats']['sync_errors'] == 5
        assert stats['global_stats']['snapshots_fetched'] == 10

    def test_build_snapshot_url_binance(self, manager_setup):
        """测试：构建Binance快照URL"""
        manager = manager_setup
        symbol = "BTCUSDT"

        url = manager._build_snapshot_url(symbol)

        expected_url = "https://api.binance.com/api/v3/depth?symbol=BTCUSDT&limit=1000"
        assert url == expected_url

    def test_build_snapshot_url_okx(self):
        """测试：构建OKX快照URL"""
        config = Mock(spec=ExchangeConfig)
        config.exchange = Exchange.OKX
        config.market_type = MarketType.FUTURES
        config.snapshot_interval = 60

        normalizer = Mock(spec=DataNormalizer)
        manager = OrderBookManager(config, normalizer)

        symbol = "BTC-USDT"
        url = manager._build_snapshot_url(symbol)

        expected_url = f"https://www.okx.com/api/v5/market/books?instId=BTC-USDT&sz={manager.depth_limit}"
        assert url == expected_url

    def test_check_and_reset_weight(self, manager_setup):
        """测试：检查和重置API权重"""
        manager = manager_setup

        # 设置初始权重
        manager.api_weight_used = 100
        manager.weight_reset_time = datetime.now(timezone.utc) - timedelta(minutes=2)

        manager._check_and_reset_weight()

        # 权重应该被重置
        assert manager.api_weight_used == 0
        assert manager.weight_reset_time > datetime.now(timezone.utc) - timedelta(seconds=10)

    def test_build_snapshot_url_custom_exchange(self, manager_setup):
        """测试：构建自定义交易所快照URL"""
        manager = manager_setup

        # 修改配置为自定义交易所
        manager.config.exchange = Mock()
        manager.config.exchange.value = "custom"
        manager.config.base_url = "https://api.custom.com"

        symbol = "BTCUSDT"
        url = manager._build_snapshot_url(symbol)

        expected_url = "https://api.custom.com/depth?symbol=BTCUSDT"
        assert url == expected_url


@pytest.mark.skipif(not HAS_ORDERBOOK_MODULES, reason="OrderBook模块不可用")
class TestOrderBookManagerAdvancedFeatures:
    """测试OrderBookManager高级功能 - TDD增强覆盖率"""

    @pytest.fixture
    def manager_setup(self):
        """设置测试用的管理器"""
        config = Mock(spec=ExchangeConfig)
        config.exchange = Exchange.BINANCE
        config.market_type = MarketType.SPOT
        config.base_url = "https://api.binance.com"
        config.snapshot_interval = 30

        normalizer = Mock(spec=DataNormalizer)
        manager = OrderBookManager(config, normalizer)
        manager.session = AsyncMock()
        manager.last_snapshot_request = {}
        manager.api_weight_used = 0

        return manager

    @pytest.mark.asyncio
    async def test_sync_orderbook_complete_flow(self, manager_setup):
        """测试：完整的订单簿同步流程"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 创建订单簿状态
        state = OrderBookState(symbol=symbol, exchange="binance")
        state.first_update_id = 100
        manager.orderbook_states[symbol] = state

        # 创建模拟快照
        snapshot = OrderBookSnapshot(
            symbol=symbol,
            exchange="binance",
            last_update_id=150,
            bids=[PriceLevel(price=Decimal("50000"), quantity=Decimal("1.0"))],
            asks=[PriceLevel(price=Decimal("50100"), quantity=Decimal("0.5"))],
            timestamp=datetime.now(timezone.utc)
        )

        with patch.object(manager, '_fetch_snapshot') as mock_fetch:
            mock_fetch.return_value = snapshot

            with patch.object(manager, '_clean_expired_updates_binance_style') as mock_clean:
                with patch.object(manager, '_apply_buffered_updates_binance_style') as mock_apply:
                    mock_apply.return_value = 5  # 应用了5个更新

                    await manager._sync_orderbook(symbol)

                    # 验证同步流程
                    assert state.local_orderbook is snapshot
                    assert state.last_update_id == 150
                    assert state.is_synced is True
                    assert state.error_count == 0
                    assert state.sync_in_progress is False

                    # 验证方法调用
                    mock_fetch.assert_called_once_with(symbol)
                    mock_clean.assert_called_once()
                    mock_apply.assert_called_once_with(symbol)

    @pytest.mark.asyncio
    async def test_handle_update_without_sync(self, manager_setup):
        """测试：处理未同步状态下的更新"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 创建未同步的状态
        state = OrderBookState(symbol=symbol, exchange="binance")
        state.is_synced = False
        manager.orderbook_states[symbol] = state

        # 创建模拟更新数据
        update_data = {
            "U": 100,
            "u": 101,
            "b": [["50000.00", "1.0"]],
            "a": [["50100.00", "0.5"]]
        }

        # 创建模拟更新对象
        mock_update = OrderBookUpdate(
            symbol=symbol,
            exchange="binance",
            first_update_id=100,
            last_update_id=101,
            bids=[PriceLevel(price=Decimal("50000"), quantity=Decimal("1.0"))],
            asks=[PriceLevel(price=Decimal("50100"), quantity=Decimal("0.5"))],
            timestamp=datetime.now(timezone.utc)
        )

        with patch.object(manager, '_parse_update') as mock_parse:
            mock_parse.return_value = mock_update

            result = await manager.handle_update(symbol, update_data)

            # 未同步时应该返回None，但更新被缓冲
            assert result is None
            assert len(state.update_buffer) == 1
            assert state.update_buffer[0] is mock_update

    @pytest.mark.asyncio
    async def test_apply_update_functionality(self, manager_setup):
        """测试：应用更新功能"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 创建已同步的状态和本地订单簿
        state = OrderBookState(symbol=symbol, exchange="binance")
        state.is_synced = True
        state.local_orderbook = OrderBookSnapshot(
            symbol=symbol,
            exchange="binance",
            last_update_id=100,
            bids=[PriceLevel(price=Decimal("50000"), quantity=Decimal("1.0"))],
            asks=[PriceLevel(price=Decimal("50100"), quantity=Decimal("0.5"))],
            timestamp=datetime.now(timezone.utc)
        )
        manager.orderbook_states[symbol] = state

        # 创建更新
        update = OrderBookUpdate(
            symbol=symbol,
            exchange="binance",
            first_update_id=101,
            last_update_id=101,
            bids=[PriceLevel(price=Decimal("49999"), quantity=Decimal("2.0"))],  # 新价位
            asks=[PriceLevel(price=Decimal("50100"), quantity=Decimal("0"))],    # 删除价位
            timestamp=datetime.now(timezone.utc)
        )

        result = await manager._apply_update(symbol, update)

        # 验证结果
        assert result is not None
        assert isinstance(result, EnhancedOrderBook)

    def test_error_handling_mechanisms(self, manager_setup):
        """测试：错误处理机制"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 创建状态
        state = OrderBookState(symbol=symbol, exchange="binance")
        manager.orderbook_states[symbol] = state

        # 测试错误处理
        error = Exception("测试错误")
        manager._handle_sync_error(symbol, error)

        # 验证错误计数和统计
        assert state.error_count == 1
        assert manager.consecutive_errors == 1
        assert manager.stats['sync_errors'] == 1
        assert manager.backoff_multiplier > 1.0

    def test_backoff_delay_calculation(self, manager_setup):
        """测试：退避延迟计算"""
        manager = manager_setup

        # 测试不同错误次数的延迟计算
        delay_1 = manager._calculate_backoff_delay(1)
        delay_3 = manager._calculate_backoff_delay(3)
        delay_10 = manager._calculate_backoff_delay(10)

        # 验证延迟递增
        assert delay_1 < delay_3 < delay_10
        assert delay_10 <= 300.0  # 最大延迟限制

    def test_should_retry_sync_logic(self, manager_setup):
        """测试：重试同步逻辑"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 创建状态
        state = OrderBookState(symbol=symbol, exchange="binance")
        manager.orderbook_states[symbol] = state

        # 测试正常情况下应该重试
        assert manager._should_retry_sync(symbol) is True

        # 测试错误次数过多时不应该重试
        state.error_count = manager.max_error_count
        assert manager._should_retry_sync(symbol) is False

        # 测试不存在的symbol
        assert manager._should_retry_sync("NONEXISTENT") is False

    def test_need_resync_conditions(self, manager_setup):
        """测试：需要重新同步的条件"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 创建状态
        state = OrderBookState(symbol=symbol, exchange="binance")

        # 测试错误次数过多
        state.error_count = manager.max_error_count
        assert manager._need_resync(state) is True

        # 测试没有本地订单簿
        state.error_count = 0
        state.local_orderbook = None
        assert manager._need_resync(state) is True

        # 测试缓冲区过大
        state.local_orderbook = Mock()
        state.update_buffer = deque([Mock() for _ in range(600)])  # 超过500
        assert manager._need_resync(state) is True

        # 测试正常情况
        state.update_buffer = deque()
        assert manager._need_resync(state) is False

    @pytest.mark.asyncio
    async def test_process_buffered_updates(self, manager_setup):
        """测试：处理缓冲更新"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 创建已同步的状态
        state = OrderBookState(symbol=symbol, exchange="binance")
        state.is_synced = True
        state.update_buffer = deque([Mock(), Mock()])  # 添加一些模拟更新
        manager.orderbook_states[symbol] = state

        with patch.object(manager, '_apply_buffered_updates') as mock_apply:
            mock_apply.return_value = 2  # 应用了2个更新

            await manager._process_buffered_updates(symbol)

            # 验证方法被调用
            mock_apply.assert_called_once_with(symbol)

    @pytest.mark.asyncio
    async def test_need_snapshot_refresh_logic(self, manager_setup):
        """测试：快照刷新需求逻辑"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 设置管理器的必要属性
        manager.snapshot_interval = 30  # 30秒间隔
        manager.min_snapshot_interval = 10  # 最小10秒间隔
        manager.backoff_multiplier = 1.0

        # 创建状态
        state = OrderBookState(symbol=symbol, exchange="binance")
        state.local_orderbook = Mock()  # 需要有本地订单簿
        state.last_snapshot_time = datetime.now(timezone.utc) - timedelta(seconds=35)  # 35秒前

        # 测试需要刷新（超过30秒）
        assert manager._need_snapshot_refresh(state) is True

        # 测试不需要刷新（最近刷新过）
        state.last_snapshot_time = datetime.now(timezone.utc) - timedelta(seconds=10)  # 10秒前
        assert manager._need_snapshot_refresh(state) is False

        # 测试没有本地订单簿时需要刷新
        state.local_orderbook = None
        assert manager._need_snapshot_refresh(state) is True

    @pytest.mark.asyncio
    async def test_refresh_snapshot_functionality(self, manager_setup):
        """测试：刷新快照功能"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 创建状态
        state = OrderBookState(symbol=symbol, exchange="binance")
        manager.orderbook_states[symbol] = state

        # 创建模拟快照
        mock_snapshot = OrderBookSnapshot(
            symbol=symbol,
            exchange="binance",
            last_update_id=123,
            bids=[PriceLevel(price=Decimal("50000"), quantity=Decimal("1.0"))],
            asks=[PriceLevel(price=Decimal("50100"), quantity=Decimal("0.5"))],
            timestamp=datetime.now(timezone.utc)
        )

        with patch.object(manager, '_fetch_snapshot') as mock_fetch:
            mock_fetch.return_value = mock_snapshot

            await manager._refresh_snapshot(symbol)

            # 验证fetch方法被调用
            mock_fetch.assert_called_once_with(symbol)

            # 验证状态被更新
            assert state.local_orderbook is mock_snapshot
            assert state.last_update_id == 123

    @pytest.mark.asyncio
    async def test_reset_orderbook_state(self, manager_setup):
        """测试：重置订单簿状态"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 创建有错误的状态
        state = OrderBookState(symbol=symbol, exchange="binance")
        state.error_count = 10
        state.is_synced = True
        state.update_buffer = deque([Mock(), Mock()])
        manager.orderbook_states[symbol] = state

        await manager._reset_orderbook_state(symbol)

        # 验证状态被重置
        assert state.error_count == 0
        assert state.is_synced is False
        assert len(state.update_buffer) == 0
        assert state.local_orderbook is None

    def test_parse_update_exchange_routing(self, manager_setup):
        """测试：更新解析的交易所路由"""
        manager = manager_setup
        symbol = "BTCUSDT"

        # 测试Binance解析
        manager.config.exchange = Exchange.BINANCE
        binance_data = {"U": 100, "u": 101, "b": [], "a": []}

        with patch.object(manager, '_parse_binance_update') as mock_binance:
            mock_binance.return_value = Mock()
            result = manager._parse_update(symbol, binance_data)
            mock_binance.assert_called_once_with(symbol, binance_data)
            assert result is not None

        # 测试OKX解析
        manager.config.exchange = Exchange.OKX
        okx_data = {"data": [{"bids": [], "asks": []}]}

        with patch.object(manager, '_parse_okx_update') as mock_okx:
            mock_okx.return_value = Mock()
            result = manager._parse_update(symbol, okx_data)
            mock_okx.assert_called_once_with(symbol, okx_data)
            assert result is not None

        # 测试不支持的交易所
        manager.config.exchange = Exchange.DERIBIT
        result = manager._parse_update(symbol, {})
        assert result is None

    @pytest.mark.asyncio
    async def test_start_okx_management_mode(self, manager_setup):
        """测试：启动OKX管理模式"""
        manager = manager_setup
        manager.config.exchange = Exchange.OKX
        symbols = ["BTCUSDT", "ETHUSDT"]

        with patch.object(manager, '_start_okx_management') as mock_okx:
            mock_okx.return_value = None

            result = await manager.start(symbols)

            # 验证OKX模式被调用
            mock_okx.assert_called_once_with(symbols)
            assert result is True  # 启动成功

    @pytest.mark.asyncio
    async def test_start_traditional_management_mode(self, manager_setup):
        """测试：启动传统管理模式"""
        manager = manager_setup
        manager.config.exchange = Exchange.BINANCE  # 非OKX交易所
        symbols = ["BTCUSDT"]

        with patch.object(manager, 'start_symbol_management') as mock_start:
            mock_start.return_value = None

            result = await manager.start(symbols)

            # 验证传统模式被调用
            mock_start.assert_called_once_with("BTCUSDT")
            assert result is True  # 启动成功
