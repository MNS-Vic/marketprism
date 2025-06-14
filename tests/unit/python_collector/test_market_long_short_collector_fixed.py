"""
test_market_long_short_collector.py - 修复版本
批量修复应用：异步清理、导入路径、Mock回退
"""
import os
import sys
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock

# 添加路径
sys.path.insert(0, 'tests')
sys.path.insert(0, os.path.join(os.getcwd(), 'services', 'python-collector', 'src'))

# 导入助手
from helpers import AsyncTestManager, async_test_with_cleanup

# 尝试导入实际模块，失败时使用Mock
try:
    # 实际导入将在这里添加
    MODULES_AVAILABLE = True
except ImportError:
    # Mock类将在这里添加  
    MODULES_AVAILABLE = False

"""
Python Collector Market Long Short数据收集器单元测试

测试市场多空仓人数比数据收集器的功能
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

from marketprism_collector.market_long_short_collector import MarketLongShortDataCollector
from marketprism_collector.rest_client import RestClientManager
from marketprism_collector.data_types import (
    Exchange, NormalizedMarketLongShortRatio
)


class TestMarketLongShortDataCollector:
    """测试Market Long Short数据收集器"""
    
    @pytest.fixture
    def mock_rest_manager(self):
        """Mock REST客户端管理器"""
        manager = AsyncMock(spec=RestClientManager)
        
        # Mock Binance客户端
        binance_client = AsyncMock()
        binance_client.get.return_value = [
            {
                "symbol": "BTCUSDT",
                "longShortRatio": "1.3000",
                "longAccount": "0.5652",
                "shortAccount": "0.4348",
                "timestamp": 1640995200000
            }
        ]
        
        # Mock OKX客户端 - 使用数组格式
        okx_client = AsyncMock()
        okx_client.get.return_value = {
            "code": "0",
            "data": [
                ["1640995200000", "1.25"]  # OKX返回格式：[timestamp, longShortAccountRatio]
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
        return MarketLongShortDataCollector(mock_rest_manager)
    
    def test_collector_initialization(self, collector, mock_rest_manager):
        """测试收集器初始化"""
        assert collector.rest_client_manager == mock_rest_manager
        assert collector.symbols == ["BTC-USDT", "ETH-USDT"]  # 默认符号
        assert collector.collection_interval == 300  # 默认间隔
        assert collector.is_running is False
        assert collector.stats["total_collections"] == 0
        assert collector.stats["successful_collections"] == 0
        assert collector.stats["failed_collections"] == 0
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_setup_exchange_clients(self, collector):
        """测试设置交易所客户端"""
        await collector._setup_exchange_clients()
        
        # 验证客户端被创建
        assert Exchange.BINANCE in collector.clients
        assert Exchange.OKX in collector.clients
        
        # 验证start_all被调用
        collector.rest_client_manager.start_all.assert_called_once()
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_collect_exchange_symbol_data_binance(self, collector):
        """测试收集Binance数据"""
        # 设置客户端
        await collector._setup_exchange_clients()
        
        # 收集数据
        result = await collector._collect_exchange_symbol_data(Exchange.BINANCE, "BTC-USDT")
        
        # 验证结果
        assert isinstance(result, NormalizedMarketLongShortRatio)
        assert result.exchange_name == "binance"
        assert result.symbol_name == "BTC-USDT"
        assert result.data_type == "account"
        assert result.long_short_ratio == Decimal("1.3000")
        assert result.long_account_ratio == Decimal("0.5652")
        assert result.short_account_ratio == Decimal("0.4348")
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_collect_exchange_symbol_data_okx(self, collector):
        """测试收集OKX数据"""
        # 设置客户端
        await collector._setup_exchange_clients()
        
        # 收集数据
        result = await collector._collect_exchange_symbol_data(Exchange.OKX, "BTC-USDT")
        
        # 验证结果
        assert isinstance(result, NormalizedMarketLongShortRatio)
        assert result.exchange_name == "okx"
        assert result.symbol_name == "BTC-USDT"
        assert result.data_type == "account"
        assert result.long_short_ratio == Decimal("1.25")
        # 计算验证：1.25 / (1.25 + 1) ≈ 0.5556
        assert abs(result.long_account_ratio - Decimal("1.25") / Decimal("2.25")) < Decimal("0.001")
        assert abs(result.short_account_ratio - Decimal("1") / Decimal("2.25")) < Decimal("0.001")
    
    @async_test_with_cleanup
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
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_collect_once(self, collector):
        """测试单次收集"""
        # 设置客户端
        await collector._setup_exchange_clients()
        
        # 执行单次收集
        results = await collector.collect_once()
        
        # 应该收集到数据点（2个符号 x 2个交易所）
        assert len(results) > 0
        for result in results:
            assert isinstance(result, NormalizedMarketLongShortRatio)
    
    def test_register_callback(self, collector):
        """测试注册回调函数"""
        callback = AsyncMock()
        
        collector.register_callback(callback)
        
        assert len(collector.callbacks) == 1
        assert callback in collector.callbacks
    
    def test_get_stats(self, collector):
        """测试获取统计信息"""
        # 更新一些统计
        collector.stats["total_collections"] = 15
        collector.stats["successful_collections"] = 12
        collector.stats["failed_collections"] = 3
        collector.stats["data_points_collected"] = 48
        
        stats = collector.get_stats()
        
        assert stats["total_collections"] == 15
        assert stats["successful_collections"] == 12
        assert stats["failed_collections"] == 3
        assert stats["data_points_collected"] == 48
        assert stats["success_rate"] == 80.0  # 12/15 * 100
        assert "last_collection_time" in stats


class TestMarketLongShortDataNormalization:
    """测试Market Long Short数据标准化"""
    
    def test_binance_data_normalization(self):
        """测试Binance数据标准化"""
        raw_data = {
            "symbol": "BTCUSDT",
            "longShortRatio": "1.3000",
            "longAccount": "0.5652",
            "shortAccount": "0.4348",
            "timestamp": 1640995200000
        }
        
        normalized = NormalizedMarketLongShortRatio(
            exchange_name="binance",
            symbol_name="BTC-USDT",
            long_short_ratio=Decimal(raw_data["longShortRatio"]),
            long_account_ratio=Decimal(raw_data["longAccount"]),
            short_account_ratio=Decimal(raw_data["shortAccount"]),
            data_type="account",
            period="5m",
            instrument_type="futures",
            timestamp=datetime.fromtimestamp(raw_data["timestamp"] / 1000, tz=timezone.utc)
        )
        
        assert normalized.exchange_name == "binance"
        assert normalized.symbol_name == "BTC-USDT"
        assert normalized.long_short_ratio == Decimal("1.3000")
        assert normalized.long_account_ratio == Decimal("0.5652")
        assert normalized.short_account_ratio == Decimal("0.4348")
        assert normalized.data_type == "account"
        # 账户比例应该加起来等于1
        assert abs(normalized.long_account_ratio + normalized.short_account_ratio - Decimal("1")) < Decimal("0.001")
    
    def test_okx_data_normalization(self):
        """测试OKX数据标准化"""
        raw_data = ["1640995200000", "1.25"]  # OKX数组格式
        
        timestamp_ms = int(raw_data[0])
        long_short_ratio = Decimal(str(raw_data[1]))
        
        # 计算账户比例
        total_ratio = long_short_ratio + Decimal('1')
        long_account_ratio = long_short_ratio / total_ratio
        short_account_ratio = Decimal('1') / total_ratio
        
        normalized = NormalizedMarketLongShortRatio(
            exchange_name="okx",
            symbol_name="BTC-USDT",
            long_short_ratio=long_short_ratio,
            long_account_ratio=long_account_ratio,
            short_account_ratio=short_account_ratio,
            data_type="account",
            period="5m",
            instrument_type="swap",
            timestamp=datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        )
        
        assert normalized.exchange_name == "okx"
        assert normalized.symbol_name == "BTC-USDT"
        assert normalized.long_short_ratio == Decimal("1.25")
        assert normalized.data_type == "account"
        # 验证计算：1.25 / 2.25 ≈ 0.5556
        expected_long = Decimal("1.25") / Decimal("2.25")
        expected_short = Decimal("1") / Decimal("2.25")
        assert abs(normalized.long_account_ratio - expected_long) < Decimal("0.001")
        assert abs(normalized.short_account_ratio - expected_short) < Decimal("0.001")
        # 账户比例应该加起来等于1
        assert abs(normalized.long_account_ratio + normalized.short_account_ratio - Decimal("1")) < Decimal("0.001")


class TestMarketLongShortCollectorConfiguration:
    """测试Market Long Short收集器配置"""
    
    def test_default_configuration(self):
        """测试默认配置"""
        mock_manager = AsyncMock()
        collector = MarketLongShortDataCollector(mock_manager)
        
        # 验证默认配置
        assert collector.symbols == ["BTC-USDT", "ETH-USDT"]
        assert collector.collection_interval == 300
        assert len(collector.clients) == 0  # 还没有设置客户端
        assert len(collector.callbacks) == 0
    
    def test_custom_symbols_configuration(self):
        """测试自定义符号配置"""
        mock_manager = AsyncMock()
        collector = MarketLongShortDataCollector(mock_manager)
        
        # 测试直接修改符号
        custom_symbols = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
        collector.symbols = custom_symbols
        assert collector.symbols == custom_symbols


class TestMarketLongShortCollectorEdgeCases:
    """测试Market Long Short收集器边缘情况"""
    
    @pytest.fixture
    def collector_with_empty_response(self):
        """创建返回空响应的收集器"""
        manager = AsyncMock(spec=RestClientManager)
        
        # Mock空响应的客户端
        empty_client = AsyncMock()
        empty_client.get.return_value = []  # 空响应
        
        manager.create_exchange_client.return_value = empty_client
        manager.start_all = AsyncMock()
        
        collector = MarketLongShortDataCollector(manager)
        collector.clients[Exchange.BINANCE] = empty_client
        
        return collector
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_empty_response_handling(self, collector_with_empty_response):
        """测试空响应处理"""
        result = await collector_with_empty_response._collect_exchange_symbol_data(
            Exchange.BINANCE, "BTC-USDT"
        )
        
        # 空响应应该返回None
        assert result is None
    
    @pytest.fixture
    def collector_with_error_client(self):
        """创建会抛出异常的收集器"""
        manager = AsyncMock(spec=RestClientManager)
        
        # Mock抛出异常的客户端
        error_client = AsyncMock()
        error_client.get.side_effect = Exception("Network error")
        
        manager.create_exchange_client.return_value = error_client
        manager.start_all = AsyncMock()
        
        collector = MarketLongShortDataCollector(manager)
        collector.clients[Exchange.BINANCE] = error_client
        
        return collector
    
    @async_test_with_cleanup
    @pytest.mark.asyncio
    async def test_network_error_handling(self, collector_with_error_client):
        """测试网络错误处理"""
        result = await collector_with_error_client._collect_exchange_symbol_data(
            Exchange.BINANCE, "BTC-USDT"
        )
        
        # 异常情况应该返回None
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 