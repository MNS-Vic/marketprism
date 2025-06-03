"""
追踪上下文管理

定义追踪上下文和Span上下文的数据结构。
"""

import uuid
import time
import threading
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SpanKind(Enum):
    """Span类型枚举"""
    INTERNAL = "internal"     # 内部调用
    SERVER = "server"         # 服务器端
    CLIENT = "client"         # 客户端
    PRODUCER = "producer"     # 消息生产者
    CONSUMER = "consumer"     # 消息消费者


class SpanStatus(Enum):
    """Span状态枚举"""
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class SpanContext:
    """Span上下文"""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    baggage: Dict[str, str] = field(default_factory=dict)
    
    @classmethod
    def create_root(cls) -> 'SpanContext':
        """创建根Span上下文"""
        return cls(
            trace_id=str(uuid.uuid4()),
            span_id=str(uuid.uuid4())
        )
    
    @classmethod
    def create_child(cls, parent: 'SpanContext') -> 'SpanContext':
        """创建子Span上下文"""
        return cls(
            trace_id=parent.trace_id,
            span_id=str(uuid.uuid4()),
            parent_span_id=parent.span_id,
            baggage=parent.baggage.copy()
        )
    
    def set_baggage(self, key: str, value: str):
        """设置行李数据"""
        self.baggage[key] = value
    
    def get_baggage(self, key: str) -> Optional[str]:
        """获取行李数据"""
        return self.baggage.get(key)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'trace_id': self.trace_id,
            'span_id': self.span_id,
            'parent_span_id': self.parent_span_id,
            'baggage': self.baggage
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SpanContext':
        """从字典创建"""
        return cls(
            trace_id=data['trace_id'],
            span_id=data['span_id'],
            parent_span_id=data.get('parent_span_id'),
            baggage=data.get('baggage', {})
        )
    
    def to_header_value(self) -> str:
        """转换为HTTP头值"""
        value = f"trace_id={self.trace_id};span_id={self.span_id}"
        if self.parent_span_id:
            value += f";parent_span_id={self.parent_span_id}"
        
        for key, val in self.baggage.items():
            value += f";{key}={val}"
        
        return value
    
    @classmethod
    def from_header_value(cls, header_value: str) -> Optional['SpanContext']:
        """从HTTP头值创建"""
        try:
            parts = header_value.split(';')
            data = {}
            baggage = {}
            
            for part in parts:
                if '=' in part:
                    key, value = part.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if key in ['trace_id', 'span_id', 'parent_span_id']:
                        data[key] = value
                    else:
                        baggage[key] = value
            
            if 'trace_id' in data and 'span_id' in data:
                data['baggage'] = baggage
                return cls.from_dict(data)
            
        except Exception:
            pass
        
        return None


@dataclass 
class TraceContext:
    """追踪上下文"""
    span_context: SpanContext
    tags: Dict[str, Any] = field(default_factory=dict)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    
    # 请求信息
    service_name: Optional[str] = None
    operation_name: Optional[str] = None
    
    # 时间信息
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    # 状态信息
    status: SpanStatus = SpanStatus.OK
    kind: SpanKind = SpanKind.INTERNAL
    
    # 错误信息
    error: Optional[Exception] = None
    error_message: Optional[str] = None
    
    def __post_init__(self):
        if self.start_time is None:
            self.start_time = datetime.now(timezone.utc)
    
    def set_tag(self, key: str, value: Any):
        """设置标签"""
        self.tags[key] = value
    
    def get_tag(self, key: str) -> Any:
        """获取标签"""
        return self.tags.get(key)
    
    def log(self, message: str, **fields):
        """添加日志"""
        log_entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'message': message,
            **fields
        }
        self.logs.append(log_entry)
    
    def set_error(self, error: Exception, message: str = None):
        """设置错误"""
        self.error = error
        self.error_message = message or str(error)
        self.status = SpanStatus.ERROR
        self.set_tag('error', True)
        self.set_tag('error.type', type(error).__name__)
        self.set_tag('error.message', self.error_message)
    
    def finish(self):
        """完成追踪"""
        if self.end_time is None:
            self.end_time = datetime.now(timezone.utc)
    
    @property
    def duration(self) -> Optional[float]:
        """获取持续时间（秒）"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None
    
    @property
    def is_finished(self) -> bool:
        """是否已完成"""
        return self.end_time is not None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = {
            'span_context': self.span_context.to_dict(),
            'tags': self.tags,
            'logs': self.logs,
            'service_name': self.service_name,
            'operation_name': self.operation_name,
            'status': self.status.value,
            'kind': self.kind.value
        }
        
        if self.start_time:
            data['start_time'] = self.start_time.isoformat()
        
        if self.end_time:
            data['end_time'] = self.end_time.isoformat()
        
        if self.duration is not None:
            data['duration'] = self.duration
        
        if self.error_message:
            data['error_message'] = self.error_message
        
        return data


class TraceContextManager:
    """追踪上下文管理器"""
    
    def __init__(self):
        self._local = threading.local()
    
    def get_current_context(self) -> Optional[TraceContext]:
        """获取当前上下文"""
        return getattr(self._local, 'context', None)
    
    def set_current_context(self, context: Optional[TraceContext]):
        """设置当前上下文"""
        self._local.context = context
    
    def clear_context(self):
        """清除当前上下文"""
        if hasattr(self._local, 'context'):
            delattr(self._local, 'context')
    
    def create_child_context(self, 
                            operation_name: str,
                            kind: SpanKind = SpanKind.INTERNAL,
                            service_name: str = None) -> TraceContext:
        """创建子上下文"""
        current = self.get_current_context()
        
        if current:
            span_context = SpanContext.create_child(current.span_context)
        else:
            span_context = SpanContext.create_root()
        
        return TraceContext(
            span_context=span_context,
            operation_name=operation_name,
            kind=kind,
            service_name=service_name or (current.service_name if current else None)
        )


# 全局追踪上下文管理器
_trace_context_manager = TraceContextManager()


def get_current_trace_context() -> Optional[TraceContext]:
    """获取当前追踪上下文"""
    return _trace_context_manager.get_current_context()


def set_current_trace_context(context: Optional[TraceContext]):
    """设置当前追踪上下文"""
    _trace_context_manager.set_current_context(context)


def create_child_trace_context(operation_name: str,
                              kind: SpanKind = SpanKind.INTERNAL,
                              service_name: str = None) -> TraceContext:
    """创建子追踪上下文"""
    return _trace_context_manager.create_child_context(operation_name, kind, service_name)