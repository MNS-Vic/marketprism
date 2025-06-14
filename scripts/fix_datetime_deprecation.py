#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复和统一datetime用法的自动化脚本

将项目中所有 datetime.datetime.now(datetime.timezone.utc) 和 datetime.datetime.now(datetime.timezone.utc) 的用法
统一为安全且兼容的 datetime.now(datetime.timezone.utc)。
"""

import datetime
import os
import re
import sys
from typing import List, Tuple

def find_python_files(directory: str) -> List[str]:
    """查找所有Python文件"""
    python_files = []
    for root, dirs, files in os.walk(directory):
        # 跳过虚拟环境和缓存目录
        dirs[:] = [d for d in dirs if not d.startswith(('.', '__pycache__', 'venv', 'node_modules'))]
        
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    
    return python_files

def ensure_datetime_import(content: str) -> Tuple[str, bool]:
    """确保文件顶部有 'import datetime'"""
    modified = False
    
    # 如果没有导入datetime，则添加
    if 'import datetime' not in content and 'from datetime import' in content:
        # 寻找第一个import语句
        first_import_match = re.search(r'^(import|from)\s', content, re.MULTILINE)
        if first_import_match:
            pos = first_import_match.start()
            content = content[:pos] + "import datetime\n" + content[pos:]
            modified = True
            
    # 清理旧的 from datetime import timezone 等
    content = re.sub(r'from datetime import timezone\n', '', content)
    content = re.sub(r'from datetime import datetime, timezone\n', '', content)
    
    return content, modified


def unify_datetime_calls(content: str) -> Tuple[str, int]:
    """统一datetime调用"""
    count = 0
    
    # 模式1: datetime.datetime.now(datetime.timezone.utc)
    pattern_utcnow = r'datetime\.utcnow\(\)'
    # 模式2: datetime.datetime.now(datetime.timezone.utc)
    pattern_now_utc = r'datetime\.now\(timezone\.utc\)'
    
    # 统一替换为完全限定的名称
    replacement = 'datetime.datetime.now(datetime.timezone.utc)'
    
    # 执行替换
    content, c1 = re.subn(pattern_utcnow, replacement, content)
    content, c2 = re.subn(pattern_now_utc, replacement, content)
    
    count = c1 + c2
    return content, count

def process_file(file_path: str) -> Tuple[bool, int]:
    """处理单个文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # 统一datetime调用
        content, replacements = unify_datetime_calls(content)
        
        # 如果有替换，确保导入存在
        if replacements > 0:
            content, _ = ensure_datetime_import(content)
        
        # 如果有修改，写回文件
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True, replacements
        
        return False, 0
        
    except Exception as e:
        print(f"  ❌ 处理文件失败: {file_path} - {e}")
        return False, 0

def main():
    """主函数"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    os.chdir(project_root)
    
    print("🔧 MarketPrism `datetime` 用法统一工具")
    print("=" * 60)
    
    # 扩大目标目录范围，覆盖整个项目
    target_dirs = [
        'services',
        'core',
        'tests',
        'examples',
        'config',
        'scripts' # 也检查脚本自身
    ]
    
    total_files_scanned = 0
    modified_files_count = 0
    total_replacements_count = 0
    
    all_python_files = []
    for target_dir in target_dirs:
        if os.path.exists(target_dir):
            all_python_files.extend(find_python_files(target_dir))
        else:
            print(f"⚠️  目录不存在: {target_dir}")
            
    # 去重
    all_python_files = sorted(list(set(all_python_files)))
    
    print(f"🔍 发现 {len(all_python_files)} 个Python文件待扫描...")

    for file_path in all_python_files:
        total_files_scanned += 1
        
        print(f"  📄 正在处理: {file_path}", end='\r')
        file_modified, replacements = process_file(file_path)
        
        if file_modified:
            modified_files_count += 1
            total_replacements_count += replacements
            print(f"  📄 {file_path} ... ✅ 已修复 {replacements} 处")

    print("\n" + "=" * 60)
    print("📊 修复统计:")
    print(f"  • 扫描文件总数: {total_files_scanned}")
    print(f"  • 修改文件数量: {modified_files_count}")
    print(f"  • 替换调用总数: {total_replacements_count}")
    
    if total_replacements_count > 0:
        print(f"\n✅ 成功统一了 {total_replacements_count} 处 `datetime` 调用！")
    else:
        print("\n✅ 所有 `datetime` 调用已统一，无需修改。")

if __name__ == "__main__":
    main() 