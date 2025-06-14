#!/usr/bin/env python3
"""
修复datetime类型注解问题的脚本

专门处理类型注解中的 datetime.datetime -> datetime 问题
"""

import os
import re
import sys
from pathlib import Path

def fix_datetime_type_annotations(content: str) -> tuple[str, int]:
    """修复文件中的datetime类型注解问题"""
    fixes_count = 0
    
    # 修复模式列表 - 专门针对类型注解
    patterns = [
        # 类型注解中的 datetime.datetime -> datetime
        (r': datetime\.datetime\s*=', ': datetime =', 'type annotation datetime.datetime'),
        (r': Optional\[datetime\.datetime\]', ': Optional[datetime]', 'Optional datetime.datetime'),
        (r': List\[datetime\.datetime\]', ': List[datetime]', 'List datetime.datetime'),
        (r': Dict\[str, datetime\.datetime\]', ': Dict[str, datetime]', 'Dict datetime.datetime'),
        
        # 其他可能的类型注解模式
        (r'-> datetime\.datetime', '-> datetime', 'return type datetime.datetime'),
        (r'\(datetime\.datetime\)', '(datetime)', 'function parameter datetime.datetime'),
    ]
    
    original_content = content
    
    for pattern, replacement, description in patterns:
        matches = re.findall(pattern, content)
        if matches:
            content = re.sub(pattern, replacement, content)
            fixes_count += len(matches)
            print(f"  ✅ 修复 {len(matches)} 个 {description}")
    
    return content, fixes_count

def fix_file(file_path: Path) -> bool:
    """修复单个文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        print(f"\n🔧 修复文件: {file_path}")
        
        # 修复datetime类型注解
        content, fixes_count = fix_datetime_type_annotations(content)
        
        # 如果有修改，写回文件
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"  ✅ 完成修复，共 {fixes_count} 处修改")
            return True
        else:
            print("  ℹ️  无需修复")
            return False
            
    except Exception as e:
        print(f"  ❌ 修复失败: {e}")
        return False

def main():
    """主函数"""
    print("🚀 开始修复DateTime类型注解问题...")
    
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