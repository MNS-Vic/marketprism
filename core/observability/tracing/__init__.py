"""
MarketPrism 分布式追踪系统

提供统一的分布式追踪、链路跟踪和上下文管理功能。
"""

from datetime import datetime, timezone
from .trace_context import (
    SpanKind, SpanStatus, SpanContext, TraceContext, TraceContextManager,
    get_current_trace_context, set_current_trace_context, 
    create_child_trace_context
)

__all__ = [
    "SpanKind", "SpanStatus", "SpanContext", "TraceContext", 
    "TraceContextManager", "get_current_trace_context", 
    "set_current_trace_context", "create_child_trace_context"
]
# 兼容性别名 - 支持旧API
def get_trace_manager():
    """兼容性函数：获取追踪管理器"""
    return TraceContextManager()

def create_trace_context(operation_name: str):
    """兼容性函数：创建追踪上下文"""
    return create_child_trace_context(operation_name)

def finish_current_trace():
    """兼容性函数：结束当前追踪"""
    context = get_current_trace_context()
    if context:
        context.finish()
    return context

# 类别名
TraceManager = TraceContextManager
TraceContext = TraceContext

# 添加到__all__中
if "get_trace_manager" not in __all__:
    __all__.extend([
        "get_trace_manager", "create_trace_context", "finish_current_trace",
        "TraceManager", "TraceContext"
    ])
