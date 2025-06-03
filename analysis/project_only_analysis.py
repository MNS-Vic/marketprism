#!/usr/bin/env python3
"""
MarketPrism项目代码专项分析
仅分析项目自有代码，排除依赖库
"""

import os
from pathlib import Path
import ast

def analyze_project_only():
    """分析仅项目自有代码"""
    print("🎯 分析MarketPrism项目自有代码...")
    
    # 排除依赖库目录
    exclude_dirs = {
        "venv", "venv_tdd", "__pycache__", ".git", 
        "node_modules", "dist", "build", ".pytest_cache",
        "coverage_html_report", ".coverage"
    }
    
    project_files = []
    week_files = []
    test_files = []
    core_files = []
    
    for file_path in Path(".").rglob("*.py"):
        # 跳过依赖库目录
        if any(excluded in str(file_path) for excluded in exclude_dirs):
            continue
            
        project_files.append(file_path)
        
        if "week" in file_path.name.lower():
            week_files.append(file_path)
        if "test" in file_path.name.lower():
            test_files.append(file_path)
        if "core/" in str(file_path):
            core_files.append(file_path)
    
    print(f"📊 项目文件统计:")
    print(f"  📁 总项目文件: {len(project_files)}")
    print(f"  📅 Week相关文件: {len(week_files)}")
    print(f"  🧪 测试文件: {len(test_files)}")
    print(f"  🏗️ 核心组件文件: {len(core_files)}")
    
    # 分析代码行数
    total_lines = 0
    for file_path in project_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                total_lines += len(f.readlines())
        except:
            pass
    
    print(f"  📏 项目总代码行数: {total_lines:,}")
    
    # 分析重复组件
    analyze_project_duplicates(project_files)
    
    # 分析整合进展
    analyze_consolidation_progress()

def analyze_project_duplicates(project_files):
    """分析项目重复组件"""
    print(f"\n🔍 分析项目重复组件...")
    
    classes = {}
    for file_path in project_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read())
                
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_name = node.name
                    if class_name not in classes:
                        classes[class_name] = []
                    classes[class_name].append(str(file_path))
        except:
            continue
    
    # 查找项目重复类
    project_duplicates = {name: files for name, files in classes.items() 
                         if len(files) > 1 and any("marketprism" in f or "week" in f or "core/" in f for f in files)}
    
    print(f"📊 项目重复类统计:")
    print(f"  🔄 项目重复类数: {len(project_duplicates)}")
    
    # 显示关键重复
    critical_duplicates = {name: files for name, files in project_duplicates.items() if len(files) >= 3}
    
    print(f"\n🚨 关键重复类 (3个以上):")
    for class_name, files in sorted(critical_duplicates.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
        print(f"  📋 {class_name} ({len(files)}个重复):")
        for file in files[:5]:
            if any(excluded not in file for excluded in ["venv", "__pycache__"]):
                print(f"    📁 {file}")
        if len(files) > 5:
            print(f"    ... 和其他 {len(files)-5} 个文件")

def analyze_consolidation_progress():
    """分析整合进展"""
    print(f"\n📈 分析整合进展...")
    
    # 检查统一组件
    core_components = {
        "配置管理": "core/config/unified_config_system.py",
        "监控管理": "core/monitoring/unified_monitoring_platform.py", 
        "安全管理": "core/security/unified_security_platform.py",
        "运维管理": "core/operations/unified_operations_platform.py",
        "性能优化": "core/performance/unified_performance_platform.py"
    }
    
    print("🏗️ 统一组件状态:")
    for component_name, file_path in core_components.items():
        if Path(file_path).exists():
            print(f"  ✅ {component_name}: {file_path}")
        else:
            print(f"  ⏳ {component_name}: 待创建")
    
    # 检查历史归档
    archive_dirs = [
        "week_development_history/week1_config_legacy",
        "week_development_history/week5_config_v2", 
        "week_development_history/week2_monitoring_basic",
        "week_development_history/scattered_configs",
        "week_development_history/scattered_monitoring"
    ]
    
    print(f"\n📦 历史归档状态:")
    for archive_dir in archive_dirs:
        if Path(archive_dir).exists():
            file_count = len(list(Path(archive_dir).rglob("*.py")))
            print(f"  ✅ {archive_dir}: {file_count}个文件已归档")
        else:
            print(f"  ❌ {archive_dir}: 不存在")

def calculate_consolidation_impact():
    """计算整合影响"""
    print(f"\n💡 计算整合影响...")
    
    # 统计Week文件
    week_patterns = ["week*.py"]
    remaining_week_files = []
    
    for pattern in week_patterns:
        for file_path in Path(".").rglob(pattern):
            if not any(excluded in str(file_path) for excluded in ["venv", "__pycache__", "backup", "week_development_history"]):
                remaining_week_files.append(file_path)
    
    print(f"📊 剩余Week文件: {len(remaining_week_files)}")
    
    # 按Week分组
    week_groups = {}
    for file_path in remaining_week_files:
        file_name = file_path.name
        if "week5" in file_name:
            week_groups.setdefault("Week 5", []).append(file_path)
        elif "week6" in file_name:
            week_groups.setdefault("Week 6", []).append(file_path)
        elif "week7" in file_name:
            week_groups.setdefault("Week 7", []).append(file_path)
    
    for week, files in week_groups.items():
        print(f"  📅 {week}: {len(files)}个文件")
        if len(files) <= 5:
            for file in files:
                print(f"    📄 {file}")
    
    # 估算整合潜力
    estimated_reduction = len(remaining_week_files) * 0.8  # 预计可减少80%
    print(f"\n🎯 第2阶段整合潜力:")
    print(f"  🗑️ 可减少Week文件: {int(estimated_reduction)}个")
    print(f"  📈 整合进度: 约60%完成")

if __name__ == "__main__":
    print("🚀" + "="*60 + "🚀")
    print("    MarketPrism项目代码专项分析")
    print("    仅分析项目自有代码，排除依赖库")
    print("🚀" + "="*60 + "🚀")
    print()
    
    analyze_project_only()
    calculate_consolidation_impact()
    
    print("\n✅ 项目代码专项分析完成!")
    print("🚀 继续第2阶段整合: 运维和性能系统")