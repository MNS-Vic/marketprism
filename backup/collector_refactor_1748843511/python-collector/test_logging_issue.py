#!/usr/bin/env python3
"""
诊断logging模块冲突问题
"""

import sys
print("Python路径:")
for i, path in enumerate(sys.path):
    print(f"  {i}: {path}")

print("\n检查logging模块位置:")
try:
    import logging
    print(f"logging模块位置: {logging.__file__}")
    print(f"logging模块内容: {dir(logging)}")
    print(f"是否有getLogger: {'getLogger' in dir(logging)}")
except Exception as e:
    print(f"导入logging失败: {e}")

print("\n检查是否有logging.py文件冲突:")
import os
for path in sys.path:
    logging_py = os.path.join(path, 'logging.py')
    if os.path.exists(logging_py):
        print(f"发现logging.py文件: {logging_py}")

# 检查当前目录是否有logging相关文件
current_dir = os.getcwd()
print(f"\n当前目录: {current_dir}")
for item in os.listdir(current_dir):
    if 'logging' in item.lower():
        print(f"发现logging相关文件/目录: {item}") 