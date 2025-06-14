"""
MarketPrism 动态权重计算器

完全实现Binance官方文档中的权重计算规则：
1. "每个请求都有一个特定的权重，它会添加到您的访问限制中"
2. "越消耗资源的接口, 比如查询多个交易对, 权重就会越大"
3. "每一个接口均有一个相应的权重(weight)，有的接口根据参数不同可能拥有不同的权重"
4. "连接到 WebSocket API 会用到2个权重"

支持的权重计算场景：
- 基础端点权重
- 参数相关的动态权重
- 数据量相关的权重计算
- WebSocket连接权重
- 批量操作权重
"""

from datetime import datetime, timezone
import re
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ExchangeType(Enum):
    """交易所类型"""
    BINANCE = "binance"
    OKX = "okx"
    DERIBIT = "deribit"


class RequestType(Enum):
    """请求类型"""
    REST_API = "rest_api"
    WEBSOCKET = "websocket"
    ORDER = "order"
    MARKET_DATA = "market_data"


@dataclass
class WeightRule:
    """权重规则定义"""
    base_weight: int                              # 基础权重
    parameter_weights: Dict[str, Any] = field(default_factory=dict)  # 参数相关权重
    scaling_rules: Dict[str, Any] = field(default_factory=dict)      # 缩放规则
    max_weight: Optional[int] = None              # 最大权重限制
    description: str = ""                         # 规则描述


class DynamicWeightCalculator:
    """动态权重计算器"""
    
    def __init__(self):
        """初始化权重计算器，加载所有交易所的权重规则"""
        self.weight_rules: Dict[str, Dict[str, WeightRule]] = {}
        self._load_binance_weight_rules()
        self._load_okx_weight_rules()
        self._load_deribit_weight_rules()
    
    def _load_binance_weight_rules(self):
        """加载Binance的权重规则（基于官方文档）"""
        self.weight_rules["binance"] = {
            # 基础API权重
            "/api/v3/ping": WeightRule(
                base_weight=1,
                description="测试连接"
            ),
            
            "/api/v3/time": WeightRule(
                base_weight=1,
                description="服务器时间"
            ),
            
            "/api/v3/exchangeInfo": WeightRule(
                base_weight=10,
                description="交易所信息"
            ),
            
            # 市场数据权重（基于参数动态计算）
            "/api/v3/depth": WeightRule(
                base_weight=1,
                parameter_weights={
                    "limit": {
                        "rules": [
                            {"range": [1, 100], "weight": 1},
                            {"range": [101, 500], "weight": 5},
                            {"range": [501, 1000], "weight": 10},
                            {"range": [1001, 5000], "weight": 50}
                        ]
                    }
                },
                description="深度信息，权重取决于limit参数"
            ),
            
            "/api/v3/trades": WeightRule(
                base_weight=1,
                parameter_weights={
                    "limit": {
                        "rules": [
                            {"range": [1, 500], "weight": 1},
                            {"range": [501, 1000], "weight": 2}
                        ]
                    }
                },
                description="最近成交记录"
            ),
            
            "/api/v3/historicalTrades": WeightRule(
                base_weight=5,
                description="历史成交记录"
            ),
            
            "/api/v3/aggTrades": WeightRule(
                base_weight=1,
                parameter_weights={
                    "limit": {
                        "rules": [
                            {"range": [1, 500], "weight": 1},
                            {"range": [501, 1000], "weight": 2}
                        ]
                    }
                },
                description="聚合交易列表"
            ),
            
            "/api/v3/klines": WeightRule(
                base_weight=1,
                parameter_weights={
                    "limit": {
                        "rules": [
                            {"range": [1, 500], "weight": 1},
                            {"range": [501, 1000], "weight": 2}
                        ]
                    }
                },
                description="K线数据"
            ),
            
            # 24小时价格变动统计（动态权重）
            "/api/v3/ticker/24hr": WeightRule(
                base_weight=1,
                parameter_weights={
                    "symbol": {
                        "none": 40,  # 不提供symbol时查询所有交易对
                        "single": 1  # 单个交易对
                    },
                    "symbols": {
                        "calculation": "count * 2"  # 多个交易对时的计算方式
                    }
                },
                max_weight=200,  # 官方限制
                description="24hr价格变动，无symbol时权重40，多symbol时每个2权重"
            ),
            
            "/api/v3/ticker/price": WeightRule(
                base_weight=1,
                parameter_weights={
                    "symbol": {
                        "none": 2,   # 所有交易对
                        "single": 1  # 单个交易对
                    },
                    "symbols": {
                        "calculation": "count * 2"
                    }
                },
                description="当前价格"
            ),
            
            "/api/v3/ticker/bookTicker": WeightRule(
                base_weight=1,
                parameter_weights={
                    "symbol": {
                        "none": 2,   # 所有交易对
                        "single": 1  # 单个交易对
                    },
                    "symbols": {
                        "calculation": "count * 2"
                    }
                },
                description="最佳挂单价格"
            ),
            
            # 订单相关权重
            "/api/v3/order": WeightRule(
                base_weight=1,
                description="下单、查询、取消订单"
            ),
            
            "/api/v3/openOrders": WeightRule(
                base_weight=3,
                parameter_weights={
                    "symbol": {
                        "none": 40,  # 查询所有交易对的挂单
                        "single": 3  # 单个交易对
                    }
                },
                description="当前挂单"
            ),
            
            "/api/v3/allOrders": WeightRule(
                base_weight=10,
                parameter_weights={
                    "limit": {
                        "rules": [
                            {"range": [1, 500], "weight": 10},
                            {"range": [501, 1000], "weight": 20}
                        ]
                    }
                },
                description="所有订单历史"
            ),
            
            # 账户信息
            "/api/v3/account": WeightRule(
                base_weight=10,
                description="账户信息"
            ),
            
            "/api/v3/myTrades": WeightRule(
                base_weight=10,
                parameter_weights={
                    "limit": {
                        "rules": [
                            {"range": [1, 500], "weight": 10},
                            {"range": [501, 1000], "weight": 20}
                        ]
                    }
                },
                description="账户成交历史"
            ),
            
            # WebSocket连接权重
            "websocket_connection": WeightRule(
                base_weight=2,
                description="WebSocket连接权重"
            ),
            
            # 批量操作
            "/api/v3/batchOrders": WeightRule(
                base_weight=0,
                parameter_weights={
                    "orders": {
                        "calculation": "count * 1"  # 每个订单1权重
                    }
                },
                max_weight=200,  # 批量限制
                description="批量订单"
            )
        }
    
    def _load_okx_weight_rules(self):
        """加载OKX的权重规则"""
        self.weight_rules["okx"] = {
            "/api/v5/public/instruments": WeightRule(
                base_weight=1,
                description="获取交易产品基础信息"
            ),
            
            "/api/v5/market/ticker": WeightRule(
                base_weight=1,
                parameter_weights={
                    "instId": {
                        "none": 20,  # 查询所有产品
                        "single": 1  # 单个产品
                    }
                },
                description="获取Ticker数据"
            ),
            
            "/api/v5/market/books": WeightRule(
                base_weight=1,
                parameter_weights={
                    "sz": {
                        "rules": [
                            {"range": [1, 20], "weight": 1},
                            {"range": [21, 100], "weight": 2}
                        ]
                    }
                },
                description="获取深度数据"
            ),
            
            "/api/v5/trade/order": WeightRule(
                base_weight=1,
                description="下单"
            ),
            
            "/api/v5/trade/batch-orders": WeightRule(
                base_weight=0,
                parameter_weights={
                    "orders": {
                        "calculation": "count * 1"
                    }
                },
                max_weight=20,
                description="批量下单"
            )
        }
    
    def _load_deribit_weight_rules(self):
        """加载Deribit的权重规则"""
        self.weight_rules["deribit"] = {
            "/api/v2/public/get_instruments": WeightRule(
                base_weight=1,
                description="获取交易工具"
            ),
            
            "/api/v2/public/get_order_book": WeightRule(
                base_weight=1,
                parameter_weights={
                    "depth": {
                        "rules": [
                            {"range": [1, 20], "weight": 1},
                            {"range": [21, 100], "weight": 3}
                        ]
                    }
                },
                description="获取订单簿"
            ),
            
            "/api/v2/private/buy": WeightRule(
                base_weight=1,
                description="买入订单"
            ),
            
            "/api/v2/private/sell": WeightRule(
                base_weight=1,
                description="卖出订单"
            )
        }
    
    def calculate_weight(
        self, 
        exchange: str, 
        endpoint: str, 
        parameters: Optional[Dict[str, Any]] = None,
        request_type: str = "rest_api"
    ) -> int:
        """根据交易所、端点和参数计算请求权重"""
        # 处理None值
        if exchange is None:
            logger.warning("交易所参数为None，使用默认权重1")
            return 1
            
        exchange = exchange.lower()
        parameters = parameters or {}
        
        # 获取权重规则
        if exchange not in self.weight_rules:
            logger.warning(f"未知交易所: {exchange}, 使用默认权重1")
            return 1
        
        # 特殊处理WebSocket连接
        if request_type == "websocket" or endpoint == "websocket_connection":
            if "websocket_connection" in self.weight_rules[exchange]:
                return self.weight_rules[exchange]["websocket_connection"].base_weight
            return 2  # Binance默认WebSocket权重
        
        # 查找端点规则
        if endpoint not in self.weight_rules[exchange]:
            logger.debug(f"端点 {endpoint} 无特定权重规则，使用默认权重1")
            return 1
        
        rule = self.weight_rules[exchange][endpoint]
        
        # 处理特殊权重规则（如 ticker/24hr 无参数时的40权重）
        special_weight = self._apply_special_rules(rule, parameters)
        if special_weight is not None:
            return min(special_weight, rule.max_weight or special_weight)
        
        # 计算参数权重
        calculated_weight = rule.base_weight
        
        if parameters:
            for param_name, param_value in parameters.items():
                if param_name in rule.parameter_weights:
                    param_weight = self._calculate_parameter_weight(rule.parameter_weights[param_name], param_value)
                    calculated_weight = param_weight  # 参数权重替换基础权重
                    break  # 只使用第一个匹配的参数权重

        # 应用最大权重限制
        if rule.max_weight is not None:
            calculated_weight = min(calculated_weight, rule.max_weight)
        
        logger.debug(f"权重计算: {exchange} {endpoint} = {calculated_weight}")
        return calculated_weight
    
    def _calculate_parameter_weight(self, param_rule: Dict[str, Any], param_value: Any) -> int:
        """计算单个参数的权重贡献"""
        if param_value is None:
            # 参数为空的情况
            return param_rule.get("none", 0)
        
        # 如果有范围规则（针对数值参数）
        if "rules" in param_rule:
            # 尝试将字符串转换为数值
            numeric_value = param_value
            if isinstance(param_value, str) and param_value.isdigit():
                numeric_value = int(param_value)
            elif isinstance(param_value, str):
                try:
                    numeric_value = float(param_value)
                except ValueError:
                    pass
            
            if isinstance(numeric_value, (int, float)):
                for rule_item in param_rule["rules"]:
                    if "range" in rule_item:
                        min_val, max_val = rule_item["range"]
                        if min_val <= numeric_value <= max_val:
                            return rule_item["weight"]
        
        # 如果是单个值（有symbol参数）
        if param_value is not None and "single" in param_rule:
            return param_rule["single"]
        
        # 如果有计算公式（symbols列表或字符串）
        if "calculation" in param_rule:
            return self._calculate_formula_weight(param_rule["calculation"], param_value)
        
        # 默认返回0
        return 0
    
    def _calculate_formula_weight(self, formula: str, param_value: Any) -> int:
        """计算基于公式的权重"""
        try:
            if isinstance(param_value, list):
                count = len(param_value)
            elif isinstance(param_value, str) and "," in param_value:
                count = len(param_value.split(","))
            else:
                count = 1
            
            if formula == "count * 1":
                return count
            elif formula == "count * 2":
                return count * 2
            elif "count" in formula:
                # 解析更复杂的公式
                formula = formula.replace("count", str(count))
                return int(eval(formula))
            
        except Exception as e:
            logger.error(f"公式计算错误: {formula}, 参数: {param_value}, 错误: {e}")
        
        return 1
    
    def _apply_special_rules(self, rule: WeightRule, parameters: Dict[str, Any]) -> Optional[int]:
        """应用特殊计算规则，返回None表示使用常规计算"""
        if not parameters:
            # 如果没有提供参数，检查是否有 "none" 规则
            for param_name, param_rule in rule.parameter_weights.items():
                if "none" in param_rule:
                    return param_rule["none"]
        return None
    
    def get_weight_info(self, exchange: str, endpoint: str) -> Optional[WeightRule]:
        """获取端点的权重规则信息"""
        exchange = exchange.lower()
        
        if exchange in self.weight_rules and endpoint in self.weight_rules[exchange]:
            return self.weight_rules[exchange][endpoint]
        
        return None
    
    def list_endpoints(self, exchange: str) -> List[str]:
        """列出指定交易所的所有端点"""
        exchange = exchange.lower()
        
        if exchange in self.weight_rules:
            return list(self.weight_rules[exchange].keys())
        
        return []
    
    def validate_parameters(self, exchange: str, endpoint: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """验证参数并给出权重建议"""
        rule = self.get_weight_info(exchange, endpoint)
        if not rule:
            return {"valid": True, "warnings": [], "estimated_weight": 1}
        
        warnings = []
        estimated_weight = self.calculate_weight(exchange, endpoint, parameters)
        
        # 检查是否可能触发高权重
        if estimated_weight > 50:
            warnings.append(f"高权重请求 ({estimated_weight})，建议优化参数")
        
        # 检查参数建议
        if endpoint == "/api/v3/ticker/24hr" and "symbol" not in parameters:
            warnings.append("建议指定symbol参数以降低权重 (从40降到1)")
        
        if endpoint == "/api/v3/depth" and parameters.get("limit", 100) > 100:
            warnings.append("limit > 100 会增加权重，考虑分批获取")
        
        return {
            "valid": True,
            "warnings": warnings,
            "estimated_weight": estimated_weight,
            "max_weight": rule.max_weight
        }


# 全局实例
_global_weight_calculator: Optional[DynamicWeightCalculator] = None


def get_weight_calculator() -> DynamicWeightCalculator:
    """获取全局权重计算器实例"""
    global _global_weight_calculator
    if _global_weight_calculator is None:
        _global_weight_calculator = DynamicWeightCalculator()
    return _global_weight_calculator


# 便利函数
def calculate_request_weight(
    exchange: str, 
    endpoint: str, 
    parameters: Optional[Dict[str, Any]] = None,
    request_type: str = "rest_api"
) -> int:
    """便利函数：计算请求权重"""
    calculator = get_weight_calculator()
    return calculator.calculate_weight(exchange, endpoint, parameters, request_type)


def validate_request_parameters(exchange: str, endpoint: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """便利函数：验证请求参数"""
    calculator = get_weight_calculator()
    return calculator.validate_parameters(exchange, endpoint, parameters)


if __name__ == "__main__":
    # 演示权重计算的各种场景
    def demo_weight_calculation():
        print("=== MarketPrism 动态权重计算演示 ===\n")
        
        calculator = DynamicWeightCalculator()
        
        # 测试场景1：基础权重
        print("1. 基础权重测试:")
        weight = calculator.calculate_weight("binance", "/api/v3/ping")
        print(f"   /api/v3/ping: {weight} (应该是1)")
        
        weight = calculator.calculate_weight("binance", "/api/v3/exchangeInfo")
        print(f"   /api/v3/exchangeInfo: {weight} (应该是10)")
        
        # 测试场景2：参数相关权重
        print("\n2. 参数相关权重测试:")
        
        # depth权重测试
        weight = calculator.calculate_weight("binance", "/api/v3/depth", {"limit": 50})
        print(f"   /api/v3/depth (limit=50): {weight} (应该是1)")
        
        weight = calculator.calculate_weight("binance", "/api/v3/depth", {"limit": 200})
        print(f"   /api/v3/depth (limit=200): {weight} (应该是5)")
        
        weight = calculator.calculate_weight("binance", "/api/v3/depth", {"limit": 1000})
        print(f"   /api/v3/depth (limit=1000): {weight} (应该是10)")
        
        # 测试场景3：24hr ticker权重
        print("\n3. 24hr ticker权重测试:")
        
        weight = calculator.calculate_weight("binance", "/api/v3/ticker/24hr", {"symbol": "BTCUSDT"})
        print(f"   单个交易对: {weight} (应该是1)")
        
        weight = calculator.calculate_weight("binance", "/api/v3/ticker/24hr", {})
        print(f"   所有交易对: {weight} (应该是40)")
        
        weight = calculator.calculate_weight("binance", "/api/v3/ticker/24hr", {"symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT"]})
        print(f"   多个交易对 (3个): {weight} (应该是6)")
        
        # 测试场景4：WebSocket权重
        print("\n4. WebSocket权重测试:")
        
        weight = calculator.calculate_weight("binance", "websocket_connection", {}, "websocket")
        print(f"   WebSocket连接: {weight} (应该是2)")
        
        # 测试场景5：批量操作权重
        print("\n5. 批量操作权重测试:")
        
        orders = [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}, {"symbol": "BNBUSDT"}]
        weight = calculator.calculate_weight("binance", "/api/v3/batchOrders", {"orders": orders})
        print(f"   批量订单 (3个): {weight} (应该是3)")
        
        # 测试场景6：参数验证
        print("\n6. 参数验证测试:")
        
        validation = calculator.validate_parameters("binance", "/api/v3/ticker/24hr", {})
        print(f"   24hr ticker无参数: 警告={validation['warnings']}, 权重={validation['estimated_weight']}")
        
        validation = calculator.validate_parameters("binance", "/api/v3/depth", {"limit": 5000})
        print(f"   depth大limit: 警告={validation['warnings']}, 权重={validation['estimated_weight']}")
        
        # 测试场景7：其他交易所
        print("\n7. 其他交易所权重测试:")
        
        weight = calculator.calculate_weight("okx", "/api/v5/market/ticker", {"instId": "BTC-USDT"})
        print(f"   OKX单个ticker: {weight}")
        
        weight = calculator.calculate_weight("okx", "/api/v5/market/ticker", {})
        print(f"   OKX所有ticker: {weight}")
        
        print("\n=== 演示完成 ===")
    
    # 运行演示
    demo_weight_calculation()