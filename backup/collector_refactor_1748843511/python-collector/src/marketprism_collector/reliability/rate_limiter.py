"""
MarketPrism 智能限流器系统

设计目标：
- 保护系统免受过载
- 维持稳定性能
- 自适应调整限流阈值
- 智能排队机制

特性：
- 滑动窗口算法
- 优先级队列
- 自适应阈值调整
- 详细监控指标
"""

import asyncio
import time
import logging
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum
from dataclasses import dataclass, field
from collections import deque
import heapq
from datetime import datetime

logger = logging.getLogger(__name__)


class RequestPriority(Enum):
    """请求优先级"""
    CRITICAL = 1    # 关键操作 (健康检查、告警)
    HIGH = 2        # 高优先级 (交易数据)
    NORMAL = 3      # 普通优先级 (历史数据)
    LOW = 4         # 低优先级 (统计数据)


@dataclass
class RateLimitConfig:
    """限流器配置"""
    max_requests_per_second: int = 50       # 最大请求速率
    window_size: int = 60                   # 时间窗口 (秒)
    adaptive_factor_min: float = 0.5        # 自适应因子最小值
    adaptive_factor_max: float = 2.0        # 自适应因子最大值
    adaptive_threshold_high: float = 0.8     # 高负载阈值
    adaptive_threshold_low: float = 0.5      # 低负载阈值
    queue_max_size: int = 1000              # 等待队列最大大小
    queue_timeout: float = 30.0             # 队列超时 (秒)
    burst_allowance: int = 10               # 突发允许量


@dataclass
class RequestRecord:
    """请求记录"""
    timestamp: float = field(default_factory=time.time)
    priority: RequestPriority = RequestPriority.NORMAL
    operation_type: str = ""
    success: bool = True
    response_time: float = 0.0


@dataclass
class QueuedRequest:
    """排队请求"""
    priority: RequestPriority
    timestamp: float
    operation_type: str
    future: asyncio.Future
    timeout_handle: Optional[asyncio.Handle] = None
    
    def __lt__(self, other):
        # 优先级队列比较 (优先级数值越小，优先级越高)
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        return self.timestamp < other.timestamp


class AdaptiveRateLimiter:
    """自适应限流器"""
    
    def __init__(self, name: str, config: Optional[RateLimitConfig] = None):
        self.name = name
        self.config = config or RateLimitConfig()
        
        # 当前状态
        self.current_load = 0.0
        self.adaptive_factor = 1.0
        self.last_adjustment_time = time.time()
        
        # 请求历史记录
        self.request_history: deque = deque(maxlen=10000)
        
        # 等待队列 (优先级队列)
        self.waiting_queue: List[QueuedRequest] = []
        self.queue_size = 0
        
        # 统计指标
        self.total_requests = 0
        self.total_allowed = 0
        self.total_queued = 0
        self.total_rejected = 0
        
        # 操作类型限制
        self.operation_limits: Dict[str, int] = {}
        
        logger.info(f"限流器 '{name}' 已初始化，配置: {self.config}")
    
    async def acquire_permit(
        self, 
        operation_type: str,
        priority: RequestPriority = RequestPriority.NORMAL,
        timeout: Optional[float] = None
    ) -> bool:
        """获取操作许可"""
        self.total_requests += 1
        current_time = time.time()
        
        # 清理过期请求记录
        self._cleanup_old_records(current_time)
        
        # 计算当前请求速率
        current_rps = self._calculate_current_rps()
        
        # 自适应调整限流阈值
        self._adjust_adaptive_factor(current_rps)
        
        # 计算有效限制
        effective_limit = self._get_effective_limit(operation_type)
        
        # 检查是否可以直接允许
        if current_rps < effective_limit:
            # 检查突发限制
            if self._check_burst_limit():
                await self._grant_permit(operation_type, priority, current_time)
                return True
        
        # 需要排队等待
        return await self._enqueue_request(operation_type, priority, timeout)
    
    def _calculate_current_rps(self) -> float:
        """计算当前请求速率"""
        current_time = time.time()
        window_start = current_time - self.config.window_size
        
        recent_requests = [
            record for record in self.request_history
            if record.timestamp >= window_start
        ]
        
        if not recent_requests:
            return 0.0
        
        return len(recent_requests) / self.config.window_size
    
    def _adjust_adaptive_factor(self, current_rps: float):
        """自适应调整限流因子"""
        max_rps = self.config.max_requests_per_second
        load_ratio = current_rps / max_rps if max_rps > 0 else 0
        
        # 高负载时收紧限流
        if load_ratio >= self.config.adaptive_threshold_high:
            self.adaptive_factor = max(
                self.adaptive_factor * 0.9,
                self.config.adaptive_factor_min
            )
            logger.debug(f"限流器 '{self.name}' 收紧限流，因子: {self.adaptive_factor:.2f}")
        
        # 低负载时放宽限流
        elif load_ratio <= self.config.adaptive_threshold_low:
            self.adaptive_factor = min(
                self.adaptive_factor * 1.1,
                self.config.adaptive_factor_max
            )
            logger.debug(f"限流器 '{self.name}' 放宽限流，因子: {self.adaptive_factor:.2f}")
        
        self.current_load = load_ratio
        self.last_adjustment_time = time.time()
    
    def _get_effective_limit(self, operation_type: str) -> float:
        """获取有效限制"""
        base_limit = self.config.max_requests_per_second * self.adaptive_factor
        
        # 应用操作类型特定限制
        if operation_type in self.operation_limits:
            operation_limit = self.operation_limits[operation_type]
            return min(base_limit, operation_limit)
        
        return base_limit
    
    def _check_burst_limit(self) -> bool:
        """检查突发限制"""
        current_time = time.time()
        burst_window = 1.0  # 1秒突发窗口
        
        recent_burst = [
            record for record in self.request_history
            if record.timestamp >= current_time - burst_window
        ]
        
        return len(recent_burst) < self.config.burst_allowance
    
    async def _grant_permit(
        self, 
        operation_type: str, 
        priority: RequestPriority,
        timestamp: float
    ):
        """授予许可"""
        record = RequestRecord(
            timestamp=timestamp,
            priority=priority,
            operation_type=operation_type,
            success=True
        )
        self.request_history.append(record)
        self.total_allowed += 1
        
        logger.debug(f"限流器 '{self.name}' 授予许可: {operation_type} (优先级: {priority.name})")
    
    async def _enqueue_request(
        self, 
        operation_type: str,
        priority: RequestPriority,
        timeout: Optional[float]
    ) -> bool:
        """将请求加入等待队列"""
        # 检查队列容量
        if self.queue_size >= self.config.queue_max_size:
            self.total_rejected += 1
            logger.warning(f"限流器 '{self.name}' 队列已满，拒绝请求: {operation_type}")
            return False
        
        # 创建排队请求
        future = asyncio.Future()
        request_timeout = timeout or self.config.queue_timeout
        
        queued_request = QueuedRequest(
            priority=priority,
            timestamp=time.time(),
            operation_type=operation_type,
            future=future
        )
        
        # 设置超时处理
        def timeout_callback():
            if not future.done():
                future.set_result(False)
                self._remove_from_queue(queued_request)
                logger.warning(f"限流器 '{self.name}' 请求超时: {operation_type}")
        
        queued_request.timeout_handle = asyncio.get_event_loop().call_later(
            request_timeout, timeout_callback
        )
        
        # 加入优先级队列
        heapq.heappush(self.waiting_queue, queued_request)
        self.queue_size += 1
        self.total_queued += 1
        
        logger.debug(f"限流器 '{self.name}' 请求排队: {operation_type} (队列大小: {self.queue_size})")
        
        # 启动队列处理
        asyncio.create_task(self._process_queue())
        
        # 等待处理结果
        return await future
    
    async def _process_queue(self):
        """处理等待队列"""
        while self.waiting_queue and self.queue_size > 0:
            # 检查是否有可用许可
            current_rps = self._calculate_current_rps()
            effective_limit = self._get_effective_limit("queue_processing")
            
            if current_rps >= effective_limit:
                # 没有可用许可，等待一段时间再试
                await asyncio.sleep(0.1)
                continue
            
            # 获取最高优先级请求
            try:
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
            await self._grant_permit(
                queued_request.operation_type,
                queued_request.priority,
                time.time()
            )
            
            # 通知请求者
            queued_request.future.set_result(True)
            
            logger.debug(f"限流器 '{self.name}' 队列处理成功: {queued_request.operation_type}")
    
    def _remove_from_queue(self, target_request: QueuedRequest):
        """从队列中移除请求"""
        # 注意：这是简化实现，实际应用中可能需要更高效的数据结构
        try:
            self.waiting_queue.remove(target_request)
            heapq.heapify(self.waiting_queue)
            self.queue_size -= 1
        except ValueError:
            pass  # 请求不在队列中
    
    def _cleanup_old_records(self, current_time: float):
        """清理过期记录"""
        cutoff_time = current_time - self.config.window_size * 2  # 保留更长历史
        
        while self.request_history and self.request_history[0].timestamp < cutoff_time:
            self.request_history.popleft()
    
    def set_operation_limit(self, operation_type: str, limit: int):
        """设置操作类型特定限制"""
        self.operation_limits[operation_type] = limit
        logger.info(f"限流器 '{self.name}' 设置操作限制: {operation_type} = {limit}/s")
    
    async def start(self):
        """启动限流器"""
        logger.info(f"限流器 '{self.name}' 已启动")
        # 启动队列处理任务
        asyncio.create_task(self._process_queue())
    
    async def stop(self):
        """停止限流器"""
        logger.info(f"限流器 '{self.name}' 已停止")
        # 清空等待队列
        while self.waiting_queue:
            request = heapq.heappop(self.waiting_queue)
            if not request.future.done():
                request.future.set_result(False)
        self.queue_size = 0
    
    # 添加一个兼容方法
    async def acquire(self) -> bool:
        """获取许可（兼容方法）"""
        return await self.acquire_permit("default")

    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        current_time = time.time()
        return {
            "name": self.name,
            "is_running": True,  # 简化实现
            "current_load": round(self.current_load, 3),
            "adaptive_factor": round(self.adaptive_factor, 3),
            "max_rps": self.config.max_requests_per_second,
            "current_rps": round(self._calculate_current_rps(), 2),
            "queue_size": self.queue_size,
            "queue_max_size": self.config.queue_max_size,
            "total_requests": self.total_requests,
            "total_allowed": self.total_allowed,
            "total_queued": self.total_queued,
            "total_rejected": self.total_rejected,
            "allow_rate": round(self.total_allowed / max(self.total_requests, 1) * 100, 2),
            "operation_limits": self.operation_limits,
            "last_adjustment": datetime.fromtimestamp(self.last_adjustment_time).isoformat() if self.last_adjustment_time else None
        }
    
    def reset(self):
        """重置限流器"""
        self.request_history.clear()
        self.waiting_queue.clear()
        self.queue_size = 0
        self.adaptive_factor = 1.0
        self.current_load = 0.0
        self.total_requests = 0
        self.total_allowed = 0
        self.total_queued = 0
        self.total_rejected = 0
        logger.info(f"限流器 '{self.name}' 已重置")


# 限流器管理器
class RateLimiterManager:
    """限流器管理器"""
    
    def __init__(self):
        self.limiters: Dict[str, AdaptiveRateLimiter] = {}
        
        # 预定义操作类型限制
        self.operation_configs = {
            "funding_rate_collection": {"max_rps": 10, "priority": RequestPriority.HIGH},
            "trade_data_processing": {"max_rps": 100, "priority": RequestPriority.HIGH},
            "health_check": {"max_rps": 5, "priority": RequestPriority.CRITICAL},
            "admin_operations": {"max_rps": 1, "priority": RequestPriority.NORMAL},
            "historical_data": {"max_rps": 20, "priority": RequestPriority.LOW}
        }
    
    def get_limiter(self, name: str, config: Optional[RateLimitConfig] = None) -> AdaptiveRateLimiter:
        """获取或创建限流器"""
        if name not in self.limiters:
            limiter = AdaptiveRateLimiter(name, config)
            
            # 应用预定义限制
            for op_type, op_config in self.operation_configs.items():
                limiter.set_operation_limit(op_type, op_config["max_rps"])
            
            self.limiters[name] = limiter
        
        return self.limiters[name]
    
    async def acquire_permit(
        self, 
        limiter_name: str,
        operation_type: str,
        priority: Optional[RequestPriority] = None,
        timeout: Optional[float] = None
    ) -> bool:
        """便捷方法：获取许可"""
        limiter = self.get_limiter(limiter_name)
        
        # 使用预定义优先级
        if priority is None and operation_type in self.operation_configs:
            priority = self.operation_configs[operation_type]["priority"]
        
        priority = priority or RequestPriority.NORMAL
        
        return await limiter.acquire_permit(operation_type, priority, timeout)
    
    def get_all_status(self) -> Dict[str, Any]:
        """获取所有限流器状态"""
        return {
            name: limiter.get_status()
            for name, limiter in self.limiters.items()
        }


# 全局限流器管理器实例
rate_limiter_manager = RateLimiterManager() 