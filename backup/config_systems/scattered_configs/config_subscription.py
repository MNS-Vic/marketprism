"""
MarketPrism 配置订阅系统
实现配置变更的订阅、过滤和推送机制
"""

import asyncio
import json
import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Set, Pattern
from dataclasses import dataclass, asdict
from enum import Enum
import re
import uuid
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
import fnmatch

from ..repositories.config_repository import ConfigRepository


class SubscriptionStatus(Enum):
    """订阅状态枚举"""
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    ERROR = "error"


class EventType(Enum):
    """事件类型枚举"""
    CONFIG_ADDED = "config_added"
    CONFIG_UPDATED = "config_updated"
    CONFIG_DELETED = "config_deleted"
    NAMESPACE_ADDED = "namespace_added"
    NAMESPACE_DELETED = "namespace_deleted"
    BATCH_UPDATE = "batch_update"


class FilterType(Enum):
    """过滤器类型枚举"""
    EXACT_MATCH = "exact_match"
    WILDCARD = "wildcard"
    REGEX = "regex"
    PREFIX = "prefix"
    SUFFIX = "suffix"
    CONTAINS = "contains"


@dataclass
class ConfigEvent:
    """配置事件"""
    event_id: str
    event_type: EventType
    namespace: str
    key: str
    old_value: Any
    new_value: Any
    timestamp: datetime
    source: str  # 事件来源
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'event_id': self.event_id,
            'event_type': self.event_type.value,
            'namespace': self.namespace,
            'key': self.key,
            'old_value': self.old_value,
            'new_value': self.new_value,
            'timestamp': self.timestamp.isoformat(),
            'source': self.source,
            'metadata': self.metadata
        }


@dataclass
class SubscriptionFilter:
    """订阅过滤器"""
    filter_type: FilterType
    pattern: str
    case_sensitive: bool = True
    
    def matches(self, value: str) -> bool:
        """检查值是否匹配过滤器"""
        if not self.case_sensitive:
            value = value.lower()
            pattern = self.pattern.lower()
        else:
            pattern = self.pattern
        
        if self.filter_type == FilterType.EXACT_MATCH:
            return value == pattern
        elif self.filter_type == FilterType.WILDCARD:
            return fnmatch.fnmatch(value, pattern)
        elif self.filter_type == FilterType.REGEX:
            return bool(re.match(pattern, value))
        elif self.filter_type == FilterType.PREFIX:
            return value.startswith(pattern)
        elif self.filter_type == FilterType.SUFFIX:
            return value.endswith(pattern)
        elif self.filter_type == FilterType.CONTAINS:
            return pattern in value
        else:
            return False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'filter_type': self.filter_type.value,
            'pattern': self.pattern,
            'case_sensitive': self.case_sensitive
        }


@dataclass
class Subscription:
    """配置订阅"""
    subscription_id: str
    client_id: str
    namespace_filters: List[SubscriptionFilter]
    key_filters: List[SubscriptionFilter]
    event_types: Set[EventType]
    callback: Optional[Callable[[ConfigEvent], None]]
    status: SubscriptionStatus
    created_at: datetime
    last_activity: datetime
    delivery_count: int = 0
    error_count: int = 0
    max_queue_size: int = 1000
    batch_size: int = 1
    batch_timeout: float = 1.0  # 秒
    
    def matches_event(self, event: ConfigEvent) -> bool:
        """检查事件是否匹配订阅"""
        # 检查事件类型
        if event.event_type not in self.event_types:
            return False
        
        # 检查命名空间过滤器
        if self.namespace_filters:
            namespace_match = any(f.matches(event.namespace) for f in self.namespace_filters)
            if not namespace_match:
                return False
        
        # 检查键过滤器
        if self.key_filters:
            key_match = any(f.matches(event.key) for f in self.key_filters)
            if not key_match:
                return False
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'subscription_id': self.subscription_id,
            'client_id': self.client_id,
            'namespace_filters': [f.to_dict() for f in self.namespace_filters],
            'key_filters': [f.to_dict() for f in self.key_filters],
            'event_types': [et.value for et in self.event_types],
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'last_activity': self.last_activity.isoformat(),
            'delivery_count': self.delivery_count,
            'error_count': self.error_count,
            'max_queue_size': self.max_queue_size,
            'batch_size': self.batch_size,
            'batch_timeout': self.batch_timeout
        }


@dataclass
class SubscriptionMetrics:
    """订阅指标"""
    total_subscriptions: int = 0
    active_subscriptions: int = 0
    paused_subscriptions: int = 0
    cancelled_subscriptions: int = 0
    total_events_generated: int = 0
    total_events_delivered: int = 0
    total_delivery_failures: int = 0
    average_delivery_time: float = 0.0
    events_per_second: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EventQueue:
    """事件队列"""
    
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self.queue = deque()
        self.lock = threading.RLock()
        self.not_empty = threading.Condition(self.lock)
        self.not_full = threading.Condition(self.lock)
    
    def put(self, event: ConfigEvent, timeout: Optional[float] = None) -> bool:
        """添加事件到队列"""
        with self.not_full:
            if len(self.queue) >= self.max_size:
                if timeout is None:
                    return False
                if not self.not_full.wait(timeout):
                    return False
            
            self.queue.append(event)
            self.not_empty.notify()
            return True
    
    def get(self, timeout: Optional[float] = None) -> Optional[ConfigEvent]:
        """从队列获取事件"""
        with self.not_empty:
            if not self.queue:
                if timeout is None:
                    return None
                if not self.not_empty.wait(timeout):
                    return None
            
            event = self.queue.popleft()
            self.not_full.notify()
            return event
    
    def get_batch(self, batch_size: int, timeout: float = 1.0) -> List[ConfigEvent]:
        """批量获取事件"""
        events = []
        start_time = time.time()
        
        while len(events) < batch_size and (time.time() - start_time) < timeout:
            remaining_timeout = timeout - (time.time() - start_time)
            if remaining_timeout <= 0:
                break
            
            event = self.get(remaining_timeout)
            if event:
                events.append(event)
            else:
                break
        
        return events
    
    def size(self) -> int:
        """获取队列大小"""
        with self.lock:
            return len(self.queue)
    
    def clear(self):
        """清空队列"""
        with self.lock:
            self.queue.clear()
            self.not_full.notify_all()


class ConfigSubscription:
    """
    配置订阅系统
    实现配置变更的订阅、过滤和推送机制
    """
    
    def __init__(
        self,
        config_repository: Optional[ConfigRepository] = None,
        max_subscriptions: int = 10000,
        max_events_per_second: int = 10000,
        event_retention_hours: int = 24,
        enable_batch_delivery: bool = True,
        worker_threads: int = 5
    ):
        """
        初始化配置订阅系统
        
        Args:
            config_repository: 配置仓库
            max_subscriptions: 最大订阅数
            max_events_per_second: 最大事件处理速率
            event_retention_hours: 事件保留时间（小时）
            enable_batch_delivery: 是否启用批量推送
            worker_threads: 工作线程数
        """
        self.config_repository = config_repository
        self.max_subscriptions = max_subscriptions
        self.max_events_per_second = max_events_per_second
        self.event_retention_hours = event_retention_hours
        self.enable_batch_delivery = enable_batch_delivery
        self.worker_threads = worker_threads
        
        # 订阅管理
        self.subscriptions: Dict[str, Subscription] = {}
        self.client_subscriptions: Dict[str, Set[str]] = defaultdict(set)
        self.subscription_lock = threading.RLock()
        
        # 事件管理
        self.event_queue = EventQueue()
        self.event_history: List[ConfigEvent] = []
        self.event_lock = threading.RLock()
        
        # 推送队列（每个订阅一个队列）
        self.delivery_queues: Dict[str, EventQueue] = {}
        
        # 指标
        self.metrics = SubscriptionMetrics()
        self.metrics_lock = threading.RLock()
        
        # 线程管理
        self.executor = ThreadPoolExecutor(max_workers=worker_threads)
        self.event_processor_thread = None
        self.delivery_threads: Dict[str, threading.Thread] = {}
        self.running = False
        
        # 速率限制
        self.event_timestamps = deque()
        
        self.logger = logging.getLogger(__name__)
        
        # 启动事件处理器
        self.start()
    
    def subscribe(
        self,
        client_id: str,
        namespace_patterns: List[str] = None,
        key_patterns: List[str] = None,
        event_types: List[EventType] = None,
        callback: Optional[Callable[[ConfigEvent], None]] = None,
        filter_type: FilterType = FilterType.WILDCARD,
        case_sensitive: bool = True,
        batch_size: int = 1,
        batch_timeout: float = 1.0,
        max_queue_size: int = 1000
    ) -> str:
        """
        创建配置订阅
        
        Args:
            client_id: 客户端ID
            namespace_patterns: 命名空间模式列表
            key_patterns: 键模式列表
            event_types: 事件类型列表
            callback: 事件回调函数
            filter_type: 过滤器类型
            case_sensitive: 是否区分大小写
            batch_size: 批量大小
            batch_timeout: 批量超时时间
            max_queue_size: 最大队列大小
            
        Returns:
            订阅ID
        """
        with self.subscription_lock:
            if len(self.subscriptions) >= self.max_subscriptions:
                raise RuntimeError(f"Maximum subscriptions limit reached: {self.max_subscriptions}")
            
            subscription_id = str(uuid.uuid4())
            
            # 创建命名空间过滤器
            namespace_filters = []
            if namespace_patterns:
                for pattern in namespace_patterns:
                    namespace_filters.append(SubscriptionFilter(
                        filter_type=filter_type,
                        pattern=pattern,
                        case_sensitive=case_sensitive
                    ))
            
            # 创建键过滤器
            key_filters = []
            if key_patterns:
                for pattern in key_patterns:
                    key_filters.append(SubscriptionFilter(
                        filter_type=filter_type,
                        pattern=pattern,
                        case_sensitive=case_sensitive
                    ))
            
            # 设置事件类型
            if event_types is None:
                event_types = {EventType.CONFIG_ADDED, EventType.CONFIG_UPDATED, EventType.CONFIG_DELETED}
            else:
                event_types = set(event_types)
            
            # 创建订阅
            subscription = Subscription(
                subscription_id=subscription_id,
                client_id=client_id,
                namespace_filters=namespace_filters,
                key_filters=key_filters,
                event_types=event_types,
                callback=callback,
                status=SubscriptionStatus.ACTIVE,
                created_at=datetime.now(),
                last_activity=datetime.now(),
                batch_size=batch_size,
                batch_timeout=batch_timeout,
                max_queue_size=max_queue_size
            )
            
            self.subscriptions[subscription_id] = subscription
            self.client_subscriptions[client_id].add(subscription_id)
            
            # 创建推送队列
            self.delivery_queues[subscription_id] = EventQueue(max_queue_size)
            
            # 启动推送线程
            self._start_delivery_thread(subscription_id)
            
            # 更新指标
            with self.metrics_lock:
                self.metrics.total_subscriptions += 1
                self.metrics.active_subscriptions += 1
            
            self.logger.info(f"Created subscription {subscription_id} for client {client_id}")
            return subscription_id
    
    def unsubscribe(self, subscription_id: str) -> bool:
        """
        取消订阅
        
        Args:
            subscription_id: 订阅ID
            
        Returns:
            是否成功
        """
        with self.subscription_lock:
            subscription = self.subscriptions.get(subscription_id)
            if not subscription:
                return False
            
            # 更新订阅状态
            subscription.status = SubscriptionStatus.CANCELLED
            
            # 从客户端订阅集合中移除
            self.client_subscriptions[subscription.client_id].discard(subscription_id)
            
            # 停止推送线程
            self._stop_delivery_thread(subscription_id)
            
            # 清理推送队列
            if subscription_id in self.delivery_queues:
                self.delivery_queues[subscription_id].clear()
                del self.delivery_queues[subscription_id]
            
            # 移除订阅
            del self.subscriptions[subscription_id]
            
            # 更新指标
            with self.metrics_lock:
                self.metrics.active_subscriptions -= 1
                self.metrics.cancelled_subscriptions += 1
            
            self.logger.info(f"Cancelled subscription {subscription_id}")
            return True
    
    def pause_subscription(self, subscription_id: str) -> bool:
        """
        暂停订阅
        
        Args:
            subscription_id: 订阅ID
            
        Returns:
            是否成功
        """
        with self.subscription_lock:
            subscription = self.subscriptions.get(subscription_id)
            if not subscription or subscription.status != SubscriptionStatus.ACTIVE:
                return False
            
            subscription.status = SubscriptionStatus.PAUSED
            
            # 更新指标
            with self.metrics_lock:
                self.metrics.active_subscriptions -= 1
                self.metrics.paused_subscriptions += 1
            
            self.logger.info(f"Paused subscription {subscription_id}")
            return True
    
    def resume_subscription(self, subscription_id: str) -> bool:
        """
        恢复订阅
        
        Args:
            subscription_id: 订阅ID
            
        Returns:
            是否成功
        """
        with self.subscription_lock:
            subscription = self.subscriptions.get(subscription_id)
            if not subscription or subscription.status != SubscriptionStatus.PAUSED:
                return False
            
            subscription.status = SubscriptionStatus.ACTIVE
            
            # 更新指标
            with self.metrics_lock:
                self.metrics.paused_subscriptions -= 1
                self.metrics.active_subscriptions += 1
            
            self.logger.info(f"Resumed subscription {subscription_id}")
            return True
    
    def list_subscriptions(self, client_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        列出订阅
        
        Args:
            client_id: 客户端ID（可选）
            
        Returns:
            订阅列表
        """
        with self.subscription_lock:
            if client_id:
                subscription_ids = self.client_subscriptions.get(client_id, set())
                subscriptions = [self.subscriptions[sid] for sid in subscription_ids if sid in self.subscriptions]
            else:
                subscriptions = list(self.subscriptions.values())
            
            return [sub.to_dict() for sub in subscriptions]
    
    def publish_event(
        self,
        event_type: EventType,
        namespace: str,
        key: str,
        old_value: Any = None,
        new_value: Any = None,
        source: str = "system",
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        发布配置事件
        
        Args:
            event_type: 事件类型
            namespace: 命名空间
            key: 配置键
            old_value: 旧值
            new_value: 新值
            source: 事件源
            metadata: 元数据
            
        Returns:
            事件ID
        """
        # 速率限制检查
        if not self._check_rate_limit():
            self.logger.warning("Event rate limit exceeded, dropping event")
            return ""
        
        event_id = str(uuid.uuid4())
        event = ConfigEvent(
            event_id=event_id,
            event_type=event_type,
            namespace=namespace,
            key=key,
            old_value=old_value,
            new_value=new_value,
            timestamp=datetime.now(),
            source=source,
            metadata=metadata or {}
        )
        
        # 添加到事件队列
        if not self.event_queue.put(event, timeout=1.0):
            self.logger.warning(f"Failed to queue event {event_id}, queue is full")
            return ""
        
        # 更新指标
        with self.metrics_lock:
            self.metrics.total_events_generated += 1
        
        self.logger.debug(f"Published event {event_id}: {event_type.value} for {namespace}.{key}")
        return event_id
    
    def get_subscription_info(self, subscription_id: str) -> Optional[Dict[str, Any]]:
        """获取订阅信息"""
        with self.subscription_lock:
            subscription = self.subscriptions.get(subscription_id)
            if subscription:
                info = subscription.to_dict()
                # 添加队列信息
                queue = self.delivery_queues.get(subscription_id)
                if queue:
                    info['queue_size'] = queue.size()
                return info
            return None
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取订阅指标"""
        with self.metrics_lock:
            metrics = self.metrics.to_dict()
            
            # 添加实时统计
            metrics['queue_size'] = self.event_queue.size()
            metrics['event_history_size'] = len(self.event_history)
            
            # 计算事件处理速率
            now = time.time()
            recent_events = [ts for ts in self.event_timestamps if now - ts < 60]  # 最近1分钟
            metrics['events_per_minute'] = len(recent_events)
            
            return metrics
    
    def get_event_history(
        self,
        limit: int = 100,
        since: Optional[datetime] = None,
        event_types: Optional[List[EventType]] = None,
        namespace: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        获取事件历史
        
        Args:
            limit: 限制数量
            since: 起始时间
            event_types: 事件类型过滤
            namespace: 命名空间过滤
            
        Returns:
            事件历史列表
        """
        with self.event_lock:
            events = self.event_history.copy()
        
        # 过滤事件
        if since:
            events = [e for e in events if e.timestamp >= since]
        
        if event_types:
            event_type_set = set(event_types)
            events = [e for e in events if e.event_type in event_type_set]
        
        if namespace:
            events = [e for e in events if e.namespace == namespace]
        
        # 按时间倒序排列并限制数量
        events.sort(key=lambda e: e.timestamp, reverse=True)
        events = events[:limit]
        
        return [event.to_dict() for event in events]
    
    def _check_rate_limit(self) -> bool:
        """检查速率限制"""
        now = time.time()
        
        # 清理旧的时间戳
        while self.event_timestamps and now - self.event_timestamps[0] > 1.0:
            self.event_timestamps.popleft()
        
        # 检查速率
        if len(self.event_timestamps) >= self.max_events_per_second:
            return False
        
        self.event_timestamps.append(now)
        return True
    
    def _process_events(self):
        """事件处理器"""
        while self.running:
            try:
                event = self.event_queue.get(timeout=1.0)
                if not event:
                    continue
                
                # 添加到历史记录
                with self.event_lock:
                    self.event_history.append(event)
                    # 清理过期事件
                    cutoff_time = datetime.now() - timedelta(hours=self.event_retention_hours)
                    self.event_history = [e for e in self.event_history if e.timestamp >= cutoff_time]
                
                # 分发事件到匹配的订阅
                self._distribute_event(event)
                
            except Exception as e:
                self.logger.error(f"Error processing event: {e}")
    
    def _distribute_event(self, event: ConfigEvent):
        """分发事件到订阅"""
        with self.subscription_lock:
            for subscription_id, subscription in self.subscriptions.items():
                if subscription.status != SubscriptionStatus.ACTIVE:
                    continue
                
                if subscription.matches_event(event):
                    # 添加到推送队列
                    queue = self.delivery_queues.get(subscription_id)
                    if queue:
                        if not queue.put(event, timeout=0.1):
                            self.logger.warning(f"Failed to queue event for subscription {subscription_id}")
                            subscription.error_count += 1
    
    def _start_delivery_thread(self, subscription_id: str):
        """启动推送线程"""
        def delivery_worker():
            subscription = self.subscriptions.get(subscription_id)
            queue = self.delivery_queues.get(subscription_id)
            
            if not subscription or not queue:
                return
            
            while subscription_id in self.subscriptions and self.running:
                try:
                    if subscription.status != SubscriptionStatus.ACTIVE:
                        time.sleep(1.0)
                        continue
                    
                    if self.enable_batch_delivery and subscription.batch_size > 1:
                        # 批量推送
                        events = queue.get_batch(subscription.batch_size, subscription.batch_timeout)
                        if events:
                            self._deliver_events_batch(subscription, events)
                    else:
                        # 单个推送
                        event = queue.get(timeout=1.0)
                        if event:
                            self._deliver_event(subscription, event)
                
                except Exception as e:
                    self.logger.error(f"Error in delivery thread for subscription {subscription_id}: {e}")
                    subscription.error_count += 1
                    time.sleep(1.0)
        
        thread = threading.Thread(target=delivery_worker, daemon=True)
        thread.start()
        self.delivery_threads[subscription_id] = thread
    
    def _stop_delivery_thread(self, subscription_id: str):
        """停止推送线程"""
        thread = self.delivery_threads.pop(subscription_id, None)
        if thread and thread.is_alive():
            # 线程会在下次循环时自动退出
            pass
    
    def _deliver_event(self, subscription: Subscription, event: ConfigEvent):
        """推送单个事件"""
        start_time = time.time()
        
        try:
            if subscription.callback:
                subscription.callback(event)
            
            subscription.delivery_count += 1
            subscription.last_activity = datetime.now()
            
            # 更新指标
            delivery_time = time.time() - start_time
            with self.metrics_lock:
                self.metrics.total_events_delivered += 1
                self._update_average_delivery_time(delivery_time)
            
        except Exception as e:
            subscription.error_count += 1
            with self.metrics_lock:
                self.metrics.total_delivery_failures += 1
            self.logger.error(f"Failed to deliver event {event.event_id} to subscription {subscription.subscription_id}: {e}")
    
    def _deliver_events_batch(self, subscription: Subscription, events: List[ConfigEvent]):
        """批量推送事件"""
        start_time = time.time()
        
        try:
            if subscription.callback:
                # 创建批量事件
                batch_event = ConfigEvent(
                    event_id=str(uuid.uuid4()),
                    event_type=EventType.BATCH_UPDATE,
                    namespace="batch",
                    key="batch",
                    old_value=None,
                    new_value=[event.to_dict() for event in events],
                    timestamp=datetime.now(),
                    source="subscription_system",
                    metadata={'batch_size': len(events)}
                )
                
                subscription.callback(batch_event)
            
            subscription.delivery_count += len(events)
            subscription.last_activity = datetime.now()
            
            # 更新指标
            delivery_time = time.time() - start_time
            with self.metrics_lock:
                self.metrics.total_events_delivered += len(events)
                self._update_average_delivery_time(delivery_time)
            
        except Exception as e:
            subscription.error_count += 1
            with self.metrics_lock:
                self.metrics.total_delivery_failures += len(events)
            self.logger.error(f"Failed to deliver batch events to subscription {subscription.subscription_id}: {e}")
    
    def _update_average_delivery_time(self, delivery_time: float):
        """更新平均推送时间"""
        if self.metrics.total_events_delivered > 0:
            total_time = self.metrics.average_delivery_time * (self.metrics.total_events_delivered - 1)
            self.metrics.average_delivery_time = (total_time + delivery_time) / self.metrics.total_events_delivered
        else:
            self.metrics.average_delivery_time = delivery_time
    
    def start(self):
        """启动订阅系统"""
        if self.running:
            return
        
        self.running = True
        
        # 启动事件处理器
        self.event_processor_thread = threading.Thread(target=self._process_events, daemon=True)
        self.event_processor_thread.start()
        
        self.logger.info("ConfigSubscription started")
    
    def stop(self):
        """停止订阅系统"""
        self.running = False
        
        # 等待事件处理器停止
        if self.event_processor_thread and self.event_processor_thread.is_alive():
            self.event_processor_thread.join(timeout=5.0)
        
        # 停止所有推送线程
        for subscription_id in list(self.delivery_threads.keys()):
            self._stop_delivery_thread(subscription_id)
        
        # 关闭线程池
        self.executor.shutdown(wait=True)
        
        self.logger.info("ConfigSubscription stopped")