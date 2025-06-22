"""
MarketPrism Collector Core服务适配器 - 简化版本

直接使用core模块功能，移除复杂的适配逻辑
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone

# 直接导入core模块
try:
    from core.observability.metrics import get_global_manager as get_global_monitoring
    from core.security import get_security_manager
    from core.reliability import get_reliability_manager
    from core.storage import get_storage_manager
    from core.performance import get_global_performance
    from core.errors import get_global_error_handler
    from core.observability.logging import get_structured_logger
    CORE_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Core模块不可用: {e}")
    CORE_AVAILABLE = False
    
    # 提供降级实现
    def get_global_monitoring():
        return None
    def get_security_manager():
        return None
    def get_reliability_manager():
        return None
    def get_storage_manager():
        return None
    def get_global_performance():
        return None
    def get_global_error_handler():
        return None
    def get_structured_logger(name):
        return logging.getLogger(name)


class SimplifiedCoreServices:
    """简化的Core服务接口"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._init_services()
    
    def _init_services(self):
        """初始化服务"""
        if CORE_AVAILABLE:
            self.monitoring = get_global_monitoring()
            self.security = get_security_manager()
            self.reliability = get_reliability_manager()
            self.storage = get_storage_manager()
            self.performance = get_global_performance()
            self.error_handler = get_global_error_handler()
            self.logger_service = get_structured_logger("collector")
            
            self.logger.info("✅ Core服务初始化成功")
        else:
            self.monitoring = None
            self.security = None
            self.reliability = None
            self.storage = None
            self.performance = None
            self.error_handler = None
            self.logger_service = logging.getLogger("collector")
            
            self.logger.warning("⚠️ Core服务不可用，使用降级模式")
    
    # 监控服务
    def get_monitoring_service(self):
        """获取监控服务"""
        return self.monitoring
    
    def record_metric(self, name: str, value: float, labels: Dict[str, str] = None):
        """记录指标"""
        if self.monitoring and hasattr(self.monitoring, 'collect_metric'):
            self.monitoring.collect_metric(name, value, labels or {})
        else:
            self.logger.debug(f"记录指标: {name}={value}")
    
    # 安全服务
    def get_security_service(self):
        """获取安全服务"""
        return self.security
    
    def validate_api_key(self, api_key: str) -> bool:
        """验证API密钥"""
        if self.security and hasattr(self.security, 'validate_api_key'):
            return self.security.validate_api_key(api_key)
        return True  # 降级模式
    
    # 可靠性服务
    def get_reliability_service(self):
        """获取可靠性服务"""
        return self.reliability
    
    def create_circuit_breaker(self, name: str, **kwargs):
        """创建熔断器"""
        if self.reliability and hasattr(self.reliability, 'create_circuit_breaker'):
            return self.reliability.create_circuit_breaker(name, **kwargs)
        return None
    
    def create_rate_limiter(self, name: str, **kwargs):
        """创建限流器"""
        if self.reliability and hasattr(self.reliability, 'create_rate_limiter'):
            return self.reliability.create_rate_limiter(name, **kwargs)
        return None

    def create_health_checker(self, **kwargs):
        """创建健康检查器"""
        if self.monitoring and hasattr(self.monitoring, 'create_health_checker'):
            return self.monitoring.create_health_checker(**kwargs)
        # 返回一个简单的健康检查器mock
        return type('HealthChecker', (), {
            'check_health': lambda: {"status": "healthy", "timestamp": "2024-01-01T00:00:00Z"},
            'add_check': lambda name, func: None,
            'remove_check': lambda name: None,
            'get_status': lambda: "healthy"
        })()
    
    # 存储服务
    def get_storage_service(self):
        """获取存储服务"""
        return self.storage
    
    def get_clickhouse_writer(self, config: Dict[str, Any]):
        """获取ClickHouse写入器"""
        if self.storage and hasattr(self.storage, 'get_clickhouse_writer'):
            return self.storage.get_clickhouse_writer(config)
        return None
    
    # 性能服务
    def get_performance_service(self):
        """获取性能服务"""
        return self.performance
    
    def get_performance_optimizer(self):
        """获取性能优化器"""
        return self.performance
    
    # 错误处理服务
    def get_error_handler(self):
        """获取错误处理服务"""
        return self.error_handler
    
    def handle_error(self, error: Exception, context: Dict[str, Any] = None) -> str:
        """处理错误"""
        if self.error_handler and hasattr(self.error_handler, 'handle_error'):
            return self.error_handler.handle_error(error, context or {})
        else:
            # 降级处理
            error_id = f"error_{int(datetime.now(timezone.utc).timestamp())}"
            self.logger.error(f"错误处理[{error_id}]: {error}", exc_info=True)
            return error_id
    
    # 日志服务
    def get_logger_service(self):
        """获取日志服务"""
        return self.logger_service
    
    # 服务状态
    def get_services_status(self) -> Dict[str, bool]:
        """获取服务状态"""
        return {
            'core_available': CORE_AVAILABLE,
            'monitoring': self.monitoring is not None,
            'security': self.security is not None,
            'reliability': self.reliability is not None,
            'storage': self.storage is not None,
            'performance': self.performance is not None,
            'error_handler': self.error_handler is not None,
            'logger': self.logger_service is not None
        }


# 全局实例
core_services = SimplifiedCoreServices()

# 便利函数 - 保持向后兼容
def get_core_monitoring():
    """获取Core监控服务"""
    return core_services.get_monitoring_service()

def get_core_security():
    """获取Core安全服务"""
    return core_services.get_security_service()

def get_core_reliability():
    """获取Core可靠性服务"""
    return core_services.get_reliability_service()

def get_core_storage():
    """获取Core存储服务"""
    return core_services.get_storage_service()

def get_core_performance():
    """获取Core性能服务"""
    return core_services.get_performance_service()

def get_core_error_handler():
    """获取Core错误处理服务"""
    return core_services.get_error_handler()

def get_core_logger():
    """获取Core日志服务"""
    return core_services.get_logger_service()

# 向后兼容的类别名
CoreServicesAdapter = SimplifiedCoreServices
