"""
🚀 MarketPrism 统一安全管理模块
"""

from datetime import datetime, timezone
from .unified_security_platform import UnifiedSecurityPlatform

# 全局安全管理器实例
_global_security_manager = None

def get_security_manager():
    """获取全局安全管理器"""
    global _global_security_manager
    if _global_security_manager is None:
        _global_security_manager = UnifiedSecurityPlatform()
    return _global_security_manager

def set_security_manager(manager):
    """设置全局安全管理器"""
    global _global_security_manager
    _global_security_manager = manager

# 兼容性别名
SecurityManager = UnifiedSecurityPlatform

__all__ = [
    'UnifiedSecurityPlatform',
    'SecurityManager',
    'get_security_manager', 
    'set_security_manager'
]
