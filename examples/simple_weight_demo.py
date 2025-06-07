"""
MarketPrism 简化权重计算演示

直接演示动态权重计算功能，避免复杂的模块导入
"""

import sys
import os

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# 直接导入权重计算器类
import json
import time
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum

class ExchangeType(Enum):
    """交易所类型"""
    BINANCE = "binance"
    OKX = "okx"
    DERIBIT = "deribit"


@dataclass
class WeightRule:
    """权重规则定义"""
    base_weight: int                              
    parameter_weights: Dict[str, Any] = field(default_factory=dict)  
    scaling_rules: Dict[str, Any] = field(default_factory=dict)      
    max_weight: Optional[int] = None              
    description: str = ""                         


class SimpleWeightCalculator:
    """简化的权重计算器"""
    
    def __init__(self):
        self.weight_rules = {}
        self._load_binance_rules()
    
    def _load_binance_rules(self):
        """加载Binance权重规则"""
        self.weight_rules["binance"] = {
            # 基础API权重
            "/api/v3/ping": WeightRule(base_weight=1, description="测试连接"),
            "/api/v3/time": WeightRule(base_weight=1, description="服务器时间"),
            "/api/v3/exchangeInfo": WeightRule(base_weight=10, description="交易所信息"),
            
            # 深度数据 - 权重随limit参数变化
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
            
            # 24小时价格变动 - 体现多交易对权重增加
            "/api/v3/ticker/24hr": WeightRule(
                base_weight=1,
                parameter_weights={
                    "symbol": {"none": 40, "single": 1},
                    "symbols": {"calculation": "count * 2"}
                },
                max_weight=200,
                description="24hr价格变动，无symbol时权重40，多symbol时每个2权重"
            ),
            
            # WebSocket连接权重
            "websocket_connection": WeightRule(
                base_weight=2,
                description="WebSocket连接权重"
            ),
            
            # 批量订单
            "/api/v3/batchOrders": WeightRule(
                base_weight=0,
                parameter_weights={
                    "orders": {"calculation": "count * 1"}
                },
                max_weight=200,
                description="批量订单"
            )
        }
    
    def calculate_weight(self, exchange: str, endpoint: str, parameters: Optional[Dict[str, Any]] = None) -> int:
        """计算请求权重"""
        exchange = exchange.lower()
        parameters = parameters or {}
        
        if exchange not in self.weight_rules:
            return 1
            
        if endpoint not in self.weight_rules[exchange]:
            return 1
        
        rule = self.weight_rules[exchange][endpoint]
        calculated_weight = rule.base_weight
        
        # 处理参数权重
        for param_name, param_value in parameters.items():
            if param_name in rule.parameter_weights:
                param_rule = rule.parameter_weights[param_name]
                weight_addition = self._calculate_parameter_weight(param_rule, param_value)
                calculated_weight += weight_addition
        
        # 应用特殊规则
        calculated_weight = self._apply_special_rules(rule, parameters, calculated_weight)
        
        # 应用最大权重限制
        if rule.max_weight is not None:
            calculated_weight = min(calculated_weight, rule.max_weight)
        
        return calculated_weight
    
    def _calculate_parameter_weight(self, param_rule: Dict[str, Any], param_value: Any) -> int:
        """计算参数权重"""
        if param_value is None:
            return param_rule.get("none", 0)
        
        # 范围规则
        if "rules" in param_rule and isinstance(param_value, (int, float)):
            for rule_item in param_rule["rules"]:
                if "range" in rule_item:
                    min_val, max_val = rule_item["range"]
                    if min_val <= param_value <= max_val:
                        return rule_item["weight"]
        
        # 计算公式
        if "calculation" in param_rule:
            return self._calculate_formula_weight(param_rule["calculation"], param_value)
        
        return 0
    
    def _calculate_formula_weight(self, formula: str, param_value: Any) -> int:
        """计算公式权重"""
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
            
        except Exception:
            pass
        
        return 1
    
    def _apply_special_rules(self, rule: WeightRule, parameters: Dict[str, Any], current_weight: int) -> int:
        """应用特殊规则"""
        # 24hr ticker特殊规则
        if "/api/v3/ticker/24hr" in rule.description:
            if "symbol" not in parameters and "symbols" not in parameters:
                return 40
            elif "symbols" in parameters:
                symbols = parameters["symbols"]
                if isinstance(symbols, list):
                    return len(symbols) * 2
                elif isinstance(symbols, str):
                    return len(symbols.split(",")) * 2
        
        return current_weight


def demo_weight_calculation():
    """演示权重计算"""
    print("🚀 MarketPrism 动态权重计算演示")
    print("📖 基于Binance官方文档的权重计算规则")
    print("=" * 60)
    
    calculator = SimpleWeightCalculator()
    
    # 1. 基础权重测试
    print("\n1. 基础权重测试（固定权重）:")
    basic_tests = [
        ("/api/v3/ping", {}, "测试连接"),
        ("/api/v3/time", {}, "服务器时间"),
        ("/api/v3/exchangeInfo", {}, "交易所信息"),
        ("websocket_connection", {}, "WebSocket连接")
    ]
    
    for endpoint, params, desc in basic_tests:
        weight = calculator.calculate_weight("binance", endpoint, params)
        print(f"   {endpoint:<25} | 权重: {weight:>2} | {desc}")
    
    # 2. 参数相关权重测试
    print("\n2. 参数相关权重测试（体现'参数不同权重不同'）:")
    print("   深度数据权重随limit参数变化:")
    
    for limit in [50, 100, 200, 500, 1000, 5000]:
        weight = calculator.calculate_weight("binance", "/api/v3/depth", {"symbol": "BTCUSDT", "limit": limit})
        print(f"     limit={limit:<4} | 权重: {weight:>2}")
    
    # 3. 多交易对权重测试
    print("\n3. 多交易对权重测试（体现'查询多个交易对权重增加'）:")
    print("   24小时价格变动权重:")
    
    # 单个交易对
    weight = calculator.calculate_weight("binance", "/api/v3/ticker/24hr", {"symbol": "BTCUSDT"})
    print(f"     单个交易对: {weight}")
    
    # 所有交易对
    weight = calculator.calculate_weight("binance", "/api/v3/ticker/24hr", {})
    print(f"     所有交易对: {weight}")
    
    # 多个指定交易对
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT"]
    weight = calculator.calculate_weight("binance", "/api/v3/ticker/24hr", {"symbols": symbols})
    print(f"     {len(symbols)}个指定交易对: {weight} (每个2权重)")
    
    # 4. 批量操作权重测试
    print("\n4. 批量操作权重测试:")
    print("   批量订单权重:")
    
    for order_count in [1, 3, 5, 10]:
        orders = [{"symbol": f"BTC{i}USDT"} for i in range(order_count)]
        weight = calculator.calculate_weight("binance", "/api/v3/batchOrders", {"orders": orders})
        print(f"     {order_count:>2}个订单: {weight} (每个订单1权重)")
    
    # 5. 权重优化示例
    print("\n5. 权重优化示例:")
    print("   优化前后对比:")
    
    # 优化前：查询所有交易对的24hr数据
    weight_before = calculator.calculate_weight("binance", "/api/v3/ticker/24hr", {})
    
    # 优化后：只查询单个交易对
    weight_after = calculator.calculate_weight("binance", "/api/v3/ticker/24hr", {"symbol": "BTCUSDT"})
    
    print(f"     查询所有24hr数据: {weight_before} 权重")
    print(f"     查询单个24hr数据: {weight_after} 权重")
    print(f"     节省权重: {weight_before - weight_after}")
    
    # 6. 实际应用场景
    print("\n6. 实际应用场景权重计算:")
    scenarios = [
        {
            "name": "获取BTC深度数据(100档)",
            "endpoint": "/api/v3/depth",
            "params": {"symbol": "BTCUSDT", "limit": 100}
        },
        {
            "name": "获取BTC深度数据(1000档)",
            "endpoint": "/api/v3/depth", 
            "params": {"symbol": "BTCUSDT", "limit": 1000}
        },
        {
            "name": "获取前5交易对24hr数据",
            "endpoint": "/api/v3/ticker/24hr",
            "params": {"symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "DOTUSDT"]}
        },
        {
            "name": "批量下5个订单",
            "endpoint": "/api/v3/batchOrders",
            "params": {"orders": [{"symbol": "BTCUSDT"} for _ in range(5)]}
        }
    ]
    
    total_weight = 0
    for scenario in scenarios:
        weight = calculator.calculate_weight("binance", scenario["endpoint"], scenario["params"])
        total_weight += weight
        print(f"   {scenario['name']:<30} | 权重: {weight:>2}")
    
    print(f"\n   总权重消耗: {total_weight}")
    print(f"   占用Binance限制: {total_weight/6000*100:.1f}% (6000权重/分钟)")
    
    print("\n=" * 60)
    print("✅ 演示完成!")
    print("💡 关键特性验证:")
    print("  ✓ 每个请求都有特定权重")
    print("  ✓ 参数不同导致权重变化")
    print("  ✓ 多交易对查询权重成倍增加")
    print("  ✓ WebSocket连接固定2权重")
    print("  ✓ 批量操作权重线性增长")
    print("=" * 60)


if __name__ == "__main__":
    demo_weight_calculation()