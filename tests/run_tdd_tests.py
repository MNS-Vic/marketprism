#!/usr/bin/env python3
"""
MarketPrism TDD测试运行器
运行TDD测试套件并生成覆盖率报告
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path
from typing import List, Dict, Any

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "services" / "data-collector" / "src"))

def setup_environment():
    """设置测试环境"""
    os.environ["MARKETPRISM_ENV"] = "test"
    os.environ["MARKETPRISM_LOG_LEVEL"] = "DEBUG"
    os.environ["MARKETPRISM_TEST_MODE"] = "true"
    os.environ["PYTHONPATH"] = f"{project_root}:{project_root}/services/data-collector/src"
    
    print("🔧 测试环境已设置")
    print(f"   PYTHONPATH: {os.environ['PYTHONPATH']}")
    print(f"   MARKETPRISM_ENV: {os.environ['MARKETPRISM_ENV']}")


def run_unit_tests(verbose: bool = False, coverage: bool = True) -> bool:
    """运行单元测试"""
    print("\n🧪 运行单元测试...")
    
    cmd = [
        "python", "-m", "pytest",
        "tests/unit/",
        "-v" if verbose else "-q",
        "--tb=short",
        "--asyncio-mode=auto"
    ]
    
    if coverage:
        cmd.extend([
            "--cov=core",
            "--cov=services", 
            "--cov-report=term-missing",
            "--cov-report=html:tests/reports/coverage_unit",
            "--cov-fail-under=10"  # 降低初始要求
        ])
    
    try:
        result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)
        
        print("📊 单元测试结果:")
        print(result.stdout)
        
        if result.stderr:
            print("⚠️ 警告/错误:")
            print(result.stderr)
            
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ 运行单元测试失败: {e}")
        return False


def run_integration_tests(verbose: bool = False) -> bool:
    """运行集成测试"""
    print("\n🔗 运行集成测试...")
    
    cmd = [
        "python", "-m", "pytest",
        "tests/integration/",
        "-v" if verbose else "-q",
        "--tb=short",
        "--asyncio-mode=auto",
        "-m", "integration"
    ]
    
    try:
        result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)
        
        print("📊 集成测试结果:")
        print(result.stdout)
        
        if result.stderr:
            print("⚠️ 警告/错误:")
            print(result.stderr)
            
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ 运行集成测试失败: {e}")
        return False


def run_specific_tests(test_pattern: str, verbose: bool = False) -> bool:
    """运行特定测试"""
    print(f"\n🎯 运行特定测试: {test_pattern}")
    
    cmd = [
        "python", "-m", "pytest",
        "-k", test_pattern,
        "-v" if verbose else "-q",
        "--tb=short",
        "--asyncio-mode=auto"
    ]
    
    try:
        result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)
        
        print("📊 测试结果:")
        print(result.stdout)
        
        if result.stderr:
            print("⚠️ 警告/错误:")
            print(result.stderr)
            
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ 运行特定测试失败: {e}")
        return False


def run_coverage_report() -> Dict[str, Any]:
    """生成覆盖率报告"""
    print("\n📈 生成覆盖率报告...")
    
    cmd = [
        "python", "-m", "pytest",
        "tests/unit/",
        "--cov=core",
        "--cov=services",
        "--cov-report=term-missing",
        "--cov-report=html:tests/reports/coverage",
        "--cov-report=json:tests/reports/coverage.json",
        "-q"
    ]
    
    try:
        result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)
        
        # 解析覆盖率信息
        coverage_info = {
            "success": result.returncode == 0,
            "output": result.stdout,
            "errors": result.stderr
        }
        
        # 尝试从输出中提取覆盖率百分比
        for line in result.stdout.split('\n'):
            if 'TOTAL' in line and '%' in line:
                parts = line.split()
                for part in parts:
                    if '%' in part:
                        coverage_info["total_coverage"] = part
                        break
                        
        return coverage_info
        
    except Exception as e:
        print(f"❌ 生成覆盖率报告失败: {e}")
        return {"success": False, "error": str(e)}


def check_test_dependencies() -> bool:
    """检查测试依赖"""
    print("🔍 检查测试依赖...")
    
    required_packages = [
        "pytest",
        "pytest-asyncio", 
        "pytest-cov",
        "aioresponses",
        "factory-boy"
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ 缺少测试依赖: {', '.join(missing_packages)}")
        print("请运行: pip install -r requirements-test.txt")
        return False
    
    print("✅ 所有测试依赖已安装")
    return True


def create_test_reports_dir():
    """创建测试报告目录"""
    reports_dir = project_root / "tests" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"📁 测试报告目录: {reports_dir}")


def print_test_summary(results: Dict[str, bool]):
    """打印测试摘要"""
    print("\n" + "="*60)
    print("📋 测试摘要")
    print("="*60)
    
    total_tests = len(results)
    passed_tests = sum(1 for result in results.values() if result)
    
    for test_type, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"   {test_type}: {status}")
    
    print(f"\n总计: {passed_tests}/{total_tests} 测试套件通过")
    
    if passed_tests == total_tests:
        print("🎉 所有测试都通过了！")
    else:
        print("⚠️ 部分测试失败，请检查上面的错误信息")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="MarketPrism TDD测试运行器")
    parser.add_argument("--unit", action="store_true", help="只运行单元测试")
    parser.add_argument("--integration", action="store_true", help="只运行集成测试")
    parser.add_argument("--coverage", action="store_true", help="生成覆盖率报告")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    parser.add_argument("--pattern", "-k", help="运行匹配模式的测试")
    parser.add_argument("--no-coverage", action="store_true", help="禁用覆盖率")
    
    args = parser.parse_args()
    
    print("🚀 MarketPrism TDD测试运行器")
    print("="*60)
    
    # 设置环境
    setup_environment()
    
    # 检查依赖
    if not check_test_dependencies():
        sys.exit(1)
    
    # 创建报告目录
    create_test_reports_dir()
    
    results = {}
    
    try:
        # 运行特定模式的测试
        if args.pattern:
            results["pattern_tests"] = run_specific_tests(args.pattern, args.verbose)
        
        # 运行单元测试
        elif args.unit or not (args.integration or args.coverage):
            enable_coverage = not args.no_coverage
            results["unit_tests"] = run_unit_tests(args.verbose, enable_coverage)
        
        # 运行集成测试
        elif args.integration:
            results["integration_tests"] = run_integration_tests(args.verbose)
        
        # 生成覆盖率报告
        elif args.coverage:
            coverage_result = run_coverage_report()
            results["coverage_report"] = coverage_result["success"]
            
            if coverage_result["success"]:
                print("✅ 覆盖率报告生成成功")
                if "total_coverage" in coverage_result:
                    print(f"📊 总覆盖率: {coverage_result['total_coverage']}")
            else:
                print("❌ 覆盖率报告生成失败")
        
        # 默认运行所有测试
        else:
            enable_coverage = not args.no_coverage
            results["unit_tests"] = run_unit_tests(args.verbose, enable_coverage)
            results["integration_tests"] = run_integration_tests(args.verbose)
            
            if enable_coverage:
                coverage_result = run_coverage_report()
                results["coverage_report"] = coverage_result["success"]
    
    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")
        sys.exit(1)
    
    except Exception as e:
        print(f"\n❌ 测试运行出错: {e}")
        sys.exit(1)
    
    # 打印摘要
    print_test_summary(results)
    
    # 设置退出码
    if all(results.values()):
        print("\n🎯 测试目标达成！")
        sys.exit(0)
    else:
        print("\n🔧 需要修复失败的测试")
        sys.exit(1)


if __name__ == "__main__":
    main()
