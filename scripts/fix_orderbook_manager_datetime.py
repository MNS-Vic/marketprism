#!/usr/bin/env python3
"""
修复orderbook_manager.py中的datetime.datetime问题
"""

import re

def fix_orderbook_manager():
    file_path = "services/data-collector/src/marketprism_collector/orderbook_manager.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 替换所有的 datetime.datetime.now(timezone.utc) -> datetime.now(timezone.utc)
    content = re.sub(r'datetime\.datetime\.now\(timezone\.utc\)', 'datetime.now(timezone.utc)', content)
    
    # 替换所有的 datetime.datetime.now() -> datetime.now()
    content = re.sub(r'datetime\.datetime\.now\(\)', 'datetime.now()', content)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ 修复完成：orderbook_manager.py")

if __name__ == "__main__":
    fix_orderbook_manager()