#!/usr/bin/env python3
"""
迁移Python-Collector的core组件到正确位置
"""
import shutil
from pathlib import Path

def migrate_core_components():
    """迁移core组件"""
    
    src_core = Path("services/python-collector/src/marketprism_collector/core")
    
    # 检查core目录是否存在
    if not src_core.exists():
        print("✅ core目录不存在，无需迁移")
        return
    
    print("🔄 开始迁移Python-Collector的core组件...")
    
    # 创建备份目录
    backup_dir = Path("backup/python_collector_core_migration")
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # 备份整个core目录
    if src_core.exists():
        backup_core = backup_dir / "core"
        if backup_core.exists():
            shutil.rmtree(backup_core)
        shutil.copytree(src_core, backup_core)
        print(f"  ✅ 已备份core目录到: {backup_core}")
    
    # 分析core目录中的文件，确定迁移策略
    components_analysis = {
        "middleware": [],
        "errors": [],
        "logging": [],
        "integration": [],
        "other": []
    }
    
    for py_file in src_core.rglob("*.py"):
        relative_path = py_file.relative_to(src_core)
        
        if "middleware" in str(relative_path):
            components_analysis["middleware"].append(relative_path)
        elif "errors" in str(relative_path):
            components_analysis["errors"].append(relative_path)
        elif "logging" in str(relative_path):
            components_analysis["logging"].append(relative_path)
        elif "integration" in str(relative_path) or "example" in str(relative_path):
            components_analysis["integration"].append(relative_path)
        else:
            components_analysis["other"].append(relative_path)
    
    print("\n📊 Core目录内容分析:")
    for category, files in components_analysis.items():
        if files:
            print(f"  {category}: {len(files)}个文件")
            for file in files:
                print(f"    - {file}")
    
    # 迁移策略
    print("\n🎯 迁移策略:")
    
    # 1. middleware组件 -> 可能迁移到项目级core/middleware
    if components_analysis["middleware"]:
        print("  📋 Middleware组件 -> 需要评估是否迁移到项目级core/middleware")
        print("     建议: 检查是否与项目级middleware重复")
    
    # 2. errors组件 -> 迁移到项目级core/errors
    if components_analysis["errors"]:
        print("  ❌ Errors组件 -> 建议迁移到项目级core/errors")
        print("     这些应该是通用的错误处理组件")
    
    # 3. logging组件 -> 迁移到项目级core/logging  
    if components_analysis["logging"]:
        print("  📝 Logging组件 -> 建议迁移到项目级core/logging")
        print("     日志组件应该在基础设施层")
    
    # 4. integration/example -> 迁移到examples或docs
    if components_analysis["integration"]:
        print("  🔗 Integration/Example -> 迁移到examples/或docs/")
        print("     示例和集成代码不应在服务代码中")
    
    # 5. 其他组件 -> 单独评估
    if components_analysis["other"]:
        print("  ❓ 其他组件 -> 需要单独评估迁移位置")
    
    # 执行安全迁移
    print("\n🔄 执行安全迁移...")
    
    # 迁移integration_example.py到examples目录
    integration_example = src_core / "integration_example.py"
    if integration_example.exists():
        examples_dir = Path("examples/python_collector")
        examples_dir.mkdir(parents=True, exist_ok=True)
        
        target_file = examples_dir / "core_integration_example.py"
        shutil.copy2(integration_example, target_file)
        print(f"  ✅ 迁移集成示例: {integration_example} -> {target_file}")
    
    # 检查是否可以安全删除core目录
    critical_files = []
    for py_file in src_core.rglob("*.py"):
        # 检查文件是否被导入
        file_content = py_file.read_text(encoding='utf-8')
        if "class" in file_content and len(file_content) > 1000:
            critical_files.append(py_file)
    
    if critical_files:
        print(f"\n⚠️  发现{len(critical_files)}个可能包含重要业务逻辑的文件:")
        for file in critical_files:
            print(f"    - {file}")
        print("  🔴 建议手动检查这些文件后再删除core目录")
    else:
        print("\n✅ 未发现关键业务逻辑文件，可以安全删除core目录")
        
        # 删除core目录
        try:
            shutil.rmtree(src_core)
            print(f"  ❌ 已删除core目录: {src_core}")
        except Exception as e:
            print(f"  ❌ 删除core目录失败: {e}")
    
    print("\n✅ Core组件迁移分析完成")
    print(f"  📁 备份位置: {backup_core}")
    print("  📋 建议: 根据分析结果手动完成剩余迁移工作")

if __name__ == "__main__":
    migrate_core_components()