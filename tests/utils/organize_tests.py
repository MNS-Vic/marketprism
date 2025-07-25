#!/usr/bin/env python3
"""
测试文件整理工具 - 将分散在项目中的测试脚本整合到tests目录

使用方法:
python tests/utils/organize_tests.py
"""

from datetime import datetime, timezone
import os
import re
import shutil
import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()

# 测试文件的正则表达式模式
TEST_FILE_PATTERN = re.compile(r'test_.*\.py$')

# 排除的目录
EXCLUDE_DIRS = [
    'venv',
    '.git',
    '.pytest_cache',
    '__pycache__',
    'tests'  # 排除tests目录，因为我们只需要处理分散在其他地方的测试
]

# 测试目标目录映射
TEST_DIRS = {
    'unit': PROJECT_ROOT / 'tests' / 'unit',
    'integration': PROJECT_ROOT / 'tests' / 'integration',
    'performance': PROJECT_ROOT / 'tests' / 'performance',
    'load_testing': PROJECT_ROOT / 'tests' / 'load_testing',
}

# 功能模块映射
MODULE_DIRS = {
    'unit': {
        'api': TEST_DIRS['unit'] / 'api',
        'services': TEST_DIRS['unit'] / 'services',
        'models': TEST_DIRS['unit'] / 'models',
        'utils': TEST_DIRS['unit'] / 'utils',
    },
    'integration': {
        'services': TEST_DIRS['integration'] / 'services',
        'api': TEST_DIRS['integration'] / 'api',
    }
}

def ensure_dirs():
    """确保所有测试目录存在"""
    for dir_path in TEST_DIRS.values():
        dir_path.mkdir(exist_ok=True, parents=True)
    
    for module_dirs in MODULE_DIRS.values():
        for dir_path in module_dirs.values():
            dir_path.mkdir(exist_ok=True, parents=True)

def is_excluded(path):
    """检查路径是否应该被排除"""
    for exclude_dir in EXCLUDE_DIRS:
        if exclude_dir in str(path):
            return True
    return False

def categorize_test_file(file_path):
    """
    根据文件内容和命名来分类测试文件
    返回: (test_type, module_type)
    """
    file_name = os.path.basename(file_path)
    file_content = ''
    
    # 尝试读取文件内容
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
    except Exception as e:
        print(f"无法读取文件 {file_path}: {e}")
    
    # 根据文件名和内容分类
    if 'integration' in file_name or 'integration' in file_content:
        test_type = 'integration'
        if 'service' in file_name or 'collector' in file_name or 'normalizer' in file_name:
            module_type = 'services'
        else:
            module_type = 'api'
    elif 'performance' in file_name or 'performance' in file_content:
        test_type = 'performance'
        module_type = None
    elif 'load' in file_name or 'load_test' in file_content:
        test_type = 'load_testing'
        module_type = None
    else:
        # 默认为单元测试
        test_type = 'unit'
        if 'api' in file_name or 'endpoint' in file_name:
            module_type = 'api'
        elif 'service' in file_name or 'collector' in file_name or 'normalizer' in file_name:
            module_type = 'services'
        elif 'model' in file_name:
            module_type = 'models'
        else:
            module_type = 'utils'
    
    return test_type, module_type

def find_and_organize_tests():
    """查找并整理测试文件"""
    # 确保目录存在
    ensure_dirs()
    
    # 查找所有测试文件
    test_files = []
    for root, dirs, files in os.walk(PROJECT_ROOT):
        # 跳过排除的目录
        dirs[:] = [d for d in dirs if not is_excluded(os.path.join(root, d))]
        
        for file in files:
            if TEST_FILE_PATTERN.match(file):
                test_files.append(os.path.join(root, file))
    
    print(f"找到 {len(test_files)} 个测试文件")
    
    # 整理测试文件
    for file_path in test_files:
        test_type, module_type = categorize_test_file(file_path)
        
        # 确定目标目录
        if module_type and module_type in MODULE_DIRS.get(test_type, {}):
            target_dir = MODULE_DIRS[test_type][module_type]
        else:
            target_dir = TEST_DIRS[test_type]
        
        file_name = os.path.basename(file_path)
        target_path = os.path.join(target_dir, file_name)
        
        # 检查目标路径是否已存在同名文件
        if os.path.exists(target_path):
            # 读取两个文件内容
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    source_content = f.read()
                with open(target_path, 'r', encoding='utf-8') as f:
                    target_content = f.read()
                
                # 如果内容相同，跳过复制
                if source_content == target_content:
                    print(f"跳过 {file_path}，目标已存在相同内容的文件")
                    continue
                else:
                    # 如果内容不同，重命名
                    base, ext = os.path.splitext(file_name)
                    target_path = os.path.join(target_dir, f"{base}_external{ext}")
                    print(f"目标已存在不同内容的文件，重命名为 {target_path}")
            except Exception as e:
                print(f"比较文件时出错 {file_path}: {e}")
                continue
        
        # 复制文件，添加标记注释
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            with open(target_path, 'w', encoding='utf-8') as f:
                f.write(f"# 从 {file_path} 移动而来\n")
                f.write(content)
            
            print(f"已整理 {file_path} -> {target_path}")
        except Exception as e:
            print(f"处理文件时出错 {file_path}: {e}")

def main():
    """主函数"""
    print("开始整理测试文件...")
    find_and_organize_tests()
    print("测试文件整理完成！")

if __name__ == "__main__":
    main() 