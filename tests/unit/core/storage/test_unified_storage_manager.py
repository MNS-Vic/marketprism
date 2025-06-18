"""
统一存储管理器测试
测试UnifiedStorageManager的核心功能
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, List
from datetime import datetime

# 导入被测试的模块
try:
    from core.storage.unified_storage_manager import (
        UnifiedStorageManager, 
        UnifiedStorageConfig,
        StorageMode
    )
    from core.storage.types import StorageType
except ImportError as e:
    pytest.skip(f"存储模块导入失败: {e}", allow_module_level=True)


class TestUnifiedStorageManagerInitialization:
    """统一存储管理器初始化测试"""
    
    def test_storage_manager_initialization_default(self):
        """测试使用默认配置初始化存储管理器"""
        config = UnifiedStorageConfig()
        storage_manager = UnifiedStorageManager(config)
        
        assert storage_manager is not None
        assert storage_manager.config == config
        assert hasattr(storage_manager, '_hot_storage')
        assert hasattr(storage_manager, '_cold_storage')
        assert hasattr(storage_manager, '_writers')
        
    def test_storage_manager_initialization_hot_storage(self):
        """测试热存储模式初始化"""
        config = UnifiedStorageConfig(
            storage_type="hot",
            clickhouse_host="localhost",
            clickhouse_port=8123,
            redis_enabled=True
        )
        
        storage_manager = UnifiedStorageManager(config)
        
        assert storage_manager.config.storage_type == "hot"
        assert storage_manager.config.redis_enabled is True
        
    def test_storage_manager_initialization_cold_storage(self):
        """测试冷存储模式初始化"""
        config = UnifiedStorageConfig(
            storage_type="cold",
            clickhouse_host="localhost",
            clickhouse_port=8124,
            enable_compression=True
        )
        
        storage_manager = UnifiedStorageManager(config)
        
        assert storage_manager.config.storage_type == "cold"
        assert storage_manager.config.enable_compression is True
        
    def test_storage_manager_initialization_hybrid_storage(self):
        """测试混合存储模式初始化"""
        config = UnifiedStorageConfig(
            storage_type="hybrid",
            clickhouse_host="localhost",
            redis_enabled=True,
            enable_compression=True
        )
        
        storage_manager = UnifiedStorageManager(config)
        
        assert storage_manager.config.storage_type == "hybrid"
        
    def test_storage_manager_validates_config(self):
        """测试存储管理器验证配置"""
        # 测试无效配置
        with pytest.raises((ValueError, TypeError)):
            UnifiedStorageManager(None)
            
        # 测试无效存储类型
        with pytest.raises(ValueError):
            config = UnifiedStorageConfig(storage_type="invalid_type")
            UnifiedStorageManager(config)


class TestUnifiedStorageManagerConnection:
    """统一存储管理器连接测试"""
    
    @pytest.fixture
    def storage_manager(self):
        """创建测试用的存储管理器"""
        config = UnifiedStorageConfig(
            clickhouse_host="localhost",
            clickhouse_port=8123,
            clickhouse_database="test_marketprism"
        )
        return UnifiedStorageManager(config)
        
    async def test_storage_manager_connect_clickhouse(self, storage_manager, mock_clickhouse_client):
        """测试连接ClickHouse"""
        with patch('aiochclient.ChClient') as mock_client_class:
            mock_client_class.return_value = mock_clickhouse_client
            
            await storage_manager.connect()
            
            # 验证连接建立
            assert storage_manager._clickhouse_client is not None
            mock_client_class.assert_called_once()
            
    async def test_storage_manager_connect_redis(self, storage_manager, mock_redis_client):
        """测试连接Redis"""
        storage_manager.config.redis_enabled = True
        
        with patch('redis.asyncio.Redis') as mock_redis_class:
            mock_redis_class.return_value = mock_redis_client
            
            await storage_manager.connect()
            
            # 验证Redis连接
            assert storage_manager._redis_client is not None
            mock_redis_class.assert_called_once()
            
    async def test_storage_manager_connection_error_handling(self, storage_manager):
        """测试连接错误处理"""
        with patch('aiochclient.ChClient') as mock_client_class:
            mock_client_class.side_effect = ConnectionError("连接失败")
            
            with pytest.raises(ConnectionError):
                await storage_manager.connect()
                
    async def test_storage_manager_disconnect(self, storage_manager, mock_clickhouse_client):
        """测试断开连接"""
        storage_manager._clickhouse_client = mock_clickhouse_client
        storage_manager._redis_client = Mock()
        
        await storage_manager.disconnect()
        
        # 验证连接关闭
        mock_clickhouse_client.close.assert_called_once()
        assert storage_manager._clickhouse_client is None


class TestUnifiedStorageManagerDataOperations:
    """统一存储管理器数据操作测试"""
    
    @pytest.fixture
    def connected_storage_manager(self, mock_clickhouse_client, mock_redis_client):
        """创建已连接的存储管理器"""
        config = UnifiedStorageConfig(
            storage_type="hot",
            redis_enabled=True
        )
        storage_manager = UnifiedStorageManager(config)
        storage_manager._clickhouse_client = mock_clickhouse_client
        storage_manager._redis_client = mock_redis_client
        
        return storage_manager
        
    async def test_storage_manager_write_trade_data(self, connected_storage_manager, sample_trade_data):
        """测试写入交易数据"""
        storage_manager = connected_storage_manager
        
        await storage_manager.write_trade_data([sample_trade_data])
        
        # 验证ClickHouse写入
        storage_manager._clickhouse_client.execute.assert_called_once()
        
        # 验证Redis缓存（如果启用）
        if storage_manager.config.redis_enabled:
            storage_manager._redis_client.set.assert_called()
            
    async def test_storage_manager_write_orderbook_data(self, connected_storage_manager, sample_orderbook_data):
        """测试写入订单簿数据"""
        storage_manager = connected_storage_manager
        
        await storage_manager.write_orderbook_data([sample_orderbook_data])
        
        storage_manager._clickhouse_client.execute.assert_called_once()
        
    async def test_storage_manager_write_ticker_data(self, connected_storage_manager, sample_ticker_data):
        """测试写入行情数据"""
        storage_manager = connected_storage_manager
        
        await storage_manager.write_ticker_data([sample_ticker_data])
        
        storage_manager._clickhouse_client.execute.assert_called_once()
        
    async def test_storage_manager_batch_write(self, connected_storage_manager):
        """测试批量写入数据"""
        storage_manager = connected_storage_manager
        
        trade_data = [
            {"exchange": "binance", "symbol": "BTCUSDT", "price": 50000.0},
            {"exchange": "binance", "symbol": "ETHUSDT", "price": 3000.0}
        ]
        
        await storage_manager.batch_write_trades(trade_data)
        
        # 验证批量写入
        storage_manager._clickhouse_client.execute.assert_called_once()
        
    async def test_storage_manager_read_trade_data(self, connected_storage_manager):
        """测试读取交易数据"""
        storage_manager = connected_storage_manager
        
        # 模拟查询结果
        mock_result = [
            {"exchange": "binance", "symbol": "BTCUSDT", "price": 50000.0}
        ]
        storage_manager._clickhouse_client.fetch.return_value = mock_result
        
        result = await storage_manager.read_trade_data(
            exchange="binance",
            symbol="BTCUSDT",
            start_time=datetime.now(),
            end_time=datetime.now()
        )
        
        assert result == mock_result
        storage_manager._clickhouse_client.fetch.assert_called_once()
        
    async def test_storage_manager_read_with_cache(self, connected_storage_manager):
        """测试带缓存的读取"""
        storage_manager = connected_storage_manager
        
        # 模拟Redis缓存命中
        cached_data = '{"data": "cached_result"}'
        storage_manager._redis_client.get.return_value = cached_data
        
        result = await storage_manager.read_trade_data_cached(
            exchange="binance",
            symbol="BTCUSDT"
        )
        
        # 验证从缓存读取
        storage_manager._redis_client.get.assert_called_once()
        # 不应该查询ClickHouse
        storage_manager._clickhouse_client.fetch.assert_not_called()


class TestUnifiedStorageManagerHotColdStorage:
    """统一存储管理器热冷存储测试"""
    
    @pytest.fixture
    def hybrid_storage_manager(self, mock_clickhouse_client):
        """创建混合存储管理器"""
        config = UnifiedStorageConfig(
            storage_type="hybrid",
            hot_data_ttl=3600,
            cold_data_ttl=2592000,
            archive_threshold_days=7
        )
        storage_manager = UnifiedStorageManager(config)
        storage_manager._clickhouse_client = mock_clickhouse_client
        
        return storage_manager
        
    async def test_storage_manager_hot_storage_write(self, hybrid_storage_manager):
        """测试热存储写入"""
        storage_manager = hybrid_storage_manager
        
        recent_data = {
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "timestamp": datetime.now().timestamp() * 1000
        }
        
        await storage_manager.write_to_hot_storage([recent_data])
        
        # 验证写入热存储
        storage_manager._clickhouse_client.execute.assert_called_once()
        
    async def test_storage_manager_cold_storage_write(self, hybrid_storage_manager):
        """测试冷存储写入"""
        storage_manager = hybrid_storage_manager
        
        old_data = {
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "timestamp": (datetime.now().timestamp() - 86400 * 30) * 1000  # 30天前
        }
        
        await storage_manager.write_to_cold_storage([old_data])
        
        storage_manager._clickhouse_client.execute.assert_called_once()
        
    async def test_storage_manager_data_archival(self, hybrid_storage_manager):
        """测试数据归档"""
        storage_manager = hybrid_storage_manager
        
        await storage_manager.archive_old_data()
        
        # 验证归档操作
        storage_manager._clickhouse_client.execute.assert_called()
        
    async def test_storage_manager_data_cleanup(self, hybrid_storage_manager):
        """测试数据清理"""
        storage_manager = hybrid_storage_manager
        
        await storage_manager.cleanup_expired_data()
        
        # 验证清理操作
        storage_manager._clickhouse_client.execute.assert_called()


class TestUnifiedStorageManagerPerformance:
    """统一存储管理器性能测试"""
    
    @pytest.fixture
    def performance_storage_manager(self, mock_clickhouse_client):
        """创建性能测试用的存储管理器"""
        config = UnifiedStorageConfig(
            storage_type="hot",
            batch_size=1000,
            flush_interval=5
        )
        storage_manager = UnifiedStorageManager(config)
        storage_manager._clickhouse_client = mock_clickhouse_client
        
        return storage_manager
        
    async def test_storage_manager_batch_optimization(self, performance_storage_manager):
        """测试批量优化"""
        storage_manager = performance_storage_manager
        
        # 模拟大量数据
        large_dataset = [
            {"exchange": "binance", "symbol": f"SYMBOL{i}", "price": 100.0 + i}
            for i in range(2000)
        ]
        
        await storage_manager.batch_write_trades(large_dataset)
        
        # 验证批量处理
        call_count = storage_manager._clickhouse_client.execute.call_count
        assert call_count >= 2  # 应该分批处理
        
    async def test_storage_manager_connection_pooling(self, performance_storage_manager):
        """测试连接池"""
        storage_manager = performance_storage_manager
        
        # 模拟并发写入
        tasks = []
        for i in range(10):
            data = [{"exchange": "binance", "symbol": "BTCUSDT", "price": 50000.0 + i}]
            task = storage_manager.write_trade_data(data)
            tasks.append(task)
            
        await asyncio.gather(*tasks)
        
        # 验证并发处理
        assert storage_manager._clickhouse_client.execute.call_count == 10
        
    async def test_storage_manager_memory_optimization(self, performance_storage_manager):
        """测试内存优化"""
        storage_manager = performance_storage_manager
        
        # 测试大数据集的内存使用
        large_data = [
            {"exchange": "binance", "symbol": "BTCUSDT", "data": "x" * 1000}
            for _ in range(1000)
        ]
        
        # 应该不会导致内存溢出
        await storage_manager.write_trade_data(large_data)
        
        # 验证数据被正确处理
        storage_manager._clickhouse_client.execute.assert_called()


class TestUnifiedStorageManagerErrorHandling:
    """统一存储管理器错误处理测试"""
    
    @pytest.fixture
    def error_prone_storage_manager(self, mock_clickhouse_client):
        """创建容易出错的存储管理器"""
        config = UnifiedStorageConfig()
        storage_manager = UnifiedStorageManager(config)
        storage_manager._clickhouse_client = mock_clickhouse_client
        
        return storage_manager
        
    async def test_storage_manager_handles_write_errors(self, error_prone_storage_manager):
        """测试写入错误处理"""
        storage_manager = error_prone_storage_manager
        
        # 模拟写入错误
        storage_manager._clickhouse_client.execute.side_effect = Exception("写入失败")
        
        data = [{"exchange": "binance", "symbol": "BTCUSDT", "price": 50000.0}]
        
        # 应该不抛出异常，而是记录错误
        with pytest.raises(Exception):
            await storage_manager.write_trade_data(data)
            
    async def test_storage_manager_handles_read_errors(self, error_prone_storage_manager):
        """测试读取错误处理"""
        storage_manager = error_prone_storage_manager
        
        # 模拟读取错误
        storage_manager._clickhouse_client.fetch.side_effect = Exception("读取失败")
        
        with pytest.raises(Exception):
            await storage_manager.read_trade_data(
                exchange="binance",
                symbol="BTCUSDT",
                start_time=datetime.now(),
                end_time=datetime.now()
            )
            
    async def test_storage_manager_retry_mechanism(self, error_prone_storage_manager):
        """测试重试机制"""
        storage_manager = error_prone_storage_manager
        
        # 模拟第一次失败，第二次成功
        storage_manager._clickhouse_client.execute.side_effect = [
            Exception("临时失败"),
            None  # 成功
        ]
        
        data = [{"exchange": "binance", "symbol": "BTCUSDT", "price": 50000.0}]
        
        with patch.object(storage_manager, '_retry_write') as mock_retry:
            mock_retry.return_value = True
            
            await storage_manager.write_trade_data_with_retry(data)
            
            # 验证重试被调用
            mock_retry.assert_called_once()


@pytest.mark.integration
class TestUnifiedStorageManagerIntegration:
    """统一存储管理器集成测试"""
    
    async def test_storage_manager_full_lifecycle(self, mock_clickhouse_client, mock_redis_client):
        """测试存储管理器完整生命周期"""
        config = UnifiedStorageConfig(
            storage_type="hybrid",
            redis_enabled=True
        )
        
        storage_manager = UnifiedStorageManager(config)
        
        with patch('aiochclient.ChClient', return_value=mock_clickhouse_client):
            with patch('redis.asyncio.Redis', return_value=mock_redis_client):
                # 连接
                await storage_manager.connect()
                
                # 写入数据
                trade_data = [{"exchange": "binance", "symbol": "BTCUSDT", "price": 50000.0}]
                await storage_manager.write_trade_data(trade_data)
                
                # 读取数据
                mock_clickhouse_client.fetch.return_value = trade_data
                result = await storage_manager.read_trade_data(
                    exchange="binance",
                    symbol="BTCUSDT",
                    start_time=datetime.now(),
                    end_time=datetime.now()
                )
                
                assert result == trade_data
                
                # 断开连接
                await storage_manager.disconnect()
                
                # 验证完整流程
                mock_clickhouse_client.execute.assert_called()
                mock_clickhouse_client.fetch.assert_called()
                mock_clickhouse_client.close.assert_called()
