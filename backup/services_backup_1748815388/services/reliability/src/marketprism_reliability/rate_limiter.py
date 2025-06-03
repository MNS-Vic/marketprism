"""
企业级自适应限流器系统

实现令牌桶算法、滑动窗口限流和智能自适应策略
提供多级限流、优先级队列和动态调整功能
"""

import asyncio
import time
import logging
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from collections import deque, defaultdict
import heapq

logger = logging.getLogger(__name__)


class RequestPriority(Enum):
    """请求优先级"""
    CRITICAL = 1    # 关键请求
    HIGH = 2        # 高优先级
    NORMAL = 3      # 普通优先级
    LOW = 4         # 低优先级


class RateLimitStrategy(Enum):
    """限流策略"""
    TOKEN_BUCKET = "token_bucket"           # 令牌桶
    SLIDING_WINDOW = "sliding_window"       # 滑动窗口
    FIXED_WINDOW = "fixed_window"           # 固定窗口
    ADAPTIVE = "adaptive"                   # 自适应


@dataclass
class RateLimitConfig:
    """限流器配置"""
    max_requests_per_second: float = 100.0     # 每秒最大请求数
    burst_capacity: int = 200                  # 突发容量
    window_size_seconds: int = 60              # 窗口大小(秒)
    strategy: RateLimitStrategy = RateLimitStrategy.ADAPTIVE
    
    # 自适应配置
    adaptive_factor: float = 1.0               # 自适应因子
    min_rate_factor: float = 0.1               # 最小速率因子
    max_rate_factor: float = 2.0               # 最大速率因子
    adjustment_interval: float = 30.0          # 调整间隔(秒)
    
    # 优先级配置
    enable_priority_queue: bool = True         # 启用优先级队列
    queue_timeout: float = 30.0                # 队列超时时间(秒)
    max_queue_size: int = 1000                 # 最大队列大小


class RateLimitException(Exception):
    """限流异常"""
    pass


class TokenBucket:
    """令牌桶实现"""
    
    def __init__(self, rate: float, capacity: int):
        self.rate = rate                    # 令牌生成速率
        self.capacity = capacity            # 桶容量
        self.tokens = capacity              # 当前令牌数
        self.last_refill = time.time()      # 上次填充时间
        self._lock = asyncio.Lock()
    
    async def consume(self, tokens: int = 1) -> bool:
        """消费令牌"""
        async with self._lock:
            await self._refill()
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
    
    async def _refill(self):
        """填充令牌"""
        now = time.time()
        elapsed = now - self.last_refill
        
        # 计算应该添加的令牌数
        tokens_to_add = elapsed * self.rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now
    
    def get_available_tokens(self) -> int:
        """获取可用令牌数"""
        return int(self.tokens)


class SlidingWindow:
    """滑动窗口实现"""
    
    def __init__(self, window_size: int, max_requests: int):
        self.window_size = window_size      # 窗口大小(秒)
        self.max_requests = max_requests    # 最大请求数
        self.requests = deque()             # 请求时间戳队列
        self._lock = asyncio.Lock()
    
    async def is_allowed(self) -> bool:
        """检查是否允许请求"""
        async with self._lock:
            now = time.time()
            
            # 清理过期请求
            while self.requests and self.requests[0] <= now - self.window_size:
                self.requests.popleft()
            
            # 检查是否超过限制
            if len(self.requests) < self.max_requests:
                self.requests.append(now)
                return True
            
            return False
    
    def get_current_count(self) -> int:
        """获取当前窗口内请求数"""
        now = time.time()
        # 清理过期请求
        while self.requests and self.requests[0] <= now - self.window_size:
            self.requests.popleft()
        return len(self.requests)


class PriorityQueue:
    """优先级队列"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.queue = []                     # 堆队列
        self.waiting_tasks = {}             # 等待任务
        self._lock = asyncio.Lock()
        self._counter = 0                   # 计数器，保证FIFO
    
    async def enqueue(self, priority: RequestPriority, request_id: str, timeout: float) -> bool:
        """入队"""
        async with self._lock:
            if len(self.queue) >= self.max_size:
                return False
            
            # 创建等待事件
            event = asyncio.Event()
            self.waiting_tasks[request_id] = event
            
            # 入队 (优先级, 计数器, 请求ID, 超时时间)
            # 确保正确处理枚举值
            if isinstance(priority, RequestPriority):
                priority_value = priority.value
            else:
                # 如果是字符串，尝试转换为对应的枚举值
                if isinstance(priority, str):
                    try:
                        priority_value = RequestPriority[priority.upper()].value
                    except (KeyError, AttributeError):
                        priority_value = RequestPriority.NORMAL.value
                else:
                    priority_value = priority
            
            heapq.heappush(self.queue, (priority_value, self._counter, request_id, time.time() + timeout))
            self._counter += 1
            
            return True
    
    async def dequeue(self) -> Optional[str]:
        """出队"""
        async with self._lock:
            while self.queue:
                priority, counter, request_id, expire_time = heapq.heappop(self.queue)
                
                # 检查是否过期
                if time.time() > expire_time:
                    # 清理过期任务
                    if request_id in self.waiting_tasks:
                        del self.waiting_tasks[request_id]
                    continue
                
                return request_id
            
            return None
    
    async def notify(self, request_id: str):
        """通知等待的任务"""
        if request_id in self.waiting_tasks:
            event = self.waiting_tasks[request_id]
            event.set()
            del self.waiting_tasks[request_id]
    
    async def wait_for_turn(self, request_id: str, timeout: float) -> bool:
        """等待轮到自己"""
        if request_id not in self.waiting_tasks:
            return False
        
        event = self.waiting_tasks[request_id]
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            # 清理超时任务
            if request_id in self.waiting_tasks:
                del self.waiting_tasks[request_id]
            return False


class RateLimiter:
    """企业级自适应限流器"""
    
    def __init__(self, name: str, config: RateLimitConfig = None):
        self.name = name
        self.config = config or RateLimitConfig()
        
        # 限流器组件
        self.token_bucket = TokenBucket(
            self.config.max_requests_per_second,
            self.config.burst_capacity
        )
        
        self.sliding_window = SlidingWindow(
            self.config.window_size_seconds,
            int(self.config.max_requests_per_second * self.config.window_size_seconds)
        )
        
        if self.config.enable_priority_queue:
            self.priority_queue = PriorityQueue(self.config.max_queue_size)
        
        # 自适应参数
        self.current_rate_factor = 1.0
        self.last_adjustment = time.time()
        
        # 监控指标
        self.metrics = {
            "total_requests": 0,
            "allowed_requests": 0,
            "rejected_requests": 0,
            "queued_requests": 0,
            "current_rate": self.config.max_requests_per_second,
            "current_load": 0.0,
            "average_wait_time": 0.0
        }
        
        # 性能统计
        self.request_times = deque(maxlen=1000)
        self.wait_times = deque(maxlen=1000)
        
        self._request_counter = 0
        self._lock = asyncio.Lock()
        self._shutdown = False
        
        # 启动后台队列处理任务
        if self.config.enable_priority_queue:
            self._queue_processor_task = asyncio.create_task(self._queue_processor_loop())
        
        logger.info(f"限流器 '{name}' 初始化完成，配置: {self.config}")
    
    async def _queue_processor_loop(self):
        """后台队列处理循环"""
        while not self._shutdown:
            try:
                # 尝试获取许可
                if await self._try_acquire():
                    # 从队列中取出下一个请求
                    request_id = await self.priority_queue.dequeue()
                    if request_id:
                        await self.priority_queue.notify(request_id)
                    else:
                        # 队列为空，等待一段时间
                        await asyncio.sleep(0.1)
                else:
                    # 没有可用令牌，等待一段时间
                    await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"队列处理器错误: {e}")
                await asyncio.sleep(0.1)
    
    async def acquire(self, priority: RequestPriority = RequestPriority.NORMAL, 
                     timeout: float = None) -> bool:
        """
        获取访问许可
        
        Args:
            priority: 请求优先级
            timeout: 超时时间
            
        Returns:
            是否获得许可
        """
        start_time = time.time()
        timeout = timeout or self.config.queue_timeout
        
        async with self._lock:
            self.metrics["total_requests"] += 1
            self._request_counter += 1
            request_id = f"{self.name}_{self._request_counter}"
        
        # 自适应调整
        await self._adaptive_adjustment()
        
        # 尝试直接获取许可
        if await self._try_acquire():
            await self._record_success(start_time)
            return True
        
        # 如果启用优先级队列，则入队等待
        if self.config.enable_priority_queue:
            return await self._queue_and_wait(request_id, priority, timeout, start_time)
        else:
            await self._record_rejection(start_time)
            return False
    
    async def _try_acquire(self) -> bool:
        """尝试获取许可"""
        if self.config.strategy == RateLimitStrategy.TOKEN_BUCKET:
            return await self.token_bucket.consume()
        
        elif self.config.strategy == RateLimitStrategy.SLIDING_WINDOW:
            return await self.sliding_window.is_allowed()
        
        elif self.config.strategy == RateLimitStrategy.ADAPTIVE:
            # 自适应策略：结合令牌桶和滑动窗口
            token_allowed = await self.token_bucket.consume()
            window_allowed = await self.sliding_window.is_allowed()
            return token_allowed and window_allowed
        
        return False
    
    async def _queue_and_wait(self, request_id: str, priority: RequestPriority, 
                             timeout: float, start_time: float) -> bool:
        """排队等待"""
        # 入队 - 注意参数顺序：priority在前
        queued = await self.priority_queue.enqueue(priority, request_id, timeout)
        if not queued:
            await self._record_rejection(start_time)
            return False
        
        async with self._lock:
            self.metrics["queued_requests"] += 1
        
        # 等待轮到自己
        if await self.priority_queue.wait_for_turn(request_id, timeout):
            await self._record_success(start_time)
            return True
        else:
            await self._record_rejection(start_time)
            return False
    
    async def _adaptive_adjustment(self):
        """自适应调整"""
        if self.config.strategy != RateLimitStrategy.ADAPTIVE:
            return
        
        now = time.time()
        if now - self.last_adjustment < self.config.adjustment_interval:
            return
        
        # 计算当前负载
        current_load = self._calculate_current_load()
        
        # 根据负载调整速率
        if current_load > 0.8:  # 高负载，降低速率
            self.current_rate_factor *= 0.9
        elif current_load < 0.5:  # 低负载，提高速率
            self.current_rate_factor *= 1.1
        
        # 限制调整范围
        self.current_rate_factor = max(
            self.config.min_rate_factor,
            min(self.config.max_rate_factor, self.current_rate_factor)
        )
        
        # 更新令牌桶速率
        new_rate = self.config.max_requests_per_second * self.current_rate_factor
        self.token_bucket.rate = new_rate
        
        async with self._lock:
            self.metrics["current_rate"] = new_rate
            self.metrics["current_load"] = current_load
        
        self.last_adjustment = now
        
        logger.debug(f"限流器 '{self.name}' 自适应调整: 负载={current_load:.2f}, 速率因子={self.current_rate_factor:.2f}")
    
    def _calculate_current_load(self) -> float:
        """计算当前负载"""
        if self.config.strategy == RateLimitStrategy.SLIDING_WINDOW:
            current_count = self.sliding_window.get_current_count()
            max_count = int(self.config.max_requests_per_second * self.config.window_size_seconds)
            return current_count / max_count if max_count > 0 else 0.0
        
        elif self.config.strategy == RateLimitStrategy.TOKEN_BUCKET:
            available_tokens = self.token_bucket.get_available_tokens()
            return 1.0 - (available_tokens / self.config.burst_capacity)
        
        return 0.5  # 默认中等负载
    
    async def _record_success(self, start_time: float):
        """记录成功请求"""
        wait_time = time.time() - start_time
        
        async with self._lock:
            self.metrics["allowed_requests"] += 1
            self.wait_times.append(wait_time)
            
            if self.wait_times:
                self.metrics["average_wait_time"] = sum(self.wait_times) / len(self.wait_times)
    
    async def _record_rejection(self, start_time: float):
        """记录拒绝请求"""
        async with self._lock:
            self.metrics["rejected_requests"] += 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取监控指标"""
        return {
            **self.metrics,
            "config": {
                "max_requests_per_second": self.config.max_requests_per_second,
                "burst_capacity": self.config.burst_capacity,
                "strategy": self.config.strategy.value if hasattr(self.config.strategy, 'value') else str(self.config.strategy),
                "current_rate_factor": self.current_rate_factor
            },
            "queue_size": len(self.priority_queue.queue) if self.config.enable_priority_queue else 0,
            "available_tokens": self.token_bucket.get_available_tokens(),
            "window_count": self.sliding_window.get_current_count()
        }
    
    def reset(self):
        """重置限流器状态"""
        self.token_bucket.tokens = self.token_bucket.capacity
        self.sliding_window.requests.clear()
        
        if self.config.enable_priority_queue:
            self.priority_queue.queue.clear()
            self.priority_queue.waiting_tasks.clear()
        
        self.current_rate_factor = 1.0
        self.request_times.clear()
        self.wait_times.clear()
        
        # 重置指标
        self.metrics.update({
            "total_requests": 0,
            "allowed_requests": 0,
            "rejected_requests": 0,
            "queued_requests": 0,
            "current_load": 0.0,
            "average_wait_time": 0.0
        })
        
        logger.info(f"限流器 '{self.name}' 已重置")
    
    async def shutdown(self):
        """关闭限流器"""
        self._shutdown = True
        if hasattr(self, '_queue_processor_task'):
            self._queue_processor_task.cancel()
            try:
                await self._queue_processor_task
            except asyncio.CancelledError:
                pass


# 装饰器支持
def rate_limit(name: str, config: RateLimitConfig = None, priority: RequestPriority = RequestPriority.NORMAL):
    """限流装饰器"""
    limiter = RateLimiter(name, config)
    
    def decorator(func):
        async def wrapper(*args, **kwargs):
            if await limiter.acquire(priority):
                return await func(*args, **kwargs)
            else:
                raise RateLimitException(f"请求被限流器 '{name}' 拒绝")
        return wrapper
    return decorator


# 使用示例
if __name__ == "__main__":
    async def example_usage():
        # 创建限流器配置
        config = RateLimitConfig(
            max_requests_per_second=10.0,
            burst_capacity=20,
            strategy=RateLimitStrategy.ADAPTIVE,
            enable_priority_queue=True
        )
        
        # 创建限流器
        limiter = RateLimiter("api_limiter", config)
        
        # 模拟请求
        async def make_request(request_id: int, priority: RequestPriority):
            start_time = time.time()
            allowed = await limiter.acquire(priority)
            duration = time.time() - start_time
            
            status = "允许" if allowed else "拒绝"
            print(f"请求 {request_id} ({priority.name}): {status}, 等待时间: {duration:.3f}s")
            
            if allowed:
                # 模拟处理时间
                await asyncio.sleep(0.1)
        
        # 并发发送请求
        tasks = []
        for i in range(50):
            priority = RequestPriority.HIGH if i % 5 == 0 else RequestPriority.NORMAL
            task = make_request(i, priority)
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        # 打印指标
        print("\n限流器指标:")
        metrics = limiter.get_metrics()
        for key, value in metrics.items():
            print(f"  {key}: {value}")
        
        # 关闭限流器
        await limiter.shutdown()
    
    # 运行示例
    asyncio.run(example_usage())