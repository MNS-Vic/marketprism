"""
Tracing module - 链路追踪模块
提供统一的分布式链路追踪和上下文管理功能
"""
from datetime import datetime, timezone
import logging
from typing import Dict, Any, Optional
import uuid

# 导入实际的tracing组件
try:
    from core.observability.tracing.trace_context import TraceContext
    OBSERVABILITY_TRACING_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Observability tracing不可用: {e}")
    OBSERVABILITY_TRACING_AVAILABLE = False
    TraceContext = None

logger = logging.getLogger(__name__)

class UnifiedTraceContext:
    """统一追踪上下文"""
    
    def __init__(self, trace_id: str = None, span_id: str = None, parent_span_id: str = None):
        self.trace_id = trace_id or str(uuid.uuid4())
        self.span_id = span_id or str(uuid.uuid4()) 
        self.parent_span_id = parent_span_id
        self.start_time = datetime.now(timezone.utc)
        self.metadata = {}
        self.logger = logging.getLogger(__name__)
        
        # 尝试使用实际的TraceContext
        self.real_context = None
        if OBSERVABILITY_TRACING_AVAILABLE and TraceContext:
            try:
                self.real_context = TraceContext(trace_id, span_id, parent_span_id)
                self.logger.debug("✅ 真实追踪上下文初始化成功")
            except Exception as e:
                self.logger.warning(f"真实追踪上下文初始化失败: {e}")
    
    def add_metadata(self, key: str, value: Any):
        """添加元数据"""
        self.metadata[key] = value
        if self.real_context and hasattr(self.real_context, 'add_metadata'):
            try:
                self.real_context.add_metadata(key, value)
            except Exception:
                pass
    
    def create_child_span(self, operation_name: str) -> 'UnifiedTraceContext':
        """创建子span"""
        child_span_id = str(uuid.uuid4())
        child = UnifiedTraceContext(
            trace_id=self.trace_id,
            span_id=child_span_id,
            parent_span_id=self.span_id
        )
        child.add_metadata('operation_name', operation_name)
        child.add_metadata('parent_operation', self.metadata.get('operation_name', 'unknown'))
        return child
    
    def finish(self):
        """结束span"""
        self.metadata['end_time'] = datetime.now(timezone.utc).isoformat()
        self.metadata['duration_ms'] = (datetime.now(timezone.utc) - self.start_time).total_seconds() * 1000
        
        if self.real_context and hasattr(self.real_context, 'finish'):
            try:
                self.real_context.finish()
            except Exception:
                pass
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'trace_id': self.trace_id,
            'span_id': self.span_id,
            'parent_span_id': self.parent_span_id,
            'start_time': self.start_time.isoformat(),
            'metadata': self.metadata
        }

# 全局上下文栈
_context_stack = []

def get_current_trace_context() -> Optional[UnifiedTraceContext]:
    """获取当前追踪上下文"""
    if _context_stack:
        return _context_stack[-1]
    return None

def create_child_trace_context(operation_name: str) -> UnifiedTraceContext:
    """创建子追踪上下文"""
    current = get_current_trace_context()
    if current:
        child = current.create_child_span(operation_name)
    else:
        child = UnifiedTraceContext()
        child.add_metadata('operation_name', operation_name)
        child.add_metadata('is_root', True)
    
    _context_stack.append(child)
    return child

def create_trace_context(operation_name: str) -> UnifiedTraceContext:
    """创建追踪上下文"""
    context = UnifiedTraceContext()
    context.add_metadata('operation_name', operation_name)
    context.add_metadata('is_root', True)
    _context_stack.append(context)
    return context

def finish_current_trace():
    """结束当前追踪"""
    if _context_stack:
        context = _context_stack.pop()
        context.finish()
        return context
    return None

def clear_trace_stack():
    """清空追踪栈"""
    while _context_stack:
        context = _context_stack.pop()
        context.finish()

class TraceManager:
    """追踪管理器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.active_traces = {}
    
    def start_trace(self, operation_name: str) -> str:
        """开始追踪"""
        context = create_trace_context(operation_name)
        self.active_traces[context.trace_id] = context
        return context.trace_id
    
    def get_trace(self, trace_id: str) -> Optional[UnifiedTraceContext]:
        """获取追踪"""
        return self.active_traces.get(trace_id)
    
    def finish_trace(self, trace_id: str):
        """结束追踪"""
        if trace_id in self.active_traces:
            context = self.active_traces.pop(trace_id)
            context.finish()
            return context
        return None
    
    def get_all_traces(self) -> Dict[str, Dict[str, Any]]:
        """获取所有追踪"""
        return {tid: ctx.to_dict() for tid, ctx in self.active_traces.items()}

# 全局追踪管理器
_global_trace_manager = None

def get_trace_manager() -> TraceManager:
    """获取追踪管理器"""
    global _global_trace_manager
    if _global_trace_manager is None:
        _global_trace_manager = TraceManager()
    return _global_trace_manager

# 装饰器支持
def trace(operation_name: str = None):
    """追踪装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            context = create_child_trace_context(op_name)
            try:
                result = func(*args, **kwargs)
                context.add_metadata('status', 'success')
                return result
            except Exception as e:
                context.add_metadata('status', 'error')
                context.add_metadata('error', str(e))
                raise
            finally:
                finish_current_trace()
        return wrapper
    return decorator

# 导出所有公共接口
__all__ = [
    'UnifiedTraceContext',
    'TraceManager',
    'get_current_trace_context',
    'create_child_trace_context',
    'create_trace_context',
    'finish_current_trace',
    'clear_trace_stack',
    'get_trace_manager',
    'trace',
    'TraceContext'  # 别名
]

# 创建别名以保持兼容性
TraceContext = UnifiedTraceContext 