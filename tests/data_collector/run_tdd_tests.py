"""
Data Collector TDD 测试运行脚本

提供多种测试运行模式：
- 单元测试
- 集成测试
- E2E测试
- 完整测试套件
- TDD 红-绿-重构循环
"""

from datetime import datetime, timezone
import sys
import subprocess
import argparse
import os
from pathlib import Path


class DataCollectorTDDRunner:
    """Data Collector TDD 测试运行器"""
    
    def __init__(self):
        self.test_dir = Path(__file__).parent
        self.project_root = self.test_dir.parent.parent.parent
        
    def run_unit_tests(self, verbose=False):
        """运行单元测试"""
        print("🧪 运行 Data Collector 单元测试...")
        
        cmd = [
            sys.executable, "-m", "pytest",
            str(self.test_dir / "unit"),
            "-v" if verbose else "-q",
            "--tb=short",
            "--disable-warnings"
        ]
        
        return subprocess.run(cmd, cwd=self.project_root)
    
    def run_integration_tests(self, verbose=False):
        """运行集成测试"""
        print("🔗 运行 Data Collector 集成测试...")
        
        cmd = [
            sys.executable, "-m", "pytest",
            str(self.test_dir / "integration"),
            "-v" if verbose else "-q",
            "--tb=short",
            "--disable-warnings"
        ]
        
        return subprocess.run(cmd, cwd=self.project_root)
    
    def run_e2e_tests(self, verbose=False):
        """运行E2E测试"""
        print("🎯 运行 Data Collector E2E测试...")
        
        cmd = [
            sys.executable, "-m", "pytest",
            str(self.test_dir / "e2e"),
            "-v" if verbose else "-q",
            "-m", "e2e",
            "--tb=short",
            "--disable-warnings"
        ]
        
        return subprocess.run(cmd, cwd=self.project_root)
    
    def run_all_tests(self, verbose=False):
        """运行所有测试"""
        print("🚀 运行 Data Collector 完整测试套件...")
        
        cmd = [
            sys.executable, "-m", "pytest",
            str(self.test_dir),
            "-v" if verbose else "-q",
            "--tb=short",
            "--disable-warnings",
            "--maxfail=10"  # 最多失败10个就停止
        ]
        
        return subprocess.run(cmd, cwd=self.project_root)
    
    def run_with_coverage(self, test_type="all", verbose=False):
        """运行测试并生成覆盖率报告"""
        print(f"📊 运行 Data Collector {test_type} 测试（带覆盖率）...")
        
        # 确定测试目录
        if test_type == "unit":
            test_path = self.test_dir / "unit"
        elif test_type == "integration":
            test_path = self.test_dir / "integration"
        elif test_type == "e2e":
            test_path = self.test_dir / "e2e"
        else:
            test_path = self.test_dir
        
        # 数据收集器源码路径
        source_path = self.project_root / "services" / "data-collector" / "src" / "marketprism_collector"
        
        cmd = [
            sys.executable, "-m", "pytest",
            str(test_path),
            "-v" if verbose else "-q",
            "--cov=" + str(source_path),
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov",
            "--tb=short",
            "--disable-warnings"
        ]
        
        if test_type == "e2e":
            cmd.extend(["-m", "e2e"])
        
        result = subprocess.run(cmd, cwd=self.project_root)
        
        if result.returncode == 0:
            print(f"📊 覆盖率报告已生成: {self.project_root}/htmlcov/index.html")
        
        return result
    
    def run_tdd_cycle(self, test_file=None):
        """运行TDD红-绿-重构循环"""
        print("🔄 启动 TDD 红-绿-重构循环...")
        
        # 如果指定了测试文件，只运行该文件
        if test_file:
            test_path = self.test_dir / test_file
            if not test_path.exists():
                print(f"❌ 测试文件不存在: {test_path}")
                return subprocess.CompletedProcess([], 1)
        else:
            test_path = self.test_dir
        
        # RED阶段：运行测试，期望失败
        print("\n🔴 RED阶段：运行测试（期望看到失败）...")
        red_cmd = [
            sys.executable, "-m", "pytest",
            str(test_path),
            "-v",
            "--tb=short",
            "--disable-warnings",
            "--maxfail=5"
        ]
        
        red_result = subprocess.run(red_cmd, cwd=self.project_root)
        
        if red_result.returncode == 0:
            print("✅ 所有测试已经通过！无需修复。")
            return red_result
        
        print("\n🟡 发现失败的测试。现在请修复代码...")
        input("修复代码后按 Enter 继续到 GREEN 阶段...")
        
        # GREEN阶段：再次运行测试，期望通过
        print("\n🟢 GREEN阶段：运行测试（期望看到通过）...")
        green_result = subprocess.run(red_cmd, cwd=self.project_root)
        
        if green_result.returncode != 0:
            print("❌ 测试仍然失败。请继续修复代码。")
            return green_result
        
        print("✅ 测试通过！")
        print("\n🔵 REFACTOR阶段：现在可以安全地重构代码...")
        input("重构完成后按 Enter 进行最终验证...")
        
        # REFACTOR验证：最终运行测试确保重构没有破坏功能
        print("\n🔍 REFACTOR验证：确保重构没有破坏功能...")
        final_result = subprocess.run(red_cmd, cwd=self.project_root)
        
        if final_result.returncode == 0:
            print("🎉 TDD循环完成！所有测试通过。")
        else:
            print("⚠️ 重构可能引入了问题，请检查代码。")
        
        return final_result
    
    def run_specific_test(self, test_pattern, verbose=False):
        """运行特定的测试"""
        print(f"🎯 运行特定测试: {test_pattern}")
        
        cmd = [
            sys.executable, "-m", "pytest",
            str(self.test_dir),
            "-k", test_pattern,
            "-v" if verbose else "-q",
            "--tb=short",
            "--disable-warnings"
        ]
        
        return subprocess.run(cmd, cwd=self.project_root)
    
    def list_available_tests(self):
        """列出可用的测试"""
        print("📋 可用的测试文件：")
        
        for test_dir in ["unit", "integration", "e2e"]:
            test_path = self.test_dir / test_dir
            if test_path.exists():
                print(f"\n📁 {test_dir.upper()} 测试:")
                for test_file in test_path.glob("test_*.py"):
                    print(f"  - {test_file.name}")
    
    def check_dependencies(self):
        """检查测试依赖"""
        print("🔍 检查测试依赖...")
        
        required_packages = [
            "pytest",
            "pytest-asyncio",
            "pytest-cov",
            "aiohttp",
            "psutil"
        ]
        
        missing_packages = []
        for package in required_packages:
            try:
                __import__(package.replace("-", "_"))
                print(f"✅ {package}")
            except ImportError:
                print(f"❌ {package}")
                missing_packages.append(package)
        
        if missing_packages:
            print(f"\n⚠️ 缺少依赖包: {', '.join(missing_packages)}")
            print(f"请运行: pip install {' '.join(missing_packages)}")
            return False
        
        print("\n✅ 所有依赖都已安装")
        return True


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Data Collector TDD 测试运行器")
    parser.add_argument(
        "command",
        choices=["unit", "integration", "e2e", "all", "coverage", "tdd", "specific", "list", "deps"],
        help="要执行的测试命令"
    )
    parser.add_argument(
        "--test-type",
        choices=["unit", "integration", "e2e", "all"],
        default="all",
        help="覆盖率测试类型（仅用于coverage命令）"
    )
    parser.add_argument(
        "--pattern",
        help="测试模式（仅用于specific命令）"
    )
    parser.add_argument(
        "--file",
        help="特定测试文件（仅用于tdd命令）"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="详细输出"
    )
    
    args = parser.parse_args()
    
    runner = DataCollectorTDDRunner()
    
    # 检查依赖
    if args.command != "deps" and not runner.check_dependencies():
        sys.exit(1)
    
    # 执行相应命令
    if args.command == "unit":
        result = runner.run_unit_tests(args.verbose)
    elif args.command == "integration":
        result = runner.run_integration_tests(args.verbose)
    elif args.command == "e2e":
        result = runner.run_e2e_tests(args.verbose)
    elif args.command == "all":
        result = runner.run_all_tests(args.verbose)
    elif args.command == "coverage":
        result = runner.run_with_coverage(args.test_type, args.verbose)
    elif args.command == "tdd":
        result = runner.run_tdd_cycle(args.file)
    elif args.command == "specific":
        if not args.pattern:
            print("❌ 使用specific命令时必须指定--pattern参数")
            sys.exit(1)
        result = runner.run_specific_test(args.pattern, args.verbose)
    elif args.command == "list":
        runner.list_available_tests()
        sys.exit(0)
    elif args.command == "deps":
        runner.check_dependencies()
        sys.exit(0)
    
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()