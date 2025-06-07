"""
MarketPrism 动态权重计算演示

完整展示Binance官方文档中的各种权重计算场景：
1. "每个请求都有一个特定的权重"
2. "越消耗资源的接口, 比如查询多个交易对, 权重就会越大"
3. "每一个接口均有一个相应的权重(weight)，有的接口根据参数不同可能拥有不同的权重"
4. "连接到 WebSocket API 会用到2个权重"

演示内容：
- 基础权重vs动态权重
- 参数如何影响权重
- 多交易对查询的权重计算
- WebSocket连接权重
- 批量操作权重
- 权重优化建议
"""

import asyncio
import sys
import os
import time
from typing import Dict, Any, List

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from core.reliability.dynamic_weight_calculator import (
    DynamicWeightCalculator,
    calculate_request_weight,
    validate_request_parameters
)
from core.reliability.enhanced_ip_rate_limit_coordinator import (
    create_enhanced_ip_coordinator,
    ExchangeType,
    RequestType
)


class WeightDemoRunner:
    """权重演示运行器"""
    
    def __init__(self):
        self.calculator = DynamicWeightCalculator()
        self.coordinator = None
    
    async def setup_coordinator(self):
        """设置协调器"""
        self.coordinator = await create_enhanced_ip_coordinator(
            primary_ip="192.168.1.100",
            backup_ips=["192.168.1.101", "192.168.1.102"]
        )
    
    def demo_basic_weights(self):
        """演示基础权重"""
        print("=" * 60)
        print("1. 基础权重演示 - 固定权重的API")
        print("=" * 60)
        
        basic_endpoints = [
            ("/api/v3/ping", "测试连接"),
            ("/api/v3/time", "服务器时间"),
            ("/api/v3/exchangeInfo", "交易所信息"),
            ("/api/v3/order", "订单操作"),
            ("/api/v3/account", "账户信息"),
            ("websocket_connection", "WebSocket连接")
        ]
        
        for endpoint, description in basic_endpoints:
            weight = self.calculator.calculate_weight("binance", endpoint)
            print(f"  {endpoint:<25} | 权重: {weight:>2} | {description}")
        
        print()
    
    def demo_parameter_weights(self):
        """演示参数相关权重"""
        print("=" * 60)
        print("2. 参数相关权重演示 - 体现'参数不同可能拥有不同的权重'")
        print("=" * 60)
        
        # depth API权重测试
        print("深度数据 (/api/v3/depth) - limit参数影响权重:")
        depth_limits = [50, 100, 200, 500, 1000, 5000]
        for limit in depth_limits:
            weight = self.calculator.calculate_weight(
                "binance", "/api/v3/depth", {"symbol": "BTCUSDT", "limit": limit}
            )
            print(f"  limit={limit:<4} | 权重: {weight:>2}")
        
        print()
        
        # klines API权重测试
        print("K线数据 (/api/v3/klines) - limit参数影响权重:")
        kline_limits = [100, 300, 500, 800, 1000]
        for limit in kline_limits:
            weight = self.calculator.calculate_weight(
                "binance", "/api/v3/klines", 
                {"symbol": "BTCUSDT", "interval": "1h", "limit": limit}
            )
            print(f"  limit={limit:<4} | 权重: {weight:>2}")
        
        print()
    
    def demo_multi_symbol_weights(self):
        """演示多交易对权重 - 体现'查询多个交易对, 权重就会越大'"""
        print("=" * 60)
        print("3. 多交易对权重演示 - 体现'查询多个交易对, 权重就会越大'")
        print("=" * 60)
        
        # 24hr ticker权重测试
        print("24小时价格变动 (/api/v3/ticker/24hr):")
        
        # 单个交易对
        weight_single = self.calculator.calculate_weight(
            "binance", "/api/v3/ticker/24hr", {"symbol": "BTCUSDT"}
        )
        print(f"  单个交易对 (BTCUSDT)     | 权重: {weight_single:>2}")
        
        # 所有交易对
        weight_all = self.calculator.calculate_weight(
            "binance", "/api/v3/ticker/24hr", {}
        )
        print(f"  所有交易对 (无symbol参数) | 权重: {weight_all:>2}")
        
        # 多个指定交易对
        multi_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "DOTUSDT"]
        weight_multi = self.calculator.calculate_weight(
            "binance", "/api/v3/ticker/24hr", {"symbols": multi_symbols}
        )
        print(f"  {len(multi_symbols)}个指定交易对             | 权重: {weight_multi:>2} (每个交易对2权重)")
        
        print()
        
        # 价格ticker权重测试
        print("当前价格 (/api/v3/ticker/price):")
        
        weight_single = self.calculator.calculate_weight(
            "binance", "/api/v3/ticker/price", {"symbol": "BTCUSDT"}
        )
        print(f"  单个交易对               | 权重: {weight_single:>2}")
        
        weight_all = self.calculator.calculate_weight(
            "binance", "/api/v3/ticker/price", {}
        )
        print(f"  所有交易对               | 权重: {weight_all:>2}")
        
        weight_multi = self.calculator.calculate_weight(
            "binance", "/api/v3/ticker/price", {"symbols": multi_symbols}
        )
        print(f"  {len(multi_symbols)}个指定交易对             | 权重: {weight_multi:>2}")
        
        print()
    
    def demo_batch_operations(self):
        """演示批量操作权重"""
        print("=" * 60)
        print("4. 批量操作权重演示 - 权重随操作数量线性增长")
        print("=" * 60)
        
        # 模拟不同数量的批量订单
        print("批量订单 (/api/v3/batchOrders):")
        for order_count in [1, 3, 5, 10, 20]:
            orders = [{"symbol": f"BTC{i}USDT", "side": "BUY"} for i in range(order_count)]
            weight = self.calculator.calculate_weight(
                "binance", "/api/v3/batchOrders", {"orders": orders}
            )
            print(f"  {order_count:>2}个订单 | 权重: {weight:>2} (每个订单1权重)")
        
        print()
    
    def demo_websocket_weights(self):
        """演示WebSocket权重 - 体现'连接到 WebSocket API 会用到2个权重'"""
        print("=" * 60)
        print("5. WebSocket权重演示 - 体现'连接到 WebSocket API 会用到2个权重'")
        print("=" * 60)
        
        # WebSocket连接权重
        weight = self.calculator.calculate_weight(
            "binance", "websocket_connection", {}, "websocket"
        )
        print(f"  WebSocket连接            | 权重: {weight:>2} (官方文档明确规定)")
        
        # 模拟多个WebSocket连接
        for connection_count in [1, 2, 3, 5]:
            total_weight = weight * connection_count
            print(f"  {connection_count}个WebSocket连接        | 总权重: {total_weight:>2}")
        
        print()
    
    def demo_optimization_suggestions(self):
        """演示权重优化建议"""
        print("=" * 60)
        print("6. 权重优化建议演示 - 如何降低API权重消耗")
        print("=" * 60)
        
        optimization_cases = [
            {
                "name": "24hr ticker - 未指定symbol",
                "endpoint": "/api/v3/ticker/24hr",
                "parameters": {},
                "better_alternative": {"symbol": "BTCUSDT"}
            },
            {
                "name": "深度数据 - 过大的limit",
                "endpoint": "/api/v3/depth",
                "parameters": {"symbol": "BTCUSDT", "limit": 5000},
                "better_alternative": {"symbol": "BTCUSDT", "limit": 100}
            },
            {
                "name": "当前挂单 - 查询所有交易对",
                "endpoint": "/api/v3/openOrders",
                "parameters": {},
                "better_alternative": {"symbol": "BTCUSDT"}
            }
        ]
        
        for case in optimization_cases:
            # 计算原始权重
            original_weight = self.calculator.calculate_weight(
                "binance", case["endpoint"], case["parameters"]
            )
            
            # 验证并获取建议
            validation = validate_request_parameters(
                "binance", case["endpoint"], case["parameters"]
            )
            
            # 计算优化后的权重
            optimized_weight = self.calculator.calculate_weight(
                "binance", case["endpoint"], case["better_alternative"]
            )
            
            print(f"案例: {case['name']}")
            print(f"  原始权重: {original_weight:>2}")
            print(f"  优化权重: {optimized_weight:>2}")
            print(f"  节省权重: {original_weight - optimized_weight:>2}")
            
            if validation["warnings"]:
                print(f"  系统建议: {validation['warnings'][0]}")
            
            print()
    
    async def demo_real_time_coordination(self):
        """演示实时协调系统"""
        print("=" * 60)
        print("7. 实时权重协调演示 - IP级别权重管理")
        print("=" * 60)
        
        if not self.coordinator:
            await self.setup_coordinator()
        
        # 模拟各种权重的请求
        test_requests = [
            ("轻量请求", "/api/v3/ping", {}),
            ("中等请求", "/api/v3/depth", {"symbol": "BTCUSDT", "limit": 100}),
            ("重量请求", "/api/v3/ticker/24hr", {}),  # 权重40
            ("批量请求", "/api/v3/batchOrders", {
                "orders": [{"symbol": f"BTC{i}USDT"} for i in range(5)]
            })
        ]
        
        print("实时请求处理:")
        total_weight_used = 0
        
        for name, endpoint, params in test_requests:
            result = await self.coordinator.acquire_smart_permit(
                ExchangeType.BINANCE,
                endpoint,
                params
            )
            
            status = "✓" if result["granted"] else "✗"
            weight = result["calculated_weight"]
            total_weight_used += weight if result["granted"] else 0
            
            print(f"  {name:<12} | 状态: {status} | 权重: {weight:>2} | IP: {result['ip_address']}")
            
            if result["optimization_suggestions"]:
                print(f"    💡 建议: {result['optimization_suggestions'][0]}")
        
        print(f"\n  总消费权重: {total_weight_used}")
        
        # 显示系统状态
        status = await self.coordinator.get_enhanced_system_status()
        weight_stats = status["coordinator_info"]["weight_statistics"]
        
        print(f"  平均请求权重: {weight_stats['average_request_weight']:.2f}")
        print(f"  高权重请求: {weight_stats['high_weight_requests']}")
        
        # 显示权重优化报告
        optimization_report = await self.coordinator.get_weight_optimization_report()
        
        if optimization_report.get("optimization_tips"):
            print("\n  优化建议:")
            for tip in optimization_report["optimization_tips"]:
                print(f"    • {tip}")
        
        print()
    
    def demo_other_exchanges(self):
        """演示其他交易所的权重"""
        print("=" * 60)
        print("8. 其他交易所权重演示 - OKX, Deribit")
        print("=" * 60)
        
        # OKX权重测试
        print("OKX交易所:")
        okx_tests = [
            ("/api/v5/market/ticker", {"instId": "BTC-USDT"}, "单个ticker"),
            ("/api/v5/market/ticker", {}, "所有ticker"),
            ("/api/v5/market/books", {"instId": "BTC-USDT", "sz": "20"}, "深度数据(小)"),
            ("/api/v5/market/books", {"instId": "BTC-USDT", "sz": "100"}, "深度数据(大)"),
        ]
        
        for endpoint, params, description in okx_tests:
            weight = self.calculator.calculate_weight("okx", endpoint, params)
            print(f"  {description:<15} | 权重: {weight:>2}")
        
        print()
        
        # Deribit权重测试
        print("Deribit交易所:")
        deribit_tests = [
            ("/api/v2/public/get_instruments", {}, "获取交易工具"),
            ("/api/v2/public/get_order_book", {"instrument_name": "BTC-PERPETUAL", "depth": 20}, "订单簿(小)"),
            ("/api/v2/public/get_order_book", {"instrument_name": "BTC-PERPETUAL", "depth": 100}, "订单簿(大)"),
        ]
        
        for endpoint, params, description in deribit_tests:
            weight = self.calculator.calculate_weight("deribit", endpoint, params)
            print(f"  {description:<15} | 权重: {weight:>2}")
        
        print()
    
    async def run_complete_demo(self):
        """运行完整演示"""
        print("🚀 MarketPrism 动态权重计算系统演示")
        print("📖 完全基于Binance官方文档的权重计算规则")
        print("🎯 展示'每个请求的权重根据参数动态变化'的特性\n")
        
        # 基础演示（不需要协调器）
        self.demo_basic_weights()
        self.demo_parameter_weights()
        self.demo_multi_symbol_weights()
        self.demo_batch_operations()
        self.demo_websocket_weights()
        self.demo_optimization_suggestions()
        self.demo_other_exchanges()
        
        # 高级演示（需要协调器）
        await self.demo_real_time_coordination()
        
        print("=" * 60)
        print("✅ 演示完成!")
        print("💡 关键收获:")
        print("  1. 权重根据参数动态计算(如limit, symbol数量)")
        print("  2. 多交易对查询权重成倍增加")
        print("  3. WebSocket连接固定2权重")
        print("  4. 系统自动提供优化建议")
        print("  5. IP级别实时权重监控")
        print("=" * 60)


async def main():
    """主函数"""
    demo_runner = WeightDemoRunner()
    await demo_runner.run_complete_demo()


if __name__ == "__main__":
    asyncio.run(main())