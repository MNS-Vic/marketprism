"""
MarketPrism 配置客户端
实现分布式配置的客户端SDK，支持HTTP和WebSocket通信
"""

import asyncio
import json
import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, asdict
from enum import Enum
import hashlib
import os
import pickle
from pathlib import Path

try:
    import requests
    import websockets
    from websockets.client import WebSocketClientProtocol
    REQUESTS_AVAILABLE = True
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    requests = None
    websockets = None
    WebSocketClientProtocol = None
    REQUESTS_AVAILABLE = False
    WEBSOCKETS_AVAILABLE = False


class ClientStatus(Enum):
    """客户端状态枚举"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class CacheLevel(Enum):
    """缓存级别枚举"""
    MEMORY_ONLY = "memory_only"
    MEMORY_AND_DISK = "memory_and_disk"
    DISK_ONLY = "disk_only"
    NO_CACHE = "no_cache"


@dataclass
class ConfigChangeEvent:
    """配置变更事件"""
    namespace: str
    key: str
    value: Any
    action: str  # 'updated', 'deleted', 'added'
    timestamp: datetime
    version: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'namespace': self.namespace,
            'key': self.key,
            'value': self.value,
            'action': self.action,
            'timestamp': self.timestamp.isoformat(),
            'version': self.version
        }


@dataclass
class ClientMetrics:
    """客户端指标"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    reconnection_count: int = 0
    config_changes_received: int = 0
    average_response_time: float = 0.0
    last_sync_time: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        if self.last_sync_time:
            result['last_sync_time'] = self.last_sync_time.isoformat()
        return result


class ConfigCache:
    """配置缓存管理器"""
    
    def __init__(
        self,
        cache_level: CacheLevel = CacheLevel.MEMORY_AND_DISK,
        cache_dir: Optional[str] = None,
        max_memory_size: int = 1000,
        ttl_seconds: int = 3600
    ):
        self.cache_level = cache_level
        self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / '.marketprism' / 'config_cache'
        self.max_memory_size = max_memory_size
        self.ttl_seconds = ttl_seconds
        
        # 内存缓存
        self.memory_cache: Dict[str, Any] = {}
        self.cache_timestamps: Dict[str, datetime] = {}
        self.cache_lock = threading.RLock()
        
        # 确保缓存目录存在
        if self.cache_level in [CacheLevel.MEMORY_AND_DISK, CacheLevel.DISK_ONLY]:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger(__name__)
    
    def get(self, key: str) -> Optional[Any]:
        """从缓存获取配置"""
        with self.cache_lock:
            # 检查内存缓存
            if self.cache_level in [CacheLevel.MEMORY_ONLY, CacheLevel.MEMORY_AND_DISK]:
                if key in self.memory_cache:
                    # 检查TTL
                    if self._is_cache_valid(key):
                        return self.memory_cache[key]
                    else:
                        # 过期，清理
                        self.memory_cache.pop(key, None)
                        self.cache_timestamps.pop(key, None)
            
            # 检查磁盘缓存
            if self.cache_level in [CacheLevel.MEMORY_AND_DISK, CacheLevel.DISK_ONLY]:
                return self._get_from_disk(key)
            
            return None
    
    def set(self, key: str, value: Any):
        """设置缓存"""
        with self.cache_lock:
            current_time = datetime.now()
            
            # 设置内存缓存
            if self.cache_level in [CacheLevel.MEMORY_ONLY, CacheLevel.MEMORY_AND_DISK]:
                # 检查内存大小限制
                if len(self.memory_cache) >= self.max_memory_size:
                    self._evict_oldest_memory_cache()
                
                self.memory_cache[key] = value
                self.cache_timestamps[key] = current_time
            
            # 设置磁盘缓存
            if self.cache_level in [CacheLevel.MEMORY_AND_DISK, CacheLevel.DISK_ONLY]:
                self._set_to_disk(key, value, current_time)
    
    def delete(self, key: str):
        """删除缓存"""
        with self.cache_lock:
            # 删除内存缓存
            self.memory_cache.pop(key, None)
            self.cache_timestamps.pop(key, None)
            
            # 删除磁盘缓存
            if self.cache_level in [CacheLevel.MEMORY_AND_DISK, CacheLevel.DISK_ONLY]:
                cache_file = self.cache_dir / f"{self._hash_key(key)}.cache"
                if cache_file.exists():
                    try:
                        cache_file.unlink()
                    except Exception as e:
                        self.logger.warning(f"Failed to delete cache file {cache_file}: {e}")
    
    def clear(self):
        """清空所有缓存"""
        with self.cache_lock:
            # 清空内存缓存
            self.memory_cache.clear()
            self.cache_timestamps.clear()
            
            # 清空磁盘缓存
            if self.cache_level in [CacheLevel.MEMORY_AND_DISK, CacheLevel.DISK_ONLY]:
                try:
                    for cache_file in self.cache_dir.glob("*.cache"):
                        cache_file.unlink()
                except Exception as e:
                    self.logger.warning(f"Failed to clear disk cache: {e}")
    
    def _is_cache_valid(self, key: str) -> bool:
        """检查缓存是否有效"""
        if key not in self.cache_timestamps:
            return False
        
        cache_time = self.cache_timestamps[key]
        return (datetime.now() - cache_time).total_seconds() < self.ttl_seconds
    
    def _evict_oldest_memory_cache(self):
        """清理最旧的内存缓存"""
        if not self.cache_timestamps:
            return
        
        oldest_key = min(self.cache_timestamps.keys(), key=lambda k: self.cache_timestamps[k])
        self.memory_cache.pop(oldest_key, None)
        self.cache_timestamps.pop(oldest_key, None)
    
    def _hash_key(self, key: str) -> str:
        """生成键的哈希值"""
        return hashlib.md5(key.encode()).hexdigest()
    
    def _get_from_disk(self, key: str) -> Optional[Any]:
        """从磁盘获取缓存"""
        cache_file = self.cache_dir / f"{self._hash_key(key)}.cache"
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'rb') as f:
                cache_data = pickle.load(f)
            
            # 检查TTL
            cache_time = cache_data.get('timestamp')
            if cache_time and (datetime.now() - cache_time).total_seconds() < self.ttl_seconds:
                return cache_data.get('value')
            else:
                # 过期，删除文件
                cache_file.unlink()
                return None
                
        except Exception as e:
            self.logger.warning(f"Failed to read cache file {cache_file}: {e}")
            return None
    
    def _set_to_disk(self, key: str, value: Any, timestamp: datetime):
        """设置磁盘缓存"""
        cache_file = self.cache_dir / f"{self._hash_key(key)}.cache"
        
        try:
            cache_data = {
                'key': key,
                'value': value,
                'timestamp': timestamp
            }
            
            with open(cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
                
        except Exception as e:
            self.logger.warning(f"Failed to write cache file {cache_file}: {e}")


class ConfigClient:
    """
    配置客户端
    提供分布式配置的客户端SDK，支持HTTP和WebSocket通信
    """
    
    def __init__(
        self,
        server_url: str = "http://localhost:8080",
        websocket_url: str = "ws://localhost:8081",
        client_id: Optional[str] = None,
        token: Optional[str] = None,
        cache_level: CacheLevel = CacheLevel.MEMORY_AND_DISK,
        cache_dir: Optional[str] = None,
        auto_reconnect: bool = True,
        reconnect_interval: int = 5,
        request_timeout: int = 30,
        heartbeat_interval: int = 30
    ):
        """
        初始化配置客户端
        
        Args:
            server_url: 配置服务器HTTP URL
            websocket_url: 配置服务器WebSocket URL
            client_id: 客户端ID
            token: 访问令牌
            cache_level: 缓存级别
            cache_dir: 缓存目录
            auto_reconnect: 是否自动重连
            reconnect_interval: 重连间隔（秒）
            request_timeout: 请求超时（秒）
            heartbeat_interval: 心跳间隔（秒）
        """
        self.server_url = server_url.rstrip('/')
        self.websocket_url = websocket_url
        self.client_id = client_id or self._generate_client_id()
        self.token = token
        self.auto_reconnect = auto_reconnect
        self.reconnect_interval = reconnect_interval
        self.request_timeout = request_timeout
        self.heartbeat_interval = heartbeat_interval
        
        # 状态管理
        self.status = ClientStatus.DISCONNECTED
        self.last_error = None
        
        # 缓存管理
        self.cache = ConfigCache(cache_level, cache_dir)
        
        # 指标
        self.metrics = ClientMetrics()
        
        # WebSocket连接
        self.websocket = None
        self.websocket_task = None
        self.heartbeat_task = None
        
        # 订阅管理
        self.subscriptions: Dict[str, List[Callable]] = {}
        self.subscription_lock = threading.RLock()
        
        # HTTP会话
        if REQUESTS_AVAILABLE:
            self.session = requests.Session()
            if self.token:
                self.session.headers.update({'Authorization': f'Bearer {self.token}'})
        else:
            self.session = None
        
        # 线程管理
        self.event_loop = None
        self.websocket_thread = None
        
        self.logger = logging.getLogger(__name__)
    
    def _generate_client_id(self) -> str:
        """生成客户端ID"""
        timestamp = str(int(time.time() * 1000))
        random_str = hashlib.md5(f"{timestamp}{os.getpid()}".encode()).hexdigest()[:8]
        return f"client_{timestamp}_{random_str}"
    
    def authenticate(self, client_id: Optional[str] = None) -> str:
        """获取访问令牌"""
        if not REQUESTS_AVAILABLE:
            raise ImportError("requests is required for authentication")
        
        auth_data = {
            'client_id': client_id or self.client_id
        }
        
        try:
            response = self.session.post(
                f"{self.server_url}/api/v1/auth/token",
                json=auth_data,
                timeout=self.request_timeout
            )
            response.raise_for_status()
            
            token_data = response.json()
            self.token = token_data['token']
            self.session.headers.update({'Authorization': f'Bearer {self.token}'})
            
            self.logger.info(f"Authentication successful for client {self.client_id}")
            return self.token
            
        except Exception as e:
            self.logger.error(f"Authentication failed: {e}")
            raise
    
    def get_config(
        self,
        namespace: str,
        key: str,
        default: Any = None,
        use_cache: bool = True
    ) -> Any:
        """
        获取配置值
        
        Args:
            namespace: 命名空间
            key: 配置键
            default: 默认值
            use_cache: 是否使用缓存
            
        Returns:
            配置值
        """
        cache_key = f"{namespace}.{key}"
        
        # 尝试从缓存获取
        if use_cache:
            cached_value = self.cache.get(cache_key)
            if cached_value is not None:
                self.metrics.cache_hits += 1
                return cached_value
            else:
                self.metrics.cache_misses += 1
        
        # 从服务器获取
        if not REQUESTS_AVAILABLE:
            self.logger.warning("requests not available, returning cached value or default")
            return default
        
        try:
            start_time = time.time()
            
            response = self.session.get(
                f"{self.server_url}/api/v1/config/{namespace}/{key}",
                timeout=self.request_timeout
            )
            
            response_time = time.time() - start_time
            self._update_response_time(response_time)
            
            if response.status_code == 200:
                data = response.json()
                value = data.get('value', default)
                
                # 更新缓存
                if use_cache:
                    self.cache.set(cache_key, value)
                
                self.metrics.successful_requests += 1
                return value
            
            elif response.status_code == 404:
                # 配置不存在，返回默认值
                self.metrics.successful_requests += 1
                return default
            
            else:
                response.raise_for_status()
                
        except Exception as e:
            self.metrics.failed_requests += 1
            self.last_error = str(e)
            self.logger.error(f"Error getting config {namespace}.{key}: {e}")
            
            # 尝试从缓存获取
            if use_cache:
                cached_value = self.cache.get(cache_key)
                if cached_value is not None:
                    self.logger.info(f"Returning cached value for {namespace}.{key}")
                    return cached_value
            
            return default
    
    def set_config(
        self,
        namespace: str,
        key: str,
        value: Any,
        comment: Optional[str] = None
    ) -> bool:
        """
        设置配置值
        
        Args:
            namespace: 命名空间
            key: 配置键
            value: 配置值
            comment: 提交注释
            
        Returns:
            是否成功
        """
        if not REQUESTS_AVAILABLE:
            self.logger.error("requests not available for setting config")
            return False
        
        try:
            start_time = time.time()
            
            data = {
                'value': value,
                'comment': comment or f'Update {namespace}.{key}'
            }
            
            response = self.session.post(
                f"{self.server_url}/api/v1/config/{namespace}/{key}",
                json=data,
                timeout=self.request_timeout
            )
            
            response_time = time.time() - start_time
            self._update_response_time(response_time)
            
            response.raise_for_status()
            
            # 更新本地缓存
            cache_key = f"{namespace}.{key}"
            self.cache.set(cache_key, value)
            
            self.metrics.successful_requests += 1
            return True
            
        except Exception as e:
            self.metrics.failed_requests += 1
            self.last_error = str(e)
            self.logger.error(f"Error setting config {namespace}.{key}: {e}")
            return False
    
    def delete_config(self, namespace: str, key: str) -> bool:
        """
        删除配置
        
        Args:
            namespace: 命名空间
            key: 配置键
            
        Returns:
            是否成功
        """
        if not REQUESTS_AVAILABLE:
            self.logger.error("requests not available for deleting config")
            return False
        
        try:
            start_time = time.time()
            
            response = self.session.delete(
                f"{self.server_url}/api/v1/config/{namespace}/{key}",
                timeout=self.request_timeout
            )
            
            response_time = time.time() - start_time
            self._update_response_time(response_time)
            
            response.raise_for_status()
            
            # 删除本地缓存
            cache_key = f"{namespace}.{key}"
            self.cache.delete(cache_key)
            
            self.metrics.successful_requests += 1
            return True
            
        except Exception as e:
            self.metrics.failed_requests += 1
            self.last_error = str(e)
            self.logger.error(f"Error deleting config {namespace}.{key}: {e}")
            return False
    
    def list_configs(
        self,
        namespace: str,
        pattern: str = "*"
    ) -> Dict[str, Any]:
        """
        列出命名空间下的配置
        
        Args:
            namespace: 命名空间
            pattern: 匹配模式
            
        Returns:
            配置字典
        """
        if not REQUESTS_AVAILABLE:
            self.logger.error("requests not available for listing configs")
            return {}
        
        try:
            start_time = time.time()
            
            params = {'pattern': pattern} if pattern != "*" else {}
            
            response = self.session.get(
                f"{self.server_url}/api/v1/config/{namespace}/list",
                params=params,
                timeout=self.request_timeout
            )
            
            response_time = time.time() - start_time
            self._update_response_time(response_time)
            
            response.raise_for_status()
            
            data = response.json()
            configs = data.get('configs', {})
            
            # 更新缓存
            for config_key, config_value in configs.items():
                cache_key = f"{namespace}.{config_key}"
                self.cache.set(cache_key, config_value)
            
            self.metrics.successful_requests += 1
            return configs
            
        except Exception as e:
            self.metrics.failed_requests += 1
            self.last_error = str(e)
            self.logger.error(f"Error listing configs for namespace {namespace}: {e}")
            return {}
    
    def subscribe_changes(
        self,
        namespace: str,
        callback: Callable[[ConfigChangeEvent], None]
    ) -> str:
        """
        订阅配置变更
        
        Args:
            namespace: 命名空间
            callback: 变更回调函数
            
        Returns:
            订阅ID
        """
        subscription_id = f"sub_{int(time.time() * 1000)}_{len(self.subscriptions)}"
        
        with self.subscription_lock:
            if namespace not in self.subscriptions:
                self.subscriptions[namespace] = []
            
            self.subscriptions[namespace].append(callback)
        
        # 启动WebSocket连接（如果尚未连接）
        if self.status == ClientStatus.DISCONNECTED:
            self._start_websocket_connection()
        
        # 发送订阅请求
        if self.websocket and self.status == ClientStatus.CONNECTED:
            asyncio.create_task(self._send_subscribe_message(namespace))
        
        self.logger.info(f"Subscribed to namespace {namespace} with ID {subscription_id}")
        return subscription_id
    
    def unsubscribe_changes(self, namespace: str):
        """取消订阅配置变更"""
        with self.subscription_lock:
            if namespace in self.subscriptions:
                del self.subscriptions[namespace]
        
        # 发送取消订阅请求
        if self.websocket and self.status == ClientStatus.CONNECTED:
            asyncio.create_task(self._send_unsubscribe_message(namespace))
        
        self.logger.info(f"Unsubscribed from namespace {namespace}")
    
    def _start_websocket_connection(self):
        """启动WebSocket连接"""
        if not WEBSOCKETS_AVAILABLE:
            self.logger.warning("websockets not available for real-time updates")
            return
        
        if self.websocket_thread and self.websocket_thread.is_alive():
            return
        
        def run_websocket():
            self.event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.event_loop)
            self.event_loop.run_until_complete(self._websocket_handler())
        
        self.websocket_thread = threading.Thread(target=run_websocket, daemon=True)
        self.websocket_thread.start()
    
    async def _websocket_handler(self):
        """WebSocket处理器"""
        while True:
            try:
                self.status = ClientStatus.CONNECTING
                
                headers = {}
                if self.token:
                    headers['Authorization'] = f'Bearer {self.token}'
                
                async with websockets.connect(
                    self.websocket_url,
                    extra_headers=headers
                ) as websocket:
                    self.websocket = websocket
                    self.status = ClientStatus.CONNECTED
                    self.logger.info("WebSocket connected")
                    
                    # 启动心跳
                    self.heartbeat_task = asyncio.create_task(self._heartbeat_handler())
                    
                    # 重新订阅
                    await self._resubscribe_all()
                    
                    # 处理消息
                    async for message in websocket:
                        try:
                            data = json.loads(message)
                            await self._handle_websocket_message(data)
                        except json.JSONDecodeError:
                            self.logger.warning(f"Invalid JSON message: {message}")
                        except Exception as e:
                            self.logger.error(f"Error handling WebSocket message: {e}")
            
            except Exception as e:
                self.status = ClientStatus.ERROR
                self.last_error = str(e)
                self.logger.error(f"WebSocket connection error: {e}")
                
                if self.heartbeat_task:
                    self.heartbeat_task.cancel()
                
                if not self.auto_reconnect:
                    break
                
                self.status = ClientStatus.RECONNECTING
                self.metrics.reconnection_count += 1
                self.logger.info(f"Reconnecting in {self.reconnect_interval} seconds...")
                await asyncio.sleep(self.reconnect_interval)
    
    async def _heartbeat_handler(self):
        """心跳处理器"""
        while self.status == ClientStatus.CONNECTED:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                
                if self.websocket:
                    heartbeat_message = {
                        'type': 'heartbeat',
                        'client_id': self.client_id,
                        'timestamp': datetime.now().isoformat()
                    }
                    await self.websocket.send(json.dumps(heartbeat_message))
                
            except Exception as e:
                self.logger.error(f"Heartbeat error: {e}")
                break
    
    async def _resubscribe_all(self):
        """重新订阅所有命名空间"""
        with self.subscription_lock:
            for namespace in self.subscriptions.keys():
                await self._send_subscribe_message(namespace)
    
    async def _send_subscribe_message(self, namespace: str):
        """发送订阅消息"""
        if self.websocket:
            message = {
                'type': 'subscribe',
                'namespace': namespace,
                'client_id': self.client_id
            }
            await self.websocket.send(json.dumps(message))
    
    async def _send_unsubscribe_message(self, namespace: str):
        """发送取消订阅消息"""
        if self.websocket:
            message = {
                'type': 'unsubscribe',
                'namespace': namespace,
                'client_id': self.client_id
            }
            await self.websocket.send(json.dumps(message))
    
    async def _handle_websocket_message(self, data: Dict[str, Any]):
        """处理WebSocket消息"""
        message_type = data.get('type')
        
        if message_type == 'welcome':
            self.logger.info(f"Received welcome message: {data}")
        
        elif message_type == 'config_change':
            # 配置变更通知
            namespace = data.get('namespace')
            key = data.get('key')
            value = data.get('value')
            action = data.get('action')
            timestamp_str = data.get('timestamp')
            version = data.get('version')
            
            if namespace and key:
                timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.now()
                
                event = ConfigChangeEvent(
                    namespace=namespace,
                    key=key,
                    value=value,
                    action=action,
                    timestamp=timestamp,
                    version=version
                )
                
                # 更新本地缓存
                cache_key = f"{namespace}.{key}"
                if action == 'deleted':
                    self.cache.delete(cache_key)
                else:
                    self.cache.set(cache_key, value)
                
                # 调用回调函数
                with self.subscription_lock:
                    callbacks = self.subscriptions.get(namespace, [])
                    for callback in callbacks:
                        try:
                            callback(event)
                        except Exception as e:
                            self.logger.error(f"Error in config change callback: {e}")
                
                self.metrics.config_changes_received += 1
        
        elif message_type == 'subscription_confirmed':
            namespace = data.get('namespace')
            self.logger.info(f"Subscription confirmed for namespace: {namespace}")
        
        elif message_type == 'unsubscription_confirmed':
            namespace = data.get('namespace')
            self.logger.info(f"Unsubscription confirmed for namespace: {namespace}")
        
        elif message_type == 'heartbeat_ack':
            # 心跳确认
            pass
        
        elif message_type == 'error':
            error_message = data.get('message', 'Unknown error')
            self.logger.error(f"Server error: {error_message}")
    
    def _update_response_time(self, response_time: float):
        """更新平均响应时间"""
        if self.metrics.successful_requests > 0:
            total_time = self.metrics.average_response_time * (self.metrics.successful_requests - 1)
            self.metrics.average_response_time = (total_time + response_time) / self.metrics.successful_requests
        else:
            self.metrics.average_response_time = response_time
    
    def get_client_info(self) -> Dict[str, Any]:
        """获取客户端信息"""
        return {
            'client_id': self.client_id,
            'status': self.status.value,
            'server_url': self.server_url,
            'websocket_url': self.websocket_url,
            'last_error': self.last_error,
            'metrics': self.metrics.to_dict(),
            'subscriptions': list(self.subscriptions.keys()),
            'cache_level': self.cache.cache_level.value,
            'auto_reconnect': self.auto_reconnect
        }
    
    def close(self):
        """关闭客户端连接"""
        self.status = ClientStatus.DISCONNECTED
        
        # 关闭WebSocket连接
        if self.websocket:
            asyncio.create_task(self.websocket.close())
        
        # 停止事件循环
        if self.event_loop and self.event_loop.is_running():
            self.event_loop.stop()
        
        # 关闭HTTP会话
        if self.session:
            self.session.close()
        
        self.logger.info("ConfigClient closed")