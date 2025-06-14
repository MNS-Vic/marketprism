#!/usr/bin/env python3
"""
自动修复DateTime导入问题的脚本

修复以下问题：
1. datetime.datetime.now() -> datetime.now()
2. datetime.timezone.utc -> timezone.utc
3. datetime.datetime.fromtimestamp() -> datetime.fromtimestamp()
"""

import os
import re
import sys
from pathlib import Path

def fix_datetime_usage(content: str) -> tuple[str, int]:
    """修复文件中的datetime使用问题"""
    fixes_count = 0
    
    # 修复模式列表
    patterns = [
        # datetime.datetime.now(datetime.timezone.utc) -> datetime.now(timezone.utc)
        (r'datetime\.datetime\.now\(datetime\.timezone\.utc\)', 'datetime.now(timezone.utc)', 'datetime.now with timezone.utc'),
        
        # datetime.datetime.now() -> datetime.now()
        (r'datetime\.datetime\.now\(\)', 'datetime.now()', 'datetime.now without args'),
        
        # datetime.datetime.fromtimestamp() -> datetime.fromtimestamp()
        (r'datetime\.datetime\.fromtimestamp\(', 'datetime.fromtimestamp(', 'datetime.fromtimestamp'),
        
        # datetime.timezone.utc -> timezone.utc
        (r'datetime\.timezone\.utc', 'timezone.utc', 'timezone.utc'),
        
        # 其他常见模式
        (r'datetime\.datetime\.utcnow\(\)', 'datetime.now(timezone.utc)', 'datetime.utcnow to datetime.now'),
    ]
    
    original_content = content
    
    for pattern, replacement, description in patterns:
        matches = re.findall(pattern, content)
        if matches:
            content = re.sub(pattern, replacement, content)
            fixes_count += len(matches)
            print(f"  ✅ 修复 {len(matches)} 个 {description}")
    
    return content, fixes_count

def ensure_datetime_imports(content: str) -> tuple[str, bool]:
    """确保文件有正确的datetime导入"""
    lines = content.split('\n')
    
    # 检查是否已有datetime导入
    has_datetime_import = False
    has_timezone_import = False
    import_line_idx = -1
    
    for i, line in enumerate(lines):
        if 'from datetime import' in line:
            has_datetime_import = 'datetime' in line
            has_timezone_import = 'timezone' in line
            import_line_idx = i
            break
        elif 'import datetime' in line and not line.strip().startswith('#'):
            # 如果是 import datetime，需要替换为 from datetime import
            import_line_idx = i
            break
    
    modified = False
    
    # 如果没有找到datetime导入，添加
    if import_line_idx == -1:
        # 找到其他import语句的位置
        for i, line in enumerate(lines):
            if line.startswith('import ') or line.startswith('from '):
                import_line_idx = i
                break
        
        if import_line_idx == -1:
            # 如果没有其他import，在文件开头添加
            import_line_idx = 0
        
        lines.insert(import_line_idx, 'from datetime import datetime, timezone')
        modified = True
        print("  ✅ 添加datetime导入")
    
    # 如果有import但不完整，修复
    elif import_line_idx >= 0:
        current_line = lines[import_line_idx]
        
        if 'import datetime' in current_line and 'from datetime import' not in current_line:
            # 替换 import datetime 为 from datetime import
            lines[import_line_idx] = 'from datetime import datetime, timezone'
            modified = True
            print("  ✅ 修复datetime导入格式")
        
        elif 'from datetime import' in current_line:
            # 检查是否需要添加缺失的导入
            imports_needed = []
            if not has_datetime_import and 'datetime' not in current_line:
                imports_needed.append('datetime')
            if not has_timezone_import and 'timezone' not in current_line:
                imports_needed.append('timezone')
            
            if imports_needed:
                # 解析现有导入
                import_part = current_line.split('from datetime import ')[1]
                existing_imports = [imp.strip() for imp in import_part.split(',')]
                all_imports = existing_imports + imports_needed
                
                lines[import_line_idx] = f'from datetime import {", ".join(sorted(set(all_imports)))}'
                modified = True
                print(f"  ✅ 添加缺失的导入: {', '.join(imports_needed)}")
    
    if modified:
        return '\n'.join(lines), True
    return content, False

def fix_file(file_path: Path) -> bool:
    """修复单个文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        print(f"\n🔧 修复文件: {file_path}")
        
        # 确保正确的导入
        content, import_modified = ensure_datetime_imports(content)
        
        # 修复datetime使用
        content, fixes_count = fix_datetime_usage(content)
        
        # 如果有修改，写回文件
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            total_changes = fixes_count + (1 if import_modified else 0)
            print(f"  ✅ 完成修复，共 {total_changes} 处修改")
            return True
        else:
            print("  ℹ️  无需修复")
            return False
            
    except Exception as e:
        print(f"  ❌ 修复失败: {e}")
        return False

def main():
    """主函数"""
    print("🚀 开始修复DateTime导入问题...")
    
    # 项目根目录
    project_root = Path(__file__).parent.parent
    
    # 需要修复的目录
    target_dirs = [
        project_root / "services" / "data-collector" / "src" / "marketprism_collector",
        project_root / "core",
        project_root / "tests",
    ]
    
    total_files = 0
    fixed_files = 0
    
    for target_dir in target_dirs:
        if not target_dir.exists():
            print(f"⚠️  目录不存在: {target_dir}")
            continue
            
        print(f"\n📁 扫描目录: {target_dir}")
        
        # 递归查找所有Python文件
        for py_file in target_dir.rglob("*.py"):
            if py_file.name.startswith('.') or '__pycache__' in str(py_file):
                continue
                
            total_files += 1
            if fix_file(py_file):
                fixed_files += 1
    
    print(f"\n🎉 修复完成!")
    print(f"📊 总计扫描: {total_files} 个文件")
    print(f"🔧 成功修复: {fixed_files} 个文件")
    print(f"✅ 修复率: {(fixed_files/total_files*100):.1f}%" if total_files > 0 else "✅ 无文件需要修复")

if __name__ == "__main__":
    main()