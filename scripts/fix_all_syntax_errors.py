#!/usr/bin/env python3
"""
系统性修复所有语法错误脚本

这个脚本会自动检测和修复项目中的所有语法错误，包括：
1. 缩进问题
2. 导入问题
3. 语法结构问题
"""

import os
import ast
import re
from pathlib import Path
from typing import List, Tuple, Dict

class SyntaxErrorFixer:
    """语法错误修复器"""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.fixed_files = []
        self.errors = []
        
    def check_syntax(self, file_path: Path) -> Tuple[bool, str]:
        """检查Python文件语法"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            ast.parse(content)
            return True, ""
        except SyntaxError as e:
            return False, f"语法错误: {e}"
        except Exception as e:
            return False, f"其他错误: {e}"
    
    def fix_common_issues(self, content: str) -> str:
        """修复常见的语法问题"""
        lines = content.split('\n')
        fixed_lines = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # 移除错误的suppress_event_loop_warnings调用
            if 'async with safe_async_test() as fixture:' in line:
                # 跳过这行和相关的错误缩进
                i += 1
                continue
                
            # 修复错误的缩进模式
            if line.strip().startswith('async with safe_async_test()'):
                i += 1
                continue
                
            # 修复破损的方法定义
            if re.match(r'^\s+async def \w+.*:$', line):
                # 检查下一行是否有错误的缩进
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    if 'async with safe_async_test() as fixture:' in next_line:
                        # 跳过错误的async with行
                        fixed_lines.append(line)
                        i += 2
                        # 继续处理后续正确缩进的代码
                        while i < len(lines) and lines[i].strip():
                            if lines[i].startswith('        '):  # 正确的方法体缩进
                                fixed_lines.append(lines[i])
                            elif lines[i].startswith('    ') and not lines[i].startswith('        '):
                                # 修复缩进
                                fixed_lines.append('        ' + lines[i].strip())
                            else:
                                fixed_lines.append(lines[i])
                            i += 1
                        continue
            
            # 修复导入问题
            if 'from tests.tdd_framework.async_resource_manager import suppress_event_loop_warnings' in line:
                # 移除这个导入，因为我们不需要它
                i += 1
                continue
                
            # 修复破损的类定义
            if line.strip().startswith('class ') and line.endswith(':'):
                fixed_lines.append(line)
                i += 1
                # 确保类体有正确的缩进
                while i < len(lines) and (lines[i].strip() == '' or lines[i].startswith('    ')):
                    if lines[i].strip() and not lines[i].startswith('    '):
                        # 修复类体缩进
                        fixed_lines.append('    ' + lines[i].strip())
                    else:
                        fixed_lines.append(lines[i])
                    i += 1
                continue
            
            fixed_lines.append(line)
            i += 1
        
        return '\n'.join(fixed_lines)
    
    def fix_file(self, file_path: Path) -> bool:
        """修复单个文件"""
        try:
            # 检查语法
            is_valid, error = self.check_syntax(file_path)
            if is_valid:
                return True
                
            print(f"修复文件: {file_path}")
            print(f"错误: {error}")
            
            # 读取文件内容
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 创建备份
            backup_path = file_path.with_suffix(file_path.suffix + '.backup')
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # 修复内容
            fixed_content = self.fix_common_issues(content)
            
            # 写入修复后的内容
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(fixed_content)
            
            # 验证修复结果
            is_valid_after, error_after = self.check_syntax(file_path)
            if is_valid_after:
                print(f"✅ 修复成功: {file_path}")
                self.fixed_files.append(str(file_path))
                return True
            else:
                print(f"❌ 修复失败: {file_path} - {error_after}")
                # 恢复备份
                with open(backup_path, 'r', encoding='utf-8') as f:
                    original_content = f.read()
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(original_content)
                self.errors.append(f"{file_path}: {error_after}")
                return False
                
        except Exception as e:
            print(f"❌ 处理文件时出错 {file_path}: {e}")
            self.errors.append(f"{file_path}: {e}")
            return False
    
    def find_python_files_with_errors(self) -> List[Path]:
        """查找有语法错误的Python文件"""
        error_files = []
        
        for file_path in self.project_root.rglob("*.py"):
            # 跳过虚拟环境和缓存目录
            if any(part in str(file_path) for part in ['venv', '__pycache__', '.git', 'node_modules']):
                continue
                
            is_valid, error = self.check_syntax(file_path)
            if not is_valid:
                error_files.append(file_path)
                
        return error_files
    
    def fix_all(self):
        """修复所有语法错误"""
        print("🔍 查找有语法错误的Python文件...")
        error_files = self.find_python_files_with_errors()
        
        if not error_files:
            print("✅ 没有发现语法错误！")
            return
            
        print(f"📋 发现 {len(error_files)} 个有语法错误的文件")
        
        success_count = 0
        for file_path in error_files:
            if self.fix_file(file_path):
                success_count += 1
        
        print(f"\n📊 修复结果:")
        print(f"✅ 成功修复: {success_count}/{len(error_files)} 个文件")
        print(f"❌ 修复失败: {len(error_files) - success_count} 个文件")
        
        if self.errors:
            print(f"\n❌ 修复失败的文件:")
            for error in self.errors:
                print(f"  - {error}")

def main():
    project_root = "/Users/yao/Documents/GitHub/marketprism"
    fixer = SyntaxErrorFixer(project_root)
    fixer.fix_all()

if __name__ == "__main__":
    main()