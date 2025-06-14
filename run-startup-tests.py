#!/usr/bin/env python3
"""
MarketPrism 统一启动测试入口
集成启动正确性、功能性、代码质量检测
"""

import asyncio
import argparse
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

def run_quick_test():
    """运行快速测试"""
    print("🚀 运行快速启动测试...")
    
    script_path = Path("./test-startup-simple.sh").resolve()
    if not script_path.exists():
        print(f"❌ test-startup.sh 不存在: {script_path}")
        return 1
    
    # 添加执行权限
    subprocess.run(["chmod", "+x", str(script_path)], check=True)
    
    # 运行脚本
    result = subprocess.run([str(script_path)], capture_output=False, cwd=Path.cwd())
    return result.returncode

async def run_comprehensive_test():
    """运行综合测试"""
    print("🚀 运行综合启动测试...")
    
    # 运行服务启动测试
    from tests.startup.test_service_startup import ServiceStartupTester
    
    project_root = Path.cwd()
    tester = ServiceStartupTester(str(project_root))
    
    try:
        results = await tester.run_all_tests()
        
        # 保存结果
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = project_root / 'tests' / 'startup' / f'comprehensive_results_{timestamp}.json'
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        
        # 打印汇总
        summary = results.get('summary', {})
        total = summary.get('total_services', 0)
        startup_success = summary.get('startup_success', 0)
        functionality_success = summary.get('functionality_success', 0)
        
        print(f"\n📊 综合测试结果:")
        print(f"   启动成功: {startup_success}/{total}")
        print(f"   功能正常: {functionality_success}/{total}")
        print(f"   详细结果: {results_file}")
        
        return 0 if startup_success == total and functionality_success == total else 1
        
    except Exception as e:
        print(f"❌ 综合测试异常: {e}")
        return 1

def run_quality_check():
    """运行代码质量检测"""
    print("🔍 运行代码质量检测...")
    
    try:
        from tests.startup.code_quality_checker import CodeQualityChecker
        
        project_root = Path.cwd()
        checker = CodeQualityChecker(str(project_root))
        results = checker.run_all_checks()
        
        # 统计问题数量
        total_issues = sum(len(data) if isinstance(data, (list, dict)) else 0 for data in results.values())
        
        print(f"\n📋 代码质量检测结果:")
        for category, data in results.items():
            if data:
                count = len(data) if isinstance(data, (list, dict)) else 0
                print(f"   {category}: {count} 个问题")
        
        print(f"\n📊 总计: {total_issues} 个潜在问题")
        
        if total_issues == 0:
            print("🎉 代码质量优秀！")
            return 0
        elif total_issues < 10:
            print("👍 代码质量良好")
            return 0
        else:
            print("⚠️  建议改进代码质量")
            return 1
            
    except Exception as e:
        print(f"❌ 质量检测异常: {e}")
        return 1

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="MarketPrism 启动测试套件")
    parser.add_argument(
        "--mode", 
        choices=["quick", "comprehensive", "quality", "all"],
        default="quick",
        help="测试模式"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    
    args = parser.parse_args()
    
    print("🎯 MarketPrism 启动测试套件")
    print("=" * 50)
    
    exit_code = 0
    
    if args.mode in ["quick", "all"]:
        print("\n📋 第一部分: 快速测试")
        exit_code |= run_quick_test()
    
    if args.mode in ["comprehensive", "all"]:
        print("\n📋 第二部分: 综合测试")
        exit_code |= asyncio.run(run_comprehensive_test())
    
    if args.mode in ["quality", "all"]:
        print("\n📋 第三部分: 质量检测")
        exit_code |= run_quality_check()
    
    print("\n" + "=" * 50)
    if exit_code == 0:
        print("🎉 所有测试通过！")
    else:
        print("❌ 部分测试失败，请检查上述输出")
    
    return exit_code

if __name__ == "__main__":
    sys.exit(main())