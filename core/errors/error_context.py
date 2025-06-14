"""
错误上下文和元数据管理

提供丰富的错误上下文信息收集、管理和分析功能。
包括执行环境、请求上下文、系统状态等信息。
"""

from datetime import datetime, timezone
import os
import sys
import psutil
import threading
import traceback
from typing import Dict, Any, Optional, List, Union
from types import TracebackType
from dataclasses import dataclass, field
from contextlib import contextmanager


@dataclass
class StackTraceInfo:
    """堆栈跟踪信息"""
    filename: str
    function_name: str
    line_number: int
    code_context: Optional[str] = None
    
    @classmethod
    def from_frame(cls, frame: traceback.FrameSummary) -> 'StackTraceInfo':
        """从traceback frame创建堆栈信息"""
        return cls(
            filename=frame.filename,
            function_name=frame.name,
            line_number=frame.lineno,
            code_context=frame.line
        )


@dataclass
class SystemInfo:
    """系统信息快照"""
    timestamp: datetime
    python_version: str
    platform: str
    hostname: str
    process_id: int
    thread_id: int
    cpu_count: int
    memory_total: int
    memory_available: int
    memory_percent: float
    cpu_percent: float
    disk_usage: Dict[str, Any]
    
    @classmethod
    def capture(cls) -> 'SystemInfo':
        """捕获当前系统信息"""
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return cls(
            timestamp=datetime.now(timezone.utc),
            python_version=sys.version,
            platform=sys.platform,
            hostname=os.uname().nodename if hasattr(os, 'uname') else 'unknown',
            process_id=os.getpid(),
            thread_id=threading.get_ident(),
            cpu_count=psutil.cpu_count(),
            memory_total=memory.total,
            memory_available=memory.available,
            memory_percent=memory.percent,
            cpu_percent=psutil.cpu_percent(interval=0.1),
            disk_usage={
                'total': disk.total,
                'used': disk.used,
                'free': disk.free,
                'percent': (disk.used / disk.total) * 100
            }
        )


@dataclass
class RequestContext:
    """请求上下文信息"""
    request_id: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    query_params: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            k: v for k, v in self.__dict__.items() 
            if v is not None
        }


@dataclass
class BusinessContext:
    """业务上下文信息"""
    exchange_name: Optional[str] = None
    symbol: Optional[str] = None
    market_type: Optional[str] = None
    data_type: Optional[str] = None
    operation: Optional[str] = None
    component: Optional[str] = None
    service_name: Optional[str] = None
    workflow_id: Optional[str] = None
    step_name: Optional[str] = None
    additional_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            k: v for k, v in self.__dict__.items() 
            if v is not None and k != 'additional_data'
        }
        result.update(self.additional_data)
        return result


@dataclass
class ErrorMetadata:
    """错误元数据"""
    error_id: str
    correlation_id: Optional[str] = None
    parent_error_id: Optional[str] = None
    retry_count: int = 0
    first_occurrence: Optional[datetime] = None
    last_occurrence: Optional[datetime] = None
    occurrence_count: int = 1
    resolved: bool = False
    resolution_time: Optional[datetime] = None
    resolution_method: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    
    def increment_occurrence(self):
        """增加发生次数"""
        self.occurrence_count += 1
        self.last_occurrence = datetime.now(timezone.utc)
        if self.first_occurrence is None:
            self.first_occurrence = self.last_occurrence
    
    def mark_resolved(self, resolution_method: str):
        """标记为已解决"""
        self.resolved = True
        self.resolution_time = datetime.now(timezone.utc)
        self.resolution_method = resolution_method


class ErrorContext:
    """错误上下文管理器
    
    收集和管理错误发生时的完整上下文信息，包括：
    - 系统状态信息
    - 请求上下文
    - 业务上下文  
    - 堆栈跟踪信息
    - 错误元数据
    """
    
    def __init__(self):
        self.system_info: Optional[SystemInfo] = None
        self.request_context: Optional[RequestContext] = None
        self.business_context: Optional[BusinessContext] = None
        self.stack_trace: List[StackTraceInfo] = []
        self.error_metadata: Optional[ErrorMetadata] = None
        self.custom_data: Dict[str, Any] = {}
        self.captured_at = datetime.now(timezone.utc)
    
    def capture_system_info(self) -> 'ErrorContext':
        """捕获系统信息"""
        try:
            self.system_info = SystemInfo.capture()
        except Exception as e:
            # 如果无法捕获系统信息，记录基本信息
            self.custom_data['system_capture_error'] = str(e)
        return self
    
    def set_request_context(self, context: RequestContext) -> 'ErrorContext':
        """设置请求上下文"""
        self.request_context = context
        return self
    
    def set_business_context(self, context: BusinessContext) -> 'ErrorContext':
        """设置业务上下文"""
        self.business_context = context
        return self
    
    def capture_stack_trace(self, tb: Optional[TracebackType] = None) -> 'ErrorContext':
        """捕获堆栈跟踪"""
        try:
            if tb is None:
                # 如果没有提供traceback，使用当前堆栈
                frames = traceback.extract_stack()[:-1]  # 排除当前frame
            else:
                frames = traceback.extract_tb(tb)
            
            self.stack_trace = [
                StackTraceInfo.from_frame(frame) for frame in frames
            ]
        except Exception as e:
            self.custom_data['stack_capture_error'] = str(e)
        return self
    
    def set_error_metadata(self, metadata: ErrorMetadata) -> 'ErrorContext':
        """设置错误元数据"""
        self.error_metadata = metadata
        return self
    
    def add_custom_data(self, key: str, value: Any) -> 'ErrorContext':
        """添加自定义数据"""
        self.custom_data[key] = value
        return self
    
    def update_custom_data(self, data: Dict[str, Any]) -> 'ErrorContext':
        """批量更新自定义数据"""
        self.custom_data.update(data)
        return self
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {
            'captured_at': self.captured_at.isoformat(),
            'custom_data': self.custom_data
        }
        
        if self.system_info:
            result['system_info'] = {
                'timestamp': self.system_info.timestamp.isoformat(),
                'python_version': self.system_info.python_version,
                'platform': self.system_info.platform,
                'hostname': self.system_info.hostname,
                'process_id': self.system_info.process_id,
                'thread_id': self.system_info.thread_id,
                'cpu_count': self.system_info.cpu_count,
                'memory_total': self.system_info.memory_total,
                'memory_available': self.system_info.memory_available,
                'memory_percent': self.system_info.memory_percent,
                'cpu_percent': self.system_info.cpu_percent,
                'disk_usage': self.system_info.disk_usage
            }
        
        if self.request_context:
            result['request_context'] = self.request_context.to_dict()
        
        if self.business_context:
            result['business_context'] = self.business_context.to_dict()
        
        if self.stack_trace:
            result['stack_trace'] = [
                {
                    'filename': frame.filename,
                    'function_name': frame.function_name,
                    'line_number': frame.line_number,
                    'code_context': frame.code_context
                }
                for frame in self.stack_trace
            ]
        
        if self.error_metadata:
            result['error_metadata'] = {
                'error_id': self.error_metadata.error_id,
                'correlation_id': self.error_metadata.correlation_id,
                'parent_error_id': self.error_metadata.parent_error_id,
                'retry_count': self.error_metadata.retry_count,
                'first_occurrence': self.error_metadata.first_occurrence.isoformat() if self.error_metadata.first_occurrence else None,
                'last_occurrence': self.error_metadata.last_occurrence.isoformat() if self.error_metadata.last_occurrence else None,
                'occurrence_count': self.error_metadata.occurrence_count,
                'resolved': self.error_metadata.resolved,
                'resolution_time': self.error_metadata.resolution_time.isoformat() if self.error_metadata.resolution_time else None,
                'resolution_method': self.error_metadata.resolution_method,
                'tags': self.error_metadata.tags
            }
        
        return result
    
    def get_summary(self) -> Dict[str, Any]:
        """获取上下文摘要信息"""
        summary = {
            'captured_at': self.captured_at.isoformat(),
            'has_system_info': self.system_info is not None,
            'has_request_context': self.request_context is not None,
            'has_business_context': self.business_context is not None,
            'stack_frames': len(self.stack_trace),
            'custom_data_keys': list(self.custom_data.keys())
        }
        
        if self.system_info:
            summary['memory_percent'] = self.system_info.memory_percent
            summary['cpu_percent'] = self.system_info.cpu_percent
        
        if self.request_context and self.request_context.trace_id:
            summary['trace_id'] = self.request_context.trace_id
        
        if self.business_context:
            summary['exchange'] = self.business_context.exchange_name
            summary['component'] = self.business_context.component
        
        return summary


class ContextManager:
    """上下文管理器
    
    管理请求级别的上下文信息，支持线程本地存储。
    """
    
    def __init__(self):
        self._local = threading.local()
    
    def set_request_context(self, context: RequestContext):
        """设置当前线程的请求上下文"""
        self._local.request_context = context
    
    def get_request_context(self) -> Optional[RequestContext]:
        """获取当前线程的请求上下文"""
        return getattr(self._local, 'request_context', None)
    
    def set_business_context(self, context: BusinessContext):
        """设置当前线程的业务上下文"""
        self._local.business_context = context
    
    def get_business_context(self) -> Optional[BusinessContext]:
        """获取当前线程的业务上下文"""
        return getattr(self._local, 'business_context', None)
    
    def clear_context(self):
        """清除当前线程的上下文"""
        if hasattr(self._local, 'request_context'):
            delattr(self._local, 'request_context')
        if hasattr(self._local, 'business_context'):
            delattr(self._local, 'business_context')
    
    @contextmanager
    def request_scope(self, context: RequestContext):
        """请求作用域上下文管理器"""
        old_context = self.get_request_context()
        self.set_request_context(context)
        try:
            yield
        finally:
            if old_context:
                self.set_request_context(old_context)
            else:
                if hasattr(self._local, 'request_context'):
                    delattr(self._local, 'request_context')
    
    @contextmanager
    def business_scope(self, context: BusinessContext):
        """业务作用域上下文管理器"""
        old_context = self.get_business_context()
        self.set_business_context(context)
        try:
            yield
        finally:
            if old_context:
                self.set_business_context(old_context)
            else:
                if hasattr(self._local, 'business_context'):
                    delattr(self._local, 'business_context')
    
    def create_error_context(self, 
                           capture_system: bool = True,
                           tb: Optional[TracebackType] = None) -> ErrorContext:
        """创建错误上下文"""
        context = ErrorContext()
        
        if capture_system:
            context.capture_system_info()
        
        if tb:
            context.capture_stack_trace(tb)
        
        request_ctx = self.get_request_context()
        if request_ctx:
            context.set_request_context(request_ctx)
        
        business_ctx = self.get_business_context()
        if business_ctx:
            context.set_business_context(business_ctx)
        
        return context


# 全局上下文管理器实例
_global_context_manager = None


def get_global_context_manager() -> ContextManager:
    """获取全局上下文管理器"""
    global _global_context_manager
    if _global_context_manager is None:
        _global_context_manager = ContextManager()
    return _global_context_manager


def reset_global_context_manager():
    """重置全局上下文管理器（主要用于测试）"""
    global _global_context_manager
    _global_context_manager = None