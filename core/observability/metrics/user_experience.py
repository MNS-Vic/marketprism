"""
MarketPrism 用户体验监控

监控API响应时间、错误率等用户体验相关指标
"""

import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict, deque
from dataclasses import dataclass, field
import structlog

try:
    from prometheus_client import Counter, Histogram, Gauge, Summary
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


logger = structlog.get_logger(__name__)


@dataclass
class APIEndpointMetrics:
    """API端点指标"""
    endpoint: str
    method: str
    total_requests: int = 0
    error_count: int = 0
    total_response_time: float = 0.0
    min_response_time: float = float('inf')
    max_response_time: float = 0.0
    last_request_time: Optional[datetime] = None
    status_codes: Dict[int, int] = field(default_factory=lambda: defaultdict(int))
    
    def add_request(self, response_time_ms: float, status_code: int) -> None:
        """添加请求记录"""
        self.total_requests += 1
        self.total_response_time += response_time_ms
        self.min_response_time = min(self.min_response_time, response_time_ms)
        self.max_response_time = max(self.max_response_time, response_time_ms)
        self.last_request_time = datetime.now(timezone.utc)
        self.status_codes[status_code] += 1
        
        if status_code >= 400:
            self.error_count += 1
    
    def get_avg_response_time(self) -> float:
        """获取平均响应时间"""
        return self.total_response_time / self.total_requests if self.total_requests > 0 else 0.0
    
    def get_error_rate(self) -> float:
        """获取错误率"""
        return self.error_count / self.total_requests if self.total_requests > 0 else 0.0
    
    def get_success_rate(self) -> float:
        """获取成功率"""
        return 1.0 - self.get_error_rate()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'endpoint': self.endpoint,
            'method': self.method,
            'total_requests': self.total_requests,
            'error_count': self.error_count,
            'error_rate': self.get_error_rate(),
            'success_rate': self.get_success_rate(),
            'avg_response_time_ms': self.get_avg_response_time(),
            'min_response_time_ms': self.min_response_time if self.min_response_time != float('inf') else 0,
            'max_response_time_ms': self.max_response_time,
            'last_request_time': self.last_request_time.isoformat() if self.last_request_time else None,
            'status_codes': dict(self.status_codes)
        }


@dataclass
class SLAMetrics:
    """SLA指标"""
    name: str
    target_availability: float  # 目标可用性 (0-1)
    target_response_time_ms: float  # 目标响应时间
    target_error_rate: float  # 目标错误率
    
    # 实际指标
    actual_availability: float = 1.0
    actual_response_time_ms: float = 0.0
    actual_error_rate: float = 0.0
    
    # 时间窗口
    measurement_window_hours: int = 24
    
    def is_sla_met(self) -> bool:
        """检查SLA是否达标"""
        return (
            self.actual_availability >= self.target_availability and
            self.actual_response_time_ms <= self.target_response_time_ms and
            self.actual_error_rate <= self.target_error_rate
        )
    
    def get_sla_score(self) -> float:
        """获取SLA评分 (0-1)"""
        availability_score = min(self.actual_availability / self.target_availability, 1.0)
        
        response_time_score = min(self.target_response_time_ms / max(self.actual_response_time_ms, 1), 1.0)
        
        error_rate_score = 1.0 - min(self.actual_error_rate / max(self.target_error_rate, 0.001), 1.0)
        
        return (availability_score + response_time_score + error_rate_score) / 3
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'name': self.name,
            'target_availability': self.target_availability,
            'target_response_time_ms': self.target_response_time_ms,
            'target_error_rate': self.target_error_rate,
            'actual_availability': self.actual_availability,
            'actual_response_time_ms': self.actual_response_time_ms,
            'actual_error_rate': self.actual_error_rate,
            'sla_met': self.is_sla_met(),
            'sla_score': self.get_sla_score(),
            'measurement_window_hours': self.measurement_window_hours
        }


class UserExperienceMonitor:
    """用户体验监控器"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        
        # 指标存储
        self.endpoint_metrics: Dict[str, APIEndpointMetrics] = {}
        self.sla_metrics: Dict[str, SLAMetrics] = {}
        
        # 时间窗口数据
        self.response_time_windows: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.availability_windows: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1440))  # 24小时
        
        # Prometheus指标
        if PROMETHEUS_AVAILABLE:
            self._init_prometheus_metrics()
        
        # 初始化SLA定义
        self._init_sla_definitions()
        
        logger.info("用户体验监控器初始化完成")
    
    def _init_prometheus_metrics(self):
        """初始化Prometheus指标"""
        # API响应时间
        self.api_response_time = Histogram(
            'marketprism_api_response_time_seconds',
            'API response time',
            ['method', 'endpoint', 'status'],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
        )
        
        # API请求总数
        self.api_requests_total = Counter(
            'marketprism_ux_api_requests_total',
            'Total UX API requests',
            ['method', 'endpoint', 'status']
        )
        
        # SLA指标
        self.sla_availability = Gauge(
            'marketprism_sla_availability',
            'SLA availability',
            ['service']
        )
        
        self.sla_response_time = Gauge(
            'marketprism_sla_response_time_seconds',
            'SLA response time',
            ['service']
        )
        
        self.sla_error_rate = Gauge(
            'marketprism_sla_error_rate',
            'SLA error rate',
            ['service']
        )
        
        self.sla_score = Gauge(
            'marketprism_sla_score',
            'SLA score (0-1)',
            ['service']
        )
        
        # 用户体验评分
        self.user_experience_score = Gauge(
            'marketprism_user_experience_score',
            'Overall user experience score (0-1)',
            ['component']
        )
    
    def _init_sla_definitions(self):
        """初始化SLA定义"""
        sla_definitions = self.config.get('sla_definitions', {
            'api_gateway': {
                'target_availability': 0.999,  # 99.9%
                'target_response_time_ms': 500,
                'target_error_rate': 0.01  # 1%
            },
            'data_collector': {
                'target_availability': 0.995,  # 99.5%
                'target_response_time_ms': 1000,
                'target_error_rate': 0.02  # 2%
            },
            'market_data': {
                'target_availability': 0.99,  # 99%
                'target_response_time_ms': 100,  # 数据延迟
                'target_error_rate': 0.005  # 0.5%
            }
        })
        
        for service_name, sla_config in sla_definitions.items():
            self.sla_metrics[service_name] = SLAMetrics(
                name=service_name,
                **sla_config
            )
    
    def record_api_request(self, method: str, endpoint: str, status_code: int, 
                          response_time_ms: float) -> None:
        """记录API请求"""
        # 生成端点键
        endpoint_key = f"{method}:{endpoint}"
        
        # 初始化端点指标
        if endpoint_key not in self.endpoint_metrics:
            self.endpoint_metrics[endpoint_key] = APIEndpointMetrics(
                endpoint=endpoint,
                method=method
            )
        
        # 记录请求
        self.endpoint_metrics[endpoint_key].add_request(response_time_ms, status_code)
        
        # 更新Prometheus指标
        if PROMETHEUS_AVAILABLE:
            status = str(status_code)
            self.api_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status=status
            ).inc()
            
            self.api_response_time.labels(
                method=method,
                endpoint=endpoint,
                status=status
            ).observe(response_time_ms / 1000)
        
        # 记录到时间窗口
        self.response_time_windows[endpoint_key].append({
            'timestamp': datetime.now(timezone.utc),
            'response_time_ms': response_time_ms,
            'status_code': status_code
        })
        
        # 更新SLA指标
        self._update_sla_metrics()
    
    def record_service_availability(self, service_name: str, is_available: bool) -> None:
        """记录服务可用性"""
        self.availability_windows[service_name].append({
            'timestamp': datetime.now(timezone.utc),
            'available': is_available
        })
        
        # 更新SLA指标
        self._update_sla_metrics()
    
    def _update_sla_metrics(self) -> None:
        """更新SLA指标"""
        current_time = datetime.now(timezone.utc)
        
        for service_name, sla in self.sla_metrics.items():
            # 计算时间窗口
            window_start = current_time - timedelta(hours=sla.measurement_window_hours)
            
            # 计算可用性
            availability_data = self.availability_windows.get(service_name, [])
            recent_availability = [
                d for d in availability_data 
                if d['timestamp'] > window_start
            ]
            
            if recent_availability:
                available_count = sum(1 for d in recent_availability if d['available'])
                sla.actual_availability = available_count / len(recent_availability)
            
            # 计算响应时间和错误率（基于API指标）
            total_response_time = 0.0
            total_requests = 0
            error_count = 0
            
            for endpoint_key, metrics in self.endpoint_metrics.items():
                if metrics.last_request_time and metrics.last_request_time > window_start:
                    # 获取时间窗口内的数据
                    window_data = self.response_time_windows.get(endpoint_key, [])
                    recent_data = [
                        d for d in window_data 
                        if d['timestamp'] > window_start
                    ]
                    
                    for data in recent_data:
                        total_response_time += data['response_time_ms']
                        total_requests += 1
                        if data['status_code'] >= 400:
                            error_count += 1
            
            if total_requests > 0:
                sla.actual_response_time_ms = total_response_time / total_requests
                sla.actual_error_rate = error_count / total_requests
            
            # 更新Prometheus指标
            if PROMETHEUS_AVAILABLE:
                self.sla_availability.labels(service=service_name).set(sla.actual_availability)
                self.sla_response_time.labels(service=service_name).set(sla.actual_response_time_ms / 1000)
                self.sla_error_rate.labels(service=service_name).set(sla.actual_error_rate)
                self.sla_score.labels(service=service_name).set(sla.get_sla_score())
    
    def get_endpoint_metrics(self, endpoint: str = None) -> Dict[str, Any]:
        """获取端点指标"""
        if endpoint:
            matching_metrics = {
                k: v for k, v in self.endpoint_metrics.items() 
                if endpoint in k
            }
        else:
            matching_metrics = self.endpoint_metrics
        
        return {
            key: metrics.to_dict() 
            for key, metrics in matching_metrics.items()
        }
    
    def get_sla_status(self) -> Dict[str, Any]:
        """获取SLA状态"""
        return {
            service_name: sla.to_dict()
            for service_name, sla in self.sla_metrics.items()
        }
    
    def get_user_experience_score(self) -> float:
        """获取用户体验评分"""
        if not self.sla_metrics:
            return 0.0
        
        # 计算所有SLA的平均评分
        total_score = sum(sla.get_sla_score() for sla in self.sla_metrics.values())
        avg_score = total_score / len(self.sla_metrics)
        
        # 更新Prometheus指标
        if PROMETHEUS_AVAILABLE:
            self.user_experience_score.labels(component="overall").set(avg_score)
        
        return avg_score
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """获取性能摘要"""
        # 计算整体指标
        total_requests = sum(m.total_requests for m in self.endpoint_metrics.values())
        total_errors = sum(m.error_count for m in self.endpoint_metrics.values())
        
        if total_requests > 0:
            overall_error_rate = total_errors / total_requests
            avg_response_time = sum(
                m.get_avg_response_time() * m.total_requests 
                for m in self.endpoint_metrics.values()
            ) / total_requests
        else:
            overall_error_rate = 0.0
            avg_response_time = 0.0
        
        # 找出最慢的端点
        slowest_endpoints = sorted(
            self.endpoint_metrics.values(),
            key=lambda m: m.get_avg_response_time(),
            reverse=True
        )[:5]
        
        # 找出错误率最高的端点
        highest_error_endpoints = sorted(
            self.endpoint_metrics.values(),
            key=lambda m: m.get_error_rate(),
            reverse=True
        )[:5]
        
        return {
            'overall_metrics': {
                'total_requests': total_requests,
                'overall_error_rate': overall_error_rate,
                'avg_response_time_ms': avg_response_time,
                'user_experience_score': self.get_user_experience_score()
            },
            'sla_status': self.get_sla_status(),
            'slowest_endpoints': [ep.to_dict() for ep in slowest_endpoints],
            'highest_error_endpoints': [ep.to_dict() for ep in highest_error_endpoints]
        }


# 全局用户体验监控器实例
_global_ux_monitor: Optional[UserExperienceMonitor] = None


def get_ux_monitor() -> UserExperienceMonitor:
    """获取全局用户体验监控器"""
    global _global_ux_monitor
    if _global_ux_monitor is None:
        _global_ux_monitor = UserExperienceMonitor()
    return _global_ux_monitor
