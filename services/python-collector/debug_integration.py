#!/usr/bin/env python3
"""
调试集成示例导入问题
"""

print("步骤1: 导入标准库")
import time
import sys
print(f"  time导入成功")

print("\n步骤2: 检查logging状态")
import logging
print(f"  logging导入成功, getLogger存在: {hasattr(logging, 'getLogger')}")

print("\n步骤3: 导入asyncio")
try:
    import asyncio
    print(f"  asyncio导入成功")
except Exception as e:
    print(f"  asyncio导入失败: {e}")
    print("  这是问题所在!")
    # 检查当前的logging状态
    print(f"  当前logging有getLogger: {hasattr(logging, 'getLogger')}")
    print(f"  logging模块: {logging}")
    print(f"  logging内容: {[x for x in dir(logging) if not x.startswith('_')][:20]}")
    sys.exit(1)

print("\n步骤4: 导入typing")
from typing import Dict, Any
print(f"  typing导入成功")

print("\n步骤5: 导入我们的错误模块")
try:
    from src.marketprism_collector.core.errors import (
        UnifiedErrorHandler, ErrorRecoveryManager, ErrorAggregator,
        MarketPrismError, NetworkError, DataError,
        ErrorType, ErrorCategory, ErrorSeverity, RecoveryStrategy
    )
    print(f"  错误模块导入成功")
except Exception as e:
    print(f"  错误模块导入失败: {e}")

print("\n步骤6: 导入我们的日志模块")
try:
    from src.marketprism_collector.core.logging import (
        StructuredLogger, LogConfig, LogLevel, LogFormat, LogOutput, LogOutputConfig,
        get_logger
    )
    print(f"  日志模块导入成功")
except Exception as e:
    print(f"  日志模块导入失败: {e}")

print("\n全部导入成功!") 