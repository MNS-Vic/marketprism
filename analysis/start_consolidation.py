#!/usr/bin/env python3
"""
🚀 MarketPrism 冗余整合启动脚本
立即开始项目结构冗余整合工作

执行: python analysis/start_consolidation.py
"""

import os
import sys
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

def print_banner():
    """打印启动横幅"""
    print("🚀" + "="*60 + "🚀")
    print("    MarketPrism 项目冗余整合启动器")
    print("    目标: 解决32.5%代码重复问题")
    print("    时间: 21天整合计划")
    print("🚀" + "="*60 + "🚀")
    print()

def create_backup():
    """创建完整项目备份"""
    print("📦 创建项目备份...")
    
    # 创建备份目录
    backup_dir = Path("backup")
    backup_dir.mkdir(exist_ok=True)
    
    # 创建带时间戳的备份
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"marketprism_backup_{timestamp}"
    
    try:
        # Git分支备份
        print("  🔄 创建Git备份分支...")
        subprocess.run(["git", "checkout", "-b", f"backup-before-consolidation-{timestamp}"], 
                      capture_output=True, check=True)
        subprocess.run(["git", "add", "."], capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", f"Backup before consolidation {timestamp}"], 
                      capture_output=True, check=True)
        
        print(f"  ✅ Git备份分支创建成功: backup-before-consolidation-{timestamp}")
        
        # 文件系统备份
        print("  📁 创建文件系统备份...")
        backup_path = backup_dir / f"{backup_name}.tar.gz"
        subprocess.run(["tar", "-czf", str(backup_path), 
                       "--exclude=backup", "--exclude=.git", 
                       "--exclude=__pycache__", "--exclude=*.pyc",
                       "."], check=True)
        
        print(f"  ✅ 文件备份创建成功: {backup_path}")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"  ❌ 备份失败: {e}")
        return False

def analyze_current_state():
    """分析当前项目状态"""
    print("🔍 分析当前项目状态...")
    
    # 统计代码文件
    py_files = list(Path(".").rglob("*.py"))
    week_files = [f for f in py_files if "week" in f.name.lower()]
    test_files = [f for f in py_files if "test" in f.name.lower()]
    
    print(f"  📊 Python文件总数: {len(py_files)}")
    print(f"  📅 Week相关文件: {len(week_files)}")
    print(f"  🧪 测试文件数: {len(test_files)}")
    
    # 查找重复组件
    manager_files = [f for f in py_files if "manager" in f.name.lower()]
    print(f"  🔄 Manager组件文件: {len(manager_files)}")
    
    # 估算代码行数
    total_lines = 0
    for file in py_files:
        try:
            with open(file, 'r', encoding='utf-8') as f:
                total_lines += len(f.readlines())
        except:
            pass
    
    print(f"  📏 总代码行数: {total_lines:,}")
    print(f"  🎯 预计重复代码: {int(total_lines * 0.325):,} ({32.5}%)")
    print()

def create_core_structure():
    """创建核心统一组件结构"""
    print("🏗️ 创建核心统一组件结构...")
    
    # 创建核心目录结构
    core_structure = {
        "core": {
            "config": ["__init__.py", "unified_config_system.py"],
            "monitoring": ["__init__.py", "unified_monitoring_platform.py"],
            "security": ["__init__.py", "unified_security_platform.py"],
            "operations": ["__init__.py", "unified_operations_platform.py"],
            "performance": ["__init__.py", "unified_performance_platform.py"]
        }
    }
    
    for main_dir, subdirs in core_structure.items():
        main_path = Path(main_dir)
        main_path.mkdir(exist_ok=True)
        
        # 创建主__init__.py
        main_init = main_path / "__init__.py"
        if not main_init.exists():
            with open(main_init, 'w', encoding='utf-8') as f:
                f.write(f'"""\n🚀 MarketPrism 核心统一组件系统\n')
                f.write(f'统一架构 - 消除重复，提升效率\n')
                f.write(f'创建时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n"""\n\n')
                f.write("# 核心组件导入\n")
                for subdir in subdirs:
                    if isinstance(subdirs, dict):
                        f.write(f"from .{subdir} import *\n")
        
        if isinstance(subdirs, dict):
            for subdir, files in subdirs.items():
                subdir_path = main_path / subdir
                subdir_path.mkdir(exist_ok=True)
                
                for file in files:
                    file_path = subdir_path / file
                    if not file_path.exists():
                        with open(file_path, 'w', encoding='utf-8') as f:
                            if file == "__init__.py":
                                f.write(f'"""\n🚀 {subdir.title()} 统一管理系统\n')
                                f.write(f'整合所有{subdir}相关功能的统一入口\n"""\n\n')
                            else:
                                f.write(f'"""\n🚀 {subdir.title()} 统一平台\n')
                                f.write(f'整合所有{subdir}功能的核心实现\n')
                                f.write(f'TODO: 整合相关组件\n"""\n\n')
                                f.write("# TODO: 实现统一平台\n")
                                f.write("class Unified{subdir.title()}Platform:\n")
                                f.write("    pass\n")
    
    print("  ✅ 核心目录结构创建完成")

def create_analysis_tools():
    """创建分析工具"""
    print("🔧 创建分析工具...")
    
    analysis_dir = Path("analysis")
    analysis_dir.mkdir(exist_ok=True)
    
    # 创建重复代码分析工具
    duplicate_analyzer = analysis_dir / "find_duplicates.py"
    with open(duplicate_analyzer, 'w', encoding='utf-8') as f:
        f.write('''#!/usr/bin/env python3
"""
重复代码分析工具
分析项目中的重复代码和组件
"""

import os
from pathlib import Path
import ast

def find_duplicate_classes():
    """查找重复的类定义"""
    classes = {}
    
    for file in Path(".").rglob("*.py"):
        if "analysis" in str(file) or "__pycache__" in str(file):
            continue
            
        try:
            with open(file, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read())
                
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_name = node.name
                    if class_name not in classes:
                        classes[class_name] = []
                    classes[class_name].append(str(file))
        except:
            continue
    
    # 查找重复类
    duplicates = {name: files for name, files in classes.items() if len(files) > 1}
    
    print("🔍 重复类分析结果:")
    for class_name, files in duplicates.items():
        if len(files) > 1:
            print(f"\\n📋 类名: {class_name}")
            for file in files:
                print(f"  📁 {file}")
    
    return duplicates

if __name__ == "__main__":
    find_duplicate_classes()
''')
    
    print("  ✅ 分析工具创建完成")

def create_consolidation_roadmap():
    """创建整合路线图文件"""
    print("📋 创建整合路线图...")
    
    roadmap_file = Path("analysis/consolidation_roadmap.md")
    with open(roadmap_file, 'w', encoding='utf-8') as f:
        f.write(f"""# 🚀 MarketPrism 整合路线图

## 📅 整合计划启动
- **启动时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- **预计完成**: {(datetime.now().timestamp() + 21*24*3600).__str__()}
- **执行状态**: 🟡 进行中

## 🎯 第1周目标: 核心组件统一

### ✅ Day 1: 项目分析和准备
- [x] 创建项目备份
- [x] 分析当前状态
- [x] 创建核心结构
- [ ] 统一配置管理系统

### ⏳ Day 2: 监控系统整合
- [ ] 分析现有监控系统
- [ ] 整合统一监控平台
- [ ] 迁移监控数据

### ⏳ Day 3: 安全系统整合
- [ ] 分析现有安全系统
- [ ] 整合统一安全平台
- [ ] 验证安全功能

## 📊 进度跟踪

| 任务 | 状态 | 完成度 | 备注 |
|------|------|--------|------|
| 项目备份 | ✅ | 100% | 已完成 |
| 状态分析 | ✅ | 100% | 已完成 |
| 核心结构 | ✅ | 100% | 已完成 |
| 配置整合 | ⏳ | 0% | 待开始 |

## 🚨 风险跟踪
- [ ] 功能回归风险 - 制定回归测试计划
- [ ] 接口兼容性 - 建立兼容性检查
- [ ] 测试覆盖 - 重建测试套件

## 📞 联系信息
- 执行团队: 架构整合小组
- 更新频率: 每日更新
- 状态汇报: 晚会汇报
""")
    
    print("  ✅ 整合路线图创建完成")

def show_next_steps():
    """显示下一步操作指南"""
    print("🎯 下一步操作指南:")
    print()
    print("1. 📊 查看重复代码分析:")
    print("   python analysis/find_duplicates.py")
    print()
    print("2. 📋 查看详细分析报告:")
    print("   cat analysis/项目冗余分析报告.md")
    print()
    print("3. 📅 查看执行计划:")
    print("   cat analysis/冗余整合执行计划.md")
    print()
    print("4. 🗺️ 跟踪整合进度:")
    print("   cat analysis/consolidation_roadmap.md")
    print()
    print("5. 🚀 开始Day 1配置系统整合:")
    print("   # 开始整合配置管理系统")
    print("   python analysis/consolidate_config_day1.py")
    print()

def main():
    """主函数"""
    print_banner()
    
    # 检查当前目录
    if not Path("marketprism").exists() and not Path("services").exists():
        print("❌ 错误: 请在MarketPrism项目根目录执行此脚本")
        sys.exit(1)
    
    print("🚀 开始MarketPrism项目冗余整合...")
    print()
    
    # 步骤1: 创建备份
    if not create_backup():
        print("❌ 备份失败，终止整合")
        sys.exit(1)
    print()
    
    # 步骤2: 分析当前状态
    analyze_current_state()
    
    # 步骤3: 创建核心结构
    create_core_structure()
    print()
    
    # 步骤4: 创建分析工具
    create_analysis_tools()
    print()
    
    # 步骤5: 创建路线图
    create_consolidation_roadmap()
    print()
    
    print("✅ 整合准备工作完成!")
    print()
    
    # 显示下一步
    show_next_steps()

if __name__ == "__main__":
    main()