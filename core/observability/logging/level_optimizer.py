"""
MarketPrism日志级别优化器

提供智能的日志级别管理，根据环境、性能要求和业务重要性自动调整日志级别。
"""

import os
import time
from typing import Dict, Any, Optional, Set, Callable
from enum import Enum
from dataclasses import dataclass
from .unified_logger import LogLevel, ComponentType, OperationType


class Environment(Enum):
    """环境类型"""
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class BusinessCriticality(Enum):
    """业务重要性级别"""
    CRITICAL = "critical"      # 核心业务逻辑，必须记录
    IMPORTANT = "important"    # 重要业务事件，通常记录
    NORMAL = "normal"         # 一般业务操作，选择性记录
    VERBOSE = "verbose"       # 详细调试信息，很少记录


@dataclass
class LogLevelRule:
    """日志级别规则"""
    component: ComponentType
    operation: OperationType
    environment: Environment
    criticality: BusinessCriticality
    recommended_level: LogLevel
    max_frequency: Optional[float] = None  # 最大频率（次/秒）
    condition: Optional[Callable] = None   # 额外条件


class LogLevelOptimizer:
    """日志级别优化器"""
    
    def __init__(self):
        self.current_environment = self._detect_environment()
        self.performance_mode = os.getenv("MARKETPRISM_PERFORMANCE_MODE", "false").lower() == "true"
        self.rules = self._initialize_rules()
        self._performance_stats = {
            "log_calls": 0,
            "suppressed_logs": 0,
            "start_time": time.time()
        }
    
    def _detect_environment(self) -> Environment:
        """自动检测运行环境"""
        env_name = os.getenv("MARKETPRISM_ENV", "development").lower()
        
        env_mapping = {
            "dev": Environment.DEVELOPMENT,
            "development": Environment.DEVELOPMENT,
            "test": Environment.TESTING,
            "testing": Environment.TESTING,
            "stage": Environment.STAGING,
            "staging": Environment.STAGING,
            "prod": Environment.PRODUCTION,
            "production": Environment.PRODUCTION
        }
        
        return env_mapping.get(env_name, Environment.DEVELOPMENT)
    
    def _initialize_rules(self) -> Dict[str, LogLevelRule]:
        """初始化日志级别规则"""
        rules = {}
        
        # 生产环境规则
        if self.current_environment == Environment.PRODUCTION:
            rules.update(self._get_production_rules())
        
        # 开发环境规则
        elif self.current_environment == Environment.DEVELOPMENT:
            rules.update(self._get_development_rules())
        
        # 测试环境规则
        elif self.current_environment == Environment.TESTING:
            rules.update(self._get_testing_rules())
        
        # 预发布环境规则
        elif self.current_environment == Environment.STAGING:
            rules.update(self._get_staging_rules())
        
        return rules
    
    def _get_production_rules(self) -> Dict[str, LogLevelRule]:
        """生产环境日志规则"""
        return {
            # 启动/停止 - 必须记录
            "startup_critical": LogLevelRule(
                ComponentType.MAIN, OperationType.STARTUP,
                Environment.PRODUCTION, BusinessCriticality.CRITICAL,
                LogLevel.INFO
            ),
            
            # 连接事件 - 重要
            "connection_important": LogLevelRule(
                ComponentType.WEBSOCKET, OperationType.CONNECTION,
                Environment.PRODUCTION, BusinessCriticality.IMPORTANT,
                LogLevel.INFO, max_frequency=0.1  # 每10秒最多1次
            ),
            
            # 数据处理 - 仅错误
            "data_processing_normal": LogLevelRule(
                ComponentType.ORDERBOOK_MANAGER, OperationType.DATA_PROCESSING,
                Environment.PRODUCTION, BusinessCriticality.NORMAL,
                LogLevel.WARNING  # 生产环境只记录警告和错误
            ),
            
            # 性能监控 - 降低频率
            "performance_normal": LogLevelRule(
                ComponentType.MEMORY_MANAGER, OperationType.PERFORMANCE,
                Environment.PRODUCTION, BusinessCriticality.NORMAL,
                LogLevel.INFO, max_frequency=0.017  # 每分钟最多1次
            ),
            
            # 健康检查 - 仅异常
            "health_check_normal": LogLevelRule(
                ComponentType.HEALTH_CHECK, OperationType.HEALTH_CHECK,
                Environment.PRODUCTION, BusinessCriticality.NORMAL,
                LogLevel.WARNING  # 只记录不健康状态
            ),
            
            # 错误处理 - 全部记录
            "error_critical": LogLevelRule(
                ComponentType.ERROR_HANDLER, OperationType.ERROR_HANDLING,
                Environment.PRODUCTION, BusinessCriticality.CRITICAL,
                LogLevel.ERROR
            )
        }
    
    def _get_development_rules(self) -> Dict[str, LogLevelRule]:
        """开发环境日志规则"""
        return {
            # 开发环境允许更多详细日志
            "startup_verbose": LogLevelRule(
                ComponentType.MAIN, OperationType.STARTUP,
                Environment.DEVELOPMENT, BusinessCriticality.VERBOSE,
                LogLevel.DEBUG
            ),
            
            "connection_verbose": LogLevelRule(
                ComponentType.WEBSOCKET, OperationType.CONNECTION,
                Environment.DEVELOPMENT, BusinessCriticality.VERBOSE,
                LogLevel.DEBUG
            ),
            
            "data_processing_verbose": LogLevelRule(
                ComponentType.ORDERBOOK_MANAGER, OperationType.DATA_PROCESSING,
                Environment.DEVELOPMENT, BusinessCriticality.VERBOSE,
                LogLevel.DEBUG, max_frequency=1.0  # 每秒最多1次
            ),
            
            "performance_important": LogLevelRule(
                ComponentType.MEMORY_MANAGER, OperationType.PERFORMANCE,
                Environment.DEVELOPMENT, BusinessCriticality.IMPORTANT,
                LogLevel.INFO, max_frequency=0.1  # 每10秒最多1次
            )
        }
    
    def _get_testing_rules(self) -> Dict[str, LogLevelRule]:
        """测试环境日志规则"""
        return {
            # 测试环境需要详细的错误信息，但限制正常操作日志
            "error_critical": LogLevelRule(
                ComponentType.ERROR_HANDLER, OperationType.ERROR_HANDLING,
                Environment.TESTING, BusinessCriticality.CRITICAL,
                LogLevel.DEBUG  # 测试时需要详细错误信息
            ),
            
            "startup_important": LogLevelRule(
                ComponentType.MAIN, OperationType.STARTUP,
                Environment.TESTING, BusinessCriticality.IMPORTANT,
                LogLevel.INFO
            ),
            
            "data_processing_normal": LogLevelRule(
                ComponentType.ORDERBOOK_MANAGER, OperationType.DATA_PROCESSING,
                Environment.TESTING, BusinessCriticality.NORMAL,
                LogLevel.WARNING  # 测试时减少数据处理日志
            )
        }
    
    def _get_staging_rules(self) -> Dict[str, LogLevelRule]:
        """预发布环境日志规则"""
        return {
            # 预发布环境介于开发和生产之间
            "startup_important": LogLevelRule(
                ComponentType.MAIN, OperationType.STARTUP,
                Environment.STAGING, BusinessCriticality.IMPORTANT,
                LogLevel.INFO
            ),
            
            "connection_important": LogLevelRule(
                ComponentType.WEBSOCKET, OperationType.CONNECTION,
                Environment.STAGING, BusinessCriticality.IMPORTANT,
                LogLevel.INFO, max_frequency=0.2  # 每5秒最多1次
            ),
            
            "data_processing_normal": LogLevelRule(
                ComponentType.ORDERBOOK_MANAGER, OperationType.DATA_PROCESSING,
                Environment.STAGING, BusinessCriticality.NORMAL,
                LogLevel.INFO, max_frequency=0.1  # 每10秒最多1次
            ),
            
            "error_critical": LogLevelRule(
                ComponentType.ERROR_HANDLER, OperationType.ERROR_HANDLING,
                Environment.STAGING, BusinessCriticality.CRITICAL,
                LogLevel.ERROR
            )
        }
    
    def should_log(self, 
                   component: ComponentType,
                   operation: OperationType,
                   intended_level: LogLevel,
                   criticality: BusinessCriticality = BusinessCriticality.NORMAL) -> tuple[bool, LogLevel]:
        """判断是否应该记录日志以及推荐的日志级别
        
        Returns:
            (should_log, recommended_level)
        """
        self._performance_stats["log_calls"] += 1
        
        # 查找匹配的规则
        rule_key = f"{operation.value}_{criticality.value}"
        rule = self.rules.get(rule_key)
        
        if not rule:
            # 没有特定规则，使用默认逻辑
            return self._apply_default_logic(intended_level, criticality)
        
        # 应用规则
        if rule.condition and not rule.condition():
            self._performance_stats["suppressed_logs"] += 1
            return False, rule.recommended_level
        
        # 检查频率限制
        if rule.max_frequency:
            # 这里应该集成频率控制器，简化示例
            pass
        
        # 比较级别
        if intended_level.value in ["ERROR", "CRITICAL"]:
            # 错误和严重错误总是记录
            return True, intended_level
        
        if rule.recommended_level.value == "WARNING" and intended_level.value in ["DEBUG", "INFO"]:
            # 规则要求WARNING级别，但请求的是更低级别
            self._performance_stats["suppressed_logs"] += 1
            return False, rule.recommended_level
        
        return True, rule.recommended_level
    
    def _apply_default_logic(self, intended_level: LogLevel, criticality: BusinessCriticality) -> tuple[bool, LogLevel]:
        """应用默认日志逻辑"""
        
        # 性能模式下更严格
        if self.performance_mode:
            if intended_level.value == "DEBUG":
                return False, LogLevel.INFO
            if intended_level.value == "INFO" and criticality == BusinessCriticality.VERBOSE:
                return False, LogLevel.WARNING
        
        # 生产环境默认逻辑
        if self.current_environment == Environment.PRODUCTION:
            if intended_level.value == "DEBUG":
                return False, LogLevel.INFO
            if intended_level.value == "INFO" and criticality == BusinessCriticality.VERBOSE:
                return False, LogLevel.WARNING
        
        return True, intended_level
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        runtime = time.time() - self._performance_stats["start_time"]
        total_calls = self._performance_stats["log_calls"]
        suppressed = self._performance_stats["suppressed_logs"]
        
        return {
            "total_log_calls": total_calls,
            "suppressed_logs": suppressed,
            "suppression_rate": suppressed / max(total_calls, 1),
            "runtime_seconds": runtime,
            "calls_per_second": total_calls / max(runtime, 1),
            "current_environment": self.current_environment.value,
            "performance_mode": self.performance_mode
        }
    
    def update_rules(self, new_rules: Dict[str, LogLevelRule]):
        """动态更新日志规则"""
        self.rules.update(new_rules)
    
    def optimize_for_performance(self, enable: bool = True):
        """启用/禁用性能优化模式"""
        self.performance_mode = enable
        
        if enable:
            # 性能模式下的额外规则
            performance_rules = {
                "perf_data_processing": LogLevelRule(
                    ComponentType.ORDERBOOK_MANAGER, OperationType.DATA_PROCESSING,
                    self.current_environment, BusinessCriticality.VERBOSE,
                    LogLevel.WARNING, max_frequency=0.1
                ),
                
                "perf_health_check": LogLevelRule(
                    ComponentType.HEALTH_CHECK, OperationType.HEALTH_CHECK,
                    self.current_environment, BusinessCriticality.NORMAL,
                    LogLevel.ERROR  # 性能模式下只记录错误
                )
            }
            self.update_rules(performance_rules)


# 全局优化器实例
log_level_optimizer = LogLevelOptimizer()


def optimized_log_level(component: ComponentType, 
                       operation: OperationType,
                       intended_level: LogLevel,
                       criticality: BusinessCriticality = BusinessCriticality.NORMAL):
    """日志级别优化装饰器"""
    def decorator(log_func):
        def wrapper(*args, **kwargs):
            should_log, recommended_level = log_level_optimizer.should_log(
                component, operation, intended_level, criticality
            )
            
            if not should_log:
                return
            
            # 如果推荐级别不同，调整日志级别
            if recommended_level != intended_level:
                # 这里可以调整实际的日志记录级别
                pass
            
            return log_func(*args, **kwargs)
        
        return wrapper
    return decorator


class AdaptiveLogLevel:
    """自适应日志级别管理器"""
    
    def __init__(self, window_size: int = 300):  # 5分钟窗口
        self.window_size = window_size
        self._error_counts = {}
        self._log_volumes = {}
        self._last_adjustment = time.time()
    
    def record_error(self, component: str):
        """记录错误事件"""
        current_time = time.time()
        if component not in self._error_counts:
            self._error_counts[component] = []
        
        self._error_counts[component].append(current_time)
        self._cleanup_old_records(component)
    
    def record_log_volume(self, component: str, count: int):
        """记录日志量"""
        current_time = time.time()
        if component not in self._log_volumes:
            self._log_volumes[component] = []
        
        self._log_volumes[component].append((current_time, count))
        self._cleanup_old_volumes(component)
    
    def _cleanup_old_records(self, component: str):
        """清理过期记录"""
        cutoff_time = time.time() - self.window_size
        if component in self._error_counts:
            self._error_counts[component] = [
                t for t in self._error_counts[component] if t > cutoff_time
            ]
    
    def _cleanup_old_volumes(self, component: str):
        """清理过期日志量记录"""
        cutoff_time = time.time() - self.window_size
        if component in self._log_volumes:
            self._log_volumes[component] = [
                (t, c) for t, c in self._log_volumes[component] if t > cutoff_time
            ]
    
    def should_increase_verbosity(self, component: str) -> bool:
        """判断是否应该增加详细程度"""
        if component not in self._error_counts:
            return False
        
        error_count = len(self._error_counts[component])
        # 如果5分钟内错误超过10次，增加详细程度
        return error_count > 10
    
    def should_decrease_verbosity(self, component: str) -> bool:
        """判断是否应该减少详细程度"""
        if component not in self._log_volumes:
            return False
        
        total_volume = sum(count for _, count in self._log_volumes[component])
        # 如果5分钟内日志量超过1000条，减少详细程度
        return total_volume > 1000


# 全局自适应管理器
adaptive_log_manager = AdaptiveLogLevel()
