"""
Orderbook Snapshot Managers 单元测试
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from decimal import Decimal
from typing import List

from collector.orderbook_snap_managers.base_orderbook_snap_manager import BaseOrderBookSnapManager
from collector.orderbook_snap_managers.binance_spot_snap_manager import BinanceSpotSnapManager
from collector.orderbook_snap_managers.binance_derivatives_snap_manager import BinanceDerivativesSnapManager
from collector.orderbook_snap_managers.okx_spot_snap_manager import OKXSpotSnapManager
from collector.orderbook_snap_managers.okx_derivatives_snap_manager import OKXDerivativesSnapManager
from collector.data_types import PriceLevel


class TestBaseOrderBookSnapManager:
    """测试 BaseOrderBookSnapManager 基类"""

    @pytest.fixture
    def mock_normalizer(self):
        """Mock Normalizer"""
        normalizer = MagicMock()
        normalizer.normalize_enhanced_orderbook_from_snapshot = MagicMock(
            return_value=MagicMock(symbol="BTC-USDT")
        )
        return normalizer

    @pytest.fixture
    def mock_nats(self):
        """Mock NATS Publisher"""
        nats = MagicMock()
        nats.publish_enhanced_orderbook = AsyncMock()
        return nats

    @pytest.fixture
    def concrete_manager(self, mock_normalizer, mock_nats):
        """创建具体的 Manager 实例用于测试基类"""
        class ConcreteSnapManager(BaseOrderBookSnapManager):
            async def _fetch_one(self, symbol: str):
                """测试用的 fetch 实现"""
                return {
                    "bids": [["100.0", "1.0"], ["99.0", "2.0"]],
                    "asks": [["101.0", "1.5"], ["102.0", "2.5"]],
                    "last_update_id": 12345
                }

        manager = ConcreteSnapManager(
            exchange="test_exchange",
            market_type="spot",
            symbols=["BTCUSDT", "ETHUSDT"],
            normalizer=mock_normalizer,
            nats_publisher=mock_nats,
            config={"snapshot_interval": 1.0, "snapshot_depth": 100}
        )
        return manager

    @pytest.mark.asyncio
    async def test_manager_initialization(self, concrete_manager):
        """测试管理器初始化"""
        assert concrete_manager.exchange == "test_exchange"
        assert concrete_manager.market_type == "spot"
        assert concrete_manager.symbols == ["BTCUSDT", "ETHUSDT"]
        assert concrete_manager.snapshot_interval == 1.0
        assert concrete_manager.snapshot_depth == 100
        assert not concrete_manager.is_running

    @pytest.mark.asyncio
    async def test_normalize_and_publish_success(self, concrete_manager, mock_normalizer, mock_nats):
        """测试正常的标准化和发布流程"""
        bids = [["100.0", "1.0"], ["99.0", "2.0"]]
        asks = [["101.0", "1.5"], ["102.0", "2.5"]]
        
        await concrete_manager._normalize_and_publish(
            symbol="BTCUSDT",
            bids=bids,
            asks=asks,
            last_update_id=12345
        )

        # 验证 normalizer 被调用
        assert mock_normalizer.normalize_enhanced_orderbook_from_snapshot.called
        call_args = mock_normalizer.normalize_enhanced_orderbook_from_snapshot.call_args
        
        # 验证参数
        assert call_args.kwargs["exchange"] == "test_exchange"
        assert call_args.kwargs["symbol"] == "BTCUSDT"
        assert call_args.kwargs["market_type"] == "spot"
        assert call_args.kwargs["last_update_id"] == 12345
        
        # 验证 bids/asks 被转换为 PriceLevel
        bid_levels = call_args.kwargs["bids"]
        ask_levels = call_args.kwargs["asks"]
        assert len(bid_levels) == 2
        assert len(ask_levels) == 2
        assert isinstance(bid_levels[0], PriceLevel)
        assert bid_levels[0].price == Decimal("100.0")
        assert bid_levels[0].quantity == Decimal("1.0")

        # 验证 NATS 发布被调用
        assert mock_nats.publish_enhanced_orderbook.called

    @pytest.mark.asyncio
    async def test_normalize_and_publish_with_empty_data(self, concrete_manager, mock_normalizer, mock_nats):
        """测试空数据的处理"""
        await concrete_manager._normalize_and_publish(
            symbol="BTCUSDT",
            bids=[],
            asks=[],
            last_update_id=0
        )

        # 应该仍然调用 normalizer 和 NATS
        assert mock_normalizer.normalize_enhanced_orderbook_from_snapshot.called
        assert mock_nats.publish_enhanced_orderbook.called

    @pytest.mark.asyncio
    async def test_normalize_and_publish_with_exception(self, concrete_manager, mock_normalizer, mock_nats):
        """测试异常处理"""
        mock_normalizer.normalize_enhanced_orderbook_from_snapshot.side_effect = Exception("Test error")
        
        # 不应该抛出异常，应该被捕获并记录日志
        await concrete_manager._normalize_and_publish(
            symbol="BTCUSDT",
            bids=[["100", "1"]],
            asks=[["101", "1"]],
            last_update_id=123
        )
        
        # NATS 不应该被调用
        assert not mock_nats.publish_enhanced_orderbook.called

    @pytest.mark.asyncio
    async def test_start_stop(self, concrete_manager):
        """测试启动和停止"""
        # 启动
        await concrete_manager.start()
        assert concrete_manager.is_running
        
        # 等待一小段时间让调度循环运行
        await asyncio.sleep(0.1)
        
        # 停止
        await concrete_manager.stop()
        assert not concrete_manager.is_running


class TestBinanceSpotSnapManager:
    """测试 BinanceSpotSnapManager"""

    @pytest.fixture
    def mock_normalizer(self):
        normalizer = MagicMock()
        normalizer.normalize_enhanced_orderbook_from_snapshot = MagicMock(
            return_value=MagicMock(symbol="BTC-USDT")
        )
        return normalizer

    @pytest.fixture
    def mock_nats(self):
        nats = MagicMock()
        nats.publish_enhanced_orderbook = AsyncMock()
        return nats

    @pytest.fixture
    def manager(self, mock_normalizer, mock_nats):
        return BinanceSpotSnapManager(
            exchange="binance",
            market_type="spot",
            symbols=["BTCUSDT"],
            normalizer=mock_normalizer,
            nats_publisher=mock_nats,
            config={
                "snapshot_interval": 1.0,
                "snapshot_depth": 100,
                "rest_base": "https://api.binance.com",
                "request_timeout": 0.9
            }
        )

    @pytest.mark.asyncio
    async def test_fetch_one_success(self, manager):
        """测试成功获取快照"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "lastUpdateId": 12345,
            "bids": [["100.0", "1.0"], ["99.0", "2.0"]],
            "asks": [["101.0", "1.5"], ["102.0", "2.5"]]
        })

        with patch.object(manager, '_session') as mock_session:
            mock_session.get = AsyncMock(return_value=mock_response)
            mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_session.get.return_value.__aexit__ = AsyncMock()

            await manager._fetch_one("BTCUSDT")

            # 验证请求参数
            mock_session.get.assert_called_once()
            call_args = mock_session.get.call_args
            assert "symbol=BTCUSDT" in str(call_args) or call_args.kwargs.get("params", {}).get("symbol") == "BTCUSDT"

    @pytest.mark.asyncio
    async def test_fetch_one_timeout(self, manager):
        """测试请求超时"""
        with patch.object(manager, '_session') as mock_session:
            mock_session.get = AsyncMock(side_effect=asyncio.TimeoutError())

            # 不应该抛出异常
            await manager._fetch_one("BTCUSDT")

    @pytest.mark.asyncio
    async def test_fetch_one_http_error(self, manager):
        """测试 HTTP 错误"""
        mock_response = MagicMock()
        mock_response.status = 500

        with patch.object(manager, '_session') as mock_session:
            mock_session.get = AsyncMock(return_value=mock_response)
            mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_session.get.return_value.__aexit__ = AsyncMock()

            # 不应该抛出异常
            await manager._fetch_one("BTCUSDT")


class TestBinanceDerivativesSnapManager:
    """测试 BinanceDerivativesSnapManager"""

    @pytest.fixture
    def mock_normalizer(self):
        normalizer = MagicMock()
        normalizer.normalize_enhanced_orderbook_from_snapshot = MagicMock(
            return_value=MagicMock(symbol="BTC-USDT")
        )
        return normalizer

    @pytest.fixture
    def mock_nats(self):
        nats = MagicMock()
        nats.publish_enhanced_orderbook = AsyncMock()
        return nats

    @pytest.fixture
    def manager(self, mock_normalizer, mock_nats):
        return BinanceDerivativesSnapManager(
            exchange="binance_derivatives",
            market_type="perpetual",
            symbols=["BTCUSDT", "ETHUSDT"],
            normalizer=mock_normalizer,
            nats_publisher=mock_nats,
            config={
                "snapshot_interval": 1.0,
                "snapshot_depth": 100,
                "ws_api_url": "wss://ws-fapi.binance.com/ws-fapi/v1",
                "request_timeout": 0.8
            }
        )

    @pytest.mark.asyncio
    async def test_initialization(self, manager):
        """测试初始化"""
        assert manager.ws_api_url == "wss://ws-fapi.binance.com/ws-fapi/v1"
        assert manager.request_timeout == 0.8
        assert manager._ws is None
        assert manager._recv_task is None

    @pytest.mark.asyncio
    async def test_request_id_increment(self, manager):
        """测试请求 ID 自增"""
        id1 = manager._next_request_id()
        id2 = manager._next_request_id()
        id3 = manager._next_request_id()
        
        assert id2 == id1 + 1
        assert id3 == id2 + 1


class TestOKXSpotSnapManager:
    """测试 OKXSpotSnapManager"""

    @pytest.fixture
    def mock_normalizer(self):
        normalizer = MagicMock()
        normalizer.normalize_enhanced_orderbook_from_snapshot = MagicMock(
            return_value=MagicMock(symbol="BTC-USDT")
        )
        return normalizer

    @pytest.fixture
    def mock_nats(self):
        nats = MagicMock()
        nats.publish_enhanced_orderbook = AsyncMock()
        return nats

    @pytest.fixture
    def manager(self, mock_normalizer, mock_nats):
        return OKXSpotSnapManager(
            exchange="okx",
            market_type="spot",
            symbols=["BTC-USDT"],
            normalizer=mock_normalizer,
            nats_publisher=mock_nats,
            config={
                "snapshot_interval": 1.0,
                "snapshot_depth": 100,
                "rest_base": "https://www.okx.com",
                "request_timeout": 0.9
            }
        )

    @pytest.mark.asyncio
    async def test_fetch_one_success(self, manager):
        """测试成功获取 OKX 快照"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "code": "0",
            "data": [{
                "bids": [["100.0", "1.0", "0", "1"]],
                "asks": [["101.0", "1.5", "0", "1"]],
                "ts": "1234567890123"
            }]
        })

        with patch.object(manager, '_session') as mock_session:
            mock_session.get = AsyncMock(return_value=mock_response)
            mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_session.get.return_value.__aexit__ = AsyncMock()

            await manager._fetch_one("BTC-USDT")

            # 验证请求参数
            mock_session.get.assert_called_once()

