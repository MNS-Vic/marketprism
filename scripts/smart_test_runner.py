#!/usr/bin/env python3
"""
智能测试运行器 - 基于代码变更智能选择需要运行的测试
"""

import os
import sys
import subprocess
import json
from pathlib import Path
from typing import Set, List, Dict
import ast
import re

class SmartTestRunner:
    def __init__(self, base_branch: str = "main"):
        self.base_branch = base_branch
        self.project_root = Path(__file__).parent.parent
        self.is_ci = os.getenv('CI') or os.getenv('GITHUB_ACTIONS')
        self.test_mapping = self._build_test_mapping()
    
    def _build_test_mapping(self) -> Dict[str, Set[str]]:
        """构建代码文件到测试文件的映射关系"""
        mapping = {}
        
        # 扫描所有Python文件，分析导入关系
        for py_file in self.project_root.rglob("*.py"):
            if "test" in str(py_file) or "__pycache__" in str(py_file):
                continue
            
            relative_path = str(py_file.relative_to(self.project_root))
            mapping[relative_path] = set()
            
            # 查找对应的测试文件
            test_patterns = [
                f"tests/unit/{relative_path.replace('.py', '')}/test_*.py",
                f"tests/unit/test_{py_file.stem}.py",
                f"tests/integration/test_{py_file.stem}.py",
            ]
            
            for pattern in test_patterns:
                test_files = list(self.project_root.glob(pattern))
                for test_file in test_files:
                    mapping[relative_path].add(str(test_file.relative_to(self.project_root)))
        
        return mapping
    
    def get_changed_files(self) -> Set[str]:
        """获取相对于基础分支的变更文件"""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", f"{self.base_branch}...HEAD"],
                capture_output=True,
                text=True,
                cwd=self.project_root
            )
            
            if result.returncode != 0:
                print(f"Warning: Could not get git diff: {result.stderr}")
                return set()
            
            changed_files = set()
            for line in result.stdout.strip().split('\n'):
                if line and line.endswith('.py'):
                    changed_files.add(line)
            
            return changed_files
        
        except Exception as e:
            print(f"Error getting changed files: {e}")
            return set()
    
    def get_affected_tests(self, changed_files: Set[str]) -> Set[str]:
        """根据变更文件获取需要运行的测试"""
        affected_tests = set()
        
        for changed_file in changed_files:
            # 直接映射的测试
            if changed_file in self.test_mapping:
                affected_tests.update(self.test_mapping[changed_file])
            
            # 如果是测试文件本身
            if "test" in changed_file:
                affected_tests.add(changed_file)
            
            # 分析依赖关系
            affected_tests.update(self._find_dependent_tests(changed_file))
        
        return affected_tests
    
    def _find_dependent_tests(self, changed_file: str) -> Set[str]:
        """查找依赖于变更文件的测试"""
        dependent_tests = set()
        
        # 简化的依赖分析 - 基于模块路径
        module_path = changed_file.replace('/', '.').replace('.py', '')
        
        # 搜索所有测试文件中的导入
        for test_file in self.project_root.rglob("test_*.py"):
            try:
                with open(test_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # 检查是否导入了变更的模块
                if module_path in content or changed_file in content:
                    relative_test_path = str(test_file.relative_to(self.project_root))
                    dependent_tests.add(relative_test_path)
            
            except Exception:
                continue
        
        return dependent_tests
    
    def categorize_tests(self, test_files: Set[str]) -> Dict[str, List[str]]:
        """将测试文件按类型分类"""
        categories = {
            'unit': [],
            'integration': [],
            'performance': [],
            'e2e': []
        }
        
        for test_file in test_files:
            if 'unit' in test_file:
                categories['unit'].append(test_file)
            elif 'integration' in test_file:
                categories['integration'].append(test_file)
            elif 'performance' in test_file:
                categories['performance'].append(test_file)
            elif 'e2e' in test_file:
                categories['e2e'].append(test_file)
            else:
                categories['unit'].append(test_file)  # 默认为单元测试
        
        return categories
    
    def estimate_test_time(self, test_files: Set[str]) -> Dict[str, float]:
        """估算测试运行时间"""
        time_estimates = {}
        
        for test_file in test_files:
            # 基于测试类型和文件大小估算时间
            try:
                file_path = self.project_root / test_file
                if file_path.exists():
                    file_size = file_path.stat().st_size
                    
                    if 'unit' in test_file:
                        # 单元测试：每KB约0.1秒
                        estimated_time = (file_size / 1024) * 0.1
                    elif 'integration' in test_file:
                        # 集成测试：每KB约0.5秒
                        estimated_time = (file_size / 1024) * 0.5
                    elif 'performance' in test_file:
                        # 性能测试：每KB约2秒
                        estimated_time = (file_size / 1024) * 2.0
                    else:
                        estimated_time = (file_size / 1024) * 0.2
                    
                    time_estimates[test_file] = max(1.0, estimated_time)
                else:
                    time_estimates[test_file] = 5.0  # 默认5秒
            
            except Exception:
                time_estimates[test_file] = 5.0
        
        return time_estimates
    
    def generate_test_plan(self) -> Dict:
        """生成智能测试计划"""
        changed_files = self.get_changed_files()
        
        if not changed_files:
            print("No Python files changed, running minimal test suite")
            # 运行关键路径测试
            critical_tests = {
                'tests/unit/core/test_health_check.py',
                'tests/unit/services/data_collector/test_collector_basic.py'
            }
            affected_tests = {t for t in critical_tests if (self.project_root / t).exists()}
        else:
            affected_tests = self.get_affected_tests(changed_files)
        
        if not affected_tests:
            print("No tests found for changed files, running smoke tests")
            affected_tests = {'tests/unit/core/', 'tests/unit/services/'}
        
        categorized_tests = self.categorize_tests(affected_tests)
        time_estimates = self.estimate_test_time(affected_tests)
        
        total_estimated_time = sum(time_estimates.values())
        
        test_plan = {
            'changed_files': list(changed_files),
            'affected_tests': list(affected_tests),
            'categorized_tests': categorized_tests,
            'time_estimates': time_estimates,
            'total_estimated_time': total_estimated_time,
            'parallel_execution_recommended': total_estimated_time > 60,
            'test_strategy': self._determine_test_strategy(categorized_tests, total_estimated_time)
        }
        
        return test_plan
    
    def _determine_test_strategy(self, categorized_tests: Dict, total_time: float) -> str:
        """确定测试策略"""
        unit_count = len(categorized_tests['unit'])
        integration_count = len(categorized_tests['integration'])

        # CI环境下使用更保守的策略
        if self.is_ci:
            if total_time < 60:
                return "ci_fast"  # CI快速模式
            elif total_time < 180:
                return "ci_standard"  # CI标准模式
            else:
                return "ci_comprehensive"  # CI全面模式
        else:
            # 本地开发环境
            if total_time < 30:
                return "fast"  # 快速测试，串行执行
            elif total_time < 120:
                return "standard"  # 标准测试，部分并行
            else:
                return "comprehensive"  # 全面测试，最大并行度
    
    def run_tests(self, test_plan: Dict) -> bool:
        """根据测试计划运行测试"""
        print(f"🚀 Running smart test plan:")
        print(f"  - Strategy: {test_plan['test_strategy']}")
        print(f"  - Estimated time: {test_plan['total_estimated_time']:.1f}s")
        print(f"  - Tests to run: {len(test_plan['affected_tests'])}")
        
        categorized = test_plan['categorized_tests']
        strategy = test_plan['test_strategy']
        
        success = True
        
        # 根据策略执行测试
        if strategy in ["fast", "ci_fast"]:
            success &= self._run_test_category("unit", categorized['unit'], parallel=False)

        elif strategy in ["standard", "ci_standard"]:
            success &= self._run_test_category("unit", categorized['unit'], parallel=True)
            if success and categorized['integration']:
                # CI环境下集成测试也并行执行，但限制并发数
                parallel_integration = strategy == "ci_standard"
                success &= self._run_test_category("integration", categorized['integration'],
                                                 parallel=parallel_integration)

        else:  # comprehensive or ci_comprehensive
            success &= self._run_test_category("unit", categorized['unit'], parallel=True)
            if success and categorized['integration']:
                success &= self._run_test_category("integration", categorized['integration'], parallel=True)
            if success and categorized['performance'] and not self.is_ci:
                # CI环境跳过性能测试，避免资源竞争
                success &= self._run_test_category("performance", categorized['performance'], parallel=False)
        
        return success
    
    def _run_test_category(self, category: str, test_files: List[str], parallel: bool = False) -> bool:
        """运行特定类别的测试"""
        if not test_files:
            return True
        
        print(f"\n📋 Running {category} tests ({len(test_files)} files)")
        
        cmd = ["python", "-m", "pytest"]

        if parallel and len(test_files) > 1:
            if self.is_ci:
                # CI环境限制并发数，避免资源竞争
                cmd.extend(["-n", "2"])
            else:
                cmd.extend(["-n", "auto"])  # pytest-xdist并行执行

        cmd.extend(test_files)
        cmd.extend(["-v", "--tb=short"])

        # CI环境添加额外的报告和超时设置
        if self.is_ci:
            cmd.extend([
                "--timeout=300",
                "--junitxml=tests/reports/junit-{}.xml".format(category),
                "--html=tests/reports/report-{}.html".format(category),
                "--self-contained-html"
            ])

        if category == "unit":
            cmd.extend(["--cov=core/", "--cov=services/", "--cov-report=term-missing"])
            if self.is_ci:
                cmd.extend([
                    "--cov-report=xml:tests/reports/coverage-{}.xml".format(category),
                    "--cov-report=json:tests/reports/coverage-{}.json".format(category)
                ])

        # 添加CI环境特定的标记过滤
        if self.is_ci and category == "integration":
            cmd.extend(["-m", "not slow and not performance"])
        
        try:
            result = subprocess.run(cmd, cwd=self.project_root)
            success = result.returncode == 0
            
            if success:
                print(f"✅ {category} tests passed")
            else:
                print(f"❌ {category} tests failed")
            
            return success
        
        except Exception as e:
            print(f"❌ Error running {category} tests: {e}")
            return False

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Smart test runner for MarketPrism")
    parser.add_argument("--base-branch", default="main", help="Base branch for comparison")
    parser.add_argument("--plan-only", action="store_true", help="Only generate test plan, don't run tests")
    parser.add_argument("--output", help="Output test plan to JSON file")
    
    args = parser.parse_args()
    
    runner = SmartTestRunner(base_branch=args.base_branch)
    test_plan = runner.generate_test_plan()
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(test_plan, f, indent=2)
        print(f"Test plan saved to {args.output}")
    
    if args.plan_only:
        print(json.dumps(test_plan, indent=2))
        return
    
    success = runner.run_tests(test_plan)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
