#!/usr/bin/env python3
"""
MarketPrism 优化后的端到端测试

验证优化效果：
1. aiohttp会话泄漏修复
2. 交易所连接稳定性提升
3. 资源管理优化
4. 错误处理改进
5. 性能提升验证
"""

import asyncio
import json
import yaml
import sys
import time
import psutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any
import gc

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.networking.optimized_session_manager import SessionManager, SessionConfig
from core.networking.enhanced_exchange_connector import create_exchange_connector, EXCHANGE_CONFIGS
from core.monitoring.resource_manager import ResourceManager, ResourceConfig
from config.app_config import NetworkConfig


class OptimizedE2ETest:
    """优化后的端到端测试"""
    
    def __init__(self):
        self.test_results = {}
        self.start_time = None
        self.session_manager = None
        self.resource_manager = None
        self.connectors = {}
        
        # 性能基准
        self.performance_baseline = {
            'memory_usage_mb': 0,
            'session_leaks': 0,
            'connection_success_rate': 0.0,
            'response_time_ms': 0,
            'gc_collections': 0
        }
    
    async def setup_optimized_components(self):
        """设置优化组件"""
        print("🔧 设置优化组件")
        print("-" * 40)
        
        try:
            # 1. 初始化优化的会话管理器
            session_config = SessionConfig(
                connection_timeout=15.0,
                read_timeout=30.0,
                total_timeout=60.0,
                connector_limit=50,
                connector_limit_per_host=5,
                max_retries=3,
                proxy_url=NetworkConfig.get_proxy_dict().get('https') if NetworkConfig.get_proxy_dict() else None
            )
            
            self.session_manager = SessionManager(session_config)
            print(f"  ✅ 优化会话管理器已初始化")
            
            # 2. 初始化资源管理器
            resource_config = ResourceConfig(
                max_memory_usage=1024 * 1024 * 1024,  # 1GB
                memory_check_interval=30,
                cleanup_interval=15,
                enable_monitoring=True
            )
            
            self.resource_manager = ResourceManager(resource_config)
            await self.resource_manager.start()
            print(f"  ✅ 资源管理器已启动")
            
            # 3. 创建增强的交易所连接器
            exchanges = ['binance', 'okx', 'deribit']
            
            for exchange in exchanges:
                try:
                    config_overrides = {
                        'http_proxy': NetworkConfig.get_proxy_dict().get('https') if NetworkConfig.get_proxy_dict() else None,
                        'request_timeout': 20.0,
                        'max_retries': 3
                    }
                    
                    connector = create_exchange_connector(exchange, config_overrides)
                    await connector.initialize()
                    
                    self.connectors[exchange] = connector
                    print(f"    ✅ {exchange.upper()} 连接器已初始化")
                    
                except Exception as e:
                    print(f"    ⚠️ {exchange.upper()} 连接器初始化失败: {e}")
                    # 不中断测试，继续其他交易所
            
            print(f"✅ 优化组件设置完成: {len(self.connectors)} 个连接器可用")
            return True
            
        except Exception as e:
            print(f"  ❌ 优化组件设置失败: {e}")
            return False
    
    async def test_session_leak_prevention(self):
        """测试会话泄漏预防"""
        print("\n🔍 会话泄漏预防测试")
        print("-" * 40)
        
        initial_sessions = len(self.session_manager._sessions)
        initial_refs = len(self.session_manager._session_refs)
        
        print(f"  初始会话数: {initial_sessions}")
        print(f"  初始引用数: {initial_refs}")
        
        # 创建多个会话并测试清理
        test_sessions = []
        for i in range(20):
            session_key = f"test_session_{i}"
            session = self.session_manager.get_session(session_key)
            test_sessions.append((session_key, session))
        
        current_sessions = len(self.session_manager._sessions)
        print(f"  创建后会话数: {current_sessions}")
        
        # 关闭部分会话
        for i in range(0, 10):
            session_key, _ = test_sessions[i]
            await self.session_manager.close_session(session_key)
        
        # 等待清理任务运行
        await asyncio.sleep(5)
        
        # 强制垃圾回收
        collected = gc.collect()
        
        final_sessions = len(self.session_manager._sessions)
        final_refs = len(self.session_manager._session_refs)
        
        print(f"  清理后会话数: {final_sessions}")
        print(f"  清理后引用数: {final_refs}")
        print(f"  垃圾回收对象: {collected}")
        
        # 验证结果
        session_leak_prevented = (current_sessions - final_sessions) >= 10
        reference_cleanup = final_refs <= initial_refs + 10
        
        results = {
            'initial_sessions': initial_sessions,
            'peak_sessions': current_sessions,
            'final_sessions': final_sessions,
            'initial_refs': initial_refs,
            'final_refs': final_refs,
            'gc_collected': collected,
            'leak_prevented': session_leak_prevented,
            'refs_cleaned': reference_cleanup,
            'test_passed': session_leak_prevented and reference_cleanup
        }
        
        status = "✅ 通过" if results['test_passed'] else "❌ 失败"
        print(f"  {status} 会话泄漏预防: {results['leak_prevented']}")
        print(f"  {status} 引用清理: {results['refs_cleaned']}")
        
        return results
    
    async def test_connection_stability(self):
        """测试连接稳定性"""
        print("\n🌐 连接稳定性测试")
        print("-" * 40)
        
        connection_results = {}
        total_attempts = 0
        successful_connections = 0
        
        for exchange, connector in self.connectors.items():
            print(f"  测试 {exchange.upper()} 连接稳定性...")
            
            exchange_attempts = 0
            exchange_successes = 0
            response_times = []
            
            # 进行多次请求测试
            for attempt in range(5):
                try:
                    start_time = time.time()
                    
                    # 测试获取行情数据
                    if exchange == 'binance':
                        data = await connector.get_ticker('BTCUSDT')
                    elif exchange == 'okx':
                        data = await connector.get_ticker('BTC-USDT')
                    elif exchange == 'deribit':
                        data = await connector.get_ticker('BTC-PERPETUAL')
                    
                    response_time = (time.time() - start_time) * 1000
                    response_times.append(response_time)
                    
                    exchange_attempts += 1
                    exchange_successes += 1
                    
                    print(f"    ✅ 尝试 {attempt + 1}: {response_time:.1f}ms")
                    
                except Exception as e:
                    exchange_attempts += 1
                    print(f"    ❌ 尝试 {attempt + 1}: {str(e)[:50]}")
                
                # 短暂等待避免频率限制
                await asyncio.sleep(0.5)
            
            success_rate = exchange_successes / exchange_attempts if exchange_attempts > 0 else 0
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0
            
            connection_results[exchange] = {
                'attempts': exchange_attempts,
                'successes': exchange_successes,
                'success_rate': success_rate,
                'avg_response_time': avg_response_time,
                'response_times': response_times
            }
            
            total_attempts += exchange_attempts
            successful_connections += exchange_successes
            
            print(f"    📊 成功率: {success_rate:.1%}, 平均响应: {avg_response_time:.1f}ms")
        
        overall_success_rate = successful_connections / total_attempts if total_attempts > 0 else 0
        
        results = {
            'total_attempts': total_attempts,
            'successful_connections': successful_connections,
            'overall_success_rate': overall_success_rate,
            'exchange_details': connection_results,
            'test_passed': overall_success_rate >= 0.6  # 60%成功率阈值
        }
        
        status = "✅ 通过" if results['test_passed'] else "❌ 失败"
        print(f"  {status} 整体连接稳定性: {overall_success_rate:.1%}")
        
        return results
    
    async def test_resource_management(self):
        """测试资源管理"""
        print("\n💾 资源管理测试")
        print("-" * 40)
        
        # 获取初始资源状态
        initial_stats = self.resource_manager.get_statistics()
        initial_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        
        print(f"  初始内存使用: {initial_memory:.1f}MB")
        print(f"  初始追踪对象: {initial_stats['tracker_stats']['total_objects']}")
        
        # 创建一些对象进行资源管理测试
        managed_objects = []
        for i in range(100):
            obj = {'data': f'test_object_{i}', 'size': 1024 * i}
            self.resource_manager.track_object(obj)
            managed_objects.append(obj)
        
        # 模拟一些网络连接
        connection_keys = []
        for i in range(10):
            key = f"test_connection_{i}"
            connection_keys.append(key)
            
            # 使用连接池获取模拟连接
            async def mock_factory():
                return {'mock_connection': True, 'id': key}
            
            await self.resource_manager.get_connection(key, mock_factory)
        
        # 等待监控收集数据
        await asyncio.sleep(3)
        
        # 获取中间状态
        mid_stats = self.resource_manager.get_statistics()
        mid_memory = psutil.Process().memory_info().rss / 1024 / 1024
        
        print(f"  中间内存使用: {mid_memory:.1f}MB (+{mid_memory - initial_memory:.1f}MB)")
        print(f"  中间追踪对象: {mid_stats['tracker_stats']['total_objects']}")
        print(f"  连接池使用: {mid_stats['connection_pool_stats']['total_connections']}")
        
        # 清理一半对象
        for i in range(50):
            self.resource_manager.untrack_object(managed_objects[i])
        
        # 强制垃圾回收
        gc_result = self.resource_manager.force_gc()
        
        # 等待清理
        await asyncio.sleep(2)
        
        # 获取最终状态
        final_stats = self.resource_manager.get_statistics()
        final_memory = psutil.Process().memory_info().rss / 1024 / 1024
        
        print(f"  最终内存使用: {final_memory:.1f}MB")
        print(f"  最终追踪对象: {final_stats['tracker_stats']['total_objects']}")
        print(f"  GC回收对象: {gc_result['collected_objects']}")
        
        # 检查资源管理效果
        memory_growth = final_memory - initial_memory
        object_cleanup = (mid_stats['tracker_stats']['total_objects'] - 
                         final_stats['tracker_stats']['total_objects'])
        
        results = {
            'initial_memory_mb': initial_memory,
            'peak_memory_mb': mid_memory,
            'final_memory_mb': final_memory,
            'memory_growth_mb': memory_growth,
            'initial_objects': initial_stats['tracker_stats']['total_objects'],
            'peak_objects': mid_stats['tracker_stats']['total_objects'],
            'final_objects': final_stats['tracker_stats']['total_objects'],
            'objects_cleaned': object_cleanup,
            'gc_collected': gc_result['collected_objects'],
            'connections_managed': mid_stats['connection_pool_stats']['total_connections'],
            'memory_stable': memory_growth < 50,  # 内存增长不超过50MB
            'objects_managed': object_cleanup >= 40,  # 至少清理40个对象
            'test_passed': memory_growth < 50 and object_cleanup >= 40
        }
        
        status = "✅ 通过" if results['test_passed'] else "❌ 失败"
        print(f"  {status} 内存管理: 增长 {memory_growth:.1f}MB")
        print(f"  {status} 对象管理: 清理 {object_cleanup} 个对象")
        
        return results
    
    async def test_error_handling_improvements(self):
        """测试错误处理改进"""
        print("\n🛠️ 错误处理改进测试")
        print("-" * 40)
        
        error_scenarios = []
        
        # 测试不同类型的错误处理
        for exchange, connector in self.connectors.items():
            print(f"  测试 {exchange.upper()} 错误处理...")
            
            # 1. 测试无效符号错误处理
            try:
                await connector.get_ticker('INVALID_SYMBOL_12345')
                error_scenarios.append({
                    'exchange': exchange,
                    'scenario': 'invalid_symbol',
                    'handled': False,
                    'error': 'No error raised'
                })
            except Exception as e:
                error_scenarios.append({
                    'exchange': exchange,
                    'scenario': 'invalid_symbol',
                    'handled': True,
                    'error': str(e)[:100]
                })
                print(f"    ✅ 无效符号错误正确处理: {str(e)[:50]}")
            
            # 2. 测试超时处理（快速失败）
            try:
                # 模拟超时场景
                original_timeout = connector.config.request_timeout
                connector.config.request_timeout = 0.1  # 极短超时
                
                await connector.get_ticker('BTCUSDT')
                
                connector.config.request_timeout = original_timeout
                error_scenarios.append({
                    'exchange': exchange,
                    'scenario': 'timeout',
                    'handled': False,
                    'error': 'No timeout occurred'
                })
            except Exception as e:
                connector.config.request_timeout = original_timeout
                error_scenarios.append({
                    'exchange': exchange,
                    'scenario': 'timeout',
                    'handled': True,
                    'error': str(e)[:100]
                })
                print(f"    ✅ 超时错误正确处理: {str(e)[:50]}")
        
        # 统计错误处理效果
        total_scenarios = len(error_scenarios)
        handled_scenarios = sum(1 for s in error_scenarios if s['handled'])
        error_handling_rate = handled_scenarios / total_scenarios if total_scenarios > 0 else 0
        
        results = {
            'total_scenarios': total_scenarios,
            'handled_scenarios': handled_scenarios,
            'error_handling_rate': error_handling_rate,
            'error_details': error_scenarios,
            'test_passed': error_handling_rate >= 0.8  # 80%错误处理率
        }
        
        status = "✅ 通过" if results['test_passed'] else "❌ 失败"
        print(f"  {status} 错误处理率: {error_handling_rate:.1%}")
        
        return results
    
    async def run_performance_benchmark(self):
        """运行性能基准测试"""
        print("\n⚡ 性能基准测试")
        print("-" * 40)
        
        # 并发请求测试
        concurrent_requests = 50
        start_time = time.time()
        
        async def make_concurrent_request(session_key: str):
            """并发请求函数"""
            try:
                async with self.session_manager.request(
                    'GET', 
                    'https://httpbin.org/delay/1',
                    session_key=session_key
                ) as response:
                    return await response.json()
            except Exception as e:
                return {'error': str(e)}
        
        # 执行并发请求
        tasks = [
            make_concurrent_request(f"perf_test_{i}")
            for i in range(concurrent_requests)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # 统计结果
        successful_requests = sum(1 for r in results if isinstance(r, dict) and 'error' not in r)
        failed_requests = concurrent_requests - successful_requests
        requests_per_second = concurrent_requests / duration
        
        # 内存性能测试
        memory_before = psutil.Process().memory_info().rss / 1024 / 1024
        
        # 创建大量临时对象
        temp_objects = []
        for i in range(1000):
            temp_objects.append({'id': i, 'data': 'x' * 1000})
        
        memory_after = psutil.Process().memory_info().rss / 1024 / 1024
        memory_usage = memory_after - memory_before
        
        # 清理并检查内存回收
        del temp_objects
        gc.collect()
        await asyncio.sleep(1)
        
        memory_final = psutil.Process().memory_info().rss / 1024 / 1024
        memory_recovered = memory_after - memory_final
        
        performance_results = {
            'concurrent_requests': concurrent_requests,
            'successful_requests': successful_requests,
            'failed_requests': failed_requests,
            'success_rate': successful_requests / concurrent_requests,
            'duration_seconds': duration,
            'requests_per_second': requests_per_second,
            'memory_usage_mb': memory_usage,
            'memory_recovered_mb': memory_recovered,
            'memory_recovery_rate': memory_recovered / memory_usage if memory_usage > 0 else 0,
            'test_passed': (
                successful_requests / concurrent_requests >= 0.8 and
                requests_per_second >= 10 and
                memory_recovery_rate >= 0.5
            )
        }
        
        status = "✅ 通过" if performance_results['test_passed'] else "❌ 失败"
        print(f"  {status} 并发性能: {requests_per_second:.1f} req/s")
        print(f"  {status} 成功率: {performance_results['success_rate']:.1%}")
        print(f"  {status} 内存回收: {performance_results['memory_recovery_rate']:.1%}")
        
        return performance_results
    
    async def generate_optimization_report(self, test_results: Dict[str, Any]):
        """生成优化报告"""
        end_time = datetime.now(timezone.utc)
        duration = (end_time - self.start_time).total_seconds()
        
        # 汇总测试结果
        all_tests_passed = all(
            result.get('test_passed', False) 
            for result in test_results.values()
        )
        
        # 计算改进指标
        improvements = {
            'session_leak_prevention': test_results['session_leak']['leak_prevented'],
            'connection_stability': test_results['connection']['overall_success_rate'] >= 0.6,
            'resource_management': test_results['resource']['test_passed'],
            'error_handling': test_results['error_handling']['error_handling_rate'] >= 0.8,
            'performance': test_results['performance']['test_passed']
        }
        
        improvement_score = sum(improvements.values()) / len(improvements)
        
        # 生成最终报告
        optimization_report = {
            'test_metadata': {
                'test_type': 'OPTIMIZED_E2E_COMPREHENSIVE',
                'version': '1.0',
                'start_time': self.start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'duration_seconds': duration,
                'test_environment': 'optimization_validation'
            },
            'optimization_summary': {
                'all_tests_passed': all_tests_passed,
                'improvement_score': improvement_score,
                'improvements': improvements,
                'optimized_components': [
                    'session_manager',
                    'exchange_connectors',
                    'resource_manager',
                    'error_handling',
                    'performance_tuning'
                ]
            },
            'detailed_results': test_results,
            'component_statistics': {
                'session_manager': self.session_manager.get_statistics() if self.session_manager else {},
                'resource_manager': self.resource_manager.get_statistics() if self.resource_manager else {},
                'connectors': {
                    exchange: connector.get_statistics()
                    for exchange, connector in self.connectors.items()
                }
            },
            'recommendations': self._generate_recommendations(test_results)
        }
        
        # 保存报告
        report_file = f"optimization_report_{int(self.start_time.timestamp())}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(optimization_report, f, indent=2, ensure_ascii=False)
        
        # 打印总结
        print("=" * 80)
        print("📊 MarketPrism 系统优化报告")
        print("=" * 80)
        print(f"🕐 测试时长: {duration:.2f}秒")
        print(f"🎯 优化评分: {improvement_score:.1%}")
        print(f"📈 总体状态: {'✅ 优化成功' if all_tests_passed else '⚠️ 部分问题'}")
        
        print(f"\n🔧 优化组件状态:")
        for component, improved in improvements.items():
            status = "✅" if improved else "❌"
            print(f"  {status} {component.replace('_', ' ').title()}")
        
        print(f"\n📊 详细指标:")
        session_leak = test_results['session_leak']
        print(f"  会话管理: 泄漏预防 {session_leak['leak_prevented']}, 引用清理 {session_leak['refs_cleaned']}")
        
        connection = test_results['connection']
        print(f"  连接稳定性: {connection['overall_success_rate']:.1%} 成功率")
        
        resource = test_results['resource']
        print(f"  资源管理: 内存增长 {resource['memory_growth_mb']:.1f}MB, 对象清理 {resource['objects_cleaned']}")
        
        error_handling = test_results['error_handling']
        print(f"  错误处理: {error_handling['error_handling_rate']:.1%} 处理率")
        
        performance = test_results['performance']
        print(f"  性能指标: {performance['requests_per_second']:.1f} req/s, {performance['memory_recovery_rate']:.1%} 内存回收")
        
        print(f"\n📄 详细报告: {report_file}")
        print("=" * 80)
        
        return optimization_report
    
    def _generate_recommendations(self, test_results: Dict[str, Any]) -> List[str]:
        """生成优化建议"""
        recommendations = []
        
        # 会话管理建议
        session_leak = test_results['session_leak']
        if not session_leak['leak_prevented']:
            recommendations.append("改进会话清理机制，定期检查并关闭未使用的会话")
        
        # 连接稳定性建议
        connection = test_results['connection']
        if connection['overall_success_rate'] < 0.8:
            recommendations.append("优化网络连接配置，增加重试机制和代理切换")
        
        # 资源管理建议
        resource = test_results['resource']
        if resource['memory_growth_mb'] > 30:
            recommendations.append("优化内存使用，增加定期垃圾回收和对象池机制")
        
        # 错误处理建议
        error_handling = test_results['error_handling']
        if error_handling['error_handling_rate'] < 0.9:
            recommendations.append("完善错误分类和处理策略，增加自动恢复机制")
        
        # 性能建议
        performance = test_results['performance']
        if performance['requests_per_second'] < 20:
            recommendations.append("优化并发处理性能，考虑连接池复用和异步优化")
        
        if not recommendations:
            recommendations.append("系统优化状态良好，建议继续监控和定期维护")
        
        return recommendations
    
    async def cleanup(self):
        """清理测试资源"""
        try:
            # 关闭连接器
            for connector in self.connectors.values():
                await connector.close()
            
            # 关闭会话管理器
            if self.session_manager:
                await self.session_manager.close()
            
            # 停止资源管理器
            if self.resource_manager:
                await self.resource_manager.stop()
            
            print("🧹 测试资源已清理")
            
        except Exception as e:
            print(f"⚠️ 资源清理异常: {e}")
    
    async def run_optimization_test(self):
        """运行优化测试"""
        self.start_time = datetime.now(timezone.utc)
        
        print("🚀 MarketPrism 系统优化验证测试")
        print("=" * 80)
        print("🎯 目标: 验证会话管理、连接稳定性、资源管理、错误处理等优化效果")
        print("=" * 80)
        
        try:
            # 1. 设置优化组件
            if not await self.setup_optimized_components():
                raise Exception("优化组件设置失败")
            
            # 2. 运行各项测试
            test_results = {}
            
            # 会话泄漏预防测试
            test_results['session_leak'] = await self.test_session_leak_prevention()
            
            # 连接稳定性测试
            test_results['connection'] = await self.test_connection_stability()
            
            # 资源管理测试
            test_results['resource'] = await self.test_resource_management()
            
            # 错误处理改进测试
            test_results['error_handling'] = await self.test_error_handling_improvements()
            
            # 性能基准测试
            test_results['performance'] = await self.run_performance_benchmark()
            
            # 3. 生成优化报告
            optimization_report = await self.generate_optimization_report(test_results)
            
            return 0
            
        except Exception as e:
            print(f"\n❌ 优化测试失败: {e}")
            import traceback
            traceback.print_exc()
            return 1
        
        finally:
            await self.cleanup()


async def main():
    """主函数"""
    tester = OptimizedE2ETest()
    
    try:
        return await tester.run_optimization_test()
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断测试")
        return 1
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        return 1
    finally:
        await tester.cleanup()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    print(f"\n🎯 优化测试完成，退出代码: {exit_code}")
    sys.exit(exit_code)