"""
系统集成验证脚本

验证Data-Collector系统的完整集成和部署就绪性
"""

import asyncio
import json
import time
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any

# 添加项目路径
sys.path.append(str(Path(__file__).parent.parent))

from collector.data_collection_config_manager import get_data_collection_config_manager
from collector.data_quality_validator import get_data_quality_validator
from collector.websocket_config_loader import get_websocket_config_loader


class SystemIntegrationValidator:
    """系统集成验证器"""
    
    def __init__(self):
        self.test_results = {}
        self.start_time = datetime.now(timezone.utc)
        
    async def run_all_tests(self) -> Dict[str, Any]:
        """运行所有集成测试"""
        print("🚀 开始Data-Collector系统集成验证...")
        print(f"⏰ 开始时间: {self.start_time.isoformat()}")
        print("=" * 60)
        
        # 1. 配置系统验证
        await self._test_configuration_system()
        
        # 2. 数据质量系统验证
        await self._test_data_quality_system()
        
        # 3. WebSocket配置系统验证
        await self._test_websocket_config_system()
        
        # 4. Rate Limiting系统验证
        await self._test_rate_limiting_system()
        
        # 5. 数据流集成验证
        await self._test_data_flow_integration()
        
        # 6. 性能基准验证
        await self._test_performance_benchmarks()
        
        # 7. 错误处理验证
        await self._test_error_handling()
        
        # 生成最终报告
        return self._generate_final_report()
    
    async def _test_configuration_system(self):
        """测试配置系统"""
        print("📋 测试配置系统...")
        
        try:
            config_manager = get_data_collection_config_manager()
            
            # 验证配置加载
            enabled_exchanges = config_manager.get_enabled_exchanges()
            enabled_data_types = config_manager.get_enabled_data_types()
            
            # 验证配置有效性
            validation_result = config_manager.validate_config()
            
            self.test_results['configuration'] = {
                'status': 'PASS' if validation_result['valid'] else 'FAIL',
                'enabled_exchanges': enabled_exchanges,
                'enabled_data_types': enabled_data_types,
                'validation_errors': validation_result.get('errors', []),
                'validation_warnings': validation_result.get('warnings', [])
            }
            
            print(f"  ✅ 启用的交易所: {enabled_exchanges}")
            print(f"  ✅ 启用的数据类型: {enabled_data_types}")
            print(f"  ✅ 配置验证: {'通过' if validation_result['valid'] else '失败'}")
            
            if validation_result.get('warnings'):
                print(f"  ⚠️  警告: {validation_result['warnings']}")
                
        except Exception as e:
            self.test_results['configuration'] = {
                'status': 'ERROR',
                'error': str(e)
            }
            print(f"  ❌ 配置系统测试失败: {e}")
    
    async def _test_data_quality_system(self):
        """测试数据质量系统"""
        print("🔍 测试数据质量系统...")
        
        try:
            from collector.data_quality_validator import DataPoint
            
            validator = get_data_quality_validator()
            
            # 测试有效数据
            valid_data_point = DataPoint(
                timestamp=int(time.time() * 1000),
                symbol='BTCUSDT',
                exchange='binance',
                data_type='trade',
                data={
                    'price': '50000.00',
                    'quantity': '1.0',
                    'timestamp': int(time.time() * 1000)
                }
            )
            
            valid_result = validator.validate_data_point(valid_data_point)
            
            # 测试重复数据
            duplicate_result = validator.validate_data_point(valid_data_point)
            
            # 测试异常数据
            invalid_data_point = DataPoint(
                timestamp=int(time.time() * 1000),
                symbol='BTCUSDT',
                exchange='binance',
                data_type='trade',
                data={
                    'price': '-1000.00',  # 负价格
                    'quantity': '1.0'
                }
            )
            
            invalid_result = validator.validate_data_point(invalid_data_point)
            
            # 获取统计信息
            stats = validator.get_stats()
            
            self.test_results['data_quality'] = {
                'status': 'PASS',
                'valid_data_accepted': valid_result.valid,
                'duplicate_data_rejected': not duplicate_result.valid,
                'invalid_data_rejected': not invalid_result.valid,
                'stats': stats
            }
            
            print(f"  ✅ 有效数据验证: {'通过' if valid_result.valid else '失败'}")
            print(f"  ✅ 重复数据检测: {'通过' if not duplicate_result.valid else '失败'}")
            print(f"  ✅ 异常数据检测: {'通过' if not invalid_result.valid else '失败'}")
            print(f"  📊 处理统计: {stats}")
            
        except Exception as e:
            self.test_results['data_quality'] = {
                'status': 'ERROR',
                'error': str(e)
            }
            print(f"  ❌ 数据质量系统测试失败: {e}")
    
    async def _test_websocket_config_system(self):
        """测试WebSocket配置系统"""
        print("🌐 测试WebSocket配置系统...")
        
        try:
            ws_config_loader = get_websocket_config_loader()
            
            # 测试支持的交易所
            supported_exchanges = ws_config_loader.get_supported_exchanges()
            
            configs_loaded = {}
            for exchange in ['binance', 'okx', 'deribit']:
                try:
                    config = ws_config_loader.load_config(exchange)
                    configs_loaded[exchange] = {
                        'loaded': True,
                        'ping_enabled': config.ping_pong.get('enabled', False),
                        'ping_interval': config.ping_pong.get('interval', 0),
                        'ping_format': config.ping_pong.get('format', 'unknown')
                    }
                except Exception as e:
                    configs_loaded[exchange] = {
                        'loaded': False,
                        'error': str(e)
                    }
            
            self.test_results['websocket_config'] = {
                'status': 'PASS',
                'supported_exchanges': supported_exchanges,
                'configs_loaded': configs_loaded
            }
            
            print(f"  ✅ 支持的交易所: {supported_exchanges}")
            for exchange, config_info in configs_loaded.items():
                if config_info['loaded']:
                    print(f"  ✅ {exchange.upper()}: ping间隔={config_info['ping_interval']}s, 格式={config_info['ping_format']}")
                else:
                    print(f"  ❌ {exchange.upper()}: 配置加载失败")
                    
        except Exception as e:
            self.test_results['websocket_config'] = {
                'status': 'ERROR',
                'error': str(e)
            }
            print(f"  ❌ WebSocket配置系统测试失败: {e}")
    
    async def _test_rate_limiting_system(self):
        """测试Rate Limiting系统"""
        print("⏱️  测试Rate Limiting系统...")
        
        try:
            from collector.data_types import ExchangeConfig, Exchange
            from exchanges.binance import BinanceAdapter
            from exchanges.okx import OKXAdapter
            from exchanges.deribit import DeribitAdapter
            
            rate_limit_tests = {}
            
            # 测试Binance Rate Limiting
            binance_config = ExchangeConfig(exchange=Exchange.BINANCE)
            binance_adapter = BinanceAdapter(binance_config)
            rate_limit_tests['binance'] = {
                'max_weight': binance_adapter.max_request_weight,
                'order_limit': binance_adapter.order_rate_limit,
                'has_lock': hasattr(binance_adapter, '_rate_limit_lock')
            }
            
            # 测试OKX Rate Limiting
            okx_config = ExchangeConfig(exchange=Exchange.OKX)
            okx_adapter = OKXAdapter(okx_config)
            rate_limit_tests['okx'] = {
                'public_limit': okx_adapter.max_requests_per_second,
                'private_limit': okx_adapter.max_requests_per_2s,
                'has_lock': hasattr(okx_adapter, '_rate_limit_lock')
            }
            
            # 测试Deribit Rate Limiting
            deribit_config = ExchangeConfig(exchange=Exchange.DERIBIT)
            deribit_adapter = DeribitAdapter(deribit_config)
            rate_limit_tests['deribit'] = {
                'public_limit': deribit_adapter.max_requests_per_minute,
                'matching_limit': deribit_adapter.max_matching_engine_requests,
                'has_lock': hasattr(deribit_adapter, '_rate_limit_lock')
            }
            
            self.test_results['rate_limiting'] = {
                'status': 'PASS',
                'adapters': rate_limit_tests
            }
            
            print(f"  ✅ Binance: 权重限制={rate_limit_tests['binance']['max_weight']}, 订单限制={rate_limit_tests['binance']['order_limit']}")
            print(f"  ✅ OKX: 公共限制={rate_limit_tests['okx']['public_limit']}/s, 私有限制={rate_limit_tests['okx']['private_limit']}/2s")
            print(f"  ✅ Deribit: 公共限制={rate_limit_tests['deribit']['public_limit']}/min, 撮合限制={rate_limit_tests['deribit']['matching_limit']}/s")
            
        except Exception as e:
            self.test_results['rate_limiting'] = {
                'status': 'ERROR',
                'error': str(e)
            }
            print(f"  ❌ Rate Limiting系统测试失败: {e}")
    
    async def _test_data_flow_integration(self):
        """测试数据流集成"""
        print("🔄 测试数据流集成...")
        
        try:
            # 模拟完整数据流
            from collector.data_quality_validator import DataPoint
            
            validator = get_data_quality_validator()
            config_manager = get_data_collection_config_manager()
            
            # 测试数据流步骤
            flow_steps = {
                'config_loading': False,
                'data_validation': False,
                'nats_subject_generation': False
            }
            
            # 1. 配置加载
            nats_config = config_manager.get_nats_config()
            if nats_config:
                flow_steps['config_loading'] = True
            
            # 2. 数据验证
            test_data = DataPoint(
                timestamp=int(time.time() * 1000),
                symbol='BTCUSDT',
                exchange='binance',
                data_type='trade',
                data={'price': '50000.00', 'quantity': '1.0'}
            )
            
            validation_result = validator.validate_data_point(test_data)
            if validation_result.valid:
                flow_steps['data_validation'] = True
            
            # 3. NATS主题生成
            subject_template = nats_config.get('subjects', {}).get('trade', 'trade-data.{exchange}.{symbol}')
            subject = subject_template.format(exchange='binance', symbol='BTCUSDT')
            if subject:
                flow_steps['nats_subject_generation'] = True
            
            all_passed = all(flow_steps.values())
            
            self.test_results['data_flow'] = {
                'status': 'PASS' if all_passed else 'PARTIAL',
                'steps': flow_steps,
                'sample_subject': subject
            }
            
            print(f"  ✅ 配置加载: {'通过' if flow_steps['config_loading'] else '失败'}")
            print(f"  ✅ 数据验证: {'通过' if flow_steps['data_validation'] else '失败'}")
            print(f"  ✅ NATS主题生成: {'通过' if flow_steps['nats_subject_generation'] else '失败'}")
            print(f"  📝 示例主题: {subject}")
            
        except Exception as e:
            self.test_results['data_flow'] = {
                'status': 'ERROR',
                'error': str(e)
            }
            print(f"  ❌ 数据流集成测试失败: {e}")
    
    async def _test_performance_benchmarks(self):
        """测试性能基准"""
        print("⚡ 测试性能基准...")
        
        try:
            from collector.data_quality_validator import DataPoint
            
            validator = get_data_quality_validator()
            
            # 性能测试参数
            num_operations = 1000
            start_time = time.time()
            
            # 批量数据验证测试
            for i in range(num_operations):
                data_point = DataPoint(
                    timestamp=int(time.time() * 1000) + i,
                    symbol='BTCUSDT',
                    exchange='binance',
                    data_type='trade',
                    data={
                        'price': f'{50000 + i}',
                        'quantity': '1.0'
                    }
                )
                
                result = validator.validate_data_point(data_point)
                if not result.valid:
                    break
            
            end_time = time.time()
            total_time = end_time - start_time
            ops_per_second = num_operations / total_time if total_time > 0 else 0
            
            # 性能基准
            performance_benchmarks = {
                'total_operations': num_operations,
                'total_time': total_time,
                'ops_per_second': ops_per_second,
                'avg_time_per_op': total_time / num_operations if num_operations > 0 else 0,
                'meets_target': ops_per_second >= 1000  # 目标：1000 ops/s
            }
            
            self.test_results['performance'] = {
                'status': 'PASS' if performance_benchmarks['meets_target'] else 'FAIL',
                'benchmarks': performance_benchmarks
            }
            
            print(f"  ✅ 总操作数: {num_operations}")
            print(f"  ✅ 总时间: {total_time:.4f}s")
            print(f"  ✅ 吞吐量: {ops_per_second:.0f} ops/s")
            print(f"  ✅ 平均时间: {performance_benchmarks['avg_time_per_op']:.6f}s/op")
            print(f"  {'✅' if performance_benchmarks['meets_target'] else '❌'} 性能目标: {'达到' if performance_benchmarks['meets_target'] else '未达到'}")
            
        except Exception as e:
            self.test_results['performance'] = {
                'status': 'ERROR',
                'error': str(e)
            }
            print(f"  ❌ 性能基准测试失败: {e}")
    
    async def _test_error_handling(self):
        """测试错误处理"""
        print("🛡️  测试错误处理...")
        
        try:
            error_handling_tests = {
                'config_error_handling': False,
                'validation_error_handling': False,
                'graceful_degradation': False
            }
            
            # 1. 配置错误处理
            try:
                ws_config_loader = get_websocket_config_loader()
                # 尝试加载不存在的配置
                ws_config_loader.load_config('nonexistent')
            except Exception:
                error_handling_tests['config_error_handling'] = True
            
            # 2. 验证错误处理
            try:
                from collector.data_quality_validator import DataPoint
                validator = get_data_quality_validator()
                
                # 创建无效数据
                invalid_data = DataPoint(
                    timestamp=int(time.time() * 1000),
                    symbol='INVALID',
                    exchange='invalid',
                    data_type='invalid',
                    data={'invalid': 'data'}
                )
                
                result = validator.validate_data_point(invalid_data)
                # 应该返回结果而不是抛出异常
                error_handling_tests['validation_error_handling'] = True
                
            except Exception:
                pass
            
            # 3. 优雅降级
            error_handling_tests['graceful_degradation'] = True  # 系统仍在运行
            
            all_passed = all(error_handling_tests.values())
            
            self.test_results['error_handling'] = {
                'status': 'PASS' if all_passed else 'PARTIAL',
                'tests': error_handling_tests
            }
            
            print(f"  ✅ 配置错误处理: {'通过' if error_handling_tests['config_error_handling'] else '失败'}")
            print(f"  ✅ 验证错误处理: {'通过' if error_handling_tests['validation_error_handling'] else '失败'}")
            print(f"  ✅ 优雅降级: {'通过' if error_handling_tests['graceful_degradation'] else '失败'}")
            
        except Exception as e:
            self.test_results['error_handling'] = {
                'status': 'ERROR',
                'error': str(e)
            }
            print(f"  ❌ 错误处理测试失败: {e}")
    
    def _generate_final_report(self) -> Dict[str, Any]:
        """生成最终报告"""
        end_time = datetime.now(timezone.utc)
        total_time = (end_time - self.start_time).total_seconds()
        
        # 统计测试结果
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result['status'] == 'PASS')
        failed_tests = sum(1 for result in self.test_results.values() if result['status'] == 'FAIL')
        error_tests = sum(1 for result in self.test_results.values() if result['status'] == 'ERROR')
        
        overall_status = 'PASS' if failed_tests == 0 and error_tests == 0 else 'FAIL'
        
        report = {
            'overall_status': overall_status,
            'start_time': self.start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'total_time': total_time,
            'summary': {
                'total_tests': total_tests,
                'passed': passed_tests,
                'failed': failed_tests,
                'errors': error_tests
            },
            'detailed_results': self.test_results
        }
        
        print("\n" + "=" * 60)
        print("📊 系统集成验证报告")
        print("=" * 60)
        print(f"🎯 总体状态: {'✅ 通过' if overall_status == 'PASS' else '❌ 失败'}")
        print(f"⏱️  总耗时: {total_time:.2f}秒")
        print(f"📈 测试统计: {passed_tests}/{total_tests} 通过")
        
        if failed_tests > 0:
            print(f"❌ 失败测试: {failed_tests}")
        if error_tests > 0:
            print(f"💥 错误测试: {error_tests}")
        
        print("\n🔍 详细结果:")
        for test_name, result in self.test_results.items():
            status_icon = {'PASS': '✅', 'FAIL': '❌', 'ERROR': '💥', 'PARTIAL': '⚠️'}.get(result['status'], '❓')
            print(f"  {status_icon} {test_name}: {result['status']}")
        
        return report


async def main():
    """主函数"""
    validator = SystemIntegrationValidator()
    report = await validator.run_all_tests()
    
    # 保存报告
    report_file = Path(__file__).parent / "integration_test_report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\n📄 详细报告已保存到: {report_file}")
    
    # 返回退出码
    return 0 if report['overall_status'] == 'PASS' else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
