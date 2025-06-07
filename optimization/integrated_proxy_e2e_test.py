#!/usr/bin/env python3
"""
MarketPrism 集成代理端到端测试

结合优化后的组件进行完整测试：
1. 代理配置加载
2. 优化会话管理器
3. 增强交易所连接器
4. 实际API调用验证
"""

import asyncio
import json
import logging
import time
import yaml
from pathlib import Path
from typing import Dict, List, Any
from dataclasses import dataclass

# 导入我们的优化组件
import sys
sys.path.append(str(Path(__file__).parent.parent))

from core.networking.optimized_session_manager import SessionManager, SessionConfig
from core.networking.enhanced_exchange_connector import EnhancedExchangeConnector, ExchangeConfig
from config.app_config import NetworkConfig

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """测试结果"""
    test_name: str
    success: bool
    duration_ms: float
    details: Dict[str, Any]
    error: str = None


class IntegratedProxyE2ETest:
    """集成代理端到端测试"""
    
    def __init__(self):
        self.results: List[TestResult] = []
        self.config_path = Path(__file__).parent.parent / "config" / "collector_config.yaml"
        self.proxy_config = self.load_proxy_config()
        
    def load_proxy_config(self) -> Dict[str, Any]:
        """加载代理配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            return config_data.get('proxy', {})
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return {}
    
    async def test_session_manager_with_proxy(self) -> TestResult:
        """测试带代理的会话管理器"""
        test_name = "优化会话管理器 + 代理配置"
        start_time = time.time()
        
        try:
            # 创建会话配置
            session_config = SessionConfig(
                proxy_url=self.proxy_config.get('rest_api', {}).get('http_proxy'),
                connection_timeout=10.0,
                read_timeout=30.0,
                max_retries=2
            )
            
            session_manager = SessionManager(session_config)
            
            # 测试基本连接
            test_url = "https://api.binance.com/api/v3/ping"
            
            async with session_manager.request('GET', test_url) as response:
                success = response.status == 200
                response_data = await response.json() if success else None
            
            # 获取统计信息
            stats = session_manager.get_statistics()
            health = session_manager.get_health_status()
            
            await session_manager.close()
            
            duration = (time.time() - start_time) * 1000
            
            return TestResult(
                test_name=test_name,
                success=success,
                duration_ms=duration,
                details={
                    'proxy_used': session_config.proxy_url,
                    'response_data': response_data,
                    'session_stats': stats,
                    'health_status': health
                }
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return TestResult(
                test_name=test_name,
                success=False,
                duration_ms=duration,
                details={},
                error=str(e)
            )
    
    async def test_enhanced_exchange_connector(self) -> TestResult:
        """测试增强交易所连接器"""
        test_name = "增强交易所连接器"
        start_time = time.time()
        
        try:
            # 创建交易所配置
            exchange_config = ExchangeConfig(
                name="binance",
                base_url="https://api.binance.com",
                ws_url="wss://stream.binance.com:9443/ws",
                api_key="",  # 公开API不需要
                api_secret="",
                http_proxy=self.proxy_config.get('rest_api', {}).get('http_proxy')
            )
            
            connector = EnhancedExchangeConnector(exchange_config)
            
            # 测试多个API端点
            test_apis = [
                ("/api/v3/ping", "Ping"),
                ("/api/v3/time", "Server Time"),
                ("/api/v3/ticker/24hr?symbol=BTCUSDT", "24hr Ticker"),
                ("/api/v3/depth?symbol=BTCUSDT&limit=5", "Order Book")
            ]
            
            api_results = []
            
            for endpoint, description in test_apis:
                try:
                    api_start = time.time()
                    data = await connector.make_request('GET', endpoint)
                    api_duration = (time.time() - api_start) * 1000
                    
                    api_results.append({
                        'endpoint': endpoint,
                        'description': description,
                        'success': True,
                        'duration_ms': api_duration,
                        'data_size': len(str(data)) if data else 0
                    })
                    
                except Exception as e:
                    api_duration = (time.time() - api_start) * 1000
                    api_results.append({
                        'endpoint': endpoint,
                        'description': description,
                        'success': False,
                        'duration_ms': api_duration,
                        'error': str(e)
                    })
                
                # 避免频率限制
                await asyncio.sleep(0.5)
            
            # 获取连接器统计
            connector_stats = connector.get_statistics()
            
            await connector.close()
            
            duration = (time.time() - start_time) * 1000
            successful_apis = sum(1 for r in api_results if r['success'])
            
            return TestResult(
                test_name=test_name,
                success=successful_apis > 0,
                duration_ms=duration,
                details={
                    'proxy_used': exchange_config.http_proxy,
                    'successful_apis': successful_apis,
                    'total_apis': len(api_results),
                    'api_results': api_results,
                    'connector_stats': connector_stats
                }
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return TestResult(
                test_name=test_name,
                success=False,
                duration_ms=duration,
                details={},
                error=str(e)
            )
    
    async def test_multiple_exchanges(self) -> TestResult:
        """测试多个交易所连接"""
        test_name = "多交易所连接测试"
        start_time = time.time()
        
        try:
            # 定义交易所配置
            exchanges = [
                {
                    'name': 'Binance',
                    'config': ExchangeConfig(
                        name="binance",
                        base_url="https://api.binance.com",
                        ws_url="wss://stream.binance.com:9443/ws",
                        http_proxy=self.proxy_config.get('rest_api', {}).get('http_proxy')
                    ),
                    'test_endpoint': "/api/v3/ticker/price?symbol=BTCUSDT"
                },
                {
                    'name': 'OKX',
                    'config': ExchangeConfig(
                        name="okx",
                        base_url="https://www.okx.com",
                        ws_url="wss://ws.okx.com:8443/ws/v5/public",
                        http_proxy=self.proxy_config.get('rest_api', {}).get('http_proxy')
                    ),
                    'test_endpoint': "/api/v5/market/ticker?instId=BTC-USDT"
                }
            ]
            
            exchange_results = []
            
            for exchange_info in exchanges:
                exchange_start = time.time()
                
                try:
                    connector = EnhancedExchangeConnector(exchange_info['config'])
                    data = await connector.make_request('GET', exchange_info['test_endpoint'])
                    await connector.close()
                    
                    exchange_duration = (time.time() - exchange_start) * 1000
                    
                    exchange_results.append({
                        'exchange': exchange_info['name'],
                        'success': True,
                        'duration_ms': exchange_duration,
                        'data_received': len(str(data)) if data else 0
                    })
                    
                except Exception as e:
                    exchange_duration = (time.time() - exchange_start) * 1000
                    exchange_results.append({
                        'exchange': exchange_info['name'],
                        'success': False,
                        'duration_ms': exchange_duration,
                        'error': str(e)
                    })
                
                # 避免频率限制
                await asyncio.sleep(1.0)
            
            duration = (time.time() - start_time) * 1000
            successful_exchanges = sum(1 for r in exchange_results if r['success'])
            
            return TestResult(
                test_name=test_name,
                success=successful_exchanges > 0,
                duration_ms=duration,
                details={
                    'successful_exchanges': successful_exchanges,
                    'total_exchanges': len(exchange_results),
                    'exchange_results': exchange_results,
                    'proxy_used': self.proxy_config.get('rest_api', {}).get('http_proxy')
                }
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return TestResult(
                test_name=test_name,
                success=False,
                duration_ms=duration,
                details={},
                error=str(e)
            )
    
    async def test_performance_benchmark(self) -> TestResult:
        """性能基准测试"""
        test_name = "性能基准测试"
        start_time = time.time()
        
        try:
            # 创建优化的连接器
            exchange_config = ExchangeConfig(
                name="binance_benchmark",
                base_url="https://api.binance.com",
                ws_url="wss://stream.binance.com:9443/ws",
                http_proxy=self.proxy_config.get('rest_api', {}).get('http_proxy')
            )
            
            connector = EnhancedExchangeConnector(exchange_config)
            
            # 并发请求测试
            concurrent_requests = 5
            test_endpoint = "/api/v3/ticker/price?symbol=BTCUSDT"
            
            tasks = []
            for i in range(concurrent_requests):
                task = connector.make_request('GET', test_endpoint)
                tasks.append(task)
            
            # 执行并发请求
            request_start = time.time()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            request_duration = (time.time() - request_start) * 1000
            
            # 分析结果
            successful_requests = sum(1 for r in results if not isinstance(r, Exception))
            failed_requests = len(results) - successful_requests
            
            # 获取连接器统计
            final_stats = connector.get_statistics()
            
            await connector.close()
            
            duration = (time.time() - start_time) * 1000
            
            return TestResult(
                test_name=test_name,
                success=successful_requests > 0,
                duration_ms=duration,
                details={
                    'concurrent_requests': concurrent_requests,
                    'successful_requests': successful_requests,
                    'failed_requests': failed_requests,
                    'request_duration_ms': request_duration,
                    'avg_request_time_ms': request_duration / concurrent_requests,
                    'requests_per_second': concurrent_requests / (request_duration / 1000),
                    'connector_stats': final_stats,
                    'proxy_used': exchange_config.http_proxy
                }
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return TestResult(
                test_name=test_name,
                success=False,
                duration_ms=duration,
                details={},
                error=str(e)
            )
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """运行所有测试"""
        print("🚀 MarketPrism 集成代理端到端测试")
        print("=" * 60)
        print(f"代理配置: {self.proxy_config.get('rest_api', {}).get('http_proxy', '无')}")
        print("=" * 60)
        
        # 运行测试
        tests = [
            self.test_session_manager_with_proxy(),
            self.test_enhanced_exchange_connector(),
            self.test_multiple_exchanges(),
            self.test_performance_benchmark()
        ]
        
        for i, test_coro in enumerate(tests, 1):
            print(f"\n📊 测试 {i}/{len(tests)}: ", end="")
            result = await test_coro
            self.results.append(result)
            
            if result.success:
                print(f"✅ {result.test_name} ({result.duration_ms:.1f}ms)")
            else:
                print(f"❌ {result.test_name} - {result.error}")
        
        # 生成总结
        successful_tests = sum(1 for r in self.results if r.success)
        total_tests = len(self.results)
        total_duration = sum(r.duration_ms for r in self.results)
        
        print(f"\n" + "=" * 60)
        print("📊 测试总结")
        print("=" * 60)
        print(f"成功测试: {successful_tests}/{total_tests}")
        print(f"成功率: {successful_tests/total_tests:.1%}")
        print(f"总耗时: {total_duration:.1f}ms")
        print(f"平均耗时: {total_duration/total_tests:.1f}ms/测试")
        
        # 输出详细结果
        print(f"\n📋 详细结果:")
        for result in self.results:
            status = "✅" if result.success else "❌"
            print(f"  {status} {result.test_name}: {result.duration_ms:.1f}ms")
            if result.error:
                print(f"     错误: {result.error}")
        
        # 生成报告
        report = {
            'test_summary': {
                'successful_tests': successful_tests,
                'total_tests': total_tests,
                'success_rate': successful_tests / total_tests,
                'total_duration_ms': total_duration,
                'avg_duration_ms': total_duration / total_tests,
                'proxy_config': self.proxy_config
            },
            'test_results': [
                {
                    'test_name': r.test_name,
                    'success': r.success,
                    'duration_ms': r.duration_ms,
                    'details': r.details,
                    'error': r.error
                }
                for r in self.results
            ],
            'timestamp': time.time()
        }
        
        # 保存报告
        report_file = f"integrated_proxy_e2e_report_{int(time.time())}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 详细报告已保存: {report_file}")
        
        if successful_tests == total_tests:
            print("🎉 所有测试通过！代理集成优化成功！")
            return 0
        elif successful_tests >= total_tests * 0.7:
            print("⚠️ 大部分测试通过，代理配置基本正常")
            return 1
        else:
            print("❌ 多个测试失败，需要进一步检查代理配置")
            return 2


async def main():
    """主函数"""
    tester = IntegratedProxyE2ETest()
    return await tester.run_all_tests()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    print(f"\n🏁 测试完成，退出代码: {exit_code}")
    exit(exit_code)