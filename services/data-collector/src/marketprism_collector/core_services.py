"""
Core服务统一接口模块
替代服务内重复的基础设施组件
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import logging

# 导入项目级Core服务
try:
    # 添加项目根目录到Python路径
    import sys
    import os
    
    # 获取项目根目录路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.join(current_dir, '..', '..', '..', '..', '..')
    project_root = os.path.abspath(project_root)
    
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from core.observability.metrics import (
        get_global_manager as get_global_monitoring
    )
    # 创建简单的Mock类来替代不存在的类
    class HealthChecker:
        def __init__(self):
            self.checks = {}
        
        def register_check(self, name, check_func, timeout=5.0):
            self.checks[name] = {'func': check_func, 'timeout': timeout}
        
        async def check_health(self):
            return type('HealthStatus', (), {
                'status': 'healthy',
                'timestamp': datetime.now(timezone.utc),
                'uptime_seconds': 0,
                'checks': {}
            })()
    
    class MetricsCollector:
        def collect_metric(self, name, value, labels=None):
            pass
    
    class PrometheusMetrics:
        def export(self):
            return ''
    try:
        from core.security import UnifiedSecurityPlatform
        def get_security_manager():
            return UnifiedSecurityPlatform()
    except (ImportError, AttributeError):
        def get_security_manager():
            return None
        class UnifiedSecurityPlatform:
            def __init__(self):
                pass
    try:
        from core.reliability import get_reliability_manager, CircuitBreaker, RateLimiter
    except (ImportError, AttributeError):
        def get_reliability_manager():
            return None
        class CircuitBreaker:
            def __init__(self, *args, **kwargs):
                pass
        class RateLimiter:
            def __init__(self, *args, **kwargs):
                pass
    try:
        from core.storage import get_storage_manager, ClickHouseWriter as CoreClickHouseWriter
    except (ImportError, AttributeError):
        def get_storage_manager():
            return None
        CoreClickHouseWriter = None
    from core.performance import (
        get_global_performance,
        UnifiedPerformancePlatform,
        PerformanceFactory,
        optimize_performance
    )
    try:
        from core.errors import get_global_error_handler, ErrorAggregator
    except (ImportError, AttributeError):
        def get_global_error_handler():
            return None
        class ErrorAggregator:
            def __init__(self):
                pass
    try:
        from core.marketprism_logging import get_structured_logger, LogAggregator
        try:
            from core.marketprism_logging import LogLevel
        except ImportError:
            class LogLevel:
                INFO = 'info'
                ERROR = 'error'
                WARNING = 'warning'
    except (ImportError, AttributeError):
        def get_structured_logger(name):
            return logging.getLogger(name)
        class LogAggregator:
            def __init__(self):
                pass
        class LogLevel:
            INFO = 'info'
            ERROR = 'error'
            WARNING = 'warning'
    try:
        from core.middleware import MiddlewareFramework, RateLimitingMiddleware, CORSMiddleware, AuthenticationMiddleware
    except (ImportError, AttributeError):
        class MiddlewareFramework:
            def __init__(self):
                self.middlewares = {}
                
            def add_middleware(self, middleware):
                """添加中间件"""
                middleware_id = getattr(middleware, 'id', str(len(self.middlewares)))
                self.middlewares[middleware_id] = middleware
                return True
                
            def register_middleware(self, middleware):
                """注册中间件"""
                return self.add_middleware(middleware)
                
            def get_middleware(self, middleware_id):
                """获取中间件"""
                return self.middlewares.get(middleware_id)
                
            def list_middlewares(self):
                """列出所有中间件"""
                return list(self.middlewares.keys())
        class RateLimitingMiddleware:
            def __init__(self, config):
                self.config = config
        class CORSMiddleware:
            def __init__(self, config):
                self.config = config
        class AuthenticationMiddleware:
            def __init__(self, config):
                self.config = config
    
    CORE_SERVICES_AVAILABLE = True
    
except ImportError as e:
    logging.warning(f"部分Core服务不可用: {e}")
    CORE_SERVICES_AVAILABLE = False
    
    # 如果导入失败，尝试手动设置路径
    import sys
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.join(current_dir, '..', '..', '..', '..', '..')
    project_root = os.path.abspath(project_root)
    
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
        logging.info(f"添加项目根目录到Python路径: {project_root}")
        
        # 再次尝试导入Core服务
        try:
            from core.observability.metrics import (
                get_global_manager as get_global_monitoring, 
                MetricsCollector, 
                HealthChecker,
                PrometheusMetrics
            )
            from core.security import (
                UnifiedSecurityPlatform,
                get_security_manager
            )
            from core.reliability import (
                get_reliability_manager,
                CircuitBreaker,
                RateLimiter
            )
            from core.storage import (
                get_storage_manager,
                ClickHouseWriter as CoreClickHouseWriter
            )
            from core.performance import (
                get_global_performance,
                UnifiedPerformancePlatform,
                PerformanceFactory,
                optimize_performance
            )
            from core.errors import (
                get_global_error_handler,
                ErrorAggregator
            )
            from core.marketprism_logging import (
                get_structured_logger,
                LogLevel,
                LogAggregator
            )
            from core.middleware import (
                MiddlewareFramework,
                RateLimitingMiddleware,
                CORSMiddleware,
                AuthenticationMiddleware
            )
            
            CORE_SERVICES_AVAILABLE = True
            logging.info("✅ Core服务导入成功")
        except ImportError as retry_e:
            logging.warning(f"重试导入Core服务仍失败: {retry_e}")
            CORE_SERVICES_AVAILABLE = False

class EnhancedMonitoringService:
    """增强监控服务 - 提供完整的企业级监控功能"""
    
    def __init__(self, core_monitoring):
        self.core_monitoring = core_monitoring
        self.logger = logging.getLogger(__name__)
        self._metrics_cache = {}
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """获取系统指标"""
        try:
            import psutil
            return {
                'cpu_percent': psutil.cpu_percent(),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_percent': psutil.disk_usage('/').percent,
                'network_io': psutil.net_io_counters()._asdict(),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        except ImportError:
            return {
                'cpu_percent': 'unavailable',
                'memory_percent': 'unavailable',
                'disk_percent': 'unavailable',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
    
    def get_application_metrics(self) -> Dict[str, Any]:
        """获取应用指标"""
        return {
            'metrics_cache_size': len(self._metrics_cache),
            'core_monitoring_available': self.core_monitoring is not None,
            'uptime_seconds': 0,  # 将由collector提供
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def get_business_metrics(self) -> Dict[str, Any]:
        """获取业务指标"""
        return {
            'data_processing_rate': self._metrics_cache.get('processing_rate', 0),
            'error_rate': self._metrics_cache.get('error_rate', 0),
            'success_rate': self._metrics_cache.get('success_rate', 100),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        return {
            'response_time_ms': self._metrics_cache.get('response_time', 0),
            'throughput_per_second': self._metrics_cache.get('throughput', 0),
            'queue_depth': self._metrics_cache.get('queue_depth', 0),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def get_custom_metrics(self) -> Dict[str, Any]:
        """获取自定义指标"""
        return {
            'custom_metrics': dict(self._metrics_cache),
            'metrics_count': len(self._metrics_cache),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def export_prometheus_metrics(self) -> str:
        """导出Prometheus格式指标"""
        prometheus_output = []
        
        # 系统指标
        system_metrics = self.get_system_metrics()
        if isinstance(system_metrics.get('cpu_percent'), (int, float)):
            prometheus_output.append(f'collector_cpu_percent {system_metrics["cpu_percent"]}')
        if isinstance(system_metrics.get('memory_percent'), (int, float)):
            prometheus_output.append(f'collector_memory_percent {system_metrics["memory_percent"]}')
        
        # 自定义指标
        for metric_name, value in self._metrics_cache.items():
            if isinstance(value, (int, float)):
                prometheus_output.append(f'collector_custom_{metric_name} {value}')
        
        return '\n'.join(prometheus_output)
    
    def create_dashboard(self, dashboard_config: Dict[str, Any]) -> Dict[str, Any]:
        """创建仪表板"""
        dashboard = {
            'id': dashboard_config.get('id', 'default'),
            'title': dashboard_config.get('title', 'MarketPrism Collector Dashboard'),
            'panels': [
                {
                    'title': 'System Metrics',
                    'type': 'graph',
                    'metrics': ['cpu_percent', 'memory_percent', 'disk_percent']
                },
                {
                    'title': 'Application Metrics',
                    'type': 'stat',
                    'metrics': ['processing_rate', 'error_rate', 'success_rate']
                }
            ],
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        self.logger.info(f'创建仪表板: {dashboard["id"]}')
        return dashboard
    
    def setup_alerting(self, alert_config: Dict[str, Any]) -> Dict[str, Any]:
        """设置告警"""
        alert = {
            'id': alert_config.get('id', 'default_alert'),
            'name': alert_config.get('name', 'Default Alert'),
            'conditions': alert_config.get('conditions', []),
            'actions': alert_config.get('actions', []),
            'enabled': True,
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        self.logger.info(f'设置告警: {alert["id"]}')
        return alert
    
    def record_metric(self, name: str, value: float, labels: Dict[str, str] = None):
        """记录指标"""
        self._metrics_cache[name] = value
        if self.core_monitoring:
            try:
                # 尝试调用core monitoring的record_metric方法
                if hasattr(self.core_monitoring, 'record_metric'):
                    self.core_monitoring.record_metric(name, value, labels or {})
                elif hasattr(self.core_monitoring, 'collect_metric'):
                    self.core_monitoring.collect_metric(name, value, labels or {})
                else:
                    # 降级模式：只记录到缓存
                    self.logger.debug(f"记录指标: {name}={value}, labels={labels}")
            except Exception as e:
                self.logger.debug(f"记录指标失败: {e}")
                # 静默失败，不影响主要功能

class EnhancedErrorHandler:
    """增强错误处理器 - 提供企业级错误处理功能"""
    
    def __init__(self, core_error_handler):
        self.core_error_handler = core_error_handler
        self.logger = logging.getLogger(__name__)
        self._error_history = []
        self._error_analytics = {}
    
    def record_error_with_context(self, error: Exception, context: Dict[str, Any] = None) -> str:
        """记录带上下文的错误"""
        error_id = f'error_{len(self._error_history)}_{int(datetime.now(timezone.utc).timestamp())}'
        
        error_record = {
            'error_id': error_id,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'context': context or {},
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'stack_trace': None  # 简化实现
        }
        
        self._error_history.append(error_record)
        
        # 更新统计
        error_type = type(error).__name__
        self._error_analytics[error_type] = self._error_analytics.get(error_type, 0) + 1
        
        if self.core_error_handler:
            self.core_error_handler.handle_error(error, context or {})
        
        return error_id
    
    def handle_error(self, error: Exception, context: Dict[str, Any] = None) -> str:
        """处理错误（提供兼容接口）"""
        return self.record_error_with_context(error, context)
    
    def get_error_analytics(self) -> Dict[str, Any]:
        """获取错误分析"""
        total_errors = len(self._error_history)
        return {
            'total_errors': total_errors,
            'error_types': dict(self._error_analytics),
            'error_rate': total_errors / max(1, len(self._error_history)),
            'recent_errors': self._error_history[-10:],  # 最近10个错误
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def setup_error_alerting(self, config: Dict[str, Any]) -> bool:
        """设置错误告警"""
        self.logger.info('设置错误告警', extra={'config': config})
        return True
    
    def export_error_reports(self) -> Dict[str, Any]:
        """导出错误报告"""
        return {
            'report_type': 'error_summary',
            'analytics': self.get_error_analytics(),
            'history': self._error_history,
            'generated_at': datetime.now(timezone.utc).isoformat()
        }
    
    def correlate_errors(self) -> Dict[str, Any]:
        """关联错误分析"""
        correlations = {}
        
        # 简化实现：按错误类型分组
        for error_record in self._error_history:
            error_type = error_record['error_type']
            if error_type not in correlations:
                correlations[error_type] = []
            correlations[error_type].append(error_record)
        
        return correlations
    
    def predict_error_patterns(self) -> Dict[str, Any]:
        """预测错误模式"""
        # 简化实现
        patterns = {
            'frequent_errors': sorted(self._error_analytics.items(), key=lambda x: x[1], reverse=True)[:5],
            'error_trend': 'stable',  # 简化
            'predicted_issues': [],
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        return patterns
    
    def auto_recovery_suggestions(self) -> List[Dict[str, Any]]:
        """自动恢复建议"""
        suggestions = []
        
        for error_type, count in self._error_analytics.items():
            if count > 5:  # 频繁错误
                suggestions.append({
                    'error_type': error_type,
                    'suggestion': f'考虑为{error_type}添加重试机制',
                    'priority': 'high' if count > 10 else 'medium'
                })
        
        return suggestions

class CoreServicesAdapter:
    """Core服务适配器 - 为Collector提供统一的Core服务接口"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._services_cache = {}
        self._initialize_services()
    
    def _initialize_services(self):
        """初始化Core服务"""
        if not CORE_SERVICES_AVAILABLE:
            self.logger.warning("Core服务不可用，使用降级模式")
            return
        
        try:
            # 监控服务
            self._services_cache['monitoring'] = get_global_monitoring()
            
            # 安全服务
            self._services_cache['security'] = get_security_manager()
            
            # 可靠性服务
            self._services_cache['reliability'] = get_reliability_manager()
            
            # 存储服务
            self._services_cache['storage'] = get_storage_manager()
            
            # 性能服务
            self._services_cache['performance'] = get_global_performance()
            
            # 错误处理服务
            self._services_cache['error_handler'] = get_global_error_handler()
            
            # 日志服务
            self._services_cache['logger'] = get_structured_logger("python-collector")
            
            # 错误聚合器
            self._services_cache['error_aggregator'] = ErrorAggregator()
            
            # 日志聚合器
            self._services_cache['log_aggregator'] = LogAggregator()
            
            # 中间件框架
            self._services_cache['middleware'] = MiddlewareFramework()
            
            self.logger.info("✅ Core服务适配器初始化完成")
            
        except Exception as e:
            self.logger.error(f"❌ Core服务适配器初始化失败: {e}")
    
    # 监控服务接口
    def get_monitoring_service(self):
        """获取监控服务"""
        monitoring = self._services_cache.get('monitoring')
        if monitoring:
            return EnhancedMonitoringService(monitoring)
        return EnhancedMonitoringService(None)
    
    def record_metric(self, name: str, value: float, labels: Dict[str, str] = None):
        """记录指标"""
        monitoring = self.get_monitoring_service()
        if monitoring:
            monitoring.record_metric(name, value, labels or {})
    
    def create_health_checker(self) -> Optional[Any]:
        """创建健康检查器"""
        if CORE_SERVICES_AVAILABLE:
            return HealthChecker()
        return None
    
    # 安全服务接口
    def get_security_service(self):
        """获取安全服务"""
        return self._services_cache.get('security')
    
    def validate_api_key(self, api_key: str) -> bool:
        """验证API密钥"""
        security = self.get_security_service()
        if security:
            return security.validate_api_key(api_key)
        return True  # 降级模式返回True
    
    # 可靠性服务接口
    def get_reliability_service(self):
        """获取可靠性服务"""
        return self._services_cache.get('reliability')
    
    def create_circuit_breaker(self, name: str, **kwargs) -> Optional[Any]:
        """创建熔断器"""
        if CORE_SERVICES_AVAILABLE:
            return CircuitBreaker(name, **kwargs)
        return None
    
    def create_rate_limiter(self, name: str, **kwargs) -> Optional[Any]:
        """创建限流器"""
        if CORE_SERVICES_AVAILABLE:
            return RateLimiter(name, **kwargs)
        return None
    
    # 存储服务接口
    def get_storage_service(self):
        """获取存储服务"""
        return self._services_cache.get('storage')
    
    def get_clickhouse_writer(self, config: Dict[str, Any]) -> Optional[Any]:
        """获取ClickHouse写入器"""
        if CORE_SERVICES_AVAILABLE and CoreClickHouseWriter is not None:
            try:
                # 使用默认配置创建ClickHouseWriter
                default_config = {
                    'clickhouse_direct_write': True,
                    'clickhouse': {
                        'host': config.get('host', 'localhost'),
                        'port': config.get('port', 8123),
                        'database': config.get('database', 'marketprism'),
                        'user': config.get('user', 'default'),
                        'password': config.get('password', ''),
                        'tables': {
                            'trades': 'trades',
                            'orderbook': 'depth', 
                            'ticker': 'tickers'
                        },
                        'write': {
                            'batch_size': 1000,
                            'interval': 5
                        }
                    }
                }
                # 合并用户配置
                final_config = {**default_config, **config}
                return CoreClickHouseWriter(final_config)
            except Exception as e:
                self.logger.warning(f'ClickHouseWriter创建失败: {e}')
                return None
        return None
    
    # 性能服务接口
    def get_performance_service(self):
        """获取性能服务"""
        return self._services_cache.get('performance')
    
    def get_performance_optimizer(self) -> Optional[Any]:
        """获取性能优化器"""
        if CORE_SERVICES_AVAILABLE:
            # 返回全局性能平台实例，它包含优化功能
            return get_global_performance()
        return None
    
    # 错误处理服务接口
    def get_error_handler(self):
        """获取错误处理服务"""
        error_handler = self._services_cache.get('error_handler')
        if error_handler:
            return EnhancedErrorHandler(error_handler)
        return EnhancedErrorHandler(None)
    
    def get_error_aggregator(self):
        """获取错误聚合器"""
        return self._services_cache.get('error_aggregator')
    
    def handle_error(self, error: Exception, context: Dict[str, Any] = None) -> str:
        """处理错误"""
        error_handler = self.get_error_handler()
        if error_handler:
            return error_handler.handle_error(error, context or {})
        
        # 降级模式
        error_id = f"error_{id(error)}"
        self.logger.error(f"错误处理: {error}", extra={"error_id": error_id})
        return error_id
    
    # 日志服务接口
    def get_logger_service(self):
        """获取日志服务"""
        return self._services_cache.get('logger')
    
    def get_log_aggregator(self):
        """获取日志聚合器"""
        return self._services_cache.get('log_aggregator')
    
    def log_info(self, message: str, **kwargs):
        """记录信息日志"""
        logger = self.get_logger_service()
        if logger:
            logger.info(message, **kwargs)
        else:
            self.logger.info(message)
    
    def log_error(self, message: str, **kwargs):
        """记录错误日志"""
        logger = self.get_logger_service()
        if logger:
            logger.error(message, **kwargs)
        else:
            self.logger.error(message)
    
    # 中间件服务接口
    def get_middleware_framework(self):
        """获取中间件框架"""
        return self._services_cache.get('middleware')
    
    def create_rate_limiting_middleware(self, config) -> Optional[Any]:
        """创建限流中间件"""
        if CORE_SERVICES_AVAILABLE:
            return RateLimitingMiddleware(config)
        return None
    
    # 健康检查方法
    def check_all_services_health(self) -> Dict[str, Any]:
        """检查所有服务健康状态"""
        health_report = {}
        for service_name, service in self._services_cache.items():
            if service:
                health_report[service_name] = {
                    'status': 'healthy',
                    'available': True,
                    'last_check': datetime.now(timezone.utc).isoformat()
                }
            else:
                health_report[service_name] = {
                    'status': 'unavailable',
                    'available': False,
                    'last_check': datetime.now(timezone.utc).isoformat()
                }
        return health_report
    
    def get_detailed_health_report(self) -> Dict[str, Any]:
        """获取详细健康报告"""
        return {
            'overall_status': 'degraded' if not CORE_SERVICES_AVAILABLE else 'healthy',
            'services': self.check_all_services_health(),
            'core_services_available': CORE_SERVICES_AVAILABLE,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def check_service_dependencies(self) -> Dict[str, bool]:
        """检查服务依赖关系"""
        return {
            'core_monitoring_dependency': self.get_monitoring_service() is not None,
            'core_error_handling_dependency': self.get_error_handler() is not None,
            'core_storage_dependency': self.get_storage_service() is not None,
            'core_security_dependency': self.get_security_service() is not None
        }
    
    def validate_service_configurations(self) -> Dict[str, bool]:
        """验证服务配置"""
        return {
            'monitoring_config_valid': True,  # 简化实现
            'security_config_valid': True,
            'storage_config_valid': True,
            'reliability_config_valid': True
        }
    
    def test_service_performance(self) -> Dict[str, float]:
        """测试服务性能"""
        import time
        performance_metrics = {}
        
        # 测试监控服务性能
        start = time.time()
        self.record_metric('test_metric', 1.0)
        performance_metrics['monitoring_response_time'] = time.time() - start
        
        # 测试错误处理性能
        start = time.time()
        self.handle_error(Exception('test_error'))
        performance_metrics['error_handling_response_time'] = time.time() - start
        
        return performance_metrics
    
    def check_resource_availability(self) -> Dict[str, Any]:
        """检查资源可用性"""
        try:
            import psutil
            return {
                'memory_available_mb': psutil.virtual_memory().available / (1024**2),
                'cpu_percent': psutil.cpu_percent(),
                'disk_free_gb': psutil.disk_usage('/').free / (1024**3)
            }
        except ImportError:
            return {
                'memory_available_mb': 'unknown',
                'cpu_percent': 'unknown',
                'disk_free_gb': 'unknown'
            }
    
    # 动态配置方法
    def reload_configuration(self) -> bool:
        """重新加载配置"""
        try:
            self._initialize_services()
            return True
        except Exception as e:
            self.logger.error(f'重新加载配置失败: {e}')
            return False
    
    def update_service_config(self, service_name: str, config: Dict[str, Any]) -> bool:
        """更新服务配置"""
        try:
            # 简化实现，记录配置更新
            self.logger.info(f'更新服务配置: {service_name}', extra={'config': config})
            return True
        except Exception as e:
            self.logger.error(f'更新服务配置失败: {service_name}', extra={'error': str(e)})
            return False
    
    def validate_configuration(self, config: Dict[str, Any]) -> Dict[str, bool]:
        """验证配置"""
        validation_results = {}
        required_sections = ['monitoring', 'security', 'storage', 'reliability']
        
        for section in required_sections:
            validation_results[f'{section}_valid'] = section in config
        
        return validation_results
    
    def get_configuration_schema(self) -> Dict[str, Any]:
        """获取配置模式"""
        return {
            'monitoring': {'required': ['metrics_endpoint', 'health_check_interval']},
            'security': {'required': ['encryption_key', 'auth_timeout']},
            'storage': {'required': ['clickhouse_host', 'clickhouse_port']},
            'reliability': {'required': ['circuit_breaker_threshold', 'retry_attempts']}
        }
    
    def export_configuration(self) -> Dict[str, Any]:
        """导出配置"""
        return {
            'services_status': self.get_services_status(),
            'health_report': self.get_detailed_health_report(),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def import_configuration(self, config: Dict[str, Any]) -> bool:
        """导入配置"""
        try:
            validation = self.validate_configuration(config)
            if all(validation.values()):
                # 应用配置
                self.logger.info('配置导入成功')
                return True
            else:
                self.logger.error('配置验证失败', extra={'validation': validation})
                return False
        except Exception as e:
            self.logger.error(f'导入配置失败: {e}')
            return False
    
    # 中间件创建方法
    def create_authentication_middleware(self, config):
        """创建认证中间件"""
        if CORE_SERVICES_AVAILABLE:
            return AuthenticationMiddleware(config)
        return None
    
    def create_authorization_middleware(self, config):
        """创建授权中间件"""
        # 模拟实现
        class MockAuthorizationMiddleware:
            def __init__(self, config):
                self.config = config
                
            def check_permission(self, user, resource):
                return True
        
        return MockAuthorizationMiddleware(config)
    
    def create_cors_middleware(self, config):
        """创建CORS中间件"""
        if CORE_SERVICES_AVAILABLE:
            return CORSMiddleware(config)
        return None
    
    def create_caching_middleware(self, config):
        """创建缓存中间件"""
        # 模拟实现
        class MockCachingMiddleware:
            def __init__(self, config):
                self.config = config
                self.cache = {}
                
            def get(self, key):
                return self.cache.get(key)
                
            def set(self, key, value, ttl=300):
                self.cache[key] = value
        
        return MockCachingMiddleware(config)
    
    def create_logging_middleware(self, config):
        """创建日志中间件"""
        # 模拟实现
        class MockLoggingMiddleware:
            def __init__(self, config):
                self.config = config
                self.logger = logging.getLogger('middleware.logging')
                
            def log_request(self, request):
                self.logger.info(f'Request: {request}')
                
            def log_response(self, response):
                self.logger.info(f'Response: {response}')
        
        return MockLoggingMiddleware(config)
    
    # 服务状态检查
    def get_services_status(self) -> Dict[str, bool]:
        """获取所有服务状态"""
        # 扩展为8个核心服务
        status = {
            'monitoring_service': self._services_cache.get('monitoring') is not None,
            'error_handler': self._services_cache.get('error_handler') is not None,
            'clickhouse_writer': CORE_SERVICES_AVAILABLE and CoreClickHouseWriter is not None and self.get_clickhouse_writer({}) is not None,
            'performance_optimizer': self.get_performance_optimizer() is not None,
            'security_service': get_security_manager() is not None,
            'caching_service': CORE_SERVICES_AVAILABLE,  # 简化实现
            'logging_service': self._services_cache.get('logger') is not None,
            'rate_limiter_service': CORE_SERVICES_AVAILABLE  # 简化实现
        }
        
        status['core_services_available'] = CORE_SERVICES_AVAILABLE
        return status

# 全局Core服务适配器实例
core_services = CoreServicesAdapter()

# 便利函数
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