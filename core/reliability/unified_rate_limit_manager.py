"""
MarketPrism 统一速率限制管理器

整合了通用自适应限流和交易所专用精确限流的最佳特性：
- 基于真实交易所API文档的精确限流
- 自适应阈值调整和智能排队
- 优先级队列和突发处理
- 完整的监控和告警集成

设计目标：
- 统一所有限流需求到单一实现
- 保持企业级可靠性和性能
- 提供简单易用的API接口
- 支持分布式和本地部署
"""

import asyncio
import logging
import time
import heapq
from typing import Dict, Any, Optional, List, Callable, Union, Tuple
from datetime import datetime, timedelta, timezone
from functools import wraps
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import threading
import json

# Core模块导入
try:
    from ..monitoring import get_global_monitoring
    from ..errors import get_global_error_handler, MarketPrismError, ErrorSeverity, ErrorCategory
    CORE_AVAILABLE = True
except ImportError:
    CORE_AVAILABLE = False
    logging.warning("Core监控和错误处理模块不可用，使用降级实现")


class ExchangeType(Enum):
    """交易所类型"""
    BINANCE = "binance"
    OKX = "okx"
    DERIBIT = "deribit"
    BYBIT = "bybit"


class RequestType(Enum):
    """请求类型"""
    # 市场数据类
    MARKET_DATA = "market_data"
    ORDERBOOK_SNAPSHOT = "orderbook_snapshot"
    TRADE_HISTORY = "trade_history"
    KLINE_DATA = "kline_data"
    TICKER_DATA = "ticker_data"
    
    # 账户类
    ACCOUNT_INFO = "account_info"
    ORDER_HISTORY = "order_history"
    
    # 特殊数据类
    TOP_TRADER_DATA = "top_trader_data"
    FUNDING_RATE = "funding_rate"
    OPEN_INTEREST = "open_interest"
    
    # 系统类
    SYSTEM_STATUS = "system_status"
    EXCHANGE_INFO = "exchange_info"
    
    # 通用类
    DEFAULT = "default"
    OTHER = "other"


class RequestPriority(Enum):
    """请求优先级"""
    CRITICAL = 1    # 关键操作 (健康检查、告警)
    HIGH = 2        # 高优先级 (交易数据)
    MEDIUM = 3      # 中等优先级 (普通数据)
    LOW = 4         # 低优先级 (历史数据)
    BACKGROUND = 5  # 后台任务


@dataclass
class EndpointConfig:
    """端点配置"""
    path: str
    weight: int = 1
    requests_per_minute: Optional[int] = None
    requests_per_second: Optional[int] = None
    data_source: str = "缓存"  # 撮合引擎、缓存、数据库
    
    # 特殊限制
    auth_required: bool = False
    account_based: bool = False  # 是否基于账户限制
    
    # 优化建议
    recommended_interval: float = 1.0  # 建议请求间隔（秒）
    max_batch_size: Optional[int] = None


@dataclass
class RateLimitConfig:
    """统一限流配置"""
    # 基础限制
    max_requests_per_second: int = 50
    max_requests_per_minute: int = 1200
    
    # 权重系统（如Binance）
    weight_based: bool = False
    max_weight_per_minute: Optional[int] = None
    weight_reset_interval: int = 60
    
    # 自适应参数
    adaptive_enabled: bool = True
    adaptive_factor_min: float = 0.5
    adaptive_factor_max: float = 2.0
    adaptive_threshold_high: float = 0.8
    adaptive_threshold_low: float = 0.5
    
    # 队列参数
    queue_enabled: bool = True
    queue_max_size: int = 1000
    queue_timeout: float = 30.0
    
    # 突发处理
    burst_allowance: int = 10
    burst_window: float = 1.0
    
    # 安全配置
    ip_ban_threshold_429: int = 100
    ip_ban_threshold_418: int = 200
    ban_duration_minutes: Tuple[int, int] = (2, 4320)
    
    # 端点配置
    endpoints: Dict[str, EndpointConfig] = field(default_factory=dict)
    
    # 监控响应头
    weight_header_pattern: Optional[str] = None
    order_count_header_pattern: Optional[str] = None
    retry_after_header: str = "Retry-After"


@dataclass
class RequestRecord:
    """请求记录"""
    timestamp: float = field(default_factory=time.time)
    priority: RequestPriority = RequestPriority.MEDIUM
    operation_type: str = ""
    endpoint: Optional[str] = None
    weight: int = 1
    success: bool = True
    response_time: float = 0.0


@dataclass
class QueuedRequest:
    """排队请求"""
    priority: RequestPriority
    timestamp: float
    operation_type: str
    endpoint: Optional[str]
    weight: int
    future: asyncio.Future
    timeout_handle: Optional[asyncio.Handle] = None
    
    def __lt__(self, other):
        # 优先级队列比较 (优先级数值越小，优先级越高)
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        return self.timestamp < other.timestamp


class RateLimitViolation(Exception):
    """限流违规异常"""
    def __init__(self, message: str, wait_time: float = 0, exchange: str = None, endpoint: str = None):
        super().__init__(message)
        self.wait_time = wait_time
        self.exchange = exchange
        self.endpoint = endpoint


class RequestTracker:
    """请求跟踪器 - 优化版本"""
    
    def __init__(self, window_size: int = 60):
        self.window_size = window_size
        self.requests = deque()
        self.weights = deque()
        self.lock = threading.RLock()
    
    def add_request(self, weight: int = 1):
        """添加请求记录"""
        current_time = time.time()
        with self.lock:
            self.requests.append(current_time)
            self.weights.append(weight)
            self._cleanup_old_requests(current_time)
    
    def get_current_rate(self) -> Tuple[int, int]:
        """获取当前请求率 (请求数, 总权重)"""
        current_time = time.time()
        with self.lock:
            self._cleanup_old_requests(current_time)
            return len(self.requests), sum(self.weights)
    
    def _cleanup_old_requests(self, current_time: float):
        """清理过期请求"""
        cutoff_time = current_time - self.window_size
        while self.requests and self.requests[0] < cutoff_time:
            self.requests.popleft()
            self.weights.popleft()


class UnifiedRateLimitManager:
    """统一速率限制管理器"""
    
    def __init__(self, name: str, config: Optional[RateLimitConfig] = None):
        self.name = name
        self.config = config or RateLimitConfig()
        self.logger = logging.getLogger(f"{__name__}.{name}")
        
        # 请求跟踪器
        self.minute_tracker = RequestTracker(60)
        self.second_tracker = RequestTracker(1)
        self.weight_tracker = RequestTracker(self.config.weight_reset_interval) if self.config.weight_based else None
        
        # 端点特定跟踪器
        self.endpoint_trackers: Dict[str, RequestTracker] = {}
        
        # 自适应状态
        self.adaptive_factor = 1.0
        self.current_load = 0.0
        self.last_adjustment_time = time.time()
        
        # 请求历史记录（用于自适应调整）
        self.request_history: deque = deque(maxlen=10000)
        
        # 等待队列 (优先级队列)
        self.waiting_queue: List[QueuedRequest] = []
        self.queue_size = 0
        self.queue_processing = False
        
        # 安全状态
        self.consecutive_failures = 0
        self.last_429_time: Optional[float] = None
        self.last_418_time: Optional[float] = None
        self.emergency_backoff_until: Optional[float] = None
        
        # 响应头监控
        self.last_weight_header: Optional[int] = None
        self.last_order_count_header: Optional[int] = None
        
        # 统计指标
        self.total_requests = 0
        self.total_allowed = 0
        self.total_queued = 0
        self.total_rejected = 0
        
        # 锁
        self.lock = threading.RLock()
        
        # 监控集成
        self.monitoring = get_global_monitoring() if CORE_AVAILABLE else None
        self.error_handler = get_global_error_handler() if CORE_AVAILABLE else None
        
        self.logger.info(f"统一限流器 '{name}' 已初始化")
    
    async def acquire_permit(self,
                           request_type: Union[str, RequestType] = RequestType.DEFAULT,
                           endpoint: Optional[str] = None,
                           priority: RequestPriority = RequestPriority.MEDIUM,
                           account_based: bool = False,
                           timeout: Optional[float] = None) -> Dict[str, Any]:
        """获取操作许可 - 统一接口"""
        
        self.total_requests += 1
        current_time = time.time()
        
        # 标准化请求类型
        if isinstance(request_type, str):
            try:
                request_type = RequestType(request_type.lower())
            except ValueError:
                request_type = RequestType.OTHER
        
        # 检查紧急退避
        if self.emergency_backoff_until and current_time < self.emergency_backoff_until:
            wait_time = self.emergency_backoff_until - current_time
            return {
                'granted': False,
                'reason': 'Emergency backoff active',
                'wait_time': wait_time,
                'retry_after': wait_time
            }
        
        # 获取端点配置和权重
        endpoint_config = self.config.endpoints.get(endpoint) if endpoint else None
        request_weight = endpoint_config.weight if endpoint_config else 1
        
        with self.lock:
            # 清理过期记录
            self._cleanup_old_records(current_time)
            
            # 执行所有限制检查
            check_result = await self._perform_all_checks(
                request_type, endpoint, endpoint_config, request_weight, 
                priority, account_based, current_time
            )
            
            if not check_result['allowed']:
                # 如果启用队列，尝试排队
                if self.config.queue_enabled:
                    return await self._enqueue_request(
                        request_type, endpoint, request_weight, priority, timeout
                    )
                else:
                    self.total_rejected += 1
                    return {
                        'granted': False,
                        'reason': check_result['reason'],
                        'wait_time': check_result['wait_time'],
                        'retry_after': check_result['wait_time']
                    }
            
            # 所有检查通过，授予许可
            await self._grant_permit(request_type, endpoint, request_weight, priority, current_time)
            
            return {
                'granted': True,
                'manager': self.name,
                'request_type': request_type.value,
                'weight': request_weight,
                'endpoint': endpoint,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
    
    async def _perform_all_checks(self, request_type, endpoint, endpoint_config, 
                                request_weight, priority, account_based, current_time) -> Dict[str, Any]:
        """执行所有限制检查"""
        
        # 1. 基础速率检查
        rate_check = self._check_basic_rate_limits(request_weight)
        if not rate_check['allowed']:
            return rate_check
        
        # 2. 权重检查（如果适用）
        if self.config.weight_based and self.weight_tracker:
            weight_check = self._check_weight_limits(request_weight)
            if not weight_check['allowed']:
                return weight_check
        
        # 3. 端点特定检查
        if endpoint_config:
            endpoint_check = self._check_endpoint_limits(endpoint, endpoint_config)
            if not endpoint_check['allowed']:
                return endpoint_check
        
        # 4. 突发检查
        burst_check = self._check_burst_limits()
        if not burst_check['allowed']:
            return burst_check
        
        # 5. 自适应检查
        if self.config.adaptive_enabled:
            adaptive_check = self._check_adaptive_limits(request_weight)
            if not adaptive_check['allowed']:
                return adaptive_check
        
        return {'allowed': True}
    
    def _check_basic_rate_limits(self, weight: int) -> Dict[str, Any]:
        """检查基础速率限制"""
        # 按分钟检查
        current_requests_min, current_weight_min = self.minute_tracker.get_current_rate()
        if current_requests_min >= self.config.max_requests_per_minute:
            return {
                'allowed': False,
                'reason': f'Minute limit exceeded: {current_requests_min}/{self.config.max_requests_per_minute}',
                'wait_time': 60.0
            }
        
        # 按秒检查
        current_requests_sec, current_weight_sec = self.second_tracker.get_current_rate()
        if current_requests_sec >= self.config.max_requests_per_second:
            return {
                'allowed': False,
                'reason': f'Second limit exceeded: {current_requests_sec}/{self.config.max_requests_per_second}',
                'wait_time': 1.0
            }
        
        return {'allowed': True}
    
    def _check_weight_limits(self, weight: int) -> Dict[str, Any]:
        """检查权重限制"""
        if not self.weight_tracker or not self.config.max_weight_per_minute:
            return {'allowed': True}
        
        _, current_weight = self.weight_tracker.get_current_rate()
        
        if current_weight + weight > self.config.max_weight_per_minute:
            return {
                'allowed': False,
                'reason': f'Weight limit exceeded: {current_weight + weight}/{self.config.max_weight_per_minute}',
                'wait_time': float(self.config.weight_reset_interval)
            }
        
        return {'allowed': True}
    
    def _check_endpoint_limits(self, endpoint: str, config: EndpointConfig) -> Dict[str, Any]:
        """检查端点特定限制"""
        if endpoint not in self.endpoint_trackers:
            self.endpoint_trackers[endpoint] = RequestTracker(60)
        
        tracker = self.endpoint_trackers[endpoint]
        current_requests, _ = tracker.get_current_rate()
        
        if config.requests_per_minute and current_requests >= config.requests_per_minute:
            return {
                'allowed': False,
                'reason': f'Endpoint limit exceeded: {endpoint} {current_requests}/{config.requests_per_minute}',
                'wait_time': 60.0
            }
        
        return {'allowed': True}
    
    def _check_burst_limits(self) -> Dict[str, Any]:
        """检查突发限制"""
        current_time = time.time()
        burst_window_start = current_time - self.config.burst_window
        
        recent_burst = [
            record for record in self.request_history
            if record.timestamp >= burst_window_start
        ]
        
        if len(recent_burst) >= self.config.burst_allowance:
            return {
                'allowed': False,
                'reason': f'Burst limit exceeded: {len(recent_burst)}/{self.config.burst_allowance}',
                'wait_time': self.config.burst_window
            }
        
        return {'allowed': True}
    
    def _check_adaptive_limits(self, weight: int) -> Dict[str, Any]:
        """检查自适应限制"""
        # 计算当前负载
        current_rps = self._calculate_current_rps()
        max_rps = self.config.max_requests_per_second
        load_ratio = current_rps / max_rps if max_rps > 0 else 0
        
        # 自适应调整
        self._adjust_adaptive_factor(load_ratio)
        
        # 计算有效限制
        effective_limit = max_rps * self.adaptive_factor
        
        if current_rps >= effective_limit:
            return {
                'allowed': False,
                'reason': f'Adaptive limit exceeded: {current_rps:.2f}/{effective_limit:.2f} (factor: {self.adaptive_factor:.2f})',
                'wait_time': 1.0
            }
        
        return {'allowed': True}
    
    def _calculate_current_rps(self) -> float:
        """计算当前请求速率"""
        current_time = time.time()
        window_start = current_time - 60  # 1分钟窗口
        
        recent_requests = [
            record for record in self.request_history
            if record.timestamp >= window_start
        ]
        
        if not recent_requests:
            return 0.0
        
        return len(recent_requests) / 60.0
    
    def _adjust_adaptive_factor(self, load_ratio: float):
        """自适应调整限流因子"""
        # 高负载时收紧限流
        if load_ratio >= self.config.adaptive_threshold_high:
            self.adaptive_factor = max(
                self.adaptive_factor * 0.9,
                self.config.adaptive_factor_min
            )
        
        # 低负载时放宽限流
        elif load_ratio <= self.config.adaptive_threshold_low:
            self.adaptive_factor = min(
                self.adaptive_factor * 1.1,
                self.config.adaptive_factor_max
            )
        
        self.current_load = load_ratio
        self.last_adjustment_time = time.time()
    
    async def _grant_permit(self, request_type, endpoint, weight, priority, timestamp):
        """授予许可"""
        # 记录到跟踪器
        self.minute_tracker.add_request(weight)
        self.second_tracker.add_request(weight)
        
        if self.weight_tracker:
            self.weight_tracker.add_request(weight)
        
        if endpoint and endpoint in self.endpoint_trackers:
            self.endpoint_trackers[endpoint].add_request(weight)
        
        # 记录到历史
        record = RequestRecord(
            timestamp=timestamp,
            priority=priority,
            operation_type=request_type.value,
            endpoint=endpoint,
            weight=weight,
            success=True
        )
        self.request_history.append(record)
        
        self.total_allowed += 1
        
        # 监控指标
        if self.monitoring:
            self.monitoring.collect_metric(
                "rate_limit_permits_granted",
                1,
                labels={
                    "manager": self.name,
                    "request_type": request_type.value,
                    "priority": priority.name
                }
            )
    
    async def _enqueue_request(self, request_type, endpoint, weight, priority, timeout):
        """将请求加入等待队列"""
        # 检查队列容量
        if self.queue_size >= self.config.queue_max_size:
            self.total_rejected += 1
            return {
                'granted': False,
                'reason': f'Queue full: {self.queue_size}/{self.config.queue_max_size}',
                'wait_time': 0
            }
        
        # 创建排队请求
        future = asyncio.Future()
        request_timeout = timeout or self.config.queue_timeout
        
        queued_request = QueuedRequest(
            priority=priority,
            timestamp=time.time(),
            operation_type=request_type.value,
            endpoint=endpoint,
            weight=weight,
            future=future
        )
        
        # 设置超时处理
        def timeout_callback():
            if not future.done():
                future.set_result({
                    'granted': False,
                    'reason': 'Queue timeout',
                    'wait_time': 0
                })
                self._remove_from_queue(queued_request)
        
        queued_request.timeout_handle = asyncio.get_event_loop().call_later(
            request_timeout, timeout_callback
        )
        
        # 加入优先级队列
        with self.lock:
            heapq.heappush(self.waiting_queue, queued_request)
            self.queue_size += 1
            self.total_queued += 1
        
        # 启动队列处理
        if not self.queue_processing:
            asyncio.create_task(self._process_queue())
        
        # 等待处理结果
        return await future
    
    async def _process_queue(self):
        """处理等待队列"""
        self.queue_processing = True
        
        try:
            while self.waiting_queue and self.queue_size > 0:
                # 检查是否有可用许可
                current_time = time.time()
                
                # 简化检查：只检查基础限制
                current_requests_sec, _ = self.second_tracker.get_current_rate()
                if current_requests_sec >= self.config.max_requests_per_second:
                    await asyncio.sleep(0.1)
                    continue
                
                # 获取最高优先级请求
                try:
                    with self.lock:
                        queued_request = heapq.heappop(self.waiting_queue)
                        self.queue_size -= 1
                except IndexError:
                    break
                
                # 检查请求是否仍然有效
                if queued_request.future.done():
                    continue
                
                # 取消超时处理
                if queued_request.timeout_handle:
                    queued_request.timeout_handle.cancel()
                
                # 授予许可
                request_type = RequestType(queued_request.operation_type)
                await self._grant_permit(
                    request_type,
                    queued_request.endpoint,
                    queued_request.weight,
                    queued_request.priority,
                    current_time
                )
                
                # 通知请求者
                queued_request.future.set_result({
                    'granted': True,
                    'manager': self.name,
                    'request_type': queued_request.operation_type,
                    'weight': queued_request.weight,
                    'endpoint': queued_request.endpoint,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'queued': True
                })
                
        finally:
            self.queue_processing = False
    
    def _remove_from_queue(self, target_request: QueuedRequest):
        """从队列中移除请求"""
        try:
            with self.lock:
                self.waiting_queue.remove(target_request)
                heapq.heapify(self.waiting_queue)
                self.queue_size -= 1
        except ValueError:
            pass  # 请求不在队列中
    
    def _cleanup_old_records(self, current_time: float):
        """清理过期记录"""
        cutoff_time = current_time - 120  # 保留2分钟历史
        
        while self.request_history and self.request_history[0].timestamp < cutoff_time:
            self.request_history.popleft()
    
    def record_response(self, 
                       status_code: int, 
                       headers: Dict[str, str] = None,
                       endpoint: Optional[str] = None):
        """记录响应"""
        
        # 监控响应头
        if headers:
            self._parse_response_headers(headers)
        
        # 处理错误状态码
        if status_code == 429:
            self._handle_429_response(headers, endpoint)
        elif status_code == 418:
            self._handle_418_response(headers, endpoint)
        elif 200 <= status_code < 300:
            # 成功响应，重置失败计数
            self.consecutive_failures = 0
        else:
            # 其他错误
            self.consecutive_failures += 1
        
        # 监控指标
        if self.monitoring:
            self.monitoring.collect_metric(
                "rate_limit_responses",
                1,
                labels={
                    "manager": self.name,
                    "status_code": str(status_code),
                    "endpoint": endpoint or "unknown"
                }
            )
    
    def _parse_response_headers(self, headers: Dict[str, str]):
        """解析响应头"""
        
        # 权重头
        if self.config.weight_header_pattern:
            for header_name, header_value in headers.items():
                if self.config.weight_header_pattern.lower() in header_name.lower():
                    try:
                        self.last_weight_header = int(header_value)
                    except ValueError:
                        pass
        
        # 订单计数头
        if self.config.order_count_header_pattern:
            for header_name, header_value in headers.items():
                if self.config.order_count_header_pattern.lower() in header_name.lower():
                    try:
                        self.last_order_count_header = int(header_value)
                    except ValueError:
                        pass
    
    def _handle_429_response(self, headers: Dict[str, str] = None, endpoint: str = None):
        """处理429响应"""
        self.last_429_time = time.time()
        self.consecutive_failures += 1
        
        # 提取Retry-After头
        retry_after = 60  # 默认1分钟
        if headers and self.config.retry_after_header in headers:
            try:
                retry_after = int(headers[self.config.retry_after_header])
            except ValueError:
                pass
        
        # 设置紧急退避
        self.emergency_backoff_until = time.time() + retry_after
        
        self.logger.warning(
            f"收到429响应 - 限流器 '{self.name}'",
            endpoint=endpoint,
            retry_after=retry_after,
            consecutive_failures=self.consecutive_failures
        )
    
    def _handle_418_response(self, headers: Dict[str, str] = None, endpoint: str = None):
        """处理418响应 - IP封禁"""
        self.last_418_time = time.time()
        
        # 提取ban时长
        ban_duration = 3600  # 默认1小时
        if headers and self.config.retry_after_header in headers:
            try:
                ban_duration = int(headers[self.config.retry_after_header])
            except ValueError:
                pass
        
        # 设置长期退避
        self.emergency_backoff_until = time.time() + ban_duration
        
        self.logger.critical(
            f"收到418响应 - IP被封禁 - 限流器 '{self.name}'",
            endpoint=endpoint,
            ban_duration=ban_duration
        )
        
        # 发送关键告警
        if self.error_handler:
            error = MarketPrismError(
                message=f"限流器 '{self.name}' IP被封禁",
                severity=ErrorSeverity.CRITICAL,
                category=ErrorCategory.EXTERNAL_SERVICE,
                metadata={
                    'manager': self.name,
                    'endpoint': endpoint,
                    'ban_duration': ban_duration
                }
            )
            self.error_handler.handle_error(error)
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        current_time = time.time()
        current_requests_min, current_weight_min = self.minute_tracker.get_current_rate()
        current_requests_sec, current_weight_sec = self.second_tracker.get_current_rate()
        
        status = {
            'name': self.name,
            'current_time': datetime.now(timezone.utc).isoformat(),
            'config': {
                'max_requests_per_second': self.config.max_requests_per_second,
                'max_requests_per_minute': self.config.max_requests_per_minute,
                'weight_based': self.config.weight_based,
                'max_weight_per_minute': self.config.max_weight_per_minute,
                'adaptive_enabled': self.config.adaptive_enabled,
                'queue_enabled': self.config.queue_enabled
            },
            'current_usage': {
                'requests_per_minute': current_requests_min,
                'requests_per_second': current_requests_sec,
                'weight_per_minute': current_weight_min if self.config.weight_based else None
            },
            'adaptive_status': {
                'factor': round(self.adaptive_factor, 3),
                'current_load': round(self.current_load, 3),
                'last_adjustment': datetime.fromtimestamp(self.last_adjustment_time).isoformat()
            } if self.config.adaptive_enabled else None,
            'queue_status': {
                'size': self.queue_size,
                'max_size': self.config.queue_max_size,
                'processing': self.queue_processing
            } if self.config.queue_enabled else None,
            'safety_status': {
                'consecutive_failures': self.consecutive_failures,
                'last_429_time': self.last_429_time,
                'last_418_time': self.last_418_time,
                'emergency_backoff_until': self.emergency_backoff_until,
                'emergency_backoff_active': self.emergency_backoff_until and current_time < self.emergency_backoff_until
            },
            'statistics': {
                'total_requests': self.total_requests,
                'total_allowed': self.total_allowed,
                'total_queued': self.total_queued,
                'total_rejected': self.total_rejected,
                'allow_rate': round(self.total_allowed / max(self.total_requests, 1) * 100, 2)
            },
            'response_headers': {
                'last_weight': self.last_weight_header,
                'last_order_count': self.last_order_count_header
            }
        }
        
        return status
    
    def reset(self):
        """重置限流器"""
        with self.lock:
            # 清空队列
            while self.waiting_queue:
                request = heapq.heappop(self.waiting_queue)
                if not request.future.done():
                    request.future.set_result({
                        'granted': False,
                        'reason': 'Manager reset',
                        'wait_time': 0
                    })
            
            self.queue_size = 0
            self.queue_processing = False
            
            # 重置状态
            self.request_history.clear()
            self.adaptive_factor = 1.0
            self.current_load = 0.0
            self.consecutive_failures = 0
            self.last_429_time = None
            self.last_418_time = None
            self.emergency_backoff_until = None
            
            # 重置统计
            self.total_requests = 0
            self.total_allowed = 0
            self.total_queued = 0
            self.total_rejected = 0
            
        self.logger.info(f"统一限流器 '{self.name}' 已重置")
    
    # 兼容性方法
    async def acquire(self) -> bool:
        """获取许可（兼容方法）"""
        result = await self.acquire_permit()
        return result['granted']


class GlobalUnifiedRateLimitManager:
    """全局统一速率限制管理器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.managers: Dict[str, UnifiedRateLimitManager] = {}
        self.exchange_configs = self._load_exchange_configs()
        
        # 初始化交易所管理器
        for exchange_name, config in self.exchange_configs.items():
            self.managers[exchange_name] = UnifiedRateLimitManager(exchange_name, config)
        
        self.logger.info("全局统一限流管理器已初始化")
    
    def _load_exchange_configs(self) -> Dict[str, RateLimitConfig]:
        """加载交易所配置"""
        configs = {}
        
        # Binance配置
        binance_endpoints = {
            "/api/v3/depth": EndpointConfig(
                path="/api/v3/depth",
                weight=50,
                data_source="撮合引擎",
                recommended_interval=0.1
            ),
            "/api/v3/trades": EndpointConfig(
                path="/api/v3/trades",
                weight=1,
                data_source="缓存",
                recommended_interval=1.0
            ),
            "/api/v3/ticker/24hr": EndpointConfig(
                path="/api/v3/ticker/24hr",
                weight=1,
                data_source="缓存",
                recommended_interval=1.0
            ),
            "/api/v3/account": EndpointConfig(
                path="/api/v3/account",
                weight=10,
                auth_required=True,
                account_based=True,
                data_source="缓存 => 数据库"
            )
        }
        
        configs["binance"] = RateLimitConfig(
            max_requests_per_second=20,
            max_requests_per_minute=1200,
            weight_based=True,
            max_weight_per_minute=6000,
            adaptive_enabled=True,
            queue_enabled=True,
            endpoints=binance_endpoints,
            weight_header_pattern="X-MBX-USED-WEIGHT",
            order_count_header_pattern="X-MBX-ORDER-COUNT"
        )
        
        # OKX配置
        configs["okx"] = RateLimitConfig(
            max_requests_per_second=10,
            max_requests_per_minute=600,
            weight_based=False,
            adaptive_enabled=True,
            queue_enabled=True
        )
        
        # Deribit配置
        configs["deribit"] = RateLimitConfig(
            max_requests_per_second=5,
            max_requests_per_minute=300,
            weight_based=False,
            adaptive_enabled=True,
            queue_enabled=True
        )
        
        # 通用配置
        configs["default"] = RateLimitConfig(
            max_requests_per_second=10,
            max_requests_per_minute=600,
            adaptive_enabled=True,
            queue_enabled=True
        )
        
        return configs
    
    def get_manager(self, name: str) -> UnifiedRateLimitManager:
        """获取或创建管理器"""
        if name not in self.managers:
            # 使用默认配置创建新管理器
            config = self.exchange_configs.get(name, self.exchange_configs["default"])
            self.managers[name] = UnifiedRateLimitManager(name, config)
        
        return self.managers[name]
    
    async def acquire_permit(self,
                           manager_name: str,
                           request_type: Union[str, RequestType] = RequestType.DEFAULT,
                           endpoint: Optional[str] = None,
                           priority: RequestPriority = RequestPriority.MEDIUM,
                           account_based: bool = False,
                           timeout: Optional[float] = None) -> Dict[str, Any]:
        """便捷方法：获取许可"""
        manager = self.get_manager(manager_name)
        return await manager.acquire_permit(
            request_type=request_type,
            endpoint=endpoint,
            priority=priority,
            account_based=account_based,
            timeout=timeout
        )
    
    def record_response(self,
                       manager_name: str,
                       status_code: int,
                       headers: Dict[str, str] = None,
                       endpoint: Optional[str] = None):
        """记录响应"""
        if manager_name in self.managers:
            self.managers[manager_name].record_response(status_code, headers, endpoint)
    
    def get_all_status(self) -> Dict[str, Any]:
        """获取所有管理器状态"""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_managers": len(self.managers),
            "managers": {
                name: manager.get_status()
                for name, manager in self.managers.items()
            }
        }


# 全局实例
_global_unified_manager: Optional[GlobalUnifiedRateLimitManager] = None


def get_unified_rate_limit_manager() -> GlobalUnifiedRateLimitManager:
    """获取全局统一限流管理器"""
    global _global_unified_manager
    if _global_unified_manager is None:
        _global_unified_manager = GlobalUnifiedRateLimitManager()
    return _global_unified_manager


# 向后兼容性别名
RateLimitManager = GlobalUnifiedRateLimitManager
get_rate_limit_manager = get_unified_rate_limit_manager
AdaptiveRateLimiter = UnifiedRateLimitManager
RateLimiterManager = GlobalUnifiedRateLimitManager


def with_rate_limit(manager_name: str,
                   request_type: Union[str, RequestType] = RequestType.DEFAULT,
                   endpoint: Optional[str] = None,
                   priority: RequestPriority = RequestPriority.MEDIUM,
                   account_based: bool = False):
    """
    统一限流装饰器
    
    用法:
    @with_rate_limit("binance", RequestType.ORDERBOOK_SNAPSHOT, "/api/v3/depth")
    async def get_binance_orderbook():
        # API 请求代码
        pass
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            manager = get_unified_rate_limit_manager()
            
            # 获取请求许可
            permit = await manager.acquire_permit(
                manager_name=manager_name,
                request_type=request_type,
                endpoint=endpoint,
                priority=priority,
                account_based=account_based
            )
            
            if not permit['granted']:
                wait_time = permit.get('wait_time', 0)
                raise RateLimitViolation(
                    message=permit['reason'],
                    wait_time=wait_time,
                    exchange=manager_name,
                    endpoint=endpoint
                )
            
            # 执行实际请求
            try:
                result = await func(*args, **kwargs)
                
                # 记录成功响应
                manager.record_response(manager_name, 200, endpoint=endpoint)
                
                return result
                
            except Exception as e:
                # 尝试提取状态码
                status_code = 500
                headers = {}
                
                if hasattr(e, 'response'):
                    if hasattr(e.response, 'status_code'):
                        status_code = e.response.status_code
                    if hasattr(e.response, 'headers'):
                        headers = dict(e.response.headers)
                
                # 记录错误响应
                manager.record_response(manager_name, status_code, headers, endpoint)
                
                # 重新抛出异常
                raise
        
        return wrapper
    return decorator