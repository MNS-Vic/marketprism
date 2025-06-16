#!/usr/bin/env python3
"""
core_migration_tool.py - Core模块迁移工具

自动化迁移core模块中的冗余导入语句，从旧版本迁移到observability架构
"""
import os
import re
import shutil
from pathlib import Path
from typing import List, Tuple, Dict
import argparse

class CoreMigrationTool:
    """Core模块迁移工具"""
    
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.backup_dir = self.project_root / "migration_backup"
        self.migration_log = []
        
        # 迁移规则定义
        self.import_replacements = [
            # marketprism_logging 迁移
            (r'from core\.marketprism_logging import', 'from core.observability.logging import'),
            (r'import core\.marketprism_logging as', 'import core.observability.logging as'),
            (r'import core\.marketprism_logging', 'import core.observability.logging'),
            
            # tracing 迁移
            (r'from core\.tracing import', 'from core.observability.tracing import'),
            (r'import core\.tracing as', 'import core.observability.tracing as'),
            (r'import core\.tracing', 'import core.observability.tracing'),
        ]
        
        # 需要特殊处理的类名映射
        self.class_mappings = {
            'TraceContextManager': 'TraceContextManager',
            'TraceContext': 'TraceContext',
        }
    
    def create_backup(self) -> bool:
        """创建迁移前的备份"""
        try:
            if self.backup_dir.exists():
                shutil.rmtree(self.backup_dir)
            
            self.backup_dir.mkdir(exist_ok=True)
            
            # 备份关键文件
            files_to_backup = [
                "services/data-collector/src/marketprism_collector/core_integration.py",
                "services/data-collector/src/marketprism_collector/core_services.py", 
                "tests/tdd_comprehensive/test_core_comprehensive.py",
                "scripts/tools/validate_architecture_compliance.py",
                "scripts/tools/smart_component_merge.py"
            ]
            
            for file_path in files_to_backup:
                full_path = self.project_root / file_path
                if full_path.exists():
                    backup_path = self.backup_dir / file_path
                    backup_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(full_path, backup_path)
                    print(f"✅ 备份文件: {file_path}")
            
            print(f"🎯 备份完成，备份目录: {self.backup_dir}")
            return True
            
        except Exception as e:
            print(f"❌ 备份失败: {e}")
            return False
    
    def migrate_file(self, file_path: Path) -> bool:
        """迁移单个文件的导入语句"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            modified = False
            
            # 应用导入替换规则
            for pattern, replacement in self.import_replacements:
                new_content = re.sub(pattern, replacement, content)
                if new_content != content:
                    content = new_content
                    modified = True
                    self.migration_log.append(f"替换导入: {pattern} -> {replacement} in {file_path}")
            
            # 应用类名映射
            for old_class, new_class in self.class_mappings.items():
                pattern = rf'\b{old_class}\b'
                if re.search(pattern, content):
                    content = re.sub(pattern, new_class, content)
                    modified = True
                    self.migration_log.append(f"替换类名: {old_class} -> {new_class} in {file_path}")
            
            # 如果有修改，写回文件
            if modified:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"✅ 迁移完成: {file_path}")
                return True
            
            return False
            
        except Exception as e:
            print(f"❌ 迁移文件失败 {file_path}: {e}")
            return False
    
    def find_python_files(self) -> List[Path]:
        """查找所有Python文件"""
        python_files = []
        
        # 排除的目录
        exclude_dirs = {
            '__pycache__', '.git', '.pytest_cache', 'venv', 'env',
            'migration_backup', '.vscode', 'node_modules'
        }
        
        for file_path in self.project_root.rglob("*.py"):
            # 检查是否在排除目录中
            if any(exclude_dir in file_path.parts for exclude_dir in exclude_dirs):
                continue
            python_files.append(file_path)
        
        return python_files
    
    def analyze_usage(self) -> Dict[str, List[str]]:
        """分析旧模块的使用情况"""
        usage_analysis = {
            'marketprism_logging': [],
            'tracing': []
        }
        
        python_files = self.find_python_files()
        
        for file_path in python_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 检查marketprism_logging使用
                if re.search(r'core\.marketprism_logging', content):
                    usage_analysis['marketprism_logging'].append(str(file_path))
                
                # 检查tracing使用
                if re.search(r'core\.tracing', content):
                    usage_analysis['tracing'].append(str(file_path))
                    
            except Exception as e:
                print(f"⚠️ 分析文件失败 {file_path}: {e}")
        
        return usage_analysis
    
    def setup_compatibility_layer(self) -> bool:
        """设置兼容性层"""
        try:
            # 更新 observability/logging/__init__.py
            logging_init_path = self.project_root / "core/observability/logging/__init__.py"
            
            if logging_init_path.exists():
                with open(logging_init_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 添加兼容性别名
                compatibility_code = '''
# 兼容性别名 - 支持旧API
def get_logger(name: str):
    """兼容性函数：获取日志器"""
    return get_structured_logger(name)

def get_structured_logger(name: str):
    """兼容性函数：获取结构化日志器"""
    return StructuredLogger(name)

def get_log_aggregator():
    """兼容性函数：获取日志聚合器"""
    try:
        from .log_aggregator import LogAggregator
        return LogAggregator()
    except ImportError:
        return None

# 添加到__all__中
if "get_logger" not in __all__:
    __all__.extend(["get_logger", "get_structured_logger", "get_log_aggregator"])
'''
                
                if "get_logger" not in content:
                    content += compatibility_code
                    
                    with open(logging_init_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    
                    print("✅ 设置logging兼容性层")
            
            # 更新 observability/tracing/__init__.py
            tracing_init_path = self.project_root / "core/observability/tracing/__init__.py"
            
            if tracing_init_path.exists():
                with open(tracing_init_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 添加兼容性别名
                compatibility_code = '''
# 兼容性别名 - 支持旧API
def get_trace_manager():
    """兼容性函数：获取追踪管理器"""
    return TraceContextManager()

def create_trace_context(operation_name: str):
    """兼容性函数：创建追踪上下文"""
    return create_child_trace_context(operation_name)

def finish_current_trace():
    """兼容性函数：结束当前追踪"""
    context = get_current_trace_context()
    if context:
        context.finish()
    return context

# 类别名
TraceManager = TraceContextManager
TraceContext = TraceContext

# 添加到__all__中
if "get_trace_manager" not in __all__:
    __all__.extend([
        "get_trace_manager", "create_trace_context", "finish_current_trace",
        "TraceManager", "TraceContext"
    ])
'''
                
                if "get_trace_manager" not in content:
                    content += compatibility_code
                    
                    with open(tracing_init_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    
                    print("✅ 设置tracing兼容性层")
            
            return True
            
        except Exception as e:
            print(f"❌ 设置兼容性层失败: {e}")
            return False
    
    def run_migration(self, dry_run: bool = False) -> bool:
        """执行迁移"""
        print("🚀 开始Core模块迁移...")
        
        # 1. 分析使用情况
        print("\n📊 分析旧模块使用情况...")
        usage_analysis = self.analyze_usage()
        
        for module, files in usage_analysis.items():
            print(f"  {module}: {len(files)} 个文件")
            for file_path in files:
                print(f"    - {file_path}")
        
        if dry_run:
            print("\n🔍 这是预演模式，不会实际修改文件")
            return True
        
        # 2. 创建备份
        print("\n💾 创建备份...")
        if not self.create_backup():
            return False
        
        # 3. 设置兼容性层
        print("\n🔧 设置兼容性层...")
        if not self.setup_compatibility_layer():
            print("⚠️ 兼容性层设置失败，但继续迁移...")
        
        # 4. 执行文件迁移
        print("\n📝 执行文件迁移...")
        python_files = self.find_python_files()
        migrated_count = 0
        
        for file_path in python_files:
            if self.migrate_file(file_path):
                migrated_count += 1
        
        # 5. 输出迁移报告
        print(f"\n🎉 迁移完成！")
        print(f"  - 扫描文件: {len(python_files)} 个")
        print(f"  - 迁移文件: {migrated_count} 个")
        print(f"  - 迁移操作: {len(self.migration_log)} 个")
        
        if self.migration_log:
            print("\n📋 详细迁移日志:")
            for log_entry in self.migration_log:
                print(f"  {log_entry}")
        
        return True
    
    def rollback(self) -> bool:
        """回滚迁移"""
        try:
            if not self.backup_dir.exists():
                print("❌ 没有找到备份目录，无法回滚")
                return False
            
            print("🔄 开始回滚迁移...")
            
            # 恢复备份文件
            for backup_file in self.backup_dir.rglob("*.py"):
                relative_path = backup_file.relative_to(self.backup_dir)
                target_path = self.project_root / relative_path
                
                if target_path.exists():
                    shutil.copy2(backup_file, target_path)
                    print(f"✅ 恢复文件: {relative_path}")
            
            print("🎉 回滚完成！")
            return True
            
        except Exception as e:
            print(f"❌ 回滚失败: {e}")
            return False

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Core模块迁移工具")
    parser.add_argument("--dry-run", action="store_true", help="预演模式，不实际修改文件")
    parser.add_argument("--rollback", action="store_true", help="回滚迁移")
    parser.add_argument("--project-root", default=".", help="项目根目录")
    
    args = parser.parse_args()
    
    tool = CoreMigrationTool(args.project_root)
    
    if args.rollback:
        success = tool.rollback()
    else:
        success = tool.run_migration(dry_run=args.dry_run)
    
    if success:
        print("\n✅ 操作成功完成！")
        if not args.dry_run and not args.rollback:
            print("\n📋 后续步骤:")
            print("1. 运行测试: python -m pytest tests/ -v")
            print("2. 启动服务验证: ./start-data-collector.sh")
            print("3. 检查日志输出是否正常")
            print("4. 如有问题，运行回滚: python scripts/core_migration_tool.py --rollback")
    else:
        print("\n❌ 操作失败！")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())