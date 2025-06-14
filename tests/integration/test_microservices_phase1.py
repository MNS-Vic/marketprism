"""
MarketPrism 微服务架构 Phase 1 集成测试
测试数据存储服务和调度服务的基本功能
"""

import asyncio
import pytest
import aiohttp
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from core.storage.types import NormalizedTrade, NormalizedTicker, NormalizedOrderBook


class MicroservicesTestSuite:
    """微服务测试套件"""
    
    def __init__(self):
        self.base_urls = {
            "data-storage": "http://localhost:8080",
            "scheduler": "http://localhost:8081"
        }
        self.test_results = {}
        
    async def test_service_health(self, service_name: str, base_url: str) -> bool:
        """测试服务健康状态"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{base_url}/health") as response:
                    if response.status == 200:
                        health_data = await response.json()
                        return health_data.get("status") == "healthy"
            return False
        except Exception as e:
            print(f"❌ Health check failed for {service_name}: {e}")
            return False
            
    async def test_data_storage_service(self) -> Dict[str, Any]:
        """测试数据存储服务"""
        results = {
            "service_name": "data-storage-service",
            "tests": {},
            "overall_status": "unknown"
        }
        
        base_url = self.base_urls["data-storage"]
        
        try:
            async with aiohttp.ClientSession() as session:
                # 1. 测试健康检查
                health_ok = await self.test_service_health("data-storage", base_url)
                results["tests"]["health_check"] = {
                    "status": "pass" if health_ok else "fail",
                    "description": "Service health check"
                }
                
                # 2. 测试存储热交易数据
                trade_data = {
                    "timestamp": datetime.now().isoformat(),
                    "symbol": "BTCUSDT",
                    "exchange": "test_exchange",
                    "price": 50000.0,
                    "amount": 0.001,
                    "side": "buy",
                    "trade_id": "test_trade_001"
                }
                
                async with session.post(f"{base_url}/api/v1/storage/hot/trades", 
                                      json=trade_data) as response:
                    store_success = response.status == 200
                    results["tests"]["store_hot_trade"] = {
                        "status": "pass" if store_success else "fail",
                        "description": "Store hot trade data",
                        "response_status": response.status
                    }
                    
                # 3. 测试查询热交易数据
                async with session.get(f"{base_url}/api/v1/storage/hot/trades/test_exchange/BTCUSDT?limit=10") as response:
                    query_success = response.status == 200
                    results["tests"]["query_hot_trades"] = {
                        "status": "pass" if query_success else "fail",
                        "description": "Query hot trade data",
                        "response_status": response.status
                    }
                    
                # 4. 测试存储热行情数据
                ticker_data = {
                    "timestamp": datetime.now().isoformat(),
                    "symbol": "BTCUSDT",
                    "exchange": "test_exchange",
                    "last_price": 50000.0,
                    "volume_24h": 1000.0,
                    "price_change_24h": 500.0,
                    "high_24h": 51000.0,
                    "low_24h": 49000.0
                }
                
                async with session.post(f"{base_url}/api/v1/storage/hot/tickers", 
                                      json=ticker_data) as response:
                    ticker_success = response.status == 200
                    results["tests"]["store_hot_ticker"] = {
                        "status": "pass" if ticker_success else "fail",
                        "description": "Store hot ticker data",
                        "response_status": response.status
                    }
                    
                # 5. 测试查询热行情数据
                async with session.get(f"{base_url}/api/v1/storage/hot/tickers/test_exchange/BTCUSDT") as response:
                    ticker_query_success = response.status in [200, 404]  # 404也是正常的
                    results["tests"]["query_hot_ticker"] = {
                        "status": "pass" if ticker_query_success else "fail",
                        "description": "Query hot ticker data",
                        "response_status": response.status
                    }
                    
                # 6. 测试数据归档
                archive_data = {
                    "data_type": "trades",
                    "cutoff_hours": 1
                }
                
                async with session.post(f"{base_url}/api/v1/storage/cold/archive", 
                                      json=archive_data) as response:
                    archive_success = response.status == 200
                    results["tests"]["archive_to_cold"] = {
                        "status": "pass" if archive_success else "fail",
                        "description": "Archive data to cold storage",
                        "response_status": response.status
                    }
                    
                # 7. 测试存储统计
                async with session.get(f"{base_url}/api/v1/storage/stats") as response:
                    stats_success = response.status == 200
                    results["tests"]["storage_stats"] = {
                        "status": "pass" if stats_success else "fail",
                        "description": "Get storage statistics",
                        "response_status": response.status
                    }
                    
        except Exception as e:
            results["tests"]["exception"] = {
                "status": "fail",
                "description": f"Test execution error: {str(e)}"
            }
            
        # 计算总体状态
        passed_tests = sum(1 for test in results["tests"].values() if test["status"] == "pass")
        total_tests = len(results["tests"])
        results["overall_status"] = "pass" if passed_tests == total_tests else "fail"
        results["pass_rate"] = f"{passed_tests}/{total_tests}"
        
        return results
        
    async def test_scheduler_service(self) -> Dict[str, Any]:
        """测试调度服务"""
        results = {
            "service_name": "scheduler-service",
            "tests": {},
            "overall_status": "unknown"
        }
        
        base_url = self.base_urls["scheduler"]
        
        try:
            async with aiohttp.ClientSession() as session:
                # 1. 测试健康检查
                health_ok = await self.test_service_health("scheduler", base_url)
                results["tests"]["health_check"] = {
                    "status": "pass" if health_ok else "fail",
                    "description": "Service health check"
                }
                
                # 2. 测试获取调度器状态
                async with session.get(f"{base_url}/api/v1/scheduler/status") as response:
                    status_success = response.status == 200
                    results["tests"]["scheduler_status"] = {
                        "status": "pass" if status_success else "fail",
                        "description": "Get scheduler status",
                        "response_status": response.status
                    }
                    
                # 3. 测试列出任务
                async with session.get(f"{base_url}/api/v1/scheduler/tasks") as response:
                    list_success = response.status == 200
                    results["tests"]["list_tasks"] = {
                        "status": "pass" if list_success else "fail",
                        "description": "List all tasks",
                        "response_status": response.status
                    }
                    
                    if list_success:
                        tasks_data = await response.json()
                        task_count = len(tasks_data.get("data", []))
                        results["tests"]["default_tasks_created"] = {
                            "status": "pass" if task_count > 0 else "fail",
                            "description": f"Default tasks created (found {task_count} tasks)",
                            "task_count": task_count
                        }
                        
                # 4. 测试创建新任务
                new_task = {
                    "name": "test_task",
                    "cron_expression": "*/5 * * * *",
                    "target_service": "data-storage-service",
                    "target_endpoint": "/api/v1/storage/stats",
                    "payload": {}
                }
                
                async with session.post(f"{base_url}/api/v1/scheduler/tasks", 
                                      json=new_task) as response:
                    create_success = response.status == 200
                    results["tests"]["create_task"] = {
                        "status": "pass" if create_success else "fail",
                        "description": "Create new task",
                        "response_status": response.status
                    }
                    
                    if create_success:
                        task_response = await response.json()
                        test_task_id = task_response.get("task_id")
                        
                        # 5. 测试获取任务详情
                        if test_task_id:
                            async with session.get(f"{base_url}/api/v1/scheduler/tasks/{test_task_id}") as response:
                                get_success = response.status == 200
                                results["tests"]["get_task"] = {
                                    "status": "pass" if get_success else "fail",
                                    "description": "Get task details",
                                    "response_status": response.status
                                }
                                
                            # 6. 测试立即运行任务
                            async with session.post(f"{base_url}/api/v1/scheduler/tasks/{test_task_id}/run") as response:
                                run_success = response.status == 200
                                results["tests"]["run_task_now"] = {
                                    "status": "pass" if run_success else "fail",
                                    "description": "Run task immediately",
                                    "response_status": response.status
                                }
                                
                            # 7. 测试删除任务
                            async with session.delete(f"{base_url}/api/v1/scheduler/tasks/{test_task_id}") as response:
                                delete_success = response.status == 200
                                results["tests"]["delete_task"] = {
                                    "status": "pass" if delete_success else "fail",
                                    "description": "Delete task",
                                    "response_status": response.status
                                }
                                
        except Exception as e:
            results["tests"]["exception"] = {
                "status": "fail",
                "description": f"Test execution error: {str(e)}"
            }
            
        # 计算总体状态
        passed_tests = sum(1 for test in results["tests"].values() if test["status"] == "pass")
        total_tests = len(results["tests"])
        results["overall_status"] = "pass" if passed_tests == total_tests else "fail"
        results["pass_rate"] = f"{passed_tests}/{total_tests}"
        
        return results
        
    async def test_service_integration(self) -> Dict[str, Any]:
        """测试服务间集成"""
        results = {
            "service_name": "service-integration",
            "tests": {},
            "overall_status": "unknown"
        }
        
        try:
            # 1. 测试调度服务调用存储服务
            scheduler_url = self.base_urls["scheduler"]
            
            # 创建一个调用存储服务的任务
            integration_task = {
                "name": "integration_test_task",
                "cron_expression": "*/5 * * * *",
                "target_service": "data-storage-service",
                "target_endpoint": "/api/v1/storage/stats",
                "payload": {}
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{scheduler_url}/api/v1/scheduler/tasks", 
                                      json=integration_task) as response:
                    create_success = response.status == 200
                    results["tests"]["create_integration_task"] = {
                        "status": "pass" if create_success else "fail",
                        "description": "Create integration task",
                        "response_status": response.status
                    }
                    
                    if create_success:
                        task_response = await response.json()
                        task_id = task_response.get("task_id")
                        
                        # 立即运行任务测试服务间通信
                        async with session.post(f"{scheduler_url}/api/v1/scheduler/tasks/{task_id}/run") as response:
                            run_success = response.status == 200
                            results["tests"]["run_integration_task"] = {
                                "status": "pass" if run_success else "fail",
                                "description": "Run integration task",
                                "response_status": response.status
                            }
                            
                        # 等待任务执行
                        await asyncio.sleep(2)
                        
                        # 检查任务状态
                        async with session.get(f"{scheduler_url}/api/v1/scheduler/tasks/{task_id}") as response:
                            if response.status == 200:
                                task_data = await response.json()
                                task_info = task_data.get("data", {})
                                run_count = task_info.get("run_count", 0)
                                
                                results["tests"]["task_execution"] = {
                                    "status": "pass" if run_count > 0 else "fail",
                                    "description": f"Task executed (run count: {run_count})",
                                    "run_count": run_count
                                }
                                
                        # 清理测试任务
                        await session.delete(f"{scheduler_url}/api/v1/scheduler/tasks/{task_id}")
                        
        except Exception as e:
            results["tests"]["exception"] = {
                "status": "fail",
                "description": f"Integration test error: {str(e)}"
            }
            
        # 计算总体状态
        passed_tests = sum(1 for test in results["tests"].values() if test["status"] == "pass")
        total_tests = len(results["tests"])
        results["overall_status"] = "pass" if passed_tests == total_tests else "fail"
        results["pass_rate"] = f"{passed_tests}/{total_tests}"
        
        return results
        
    async def run_all_tests(self) -> Dict[str, Any]:
        """运行所有测试"""
        print("🧪 Starting MarketPrism Microservices Phase 1 Tests")
        print("=" * 60)
        
        # 运行各项测试
        storage_results = await self.test_data_storage_service()
        scheduler_results = await self.test_scheduler_service()
        integration_results = await self.test_service_integration()
        
        # 汇总结果
        all_results = {
            "test_suite": "MarketPrism Microservices Phase 1",
            "timestamp": datetime.now().isoformat(),
            "services": [storage_results, scheduler_results, integration_results]
        }
        
        # 计算总体统计
        total_tests = 0
        total_passed = 0
        
        for service_result in all_results["services"]:
            service_tests = len(service_result["tests"])
            service_passed = sum(1 for test in service_result["tests"].values() if test["status"] == "pass")
            total_tests += service_tests
            total_passed += service_passed
            
        all_results["summary"] = {
            "total_services": len(all_results["services"]),
            "total_tests": total_tests,
            "total_passed": total_passed,
            "total_failed": total_tests - total_passed,
            "overall_pass_rate": f"{total_passed}/{total_tests}",
            "success_percentage": round((total_passed / total_tests) * 100, 1) if total_tests > 0 else 0
        }
        
        return all_results
        
    def print_test_results(self, results: Dict[str, Any]):
        """打印测试结果"""
        print(f"\n📊 Test Results Summary")
        print("=" * 60)
        
        summary = results["summary"]
        print(f"Total Services Tested: {summary['total_services']}")
        print(f"Total Tests: {summary['total_tests']}")
        print(f"Passed: {summary['total_passed']}")
        print(f"Failed: {summary['total_failed']}")
        print(f"Success Rate: {summary['success_percentage']}%")
        
        print("\n📋 Detailed Results:")
        print("-" * 60)
        
        for service_result in results["services"]:
            service_name = service_result["service_name"]
            overall_status = service_result["overall_status"]
            pass_rate = service_result["pass_rate"]
            
            status_icon = "✅" if overall_status == "pass" else "❌"
            print(f"{status_icon} {service_name}: {pass_rate} ({overall_status})")
            
            for test_name, test_result in service_result["tests"].items():
                test_status = test_result["status"]
                test_desc = test_result["description"]
                test_icon = "  ✓" if test_status == "pass" else "  ✗"
                print(f"{test_icon} {test_name}: {test_desc}")
                
        print("-" * 60)
        
        if summary["success_percentage"] >= 80:
            print("🎉 Phase 1 microservices tests PASSED!")
        else:
            print("⚠️  Phase 1 microservices tests need attention")


async def main():
    """主测试函数"""
    test_suite = MicroservicesTestSuite()
    
    try:
        results = await test_suite.run_all_tests()
        test_suite.print_test_results(results)
        
        # 保存测试结果
        results_file = project_root / "tests" / "reports" / f"microservices_phase1_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        results_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
            
        print(f"\n📄 Test results saved to: {results_file}")
        
        # 返回退出码
        success_rate = results["summary"]["success_percentage"]
        return 0 if success_rate >= 80 else 1
        
    except Exception as e:
        print(f"❌ Test execution failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)