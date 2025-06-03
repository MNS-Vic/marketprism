#!/usr/bin/env python3
"""
MarketPrism Collector TDD 测试执行脚本

按照TDD计划分阶段执行测试，生成详细报告
"""

import os
import sys
import subprocess
import time
import json
from datetime import datetime
from pathlib import Path
import argparse

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TDDTestRunner:
    """TDD测试运行器"""
    
    def __init__(self):
        self.project_root = project_root
        self.test_results = {}
        self.start_time = datetime.now()
        
    def run_phase(self, phase_name: str, test_patterns: list, description: str = ""):
        """运行测试阶段"""
        print(f"\n{'='*60}")
        print(f"🧪 执行测试阶段: {phase_name}")
        print(f"📝 描述: {description}")
        print(f"{'='*60}")
        
        phase_start = time.time()
        phase_results = {
            'description': description,
            'start_time': datetime.now().isoformat(),
            'test_files': {},
            'summary': {}
        }
        
        total_tests = 0
        total_passed = 0
        total_failed = 0
        total_skipped = 0
        
        for pattern in test_patterns:
            print(f"\n📁 运行测试模式: {pattern}")
            
            # 构建pytest命令
            cmd = [
                sys.executable, "-m", "pytest",
                pattern,
                "-v",
                "--tb=short",
                "--json-report",
                f"--json-report-file={self.project_root}/tests/reports/{phase_name}_{pattern.replace('/', '_').replace('*', 'all')}.json",
                "--html={}/tests/reports/{}_report.html".format(self.project_root, phase_name),
                "--self-contained-html",
                "--cov=services.python_collector.src.marketprism_collector",
                f"--cov-report=html:{self.project_root}/tests/reports/{phase_name}_coverage",
                "--cov-report=json",
                "--timeout=120"
            ]
            
            try:
                result = subprocess.run(
                    cmd,
                    cwd=self.project_root,
                    capture_output=True,
                    text=True,
                    timeout=600  # 10分钟超时
                )
                
                # 解析结果
                if result.returncode == 0:
                    status = "✅ PASSED"
                    print(f"   {status}")
                elif result.returncode == 5:  # pytest没有找到测试
                    status = "⚠️ NO TESTS"
                    print(f"   {status} - 没有找到测试文件")
                else:
                    status = "❌ FAILED"
                    print(f"   {status}")
                    print(f"   错误输出: {result.stderr[:500]}")
                
                # 尝试读取JSON报告
                json_report_path = f"{self.project_root}/tests/reports/{phase_name}_{pattern.replace('/', '_').replace('*', 'all')}.json"
                test_stats = self._parse_json_report(json_report_path)
                
                phase_results['test_files'][pattern] = {
                    'status': status,
                    'return_code': result.returncode,
                    'stdout': result.stdout[-1000:] if result.stdout else "",
                    'stderr': result.stderr[-500:] if result.stderr else "",
                    'stats': test_stats
                }
                
                # 累计统计
                if test_stats:
                    total_tests += test_stats.get('total', 0)
                    total_passed += test_stats.get('passed', 0)
                    total_failed += test_stats.get('failed', 0)
                    total_skipped += test_stats.get('skipped', 0)
                
            except subprocess.TimeoutExpired:
                print(f"   ⏰ TIMEOUT - 测试超时")
                phase_results['test_files'][pattern] = {
                    'status': 'TIMEOUT',
                    'return_code': -1,
                    'error': 'Test execution timeout'
                }
            except Exception as e:
                print(f"   💥 ERROR - {e}")
                phase_results['test_files'][pattern] = {
                    'status': 'ERROR',
                    'return_code': -1,
                    'error': str(e)
                }
        
        phase_end = time.time()
        phase_duration = phase_end - phase_start
        
        # 阶段总结
        phase_results['summary'] = {
            'total_tests': total_tests,
            'passed': total_passed,
            'failed': total_failed,
            'skipped': total_skipped,
            'duration_seconds': phase_duration,
            'success_rate': (total_passed / total_tests * 100) if total_tests > 0 else 0
        }
        
        phase_results['end_time'] = datetime.now().isoformat()
        
        # 显示阶段总结
        print(f"\n📊 阶段 {phase_name} 总结:")
        print(f"   总测试数: {total_tests}")
        print(f"   通过: {total_passed}")
        print(f"   失败: {total_failed}")
        print(f"   跳过: {total_skipped}")
        print(f"   成功率: {phase_results['summary']['success_rate']:.1f}%")
        print(f"   耗时: {phase_duration:.1f}秒")
        
        self.test_results[phase_name] = phase_results
        return phase_results
    
    def _parse_json_report(self, json_path: str) -> dict:
        """解析pytest JSON报告"""
        try:
            if os.path.exists(json_path):
                with open(json_path, 'r') as f:
                    data = json.load(f)
                
                summary = data.get('summary', {})
                return {
                    'total': summary.get('total', 0),
                    'passed': summary.get('passed', 0),
                    'failed': summary.get('failed', 0),
                    'skipped': summary.get('skipped', 0),
                    'error': summary.get('error', 0)
                }
        except Exception as e:
            print(f"   解析JSON报告失败: {e}")
        
        return {}
    
    def run_all_phases(self):
        """运行所有测试阶段"""
        print(f"🚀 开始 MarketPrism Collector TDD 测试")
        print(f"⏰ 开始时间: {self.start_time}")
        
        # 确保报告目录存在
        os.makedirs(f"{self.project_root}/tests/reports", exist_ok=True)
        
        # Phase 1: 单元测试
        self.run_phase(
            "phase1_unit",
            [
                "tests/unit/collector/test_core_integration.py",
                "tests/unit/collector/*.py"
            ],
            "验证各个组件的独立功能和Core模块集成"
        )
        
        # Phase 2: 集成测试
        self.run_phase(
            "phase2_integration", 
            [
                "tests/integration/collector/test_exchange_adapters.py",
                "tests/integration/collector/*.py"
            ],
            "验证组件间的交互和交易所连接"
        )
        
        # Phase 3: 端到端测试
        self.run_phase(
            "phase3_e2e",
            [
                "tests/e2e/collector/test_real_data_collection.py"
            ],
            "验证完整的数据收集流程"
        )
        
        # Phase 4: 性能和稳定性测试（可选）
        if self._should_run_performance_tests():
            self.run_phase(
                "phase4_performance",
                [
                    "tests/performance/collector/*.py"
                ],
                "验证系统在高负载下的表现"
            )
        
        # 生成最终报告
        self.generate_final_report()
    
    def _should_run_performance_tests(self) -> bool:
        """判断是否应该运行性能测试"""
        # 如果前面的测试通过率低于80%，跳过性能测试
        overall_success_rate = self._calculate_overall_success_rate()
        return overall_success_rate >= 80.0
    
    def _calculate_overall_success_rate(self) -> float:
        """计算整体成功率"""
        total_tests = 0
        total_passed = 0
        
        for phase_result in self.test_results.values():
            summary = phase_result.get('summary', {})
            total_tests += summary.get('total_tests', 0)
            total_passed += summary.get('passed', 0)
        
        return (total_passed / total_tests * 100) if total_tests > 0 else 0
    
    def generate_final_report(self):
        """生成最终测试报告"""
        end_time = datetime.now()
        total_duration = (end_time - self.start_time).total_seconds()
        
        overall_success_rate = self._calculate_overall_success_rate()
        
        final_report = {
            'test_run_info': {
                'start_time': self.start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'total_duration_seconds': total_duration,
                'overall_success_rate': overall_success_rate
            },
            'phases': self.test_results,
            'recommendations': self._generate_recommendations()
        }
        
        # 保存详细报告
        report_path = f"{self.project_root}/tests/reports/tdd_final_report.json"
        with open(report_path, 'w') as f:
            json.dump(final_report, f, indent=2, ensure_ascii=False)
        
        # 显示最终总结
        print(f"\n{'='*80}")
        print(f"🎯 MarketPrism Collector TDD 测试完成")
        print(f"{'='*80}")
        print(f"⏰ 总耗时: {total_duration:.1f}秒")
        print(f"📊 整体成功率: {overall_success_rate:.1f}%")
        
        # 显示各阶段结果
        for phase_name, phase_result in self.test_results.items():
            summary = phase_result['summary']
            status_emoji = "✅" if summary['success_rate'] >= 80 else "⚠️" if summary['success_rate'] >= 60 else "❌"
            print(f"{status_emoji} {phase_name}: {summary['success_rate']:.1f}% ({summary['passed']}/{summary['total_tests']})")
        
        # 显示建议
        recommendations = final_report['recommendations']
        if recommendations:
            print(f"\n💡 改进建议:")
            for i, rec in enumerate(recommendations, 1):
                print(f"   {i}. {rec}")
        
        print(f"\n📄 详细报告: {report_path}")
        
        # 返回成功状态
        return overall_success_rate >= 80.0
    
    def _generate_recommendations(self) -> list:
        """生成改进建议"""
        recommendations = []
        overall_success_rate = self._calculate_overall_success_rate()
        
        if overall_success_rate < 60:
            recommendations.append("整体测试通过率过低，需要重点检查核心功能实现")
        elif overall_success_rate < 80:
            recommendations.append("部分测试失败，建议优先修复失败的测试用例")
        
        # 分析各阶段
        for phase_name, phase_result in self.test_results.items():
            summary = phase_result['summary']
            if summary['success_rate'] < 60:
                recommendations.append(f"{phase_name} 阶段问题严重，需要重点关注")
            elif summary['failed'] > 0:
                recommendations.append(f"{phase_name} 阶段有 {summary['failed']} 个测试失败，需要修复")
        
        # 检查跳过的测试
        total_skipped = sum(phase['summary']['skipped'] for phase in self.test_results.values())
        if total_skipped > 10:
            recommendations.append(f"有 {total_skipped} 个测试被跳过，可能需要解决环境依赖问题")
        
        return recommendations


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="MarketPrism Collector TDD 测试执行器")
    parser.add_argument("--phase", choices=["unit", "integration", "e2e", "performance", "all"], 
                       default="all", help="指定要运行的测试阶段")
    parser.add_argument("--fast", action="store_true", help="快速模式，跳过耗时的测试")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    
    args = parser.parse_args()
    
    runner = TDDTestRunner()
    
    if args.phase == "all":
        success = runner.run_all_phases()
    else:
        # 运行指定阶段
        phase_map = {
            "unit": ("phase1_unit", ["tests/unit/collector/*.py"], "单元测试"),
            "integration": ("phase2_integration", ["tests/integration/collector/*.py"], "集成测试"),
            "e2e": ("phase3_e2e", ["tests/e2e/collector/*.py"], "端到端测试"),
            "performance": ("phase4_performance", ["tests/performance/collector/*.py"], "性能测试")
        }
        
        if args.phase in phase_map:
            phase_name, patterns, description = phase_map[args.phase]
            result = runner.run_phase(phase_name, patterns, description)
            success = result['summary']['success_rate'] >= 80.0
        else:
            print(f"未知的测试阶段: {args.phase}")
            return 1
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())