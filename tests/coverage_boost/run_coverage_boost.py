#!/usr/bin/env python3
"""
覆盖率提升运行脚本
系统化运行所有覆盖率提升测试，目标达到90%+
"""

from datetime import datetime, timezone
import subprocess
import sys
import os
import json
import time
from pathlib import Path


class CoverageBooster:
    """覆盖率提升工具"""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        self.coverage_tests = [
            "test_caching_comprehensive.py",
            "test_networking_comprehensive.py", 
            "test_config_comprehensive.py",
            "test_errors_comprehensive.py"
        ]
        
    def setup_environment(self):
        """设置测试环境"""
        print("🔧 设置测试环境...")
        
        # 确保在正确的目录
        os.chdir(self.project_root)
        
        # 激活虚拟环境并安装依赖
        commands = [
            "source venv/bin/activate",
            "pip install pytest-cov pytest-html pytest-json-report",
            "pip install coverage[toml]"
        ]
        
        for cmd in commands:
            print(f"  执行: {cmd}")
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"  ⚠️ 命令执行失败: {result.stderr}")
            else:
                print(f"  ✅ 成功")

    def run_individual_test_with_coverage(self, test_file):
        """运行单个测试文件并获取覆盖率"""
        print(f"\n📊 运行覆盖率测试: {test_file}")
        
        test_path = f"tests/coverage_boost/{test_file}"
        
        # 运行测试命令
        cmd = [
            "bash", "-c",
            f"source venv/bin/activate && "
            f"pytest {test_path} "
            f"--cov=core "
            f"--cov=services "
            f"--cov-report=term "
            f"--cov-report=json:coverage_{test_file}.json "
            f"--tb=short "
            f"-v"
        ]
        
        print(f"  执行命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)
        
        if result.returncode == 0:
            print(f"  ✅ {test_file} 测试通过")
            
            # 解析覆盖率结果
            coverage_file = self.project_root / f"coverage_{test_file}.json"
            if coverage_file.exists():
                with open(coverage_file, 'r') as f:
                    coverage_data = json.load(f)
                    total_coverage = coverage_data['totals']['percent_covered']
                    print(f"  📈 覆盖率: {total_coverage:.2f}%")
                    return total_coverage
        else:
            print(f"  ❌ {test_file} 测试失败")
            print(f"  错误输出: {result.stderr}")
            
        return 0

    def run_comprehensive_coverage_test(self):
        """运行全面的覆盖率测试"""
        print("\n🚀 开始全面覆盖率测试...")
        
        # 运行所有覆盖率提升测试
        cmd = [
            "bash", "-c",
            f"source venv/bin/activate && "
            f"export PYTHONPATH={self.project_root}/services/data-collector/src:{self.project_root}:$PYTHONPATH && "
            f"pytest tests/coverage_boost/ "
            f"--cov=core "
            f"--cov=services "
            f"--cov-report=term-missing "
            f"--cov-report=html:htmlcov_boost "
            f"--cov-report=json:coverage_boost_final.json "
            f"--cov-report=xml:coverage_boost.xml "
            f"--tb=short "
            f"-v "
            f"--durations=10"
        ]
        
        print(f"执行命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)
        
        print("\n📋 测试输出:")
        print(result.stdout)
        
        if result.stderr:
            print("\n⚠️ 错误输出:")
            print(result.stderr)
        
        return result.returncode == 0

    def analyze_coverage_results(self):
        """分析覆盖率结果"""
        print("\n📊 分析覆盖率结果...")
        
        coverage_file = self.project_root / "coverage_boost_final.json"
        if not coverage_file.exists():
            print("❌ 找不到覆盖率结果文件")
            return None
        
        with open(coverage_file, 'r') as f:
            coverage_data = json.load(f)
        
        total_coverage = coverage_data['totals']['percent_covered']
        
        print(f"\n🎯 最终覆盖率结果:")
        print(f"  总覆盖率: {total_coverage:.2f}%")
        print(f"  总语句数: {coverage_data['totals']['num_statements']}")
        print(f"  已覆盖: {coverage_data['totals']['covered_lines']}")
        print(f"  未覆盖: {coverage_data['totals']['missing_lines']}")
        
        # 分析各模块覆盖率
        print(f"\n📂 各模块覆盖率:")
        files_coverage = []
        
        for filename, file_data in coverage_data['files'].items():
            if filename.startswith('core/') or filename.startswith('services/'):
                coverage_percent = (file_data['summary']['covered_lines'] / 
                                    file_data['summary']['num_statements'] * 100)
                files_coverage.append((filename, coverage_percent))
        
        # 按覆盖率排序
        files_coverage.sort(key=lambda x: x[1], reverse=True)
        
        print("\n🥇 覆盖率最高的模块:")
        for filename, coverage in files_coverage[:10]:
            print(f"  {filename}: {coverage:.2f}%")
        
        print("\n🔧 需要改进的模块:")
        low_coverage_files = [(f, c) for f, c in files_coverage if c < 70]
        for filename, coverage in low_coverage_files[-10:]:
            print(f"  {filename}: {coverage:.2f}%")
        
        return {
            'total_coverage': total_coverage,
            'high_coverage_files': files_coverage[:10],
            'low_coverage_files': low_coverage_files,
            'target_achieved': total_coverage >= 90.0
        }

    def generate_coverage_report(self, results):
        """生成覆盖率报告"""
        print("\n📝 生成覆盖率报告...")
        
        report_file = self.project_root / "coverage_boost_report.md"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("# MarketPrism 覆盖率提升报告\n\n")
            f.write(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            if results:
                f.write(f"## 总体结果\n\n")
                f.write(f"- **总覆盖率**: {results['total_coverage']:.2f}%\n")
                f.write(f"- **目标达成**: {'✅ 是' if results['target_achieved'] else '❌ 否'} (目标: 90%)\n\n")
                
                f.write(f"## 高覆盖率模块 (Top 10)\n\n")
                for filename, coverage in results['high_coverage_files']:
                    f.write(f"- `{filename}`: {coverage:.2f}%\n")
                
                f.write(f"\n## 需要改进的模块\n\n")
                for filename, coverage in results['low_coverage_files']:
                    f.write(f"- `{filename}`: {coverage:.2f}%\n")
            
            f.write(f"\n## 覆盖率提升测试\n\n")
            f.write(f"本次运行了以下覆盖率提升测试:\n\n")
            for test_file in self.coverage_tests:
                f.write(f"- `{test_file}`\n")
            
            f.write(f"\n## 详细报告\n\n")
            f.write(f"详细的HTML覆盖率报告已生成到 `htmlcov_boost/` 目录\n\n")
            f.write(f"可以通过以下命令查看:\n")
            f.write(f"```bash\n")
            f.write(f"open htmlcov_boost/index.html\n")
            f.write(f"```\n")
        
        print(f"✅ 覆盖率报告已生成: {report_file}")

    def run_baseline_comparison(self):
        """运行基线对比"""
        print("\n📏 运行基线覆盖率对比...")
        
        # 运行原有测试获取基线
        baseline_cmd = [
            "bash", "-c",
            f"source venv/bin/activate && "
            f"export PYTHONPATH={self.project_root}/services/data-collector/src:{self.project_root}:$PYTHONPATH && "
            f"pytest tests/unit/errors/ tests/unit/core/ tests/unit/storage/ "
            f"--cov=core "
            f"--cov=services "
            f"--cov-report=json:coverage_baseline.json "
            f"--tb=short"
        ]
        
        print("获取基线覆盖率...")
        result = subprocess.run(baseline_cmd, capture_output=True, text=True, cwd=self.project_root)
        
        baseline_file = self.project_root / "coverage_baseline.json"
        boost_file = self.project_root / "coverage_boost_final.json"
        
        if baseline_file.exists() and boost_file.exists():
            with open(baseline_file, 'r') as f:
                baseline_data = json.load(f)
            with open(boost_file, 'r') as f:
                boost_data = json.load(f)
            
            baseline_coverage = baseline_data['totals']['percent_covered']
            boost_coverage = boost_data['totals']['percent_covered']
            improvement = boost_coverage - baseline_coverage
            
            print(f"\n📈 覆盖率对比结果:")
            print(f"  基线覆盖率: {baseline_coverage:.2f}%")
            print(f"  提升后覆盖率: {boost_coverage:.2f}%")
            print(f"  提升幅度: +{improvement:.2f}%")
            
            if improvement > 0:
                print(f"  🎉 覆盖率成功提升!")
            else:
                print(f"  ⚠️ 覆盖率未见明显提升")
            
            return improvement
        
        return 0

    def run(self):
        """运行完整的覆盖率提升流程"""
        print("🚀 MarketPrism 覆盖率提升计划启动")
        print("=" * 50)
        
        try:
            # 1. 设置环境
            self.setup_environment()
            
            # 2. 运行基线对比
            baseline_improvement = self.run_baseline_comparison()
            
            # 3. 运行全面覆盖率测试
            success = self.run_comprehensive_coverage_test()
            
            if success:
                # 4. 分析结果
                results = self.analyze_coverage_results()
                
                # 5. 生成报告
                self.generate_coverage_report(results)
                
                # 6. 总结
                print("\n🎯 覆盖率提升任务完成!")
                if results and results['target_achieved']:
                    print("🎉 恭喜! 已达到90%覆盖率目标!")
                else:
                    print("📈 覆盖率有所提升，继续努力达到90%目标")
                
                print(f"\n📋 查看详细报告:")
                print(f"  - HTML报告: htmlcov_boost/index.html")
                print(f"  - Markdown报告: coverage_boost_report.md")
                
            else:
                print("\n❌ 覆盖率测试运行失败")
                return 1
                
        except Exception as e:
            print(f"\n💥 运行过程中出现错误: {e}")
            return 1
        
        return 0


if __name__ == "__main__":
    booster = CoverageBooster()
    exit_code = booster.run()
    sys.exit(exit_code)