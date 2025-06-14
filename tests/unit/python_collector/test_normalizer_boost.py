"""
Normalizer覆盖率提升测试
专门测试未覆盖的代码路径，提升覆盖率从18%到40%+
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone
import sys
import os

sys.path.insert(0, os.path.join(os.getcwd(), 'services', 'python-collector', 'src'))

from marketprism_collector.normalizer import DataNormalizer
from marketprism_collector.data_types import PriceLevel, NormalizedTrade, NormalizedOrderBook


class TestNormalizerCoverageBoost:
    """数据标准化器覆盖率提升测试"""
    
    @pytest.fixture
    def normalizer(self):
        """数据标准化器实例"""
        return DataNormalizer()
    
    def test_symbol_format_normalization_comprehensive(self, normalizer):
        """测试交易对格式标准化 - 覆盖所有分支"""
        # 已经有连字符的格式
        assert normalizer._normalize_symbol_format("BTC-USDT") == "BTC-USDT"
        assert normalizer._normalize_symbol_format("eth-btc") == "ETH-BTC"
        
        # 常见交易对格式转换
        assert normalizer._normalize_symbol_format("BTCUSDT") == "BTC-USDT"
        assert normalizer._normalize_symbol_format("ETHUSDC") == "ETH-USDC"
        assert normalizer._normalize_symbol_format("BNBBTC") == "BNB-BTC"
        assert normalizer._normalize_symbol_format("ADAUSD") == "ADA-USD"
        assert normalizer._normalize_symbol_format("DOTEUR") == "DOT-EUR"
        assert normalizer._normalize_symbol_format("LINKGBP") == "LINK-GBP"
        assert normalizer._normalize_symbol_format("XRPJPY") == "XRP-JPY"
        
        # 无法识别的格式返回原始
        assert normalizer._normalize_symbol_format("UNKNOWN") == "UNKNOWN"
        assert normalizer._normalize_symbol_format("XYZ") == "XYZ"
        
        # 空基础货币处理
        assert normalizer._normalize_symbol_format("USDT") == "USDT"
    
    def test_enhanced_orderbook_from_snapshot(self, normalizer):
        """测试从快照创建增强订单簿"""
        bids = [
            PriceLevel(price=Decimal("50000"), quantity=Decimal("1.0")),
            PriceLevel(price=Decimal("49900"), quantity=Decimal("2.0"))
        ]
        asks = [
            PriceLevel(price=Decimal("50100"), quantity=Decimal("1.5")),
            PriceLevel(price=Decimal("50200"), quantity=Decimal("0.5"))
        ]
        
        # 带所有参数
        result = normalizer.normalize_enhanced_orderbook_from_snapshot(
            "binance", "BTCUSDT", bids, asks, 12345, 67890
        )
        
        assert result.exchange_name == "binance"
        assert result.symbol_name == "BTC-USDT"
        assert result.last_update_id == 12345
        assert result.checksum == 67890
        assert result.depth_levels == 4
        assert result.is_valid is True
        assert len(result.bids) == 2
        assert len(result.asks) == 2
        
        # 无可选参数
        result2 = normalizer.normalize_enhanced_orderbook_from_snapshot(
            "okx", "ETH-BTC", bids, asks
        )
        
        assert result2.exchange_name == "okx"
        assert result2.symbol_name == "ETH-BTC"
        assert result2.last_update_id is None
        assert result2.checksum is None
    
    def test_enhanced_orderbook_from_update(self, normalizer):
        """测试从增量更新创建增强订单簿"""
        bids = [PriceLevel(price=Decimal("50000"), quantity=Decimal("1.0"))]
        asks = [PriceLevel(price=Decimal("50100"), quantity=Decimal("1.0"))]
        
        bid_changes = [PriceLevel(price=Decimal("50000"), quantity=Decimal("1.0"))]
        ask_changes = [PriceLevel(price=Decimal("50100"), quantity=Decimal("1.0"))]
        removed_bids = [Decimal("49900")]
        removed_asks = [Decimal("50200")]
        
        result = normalizer.normalize_enhanced_orderbook_from_update(
            "binance", "BTCUSDT", bids, asks, 100, 200, 99,
            bid_changes, ask_changes, removed_bids, removed_asks
        )
        
        assert result.exchange_name == "binance"
        assert result.symbol_name == "BTC-USDT"
        assert result.first_update_id == 100
        assert result.last_update_id == 200
        assert result.prev_update_id == 99
        assert result.bid_changes == bid_changes
        assert result.ask_changes == ask_changes
        assert result.removed_bids == removed_bids
        assert result.removed_asks == removed_asks
        assert result.depth_levels == 2
    
    def test_create_orderbook_delta(self, normalizer):
        """测试创建订单簿增量变化"""
        bid_updates = [PriceLevel(price=Decimal("50000"), quantity=Decimal("1.0"))]
        ask_updates = [PriceLevel(price=Decimal("50100"), quantity=Decimal("1.0"))]
        
        result = normalizer.create_orderbook_delta(
            "binance", "BTCUSDT", 123, bid_updates, ask_updates, 122
        )
        
        assert result.exchange_name == "binance"
        assert result.symbol_name == "BTC-USDT"
        assert result.update_id == 123
        assert result.prev_update_id == 122
        assert result.bid_updates == bid_updates
        assert result.ask_updates == ask_updates
        assert result.total_bid_changes == 1
        assert result.total_ask_changes == 1
    
    def test_binance_depth_update_normalization_comprehensive(self, normalizer):
        """测试Binance深度更新标准化 - 全面测试"""
        # 正常数据
        raw_data = {
            "s": "BTCUSDT",
            "U": 100,
            "u": 200,
            "pu": 99,
            "b": [["50000", "1.0"], ["49900", "2.0"]],
            "a": [["50100", "1.5"], ["50200", "0.5"]]
        }
        
        result = normalizer.normalize_binance_depth_update(raw_data)
        
        assert result["exchange"] == "binance"
        assert result["symbol"] == "BTCUSDT"
        assert result["first_update_id"] == 100
        assert result["last_update_id"] == 200
        assert result["prev_update_id"] == 99
        assert len(result["bids"]) == 2
        assert len(result["asks"]) == 2
        assert result["bids"][0].price == Decimal("50000")
        assert result["bids"][0].quantity == Decimal("1.0")
        
        # 空数据测试
        empty_result = normalizer.normalize_binance_depth_update({})
        assert "exchange" in empty_result
        assert empty_result["exchange"] == "binance"
        
        # 缺少字段测试
        partial_data = {"s": "ETHUSDT"}
        partial_result = normalizer.normalize_binance_depth_update(partial_data)
        assert partial_result["symbol"] == "ETHUSDT"
        assert partial_result["exchange"] == "binance"
    
    def test_okx_depth_update_normalization_comprehensive(self, normalizer):
        """测试OKX深度更新标准化 - 全面测试"""
        # 正常数据
        raw_data = {
            "data": [{
                "instId": "BTC-USDT",
                "seqId": "123456",
                "prevSeqId": "123455",
                "ts": "1640995200000",
                "checksum": 12345,
                "bids": [["50000", "1.0", "0", "1"], ["49900", "2.0", "0", "2"]],
                "asks": [["50100", "1.5", "0", "1"], ["50200", "0.5", "0", "1"]]
            }]
        }
        
        result = normalizer.normalize_okx_depth_update(raw_data)
        
        assert result["exchange"] == "okx"
        assert result["symbol"] == "BTC-USDT"
        assert result["first_update_id"] == 123456
        assert result["last_update_id"] == 123456
        assert result["prev_update_id"] == 123455
        assert result["checksum"] == 12345
        assert len(result["bids"]) == 2
        assert len(result["asks"]) == 2
        
        # 空data测试
        empty_result = normalizer.normalize_okx_depth_update({"data": []})
        assert empty_result == {}
        
        # 无data字段测试
        no_data_result = normalizer.normalize_okx_depth_update({})
        assert no_data_result == {}
        
        # prevSeqId为None的情况
        raw_data_no_prev = {
            "data": [{
                "instId": "ETH-USDT",
                "seqId": "123456",
                "ts": "1640995200000",
                "bids": [["3000", "1.0", "0", "1"]],
                "asks": [["3100", "1.0", "0", "1"]]
            }]
        }
        
        result_no_prev = normalizer.normalize_okx_depth_update(raw_data_no_prev)
        assert result_no_prev["prev_update_id"] is None
    
    def test_error_handling_comprehensive(self, normalizer):
        """测试异常处理 - 全面覆盖"""
        # Binance异常数据
        invalid_binance_data = {
            "s": "BTCUSDT",
            "b": [["invalid_price", "1.0"]],  # 无效价格
            "a": [["50100", "invalid_qty"]]   # 无效数量
        }
        
        result = normalizer.normalize_binance_depth_update(invalid_binance_data)
        assert result == {}
        
        # OKX异常数据
        invalid_okx_data = {
            "data": [{
                "instId": "BTC-USDT",
                "seqId": "invalid_seq_id",  # 无效序列ID
                "bids": [["invalid", "data", "format"]],
                "asks": []
            }]
        }
        
        result = normalizer.normalize_okx_depth_update(invalid_okx_data)
        assert result == {}
    
    @pytest.mark.asyncio
    async def test_normalize_depth_update_unified(self, normalizer):
        """测试统一深度更新标准化方法"""
        # Binance数据
        binance_data = {
            "s": "BTCUSDT",
            "U": 100,
            "u": 200,
            "b": [["50000", "1.0"]],
            "a": [["50100", "1.0"]]
        }
        
        binance_result = await normalizer.normalize_depth_update(
            binance_data, "binance", "BTCUSDT"
        )
        
        # 验证binance结果
        assert binance_result is not None
        
        # OKX数据
        okx_data = {
            "data": [{
                "instId": "BTC-USDT",
                "seqId": "123456",
                "bids": [["50000", "1.0", "0", "1"]],
                "asks": [["50100", "1.0", "0", "1"]]
            }]
        }
        
        okx_result = await normalizer.normalize_depth_update(
            okx_data, "okx", "BTC-USDT"
        )
        
        # 验证okx结果
        assert okx_result is not None
        
        # 未知交易所
        unknown_result = await normalizer.normalize_depth_update(
            {}, "unknown_exchange", "BTCUSDT"
        )
        
        assert unknown_result is None


if __name__ == "__main__":
    pytest.main([__file__]) 