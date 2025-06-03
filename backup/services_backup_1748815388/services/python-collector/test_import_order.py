#!/usr/bin/env python3
"""
测试模块导入顺序问题
"""

print("1. 基础导入测试")
try:
    import logging
    print(f"  logging.getLogger exists: {hasattr(logging, 'getLogger')}")
except Exception as e:
    print(f"  导入logging失败: {e}")

print("\n2. 导入我们的核心模块")
try:
    from src.marketprism_collector.core import logging as core_logging
    print(f"  core.logging导入成功")
    print(f"  core.logging内容: {dir(core_logging)}")
except Exception as e:
    print(f"  导入core.logging失败: {e}")

print("\n3. 再次检查标准库logging")
try:
    import logging
    print(f"  logging.getLogger exists: {hasattr(logging, 'getLogger')}")
    print(f"  logging模块ID: {id(logging)}")
    print(f"  logging模块文件: {getattr(logging, '__file__', 'NO FILE')}")
except Exception as e:
    print(f"  检查logging失败: {e}")

print("\n4. 检查sys.modules中的logging")
import sys
logging_module = sys.modules.get('logging')
if logging_module:
    print(f"  sys.modules['logging']存在")
    print(f"  模块ID: {id(logging_module)}")
    print(f"  有getLogger: {hasattr(logging_module, 'getLogger')}")
    print(f"  模块文件: {getattr(logging_module, '__file__', 'NO FILE')}")
else:
    print("  sys.modules['logging']不存在")

print("\n5. 重新导入logging并测试")
try:
    import importlib
    importlib.reload(logging)
    print(f"  重新加载后logging.getLogger exists: {hasattr(logging, 'getLogger')}")
except Exception as e:
    print(f"  重新加载失败: {e}") 