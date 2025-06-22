"""
速率限制器模块

提供自适应速率限制功能，兼容测试期望的API
"""

# 从unified_rate_limit_manager导入所需的类和枚举
from .unified_rate_limit_manager import (
    UnifiedRateLimitManager,
    GlobalUnifiedRateLimitManager,
    RateLimitConfig,
    RequestPriority,
    RequestType,
    RequestRecord,
    QueuedRequest,
    RateLimitViolation,
    RequestTracker
)

# 为了兼容性，创建别名
AdaptiveRateLimiter = UnifiedRateLimitManager
RateLimiterManager = GlobalUnifiedRateLimitManager

# 导出所有公共接口
__all__ = [
    'AdaptiveRateLimiter',
    'RateLimitConfig', 
    'RequestPriority',
    'RateLimiterManager',
    'UnifiedRateLimitManager',
    'GlobalUnifiedRateLimitManager',
    'RequestType',
    'RequestRecord',
    'QueuedRequest',
    'RateLimitViolation',
    'RequestTracker'
]
