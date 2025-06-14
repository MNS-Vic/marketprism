"""
MarketPrism Collector - Core 集成模块

提供与项目级core服务的统一集成接口
"""

from datetime import datetime, timezone
import logging
from typing import Optional
import asyncio
from typing import Dict, Any, List

# 导入项目级core服务
try:
    from core.observability.metrics import get_global_manager as get_global_monitoring
    from core.security import get_security_manager, SecurityManager  
    from core.reliability import get_reliability_manager, ReliabilityManager
    from core.storage import get_storage_manager, StorageManager
    from core.performance import get_performance_manager, PerformanceManager
    from core.tracing import get_current_trace_context, create_child_trace_context
    from core.errors import get_global_error_handler, UnifiedErrorHandler
    from core.marketprism_logging import get_logger, StructuredLogger
    from core.caching import create_multi_level_cache, CacheCoordinator
    from core.errors import get_global_error_handler, ErrorContext
    from core.storage.unified_storage_manager import UnifiedStorageManager
    from core.networking.unified_session_manager import UnifiedSessionManager
    from core.reliability.rate_limit_manager import RateLimitManager
except ImportError as e:
    logging.warning(f"部分core服务导入失败: {e}")
    
    # 提供mock接口防止导入错误
    def get_global_monitoring() -> Optional[object]:
        return None
    
    def get_security_manager() -> Optional[object]:
        return None
    
    def get_reliability_manager() -> Optional[object]:
        return None
    
    def get_storage_manager() -> Optional[object]:
        return None
    
    def get_performance_manager() -> Optional[object]:
        return None
    
    def get_current_trace_context() -> Optional[object]:
        return None
    
    def create_child_trace_context(*args, **kwargs) -> Optional[object]:
        return None
    
    def get_global_error_handler() -> Optional[object]:
        return None
    
    def get_logger(name: str) -> Optional[object]:
        return None
    
    def create_multi_level_cache(*args, **kwargs) -> Optional[object]:
        return None


class CoreServiceIntegration:
    """核心服务集成管理器"""
    
    def __init__(self):
        self._init_logger = logging.getLogger(__name__)  # 重命名避免与property冲突
        self._services = {}
        self._initialize_services()
    
    def _initialize_services(self):
        """初始化核心服务"""
        try:
            self._services["metrics"] = get_global_monitoring()
            self._services["security"] = get_security_manager()
            self._services["reliability"] = get_reliability_manager()
            self._services["storage"] = get_storage_manager()
            self._services["performance"] = get_performance_manager()
            self._services["error_handler"] = get_global_error_handler()
            self._services["logger"] = get_logger("marketprism_collector")
            
            self._init_logger.info("✅ 核心服务集成初始化完成")
        except Exception as e:
            self._init_logger.error(f"❌ 核心服务集成初始化失败: {e}")
    
    @property
    def metrics(self):
        """获取监控服务"""
        return self._services.get("metrics")
    
    @property
    def security(self):
        """获取安全服务"""
        return self._services.get("security")
    
    @property
    def reliability(self):
        """获取可靠性服务"""
        return self._services.get("reliability")
    
    @property
    def storage(self):
        """获取存储服务"""
        return self._services.get("storage")
    
    @property 
    def performance(self):
        """获取性能服务"""
        return self._services.get("performance")
    
    @property
    def error_handler(self):
        """获取错误处理服务"""
        return self._services.get("error_handler")
    
    @property
    def logger(self):
        """获取日志服务"""
        return self._services.get("logger")
    
    def is_service_available(self, service_name: str) -> bool:
        """检查服务是否可用"""
        service = self._services.get(service_name)
        return service is not None
    
    def get_health_status(self) -> dict:
        """获取所有服务健康状态"""
        status = {}
        for name, service in self._services.items():
            if service and hasattr(service, "get_health_status"):
                try:
                    status[name] = service.get_health_status()
                except Exception as e:
                    status[name] = {"healthy": False, "error": str(e)}
            else:
                status[name] = {"healthy": False, "reason": "服务不可用"}
        
        return status
    
    def create_trace_context(self, operation_name: str, **kwargs):
        """创建追踪上下文"""
        try:
            return create_child_trace_context(operation_name, **kwargs)
        except Exception:
            return None
    
    def handle_error(self, error: Exception) -> str:
        """处理错误"""
        if self.error_handler:
            try:
                return self.error_handler.handle_error(error)
            except Exception:
                pass
        return "unknown_error_id"
    
    def log_info(self, message: str, **kwargs):
        """记录信息日志"""
        if self.logger:
            try:
                self.logger.info(message, **kwargs)
            except Exception:
                pass
        else:
            logging.info(message)
    
    def log_error(self, message: str, **kwargs):
        """记录错误日志"""
        if self.logger:
            try:
                # 过滤掉不支持的error参数
                error_value = kwargs.get('error')
                safe_kwargs = {k: v for k, v in kwargs.items() if k != 'error'}
                if error_value:
                    message = f"{message}: {error_value}"
                self.logger.error(message, **safe_kwargs)
            except Exception:
                logging.error(f"{message} - {kwargs}")
        else:
            logging.error(f"{message} - {kwargs}")
    
    def record_metric(self, metric_name: str, value: float, labels: dict = None):
        """记录指标"""
        if self.metrics:
            try:
                self.metrics.record(metric_name, value, labels or {})
            except Exception:
                pass


# 全局集成实例
_core_integration = None


def get_core_integration() -> CoreServiceIntegration:
    """获取核心服务集成实例"""
    global _core_integration
    if _core_integration is None:
        _core_integration = CoreServiceIntegration()
    return _core_integration


# 便利函数
def get_metrics_service():
    """获取监控服务"""
    return get_core_integration().metrics


def get_security_service():
    """获取安全服务"""
    return get_core_integration().security


def get_reliability_service():
    """获取可靠性服务"""
    return get_core_integration().reliability


def get_storage_service():
    """获取存储服务"""
    return get_core_integration().storage


def get_performance_service():
    """获取性能服务"""
    return get_core_integration().performance


def get_error_handler_service():
    """获取错误处理服务"""
    return get_core_integration().error_handler


def get_logger_service():
    """获取日志服务"""
    return get_core_integration().logger


def log_collector_info(message: str, **kwargs):
    """记录collector信息日志"""
    get_core_integration().log_info(message, component="collector", **kwargs)


def log_collector_error(message: str, **kwargs):
    """记录collector错误日志"""
    get_core_integration().log_error(message, component="collector", **kwargs)


def handle_collector_error(error: Exception) -> str:
    """处理collector错误"""
    return get_core_integration().handle_error(error)


def record_collector_metric(metric_name: str, value: float, **labels):
    """记录collector指标"""
    labels.update({"component": "collector"})
    get_core_integration().record_metric(metric_name, value, labels)