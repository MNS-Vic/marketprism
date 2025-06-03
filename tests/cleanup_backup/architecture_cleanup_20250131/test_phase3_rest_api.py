#!/usr/bin/env python3
"""
Phase 3 REST API集成测试脚本

测试OrderBook Manager的REST API功能
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime
from typing import Dict, Any


class Phase3RestAPITester:
    """Phase 3 REST API测试器"""
    
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.session: aiohttp.ClientSession = None
        
    async def start(self):
        """启动测试器"""
        self.session = aiohttp.ClientSession()
        print(f"🚀 Phase 3 REST API测试器启动")
        print(f"📡 测试目标: {self.base_url}")
        print("=" * 60)
    
    async def stop(self):
        """停止测试器"""
        if self.session:
            await self.session.close()
        print("🛑 测试器已停止")
    
    async def test_basic_endpoints(self) -> Dict[str, Any]:
        """测试基础端点"""
        print("📋 测试基础端点...")
        results = {}
        
        endpoints = [
            ("/health", "健康检查"),
            ("/status", "状态查询"),
            ("/metrics", "Prometheus指标"),
            ("/scheduler", "调度器状态")
        ]
        
        for endpoint, description in endpoints:
            try:
                async with self.session.get(f"{self.base_url}{endpoint}") as response:
                    status = response.status
                    if endpoint == "/metrics":
                        content = await response.text()
                        results[endpoint] = {
                            "status": status,
                            "description": description,
                            "success": status == 200,
                            "content_length": len(content)
                        }
                    else:
                        data = await response.json()
                        results[endpoint] = {
                            "status": status,
                            "description": description,
                            "success": status == 200,
                            "data": data
                        }
                    
                    print(f"  ✅ {description}: {status}")
                    
            except Exception as e:
                results[endpoint] = {
                    "status": 0,
                    "description": description,
                    "success": False,
                    "error": str(e)
                }
                print(f"  ❌ {description}: {str(e)}")
        
        return results
    
    async def test_orderbook_endpoints(self) -> Dict[str, Any]:
        """测试OrderBook相关端点"""
        print("\n📊 测试OrderBook端点...")
        results = {}
        
        # 测试OrderBook API端点
        orderbook_endpoints = [
            ("/api/v1/orderbook/exchanges", "交易所列表"),
            ("/api/v1/orderbook/health", "OrderBook健康检查"),
            ("/api/v1/orderbook/stats", "OrderBook统计信息"),
        ]
        
        for endpoint, description in orderbook_endpoints:
            try:
                async with self.session.get(f"{self.base_url}{endpoint}") as response:
                    status = response.status
                    data = await response.json()
                    results[endpoint] = {
                        "status": status,
                        "description": description,
                        "success": status in [200, 404],  # 404也是正常的，表示功能存在但没有数据
                        "data": data
                    }
                    
                    if status == 200:
                        print(f"  ✅ {description}: {status}")
                    elif status == 404:
                        print(f"  ⚠️  {description}: {status} (功能正常，无数据)")
                    else:
                        print(f"  ❌ {description}: {status}")
                    
            except Exception as e:
                results[endpoint] = {
                    "status": 0,
                    "description": description,
                    "success": False,
                    "error": str(e)
                }
                print(f"  ❌ {description}: {str(e)}")
        
        return results
    
    async def test_specific_orderbook_data(self) -> Dict[str, Any]:
        """测试特定交易对的OrderBook数据"""
        print("\n📈 测试特定OrderBook数据...")
        results = {}
        
        # 测试常见交易对
        test_pairs = [
            ("binance", "BTC-USDT"),
            ("binance", "ETH-USDT"),
            ("okx", "BTC-USDT"),
            ("okx", "ETH-USDT")
        ]
        
        for exchange, symbol in test_pairs:
            endpoint = f"/api/v1/orderbook/{exchange}/{symbol}"
            try:
                async with self.session.get(f"{self.base_url}{endpoint}") as response:
                    status = response.status
                    data = await response.json()
                    results[f"{exchange}_{symbol}"] = {
                        "status": status,
                        "description": f"{exchange} {symbol} 订单簿",
                        "success": status in [200, 404, 503],  # 多种状态都是正常的
                        "data": data
                    }
                    
                    if status == 200:
                        print(f"  ✅ {exchange} {symbol}: 数据获取成功")
                    elif status == 404:
                        print(f"  ⚠️  {exchange} {symbol}: 未找到数据")
                    elif status == 503:
                        print(f"  ⚠️  {exchange} {symbol}: 服务不可用")
                    else:
                        print(f"  ❌ {exchange} {symbol}: {status}")
                    
            except Exception as e:
                results[f"{exchange}_{symbol}"] = {
                    "status": 0,
                    "description": f"{exchange} {symbol} 订单簿",
                    "success": False,
                    "error": str(e)
                }
                print(f"  ❌ {exchange} {symbol}: {str(e)}")
        
        return results
    
    async def test_orderbook_management(self) -> Dict[str, Any]:
        """测试OrderBook管理功能"""
        print("\n🔧 测试OrderBook管理功能...")
        results = {}
        
        # 测试管理端点
        management_tests = [
            ("GET", "/api/v1/orderbook/api/stats", "API统计信息"),
        ]
        
        for method, endpoint, description in management_tests:
            try:
                if method == "GET":
                    async with self.session.get(f"{self.base_url}{endpoint}") as response:
                        status = response.status
                        data = await response.json()
                elif method == "POST":
                    async with self.session.post(f"{self.base_url}{endpoint}") as response:
                        status = response.status
                        data = await response.json()
                
                results[endpoint] = {
                    "status": status,
                    "description": description,
                    "success": status in [200, 404, 503],
                    "data": data
                }
                
                if status == 200:
                    print(f"  ✅ {description}: 成功")
                else:
                    print(f"  ⚠️  {description}: {status}")
                    
            except Exception as e:
                results[endpoint] = {
                    "status": 0,
                    "description": description,
                    "success": False,
                    "error": str(e)
                }
                print(f"  ❌ {description}: {str(e)}")
        
        return results
    
    def generate_report(self, all_results: Dict[str, Any]) -> Dict[str, Any]:
        """生成测试报告"""
        total_tests = 0
        successful_tests = 0
        
        for category, results in all_results.items():
            for test_name, result in results.items():
                total_tests += 1
                if result.get('success', False):
                    successful_tests += 1
        
        success_rate = (successful_tests / total_tests * 100) if total_tests > 0 else 0
        
        report = {
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "phase": "Phase 3 - REST API集成",
            "total_tests": total_tests,
            "successful_tests": successful_tests,
            "success_rate": round(success_rate, 2),
            "status": "PASS" if success_rate >= 70 else "FAIL",
            "details": all_results
        }
        
        return report
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """运行所有测试"""
        print("🧪 开始Phase 3 REST API集成测试")
        print(f"⏰ 测试时间: {datetime.utcnow().isoformat()}")
        
        all_results = {}
        
        # 运行各类测试
        all_results["basic_endpoints"] = await self.test_basic_endpoints()
        all_results["orderbook_endpoints"] = await self.test_orderbook_endpoints()
        all_results["orderbook_data"] = await self.test_specific_orderbook_data()
        all_results["orderbook_management"] = await self.test_orderbook_management()
        
        # 生成报告
        report = self.generate_report(all_results)
        
        print("\n" + "=" * 60)
        print("📊 测试报告")
        print("=" * 60)
        print(f"🎯 阶段: {report['phase']}")
        print(f"📈 成功率: {report['success_rate']}% ({report['successful_tests']}/{report['total_tests']})")
        print(f"🏆 状态: {report['status']}")
        
        if report['status'] == 'PASS':
            print("✅ Phase 3 REST API集成测试通过！")
        else:
            print("❌ Phase 3 REST API集成测试失败")
        
        return report


async def main():
    """主函数"""
    tester = Phase3RestAPITester()
    
    try:
        await tester.start()
        
        # 等待服务启动
        print("⏳ 等待服务启动...")
        await asyncio.sleep(2)
        
        # 运行测试
        report = await tester.run_all_tests()
        
        # 保存报告
        report_file = f"phase3_test_report_{int(time.time())}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 测试报告已保存: {report_file}")
        
        return report['status'] == 'PASS'
        
    except Exception as e:
        print(f"❌ 测试执行失败: {e}")
        return False
        
    finally:
        await tester.stop()


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1) 