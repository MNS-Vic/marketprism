#!/usr/bin/env python3
"""
分析并清理Python-Collector中的重复组件
"""
import shutil
from pathlib import Path

def analyze_component_overlap():
    """分析组件重叠情况"""
    
    # 项目级core目录
    project_core = Path("core")
    
    # Python-Collector的core目录
    collector_core = Path("services/python-collector/src/marketprism_collector/core")
    
    if not collector_core.exists():
        print("✅ Python-Collector的core目录不存在，无需分析")
        return
    
    print("🔍 分析Python-Collector与项目级core的重叠情况...")
    
    analysis_results = {
        "errors": {"project": False, "collector": False, "overlap": False},
        "logging": {"project": False, "collector": False, "overlap": False},
        "middleware": {"project": False, "collector": False, "overlap": False},
        "monitoring": {"project": False, "collector": False, "overlap": False},
        "reliability": {"project": False, "collector": False, "overlap": False},
        "storage": {"project": False, "collector": False, "overlap": False},
        "tracing": {"project": False, "collector": False, "overlap": False}
    }
    
    # 检查项目级目录
    for component in analysis_results.keys():
        project_component_dir = project_core / component
        if project_component_dir.exists():
            analysis_results[component]["project"] = True
    
    # 检查collector级目录
    for component in analysis_results.keys():
        collector_component_dir = collector_core / component
        if collector_component_dir.exists():
            analysis_results[component]["collector"] = True
            
            # 如果两者都存在，标记为重叠
            if analysis_results[component]["project"]:
                analysis_results[component]["overlap"] = True
    
    print("\n📊 重叠分析结果:")
    for component, status in analysis_results.items():
        project_status = "✅" if status["project"] else "❌"
        collector_status = "✅" if status["collector"] else "❌"
        overlap_status = "🔴 重叠" if status["overlap"] else "✅ 无重叠"
        
        print(f"  {component}:")
        print(f"    项目级: {project_status}  Collector: {collector_status}  状态: {overlap_status}")
    
    return analysis_results

def check_functional_duplication():
    """检查功能重复情况"""
    
    print("\n🔍 检查功能重复情况...")
    
    collector_core = Path("services/python-collector/src/marketprism_collector/core")
    project_core = Path("core")
    
    duplications = []
    
    # 检查error_aggregator.py是否与项目级errors组件重复
    collector_error_aggregator = collector_core / "errors/error_aggregator.py"
    if collector_error_aggregator.exists():
        # 检查项目级是否有类似功能
        project_error_files = list((project_core / "errors").glob("*.py"))
        
        if any("aggregator" in f.name or "unified" in f.name for f in project_error_files):
            duplications.append({
                "type": "functional_duplicate",
                "collector_file": collector_error_aggregator,
                "description": "错误聚合功能在项目级已存在"
            })
    
    # 检查logging组件重复
    collector_logging_dir = collector_core / "logging"
    if collector_logging_dir.exists():
        project_logging_dir = project_core / "logging"
        if project_logging_dir.exists():
            duplications.append({
                "type": "component_duplicate",
                "collector_component": collector_logging_dir,
                "project_component": project_logging_dir,
                "description": "日志组件功能重复"
            })
    
    # 检查middleware重复
    collector_middleware_dir = collector_core / "middleware"
    if collector_middleware_dir.exists():
        project_middleware_dir = project_core / "middleware"
        if project_middleware_dir.exists():
            # 检查具体文件
            collector_middleware_files = list(collector_middleware_dir.glob("*.py"))
            
            if len(collector_middleware_files) > 1:  # 除了__init__.py
                duplications.append({
                    "type": "middleware_duplicate",
                    "collector_component": collector_middleware_dir,
                    "project_component": project_middleware_dir,
                    "description": f"Middleware组件可能重复，Collector有{len(collector_middleware_files)}个文件"
                })
    
    if duplications:
        print("  🔴 发现重复功能:")
        for dup in duplications:
            print(f"    - {dup['description']}")
            if 'collector_file' in dup:
                print(f"      Collector文件: {dup['collector_file']}")
            if 'collector_component' in dup:
                print(f"      Collector组件: {dup['collector_component']}")
                print(f"      项目级组件: {dup['project_component']}")
    else:
        print("  ✅ 未发现明显的功能重复")
    
    return duplications

def create_safe_cleanup_plan():
    """创建安全清理计划"""
    
    print("\n📋 创建安全清理计划...")
    
    collector_core = Path("services/python-collector/src/marketprism_collector/core")
    
    if not collector_core.exists():
        print("  ✅ 无需清理，core目录不存在")
        return []
    
    cleanup_plan = []
    
    # 1. 集成示例已经迁移，可以安全删除
    integration_example = collector_core / "integration_example.py"
    if integration_example.exists():
        cleanup_plan.append({
            "action": "delete",
            "target": integration_example,
            "reason": "已迁移到examples目录",
            "safe": True
        })
    
    # 2. 检查errors组件
    errors_dir = collector_core / "errors"
    if errors_dir.exists():
        cleanup_plan.append({
            "action": "evaluate_merge",
            "target": errors_dir,
            "reason": "可能包含有用的错误聚合功能，建议合并到项目级errors",
            "safe": False
        })
    
    # 3. 检查logging组件
    logging_dir = collector_core / "logging"
    if logging_dir.exists():
        cleanup_plan.append({
            "action": "evaluate_merge", 
            "target": logging_dir,
            "reason": "可能包含专用日志功能，建议合并到项目级logging",
            "safe": False
        })
    
    # 4. 检查middleware组件
    middleware_dir = collector_core / "middleware"
    if middleware_dir.exists():
        middleware_files = list(middleware_dir.glob("*.py"))
        non_init_files = [f for f in middleware_files if f.name != "__init__.py"]
        
        if len(non_init_files) > 0:
            cleanup_plan.append({
                "action": "evaluate_merge",
                "target": middleware_dir,
                "reason": f"包含{len(non_init_files)}个middleware文件，可能有专用功能",
                "safe": False
            })
    
    # 5. 空目录可以安全删除
    for item in collector_core.iterdir():
        if item.is_dir() and item.name not in ["errors", "logging", "middleware"]:
            py_files = list(item.rglob("*.py"))
            non_init_files = [f for f in py_files if f.name != "__init__.py"]
            
            if len(non_init_files) == 0:
                cleanup_plan.append({
                    "action": "delete",
                    "target": item,
                    "reason": "空目录，无实际代码",
                    "safe": True
                })
    
    return cleanup_plan

def execute_safe_cleanup(cleanup_plan):
    """执行安全清理"""
    
    print("\n🧹 执行安全清理...")
    
    executed_actions = []
    skipped_actions = []
    
    for plan_item in cleanup_plan:
        if plan_item["safe"]:
            try:
                target = plan_item["target"]
                
                if plan_item["action"] == "delete":
                    if target.is_file():
                        target.unlink()
                        print(f"  ❌ 删除文件: {target}")
                    elif target.is_dir():
                        shutil.rmtree(target)
                        print(f"  ❌ 删除目录: {target}")
                    
                    executed_actions.append(plan_item)
                
            except Exception as e:
                print(f"  ⚠️  删除失败 {target}: {e}")
        else:
            print(f"  🔄 跳过不安全操作: {plan_item['target']} - {plan_item['reason']}")
            skipped_actions.append(plan_item)
    
    return executed_actions, skipped_actions

def check_core_directory_status():
    """检查core目录状态"""
    
    collector_core = Path("services/python-collector/src/marketprism_collector/core")
    
    if not collector_core.exists():
        print("\n✅ Python-Collector的core目录已不存在")
        return True
    
    # 检查剩余内容
    remaining_items = list(collector_core.iterdir())
    
    if not remaining_items:
        print("\n✅ core目录为空，可以安全删除")
        try:
            collector_core.rmdir()
            print("  ❌ 已删除空的core目录")
            return True
        except Exception as e:
            print(f"  ⚠️  删除core目录失败: {e}")
            return False
    else:
        print(f"\n⚠️  core目录仍包含{len(remaining_items)}个项目:")
        for item in remaining_items:
            print(f"    - {item.name}")
        return False

def main():
    """主函数"""
    
    print("🎯 Python-Collector 重复组件分析和清理工具")
    print("=" * 60)
    
    # 1. 分析重叠情况
    overlap_analysis = analyze_component_overlap()
    
    # 2. 检查功能重复
    functional_duplications = check_functional_duplication()
    
    # 3. 创建清理计划
    cleanup_plan = create_safe_cleanup_plan()
    
    if cleanup_plan:
        print(f"\n📋 清理计划包含{len(cleanup_plan)}个操作:")
        for i, plan_item in enumerate(cleanup_plan, 1):
            safe_status = "🟢 安全" if plan_item["safe"] else "🔴 需评估"
            print(f"  {i}. {plan_item['action']}: {plan_item['target']}")
            print(f"     状态: {safe_status} - {plan_item['reason']}")
        
        # 4. 执行安全清理
        executed, skipped = execute_safe_cleanup(cleanup_plan)
        
        print(f"\n📊 清理结果:")
        print(f"  ✅ 执行操作: {len(executed)}个")
        print(f"  ⏭️  跳过操作: {len(skipped)}个")
        
        if skipped:
            print(f"\n🔄 需要手动处理的项目:")
            for item in skipped:
                print(f"  - {item['target']}: {item['reason']}")
    
    # 5. 检查最终状态
    clean_status = check_core_directory_status()
    
    print("\n" + "=" * 60)
    if clean_status:
        print("✅ Python-Collector core目录清理完成！")
    else:
        print("⚠️  Python-Collector core目录需要进一步手动处理")
    
    print("📋 建议下一步:")
    print("  1. 检查剩余的core组件是否需要迁移到项目级")
    print("  2. 更新导入语句使用项目级core组件")
    print("  3. 运行测试确保功能正常")

if __name__ == "__main__":
    main()