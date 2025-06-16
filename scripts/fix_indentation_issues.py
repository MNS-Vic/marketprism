#!/usr/bin/env python3
"""
修复缩进问题脚本

这个脚本会自动检测和修复由于之前的修复脚本导致的缩进问题。
"""

import os
import ast
from pathlib import Path
from typing import List, Tuple

def check_python_syntax(file_path: Path) -> Tuple[bool, str]:
    """检查Python文件语法是否正确"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        ast.parse(content)
        return True, ""
    except SyntaxError as e:
        return False, str(e)
    except Exception as e:
        return False, f"其他错误: {e}"

def fix_common_indentation_issues(content: str) -> str:
    """修复常见的缩进问题"""
    lines = content.split('\n')
    fixed_lines = []
    
    for i, line in enumerate(lines):
        # 修复 "async with safe_async_test() as fixture:" 相关的缩进问题
        if 'async with safe_async_test() as fixture:' in line:
            # 跳过这行，因为我们不需要这个调用
            continue
            
        # 修复错误的缩进模式
        if line.strip().startswith('proxy = ') and i > 0:
            # 检查前一行的缩进
            prev_line = lines[i-1] if i > 0 else ""
            if 'async def test_' in prev_line or 'def test_' in prev_line:
                # 这应该是测试方法内的第一行，使用8个空格缩进
                line = '        ' + line.strip()
        
        # 修复其他常见的缩进问题
        if line.strip() and not line.startswith(' ') and not line.startswith('\t'):
            # 如果这是一个非空行但没有缩进，检查上下文
            if i > 0:
                prev_line = lines[i-1]
                if ('def test_' in prev_line or 'async def test_' in prev_line) and '"""' not in line:
                    # 这应该是测试方法内的代码
                    line = '        ' + line
                elif prev_line.strip().endswith(':') and not line.startswith('class ') and not line.startswith('def '):
                    # 前一行以冒号结尾，这行应该缩进
                    line = '        ' + line
        
        fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)

def fix_indentation_issues(project_root: str):
    """修复项目中的缩进问题"""
    project_path = Path(project_root)
    fixed_files = []
    errors = []
    
    # 查找所有Python测试文件
    for file_path in project_path.rglob("test_*.py"):
        try:
            # 检查语法
            is_valid, error_msg = check_python_syntax(file_path)
            
            if not is_valid and ('IndentationError' in error_msg or 'unexpected indent' in error_msg):
                print(f"修复缩进问题: {file_path}")
                
                # 读取文件内容
                content = file_path.read_text(encoding='utf-8')
                
                # 修复缩进问题
                fixed_content = fix_common_indentation_issues(content)
                
                # 检查修复后的语法
                try:
                    ast.parse(fixed_content)
                    # 语法正确，保存文件
                    file_path.write_text(fixed_content, encoding='utf-8')
                    fixed_files.append(str(file_path))
                except SyntaxError:
                    # 修复失败，记录错误
                    errors.append(f"无法修复 {file_path}: 语法仍然错误")
                    
        except Exception as e:
            errors.append(f"处理文件 {file_path} 时出错: {e}")
    
    return fixed_files, errors

if __name__ == "__main__":
    project_root = "/Users/yao/Documents/GitHub/marketprism"
    
    print("🔧 开始修复缩进问题...")
    
    fixed_files, errors = fix_indentation_issues(project_root)
    
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
    
    print(f"\n🎯 总结: 成功修复 {len(fixed_files)} 个文件的缩进问题")