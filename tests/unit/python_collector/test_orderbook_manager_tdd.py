"""
TDD Tests for OrderBook Manager

基于TDD方法论发现并修复OrderBook Manager的设计问题
重点测试：初始化、状态管理、快照获取、增量更新、同步逻辑
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import aiohttp

# 导入测试目标
from marketprism_collector.orderbook_manager import (
    OrderBookManager,
    OrderBookSnapshot,
    OrderBookUpdate,
    OrderBookState
)
from marketprism_collector.data_types import (
    Exchange, ExchangeConfig, PriceLevel, EnhancedOrderBook, DataType
)
from marketprism_collector.normalizer import DataNormalizer


class TestOrderBookManagerInitialization:
    """TDD: OrderBook Manager 初始化测试"""
    
    def test_manager_basic_initialization(self):
        """测试基本初始化"""
        # 创建配置
        config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            snapshot_interval=60,
            symbols=["BTCUSDT", "ETHUSDT"]
        )
        normalizer = Mock(spec=DataNormalizer)
        
        # 测试初始化
        manager = OrderBookManager(config, normalizer)
        
        # 验证基本属性
        assert manager.config == config
        assert manager.normalizer == normalizer
        assert isinstance(manager.orderbook_states, dict)
        assert len(manager.orderbook_states) == 0
        assert manager.depth_limit == 400  # 统一400档深度
        assert manager.max_error_count == 5
        assert manager.session is None
    
    def test_okx_specific_initialization(self):
        """测试OKX交易所特定初始化"""
        config = ExchangeConfig(
            exchange=Exchange.OKX,
            snapshot_interval=300,
            symbols=["BTC-USDT"]
        )
        normalizer = Mock(spec=DataNormalizer)
        
        manager = OrderBookManager(config, normalizer)
        
        # 验证OKX特定配置
        assert hasattr(manager, 'okx_snapshot_sync_interval')
        assert manager.okx_snapshot_sync_interval == 300
        assert hasattr(manager, 'okx_ws_client')
        assert hasattr(manager, 'okx_snapshot_sync_tasks')


class TestOrderBookStateManagement:
    """TDD: OrderBook 状态管理测试"""
    
    def test_orderbook_state_creation(self):
        """测试订单簿状态对象创建"""
        state = OrderBookState(
            symbol="BTCUSDT",
            exchange="binance"
        )
        
        # 验证默认值
        assert state.symbol == "BTCUSDT"
        assert state.exchange == "binance"
        assert state.local_orderbook is None
        assert state.last_update_id == 0
        assert state.is_synced is False
        assert state.error_count == 0
        assert state.total_updates == 0
        assert len(state.update_buffer) == 0
        assert state.update_buffer.maxlen == 1000
    
    def test_binance_sync_algorithm_fields(self):
        """测试Binance同步算法需要的字段"""
        state = OrderBookState(
            symbol="BTCUSDT",
            exchange="binance"
        )
        
        # 验证Binance同步相关字段
        assert state.first_update_id is None
        assert state.snapshot_last_update_id is None
        assert state.sync_in_progress is False


class TestOrderBookManagerDesignIssues:
    """TDD: 发现OrderBook Manager设计问题"""
    
    def test_missing_proxy_support_in_initialization(self):
        """发现问题：初始化时缺少代理配置支持"""
        config = ExchangeConfig(
            exchange=Exchange.BINANCE,
            proxy={'enabled': True, 'http': 'http://proxy:8080'}
        )
        normalizer = Mock(spec=DataNormalizer)
        
        manager = OrderBookManager(config, normalizer)
        
        # 检查是否有代理配置处理
        assert hasattr(manager.config, 'proxy')
        # TODO: 需要在start()方法中处理config.proxy配置
    
    def test_missing_essential_methods(self):
        """发现问题：缺少必要的方法"""
        config = ExchangeConfig(exchange=Exchange.BINANCE)
        normalizer = Mock(spec=DataNormalizer)
        manager = OrderBookManager(config, normalizer)
        
        # 检查必要方法是否存在
        method_names = [
            '_can_request_snapshot',
            '_can_request_within_weight_limit', 
            '_check_and_reset_weight',
            '_build_snapshot_url',
            '_validate_update_sequence',
            '_apply_update_to_orderbook',
            '_sync_orderbook_binance'
        ]
        
        missing_methods = []
        for method_name in method_names:
            if not hasattr(manager, method_name):
                missing_methods.append(method_name)
        
        # 如果有缺失的方法，测试失败
        assert len(missing_methods) == 0, f"Missing methods: {missing_methods}"
    
    def test_missing_error_recovery_mechanism(self):
        """发现问题：缺少完整的错误恢复机制"""
        config = ExchangeConfig(exchange=Exchange.BINANCE)
        normalizer = Mock(spec=DataNormalizer)
        manager = OrderBookManager(config, normalizer)
        
        # 检查错误恢复相关方法
        assert hasattr(manager, 'consecutive_errors')
        assert hasattr(manager, 'backoff_multiplier')
        
        # 检查错误恢复方法
        error_recovery_methods = [
            '_handle_sync_error',
            '_calculate_backoff_delay',
            '_should_retry_sync'
        ]
        
        missing_methods = []
        for method_name in error_recovery_methods:
            if not hasattr(manager, method_name):
                missing_methods.append(method_name)
        
        # 如果有缺失的错误恢复方法，测试失败
        assert len(missing_methods) == 0, f"Missing error recovery methods: {missing_methods}"


class TestOrderBookDataStructures:
    """TDD: 订单簿数据结构测试"""
    
    def test_orderbook_snapshot_validation(self):
        """测试订单簿快照数据验证"""
        # 创建有效快照
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT",
            exchange="binance",
            last_update_id=12345,
            bids=[PriceLevel(price=Decimal("50000"), quantity=Decimal("1.0"))],
            asks=[PriceLevel(price=Decimal("50100"), quantity=Decimal("1.0"))],
            timestamp=datetime.now(timezone.utc)
        )
        
        assert snapshot.symbol == "BTCUSDT"
        assert snapshot.last_update_id == 12345
        assert len(snapshot.bids) == 1
        assert len(snapshot.asks) == 1
    
    def test_orderbook_update_validation(self):
        """测试订单簿更新数据验证"""
        update = OrderBookUpdate(
            symbol="BTCUSDT",
            exchange="binance",
            first_update_id=12346,
            last_update_id=12350,
            bids=[PriceLevel(price=Decimal("49950"), quantity=Decimal("2.0"))],
            asks=[PriceLevel(price=Decimal("50150"), quantity=Decimal("1.5"))],
            timestamp=datetime.now(timezone.utc)
        )
        
        assert update.first_update_id == 12346
        assert update.last_update_id == 12350
        assert len(update.bids) == 1
        assert len(update.asks) == 1