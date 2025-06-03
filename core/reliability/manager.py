"""
MarketPrism 统一可靠性管理器

设计目标：
- 集成所有可靠性组件
- 统一配置管理
- 组件间协调机制
- 实时监控和告警

组件集成：
1. 熔断器系统 - 服务保护
2. 智能限流器 - 频率控制  
3. 指数退避重试 - 失败恢复
4. 冷存储监控 - 数据管理
5. 数据质量监控 - 新增
6. 异常检测系统 - 新增

架构设计：
┌─────────────────────────────────────────────────────┐
│                可靠性管理器                          │
├─────────────────┬───────────────┬───────────────────┤
│   服务保护层     │   数据管理层   │   监控告警层      │
│ ┌─────────────┐ │ ┌───────────┐ │ ┌──────────────┐ │
│ │ 熔断器      │ │ │ 冷存储    │ │ │ 质量监控     │ │
│ │ 限流器      │ │ │ 监控      │ │ │ 异常检测     │ │
│ │ 重试系统    │ │ │           │ │ │ 性能分析     │ │
│ └─────────────┘ │ └───────────┘ │ └──────────────┘ │
└─────────────────┴───────────────┴───────────────────┘
"""

import asyncio
import time
import logging
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import statistics

# 导入现有组件
from .circuit_breaker import MarketPrismCircuitBreaker
from .rate_limiter import AdaptiveRateLimiter, RateLimitConfig
from .retry_handler import ExponentialBackoffRetry, RetryPolicy
from .redundancy_manager import ColdStorageMonitor, ColdStorageConfig

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """健康状态"""
    HEALTHY = "healthy"
    WARNING = "warning"  
    CRITICAL = "critical"
    FAILED = "failed"


class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ReliabilityConfig:
    """统一可靠性配置 - 合并了UnifiedReliabilityConfig的功能"""
    # 组件启用配置
    enable_circuit_breaker: bool = True
    enable_rate_limiter: bool = True
    enable_retry_handler: bool = True
    enable_cold_storage_monitor: bool = True
    enable_data_quality_monitor: bool = True
    enable_anomaly_detector: bool = True
    
    # 监控配置
    health_check_interval: int = 30  # 健康检查间隔(秒)
    metrics_collection_interval: int = 60  # 指标收集间隔(秒)
    alert_cooldown: int = 300  # 告警冷却时间(秒)
    
    # 性能阈值
    max_error_rate: float = 0.05  # 最大错误率 5%
    max_response_time_ms: float = 1000  # 最大响应时间 1s
    min_throughput_rps: float = 10  # 最小吞吐量 10 RPS
    
    # 数据质量阈值
    min_data_freshness_minutes: int = 5  # 数据新鲜度阈值
    max_data_drift_percentage: float = 20  # 数据漂移阈值 20%
    min_data_completeness: float = 0.95  # 数据完整性阈值 95%


@dataclass
class DataQualityMetrics:
    """数据质量指标"""
    freshness_score: float = 0.0  # 数据新鲜度分数 (0-1)
    completeness_score: float = 0.0  # 数据完整性分数 (0-1)
    accuracy_score: float = 0.0  # 数据准确性分数 (0-1)
    consistency_score: float = 0.0  # 数据一致性分数 (0-1)
    drift_score: float = 0.0  # 数据漂移分数 (0-1, 越低越好)
    overall_score: float = 0.0  # 综合质量分数 (0-1)
    last_updated: float = 0.0


@dataclass
class AnomalyAlert:
    """异常告警"""
    alert_id: str
    level: AlertLevel
    component: str
    message: str
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolved_at: Optional[float] = None


@dataclass
class SystemMetrics:
    """系统指标"""
    # 性能指标
    avg_response_time_ms: float = 0.0
    error_rate: float = 0.0
    throughput_rps: float = 0.0
    
    # 资源指标
    cpu_usage_percent: float = 0.0
    memory_usage_percent: float = 0.0
    disk_usage_percent: float = 0.0
    
    # 业务指标
    active_connections: int = 0
    processed_messages: int = 0
    failed_operations: int = 0
    
    last_updated: float = 0.0


class ReliabilityManager:
    """统一可靠性管理器 - 合并了ReliabilityManager和UnifiedReliabilityManager的功能"""
    
    def __init__(self, config: Optional[ReliabilityConfig] = None):
        self.config = config or ReliabilityConfig()
        
        # 组件实例 - 兼容两种接口
        self.components = {}  # UnifiedReliabilityManager风格
        self.circuit_breaker: Optional[MarketPrismCircuitBreaker] = None
        self.rate_limiter: Optional[AdaptiveRateLimiter] = None
        self.retry_handler: Optional[ExponentialBackoffRetry] = None
        self.cold_storage_monitor: Optional[ColdStorageMonitor] = None
        
        # 监控数据
        self.system_metrics = SystemMetrics()
        self.data_quality_metrics = DataQualityMetrics()
        self.active_alerts: List[AnomalyAlert] = []
        self.alert_history: List[AnomalyAlert] = []
        
        # 运行时状态
        self.is_running = False
        self.background_tasks: List[asyncio.Task] = []
        self.start_time = time.time()
        self.last_health_check = 0.0
        
        # 性能监控数据
        self.response_times: List[float] = []
        self.error_counts: List[int] = []
        self.throughput_samples: List[float] = []
        
        logger.info("统一可靠性管理器已初始化")
    
    async def start(self):
        """启动可靠性管理器"""
        if self.is_running:
            return
        
        self.is_running = True
        
        # 初始化组件
        await self._initialize_components()
        
        # 启动后台任务
        self.background_tasks = [
            asyncio.create_task(self._health_monitor_loop()),
            asyncio.create_task(self._metrics_collector_loop()),
            asyncio.create_task(self._data_quality_monitor_loop()),
            asyncio.create_task(self._anomaly_detector_loop())
        ]
        
        logger.info("统一可靠性管理器已启动")
    
    async def stop(self):
        """停止可靠性管理器"""
        self.is_running = False
        
        # 停止后台任务
        for task in self.background_tasks:
            task.cancel()
        
        await asyncio.gather(*self.background_tasks, return_exceptions=True)
        
        # 停止组件
        await self._stop_components()
        
        logger.info("统一可靠性管理器已停止")
    
    async def _initialize_components(self):
        """初始化可靠性组件"""
        try:
            # 初始化熔断器
            if self.config.enable_circuit_breaker:
                self.circuit_breaker = MarketPrismCircuitBreaker(
                    failure_threshold=5,
                    timeout_duration=60.0,
                    recovery_timeout=30.0
                )
                await self.circuit_breaker.start()
                self.components['circuit_breaker'] = self.circuit_breaker
                logger.info("熔断器已启动")
            
            # 初始化限流器
            if self.config.enable_rate_limiter:
                rate_config = RateLimitConfig(
                    max_requests_per_second=100,
                    burst_allowance=20,
                    adaptive_factor_max=2.0
                )
                self.rate_limiter = AdaptiveRateLimiter("main_limiter", rate_config)
                await self.rate_limiter.start()
                self.components['rate_limiter'] = self.rate_limiter
                logger.info("限流器已启动")
            
            # 初始化重试处理器
            if self.config.enable_retry_handler:
                retry_config = RetryPolicy(
                    max_attempts=3,
                    base_delay=1.0,
                    max_delay=30.0,
                    multiplier=2.0
                )
                self.retry_handler = ExponentialBackoffRetry("main_retry", retry_config)
                self.components['retry_handler'] = self.retry_handler
                logger.info("重试处理器已初始化")
            
            # 初始化冷存储监控
            if self.config.enable_cold_storage_monitor:
                cold_config = ColdStorageConfig()
                self.cold_storage_monitor = ColdStorageMonitor(cold_config)
                await self.cold_storage_monitor.start()
                self.components['cold_storage_monitor'] = self.cold_storage_monitor
                logger.info("冷存储监控已启动")
            
        except Exception as e:
            logger.error(f"组件初始化失败: {e}")
            raise
    
    async def _stop_components(self):
        """停止所有组件"""
        components = [
            (self.circuit_breaker, "熔断器"),
            (self.rate_limiter, "限流器"),
            (self.cold_storage_monitor, "冷存储监控")
        ]
        
        for component, name in components:
            if component:
                try:
                    await component.stop()
                    logger.info(f"{name}已停止")
                except Exception as e:
                    logger.error(f"停止{name}失败: {e}")
    
    async def _health_monitor_loop(self):
        """健康监控循环"""
        while self.is_running:
            try:
                await self._perform_health_check()
                await asyncio.sleep(self.config.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康监控异常: {e}")
                await asyncio.sleep(30)
    
    async def _perform_health_check(self):
        """执行健康检查"""
        self.last_health_check = time.time()
        
        try:
            # 检查各组件状态
            component_status = {}
            
            if self.circuit_breaker:
                status = self.circuit_breaker.get_status()
                component_status["circuit_breaker"] = {
                    "healthy": status["state"] != "OPEN",
                    "details": status
                }
            
            if self.rate_limiter:
                status = self.rate_limiter.get_status()
                component_status["rate_limiter"] = {
                    "healthy": status["is_running"],
                    "details": status
                }
            
            if self.cold_storage_monitor:
                status = self.cold_storage_monitor.get_status()
                component_status["cold_storage"] = {
                    "healthy": status["is_running"],
                    "details": status
                }
            
            # 检查系统指标是否正常
            await self._check_system_thresholds(component_status)
            
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
    
    async def _check_system_thresholds(self, component_status: Dict):
        """检查系统阈值"""
        # 检查错误率
        if self.system_metrics.error_rate > self.config.max_error_rate:
            await self._create_alert(
                AlertLevel.WARNING,
                "system",
                f"错误率过高: {self.system_metrics.error_rate:.2%} > {self.config.max_error_rate:.2%}"
            )
        
        # 检查响应时间
        if self.system_metrics.avg_response_time_ms > self.config.max_response_time_ms:
            await self._create_alert(
                AlertLevel.WARNING,
                "system",
                f"响应时间过长: {self.system_metrics.avg_response_time_ms:.1f}ms > {self.config.max_response_time_ms:.1f}ms"
            )
        
        # 检查吞吐量
        if self.system_metrics.throughput_rps < self.config.min_throughput_rps:
            await self._create_alert(
                AlertLevel.WARNING,
                "system",
                f"吞吐量过低: {self.system_metrics.throughput_rps:.1f} RPS < {self.config.min_throughput_rps:.1f} RPS"
            )
    
    async def _metrics_collector_loop(self):
        """指标收集循环"""
        while self.is_running:
            try:
                await self._collect_metrics()
                await asyncio.sleep(self.config.metrics_collection_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"指标收集异常: {e}")
                await asyncio.sleep(60)
    
    async def _collect_metrics(self):
        """收集系统指标"""
        try:
            # 计算性能指标
            if self.response_times:
                self.system_metrics.avg_response_time_ms = statistics.mean(self.response_times[-100:])
            
            if self.error_counts:
                total_requests = sum(self.error_counts[-10:]) + len(self.response_times[-100:])
                if total_requests > 0:
                    self.system_metrics.error_rate = sum(self.error_counts[-10:]) / total_requests
            
            if self.throughput_samples:
                self.system_metrics.throughput_rps = statistics.mean(self.throughput_samples[-10:])
            
            # 模拟资源使用率（实际应该从系统获取）
            try:
                import psutil
                self.system_metrics.cpu_usage_percent = psutil.cpu_percent()
                self.system_metrics.memory_usage_percent = psutil.virtual_memory().percent
                self.system_metrics.disk_usage_percent = psutil.disk_usage('/').percent
            except ImportError:
                # 如果没有psutil，使用模拟数据
                import random
                self.system_metrics.cpu_usage_percent = random.uniform(10, 80)
                self.system_metrics.memory_usage_percent = random.uniform(20, 70)
                self.system_metrics.disk_usage_percent = random.uniform(10, 50)
            
            self.system_metrics.last_updated = time.time()
            
        except Exception as e:
            logger.error(f"指标收集失败: {e}")
    
    async def _data_quality_monitor_loop(self):
        """数据质量监控循环"""
        if not self.config.enable_data_quality_monitor:
            return
            
        while self.is_running:
            try:
                await self._monitor_data_quality()
                await asyncio.sleep(self.config.metrics_collection_interval * 2)  # 2倍间隔
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"数据质量监控异常: {e}")
                await asyncio.sleep(120)
    
    async def _monitor_data_quality(self):
        """监控数据质量"""
        try:
            # 检查数据新鲜度
            freshness_score = await self._calculate_data_freshness()
            
            # 检查数据完整性
            completeness_score = await self._calculate_data_completeness()
            
            # 检查数据准确性
            accuracy_score = await self._calculate_data_accuracy()
            
            # 检查数据一致性
            consistency_score = await self._calculate_data_consistency()
            
            # 检查数据漂移
            drift_score = await self._calculate_data_drift()
            
            # 计算综合分数
            overall_score = (freshness_score + completeness_score + 
                           accuracy_score + consistency_score + (1 - drift_score)) / 5
            
            # 更新指标
            self.data_quality_metrics = DataQualityMetrics(
                freshness_score=freshness_score,
                completeness_score=completeness_score,
                accuracy_score=accuracy_score,
                consistency_score=consistency_score,
                drift_score=drift_score,
                overall_score=overall_score,
                last_updated=time.time()
            )
            
            # 检查质量阈值
            await self._check_data_quality_thresholds()
            
        except Exception as e:
            logger.error(f"数据质量监控失败: {e}")
    
    async def _calculate_data_freshness(self) -> float:
        """计算数据新鲜度分数"""
        # 模拟：检查最新数据的时间戳
        current_time = time.time()
        latest_data_time = current_time - 60  # 模拟最新数据是1分钟前
        
        freshness_minutes = (current_time - latest_data_time) / 60
        
        if freshness_minutes <= self.config.min_data_freshness_minutes:
            return 1.0
        else:
            # 线性衰减
            decay_factor = max(0, 1 - (freshness_minutes - self.config.min_data_freshness_minutes) / 30)
            return decay_factor
    
    async def _calculate_data_completeness(self) -> float:
        """计算数据完整性分数"""
        # 模拟：检查必需字段的完整性
        missing_rate = 0.02  # 模拟2%的缺失率
        return max(0, 1 - missing_rate)
    
    async def _calculate_data_accuracy(self) -> float:
        """计算数据准确性分数"""
        # 模拟：检查数据格式、范围等
        return 0.95  # 模拟95%准确性
    
    async def _calculate_data_consistency(self) -> float:
        """计算数据一致性分数"""
        # 模拟：检查不同数据源间的一致性
        return 0.98  # 模拟98%一致性
    
    async def _calculate_data_drift(self) -> float:
        """计算数据漂移分数"""
        # 模拟：检查数据分布的变化
        import random
        return random.uniform(0.05, 0.15)  # 模拟5-15%的漂移
    
    async def _check_data_quality_thresholds(self):
        """检查数据质量阈值"""
        metrics = self.data_quality_metrics
        
        if metrics.completeness_score < self.config.min_data_completeness:
            await self._create_alert(
                AlertLevel.WARNING,
                "data_quality",
                f"数据完整性不足: {metrics.completeness_score:.2%} < {self.config.min_data_completeness:.2%}"
            )
        
        if metrics.drift_score > self.config.max_data_drift_percentage / 100:
            await self._create_alert(
                AlertLevel.WARNING,
                "data_quality",
                f"数据漂移过大: {metrics.drift_score:.2%} > {self.config.max_data_drift_percentage:.2%}"
            )
        
        if metrics.overall_score < 0.8:  # 综合分数低于80%
            await self._create_alert(
                AlertLevel.ERROR,
                "data_quality",
                f"数据质量综合分数过低: {metrics.overall_score:.2%}"
            )
    
    async def _anomaly_detector_loop(self):
        """异常检测循环"""
        if not self.config.enable_anomaly_detector:
            return
            
        while self.is_running:
            try:
                await self._detect_anomalies()
                await asyncio.sleep(self.config.metrics_collection_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"异常检测异常: {e}")
                await asyncio.sleep(60)
    
    async def _detect_anomalies(self):
        """检测系统异常"""
        try:
            # 检测响应时间异常
            if len(self.response_times) >= 10:
                recent_avg = statistics.mean(self.response_times[-10:])
                historical_avg = statistics.mean(self.response_times[-100:]) if len(self.response_times) >= 100 else recent_avg
                
                if recent_avg > historical_avg * 2:  # 响应时间翻倍
                    await self._create_alert(
                        AlertLevel.WARNING,
                        "anomaly",
                        f"响应时间异常增长: 当前{recent_avg:.1f}ms vs 历史{historical_avg:.1f}ms"
                    )
            
            # 检测吞吐量异常
            if len(self.throughput_samples) >= 10:
                recent_throughput = statistics.mean(self.throughput_samples[-10:])
                historical_throughput = statistics.mean(self.throughput_samples[-100:]) if len(self.throughput_samples) >= 100 else recent_throughput
                
                if recent_throughput < historical_throughput * 0.5:  # 吞吐量下降一半
                    await self._create_alert(
                        AlertLevel.ERROR,
                        "anomaly",
                        f"吞吐量异常下降: 当前{recent_throughput:.1f} RPS vs 历史{historical_throughput:.1f} RPS"
                    )
            
            # 检测错误率异常
            if len(self.error_counts) >= 5:
                recent_errors = sum(self.error_counts[-5:])
                if recent_errors > 10:  # 最近5个周期错误超过10次
                    await self._create_alert(
                        AlertLevel.ERROR,
                        "anomaly",
                        f"错误率异常升高: 最近5个周期内{recent_errors}次错误"
                    )
            
        except Exception as e:
            logger.error(f"异常检测失败: {e}")
    
    async def _create_alert(self, level: AlertLevel, component: str, message: str, metadata: Dict[str, Any] = None):
        """创建告警"""
        import uuid
        alert_id = f"{component}_{int(time.time())}_{hash(message) % 10000}"
        
        # 检查是否在冷却期内
        recent_alerts = [
            alert for alert in self.active_alerts
            if alert.component == component and alert.level == level
            and time.time() - alert.timestamp < self.config.alert_cooldown
        ]
        
        if recent_alerts:
            logger.debug(f"告警在冷却期内，跳过: {message}")
            return
        
        alert = AnomalyAlert(
            alert_id=alert_id,
            level=level,
            component=component,
            message=message,
            timestamp=time.time(),
            metadata=metadata or {}
        )
        
        self.active_alerts.append(alert)
        self.alert_history.append(alert)
        
        logger.warning(f"[{level.value.upper()}] {component}: {message}")
    
    async def resolve_alert(self, alert_id: str):
        """解决告警"""
        for alert in self.active_alerts:
            if alert.alert_id == alert_id:
                alert.resolved = True
                alert.resolved_at = time.time()
                self.active_alerts.remove(alert)
                logger.info(f"告警已解决: {alert_id}")
                break
    
    def record_request(self, response_time_ms: float, is_error: bool = False):
        """记录请求性能"""
        self.response_times.append(response_time_ms)
        if len(self.response_times) > 1000:
            self.response_times = self.response_times[-500:]  # 保留最近500个
        
        if is_error:
            self.error_counts.append(1)
        else:
            self.error_counts.append(0)
        
        if len(self.error_counts) > 100:
            self.error_counts = self.error_counts[-50:]  # 保留最近50个
    
    def record_throughput(self, rps: float):
        """记录吞吐量"""
        self.throughput_samples.append(rps)
        if len(self.throughput_samples) > 100:
            self.throughput_samples = self.throughput_samples[-50:]  # 保留最近50个
    
    def get_comprehensive_status(self) -> Dict[str, Any]:
        """获取综合状态 - 兼容两种接口"""
        uptime = time.time() - self.start_time
        
        return {
            "is_running": self.is_running,
            "uptime_hours": uptime / 3600,
            "last_health_check": datetime.fromtimestamp(self.last_health_check).isoformat() if self.last_health_check else None,
            
            "components": {
                "circuit_breaker": {
                    "enabled": self.config.enable_circuit_breaker,
                    "status": self.circuit_breaker.get_status() if self.circuit_breaker else None
                },
                "rate_limiter": {
                    "enabled": self.config.enable_rate_limiter,
                    "status": self.rate_limiter.get_status() if self.rate_limiter else None
                },
                "retry_handler": {
                    "enabled": self.config.enable_retry_handler,
                    "available": self.retry_handler is not None
                },
                "cold_storage_monitor": {
                    "enabled": self.config.enable_cold_storage_monitor,
                    "status": self.cold_storage_monitor.get_status() if self.cold_storage_monitor else None
                }
            },
            
            "system_metrics": {
                "avg_response_time_ms": self.system_metrics.avg_response_time_ms,
                "error_rate": self.system_metrics.error_rate,
                "throughput_rps": self.system_metrics.throughput_rps,
                "cpu_usage_percent": self.system_metrics.cpu_usage_percent,
                "memory_usage_percent": self.system_metrics.memory_usage_percent,
                "disk_usage_percent": self.system_metrics.disk_usage_percent,
                "last_updated": datetime.fromtimestamp(self.system_metrics.last_updated).isoformat() if self.system_metrics.last_updated else None
            },
            
            "data_quality": {
                "freshness_score": self.data_quality_metrics.freshness_score,
                "completeness_score": self.data_quality_metrics.completeness_score,
                "accuracy_score": self.data_quality_metrics.accuracy_score,
                "consistency_score": self.data_quality_metrics.consistency_score,
                "drift_score": self.data_quality_metrics.drift_score,
                "overall_score": self.data_quality_metrics.overall_score,
                "last_updated": datetime.fromtimestamp(self.data_quality_metrics.last_updated).isoformat() if self.data_quality_metrics.last_updated else None
            },
            
            "alerts": {
                "active_count": len(self.active_alerts),
                "total_count": len(self.alert_history),
                "active_alerts": [
                    {
                        "alert_id": alert.alert_id,
                        "level": alert.level.value,
                        "component": alert.component,
                        "message": alert.message,
                        "timestamp": datetime.fromtimestamp(alert.timestamp).isoformat()
                    }
                    for alert in self.active_alerts
                ],
                "recent_alerts": [
                    {
                        "alert_id": alert.alert_id,
                        "level": alert.level.value,
                        "component": alert.component,
                        "message": alert.message,
                        "timestamp": datetime.fromtimestamp(alert.timestamp).isoformat(),
                        "resolved": alert.resolved
                    }
                    for alert in sorted(self.alert_history, key=lambda x: x.timestamp, reverse=True)[:10]
                ]
            }
        }


# 全局管理器实例
reliability_manager = None


def get_reliability_manager() -> Optional[ReliabilityManager]:
    """获取全局可靠性管理器实例"""
    return reliability_manager


def initialize_reliability_manager(config: Optional[ReliabilityConfig] = None):
    """初始化全局可靠性管理器"""
    global reliability_manager
    reliability_manager = ReliabilityManager(config)
    return reliability_manager


# 向后兼容性别名
UnifiedReliabilityManager = ReliabilityManager
UnifiedReliabilityConfig = ReliabilityConfig