#!/usr/bin/env python3
"""
修复suppress_event_loop_warnings导入问题

这个脚本会自动修复所有调用suppress_event_loop_warnings()但没有正确导入的文件。
"""

import os
import re
from pathlib import Path
from typing import List

def fix_suppress_warnings_imports(project_root: str):
    """修复suppress_event_loop_warnings导入问题"""
    project_path = Path(project_root)
    fixed_files = []
    errors = []
    
    # 查找所有调用suppress_event_loop_warnings()的Python文件
    for file_path in project_path.rglob("*.py"):
        try:
            content = file_path.read_text(encoding='utf-8')
            
            # 检查是否调用了suppress_event_loop_warnings()
            if 'suppress_event_loop_warnings()' in content:
                # 检查是否已经有正确的导入
                if 'from tests.tdd_framework.async_resource_manager import suppress_event_loop_warnings' not in content:
                    # 需要修复
                    print(f"修复文件: {file_path}")
                    
                    # 方案1：添加正确的导入
                    if 'import sys' in content and 'sys.path' in content:
                        # 在sys.path.insert后添加导入
                        pattern = r'(sys\.path\.insert\([^)]+\))'
                        replacement = r'\1\nfrom tests.tdd_framework.async_resource_manager import suppress_event_loop_warnings'
                        new_content = re.sub(pattern, replacement, content)
                        
                        if new_content != content:
                            file_path.write_text(new_content, encoding='utf-8')
                            fixed_files.append(str(file_path))
                            continue
                    
                    # 方案2：直接移除调用
                    # 移除suppress_event_loop_warnings()调用及其注释
                    lines = content.split('\n')
                    new_lines = []
                    skip_next = False
                    
                    for i, line in enumerate(lines):
                        if skip_next:
                            skip_next = False
                            continue
                            
                        if 'suppress_event_loop_warnings()' in line:
                            # 检查前一行是否是注释
                            if i > 0 and '# 抑制事件循环警告' in lines[i-1]:
                                # 移除前一行的注释
                                new_lines.pop()
                            # 跳过当前行
                            continue
                        elif '# 抑制事件循环警告' in line and i < len(lines)-1 and 'suppress_event_loop_warnings()' in lines[i+1]:
                            # 跳过注释行，下一行也会被跳过
                            skip_next = True
                            continue
                        else:
                            new_lines.append(line)
                    
                    new_content = '\n'.join(new_lines)
                    if new_content != content:
                        file_path.write_text(new_content, encoding='utf-8')
                        fixed_files.append(str(file_path))
                        
        except Exception as e:
            errors.append(f"处理文件 {file_path} 时出错: {e}")
    
    return fixed_files, errors

if __name__ == "__main__":
    project_root = "/Users/yao/Documents/GitHub/marketprism"
    
    print("🔧 开始修复suppress_event_loop_warnings导入问题...")
    
    fixed_files, errors = fix_suppress_warnings_imports(project_root)
    
    print(f"\n✅ 修复完成!")
    print(f"📁 修复文件数量: {len(fixed_files)}")
    
    if fixed_files:
        print("\n修复的文件:")
        for file_path in fixed_files[:10]:  # 只显示前10个
            print(f"  - {file_path}")
        if len(fixed_files) > 10:
            print(f"  ... 还有 {len(fixed_files) - 10} 个文件")
    
    if errors:
        print(f"\n❌ 错误数量: {len(errors)}")
        for error in errors[:5]:  # 只显示前5个错误
            print(f"  - {error}")
        if len(errors) > 5:
            print(f"  ... 还有 {len(errors) - 5} 个错误")
    
    print(f"\n🎯 总结: 成功修复 {len(fixed_files)} 个文件")