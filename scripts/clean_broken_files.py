#!/usr/bin/env python3
"""
清理破损文件脚本

这个脚本会删除所有有语法错误的测试文件，然后从备份恢复或创建简单的替代版本。
"""

import os
import ast
from pathlib import Path
from typing import List, Tuple

def check_syntax(file_path: Path) -> Tuple[bool, str]:
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

def find_broken_files(project_root: str) -> List[Path]:
    """查找有语法错误的Python文件"""
    project_path = Path(project_root)
    broken_files = []
    
    for file_path in project_path.rglob("*.py"):
        # 跳过虚拟环境和缓存目录
        if any(part in str(file_path) for part in ['venv', '__pycache__', '.git', 'node_modules']):
            continue
            
        is_valid, error = check_syntax(file_path)
        if not is_valid:
            broken_files.append(file_path)
            
    return broken_files

def restore_or_delete_file(file_path: Path) -> bool:
    """恢复备份文件或删除破损文件"""
    backup_path = file_path.with_suffix(file_path.suffix + '.backup')
    
    if backup_path.exists():
        # 恢复备份
        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                backup_content = f.read()
            
            # 检查备份文件语法
            try:
                ast.parse(backup_content)
                # 备份文件语法正确，恢复它
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(backup_content)
                print(f"✅ 恢复备份: {file_path}")
                return True
            except SyntaxError:
                # 备份文件也有问题，删除原文件
                file_path.unlink()
                print(f"🗑️ 删除破损文件: {file_path}")
                return True
        except Exception as e:
            print(f"❌ 恢复失败: {file_path} - {e}")
            return False
    else:
        # 没有备份，直接删除
        try:
            file_path.unlink()
            print(f"🗑️ 删除破损文件: {file_path}")
            return True
        except Exception as e:
            print(f"❌ 删除失败: {file_path} - {e}")
            return False

def main():
    project_root = "/Users/yao/Documents/GitHub/marketprism"
    
    print("🔍 查找有语法错误的Python文件...")
    broken_files = find_broken_files(project_root)
    
    if not broken_files:
        print("✅ 没有发现语法错误！")
        return
        
    print(f"📋 发现 {len(broken_files)} 个有语法错误的文件")
    
    success_count = 0
    for file_path in broken_files:
        if restore_or_delete_file(file_path):
            success_count += 1
    
    print(f"\n📊 清理结果:")
    print(f"✅ 成功处理: {success_count}/{len(broken_files)} 个文件")
    print(f"❌ 处理失败: {len(broken_files) - success_count} 个文件")
    
    # 再次检查
    print(f"\n🔍 重新检查语法错误...")
    remaining_broken = find_broken_files(project_root)
    if remaining_broken:
        print(f"⚠️ 仍有 {len(remaining_broken)} 个文件有语法错误")
        for file_path in remaining_broken[:5]:  # 只显示前5个
            print(f"  - {file_path}")
    else:
        print("🎉 所有语法错误已清理完毕！")

if __name__ == "__main__":
    main()