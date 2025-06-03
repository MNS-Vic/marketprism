#!/usr/bin/env python3
"""
Python-Collector 重复组件清理脚本
"""
import os
import shutil
from pathlib import Path

def cleanup_duplicate_components():
    """清理Python-Collector中的重复组件"""
    
    base_path = Path("services/python-collector/src/marketprism_collector")
    
    # 要清理的重复目录
    duplicate_dirs = [
        "core",
        "monitoring", 
        "reliability",
        "storage"
    ]
    
    print("🧹 开始清理Python-Collector重复组件...")
    
    for dir_name in duplicate_dirs:
        dir_path = base_path / dir_name
        
        if dir_path.exists():
            # 检查目录是否为空或只包含__init__.py
            files = list(dir_path.rglob("*.py"))
            non_init_files = [f for f in files if f.name != "__init__.py"]
            
            if len(non_init_files) == 0:
                print(f"  ❌ 删除空目录: {dir_path}")
                shutil.rmtree(dir_path)
            else:
                print(f"  ⚠️  目录包含文件，需要手动检查: {dir_path}")
                for file in non_init_files:
                    print(f"    - {file}")
        else:
            print(f"  ✅ 目录不存在: {dir_path}")
    
    print("✅ 重复组件清理完成")

if __name__ == "__main__":
    cleanup_duplicate_components()