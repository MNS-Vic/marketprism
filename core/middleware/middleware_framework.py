"""
MarketPrism API网关中间件框架

这个模块实现了灵活、高性能的中间件处理框架，基于责任链模式，
支持异步处理、中间件链管理、配置管理和错误处理。

核心功能:
1. 中间件框架：统一的中间件管理和处理
2. 中间件链：中间件的链式处理机制
3. 中间件处理器：异步中间件处理器
4. 基础中间件：所有中间件的基类
5. 上下文管理：请求处理上下文管理
6. 配置管理：中间件配置和参数管理
7. 错误处理：完善的错误处理机制
"""

from datetime import datetime, timezone
import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union, Tuple
import threading
from concurrent.futures import ThreadPoolExecutor


class MiddlewareType(Enum):
    """中间件类型枚举"""
    AUTHENTICATION = "authentication"      # 认证中间件
    AUTHORIZATION = "authorization"        # 授权中间件
    RATE_LIMITING = "rate_limiting"       # 限流中间件
    LOGGING = "logging"                   # 日志中间件
    CORS = "cors"                         # CORS中间件
    CACHING = "caching"                   # 缓存中间件
    SECURITY = "security"                 # 安全中间件
    MONITORING = "monitoring"             # 监控中间件
    CUSTOM = "custom"                     # 自定义中间件


class MiddlewareStatus(Enum):
    """中间件状态枚举"""
    INACTIVE = "inactive"                 # 未激活
    ACTIVE = "active"                     # 激活
    DISABLED = "disabled"                 # 禁用
    ERROR = "error"                       # 错误状态
    CONFIGURING = "configuring"          # 配置中
    INITIALIZING = "initializing"        # 初始化中


class MiddlewarePriority(Enum):
    """中间件优先级枚举"""
    HIGHEST = 1                           # 最高优先级
    HIGH = 25                             # 高优先级
    NORMAL = 50                           # 正常优先级
    LOW = 75                              # 低优先级
    LOWEST = 100                          # 最低优先级


@dataclass
class RequestHeaders:
    """请求头部管理"""
    headers: Dict[str, str] = field(default_factory=dict)
    
    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """获取请求头"""
        return self.headers.get(key.lower(), default)
    
    def set(self, key: str, value: str) -> None:
        """设置请求头"""
        self.headers[key.lower()] = value
    
    def remove(self, key: str) -> bool:
        """删除请求头"""
        key_lower = key.lower()
        if key_lower in self.headers:
            del self.headers[key_lower]
            return True
        return False
    
    def has(self, key: str) -> bool:
        """检查请求头是否存在"""
        return key.lower() in self.headers
    
    def to_dict(self) -> Dict[str, str]:
        """转换为字典"""
        return self.headers.copy()


@dataclass
class ResponseHeaders:
    """响应头部管理"""
    headers: Dict[str, str] = field(default_factory=dict)
    
    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """获取响应头"""
        return self.headers.get(key.lower(), default)
    
    def set(self, key: str, value: str) -> None:
        """设置响应头"""
        self.headers[key.lower()] = value
    
    def remove(self, key: str) -> bool:
        """删除响应头"""
        key_lower = key.lower()
        if key_lower in self.headers:
            del self.headers[key_lower]
            return True
        return False
    
    def has(self, key: str) -> bool:
        """检查响应头是否存在"""
        return key.lower() in self.headers
    
    def to_dict(self) -> Dict[str, str]:
        """转换为字典"""
        return self.headers.copy()


@dataclass
class MiddlewareRequest:
    """中间件请求模型"""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    method: str = "GET"
    path: str = "/"
    query_params: Dict[str, str] = field(default_factory=dict)
    headers: RequestHeaders = field(default_factory=RequestHeaders)
    body: Optional[bytes] = None
    remote_addr: str = ""
    user_agent: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_header(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """获取请求头"""
        return self.headers.get(key, default)
    
    def set_header(self, key: str, value: str) -> None:
        """设置请求头"""
        self.headers.set(key, value)
    
    def get_query_param(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """获取查询参数"""
        return self.query_params.get(key, default)
    
    def set_metadata(self, key: str, value: Any) -> None:
        """设置元数据"""
        self.metadata[key] = value
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """获取元数据"""
        return self.metadata.get(key, default)


@dataclass
class MiddlewareResponse:
    """中间件响应模型"""
    status_code: int = 200
    headers: ResponseHeaders = field(default_factory=ResponseHeaders)
    body: Optional[bytes] = None
    content_type: str = "application/json"
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_header(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """获取响应头"""
        return self.headers.get(key, default)
    
    def set_header(self, key: str, value: str) -> None:
        """设置响应头"""
        self.headers.set(key, value)
    
    def set_metadata(self, key: str, value: Any) -> None:
        """设置元数据"""
        self.metadata[key] = value
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """获取元数据"""
        return self.metadata.get(key, default)


@dataclass
class MiddlewareContext:
    """中间件处理上下文"""
    request: MiddlewareRequest
    response: Optional[MiddlewareResponse] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    processing_time: Optional[float] = None
    middleware_data: Dict[str, Any] = field(default_factory=dict)
    user_context: Dict[str, Any] = field(default_factory=dict)
    errors: List[Exception] = field(default_factory=list)
    
    def set_data(self, key: str, value: Any) -> None:
        """设置中间件数据"""
        self.middleware_data[key] = value
    
    def get_data(self, key: str, default: Any = None) -> Any:
        """获取中间件数据"""
        return self.middleware_data.get(key, default)
    
    def set_user_data(self, key: str, value: Any) -> None:
        """设置用户上下文数据"""
        self.user_context[key] = value
    
    def get_user_data(self, key: str, default: Any = None) -> Any:
        """获取用户上下文数据"""
        return self.user_context.get(key, default)
    
    def add_error(self, error: Exception) -> None:
        """添加错误"""
        self.errors.append(error)
    
    def has_errors(self) -> bool:
        """检查是否有错误"""
        return len(self.errors) > 0
    
    def finalize(self) -> None:
        """完成处理，计算处理时间"""
        self.end_time = time.time()
        self.processing_time = self.end_time - self.start_time


@dataclass
class MiddlewareResult:
    """中间件处理结果"""
    success: bool = True
    continue_chain: bool = True
    status_code: Optional[int] = None
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[bytes] = None
    error: Optional[Exception] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    processing_time: Optional[float] = None
    
    @classmethod
    def success_result(cls, continue_chain: bool = True, **kwargs) -> 'MiddlewareResult':
        """创建成功结果"""
        return cls(success=True, continue_chain=continue_chain, **kwargs)
    
    @classmethod
    def error_result(cls, error: Exception, continue_chain: bool = False, **kwargs) -> 'MiddlewareResult':
        """创建错误结果"""
        return cls(success=False, continue_chain=continue_chain, error=error, **kwargs)
    
    @classmethod
    def stop_result(cls, status_code: int = 200, body: Optional[bytes] = None, **kwargs) -> 'MiddlewareResult':
        """创建停止链结果"""
        return cls(success=True, continue_chain=False, status_code=status_code, body=body, **kwargs)


@dataclass
class MiddlewareConfig:
    """中间件配置"""
    middleware_id: str
    middleware_type: MiddlewareType
    name: str = ""
    description: str = ""
    enabled: bool = True
    priority: MiddlewarePriority = MiddlewarePriority.NORMAL
    config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self.config.get(key, default)
    
    def set_config(self, key: str, value: Any) -> None:
        """设置配置项"""
        self.config[key] = value
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """获取元数据"""
        return self.metadata.get(key, default)
    
    def set_metadata(self, key: str, value: Any) -> None:
        """设置元数据"""
        self.metadata[key] = value


class BaseMiddleware(ABC):
    """基础中间件抽象类"""
    
    def __init__(self, config: MiddlewareConfig):
        self.config = config
        self.status = MiddlewareStatus.INACTIVE
        self.stats = {
            'requests_processed': 0,
            'requests_success': 0,
            'requests_error': 0,
            'total_processing_time': 0.0,
            'average_processing_time': 0.0,
        }
        self._lock = threading.Lock()
    
    @abstractmethod
    async def process_request(self, context: MiddlewareContext) -> MiddlewareResult:
        """处理请求 - 子类必须实现"""
        pass
    
    async def process_response(self, context: MiddlewareContext) -> MiddlewareResult:
        """处理响应 - 子类可选实现"""
        return MiddlewareResult.success_result()
    
    async def initialize(self) -> bool:
        """初始化中间件 - 子类可选实现"""
        self.status = MiddlewareStatus.ACTIVE
        return True
    
    async def shutdown(self) -> bool:
        """关闭中间件 - 子类可选实现"""
        self.status = MiddlewareStatus.INACTIVE
        return True
    
    def update_stats(self, processing_time: float, success: bool) -> None:
        """更新统计信息"""
        with self._lock:
            self.stats['requests_processed'] += 1
            if success:
                self.stats['requests_success'] += 1
            else:
                self.stats['requests_error'] += 1
            
            self.stats['total_processing_time'] += processing_time
            self.stats['average_processing_time'] = (
                self.stats['total_processing_time'] / self.stats['requests_processed']
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return self.stats.copy()
    
    def get_type(self) -> MiddlewareType:
        """获取中间件类型"""
        return self.config.middleware_type
    
    def get_priority(self) -> int:
        """获取中间件优先级"""
        return self.config.priority.value
    
    def is_enabled(self) -> bool:
        """检查中间件是否启用"""
        return self.config.enabled and self.status == MiddlewareStatus.ACTIVE


class MiddlewareChain:
    """中间件链管理器"""
    
    def __init__(self):
        self.middlewares: List[BaseMiddleware] = []
        self._sorted = False
        self._lock = threading.Lock()
    
    def add_middleware(self, middleware: BaseMiddleware) -> bool:
        """添加中间件到链"""
        try:
            with self._lock:
                if middleware not in self.middlewares:
                    self.middlewares.append(middleware)
                    self._sorted = False
                    return True
                return False
        except Exception:
            return False
    
    def remove_middleware(self, middleware_id: str) -> bool:
        """从链中移除中间件"""
        try:
            with self._lock:
                for middleware in self.middlewares:
                    if middleware.config.middleware_id == middleware_id:
                        self.middlewares.remove(middleware)
                        self._sorted = False
                        return True
                return False
        except Exception:
            return False
    
    def get_middleware(self, middleware_id: str) -> Optional[BaseMiddleware]:
        """获取指定中间件"""
        with self._lock:
            for middleware in self.middlewares:
                if middleware.config.middleware_id == middleware_id:
                    return middleware
            return None
    
    def get_ordered_middlewares(self) -> List[BaseMiddleware]:
        """获取按优先级排序的中间件列表"""
        with self._lock:
            if not self._sorted:
                self.middlewares.sort(key=lambda m: m.get_priority())
                self._sorted = True
            return [m for m in self.middlewares if m.is_enabled()]
    
    def get_enabled_count(self) -> int:
        """获取启用的中间件数量"""
        return len(self.get_ordered_middlewares())
    
    def clear(self) -> None:
        """清空中间件链"""
        with self._lock:
            self.middlewares.clear()
            self._sorted = False


class MiddlewareProcessor:
    """中间件处理器"""
    
    def __init__(self, chain: MiddlewareChain):
        self.chain = chain
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'average_processing_time': 0.0,
        }
        self._lock = threading.Lock()
    
    async def process_request(self, context: MiddlewareContext) -> MiddlewareResult:
        """处理请求通过中间件链"""
        middlewares = self.chain.get_ordered_middlewares()
        start_time = time.time()
        
        try:
            # 处理请求阶段
            for middleware in middlewares:
                if not middleware.is_enabled():
                    continue
                
                middleware_start = time.time()
                try:
                    result = await middleware.process_request(context)
                    middleware_time = time.time() - middleware_start
                    middleware.update_stats(middleware_time, result.success)
                    
                    if not result.success:
                        if result.error:
                            context.add_error(result.error)
                        self._update_stats(time.time() - start_time, False)
                        return result
                    
                    if not result.continue_chain:
                        self._update_stats(time.time() - start_time, True)
                        return result
                        
                except Exception as e:
                    middleware_time = time.time() - middleware_start
                    middleware.update_stats(middleware_time, False)
                    context.add_error(e)
                    self._update_stats(time.time() - start_time, False)
                    return MiddlewareResult.error_result(e)
            
            # 如果有响应，处理响应阶段
            if context.response:
                for middleware in reversed(middlewares):
                    if not middleware.is_enabled():
                        continue
                    
                    middleware_start = time.time()
                    try:
                        result = await middleware.process_response(context)
                        middleware_time = time.time() - middleware_start
                        middleware.update_stats(middleware_time, result.success)
                        
                        if not result.success:
                            if result.error:
                                context.add_error(result.error)
                            self._update_stats(time.time() - start_time, False)
                            return result
                            
                    except Exception as e:
                        middleware_time = time.time() - middleware_start
                        middleware.update_stats(middleware_time, False)
                        context.add_error(e)
                        self._update_stats(time.time() - start_time, False)
                        return MiddlewareResult.error_result(e)
            
            context.finalize()
            self._update_stats(time.time() - start_time, True)
            return MiddlewareResult.success_result()
            
        except Exception as e:
            context.add_error(e)
            self._update_stats(time.time() - start_time, False)
            return MiddlewareResult.error_result(e)
    
    def _update_stats(self, processing_time: float, success: bool) -> None:
        """更新处理器统计信息"""
        with self._lock:
            self.stats['total_requests'] += 1
            if success:
                self.stats['successful_requests'] += 1
            else:
                self.stats['failed_requests'] += 1
            
            # 计算平均处理时间
            total_time = self.stats['average_processing_time'] * (self.stats['total_requests'] - 1)
            self.stats['average_processing_time'] = (total_time + processing_time) / self.stats['total_requests']
    
    def get_stats(self) -> Dict[str, Any]:
        """获取处理器统计信息"""
        with self._lock:
            return self.stats.copy()
    
    async def shutdown(self) -> None:
        """关闭处理器"""
        self.executor.shutdown(wait=True)


class MiddlewareFramework:
    """中间件框架主类"""
    
    def __init__(self):
        self.chain = MiddlewareChain()
        self.processor = MiddlewareProcessor(self.chain)
        self.middleware_configs: Dict[str, MiddlewareConfig] = {}
        self.middleware_instances: Dict[str, BaseMiddleware] = {}
        self._initialized = False
        self._lock = threading.Lock()
    
    async def initialize(self) -> bool:
        """初始化框架"""
        try:
            with self._lock:
                if self._initialized:
                    return True
                
                # 初始化所有中间件
                for middleware in self.middleware_instances.values():
                    success = await middleware.initialize()
                    if not success:
                        return False
                
                self._initialized = True
                return True
        except Exception:
            return False
    
    async def shutdown(self) -> bool:
        """关闭框架"""
        try:
            with self._lock:
                if not self._initialized:
                    return True
                
                # 关闭所有中间件
                for middleware in self.middleware_instances.values():
                    await middleware.shutdown()
                
                await self.processor.shutdown()
                self._initialized = False
                return True
        except Exception:
            return False
    
    def register_middleware(self, middleware: BaseMiddleware) -> bool:
        """注册中间件"""
        try:
            with self._lock:
                middleware_id = middleware.config.middleware_id
                if middleware_id in self.middleware_instances:
                    return False
                
                self.middleware_configs[middleware_id] = middleware.config
                self.middleware_instances[middleware_id] = middleware
                return self.chain.add_middleware(middleware)
        except Exception:
            return False
    
    def unregister_middleware(self, middleware_id: str) -> bool:
        """注销中间件"""
        try:
            with self._lock:
                if middleware_id not in self.middleware_instances:
                    return False
                
                success = self.chain.remove_middleware(middleware_id)
                if success:
                    del self.middleware_configs[middleware_id]
                    del self.middleware_instances[middleware_id]
                return success
        except Exception:
            return False
    
    def get_middleware(self, middleware_id: str) -> Optional[BaseMiddleware]:
        """获取中间件实例"""
        return self.middleware_instances.get(middleware_id)
    
    def get_middleware_config(self, middleware_id: str) -> Optional[MiddlewareConfig]:
        """获取中间件配置"""
        return self.middleware_configs.get(middleware_id)
    
    def list_middlewares(self) -> List[str]:
        """列出所有中间件ID"""
        return list(self.middleware_instances.keys())
    
    def get_enabled_middlewares(self) -> List[str]:
        """获取启用的中间件ID列表"""
        return [mid for mid, middleware in self.middleware_instances.items() if middleware.is_enabled()]
    
    async def process_request(self, request: MiddlewareRequest) -> Tuple[MiddlewareResult, MiddlewareContext]:
        """处理请求"""
        context = MiddlewareContext(request=request)
        result = await self.processor.process_request(context)
        return result, context
    
    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """获取综合统计信息"""
        processor_stats = self.processor.get_stats()
        middleware_stats = {}
        
        for middleware_id, middleware in self.middleware_instances.items():
            middleware_stats[middleware_id] = {
                'config': {
                    'type': middleware.config.middleware_type.value,
                    'name': middleware.config.name,
                    'enabled': middleware.config.enabled,
                    'priority': middleware.config.priority.value,
                },
                'status': middleware.status.value,
                'stats': middleware.get_stats()
            }
        
        return {
            'framework': {
                'initialized': self._initialized,
                'total_middlewares': len(self.middleware_instances),
                'enabled_middlewares': len(self.get_enabled_middlewares()),
            },
            'processor': processor_stats,
            'middlewares': middleware_stats,
        }


# 中间件异常类
class MiddlewareError(Exception):
    """中间件基础异常"""
    pass


class MiddlewareChainError(MiddlewareError):
    """中间件链异常"""
    pass


class MiddlewareConfigError(MiddlewareError):
    """中间件配置异常"""
    pass