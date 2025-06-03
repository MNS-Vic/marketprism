#!/usr/bin/env python3
"""
重复代码分析工具
分析项目中的重复代码和组件
"""

import os
from pathlib import Path
import ast

def find_duplicate_classes():
    """查找重复的类定义"""
    classes = {}
    
    for file in Path(".").rglob("*.py"):
        if "analysis" in str(file) or "__pycache__" in str(file):
            continue
            
        try:
            with open(file, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read())
                
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_name = node.name
                    if class_name not in classes:
                        classes[class_name] = []
                    classes[class_name].append(str(file))
        except:
            continue
    
    # 查找重复类
    duplicates = {name: files for name, files in classes.items() if len(files) > 1}
    
    print("🔍 重复类分析结果:")
    for class_name, files in duplicates.items():
        if len(files) > 1:
            print(f"\n📋 类名: {class_name}")
            for file in files:
                print(f"  📁 {file}")
    
    return duplicates

if __name__ == "__main__":
    find_duplicate_classes()
