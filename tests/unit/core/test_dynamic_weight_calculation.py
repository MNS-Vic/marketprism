"""
MarketPrism 动态权重计算测试

验证权重计算的准确性，确保完全符合Binance官方文档：
1. "每个请求都有一个特定的权重"
2. "越消耗资源的接口, 比如查询多个交易对, 权重就会越大"
3. "每一个接口均有一个相应的权重(weight)，有的接口根据参数不同可能拥有不同的权重"
4. "连接到 WebSocket API 会用到2个权重"
"""

from datetime import datetime, timezone
import pytest
import sys
import os

# The following sys.path manipulation is legacy and has been removed.
#
# # 添加项目根目录到Python路径
# project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# sys.path.insert(0, project_root)

# 导入真实的DynamicWeightCalculator实现
try:
    from core.reliability.dynamic_weight_calculator import (
        DynamicWeightCalculator,
        calculate_request_weight,
        validate_request_parameters,
        get_weight_calculator
    )
except ImportError as e:
    pytest.skip(f"无法导入DynamicWeightCalculator: {e}")


class TestDynamicWeightCalculator:
    """动态权重计算器测试"""
    
    def setup_method(self):
        """设置测试"""
        self.calculator = DynamicWeightCalculator()
    
    def test_basic_weights(self):
        """测试基础权重 - 验证固定权重的API"""
        # 基础API权重（来自官方文档）
        assert self.calculator.calculate_weight("binance", "/api/v3/ping") == 1
        assert self.calculator.calculate_weight("binance", "/api/v3/time") == 1
        assert self.calculator.calculate_weight("binance", "/api/v3/exchangeInfo") == 10
        assert self.calculator.calculate_weight("binance", "/api/v3/order") == 1
        assert self.calculator.calculate_weight("binance", "/api/v3/account") == 10
        assert self.calculator.calculate_weight("binance", "/api/v3/historicalTrades") == 5
    
    def test_websocket_weights(self):
        """测试WebSocket权重 - 验证'连接到 WebSocket API 会用到2个权重'"""
        # WebSocket连接权重（官方文档明确规定）
        weight = self.calculator.calculate_weight("binance", "websocket_connection", {}, "websocket")
        assert weight == 2, "WebSocket连接应该是2权重"
        
        # 通过request_type参数指定
        weight = self.calculator.calculate_weight("binance", "any_endpoint", {}, "websocket")
        assert weight == 2
    
    def test_depth_parameter_weights(self):
        """测试深度API参数权重 - 验证'参数不同可能拥有不同的权重'"""
        # depth API limit参数测试（基于官方文档）
        assert self.calculator.calculate_weight("binance", "/api/v3/depth", {"limit": 50}) == 1
        assert self.calculator.calculate_weight("binance", "/api/v3/depth", {"limit": 100}) == 1
        assert self.calculator.calculate_weight("binance", "/api/v3/depth", {"limit": 200}) == 5
        assert self.calculator.calculate_weight("binance", "/api/v3/depth", {"limit": 500}) == 5
        assert self.calculator.calculate_weight("binance", "/api/v3/depth", {"limit": 1000}) == 10
        assert self.calculator.calculate_weight("binance", "/api/v3/depth", {"limit": 5000}) == 50
    
    def test_24hr_ticker_weights(self):
        """测试24hr ticker权重 - 验证'查询多个交易对, 权重就会越大'"""
        # 单个交易对
        weight = self.calculator.calculate_weight("binance", "/api/v3/ticker/24hr", {"symbol": "BTCUSDT"})
        assert weight == 1, "单个交易对应该是1权重"
        
        # 所有交易对（无symbol参数）
        weight = self.calculator.calculate_weight("binance", "/api/v3/ticker/24hr", {})
        assert weight == 40, "查询所有交易对应该是40权重"
        
        # 多个指定交易对（列表形式）
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        weight = self.calculator.calculate_weight("binance", "/api/v3/ticker/24hr", {"symbols": symbols})
        assert weight == 6, "3个交易对应该是6权重 (每个2权重)"
        
        # 多个指定交易对（字符串形式）
        weight = self.calculator.calculate_weight("binance", "/api/v3/ticker/24hr", {"symbols": "BTCUSDT,ETHUSDT"})
        assert weight == 4, "2个交易对应该是4权重"
    
    def test_price_ticker_weights(self):
        """测试价格ticker权重"""
        # 单个交易对
        weight = self.calculator.calculate_weight("binance", "/api/v3/ticker/price", {"symbol": "BTCUSDT"})
        assert weight == 1
        
        # 所有交易对
        weight = self.calculator.calculate_weight("binance", "/api/v3/ticker/price", {})
        assert weight == 2
        
        # 多个交易对
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        weight = self.calculator.calculate_weight("binance", "/api/v3/ticker/price", {"symbols": symbols})
        assert weight == 6  # 每个交易对2权重
    
    def test_open_orders_weights(self):
        """测试当前挂单权重"""
        # 单个交易对
        weight = self.calculator.calculate_weight("binance", "/api/v3/openOrders", {"symbol": "BTCUSDT"})
        assert weight == 3
        
        # 所有交易对
        weight = self.calculator.calculate_weight("binance", "/api/v3/openOrders", {})
        assert weight == 40, "查询所有交易对的挂单应该是40权重"
    
    def test_batch_operations(self):
        """测试批量操作权重"""
        # 批量订单权重测试
        orders = [{"symbol": f"BTC{i}USDT"} for i in range(5)]
        weight = self.calculator.calculate_weight("binance", "/api/v3/batchOrders", {"orders": orders})
        assert weight == 5, "5个订单应该是5权重"
        
        # 测试上限
        large_orders = [{"symbol": f"BTC{i}USDT"} for i in range(300)]
        weight = self.calculator.calculate_weight("binance", "/api/v3/batchOrders", {"orders": large_orders})
        assert weight == 200, "批量订单权重应该有上限200"
    
    def test_klines_weights(self):
        """测试K线数据权重"""
        # 小limit
        weight = self.calculator.calculate_weight("binance", "/api/v3/klines", {"limit": 100})
        assert weight == 1
        
        # 大limit
        weight = self.calculator.calculate_weight("binance", "/api/v3/klines", {"limit": 800})
        assert weight == 2
    
    def test_trades_weights(self):
        """测试交易记录权重"""
        # 小limit
        weight = self.calculator.calculate_weight("binance", "/api/v3/trades", {"limit": 100})
        assert weight == 1
        
        # 大limit
        weight = self.calculator.calculate_weight("binance", "/api/v3/trades", {"limit": 800})
        assert weight == 2
    
    def test_okx_weights(self):
        """测试OKX权重"""
        # 基础权重
        assert self.calculator.calculate_weight("okx", "/api/v5/public/instruments") == 1
        
        # ticker权重
        assert self.calculator.calculate_weight("okx", "/api/v5/market/ticker", {"instId": "BTC-USDT"}) == 1
        assert self.calculator.calculate_weight("okx", "/api/v5/market/ticker", {}) == 20
        
        # 深度权重
        assert self.calculator.calculate_weight("okx", "/api/v5/market/books", {"sz": "20"}) == 1
        assert self.calculator.calculate_weight("okx", "/api/v5/market/books", {"sz": "100"}) == 2
    
    def test_deribit_weights(self):
        """测试Deribit权重"""
        assert self.calculator.calculate_weight("deribit", "/api/v2/public/get_instruments") == 1
        assert self.calculator.calculate_weight("deribit", "/api/v2/public/get_order_book", {"depth": 20}) == 1
        assert self.calculator.calculate_weight("deribit", "/api/v2/public/get_order_book", {"depth": 100}) == 3
    
    def test_unknown_endpoint(self):
        """测试未知端点默认权重"""
        weight = self.calculator.calculate_weight("binance", "/api/v3/unknown_endpoint")
        assert weight == 1, "未知端点应该返回默认权重1"
        
        weight = self.calculator.calculate_weight("unknown_exchange", "/api/v3/ping")
        assert weight == 1, "未知交易所应该返回默认权重1"
    
    def test_parameter_validation(self):
        """测试参数验证和优化建议"""
        # 24hr ticker无symbol参数应该有警告
        validation = validate_request_parameters("binance", "/api/v3/ticker/24hr", {})
        assert validation["estimated_weight"] == 40
        assert len(validation["warnings"]) > 0
        assert "symbol" in validation["warnings"][0]
        
        # depth大limit应该有警告
        validation = validate_request_parameters("binance", "/api/v3/depth", {"limit": 5000})
        assert validation["estimated_weight"] == 50
        assert len(validation["warnings"]) > 0
        assert "limit" in validation["warnings"][0]
    
    def test_weight_calculation_edge_cases(self):
        """测试权重计算边界情况"""
        # None参数
        weight = self.calculator.calculate_weight("binance", "/api/v3/ping", None)
        assert weight == 1
        
        # 空参数字典
        weight = self.calculator.calculate_weight("binance", "/api/v3/ping", {})
        assert weight == 1
        
        # 无关参数（应该被忽略）
        weight = self.calculator.calculate_weight("binance", "/api/v3/ping", {"irrelevant": "value"})
        assert weight == 1
    
    def test_get_weight_info(self):
        """测试获取权重规则信息"""
        rule = self.calculator.get_weight_info("binance", "/api/v3/depth")
        assert rule is not None
        assert rule.base_weight == 1
        assert "limit" in rule.parameter_weights
        
        # 测试不存在的端点
        rule = self.calculator.get_weight_info("binance", "/api/v3/nonexistent")
        assert rule is None
    
    def test_list_endpoints(self):
        """测试列出端点"""
        binance_endpoints = self.calculator.list_endpoints("binance")
        assert len(binance_endpoints) > 0
        assert "/api/v3/ping" in binance_endpoints
        assert "/api/v3/ticker/24hr" in binance_endpoints
        
        okx_endpoints = self.calculator.list_endpoints("okx")
        assert len(okx_endpoints) > 0
        
        # 测试不存在的交易所
        unknown_endpoints = self.calculator.list_endpoints("unknown")
        assert unknown_endpoints == []
    
    def test_convenience_functions(self):
        """测试便利函数"""
        # 测试全局计算器
        calculator = get_weight_calculator()
        assert isinstance(calculator, DynamicWeightCalculator)
        
        # 测试便利函数
        weight = calculate_request_weight("binance", "/api/v3/ping")
        assert weight == 1
        
        validation = validate_request_parameters("binance", "/api/v3/ticker/24hr", {})
        assert validation["estimated_weight"] == 40
    
    def test_formula_calculations(self):
        """测试公式计算"""
        # 测试count * 1公式
        orders = [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}]
        weight = self.calculator.calculate_weight("binance", "/api/v3/batchOrders", {"orders": orders})
        assert weight == 2
        
        # 测试count * 2公式
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        weight = self.calculator.calculate_weight("binance", "/api/v3/ticker/24hr", {"symbols": symbols})
        assert weight == 6
    
    def test_special_rules_application(self):
        """测试特殊规则应用"""
        # 测试24hr ticker特殊规则
        weight = self.calculator.calculate_weight("binance", "/api/v3/ticker/24hr", {})
        assert weight == 40
        
        weight = self.calculator.calculate_weight("binance", "/api/v3/ticker/24hr", {"symbols": "BTC,ETH"})
        assert weight == 4
        
        # 测试openOrders特殊规则
        weight = self.calculator.calculate_weight("binance", "/api/v3/openOrders", {})
        assert weight == 40


class TestWeightCalculatorIntegration:
    """权重计算器集成测试"""
    
    def test_real_world_scenarios(self):
        """测试真实世界场景"""
        calculator = DynamicWeightCalculator()
        
        # 场景1：获取多个交易对的价格信息
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "DOTUSDT"]
        
        # 使用24hr ticker API
        weight_24hr = calculator.calculate_weight(
            "binance", "/api/v3/ticker/24hr", {"symbols": symbols}
        )
        
        # 使用price ticker API
        weight_price = calculator.calculate_weight(
            "binance", "/api/v3/ticker/price", {"symbols": symbols}
        )
        
        assert weight_24hr == 10  # 5个交易对 * 2权重
        assert weight_price == 10  # 5个交易对 * 2权重
        
        # 场景2：获取不同深度的订单簿
        for symbol in symbols:
            weight_small = calculator.calculate_weight(
                "binance", "/api/v3/depth", {"symbol": symbol, "limit": 100}
            )
            weight_large = calculator.calculate_weight(
                "binance", "/api/v3/depth", {"symbol": symbol, "limit": 1000}
            )
            
            assert weight_small == 1
            assert weight_large == 10
    
    def test_optimization_scenarios(self):
        """测试优化场景"""
        calculator = DynamicWeightCalculator()
        
        # 优化前：查询所有交易对的24hr数据
        weight_before = calculator.calculate_weight("binance", "/api/v3/ticker/24hr", {})
        
        # 优化后：只查询需要的交易对
        weight_after = calculator.calculate_weight(
            "binance", "/api/v3/ticker/24hr", {"symbol": "BTCUSDT"}
        )
        
        assert weight_before == 40
        assert weight_after == 1
        assert weight_before - weight_after == 39  # 节省了39个权重
    
    def test_error_handling(self):
        """测试错误处理"""
        calculator = DynamicWeightCalculator()
        
        # 测试各种错误输入不会崩溃
        try:
            calculator.calculate_weight("", "", {})
            calculator.calculate_weight(None, None, None)
            calculator.calculate_weight("binance", "/api/v3/depth", {"limit": "invalid"})
            calculator.calculate_weight("binance", "/api/v3/ticker/24hr", {"symbols": None})
        except Exception as e:
            pytest.fail(f"权重计算不应该因为错误输入而崩溃: {e}")


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])