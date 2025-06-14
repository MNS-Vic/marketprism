"""
Python Collector Top Trader数据收集器单元测试

测试大户持仓比数据收集器的功能
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from decimal import Decimal

# 导入被测试的模块
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../services/python-collector/src'))

from marketprism_collector.top_trader_collector import TopTraderDataCollector
from marketprism_collector.rest_client import RestClientManager
from marketprism_collector.data_types import (
    Exchange, NormalizedTopTraderLongShortRatio
)


class TestTopTraderDataCollector:
    """测试Top Trader数据收集器"""
    
    @pytest.fixture
    def mock_rest_manager(self):
        """Mock REST客户端管理器"""
        manager = AsyncMock(spec=RestClientManager)
        
        # Mock Binance客户端
        binance_client = AsyncMock()
        binance_client.get.return_value = [
            {
                "symbol": "BTCUSDT", 
                "longShortRatio": "1.2500",
                "longAccount": "0.6250", 
                "shortAccount": "0.3750",
                "timestamp": 1640995200000
            }
        ]
        
        # Mock OKX客户端
        okx_client = AsyncMock()
        okx_client.get.return_value = {
            "code": "0",
            "data": [
                ["1640995200000", "1.15"]  # OKX实际返回格式是数组：[timestamp, longShortPosRatio]
            ]
        }
        
        # Mock客户端获取
        manager.get_client.side_effect = lambda name: {
            "binance_rest": binance_client,
            "okx_rest": okx_client
        }.get(name)
        
        # Mock创建客户端
        manager.create_exchange_client.side_effect = lambda exchange, config: {
            Exchange.BINANCE: binance_client,
            Exchange.OKX: okx_client
        }[exchange]
        
        # Mock启动
        manager.start_all = AsyncMock()
        
        return manager
    
    @pytest.fixture
    def collector(self, mock_rest_manager):
        """创建收集器实例"""
        return TopTraderDataCollector(mock_rest_manager)
    
    def test_collector_initialization(self, collector, mock_rest_manager):
        """测试收集器初始化"""
        assert collector.rest_client_manager == mock_rest_manager
        assert collector.symbols == ["BTC-USDT", "ETH-USDT", "BNB-USDT"]  # 默认符号
        assert collector.collection_interval == 300  # 默认间隔
        assert collector.is_running is False
        assert collector.stats["total_collections"] == 0
        assert collector.stats["successful_collections"] == 0
        assert collector.stats["failed_collections"] == 0
    
    @pytest.mark.asyncio
    async def test_setup_exchange_clients(self, collector):
        """测试设置交易所客户端"""
        await collector._setup_exchange_clients()
        
        # 验证客户端被创建
        assert Exchange.BINANCE in collector.clients
        assert Exchange.OKX in collector.clients
        
        # 验证start_all被调用
        collector.rest_client_manager.start_all.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_collect_exchange_symbol_data_binance(self, collector):
        """测试收集Binance数据"""
        # 设置客户端
        await collector._setup_exchange_clients()
        
        # 收集数据
        result = await collector._collect_exchange_symbol_data(Exchange.BINANCE, "BTC-USDT")
        
        # 验证结果
        assert isinstance(result, NormalizedTopTraderLongShortRatio)
        assert result.exchange_name == "binance"
        assert result.symbol_name == "BTC-USDT"
    
    @pytest.mark.asyncio
    async def test_collect_exchange_symbol_data_okx(self, collector):
        """测试收集OKX数据"""
        # 设置客户端
        await collector._setup_exchange_clients()
        
        # 收集数据
        result = await collector._collect_exchange_symbol_data(Exchange.OKX, "BTC-USDT")
        
        # 验证结果
        assert isinstance(result, NormalizedTopTraderLongShortRatio)
        assert result.exchange_name == "okx"
        assert result.symbol_name == "BTC-USDT"
    
    @pytest.mark.asyncio
    async def test_start_and_stop_collector(self, collector):
        """测试启动和停止收集器"""
        # Mock收集循环以避免无限循环
        collector._collection_loop = AsyncMock()
        
        # 启动收集器
        await collector.start(["BTC-USDT", "ETH-USDT"])
        assert collector.is_running is True
        assert collector.symbols == ["BTC-USDT", "ETH-USDT"]
        
        # 停止收集器
        await collector.stop()
        assert collector.is_running is False
    
    @pytest.mark.asyncio
    async def test_collect_once(self, collector):
        """测试单次收集"""
        # 设置客户端
        await collector._setup_exchange_clients()
        
        # 执行单次收集
        results = await collector.collect_once()
        
        # 应该收集到数据点（3个符号 x 2个交易所）
        assert len(results) > 0
        for result in results:
            assert isinstance(result, NormalizedTopTraderLongShortRatio)
    
    def test_register_callback(self, collector):
        """测试注册回调函数"""
        callback = AsyncMock()
        
        collector.register_callback(callback)
        
        assert len(collector.callbacks) == 1
        assert callback in collector.callbacks
    
    def test_get_stats(self, collector):
        """测试获取统计信息"""
        # 更新一些统计
        collector.stats["total_collections"] = 10
        collector.stats["successful_collections"] = 8
        collector.stats["failed_collections"] = 2
        collector.stats["data_points_collected"] = 48
        
        stats = collector.get_stats()
        
        assert stats["total_collections"] == 10
        assert stats["successful_collections"] == 8
        assert stats["failed_collections"] == 2
        assert stats["data_points_collected"] == 48
        assert "last_collection_time" in stats


class TestTopTraderDataNormalization:
    """测试Top Trader数据标准化"""
    
    def test_binance_data_normalization(self):
        """测试Binance数据标准化"""
        raw_data = {
            "symbol": "BTCUSDT",
            "longShortRatio": "1.2500", 
            "longAccount": "0.6250",
            "shortAccount": "0.3750",
            "timestamp": 1640995200000
        }
        
        # Binance大户数据主要关注账户比例，但我们需要推算持仓比例
        # 从longShortRatio可以推算持仓比例
        total_ratio = Decimal("1") + Decimal(raw_data["longShortRatio"])
        long_pos_ratio = Decimal(raw_data["longShortRatio"]) / total_ratio
        short_pos_ratio = Decimal("1") / total_ratio
        
        normalized = NormalizedTopTraderLongShortRatio(
            exchange_name="binance",
            symbol_name="BTC-USDT",  # 转换后的格式
            long_short_ratio=Decimal(raw_data["longShortRatio"]),
            long_position_ratio=long_pos_ratio,
            short_position_ratio=short_pos_ratio,
            long_account_ratio=Decimal(raw_data["longAccount"]),
            short_account_ratio=Decimal(raw_data["shortAccount"]),
            timestamp=datetime.fromtimestamp(raw_data["timestamp"] / 1000, tz=timezone.utc)
        )
        
        assert normalized.exchange_name == "binance"
        assert normalized.symbol_name == "BTC-USDT"
        assert normalized.long_short_ratio == Decimal("1.2500")
        assert normalized.long_account_ratio == Decimal("0.6250")
        assert normalized.short_account_ratio == Decimal("0.3750")
        assert normalized.long_position_ratio + normalized.short_position_ratio == Decimal("1")
    
    def test_okx_data_normalization(self):
        """测试OKX数据标准化"""
        raw_data = {
            "instId": "BTC-USDT-SWAP",
            "ratio": "1.15",
            "longRatio": "0.535", 
            "shortRatio": "0.465",
            "ts": "1640995200000"
        }
        
        normalized = NormalizedTopTraderLongShortRatio(
            exchange_name="okx",
            symbol_name="BTC-USDT",  # 转换后的格式
            long_short_ratio=Decimal(raw_data["ratio"]),
            long_position_ratio=Decimal(raw_data["longRatio"]),
            short_position_ratio=Decimal(raw_data["shortRatio"]),
            timestamp=datetime.fromtimestamp(int(raw_data["ts"]) / 1000, tz=timezone.utc)
        )
        
        assert normalized.exchange_name == "okx"
        assert normalized.symbol_name == "BTC-USDT" 
        assert normalized.long_short_ratio == Decimal("1.15")
        assert normalized.long_position_ratio == Decimal("0.535")
        assert normalized.short_position_ratio == Decimal("0.465")
        # OKX直接提供持仓比例，应该加起来等于1
        assert abs(normalized.long_position_ratio + normalized.short_position_ratio - Decimal("1")) < Decimal("0.001")


class TestTopTraderCollectorConfiguration:
    """测试Top Trader收集器配置"""
    
    def test_default_configuration(self):
        """测试默认配置"""
        mock_manager = AsyncMock()
        collector = TopTraderDataCollector(mock_manager)
        
        # 验证默认配置
        assert collector.symbols == ["BTC-USDT", "ETH-USDT", "BNB-USDT"]
        assert collector.collection_interval == 300
        assert len(collector.clients) == 0  # 还没有设置客户端
        assert len(collector.callbacks) == 0
    
    def test_custom_symbols_configuration(self):
        """测试自定义符号配置"""
        mock_manager = AsyncMock()
        collector = TopTraderDataCollector(mock_manager)
        
        # 通过start方法设置自定义符号
        custom_symbols = ["BTC-USDT", "ETH-USDT"]
        
        # 验证符号可以通过start方法改变
        assert hasattr(collector, 'start')  # 验证方法存在
        
        # 测试直接修改符号
        collector.symbols = custom_symbols
        assert collector.symbols == custom_symbols


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 