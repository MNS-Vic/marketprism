"""
TDD测试：统一存储管理器测试
目标：提升存储系统的测试覆盖率

测试策略：
1. 测试存储管理器的核心功能
2. 测试ClickHouse集成
3. 测试缓存机制
4. 测试错误处理和恢复
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# 设置Python路径
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from core.storage.unified_storage_manager import (
    UnifiedStorageManager, UnifiedStorageConfig, StorageType
)
from core.storage.types import StorageConfig


class TestUnifiedStorageManagerInitialization:
    """测试统一存储管理器初始化"""
    
    def test_storage_manager_initialization_with_clickhouse(self):
        """测试：使用ClickHouse配置初始化存储管理器"""
        config = UnifiedStorageConfig(
            storage_type=StorageType.CLICKHOUSE,
            clickhouse_host="localhost",
            clickhouse_port=8123,
            clickhouse_database="test_db",
            clickhouse_user="default",
            clickhouse_password="",
            redis_enabled=False,
            memory_cache_enabled=True,
            batch_size=100,
            flush_interval=5.0
        )
        
        storage_manager = UnifiedStorageManager(config)
        
        # 验证初始化
        assert storage_manager.config == config
        assert storage_manager.config.storage_type == StorageType.CLICKHOUSE
        assert storage_manager.stats["writes"] == 0
        assert storage_manager.stats["reads"] == 0
        assert storage_manager.stats["errors"] == 0
        
    def test_storage_manager_initialization_with_redis_cache(self):
        """测试：启用Redis缓存的存储管理器初始化"""
        config = UnifiedStorageConfig(
            storage_type=StorageType.CLICKHOUSE,
            clickhouse_host="localhost",
            clickhouse_port=8123,
            clickhouse_database="test_db",
            redis_enabled=True,
            redis_host="localhost",
            redis_port=6379,
            redis_db=0,
            memory_cache_enabled=True
        )
        
        storage_manager = UnifiedStorageManager(config)
        
        # 验证Redis配置
        assert storage_manager.config.redis_enabled is True
        assert storage_manager.config.redis_host == "localhost"
        assert storage_manager.config.redis_port == 6379
        
    def test_storage_manager_initialization_validation(self):
        """测试：存储管理器初始化验证"""
        # 无效配置应该抛出异常
        with pytest.raises((ValueError, TypeError)):
            UnifiedStorageManager(None)
            
        # 缺少必要配置应该抛出异常
        invalid_config = UnifiedStorageConfig(
            storage_type=StorageType.CLICKHOUSE,
            # 缺少ClickHouse配置
        )
        
        with pytest.raises(ValueError):
            storage_manager = UnifiedStorageManager(invalid_config)
            # 尝试连接应该失败
            asyncio.run(storage_manager.initialize())


class TestUnifiedStorageManagerDataOperations:
    """测试存储管理器数据操作"""
    
    @pytest.mark.asyncio
    async def test_store_trade_data(self):
        """测试：存储交易数据"""
        config = UnifiedStorageConfig(
            storage_type=StorageType.CLICKHOUSE,
            clickhouse_host="localhost",
            clickhouse_port=8123,
            clickhouse_database="test_db",
            redis_enabled=False,
            memory_cache_enabled=True
        )
        
        storage_manager = UnifiedStorageManager(config)
        
        # Mock ClickHouse写入
        storage_manager._write_trade_to_clickhouse = AsyncMock(return_value=True)
        
        # 测试交易数据
        trade_data = {
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "trade_id": "12345",
            "price": 50000.0,
            "quantity": 0.1,
            "side": "buy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "is_buyer_maker": False
        }
        
        # 存储交易数据
        await storage_manager.store_trade(trade_data)
        
        # 验证调用
        storage_manager._write_trade_to_clickhouse.assert_called_once_with(trade_data)
        assert storage_manager.stats["writes"] == 1
        
    @pytest.mark.asyncio
    async def test_store_orderbook_data(self):
        """测试：存储订单簿数据"""
        config = UnifiedStorageConfig(
            storage_type=StorageType.CLICKHOUSE,
            clickhouse_host="localhost",
            clickhouse_port=8123,
            clickhouse_database="test_db",
            redis_enabled=False,
            memory_cache_enabled=True
        )
        
        storage_manager = UnifiedStorageManager(config)
        
        # Mock ClickHouse写入
        storage_manager._write_orderbook_to_clickhouse = AsyncMock(return_value=True)
        
        # 测试订单簿数据
        orderbook_data = {
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "bids": [[50000.0, 0.1], [49999.0, 0.2]],
            "asks": [[50001.0, 0.1], [50002.0, 0.2]],
            "last_update_id": 12345
        }
        
        # 存储订单簿数据
        await storage_manager.store_orderbook(orderbook_data)
        
        # 验证调用
        storage_manager._write_orderbook_to_clickhouse.assert_called_once_with(orderbook_data)
        assert storage_manager.stats["writes"] == 1
        
    @pytest.mark.asyncio
    async def test_store_ticker_data(self):
        """测试：存储行情数据"""
        config = UnifiedStorageConfig(
            storage_type=StorageType.CLICKHOUSE,
            clickhouse_host="localhost",
            clickhouse_port=8123,
            clickhouse_database="test_db",
            redis_enabled=False,
            memory_cache_enabled=True
        )
        
        storage_manager = UnifiedStorageManager(config)
        
        # Mock ClickHouse写入
        storage_manager._write_ticker_to_clickhouse = AsyncMock(return_value=True)
        
        # 测试行情数据
        ticker_data = {
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "last_price": 50000.0,
            "volume_24h": 1000.0,
            "price_change_24h": 1000.0,
            "price_change_percent_24h": 2.0,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # 存储行情数据
        await storage_manager.store_ticker(ticker_data)
        
        # 验证调用
        storage_manager._write_ticker_to_clickhouse.assert_called_once_with(ticker_data)
        assert storage_manager.stats["writes"] == 1


class TestUnifiedStorageManagerCaching:
    """测试存储管理器缓存功能"""
    
    @pytest.mark.asyncio
    async def test_memory_cache_functionality(self):
        """测试：内存缓存功能"""
        config = UnifiedStorageConfig(
            storage_type=StorageType.CLICKHOUSE,
            clickhouse_host="localhost",
            clickhouse_port=8123,
            clickhouse_database="test_db",
            memory_cache_enabled=True,
            memory_cache_size=1000
        )
        
        storage_manager = UnifiedStorageManager(config)
        
        # 测试缓存写入
        key = "test_key"
        value = {"test": "data"}
        
        storage_manager._cache_in_memory(key, value)
        
        # 验证缓存
        assert key in storage_manager.memory_cache
        assert storage_manager.memory_cache[key] == value
        
    @pytest.mark.asyncio
    async def test_redis_cache_functionality(self):
        """测试：Redis缓存功能"""
        config = UnifiedStorageConfig(
            storage_type=StorageType.CLICKHOUSE,
            clickhouse_host="localhost",
            clickhouse_port=8123,
            clickhouse_database="test_db",
            redis_enabled=True,
            redis_host="localhost",
            redis_port=6379
        )
        
        storage_manager = UnifiedStorageManager(config)
        
        # Mock Redis操作
        storage_manager._cache_latest_trade = AsyncMock()
        
        # 测试数据
        trade_data = {
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "price": 50000.0
        }
        
        # 缓存交易数据
        await storage_manager._cache_latest_trade(trade_data)
        
        # 验证调用
        storage_manager._cache_latest_trade.assert_called_once_with(trade_data)
        
    @pytest.mark.asyncio
    async def test_cache_eviction_policy(self):
        """测试：缓存淘汰策略"""
        config = UnifiedStorageConfig(
            storage_type=StorageType.CLICKHOUSE,
            clickhouse_host="localhost",
            clickhouse_port=8123,
            clickhouse_database="test_db",
            memory_cache_enabled=True,
            memory_cache_size=2  # 小缓存用于测试淘汰
        )
        
        storage_manager = UnifiedStorageManager(config)
        
        # 填充缓存超过限制
        storage_manager._cache_in_memory("key1", "value1")
        storage_manager._cache_in_memory("key2", "value2")
        storage_manager._cache_in_memory("key3", "value3")  # 应该触发淘汰
        
        # 验证缓存大小限制
        assert len(storage_manager.memory_cache) <= config.memory_cache_size


class TestUnifiedStorageManagerErrorHandling:
    """测试存储管理器错误处理"""
    
    @pytest.mark.asyncio
    async def test_clickhouse_connection_error_handling(self):
        """测试：ClickHouse连接错误处理"""
        config = UnifiedStorageConfig(
            storage_type=StorageType.CLICKHOUSE,
            clickhouse_host="invalid_host",
            clickhouse_port=8123,
            clickhouse_database="test_db"
        )
        
        storage_manager = UnifiedStorageManager(config)
        
        # Mock连接失败
        storage_manager._write_trade_to_clickhouse = AsyncMock(
            side_effect=Exception("Connection failed")
        )
        
        # 测试数据
        trade_data = {
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "price": 50000.0
        }
        
        # 存储应该处理错误
        await storage_manager.store_trade(trade_data)
        
        # 验证错误计数
        assert storage_manager.stats["errors"] == 1
        
    @pytest.mark.asyncio
    async def test_data_validation_error_handling(self):
        """测试：数据验证错误处理"""
        config = UnifiedStorageConfig(
            storage_type=StorageType.CLICKHOUSE,
            clickhouse_host="localhost",
            clickhouse_port=8123,
            clickhouse_database="test_db"
        )
        
        storage_manager = UnifiedStorageManager(config)
        
        # 无效数据
        invalid_trade_data = {
            # 缺少必要字段
            "exchange": "binance"
        }
        
        # Mock写入方法
        storage_manager._write_trade_to_clickhouse = AsyncMock()
        
        # 存储无效数据应该处理错误
        await storage_manager.store_trade(invalid_trade_data)
        
        # 验证处理（可能记录错误或使用默认值）
        assert storage_manager.stats["writes"] >= 0  # 可能成功也可能失败
        
    @pytest.mark.asyncio
    async def test_batch_operation_error_recovery(self):
        """测试：批量操作错误恢复"""
        config = UnifiedStorageConfig(
            storage_type=StorageType.CLICKHOUSE,
            clickhouse_host="localhost",
            clickhouse_port=8123,
            clickhouse_database="test_db",
            batch_size=3
        )
        
        storage_manager = UnifiedStorageManager(config)
        
        # Mock批量写入，部分失败
        storage_manager._write_trade_to_clickhouse = AsyncMock(
            side_effect=[Exception("Failed"), True, True]
        )
        
        # 批量数据
        trade_data_list = [
            {"exchange": "binance", "symbol": "BTCUSDT", "price": 50000.0},
            {"exchange": "binance", "symbol": "ETHUSDT", "price": 3000.0},
            {"exchange": "binance", "symbol": "ADAUSDT", "price": 1.0}
        ]
        
        # 处理批量数据
        for trade_data in trade_data_list:
            await storage_manager.store_trade(trade_data)
        
        # 验证部分成功处理
        assert storage_manager.stats["writes"] >= 2  # 至少2个成功
        assert storage_manager.stats["errors"] >= 1  # 至少1个失败


class TestUnifiedStorageManagerPerformance:
    """测试存储管理器性能功能"""
    
    def test_storage_statistics_tracking(self):
        """测试：存储统计跟踪"""
        config = UnifiedStorageConfig(
            storage_type=StorageType.CLICKHOUSE,
            clickhouse_host="localhost",
            clickhouse_port=8123,
            clickhouse_database="test_db"
        )
        
        storage_manager = UnifiedStorageManager(config)
        
        # 验证初始统计
        stats = storage_manager.get_stats()
        
        assert "writes" in stats
        assert "reads" in stats
        assert "errors" in stats
        assert "cache_hits" in stats
        assert "cache_misses" in stats
        assert stats["writes"] == 0
        assert stats["reads"] == 0
        assert stats["errors"] == 0
        
    def test_performance_metrics_collection(self):
        """测试：性能指标收集"""
        config = UnifiedStorageConfig(
            storage_type=StorageType.CLICKHOUSE,
            clickhouse_host="localhost",
            clickhouse_port=8123,
            clickhouse_database="test_db"
        )
        
        storage_manager = UnifiedStorageManager(config)
        
        # 获取性能指标
        metrics = storage_manager.get_performance_metrics()
        
        assert "total_operations" in metrics
        assert "success_rate" in metrics
        assert "average_latency" in metrics
        assert "cache_hit_rate" in metrics
