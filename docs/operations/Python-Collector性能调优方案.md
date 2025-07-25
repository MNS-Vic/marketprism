# Python-Collector 性能调优方案

## ⚡ 性能调优完整方案

**制定时间**: 2025-05-24  
**适用范围**: services/python-collector  
**优化目标**: 企业级性能标准  

## 🎯 性能调优目标

### 核心性能指标
- **吞吐量提升**: 40.9 msg/s → 80+ msg/s (+95%)
- **内存优化**: 600MB → 400MB (-33%)
- **延迟降低**: P95 < 100ms, P99 < 500ms
- **连接稳定性**: 99.9%+ 连接可用性
- **错误率控制**: < 0.1% 处理错误率

## 🧠 内存使用优化

### 1. 内存泄漏检测和修复

#### 1.1 内存监控增强
```python
# services/python-collector/src/marketprism_collector/monitoring/memory_profiler.py
import tracemalloc
import gc
import psutil
from typing import Dict, List, Optional
import structlog

class MemoryProfiler:
    """内存使用分析器"""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        self.snapshots = []
        self.baseline_memory = None
        
    def start_profiling(self):
        """开始内存分析"""
        tracemalloc.start()
        self.baseline_memory = self._get_memory_usage()
        self.logger.info("内存分析已启动", baseline_mb=self.baseline_memory)
    
    def take_snapshot(self, label: str = ""):
        """拍摄内存快照"""
        if not tracemalloc.is_tracing():
            return None
            
        snapshot = tracemalloc.take_snapshot()
        current_memory = self._get_memory_usage()
        
        snapshot_info = {
            'label': label,
            'timestamp': time.time(),
            'memory_mb': current_memory,
            'memory_delta': current_memory - self.baseline_memory,
            'snapshot': snapshot
        }
        
        self.snapshots.append(snapshot_info)
        self.logger.info(
            "内存快照已拍摄",
            label=label,
            memory_mb=current_memory,
            delta_mb=snapshot_info['memory_delta']
        )
        
        return snapshot_info
    
    def analyze_top_allocations(self, limit: int = 10) -> List[Dict]:
        """分析内存分配热点"""
        if not self.snapshots:
            return []
            
        latest_snapshot = self.snapshots[-1]['snapshot']
        top_stats = latest_snapshot.statistics('lineno')
        
        allocations = []
        for stat in top_stats[:limit]:
            allocations.append({
                'file': stat.traceback.format()[0],
                'size_mb': stat.size / 1024 / 1024,
                'count': stat.count
            })
            
        return allocations
    
    def _get_memory_usage(self) -> float:
        """获取当前内存使用量(MB)"""
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024
```

#### 1.2 对象池管理
```python
# services/python-collector/src/marketprism_collector/utils/object_pool.py
from typing import Generic, TypeVar, Queue, Callable
import threading

T = TypeVar('T')

class ObjectPool(Generic[T]):
    """对象池 - 减少对象创建开销"""
    
    def __init__(self, factory: Callable[[], T], max_size: int = 100):
        self.factory = factory
        self.pool = Queue(maxsize=max_size)
        self.max_size = max_size
        self.lock = threading.Lock()
        
    def acquire(self) -> T:
        """获取对象"""
        try:
            return self.pool.get_nowait()
        except:
            return self.factory()
    
    def release(self, obj: T):
        """释放对象"""
        if self.pool.qsize() < self.max_size:
            # 重置对象状态
            if hasattr(obj, 'reset'):
                obj.reset()
            self.pool.put_nowait(obj)

# 使用示例：消息对象池
class MessagePool:
    """消息对象池"""
    
    def __init__(self):
        self.trade_pool = ObjectPool(lambda: NormalizedTrade.__new__(NormalizedTrade), 1000)
        self.orderbook_pool = ObjectPool(lambda: NormalizedOrderBook.__new__(NormalizedOrderBook), 500)
        self.ticker_pool = ObjectPool(lambda: NormalizedTicker.__new__(NormalizedTicker), 200)
    
    def get_trade(self) -> NormalizedTrade:
        return self.trade_pool.acquire()
    
    def release_trade(self, trade: NormalizedTrade):
        self.trade_pool.release(trade)
```

#### 1.3 内存使用优化策略
```python
# services/python-collector/src/marketprism_collector/optimizations/memory_optimizer.py
import gc
import weakref
from typing import Dict, Set
import structlog

class MemoryOptimizer:
    """内存优化器"""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        self.weak_refs: Set[weakref.ref] = set()
        
    def optimize_gc(self):
        """优化垃圾回收"""
        # 调整GC阈值
        gc.set_threshold(700, 10, 10)  # 更激进的GC
        
        # 强制回收
        collected = gc.collect()
        self.logger.debug("垃圾回收完成", collected_objects=collected)
        
    def register_cleanup(self, obj, cleanup_func):
        """注册清理函数"""
        def cleanup_callback(ref):
            cleanup_func()
            self.weak_refs.discard(ref)
            
        weak_ref = weakref.ref(obj, cleanup_callback)
        self.weak_refs.add(weak_ref)
        
    def clear_caches(self):
        """清理缓存"""
        # 清理函数缓存
        import functools
        functools.lru_cache.cache_clear()
        
        # 清理正则表达式缓存
        import re
        re.purge()
```

### 2. 数据结构优化

#### 2.1 使用__slots__减少内存占用
```python
# services/python-collector/src/marketprism_collector/types_optimized.py
from decimal import Decimal
from datetime import datetime
from typing import List, Optional

class OptimizedNormalizedTrade:
    """内存优化的交易数据"""
    __slots__ = (
        'exchange_name', 'symbol_name', 'trade_id', 'price', 'quantity',
        'side', 'timestamp', 'is_buyer_maker', 'quote_quantity'
    )
    
    def __init__(self, **kwargs):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))
    
    def reset(self):
        """重置对象状态供对象池使用"""
        for slot in self.__slots__:
            setattr(self, slot, None)

class OptimizedOrderBookEntry:
    """内存优化的订单簿条目"""
    __slots__ = ('price', 'quantity')
    
    def __init__(self, price: Decimal, quantity: Decimal):
        self.price = price
        self.quantity = quantity
```

#### 2.2 批量处理优化
```python
# services/python-collector/src/marketprism_collector/processing/batch_processor.py
from collections import deque
import asyncio
from typing import List, Callable, TypeVar

T = TypeVar('T')

class BatchProcessor:
    """批量处理器 - 减少处理开销"""
    
    def __init__(self, 
                 batch_size: int = 100,
                 flush_interval: float = 1.0,
                 processor: Callable[[List[T]], None] = None):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.processor = processor
        self.buffer = deque()
        self.last_flush = time.time()
        
    async def add(self, item: T):
        """添加项目到批处理缓冲区"""
        self.buffer.append(item)
        
        # 检查是否需要刷新
        if (len(self.buffer) >= self.batch_size or 
            time.time() - self.last_flush >= self.flush_interval):
            await self.flush()
    
    async def flush(self):
        """刷新缓冲区"""
        if not self.buffer:
            return
            
        batch = list(self.buffer)
        self.buffer.clear()
        self.last_flush = time.time()
        
        if self.processor:
            await self.processor(batch)
```

## 🔗 连接池管理优化

### 1. WebSocket连接池
```python
# services/python-collector/src/marketprism_collector/connections/websocket_pool.py
import asyncio
import websockets
from typing import Dict, List, Optional
import structlog

class WebSocketPool:
    """WebSocket连接池管理器"""
    
    def __init__(self, max_connections_per_exchange: int = 5):
        self.max_connections = max_connections_per_exchange
        self.pools: Dict[str, List[websockets.WebSocketServerProtocol]] = {}
        self.active_connections: Dict[str, int] = {}
        self.logger = structlog.get_logger(__name__)
        
    async def get_connection(self, exchange: str, url: str) -> websockets.WebSocketServerProtocol:
        """获取连接"""
        if exchange not in self.pools:
            self.pools[exchange] = []
            self.active_connections[exchange] = 0
            
        # 尝试复用现有连接
        pool = self.pools[exchange]
        for conn in pool[:]:  # 复制列表避免修改时迭代
            if conn.open:
                return conn
            else:
                pool.remove(conn)
                self.active_connections[exchange] -= 1
        
        # 创建新连接
        if self.active_connections[exchange] < self.max_connections:
            try:
                conn = await websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=10,
                    max_size=2**20,  # 1MB
                    compression=None  # 禁用压缩减少CPU开销
                )
                
                pool.append(conn)
                self.active_connections[exchange] += 1
                
                self.logger.info(
                    "WebSocket连接已创建",
                    exchange=exchange,
                    active_connections=self.active_connections[exchange]
                )
                
                return conn
                
            except Exception as e:
                self.logger.error("WebSocket连接创建失败", exchange=exchange, error=str(e))
                raise
        
        raise Exception(f"达到{exchange}最大连接数限制")
    
    async def release_connection(self, exchange: str, conn: websockets.WebSocketServerProtocol):
        """释放连接"""
        if exchange in self.pools and conn in self.pools[exchange]:
            if not conn.open:
                self.pools[exchange].remove(conn)
                self.active_connections[exchange] -= 1
    
    async def close_all(self):
        """关闭所有连接"""
        for exchange, pool in self.pools.items():
            for conn in pool:
                if conn.open:
                    await conn.close()
            pool.clear()
            self.active_connections[exchange] = 0
```

### 2. HTTP连接池优化
```python
# services/python-collector/src/marketprism_collector/connections/http_pool.py
import aiohttp
import asyncio
from typing import Dict, Optional
import structlog

class HTTPConnectionPool:
    """HTTP连接池管理器"""
    
    def __init__(self):
        self.sessions: Dict[str, aiohttp.ClientSession] = {}
        self.logger = structlog.get_logger(__name__)
        
    async def get_session(self, exchange: str) -> aiohttp.ClientSession:
        """获取HTTP会话"""
        if exchange not in self.sessions:
            # 优化的连接器配置
            connector = aiohttp.TCPConnector(
                limit=100,  # 总连接数限制
                limit_per_host=20,  # 每个主机连接数限制
                ttl_dns_cache=300,  # DNS缓存5分钟
                use_dns_cache=True,
                keepalive_timeout=30,
                enable_cleanup_closed=True
            )
            
            # 优化的超时配置
            timeout = aiohttp.ClientTimeout(
                total=30,
                connect=10,
                sock_read=10
            )
            
            session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={'User-Agent': 'MarketPrism/2.0'},
                raise_for_status=False
            )
            
            self.sessions[exchange] = session
            self.logger.info("HTTP会话已创建", exchange=exchange)
            
        return self.sessions[exchange]
    
    async def close_all(self):
        """关闭所有会话"""
        for exchange, session in self.sessions.items():
            await session.close()
            self.logger.info("HTTP会话已关闭", exchange=exchange)
        self.sessions.clear()
```

## 🚀 异步处理优化

### 1. 协程池管理
```python
# services/python-collector/src/marketprism_collector/async_utils/coroutine_pool.py
import asyncio
from typing import Callable, Any, List
import structlog

class CoroutinePool:
    """协程池管理器"""
    
    def __init__(self, max_workers: int = 50):
        self.max_workers = max_workers
        self.semaphore = asyncio.Semaphore(max_workers)
        self.active_tasks: List[asyncio.Task] = []
        self.logger = structlog.get_logger(__name__)
        
    async def submit(self, coro_func: Callable, *args, **kwargs) -> asyncio.Task:
        """提交协程任务"""
        async def wrapped_coro():
            async with self.semaphore:
                try:
                    return await coro_func(*args, **kwargs)
                except Exception as e:
                    self.logger.error("协程执行失败", error=str(e))
                    raise
                finally:
                    # 清理完成的任务
                    self.active_tasks = [t for t in self.active_tasks if not t.done()]
        
        task = asyncio.create_task(wrapped_coro())
        self.active_tasks.append(task)
        return task
    
    async def wait_all(self):
        """等待所有任务完成"""
        if self.active_tasks:
            await asyncio.gather(*self.active_tasks, return_exceptions=True)
            self.active_tasks.clear()
    
    def get_stats(self) -> dict:
        """获取池状态"""
        return {
            'max_workers': self.max_workers,
            'active_tasks': len(self.active_tasks),
            'available_workers': self.semaphore._value
        }
```

### 2. 异步队列优化
```python
# services/python-collector/src/marketprism_collector/async_utils/optimized_queue.py
import asyncio
from typing import TypeVar, Generic, Optional
import time

T = TypeVar('T')

class OptimizedAsyncQueue(Generic[T]):
    """优化的异步队列"""
    
    def __init__(self, maxsize: int = 1000):
        self.queue = asyncio.Queue(maxsize=maxsize)
        self.stats = {
            'total_put': 0,
            'total_get': 0,
            'total_dropped': 0,
            'last_put_time': 0,
            'last_get_time': 0
        }
        
    async def put_nowait_or_drop(self, item: T) -> bool:
        """非阻塞放入，满了就丢弃"""
        try:
            self.queue.put_nowait(item)
            self.stats['total_put'] += 1
            self.stats['last_put_time'] = time.time()
            return True
        except asyncio.QueueFull:
            self.stats['total_dropped'] += 1
            return False
    
    async def get_with_timeout(self, timeout: float = 1.0) -> Optional[T]:
        """带超时的获取"""
        try:
            item = await asyncio.wait_for(self.queue.get(), timeout=timeout)
            self.stats['total_get'] += 1
            self.stats['last_get_time'] = time.time()
            return item
        except asyncio.TimeoutError:
            return None
    
    def get_stats(self) -> dict:
        """获取队列统计"""
        return {
            **self.stats,
            'current_size': self.queue.qsize(),
            'max_size': self.queue.maxsize,
            'utilization': self.queue.qsize() / self.queue.maxsize * 100
        }
```

### 3. 事件循环优化
```python
# services/python-collector/src/marketprism_collector/async_utils/loop_optimizer.py
import asyncio
import uvloop  # 高性能事件循环
import structlog

class LoopOptimizer:
    """事件循环优化器"""
    
    @staticmethod
    def setup_optimized_loop():
        """设置优化的事件循环"""
        try:
            # 使用uvloop提升性能
            uvloop.install()
            logger = structlog.get_logger(__name__)
            logger.info("已启用uvloop高性能事件循环")
        except ImportError:
            logger.warning("uvloop不可用，使用默认事件循环")
    
    @staticmethod
    def configure_loop_policy():
        """配置循环策略"""
        # 设置事件循环策略
        if hasattr(asyncio, 'WindowsSelectorEventLoopPolicy'):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        # 获取当前循环
        loop = asyncio.get_event_loop()
        
        # 优化循环参数
        if hasattr(loop, 'set_debug'):
            loop.set_debug(False)  # 生产环境关闭调试
```

## 📊 性能监控和分析

### 1. 性能分析器
```python
# services/python-collector/src/marketprism_collector/monitoring/performance_analyzer.py
import time
import asyncio
from typing import Dict, List
import structlog
from dataclasses import dataclass

@dataclass
class PerformanceMetrics:
    """性能指标"""
    operation: str
    duration: float
    timestamp: float
    memory_before: float
    memory_after: float
    cpu_percent: float

class PerformanceAnalyzer:
    """性能分析器"""
    
    def __init__(self):
        self.metrics: List[PerformanceMetrics] = []
        self.logger = structlog.get_logger(__name__)
        
    async def profile_async(self, operation: str, coro):
        """分析异步操作性能"""
        import psutil
        process = psutil.Process()
        
        # 记录开始状态
        start_time = time.time()
        memory_before = process.memory_info().rss / 1024 / 1024
        cpu_before = process.cpu_percent()
        
        try:
            result = await coro
            return result
        finally:
            # 记录结束状态
            end_time = time.time()
            memory_after = process.memory_info().rss / 1024 / 1024
            cpu_after = process.cpu_percent()
            
            metrics = PerformanceMetrics(
                operation=operation,
                duration=end_time - start_time,
                timestamp=start_time,
                memory_before=memory_before,
                memory_after=memory_after,
                cpu_percent=(cpu_before + cpu_after) / 2
            )
            
            self.metrics.append(metrics)
            
            # 记录性能日志
            self.logger.info(
                "性能分析完成",
                operation=operation,
                duration_ms=metrics.duration * 1000,
                memory_delta_mb=memory_after - memory_before,
                cpu_percent=metrics.cpu_percent
            )
    
    def get_performance_summary(self) -> Dict:
        """获取性能摘要"""
        if not self.metrics:
            return {}
            
        operations = {}
        for metric in self.metrics:
            if metric.operation not in operations:
                operations[metric.operation] = []
            operations[metric.operation].append(metric.duration)
        
        summary = {}
        for op, durations in operations.items():
            summary[op] = {
                'count': len(durations),
                'avg_duration': sum(durations) / len(durations),
                'min_duration': min(durations),
                'max_duration': max(durations),
                'p95_duration': sorted(durations)[int(len(durations) * 0.95)]
            }
            
        return summary
```

## 🔧 实施计划

### 第一周：内存优化
- [ ] 实施内存监控和分析
- [ ] 添加对象池管理
- [ ] 优化数据结构使用__slots__
- [ ] 实施批量处理优化

### 第二周：连接池优化
- [ ] 实施WebSocket连接池
- [ ] 优化HTTP连接管理
- [ ] 添加连接健康检查
- [ ] 实施连接复用策略

### 第三周：异步处理优化
- [ ] 实施协程池管理
- [ ] 优化异步队列
- [ ] 配置高性能事件循环
- [ ] 添加异步性能监控

### 第四周：性能测试和调优
- [ ] 进行压力测试
- [ ] 性能基准测试
- [ ] 瓶颈分析和优化
- [ ] 文档更新和培训

## 📈 预期优化效果

### 性能提升
- **吞吐量**: 40.9 → 80+ msg/s (+95%)
- **内存使用**: 600MB → 400MB (-33%)
- **处理延迟**: P95 < 100ms (-50%)
- **连接稳定性**: 99.9%+ (+0.9%)

### 资源效率
- **CPU使用率**: 降低20%
- **内存碎片**: 减少40%
- **连接复用率**: 提升60%
- **错误率**: 降低至0.1%

---

## ✅ Python-Collector性能调优方案状态: **已制定完成**

**制定时间**: 2025-05-24  
**覆盖范围**: ✅ 全面  
**可执行性**: ✅ 高  
**预期效果**: ✅ 显著  

Python-Collector性能调优方案已制定完成，为企业级性能优化提供了完整的实施路径。 