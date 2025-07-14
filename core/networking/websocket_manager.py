"""
统一WebSocket连接管理器

基于成功连接的模式，提供：
- 统一的WebSocket连接逻辑
- 自动代理检测和配置
- SSL/TLS灵活配置
- 连接重试和恢复
- aiohttp和websockets库兼容性
- 交易所特定的连接管理（Binance/OKX）
- 连接状态监控和健康检查
- 自动重连和订阅恢复
- 多数据类型订阅和分发支持（新增）
- 数据路由和回调机制（新增）
"""

from datetime import datetime, timezone
import asyncio
import os
import time
import asyncio
from collections import deque
from typing import Optional, Dict, Any, Union, List, Callable
from dataclasses import dataclass, field
from enum import Enum
import aiohttp
import websockets
import structlog
import json
import hashlib
import gzip

from .proxy_manager import ProxyConfig, proxy_manager


class DataType(str, Enum):
    """数据类型枚举"""
    ORDERBOOK = "orderbook"
    TRADE = "trade"
    KLINE = "kline"
    FUNDING_RATE = "funding_rate"
    OPEN_INTEREST = "open_interest"
    LIQUIDATION = "liquidation"
    TICKER = "ticker"


@dataclass
class DataSubscription:
    """数据订阅配置"""
    data_type: DataType
    symbols: List[str]
    callback: Callable[[str, Dict[str, Any]], None]  # (data_type, data) -> None
    exchange: str
    market_type: str = "spot"  # spot, swap, futures
    active: bool = True


@dataclass
class WebSocketConfig:
    """WebSocket连接配置"""
    url: str
    timeout: int = 10
    ssl_verify: bool = True
    ssl_context: Optional[Any] = None
    ping_interval: Optional[int] = None
    ping_timeout: Optional[int] = None
    max_size: Optional[int] = None
    extra_headers: Optional[Dict[str, str]] = None
    subprotocols: Optional[list] = None
    
    # 交易所特定配置
    exchange_name: Optional[str] = None
    market_type: Optional[str] = None
    rest_base_url: Optional[str] = None
    rest_depth_endpoint: Optional[str] = None
    max_depth_levels: Optional[int] = None
    disable_ssl_for_exchanges: Optional[list] = None

    # 长期运行配置
    auto_reconnect: bool = True
    max_reconnect_attempts: int = -1  # -1表示无限重连
    reconnect_delay: float = 1.0  # 初始重连延迟（秒）
    max_reconnect_delay: float = 300.0  # 最大重连延迟（秒）
    backoff_multiplier: float = 2.0  # 退避倍数
    connection_timeout: int = 86400  # 连接超时时间（秒），默认24小时

    # 主动重连配置
    proactive_reconnect_enabled: bool = True  # 启用主动重连
    proactive_reconnect_threshold: int = 86100  # 23小时55分钟后主动重连
    dual_connection_enabled: bool = True  # 启用双连接模式
    data_buffer_size: int = 1000  # 数据缓冲区大小
    
    def should_disable_ssl(self) -> bool:
        """判断是否应该禁用SSL验证"""
        if not self.ssl_verify:
            return True
            
        # 某些交易所在代理环境下需要禁用SSL
        if (self.disable_ssl_for_exchanges and 
            self.exchange_name and 
            self.exchange_name.lower() in [ex.lower() for ex in self.disable_ssl_for_exchanges]):
            return True
            
        return False


class WebSocketWrapper:
    """统一的WebSocket包装器，兼容不同底层实现"""
    
    def __init__(self, 
                 ws: Union[aiohttp.ClientWebSocketResponse, websockets.WebSocketClientProtocol],
                 session: Optional[aiohttp.ClientSession] = None,
                 connection_type: str = "aiohttp"):
        self.ws = ws
        self.session = session
        self.connection_type = connection_type
        self.closed = False
        self.logger = structlog.get_logger(__name__)
    
    async def send(self, data: str):
        """发送消息"""
        if self.closed:
            raise ConnectionError("WebSocket连接已关闭")
        
        try:
            if self.connection_type == "aiohttp":
                await self.ws.send_str(data)
            else:  # websockets
                await self.ws.send(data)
        except Exception as e:
            self.logger.error("发送WebSocket消息失败", error=str(e))
            raise
    
    async def close(self):
        """关闭连接"""
        if self.closed:
            return
        
        try:
            if not self.ws.closed:
                await self.ws.close()
            
            if self.session:
                await self.session.close()
            
            self.closed = True
            
        except Exception as e:
            self.logger.warning("关闭WebSocket连接时出错", error=str(e))
    
    def __aiter__(self):
        """异步迭代器"""
        return self
    
    async def __anext__(self):
        """异步迭代下一个消息"""
        if self.closed:
            raise StopAsyncIteration
        
        try:
            if self.connection_type == "aiohttp":
                msg = await self.ws.receive()
                
                if msg.type == aiohttp.WSMsgType.TEXT:
                    return msg.data
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    return msg.data.decode('utf-8')
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                    self.closed = True
                    raise StopAsyncIteration
                else:
                    # 跳过其他类型的消息，继续获取下一个
                    return await self.__anext__()
            else:  # websockets
                try:
                    message = await self.ws.recv()
                    return message
                except websockets.exceptions.ConnectionClosed:
                    self.closed = True
                    raise StopAsyncIteration
                    
        except Exception as e:
            self.closed = True
            self.logger.error("WebSocket消息接收失败", error=str(e))
            raise StopAsyncIteration


class BaseWebSocketClient:
    """
    一个抽象的WebSocket客户端基类，定义了所有客户端应遵循的接口。
    """
    async def connect(self, url: str, **kwargs):
        raise NotImplementedError

    async def send(self, data: str):
        raise NotImplementedError

    async def close(self):
        raise NotImplementedError

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise NotImplementedError


# ===== 数据缓冲和去重机制 =====

class CircularDataBuffer:
    """环形数据缓冲区"""

    def __init__(self, size: int = 1000):
        self.buffer = [None] * size
        self.head = 0
        self.tail = 0
        self.count = 0
        self.size = size
        self.lock = asyncio.Lock()

    async def add_data(self, data: dict):
        """添加数据到缓冲区"""
        async with self.lock:
            self.buffer[self.tail] = {
                'data': data,
                'timestamp': time.time(),
                'sequence': self._get_sequence_number(data)
            }
            self.tail = (self.tail + 1) % self.size
            if self.count < self.size:
                self.count += 1
            else:
                self.head = (self.head + 1) % self.size

    async def get_recent_data(self, count: int = 10) -> List[dict]:
        """获取最近的数据"""
        async with self.lock:
            result = []
            current = (self.tail - 1) % self.size
            for _ in range(min(count, self.count)):
                if self.buffer[current] is not None:
                    result.append(self.buffer[current])
                current = (current - 1) % self.size
            return result

    def _get_sequence_number(self, data: dict) -> Optional[int]:
        """从数据中提取序列号"""
        # 尝试从不同字段提取序列号
        for field in ['E', 'eventTime', 'timestamp', 'ts']:
            if field in data:
                return data[field]
        return None


class DataDeduplicator:
    """数据去重器"""

    def __init__(self, window_size: int = 1000):
        self.seen_messages = {}
        self.window_size = window_size
        self.cleanup_counter = 0

    def is_duplicate(self, data: dict) -> bool:
        """检查数据是否重复"""
        key = self._generate_message_key(data)
        current_time = time.time()

        if key in self.seen_messages:
            # 检查时间窗口（5秒内的重复消息）
            if current_time - self.seen_messages[key] < 5:
                return True

        self.seen_messages[key] = current_time

        # 定期清理过期条目
        self.cleanup_counter += 1
        if self.cleanup_counter % 100 == 0:
            self._cleanup_old_entries(current_time)

        return False

    def _generate_message_key(self, data: dict) -> str:
        """生成消息唯一标识"""
        # 基于关键字段生成哈希
        key_fields = []

        # 提取关键字段
        for field in ['s', 'symbol', 'instId', 'E', 'eventTime', 'timestamp', 'ts', 'c', 'price']:
            if field in data:
                key_fields.append(f"{field}:{data[field]}")

        key_string = "|".join(key_fields)
        return hashlib.md5(key_string.encode()).hexdigest()

    def _cleanup_old_entries(self, current_time: float):
        """清理过期条目"""
        expired_keys = [
            key for key, timestamp in self.seen_messages.items()
            if current_time - timestamp > 60  # 清理60秒前的条目
        ]
        for key in expired_keys:
            del self.seen_messages[key]


class ReconnectionDataHandler:
    """重连期间数据处理器"""

    def __init__(self, max_storage_time: int = 30):
        self.temp_storage = deque()
        self.is_reconnecting = False
        self.max_storage_time = max_storage_time
        self.lock = asyncio.Lock()

    async def start_reconnection_mode(self):
        """开始重连模式"""
        async with self.lock:
            self.is_reconnecting = True
            self.temp_storage.clear()

    async def end_reconnection_mode(self) -> List[dict]:
        """结束重连模式，返回暂存的数据"""
        async with self.lock:
            self.is_reconnecting = False
            stored_data = list(self.temp_storage)
            self.temp_storage.clear()
            return stored_data

    async def handle_data(self, data: dict) -> bool:
        """处理数据，返回是否应该正常处理"""
        if not self.is_reconnecting:
            return True

        async with self.lock:
            # 暂存数据
            self.temp_storage.append({
                'data': data,
                'timestamp': time.time()
            })

            # 清理过期数据
            current_time = time.time()
            while (self.temp_storage and
                   current_time - self.temp_storage[0]['timestamp'] > self.max_storage_time):
                self.temp_storage.popleft()

            return False  # 重连期间不正常处理


class WebSocketConnectionManager:
    """WebSocket连接管理器 - 支持多数据类型订阅和分发"""

    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        self.connections: Dict[str, WebSocketWrapper] = {}

        # 数据订阅管理
        self.subscriptions: Dict[str, List[DataSubscription]] = {}  # connection_id -> subscriptions
        self.data_handlers: Dict[str, Callable] = {}  # exchange -> message_handler

        # 长期运行管理
        self.connection_configs: Dict[str, WebSocketConfig] = {}  # connection_id -> config
        self.connection_tasks: Dict[str, asyncio.Task] = {}  # connection_id -> monitoring_task
        self.reconnect_attempts: Dict[str, int] = {}  # connection_id -> attempt_count
        self.last_message_time: Dict[str, float] = {}  # connection_id -> timestamp
        self.connection_start_times: Dict[str, float] = {}  # connection_id -> start_timestamp

        # 主动重连管理
        self.proactive_reconnect_tasks: Dict[str, asyncio.Task] = {}  # connection_id -> proactive_task
        self.dual_connections: Dict[str, str] = {}  # primary_id -> backup_id
        self.data_buffers: Dict[str, CircularDataBuffer] = {}  # connection_id -> buffer
        self.data_deduplicator = DataDeduplicator()
        self.reconnection_handlers: Dict[str, ReconnectionDataHandler] = {}  # connection_id -> handler

        # 消息路由统计
        self.routing_stats = {
            'total_messages': 0,
            'routed_messages': 0,
            'unrouted_messages': 0,
            'callback_errors': 0,
            'reconnections': 0,
            'connection_failures': 0,
            'proactive_reconnections': 0,
            'duplicate_messages': 0,
            'buffered_messages': 0,
            'smooth_reconnections': 0
        }
    
    async def connect(self, 
                     config: WebSocketConfig,
                     proxy_config: Optional[ProxyConfig] = None,
                     exchange_config: Optional[Dict[str, Any]] = None) -> Optional[WebSocketWrapper]:
        """
        建立WebSocket连接
        
        基于成功的连接模式：
        1. 优先尝试aiohttp + 代理
        2. SSL配置灵活处理 
        3. 回退到websockets库
        """
        try:
            # 获取代理配置
            if proxy_config is None:
                proxy_config = proxy_manager.get_proxy_config(exchange_config)
            
            # 记录连接尝试
            self.logger.info("尝试建立WebSocket连接",
                           url=config.url,
                           exchange=config.exchange_name,
                           has_proxy=proxy_config.has_proxy(),
                           ssl_verify=not config.should_disable_ssl())
            
            # 如果有代理，优先使用aiohttp
            if proxy_config.has_proxy():
                connection = await self._connect_with_aiohttp_proxy(config, proxy_config)
                if connection:
                    return connection
                
                # aiohttp失败，尝试其他方式
                self.logger.warning("aiohttp代理连接失败，尝试其他方式")
            
            # 直接连接（使用websockets或aiohttp）
            return await self._connect_direct(config)
            
        except Exception as e:
            self.logger.error("WebSocket连接失败", error=str(e), url=config.url)
            return None
    
    async def _connect_with_aiohttp_proxy(self, 
                                        config: WebSocketConfig, 
                                        proxy_config: ProxyConfig) -> Optional[WebSocketWrapper]:
        """使用aiohttp通过代理连接"""
        try:
            proxy_url = proxy_config.to_aiohttp_proxy()
            if not proxy_url:
                return None
            
            # 超时配置
            timeout = aiohttp.ClientTimeout(total=config.timeout)
            
            # SSL配置
            ssl_context = None if config.should_disable_ssl() else config.ssl_context
            
            # 创建会话（兼容不同aiohttp版本）
            try:
                # 新版本aiohttp
                session = aiohttp.ClientSession(timeout=timeout, trust_env=True)
            except TypeError:
                # 旧版本aiohttp不支持trust_env
                session = aiohttp.ClientSession(timeout=timeout)
            
            # 连接参数
            connect_kwargs = {
                'proxy': proxy_url,
                'ssl': ssl_context,
                'timeout': timeout
            }
            
            # 添加可选参数
            if config.extra_headers:
                connect_kwargs['headers'] = config.extra_headers
            
            if config.subprotocols:
                connect_kwargs['protocols'] = config.subprotocols
                
            if config.max_size:
                connect_kwargs['max_msg_size'] = config.max_size
            
            # 建立连接
            ws = await session.ws_connect(config.url, **connect_kwargs)
            
            wrapper = WebSocketWrapper(ws, session, "aiohttp")
            
            # 缓存连接
            connection_key = f"{config.exchange_name or 'unknown'}_{config.url}"
            self.connections[connection_key] = wrapper
            
            self.logger.info("aiohttp代理WebSocket连接成功", 
                           proxy=proxy_url, 
                           ssl_disabled=config.should_disable_ssl())
            
            return wrapper
            
        except Exception as e:
            if 'session' in locals():
                await session.close()
            self.logger.error("aiohttp代理连接失败", error=str(e))
            return None
    
    async def _connect_direct(self, config: WebSocketConfig) -> Optional[WebSocketWrapper]:
        """直接WebSocket连接"""
        try:
            # 优先尝试websockets库（更稳定）
            if not proxy_manager.get_proxy_config().has_proxy():
                return await self._connect_with_websockets(config)
            
            # 有代理环境时使用aiohttp
            return await self._connect_with_aiohttp_direct(config)
            
        except Exception as e:
            self.logger.error("直接WebSocket连接失败", error=str(e))
            return None
    
    async def _connect_with_websockets(self, config: WebSocketConfig) -> Optional[WebSocketWrapper]:
        """使用websockets库连接"""
        try:
            # 连接参数
            connect_kwargs = {
                'ping_interval': config.ping_interval,
                'ping_timeout': config.ping_timeout
            }
            
            # SSL配置
            if config.should_disable_ssl():
                connect_kwargs['ssl'] = None
            elif config.ssl_context:
                connect_kwargs['ssl'] = config.ssl_context
            
            # 添加可选参数
            if config.extra_headers:
                connect_kwargs['extra_headers'] = config.extra_headers
            
            if config.subprotocols:
                connect_kwargs['subprotocols'] = config.subprotocols
                
            if config.max_size:
                connect_kwargs['max_size'] = config.max_size
            
            # 建立连接
            ws = await websockets.connect(config.url, **connect_kwargs)
            
            wrapper = WebSocketWrapper(ws, None, "websockets")
            
            # 缓存连接
            connection_key = f"{config.exchange_name or 'unknown'}_{config.url}"
            self.connections[connection_key] = wrapper
            
            self.logger.info("websockets直接连接成功")
            return wrapper
            
        except Exception as e:
            self.logger.error("websockets连接失败", error=str(e))
            return None
    
    async def _connect_with_aiohttp_direct(self, config: WebSocketConfig) -> Optional[WebSocketWrapper]:
        """使用aiohttp直接连接"""
        try:
            timeout = aiohttp.ClientTimeout(total=config.timeout)
            ssl_context = None if config.should_disable_ssl() else config.ssl_context
            
            # 创建会话
            session = aiohttp.ClientSession(timeout=timeout)
            
            # 连接参数
            connect_kwargs = {
                'ssl': ssl_context,
                'timeout': timeout
            }
            
            if config.extra_headers:
                connect_kwargs['headers'] = config.extra_headers
            
            if config.subprotocols:
                connect_kwargs['protocols'] = config.subprotocols
                
            if config.max_size:
                connect_kwargs['max_msg_size'] = config.max_size
            
            # 建立连接
            ws = await session.ws_connect(config.url, **connect_kwargs)
            
            wrapper = WebSocketWrapper(ws, session, "aiohttp")
            
            # 缓存连接
            connection_key = f"{config.exchange_name or 'unknown'}_{config.url}"
            self.connections[connection_key] = wrapper
            
            self.logger.info("aiohttp直接连接成功")
            return wrapper
            
        except Exception as e:
            if 'session' in locals():
                await session.close()
            self.logger.error("aiohttp直接连接失败", error=str(e))
            return None
    
    async def close_connection(self, connection_key: str):
        """关闭指定连接"""
        if connection_key in self.connections:
            await self.connections[connection_key].close()
            del self.connections[connection_key]
    
    async def close_all_connections(self):
        """关闭所有连接"""
        for connection in self.connections.values():
            await connection.close()
        self.connections.clear()
    
    def get_connection(self, connection_key: str) -> Optional[WebSocketWrapper]:
        """获取连接"""
        return self.connections.get(connection_key)
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计"""
        return {
            'total_connections': len(self.connections),
            'active_connections': len([c for c in self.connections.values() if not c.closed]),
            'connections': list(self.connections.keys()),
            'total_subscriptions': sum(len(subs) for subs in self.subscriptions.values()),
            'routing_stats': self.routing_stats.copy()
        }

    async def subscribe_data_type(self,
                                connection_key: str,
                                data_type: DataType,
                                symbols: List[str],
                                callback: Callable[[str, Dict[str, Any]], None],
                                exchange: str,
                                market_type: str = "spot") -> bool:
        """
        订阅特定数据类型

        Args:
            connection_key: 连接标识
            data_type: 数据类型
            symbols: 交易对列表
            callback: 数据回调函数
            exchange: 交易所名称
            market_type: 市场类型

        Returns:
            订阅是否成功
        """
        try:
            if connection_key not in self.connections:
                self.logger.error("连接不存在", connection_key=connection_key)
                return False

            # 创建订阅
            subscription = DataSubscription(
                data_type=data_type,
                symbols=symbols,
                callback=callback,
                exchange=exchange,
                market_type=market_type
            )

            # 添加到订阅列表
            if connection_key not in self.subscriptions:
                self.subscriptions[connection_key] = []

            self.subscriptions[connection_key].append(subscription)

            self.logger.info("数据类型订阅成功",
                           connection_key=connection_key,
                           data_type=data_type.value,
                           symbols=symbols,
                           exchange=exchange,
                           market_type=market_type)

            return True

        except Exception as e:
            self.logger.error("数据类型订阅失败",
                            connection_key=connection_key,
                            data_type=data_type.value,
                            error=str(e))
            return False

    def register_message_handler(self, exchange: str, handler: Callable[[Dict[str, Any]], None]):
        """
        注册交易所特定的消息处理器

        Args:
            exchange: 交易所名称
            handler: 消息处理函数
        """
        self.data_handlers[exchange] = handler
        self.logger.info("消息处理器注册成功", exchange=exchange)

    async def route_message(self, connection_key: str, message: Dict[str, Any]):
        """
        路由消息到对应的订阅回调

        Args:
            connection_key: 连接标识
            message: 接收到的消息
        """
        try:
            self.routing_stats['total_messages'] += 1

            # 更新最后消息时间（用于连接健康检查）
            self.last_message_time[connection_key] = time.time()

            # 检查重连期间数据处理
            handler = self.reconnection_handlers.get(connection_key)
            if handler:
                should_process = await handler.handle_data(message)
                if not should_process:
                    return  # 重连期间暂存数据，不进行正常处理

            # 数据去重检查
            if self.data_deduplicator.is_duplicate(message):
                self.routing_stats['duplicate_messages'] = self.routing_stats.get('duplicate_messages', 0) + 1
                return

            # 添加到数据缓冲区
            buffer = self.data_buffers.get(connection_key)
            if buffer:
                await buffer.add_data(message)

            # 获取连接的订阅列表
            subscriptions = self.subscriptions.get(connection_key, [])
            if not subscriptions:
                self.routing_stats['unrouted_messages'] += 1
                return

            # 解析消息，确定数据类型和交易对
            data_type, symbol, parsed_data = self._parse_message(message, subscriptions[0].exchange)

            if not data_type or not symbol:
                self.routing_stats['unrouted_messages'] += 1
                return

            # 查找匹配的订阅
            routed = False
            for subscription in subscriptions:
                if (subscription.active and
                    subscription.data_type == data_type and
                    symbol in subscription.symbols):

                    try:
                        # 调用回调函数
                        await self._safe_callback(subscription.callback, data_type.value, parsed_data)
                        routed = True
                    except Exception as e:
                        self.logger.error("回调函数执行失败",
                                        data_type=data_type.value,
                                        symbol=symbol,
                                        error=str(e))
                        self.routing_stats['callback_errors'] += 1

            if routed:
                self.routing_stats['routed_messages'] += 1
            else:
                self.routing_stats['unrouted_messages'] += 1

        except Exception as e:
            self.logger.error("消息路由失败",
                            connection_key=connection_key,
                            error=str(e))
            self.routing_stats['unrouted_messages'] += 1

    def _parse_message(self, message: Dict[str, Any], exchange: str) -> tuple:
        """
        解析消息，提取数据类型和交易对

        Returns:
            (data_type, symbol, parsed_data)
        """
        try:
            if exchange.lower() == "binance":
                return self._parse_binance_message(message)
            elif exchange.lower() == "okx":
                return self._parse_okx_message(message)
            else:
                return None, None, None

        except Exception as e:
            self.logger.error("消息解析失败", exchange=exchange, error=str(e))
            return None, None, None

    def _parse_binance_message(self, message: Dict[str, Any]) -> tuple:
        """解析Binance消息"""
        try:
            # Binance组合流格式: {"stream": "btcusdt@depth", "data": {...}}
            if "stream" in message and "data" in message:
                stream = message["stream"]
                data = message["data"]

                # 解析流名称
                if "@depth" in stream:
                    symbol = stream.split("@")[0].upper()
                    return DataType.ORDERBOOK, symbol, data
                elif "@trade" in stream:
                    symbol = stream.split("@")[0].upper()
                    return DataType.TRADE, symbol, data
                elif "@kline" in stream:
                    symbol = stream.split("@")[0].upper()
                    return DataType.KLINE, symbol, data
                elif "@forceOrder" in stream:
                    symbol = stream.split("@")[0].upper() if stream != "!forceOrder@arr" else "ALL"
                    return DataType.LIQUIDATION, symbol, data

            return None, None, None

        except Exception as e:
            self.logger.error("Binance消息解析失败", error=str(e))
            return None, None, None

    def _parse_okx_message(self, message: Dict[str, Any]) -> tuple:
        """解析OKX消息"""
        try:
            # OKX格式: {"arg": {"channel": "books", "instId": "BTC-USDT"}, "data": [...]}
            if "arg" in message and "data" in message:
                arg = message["arg"]
                data = message["data"]

                channel = arg.get("channel", "")
                symbol = arg.get("instId", "")

                if channel == "books":
                    return DataType.ORDERBOOK, symbol, data
                elif channel == "trades":
                    return DataType.TRADE, symbol, data
                elif channel == "candle1m":
                    return DataType.KLINE, symbol, data
                elif channel == "funding-rate":
                    return DataType.FUNDING_RATE, symbol, data
                elif channel == "open-interest":
                    return DataType.OPEN_INTEREST, symbol, data
                elif channel == "liquidation-orders":
                    return DataType.LIQUIDATION, symbol, data

            return None, None, None

        except Exception as e:
            self.logger.error("OKX消息解析失败", error=str(e))
            return None, None, None

    async def _safe_callback(self, callback: Callable, data_type: str, data: Dict[str, Any]):
        """安全地调用回调函数"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(data_type, data)
            else:
                callback(data_type, data)
        except Exception as e:
            self.logger.error("回调函数执行异常", error=str(e))
            raise

    async def connect_with_auto_reconnect(self,
                                        connection_id: str,
                                        config: WebSocketConfig,
                                        proxy_config: Optional[ProxyConfig] = None,
                                        exchange_config: Optional[Dict[str, Any]] = None) -> bool:
        """
        建立支持自动重连的WebSocket连接

        Args:
            connection_id: 连接标识
            config: WebSocket配置
            proxy_config: 代理配置
            exchange_config: 交易所配置

        Returns:
            连接是否成功建立
        """
        try:
            # 存储配置用于重连
            self.connection_configs[connection_id] = config

            # 建立初始连接
            connection = await self.connect(config, proxy_config, exchange_config)
            if not connection:
                self.logger.error("初始连接建立失败", connection_id=connection_id)
                return False

            # 存储连接
            self.connections[connection_id] = connection
            self.reconnect_attempts[connection_id] = 0
            self.last_message_time[connection_id] = time.time()
            self.connection_start_times[connection_id] = time.time()

            # 初始化数据处理组件
            self.data_buffers[connection_id] = CircularDataBuffer(config.data_buffer_size)
            self.reconnection_handlers[connection_id] = ReconnectionDataHandler()

            # 启动连接监控任务
            if config.auto_reconnect:
                task = asyncio.create_task(self._connection_monitor_loop(connection_id))
                self.connection_tasks[connection_id] = task

            # 启动主动重连任务
            if config.proactive_reconnect_enabled:
                proactive_task = asyncio.create_task(self._proactive_reconnect_loop(connection_id))
                self.proactive_reconnect_tasks[connection_id] = proactive_task

            self.logger.info("WebSocket连接建立成功",
                           connection_id=connection_id,
                           auto_reconnect=config.auto_reconnect)

            return True

        except Exception as e:
            self.logger.error("建立自动重连连接失败",
                            connection_id=connection_id,
                            error=str(e))
            return False

    async def _connection_monitor_loop(self, connection_id: str):
        """
        连接监控循环

        监控连接状态，处理自动重连
        """
        try:
            config = self.connection_configs[connection_id]

            while connection_id in self.connections:
                await asyncio.sleep(30)  # 每30秒检查一次

                # 检查连接是否仍然有效
                if not await self._is_connection_healthy(connection_id):
                    self.logger.warning("检测到连接不健康，开始重连", connection_id=connection_id)

                    # 执行重连
                    success = await self._reconnect_connection(connection_id)
                    if not success:
                        self.logger.error("重连失败，停止监控", connection_id=connection_id)
                        break

        except asyncio.CancelledError:
            self.logger.info("连接监控任务已取消", connection_id=connection_id)
        except Exception as e:
            self.logger.error("连接监控异常", connection_id=connection_id, error=str(e))

    async def _proactive_reconnect_loop(self, connection_id: str):
        """
        主动重连循环

        在官方强制断开前主动重连，确保数据连续性
        """
        try:
            config = self.connection_configs[connection_id]

            while connection_id in self.connections:
                # 检查连接年龄
                connection_age = time.time() - self.connection_start_times.get(connection_id, 0)

                # 如果接近主动重连阈值，执行主动重连
                if connection_age >= config.proactive_reconnect_threshold:
                    self.logger.info("触发主动重连",
                                   connection_id=connection_id,
                                   connection_age_hours=connection_age / 3600)

                    # 执行平滑重连
                    success = await self._perform_smooth_reconnection(connection_id)
                    if success:
                        # 重置连接开始时间
                        self.connection_start_times[connection_id] = time.time()
                        self.routing_stats['reconnections'] += 1
                    else:
                        self.logger.error("主动重连失败", connection_id=connection_id)
                        break

                # 每小时检查一次
                await asyncio.sleep(3600)

        except asyncio.CancelledError:
            self.logger.info("主动重连任务已取消", connection_id=connection_id)
        except Exception as e:
            self.logger.error("主动重连循环异常", connection_id=connection_id, error=str(e))

    async def _perform_smooth_reconnection(self, connection_id: str) -> bool:
        """
        执行平滑重连

        实现零数据丢失的连接切换
        """
        try:
            config = self.connection_configs.get(connection_id)
            if not config:
                return False

            # 生成备用连接ID
            backup_connection_id = f"{connection_id}_backup_{int(time.time())}"

            self.logger.info("开始平滑重连",
                           primary=connection_id,
                           backup=backup_connection_id)

            # 阶段1: 启动重连数据处理模式
            handler = self.reconnection_handlers.get(connection_id)
            if handler:
                await handler.start_reconnection_mode()

            # 阶段2: 建立备用连接
            backup_connection = await self.connect(config)
            if not backup_connection:
                self.logger.error("备用连接建立失败", backup_id=backup_connection_id)
                if handler:
                    await handler.end_reconnection_mode()
                return False

            # 阶段3: 数据同步期（双连接并行）
            self.connections[backup_connection_id] = backup_connection
            self.connection_start_times[backup_connection_id] = time.time()
            self.last_message_time[backup_connection_id] = time.time()
            self.dual_connections[connection_id] = backup_connection_id

            # 等待数据同步稳定
            await asyncio.sleep(2)

            # 阶段4: 恢复订阅
            await self._restore_subscriptions(backup_connection_id)

            # 阶段5: 切换主连接
            old_connection = self.connections.get(connection_id)
            self.connections[connection_id] = backup_connection
            self.connection_start_times[connection_id] = time.time()

            # 阶段6: 处理暂存数据
            if handler:
                stored_data = await handler.end_reconnection_mode()
                for item in stored_data:
                    await self.route_message(connection_id, item['data'])

            # 阶段7: 清理旧连接
            await asyncio.sleep(1)  # 1秒缓冲
            if old_connection:
                try:
                    await old_connection.close()
                except Exception:
                    pass

            # 清理备用连接记录
            self.connections.pop(backup_connection_id, None)
            self.connection_start_times.pop(backup_connection_id, None)
            self.last_message_time.pop(backup_connection_id, None)
            self.dual_connections.pop(connection_id, None)

            self.logger.info("平滑重连完成", connection_id=connection_id)
            return True

        except Exception as e:
            self.logger.error("平滑重连失败", connection_id=connection_id, error=str(e))
            # 清理状态
            if handler:
                await handler.end_reconnection_mode()
            return False

    async def _is_connection_healthy(self, connection_id: str) -> bool:
        """
        检查连接是否健康

        Args:
            connection_id: 连接标识

        Returns:
            连接是否健康
        """
        try:
            connection = self.connections.get(connection_id)
            if not connection:
                return False

            # 检查连接是否关闭
            if connection.closed:
                return False

            # 检查最后消息时间（如果超过5分钟没有消息，认为连接可能有问题）
            last_msg_time = self.last_message_time.get(connection_id, 0)
            if time.time() - last_msg_time > 300:  # 5分钟
                self.logger.warning("连接长时间无消息",
                                  connection_id=connection_id,
                                  last_message_ago=time.time() - last_msg_time)
                return False

            return True

        except Exception as e:
            self.logger.error("健康检查异常", connection_id=connection_id, error=str(e))
            return False

    async def _reconnect_connection(self, connection_id: str) -> bool:
        """
        重连WebSocket连接

        Args:
            connection_id: 连接标识

        Returns:
            重连是否成功
        """
        try:
            config = self.connection_configs.get(connection_id)
            if not config:
                self.logger.error("找不到连接配置", connection_id=connection_id)
                return False

            # 获取当前重连次数
            attempt = self.reconnect_attempts.get(connection_id, 0)

            # 检查是否超过最大重连次数
            if config.max_reconnect_attempts > 0 and attempt >= config.max_reconnect_attempts:
                self.logger.error("超过最大重连次数",
                                connection_id=connection_id,
                                attempts=attempt)
                return False

            # 计算重连延迟（指数退避）
            delay = min(
                config.reconnect_delay * (config.backoff_multiplier ** attempt),
                config.max_reconnect_delay
            )

            self.logger.info("准备重连",
                           connection_id=connection_id,
                           attempt=attempt + 1,
                           delay=delay)

            # 等待重连延迟
            await asyncio.sleep(delay)

            # 关闭旧连接
            old_connection = self.connections.get(connection_id)
            if old_connection:
                try:
                    await old_connection.close()
                except Exception:
                    pass

            # 建立新连接
            new_connection = await self.connect(config)
            if not new_connection:
                # 重连失败，增加重连次数
                self.reconnect_attempts[connection_id] = attempt + 1
                self.routing_stats['connection_failures'] += 1
                return False

            # 更新连接
            self.connections[connection_id] = new_connection
            self.reconnect_attempts[connection_id] = 0  # 重置重连次数
            self.last_message_time[connection_id] = time.time()
            self.routing_stats['reconnections'] += 1

            # 恢复订阅
            await self._restore_subscriptions(connection_id)

            self.logger.info("重连成功", connection_id=connection_id)
            return True

        except Exception as e:
            self.logger.error("重连异常", connection_id=connection_id, error=str(e))
            self.reconnect_attempts[connection_id] = self.reconnect_attempts.get(connection_id, 0) + 1
            return False

    async def _restore_subscriptions(self, connection_id: str):
        """
        恢复订阅

        重连后需要重新发送所有订阅请求
        """
        try:
            subscriptions = self.subscriptions.get(connection_id, [])
            if not subscriptions:
                return

            self.logger.info("恢复订阅",
                           connection_id=connection_id,
                           subscription_count=len(subscriptions))

            # 这里需要根据交易所类型发送订阅请求
            # 具体实现取决于交易所的订阅协议
            for subscription in subscriptions:
                if subscription.exchange.lower() == "okx":
                    await self._send_okx_subscription(connection_id, subscription)
                # Binance的订阅在URL中，重连后自动恢复

        except Exception as e:
            self.logger.error("恢复订阅失败", connection_id=connection_id, error=str(e))

    async def _send_okx_subscription(self, connection_id: str, subscription: DataSubscription):
        """发送OKX订阅请求"""
        try:
            connection = self.connections.get(connection_id)
            if not connection:
                return

            # 构建OKX订阅请求
            for symbol in subscription.symbols:
                if subscription.data_type == DataType.ORDERBOOK:
                    channel = "books"
                elif subscription.data_type == DataType.TRADE:
                    channel = "trades"
                elif subscription.data_type == DataType.FUNDING_RATE:
                    channel = "funding-rate"
                elif subscription.data_type == DataType.OPEN_INTEREST:
                    channel = "open-interest"
                else:
                    continue

                request = {
                    "op": "subscribe",
                    "args": [{
                        "channel": channel,
                        "instId": symbol
                    }]
                }

                await connection.send(json.dumps(request))
                await asyncio.sleep(0.1)  # 避免频率限制

        except Exception as e:
            self.logger.error("发送OKX订阅失败", error=str(e))

    async def close_connection(self, connection_id: str):
        """
        关闭连接

        Args:
            connection_id: 连接标识
        """
        try:
            # 停止监控任务
            task = self.connection_tasks.get(connection_id)
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # 停止主动重连任务
            proactive_task = self.proactive_reconnect_tasks.get(connection_id)
            if proactive_task and not proactive_task.done():
                proactive_task.cancel()
                try:
                    await proactive_task
                except asyncio.CancelledError:
                    pass

            # 关闭连接
            connection = self.connections.get(connection_id)
            if connection:
                await connection.close()

            # 清理状态
            self.connections.pop(connection_id, None)
            self.connection_configs.pop(connection_id, None)
            self.connection_tasks.pop(connection_id, None)
            self.reconnect_attempts.pop(connection_id, None)
            self.last_message_time.pop(connection_id, None)
            self.connection_start_times.pop(connection_id, None)
            self.subscriptions.pop(connection_id, None)

            # 清理主动重连相关状态
            self.proactive_reconnect_tasks.pop(connection_id, None)
            self.dual_connections.pop(connection_id, None)
            self.data_buffers.pop(connection_id, None)
            self.reconnection_handlers.pop(connection_id, None)

            self.logger.info("连接已关闭", connection_id=connection_id)

        except Exception as e:
            self.logger.error("关闭连接失败", connection_id=connection_id, error=str(e))


# ===== 交易所特定的WebSocket配置和工厂函数 =====

def create_binance_websocket_config(market_type: str, symbols: list, data_types: List[str] = None,
                                   websocket_depth: int = 20) -> WebSocketConfig:
    """
    创建Binance WebSocket配置 - 基于官方API文档

    Args:
        market_type: 市场类型 ("spot", "perpetual", "futures")
        symbols: 交易对列表
        data_types: 数据类型列表 ["orderbook", "trade", "kline", "liquidation"]
        websocket_depth: WebSocket深度档位 (5, 10, 20 或其他)

    Returns:
        WebSocketConfig: 配置对象

    Raises:
        ValueError: 不支持的市场类型
    """
    if data_types is None:
        data_types = ["orderbook"]

    # 根据市场类型选择正确的WebSocket端点和API
    if market_type in ["spot"]:
        # 现货交易 - 基于官方文档
        base_url = "wss://stream.binance.com:9443"
        rest_base_url = "https://api.binance.com"
        rest_depth_endpoint = "/api/v3/depth"
    elif market_type in ["perpetual", "swap", "futures"]:
        # USD本位永续合约 - 基于官方文档
        base_url = "wss://fstream.binance.com"
        rest_base_url = "https://fapi.binance.com"
        rest_depth_endpoint = "/fapi/v1/depth"
    else:
        raise ValueError(f"不支持的Binance市场类型: {market_type}. 支持的类型: spot, perpetual, futures")

    # 构建数据流
    streams = []
    for symbol in symbols:
        symbol_lower = symbol.lower()
        for data_type in data_types:
            if data_type == "orderbook":
                # 根据深度选择合适的流 - 基于官方文档
                if websocket_depth in [5, 10, 20]:
                    # 部分深度流 - 支持5, 10, 20档
                    streams.append(f"{symbol_lower}@depth{websocket_depth}@100ms")
                else:
                    # 完整深度流 - 用于全量订单簿维护
                    streams.append(f"{symbol_lower}@depth@100ms")
            elif data_type == "trade":
                streams.append(f"{symbol_lower}@trade")
            elif data_type == "kline":
                streams.append(f"{symbol_lower}@kline_1m")
            elif data_type == "liquidation" and market_type in ["perpetual", "swap", "futures"]:
                # 强平数据仅在期货/永续合约中可用
                streams.append(f"{symbol_lower}@forceOrder")

    url = f"{base_url}/stream?streams={'/'.join(streams)}"

    return WebSocketConfig(
        url=url,
        exchange_name="binance",
        market_type=market_type,
        rest_base_url=rest_base_url,
        rest_depth_endpoint=rest_depth_endpoint,
        ping_interval=20,  # Binance官方要求20秒ping
        ping_timeout=60,   # 60秒pong超时
        max_depth_levels=5000 if market_type == "spot" else 1000  # 现货5000档，期货1000档
    )


def create_okx_websocket_config(market_type: str, symbols: list, data_types: List[str] = None) -> WebSocketConfig:
    """创建OKX WebSocket配置"""
    if data_types is None:
        data_types = ["orderbook"]

    # OKX所有市场类型使用同一个WebSocket URL
    url = "wss://ws.okx.com:8443/ws/v5/public"

    # 注意：OKX的订阅是在连接建立后通过消息发送的，不在URL中
    # 这里只是创建基础配置，实际订阅会在连接后处理

    return WebSocketConfig(
        url=url,
        exchange_name="okx",
        ping_interval=25,  # OKX客户端主动ping，25秒间隔
        ping_timeout=60
    )


# 全局WebSocket连接管理器实例
websocket_manager = WebSocketConnectionManager()