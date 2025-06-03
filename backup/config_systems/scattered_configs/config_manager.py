"""
MarketPrism 可靠性配置管理系统

设计目标：
- 统一管理所有可靠性组件配置
- 支持环境变量配置
- 支持配置文件加载
- 配置验证和热重载
- 配置模板生成

配置层次：
1. 默认配置 (代码中定义)
2. 配置文件 (YAML/JSON)
3. 环境变量 (覆盖优先级最高)

配置结构：
reliability:
  global:
    enable_all: true
    log_level: "INFO"
  circuit_breaker:
    enabled: true
    failure_threshold: 5
    timeout_duration: 60.0
  rate_limiter:
    enabled: true
    requests_per_second: 100
    burst_size: 20
  retry_handler:
    enabled: true
    max_retries: 3
    base_delay: 1.0
  cold_storage:
    enabled: true
    backup_interval_hours: 24
  monitoring:
    health_check_interval: 30
    metrics_collection_interval: 60
    data_quality_checks: true
    anomaly_detection: true
"""

import os
import json
import yaml
import logging
from typing import Dict, Any, Optional, Union, List
from dataclasses import dataclass, field, asdict
from pathlib import Path
from datetime import datetime
import copy

# 导入配置类
from .reliability_manager import ReliabilityConfig
from .circuit_breaker import CircuitBreakerConfig
from .rate_limiter import RateLimitConfig  
from .retry_handler import RetryPolicy
from .redundancy_manager import ColdStorageConfig

logger = logging.getLogger(__name__)


@dataclass
class GlobalConfig:
    """全局配置"""
    enable_all: bool = True
    log_level: str = "INFO"
    environment: str = "development"  # development, staging, production
    project_name: str = "MarketPrism"
    version: str = "3.0.0"
    config_update_check_interval: int = 300  # 配置更新检查间隔(秒)


@dataclass
class MonitoringConfig:
    """监控配置"""
    health_check_interval: int = 30
    metrics_collection_interval: int = 60
    alert_cooldown: int = 300
    
    # 性能阈值
    max_error_rate: float = 0.05
    max_response_time_ms: float = 1000
    min_throughput_rps: float = 10
    
    # 数据质量阈值
    min_data_freshness_minutes: int = 5
    max_data_drift_percentage: float = 20
    min_data_completeness: float = 0.95
    
    # 监控功能开关
    enable_data_quality_monitoring: bool = True
    enable_anomaly_detection: bool = True
    enable_performance_profiling: bool = True
    enable_resource_monitoring: bool = True


@dataclass
class IntegrationConfig:
    """集成配置"""
    enable_prometheus_metrics: bool = True
    enable_grafana_dashboard: bool = True
    enable_slack_alerts: bool = False
    enable_email_alerts: bool = False
    enable_webhook_alerts: bool = False
    
    prometheus_port: int = 9090
    metrics_endpoint: str = "/metrics"
    
    # 告警通道配置
    slack_webhook_url: Optional[str] = None
    email_smtp_server: Optional[str] = None
    email_smtp_port: int = 587
    email_username: Optional[str] = None
    email_password: Optional[str] = None
    webhook_url: Optional[str] = None


@dataclass
class AdvancedConfig:
    """高级配置"""
    # 自适应调整
    enable_adaptive_thresholds: bool = True
    threshold_adjustment_factor: float = 0.1
    learning_window_hours: int = 24
    
    # 预测功能
    enable_predictive_alerts: bool = False
    prediction_horizon_minutes: int = 30
    
    # 容错配置
    graceful_degradation: bool = True
    backup_strategy: str = "local"  # local, remote, hybrid
    
    # 性能优化
    enable_performance_tuning: bool = True
    auto_scaling_enabled: bool = False
    resource_optimization: bool = True


@dataclass
class MarketPrismReliabilityConfig:
    """MarketPrism 完整可靠性配置"""
    global_config: GlobalConfig = field(default_factory=GlobalConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    integration: IntegrationConfig = field(default_factory=IntegrationConfig)
    advanced: AdvancedConfig = field(default_factory=AdvancedConfig)
    
    # 组件配置
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    rate_limiter: RateLimitConfig = field(default_factory=RateLimitConfig)
    retry_handler: RetryPolicy = field(default_factory=RetryPolicy)
    cold_storage: ColdStorageConfig = field(default_factory=ColdStorageConfig)
    
    # 运行时配置
    reliability: ReliabilityConfig = field(default_factory=ReliabilityConfig)


class ConfigManager:
    """配置管理器"""
    
    DEFAULT_CONFIG_PATHS = [
        "config/reliability.yaml",
        "config/reliability.yml", 
        "config/reliability.json",
        "./reliability.yaml",
        "./reliability.yml",
        "./reliability.json"
    ]
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.config: MarketPrismReliabilityConfig = MarketPrismReliabilityConfig()
        self.last_loaded = None
        self.watchers: List[callable] = []
        
        # 环境变量前缀
        self.env_prefix = "MARKETPRISM_RELIABILITY"
        
        logger.info("配置管理器已初始化")
    
    def load_config(self, config_path: Optional[str] = None) -> MarketPrismReliabilityConfig:
        """加载配置"""
        try:
            # 1. 从默认配置开始
            self.config = MarketPrismReliabilityConfig()
            
            # 2. 尝试加载配置文件
            config_file = self._find_config_file(config_path)
            if config_file:
                file_config = self._load_config_file(config_file)
                self._merge_config(file_config)
                logger.info(f"已加载配置文件: {config_file}")
            
            # 3. 应用环境变量覆盖
            self._apply_env_overrides()
            
            # 4. 验证配置
            self._validate_config()
            
            # 5. 同步到各组件配置
            self._sync_component_configs()
            
            self.last_loaded = datetime.now()
            logger.info("配置加载完成")
            
            # 通知观察者
            self._notify_watchers()
            
            return self.config
            
        except Exception as e:
            logger.error(f"配置加载失败: {e}")
            raise
    
    def _find_config_file(self, config_path: Optional[str] = None) -> Optional[str]:
        """查找配置文件"""
        paths_to_check = []
        
        if config_path:
            paths_to_check.append(config_path)
        
        if self.config_path:
            paths_to_check.append(self.config_path)
        
        paths_to_check.extend(self.DEFAULT_CONFIG_PATHS)
        
        for path in paths_to_check:
            if os.path.exists(path):
                return path
        
        logger.warning("未找到配置文件，使用默认配置")
        return None
    
    def _load_config_file(self, config_path: str) -> Dict[str, Any]:
        """从文件加载配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                if config_path.endswith(('.yaml', '.yml')):
                    return yaml.safe_load(f) or {}
                elif config_path.endswith('.json'):
                    return json.load(f) or {}
                else:
                    raise ValueError(f"不支持的配置文件格式: {config_path}")
        
        except Exception as e:
            logger.error(f"配置文件加载失败 {config_path}: {e}")
            raise
    
    def _merge_config(self, file_config: Dict[str, Any]):
        """合并配置"""
        try:
            # 深度合并配置
            if 'global' in file_config:
                self._update_dataclass(self.config.global_config, file_config['global'])
            
            if 'monitoring' in file_config:
                self._update_dataclass(self.config.monitoring, file_config['monitoring'])
            
            if 'integration' in file_config:
                self._update_dataclass(self.config.integration, file_config['integration'])
            
            if 'advanced' in file_config:
                self._update_dataclass(self.config.advanced, file_config['advanced'])
            
            if 'circuit_breaker' in file_config:
                self._update_dataclass(self.config.circuit_breaker, file_config['circuit_breaker'])
            
            if 'rate_limiter' in file_config:
                self._update_dataclass(self.config.rate_limiter, file_config['rate_limiter'])
            
            if 'retry_handler' in file_config:
                self._update_dataclass(self.config.retry_handler, file_config['retry_handler'])
            
            if 'cold_storage' in file_config:
                self._update_dataclass(self.config.cold_storage, file_config['cold_storage'])
            
        except Exception as e:
            logger.error(f"配置合并失败: {e}")
            raise
    
    def _update_dataclass(self, obj, updates: Dict[str, Any]):
        """更新数据类实例"""
        for key, value in updates.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
            else:
                logger.warning(f"未知配置项: {key}")
    
    def _apply_env_overrides(self):
        """应用环境变量覆盖"""
        try:
            # 全局配置环境变量
            self._apply_env_to_dataclass(
                self.config.global_config,
                f"{self.env_prefix}_GLOBAL"
            )
            
            # 监控配置环境变量
            self._apply_env_to_dataclass(
                self.config.monitoring,
                f"{self.env_prefix}_MONITORING"
            )
            
            # 集成配置环境变量
            self._apply_env_to_dataclass(
                self.config.integration,
                f"{self.env_prefix}_INTEGRATION"
            )
            
            # 组件配置环境变量
            self._apply_env_to_dataclass(
                self.config.circuit_breaker,
                f"{self.env_prefix}_CIRCUIT_BREAKER"
            )
            
            self._apply_env_to_dataclass(
                self.config.rate_limiter,
                f"{self.env_prefix}_RATE_LIMITER"
            )
            
            self._apply_env_to_dataclass(
                self.config.retry_handler,
                f"{self.env_prefix}_RETRY_HANDLER"
            )
            
            self._apply_env_to_dataclass(
                self.config.cold_storage,
                f"{self.env_prefix}_COLD_STORAGE"
            )
            
        except Exception as e:
            logger.error(f"环境变量应用失败: {e}")
    
    def _apply_env_to_dataclass(self, obj, prefix: str):
        """将环境变量应用到数据类"""
        for field_name in obj.__dataclass_fields__:
            env_key = f"{prefix}_{field_name.upper()}"
            env_value = os.getenv(env_key)
            
            if env_value is not None:
                field_type = obj.__dataclass_fields__[field_name].type
                
                try:
                    # 类型转换
                    if field_type == bool:
                        value = env_value.lower() in ('true', '1', 'yes', 'on')
                    elif field_type == int:
                        value = int(env_value)
                    elif field_type == float:
                        value = float(env_value)
                    else:
                        value = env_value
                    
                    setattr(obj, field_name, value)
                    logger.debug(f"环境变量覆盖: {env_key} = {value}")
                
                except (ValueError, TypeError) as e:
                    logger.warning(f"环境变量类型转换失败 {env_key}: {e}")
    
    def _validate_config(self):
        """验证配置"""
        try:
            # 验证基本配置
            assert 0 < self.config.monitoring.health_check_interval <= 3600, "健康检查间隔应在1-3600秒之间"
            assert 0 < self.config.monitoring.metrics_collection_interval <= 3600, "指标收集间隔应在1-3600秒之间"
            assert 0 <= self.config.monitoring.max_error_rate <= 1, "错误率阈值应在0-1之间"
            
            # 验证组件配置
            if self.config.circuit_breaker.failure_threshold <= 0:
                raise ValueError("熔断器失败阈值必须大于0")
            
            if self.config.rate_limiter.requests_per_second <= 0:
                raise ValueError("限流器请求速率必须大于0")
            
            if self.config.retry_handler.max_retries < 0:
                raise ValueError("重试次数不能为负数")
            
            logger.info("配置验证通过")
            
        except Exception as e:
            logger.error(f"配置验证失败: {e}")
            raise
    
    def _sync_component_configs(self):
        """同步组件配置到可靠性配置"""
        try:
            # 从监控配置同步到可靠性配置
            self.config.reliability.health_check_interval = self.config.monitoring.health_check_interval
            self.config.reliability.metrics_collection_interval = self.config.monitoring.metrics_collection_interval
            self.config.reliability.alert_cooldown = self.config.monitoring.alert_cooldown
            
            self.config.reliability.max_error_rate = self.config.monitoring.max_error_rate
            self.config.reliability.max_response_time_ms = self.config.monitoring.max_response_time_ms
            self.config.reliability.min_throughput_rps = self.config.monitoring.min_throughput_rps
            
            self.config.reliability.min_data_freshness_minutes = self.config.monitoring.min_data_freshness_minutes
            self.config.reliability.max_data_drift_percentage = self.config.monitoring.max_data_drift_percentage
            self.config.reliability.min_data_completeness = self.config.monitoring.min_data_completeness
            
            # 从全局配置同步组件启用状态
            if not self.config.global_config.enable_all:
                self.config.reliability.enable_circuit_breaker = False
                self.config.reliability.enable_rate_limiter = False
                self.config.reliability.enable_retry_handler = False
                self.config.reliability.enable_cold_storage_monitor = False
                self.config.reliability.enable_data_quality_monitor = False
                self.config.reliability.enable_anomaly_detector = False
            
            logger.debug("组件配置同步完成")
            
        except Exception as e:
            logger.error(f"组件配置同步失败: {e}")
    
    def save_config(self, config_path: Optional[str] = None, format: str = "yaml"):
        """保存配置到文件"""
        try:
            save_path = config_path or self.config_path or f"reliability_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}"
            
            # 转换为字典
            config_dict = self._config_to_dict()
            
            # 保存文件
            with open(save_path, 'w', encoding='utf-8') as f:
                if format.lower() in ('yaml', 'yml'):
                    yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True, indent=2)
                elif format.lower() == 'json':
                    json.dump(config_dict, f, indent=2, ensure_ascii=False)
                else:
                    raise ValueError(f"不支持的格式: {format}")
            
            logger.info(f"配置已保存到: {save_path}")
            
        except Exception as e:
            logger.error(f"配置保存失败: {e}")
            raise
    
    def _config_to_dict(self) -> Dict[str, Any]:
        """将配置转换为字典"""
        return {
            "global": asdict(self.config.global_config),
            "monitoring": asdict(self.config.monitoring),
            "integration": asdict(self.config.integration),
            "advanced": asdict(self.config.advanced),
            "circuit_breaker": asdict(self.config.circuit_breaker),
            "rate_limiter": asdict(self.config.rate_limiter),
            "retry_handler": asdict(self.config.retry_handler),
            "cold_storage": asdict(self.config.cold_storage)
        }
    
    def generate_template(self, template_path: str = "reliability_config_template.yaml"):
        """生成配置模板"""
        try:
            template = MarketPrismReliabilityConfig()
            template_dict = {
                "global": asdict(template.global_config),
                "monitoring": asdict(template.monitoring),
                "integration": asdict(template.integration),
                "advanced": asdict(template.advanced),
                "circuit_breaker": asdict(template.circuit_breaker),
                "rate_limiter": asdict(template.rate_limiter),
                "retry_handler": asdict(template.retry_handler),
                "cold_storage": asdict(template.cold_storage)
            }
            
            # 添加注释说明
            template_with_comments = self._add_config_comments(template_dict)
            
            with open(template_path, 'w', encoding='utf-8') as f:
                f.write(template_with_comments)
            
            logger.info(f"配置模板已生成: {template_path}")
            
        except Exception as e:
            logger.error(f"模板生成失败: {e}")
            raise
    
    def _add_config_comments(self, config_dict: Dict[str, Any]) -> str:
        """为配置添加注释说明"""
        comments = """# MarketPrism 可靠性系统配置文件
# 这是一个完整的配置模板，包含所有可配置选项和说明

# 全局配置
global:
  enable_all: true          # 是否启用所有组件
  log_level: "INFO"         # 日志级别: DEBUG, INFO, WARNING, ERROR
  environment: "development" # 环境: development, staging, production
  project_name: "MarketPrism"
  version: "3.0.0"
  config_update_check_interval: 300  # 配置更新检查间隔(秒)

# 监控配置
monitoring:
  health_check_interval: 30           # 健康检查间隔(秒)
  metrics_collection_interval: 60     # 指标收集间隔(秒)
  alert_cooldown: 300                 # 告警冷却时间(秒)
  
  # 性能阈值
  max_error_rate: 0.05               # 最大错误率 (5%)
  max_response_time_ms: 1000         # 最大响应时间 (毫秒)
  min_throughput_rps: 10             # 最小吞吐量 (RPS)
  
  # 数据质量阈值
  min_data_freshness_minutes: 5       # 数据新鲜度阈值 (分钟)
  max_data_drift_percentage: 20       # 数据漂移阈值 (%)
  min_data_completeness: 0.95         # 数据完整性阈值 (95%)
  
  # 监控功能开关
  enable_data_quality_monitoring: true
  enable_anomaly_detection: true
  enable_performance_profiling: true
  enable_resource_monitoring: true

# 集成配置
integration:
  enable_prometheus_metrics: true
  enable_grafana_dashboard: true
  enable_slack_alerts: false
  enable_email_alerts: false
  enable_webhook_alerts: false
  
  prometheus_port: 9090
  metrics_endpoint: "/metrics"
  
  # 告警通道配置 (需要时填写)
  slack_webhook_url: null
  email_smtp_server: null
  email_smtp_port: 587
  email_username: null
  email_password: null
  webhook_url: null

# 高级配置
advanced:
  # 自适应调整
  enable_adaptive_thresholds: true
  threshold_adjustment_factor: 0.1
  learning_window_hours: 24
  
  # 预测功能
  enable_predictive_alerts: false
  prediction_horizon_minutes: 30
  
  # 容错配置
  graceful_degradation: true
  backup_strategy: "local"  # local, remote, hybrid
  
  # 性能优化
  enable_performance_tuning: true
  auto_scaling_enabled: false
  resource_optimization: true

# 熔断器配置
circuit_breaker:
  failure_threshold: 5        # 失败阈值
  timeout_duration: 60.0      # 超时时间(秒)
  recovery_timeout: 30.0      # 恢复超时(秒)
  enable_metrics: true
  slow_call_duration: 5.0

# 限流器配置
rate_limiter:
  requests_per_second: 100    # 每秒请求数
  burst_size: 20              # 突发大小
  enable_adaptive: true       # 启用自适应
  window_size: 60
  enable_metrics: true

# 重试处理器配置
retry_handler:
  max_retries: 3              # 最大重试次数
  base_delay: 1.0             # 基础延迟(秒)
  max_delay: 30.0             # 最大延迟(秒)
  backoff_factor: 2.0         # 退避因子
  enable_jitter: true

# 冷存储配置
cold_storage:
  host: "localhost"
  port: 9000
  database: "marketprism_cold"
  backup_enabled: true
  migration_enabled: true
  query_optimization: true
  compression_enabled: true
  data_retention_days: 365

# 环境变量支持:
# 所有配置项都可以通过环境变量覆盖
# 格式: MARKETPRISM_RELIABILITY_<SECTION>_<KEY>
# 例如: MARKETPRISM_RELIABILITY_GLOBAL_ENABLE_ALL=true
#       MARKETPRISM_RELIABILITY_MONITORING_MAX_ERROR_RATE=0.1
"""
        return comments
    
    def watch_config_changes(self, callback: callable):
        """监听配置变化"""
        self.watchers.append(callback)
    
    def _notify_watchers(self):
        """通知观察者配置已更新"""
        for watcher in self.watchers:
            try:
                watcher(self.config)
            except Exception as e:
                logger.error(f"配置变化通知失败: {e}")
    
    def get_config(self) -> MarketPrismReliabilityConfig:
        """获取当前配置"""
        return self.config
    
    def reload_config(self):
        """重新加载配置"""
        logger.info("重新加载配置...")
        return self.load_config(self.config_path)
    
    def get_config_summary(self) -> Dict[str, Any]:
        """获取配置摘要"""
        return {
            "last_loaded": self.last_loaded.isoformat() if self.last_loaded else None,
            "config_path": self.config_path,
            "environment": self.config.global_config.environment,
            "enabled_components": {
                "circuit_breaker": self.config.reliability.enable_circuit_breaker,
                "rate_limiter": self.config.reliability.enable_rate_limiter,
                "retry_handler": self.config.reliability.enable_retry_handler,
                "cold_storage_monitor": self.config.reliability.enable_cold_storage_monitor,
                "data_quality_monitor": self.config.reliability.enable_data_quality_monitor,
                "anomaly_detector": self.config.reliability.enable_anomaly_detector
            },
            "monitoring_intervals": {
                "health_check": self.config.monitoring.health_check_interval,
                "metrics_collection": self.config.monitoring.metrics_collection_interval
            },
            "thresholds": {
                "max_error_rate": self.config.monitoring.max_error_rate,
                "max_response_time_ms": self.config.monitoring.max_response_time_ms,
                "min_throughput_rps": self.config.monitoring.min_throughput_rps
            }
        }


# 全局配置管理器实例
config_manager = None


def get_config_manager() -> Optional[ConfigManager]:
    """获取全局配置管理器实例"""
    return config_manager


def initialize_config_manager(config_path: Optional[str] = None) -> ConfigManager:
    """初始化全局配置管理器"""
    global config_manager
    config_manager = ConfigManager(config_path)
    return config_manager 