"""
MarketPrism统一日志管理系统

整合所有日志功能：统一格式、级别优化、去重、性能监控等。
提供一站式的日志管理解决方案。
"""

import os
import sys
import time
import threading
from typing import Dict, Any, Optional, List, Union
from contextlib import contextmanager
from dataclasses import dataclass

from .unified_logger import UnifiedLogger, LoggerFactory, ComponentType, OperationType
from .level_optimizer import log_level_optimizer, LogLevel, BusinessCriticality
from .deduplication import log_deduplicator, LogEntry
from .log_standards import LogMessageTemplate, PerformanceMetric, BusinessEventLogger


@dataclass
class LogConfiguration:
    """统一日志配置"""
    # 基础配置
    global_level: str = "INFO"
    use_json_format: bool = False
    enable_file_logging: bool = True
    log_file_path: str = "/tmp/marketprism.log"
    
    # 性能配置
    enable_performance_mode: bool = False
    enable_deduplication: bool = True
    enable_aggregation: bool = True
    max_log_rate: float = 100.0  # 每秒最大日志数
    
    # 环境配置
    environment: str = "development"
    use_emoji: bool = False
    enable_debug: bool = False
    
    # 输出配置
    console_output: bool = True
    file_output: bool = True
    remote_logging: bool = False
    remote_endpoint: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> 'LogConfiguration':
        """从环境变量创建配置"""
        return cls(
            global_level=os.getenv("MARKETPRISM_LOG_LEVEL", "INFO"),
            use_json_format=os.getenv("MARKETPRISM_LOG_JSON", "false").lower() == "true",
            enable_file_logging=os.getenv("MARKETPRISM_LOG_FILE", "true").lower() == "true",
            log_file_path=os.getenv("MARKETPRISM_LOG_PATH", "/tmp/marketprism.log"),
            enable_performance_mode=os.getenv("MARKETPRISM_PERFORMANCE_MODE", "false").lower() == "true",
            enable_deduplication=os.getenv("MARKETPRISM_LOG_DEDUP", "true").lower() == "true",
            environment=os.getenv("MARKETPRISM_ENV", "development"),
            use_emoji=os.getenv("MARKETPRISM_USE_EMOJI", "false").lower() == "true",
            enable_debug=os.getenv("MARKETPRISM_DEBUG", "false").lower() == "true",
            remote_endpoint=os.getenv("MARKETPRISM_LOG_ENDPOINT")
        )


class UnifiedLogManager:
    """统一日志管理器 - 系统的核心日志管理类"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, config: Optional[LogConfiguration] = None):
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config: Optional[LogConfiguration] = None):
        if self._initialized:
            return
        
        self.config = config or LogConfiguration.from_env()
        self._loggers: Dict[str, UnifiedLogger] = {}
        self._performance_stats = {
            "total_logs": 0,
            "suppressed_logs": 0,
            "start_time": time.time(),
            "last_stats_report": time.time()
        }
        
        # 初始化系统
        self._initialize_logging_system()
        self._initialized = True
    
    def _initialize_logging_system(self):
        """初始化日志系统"""
        # 配置基础日志系统
        LoggerFactory.configure_logging(
            level=self.config.global_level,
            use_json=self.config.use_json_format,
            enable_file_logging=self.config.enable_file_logging,
            log_file_path=self.config.log_file_path
        )
        
        # 配置性能优化
        if self.config.enable_performance_mode:
            log_level_optimizer.optimize_for_performance(True)
        
        # 启动后台任务
        self._start_background_tasks()
    
    def _start_background_tasks(self):
        """启动后台任务"""
        # 统计报告任务
        def stats_reporter():
            while True:
                time.sleep(300)  # 每5分钟报告一次
                self._report_statistics()
        
        stats_thread = threading.Thread(target=stats_reporter, daemon=True)
        stats_thread.start()
    
    def get_logger(self, 
                   component: ComponentType,
                   exchange: Optional[str] = None,
                   market_type: Optional[str] = None,
                   correlation_id: Optional[str] = None) -> 'ManagedLogger':
        """获取托管的日志记录器"""
        
        # 构建logger键
        key_parts = [component.value]
        if exchange:
            key_parts.append(exchange)
        if market_type:
            key_parts.append(market_type)
        logger_key = ".".join(key_parts)
        
        if logger_key not in self._loggers:
            base_logger = LoggerFactory.get_logger(
                component=component,
                exchange=exchange,
                market_type=market_type,
                correlation_id=correlation_id
            )
            
            self._loggers[logger_key] = ManagedLogger(
                base_logger=base_logger,
                manager=self,
                component=component,
                exchange=exchange,
                market_type=market_type
            )
        
        return self._loggers[logger_key]
    
    def _should_log(self, 
                   component: ComponentType,
                   operation: OperationType,
                   level: LogLevel,
                   message: str,
                   criticality: BusinessCriticality = BusinessCriticality.NORMAL) -> tuple[bool, Optional[str]]:
        """统一的日志过滤逻辑"""
        
        # 性能统计
        self._performance_stats["total_logs"] += 1
        
        # 级别优化检查
        should_log_level, recommended_level = log_level_optimizer.should_log(
            component, operation, level, criticality
        )
        
        if not should_log_level:
            self._performance_stats["suppressed_logs"] += 1
            return False, None
        
        # 去重检查
        if self.config.enable_deduplication:
            log_entry = LogEntry(
                timestamp=time.time(),
                level=level.value,
                component=component.value,
                message=message
            )
            
            should_log_dedup, dedup_message = log_deduplicator.should_log(log_entry)
            if not should_log_dedup:
                self._performance_stats["suppressed_logs"] += 1
                return False, None
            
            return True, dedup_message
        
        return True, None
    
    def _report_statistics(self):
        """报告日志系统统计信息"""
        current_time = time.time()
        runtime = current_time - self._performance_stats["start_time"]
        
        # 获取各组件统计
        optimizer_stats = log_level_optimizer.get_performance_stats()
        deduplicator_stats = log_deduplicator.get_statistics()
        
        # 构建统计报告
        stats_report = {
            "log_manager_stats": {
                "total_logs_processed": self._performance_stats["total_logs"],
                "suppressed_logs": self._performance_stats["suppressed_logs"],
                "suppression_rate": self._performance_stats["suppressed_logs"] / max(self._performance_stats["total_logs"], 1),
                "runtime_seconds": runtime,
                "logs_per_second": self._performance_stats["total_logs"] / max(runtime, 1),
                "active_loggers": len(self._loggers)
            },
            "level_optimizer_stats": optimizer_stats,
            "deduplicator_stats": deduplicator_stats
        }
        
        # 使用系统logger记录统计
        system_logger = self.get_logger(ComponentType.MAIN)
        system_logger.performance("Log system statistics", stats_report)
        
        self._performance_stats["last_stats_report"] = current_time
    
    def get_system_statistics(self) -> Dict[str, Any]:
        """获取系统统计信息"""
        return {
            "configuration": {
                "global_level": self.config.global_level,
                "performance_mode": self.config.enable_performance_mode,
                "deduplication_enabled": self.config.enable_deduplication,
                "environment": self.config.environment
            },
            "performance": self._performance_stats,
            "optimizer": log_level_optimizer.get_performance_stats(),
            "deduplicator": log_deduplicator.get_statistics()
        }
    
    def update_configuration(self, new_config: LogConfiguration):
        """动态更新配置"""
        self.config = new_config
        
        # 重新配置优化器
        if new_config.enable_performance_mode:
            log_level_optimizer.optimize_for_performance(True)
        else:
            log_level_optimizer.optimize_for_performance(False)
    
    def shutdown(self):
        """关闭日志管理器"""
        # 最后一次统计报告
        self._report_statistics()
        
        # 清理资源
        self._loggers.clear()


class ManagedLogger:
    """托管的日志记录器 - 包装UnifiedLogger并添加管理功能"""
    
    def __init__(self, 
                 base_logger: UnifiedLogger,
                 manager: UnifiedLogManager,
                 component: ComponentType,
                 exchange: Optional[str] = None,
                 market_type: Optional[str] = None):
        self.base_logger = base_logger
        self.manager = manager
        self.component = component
        self.exchange = exchange
        self.market_type = market_type
        
        # 性能统计
        self._local_stats = {
            "logs_sent": 0,
            "logs_suppressed": 0,
            "last_log_time": time.time()
        }
    
    def _log_with_management(self, 
                           operation: OperationType,
                           level: LogLevel,
                           message: str,
                           criticality: BusinessCriticality = BusinessCriticality.NORMAL,
                           **kwargs):
        """带管理功能的日志记录"""
        
        # 检查是否应该记录
        should_log, additional_message = self.manager._should_log(
            self.component, operation, level, message, criticality
        )
        
        if not should_log:
            self._local_stats["logs_suppressed"] += 1
            return
        
        # 添加额外信息
        final_message = message
        if additional_message:
            final_message += f" {additional_message}"
        
        # 记录日志
        self._local_stats["logs_sent"] += 1
        self._local_stats["last_log_time"] = time.time()
        
        # 调用基础logger的相应方法
        if operation == OperationType.STARTUP:
            self.base_logger.startup(final_message, **kwargs)
        elif operation == OperationType.SHUTDOWN:
            self.base_logger.shutdown(final_message, **kwargs)
        elif operation == OperationType.CONNECTION:
            success = kwargs.pop('success', True)
            self.base_logger.connection(final_message, success=success, **kwargs)
        elif operation == OperationType.DATA_PROCESSING:
            self.base_logger.data_processing(final_message, **kwargs)
        elif operation == OperationType.ERROR_HANDLING:
            error = kwargs.pop('error', None)
            if level == LogLevel.ERROR:
                self.base_logger.error(final_message, error=error, **kwargs)
            else:
                self.base_logger.warning(final_message, **kwargs)
        elif operation == OperationType.PERFORMANCE:
            metrics = kwargs.pop('metrics', {})
            self.base_logger.performance(final_message, metrics, **kwargs)
        elif operation == OperationType.HEALTH_CHECK:
            healthy = kwargs.pop('healthy', True)
            self.base_logger.health_check(final_message, healthy=healthy, **kwargs)
    
    # 便捷方法
    def startup(self, message: str, **kwargs):
        """启动日志"""
        self._log_with_management(
            OperationType.STARTUP, LogLevel.INFO, message,
            BusinessCriticality.IMPORTANT, **kwargs
        )
    
    def shutdown(self, message: str, **kwargs):
        """停止日志"""
        self._log_with_management(
            OperationType.SHUTDOWN, LogLevel.INFO, message,
            BusinessCriticality.IMPORTANT, **kwargs
        )
    
    def connection_success(self, message: str, **kwargs):
        """连接成功日志"""
        self._log_with_management(
            OperationType.CONNECTION, LogLevel.INFO, message,
            BusinessCriticality.IMPORTANT, success=True, **kwargs
        )
    
    def connection_failure(self, message: str, error: Optional[Exception] = None, **kwargs):
        """连接失败日志"""
        self._log_with_management(
            OperationType.CONNECTION, LogLevel.ERROR, message,
            BusinessCriticality.CRITICAL, success=False, error=error, **kwargs
        )
    
    def data_processed(self, message: str, **kwargs):
        """数据处理日志"""
        # 🔧 修复：移除可能冲突的operation参数
        clean_kwargs = {k: v for k, v in kwargs.items() if k != 'operation'}
        self._log_with_management(
            OperationType.DATA_PROCESSING, LogLevel.DEBUG, message,
            BusinessCriticality.VERBOSE, **clean_kwargs
        )
    
    def error(self, message: str, error: Optional[Exception] = None, **kwargs):
        """错误日志"""
        # 🔧 修复：移除可能冲突的operation参数
        clean_kwargs = {k: v for k, v in kwargs.items() if k != 'operation'}
        self._log_with_management(
            OperationType.ERROR_HANDLING, LogLevel.ERROR, message,
            BusinessCriticality.CRITICAL, error=error, **clean_kwargs
        )
    
    def warning(self, message: str, **kwargs):
        """警告日志"""
        # 🔧 修复：移除可能冲突的operation参数
        clean_kwargs = {k: v for k, v in kwargs.items() if k != 'operation'}
        self._log_with_management(
            OperationType.ERROR_HANDLING, LogLevel.WARNING, message,
            BusinessCriticality.IMPORTANT, **clean_kwargs
        )
    
    def performance(self, message: str, metrics: Dict[str, Any], **kwargs):
        """性能日志"""
        # 🔧 修复：移除可能冲突的operation参数
        clean_kwargs = {k: v for k, v in kwargs.items() if k != 'operation'}
        self._log_with_management(
            OperationType.PERFORMANCE, LogLevel.INFO, message,
            BusinessCriticality.NORMAL, metrics=metrics, **clean_kwargs
        )
    
    def health_check(self, message: str, healthy: bool = True, **kwargs):
        """健康检查日志"""
        criticality = BusinessCriticality.NORMAL if healthy else BusinessCriticality.IMPORTANT
        level = LogLevel.DEBUG if healthy else LogLevel.WARNING

        self._log_with_management(
            OperationType.HEALTH_CHECK, level, message,
            criticality, healthy=healthy, **kwargs
        )

    def info(self, message: str, **kwargs):
        """通用信息日志 - 向后兼容"""
        # 🔧 修复：移除可能冲突的operation参数
        clean_kwargs = {k: v for k, v in kwargs.items() if k != 'operation'}
        self._log_with_management(
            OperationType.DATA_PROCESSING, LogLevel.INFO, message,
            BusinessCriticality.NORMAL, **clean_kwargs
        )

    def debug(self, message: str, **kwargs):
        """调试日志 - 向后兼容"""
        # 🔧 修复：移除可能冲突的operation参数
        clean_kwargs = {k: v for k, v in kwargs.items() if k != 'operation'}
        self._log_with_management(
            OperationType.DATA_PROCESSING, LogLevel.DEBUG, message,
            BusinessCriticality.VERBOSE, **clean_kwargs
        )
    
    @contextmanager
    def operation_context(self, operation_name: str):
        """操作上下文管理器"""
        start_time = time.time()
        self.startup(f"Starting {operation_name}")
        
        try:
            yield
            duration = time.time() - start_time
            self.performance(
                f"Completed {operation_name}",
                {"operation": operation_name, "duration_seconds": duration}
            )
        except Exception as e:
            duration = time.time() - start_time
            self.error(
                f"Failed {operation_name}",
                error=e,
                operation=operation_name,
                duration_seconds=duration
            )
            raise
    
    def get_local_statistics(self) -> Dict[str, Any]:
        """获取本地统计信息"""
        return {
            "component": self.component.value,
            "exchange": self.exchange,
            "market_type": self.market_type,
            "logs_sent": self._local_stats["logs_sent"],
            "logs_suppressed": self._local_stats["logs_suppressed"],
            "suppression_rate": self._local_stats["logs_suppressed"] / max(
                self._local_stats["logs_sent"] + self._local_stats["logs_suppressed"], 1
            ),
            "last_log_time": self._local_stats["last_log_time"]
        }


# 全局日志管理器实例
_global_log_manager = None
_manager_lock = threading.Lock()


def get_managed_logger(component: ComponentType,
                      exchange: Optional[str] = None,
                      market_type: Optional[str] = None,
                      correlation_id: Optional[str] = None) -> ManagedLogger:
    """获取托管日志记录器的全局函数"""
    global _global_log_manager
    
    if _global_log_manager is None:
        with _manager_lock:
            if _global_log_manager is None:
                _global_log_manager = UnifiedLogManager()
    
    return _global_log_manager.get_logger(component, exchange, market_type, correlation_id)


def configure_global_logging(config: Optional[LogConfiguration] = None):
    """配置全局日志系统"""
    global _global_log_manager
    
    with _manager_lock:
        _global_log_manager = UnifiedLogManager(config)


def get_global_log_statistics() -> Dict[str, Any]:
    """获取全局日志统计"""
    if _global_log_manager:
        return _global_log_manager.get_system_statistics()
    return {"error": "Log manager not initialized"}


def shutdown_global_logging():
    """关闭全局日志系统"""
    global _global_log_manager
    
    if _global_log_manager:
        _global_log_manager.shutdown()
        _global_log_manager = None
