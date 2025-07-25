#!/usr/bin/env python3
"""
测试覆盖率报告生成器
生成详细的测试覆盖率报告和分析
"""

import os
import sys
import subprocess
import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def run_coverage_analysis() -> Dict[str, Any]:
    """运行覆盖率分析"""
    print("🔍 运行覆盖率分析...")
    
    # 设置环境
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{project_root}:{project_root}/services/data-collector/src"
    env["MARKETPRISM_ENV"] = "test"
    
    cmd = [
        "python", "-m", "pytest",
        "tests/unit/",
        "--cov=core",
        "--cov=services",
        "--cov-report=json:tests/reports/coverage.json",
        "--cov-report=html:tests/reports/coverage_html",
        "--cov-report=term-missing",
        "--cov-fail-under=0",  # 不因覆盖率低而失败
        "-q"
    ]
    
    try:
        result = subprocess.run(
            cmd, 
            cwd=project_root, 
            capture_output=True, 
            text=True,
            env=env
        )
        
        # 读取JSON覆盖率报告
        coverage_json_path = project_root / "tests" / "reports" / "coverage.json"
        coverage_data = {}
        
        if coverage_json_path.exists():
            with open(coverage_json_path, 'r') as f:
                coverage_data = json.load(f)
        
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "coverage_data": coverage_data
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "coverage_data": {}
        }


def analyze_coverage_by_module(coverage_data: Dict[str, Any]) -> Dict[str, Any]:
    """按模块分析覆盖率"""
    if not coverage_data or "files" not in coverage_data:
        return {}
    
    module_coverage = {}
    
    for file_path, file_data in coverage_data["files"].items():
        # 提取模块名
        if file_path.startswith("core/"):
            parts = file_path.split("/")
            if len(parts) >= 2:
                module = parts[1]
                
                if module not in module_coverage:
                    module_coverage[module] = {
                        "files": [],
                        "total_statements": 0,
                        "covered_statements": 0,
                        "missing_lines": []
                    }
                
                # 计算覆盖的语句数
                executed_lines = file_data.get("executed_lines", [])
                missing_lines = file_data.get("missing_lines", [])
                total_lines = len(executed_lines) + len(missing_lines)
                
                module_coverage[module]["files"].append({
                    "file": file_path,
                    "coverage": file_data.get("summary", {}).get("percent_covered", 0),
                    "statements": total_lines,
                    "covered": len(executed_lines),
                    "missing": len(missing_lines)
                })
                
                module_coverage[module]["total_statements"] += total_lines
                module_coverage[module]["covered_statements"] += len(executed_lines)
                module_coverage[module]["missing_lines"].extend(missing_lines)
    
    # 计算每个模块的覆盖率
    for module, data in module_coverage.items():
        if data["total_statements"] > 0:
            data["coverage_percent"] = (data["covered_statements"] / data["total_statements"]) * 100
        else:
            data["coverage_percent"] = 0
    
    return module_coverage


def generate_coverage_summary(coverage_data: Dict[str, Any]) -> Dict[str, Any]:
    """生成覆盖率摘要"""
    if not coverage_data:
        return {}
    
    totals = coverage_data.get("totals", {})
    
    return {
        "total_statements": totals.get("num_statements", 0),
        "covered_statements": totals.get("covered_lines", 0),
        "missing_statements": totals.get("missing_lines", 0),
        "coverage_percent": totals.get("percent_covered", 0),
        "num_files": len(coverage_data.get("files", {})),
        "timestamp": datetime.now().isoformat()
    }


def identify_priority_areas(module_coverage: Dict[str, Any]) -> List[Dict[str, Any]]:
    """识别优先改进区域"""
    priority_areas = []
    
    for module, data in module_coverage.items():
        coverage_percent = data.get("coverage_percent", 0)
        total_statements = data.get("total_statements", 0)
        
        # 计算优先级分数（覆盖率低且代码量大的模块优先级高）
        if total_statements > 0:
            priority_score = (100 - coverage_percent) * (total_statements / 100)
            
            priority_areas.append({
                "module": module,
                "coverage_percent": coverage_percent,
                "total_statements": total_statements,
                "priority_score": priority_score,
                "files_count": len(data.get("files", []))
            })
    
    # 按优先级分数排序
    priority_areas.sort(key=lambda x: x["priority_score"], reverse=True)
    
    return priority_areas


def generate_test_recommendations(priority_areas: List[Dict[str, Any]]) -> List[str]:
    """生成测试建议"""
    recommendations = []
    
    for area in priority_areas[:5]:  # 前5个优先级最高的模块
        module = area["module"]
        coverage = area["coverage_percent"]
        
        if coverage < 10:
            recommendations.append(
                f"🔴 {module}: 覆盖率极低({coverage:.1f}%)，需要创建基础测试套件"
            )
        elif coverage < 30:
            recommendations.append(
                f"🟡 {module}: 覆盖率较低({coverage:.1f}%)，需要增加核心功能测试"
            )
        elif coverage < 60:
            recommendations.append(
                f"🟠 {module}: 覆盖率中等({coverage:.1f}%)，需要增加边界情况测试"
            )
        elif coverage < 90:
            recommendations.append(
                f"🟢 {module}: 覆盖率良好({coverage:.1f}%)，需要完善异常处理测试"
            )
    
    return recommendations


def print_coverage_report(analysis_result: Dict[str, Any]):
    """打印覆盖率报告"""
    print("\n" + "="*80)
    print("📊 MarketPrism TDD 测试覆盖率报告")
    print("="*80)
    
    if not analysis_result["success"]:
        print("❌ 覆盖率分析失败")
        if "error" in analysis_result:
            print(f"错误: {analysis_result['error']}")
        return
    
    coverage_data = analysis_result["coverage_data"]
    summary = generate_coverage_summary(coverage_data)
    
    print(f"📈 总体覆盖率: {summary.get('coverage_percent', 0):.2f}%")
    print(f"📁 文件数量: {summary.get('num_files', 0)}")
    print(f"📝 总语句数: {summary.get('total_statements', 0)}")
    print(f"✅ 已覆盖: {summary.get('covered_statements', 0)}")
    print(f"❌ 未覆盖: {summary.get('missing_statements', 0)}")
    print(f"🕒 生成时间: {summary.get('timestamp', 'N/A')}")
    
    # 按模块分析
    module_coverage = analyze_coverage_by_module(coverage_data)
    
    if module_coverage:
        print("\n📋 模块覆盖率详情:")
        print("-" * 60)
        
        for module, data in sorted(module_coverage.items(), 
                                 key=lambda x: x[1].get("coverage_percent", 0), 
                                 reverse=True):
            coverage_percent = data.get("coverage_percent", 0)
            files_count = len(data.get("files", []))
            total_statements = data.get("total_statements", 0)
            
            status_icon = "🟢" if coverage_percent >= 80 else "🟡" if coverage_percent >= 50 else "🔴"
            
            print(f"{status_icon} {module:20} {coverage_percent:6.1f}% "
                  f"({files_count:2d} files, {total_statements:4d} statements)")
    
    # 优先级区域
    priority_areas = identify_priority_areas(module_coverage)
    
    if priority_areas:
        print("\n🎯 优先改进区域 (按优先级排序):")
        print("-" * 60)
        
        for i, area in enumerate(priority_areas[:10], 1):
            module = area["module"]
            coverage = area["coverage_percent"]
            statements = area["total_statements"]
            priority = area["priority_score"]
            
            print(f"{i:2d}. {module:20} {coverage:6.1f}% "
                  f"({statements:4d} statements, 优先级: {priority:.1f})")
    
    # 测试建议
    recommendations = generate_test_recommendations(priority_areas)
    
    if recommendations:
        print("\n💡 测试改进建议:")
        print("-" * 60)
        
        for rec in recommendations:
            print(f"   {rec}")
    
    # 目标设定
    current_coverage = summary.get('coverage_percent', 0)
    target_coverage = 90
    
    print(f"\n🎯 覆盖率目标:")
    print("-" * 60)
    print(f"   当前覆盖率: {current_coverage:.2f}%")
    print(f"   目标覆盖率: {target_coverage}%")
    print(f"   需要提升: {target_coverage - current_coverage:.2f}%")
    
    if current_coverage < target_coverage:
        remaining_statements = summary.get('missing_statements', 0)
        needed_coverage = int((target_coverage - current_coverage) / 100 * summary.get('total_statements', 0))
        
        print(f"   需要覆盖额外语句: ~{needed_coverage}")
        print(f"   建议优先处理前3个模块")


def main():
    """主函数"""
    print("🚀 MarketPrism TDD 覆盖率分析器")
    
    # 创建报告目录
    reports_dir = project_root / "tests" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    # 运行覆盖率分析
    analysis_result = run_coverage_analysis()
    
    # 打印报告
    print_coverage_report(analysis_result)
    
    # 保存详细报告
    if analysis_result["success"] and analysis_result["coverage_data"]:
        coverage_data = analysis_result["coverage_data"]
        summary = generate_coverage_summary(coverage_data)
        module_coverage = analyze_coverage_by_module(coverage_data)
        priority_areas = identify_priority_areas(module_coverage)
        recommendations = generate_test_recommendations(priority_areas)
        
        detailed_report = {
            "summary": summary,
            "module_coverage": module_coverage,
            "priority_areas": priority_areas,
            "recommendations": recommendations,
            "raw_coverage": coverage_data
        }
        
        report_file = reports_dir / "detailed_coverage_report.json"
        with open(report_file, 'w') as f:
            json.dump(detailed_report, f, indent=2)
        
        print(f"\n📄 详细报告已保存: {report_file}")
        print(f"📊 HTML报告位置: {reports_dir / 'coverage_html' / 'index.html'}")
    
    print("\n✅ 覆盖率分析完成")


if __name__ == "__main__":
    main()
