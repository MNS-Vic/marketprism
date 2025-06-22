"""
MarketPrism 增强的交易所连接器

基于Binance API文档2023-12-04最新变更优化：
1. 精度错误处理改进
2. 时间戳验证增强
3. 排序结果修正
4. WebSocket连接优化
5. 用户数据流改进
"""

from datetime import datetime, timezone
import asyncio
import logging
import time
import json
import hmac
import hashlib
import websockets
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from urllib.parse import urlencode
import aiohttp
from abc import ABC, abstractmethod
import sys
from pathlib import Path

# Add the project root to the path to allow absolute imports
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root / "services" / "python-collector" / "src"))

from core.networking.unified_session_manager import UnifiedSessionManager as SessionManager, UnifiedSessionConfig as SessionConfig
from core.caching.cache_interface import Cache
from core.caching.memory_cache import MemoryCache
from core.caching.redis_cache import RedisCache
from core.enums import Exchange, MarketType, DataType
from core.errors import (
    ExchangeError,
    NetworkError,
)
from marketprism_collector.data_types import ExchangeConfig

logger = logging.getLogger(__name__)


class RateLimiter:
    """速率限制器"""
    
    def __init__(self, max_requests: int, window: int):
        self.max_requests = max_requests
        self.window = window
        self.requests = []
    
    async def acquire(self):
        """获取请求许可"""
        now = time.time()
        
        # 清理过期请求
        self.requests = [req_time for req_time in self.requests if now - req_time < self.window]
        
        # 检查是否超过限制
        if len(self.requests) >= self.max_requests:
            sleep_time = self.window - (now - self.requests[0])
            if sleep_time > 0:
                logger.warning(f"触发速率限制，等待 {sleep_time:.2f} 秒")
                await asyncio.sleep(sleep_time)
        
        self.requests.append(now)


class BinanceErrorHandler:
    """Binance API错误处理器（基于最新文档）"""
    
    # 错误码映射
    ERROR_CODES = {
        -1000: "UNKNOWN",
        -1001: "DISCONNECTED",
        -1002: "UNAUTHORIZED",
        -1003: "TOO_MANY_REQUESTS",
        -1006: "UNEXPECTED_RESP",
        -1007: "TIMEOUT",
        -1013: "INVALID_QUANTITY",
        -1014: "UNKNOWN_ORDER_COMPOSITION",
        -1015: "TOO_MANY_ORDERS",
        -1016: "SERVICE_SHUTTING_DOWN",
        -1020: "UNSUPPORTED_OPERATION",
        -1021: "INVALID_TIMESTAMP",
        -1022: "INVALID_SIGNATURE",
        -2010: "NEW_ORDER_REJECTED",
        -2011: "CANCEL_REJECTED",
        -2013: "NO_SUCH_ORDER",
        -2014: "BAD_API_KEY_FMT",
        -2015: "REJECTED_MBX_KEY",
        -2016: "NO_TRADING_WINDOW",
        -2026: "ORDER_ARCHIVED",  # 新增：归档订单错误
    }
    
    # 精度错误处理（基于2023-12-04变更）
    PRECISION_ERROR_PARAMS = [
        'quantity', 'quoteOrderQty', 'icebergQty', 
        'limitIcebergQty', 'stopIcebergQty', 'price', 
        'stopPrice', 'stopLimitPrice'
    ]
    
    @classmethod
    def handle_error(cls, error_code: int, error_msg: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """处理API错误"""
        error_info = {
            'code': error_code,
            'message': error_msg,
            'type': cls.ERROR_CODES.get(error_code, 'UNKNOWN_ERROR'),
            'context': context or {},
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'severity': 'error'
        }
        
        # 特殊错误处理
        if error_code == -2026:
            error_info['severity'] = 'warning'
            error_info['action'] = 'order_archived'
            
        elif "Parameter '%s' has too much precision" in error_msg:
            error_info['severity'] = 'warning'
            error_info['action'] = 'adjust_precision'
            error_info['affected_params'] = cls.PRECISION_ERROR_PARAMS
            
        elif error_code in [-1021, -1022]:
            error_info['severity'] = 'critical'
            error_info['action'] = 'sync_time_signature'
            
        elif error_code == -1003:
            error_info['severity'] = 'warning'
            error_info['action'] = 'rate_limit_wait'
            
        return error_info


class EnhancedExchangeConnector:
    """增强的交易所连接器
    
    特性：
    1. 统一的错误处理
    2. 智能重试机制
    3. 自动时间同步
    4. 精度自动调整
    5. 连接池优化
    6. WebSocket连接管理
    """
    
    def __init__(self, config: ExchangeConfig, session_manager: Optional[SessionManager] = None):
        self.config = config
        self.session_manager = session_manager or SessionManager()
        self._owns_session_manager = session_manager is None  # 记录是否拥有会话管理器
        
        # 速率限制器
        self.rate_limiter = RateLimiter(
            config.rate_limit_requests, 
            config.rate_limit_window
        )
        
        # 连接状态
        self.connected = False
        self.last_ping = 0
        self.server_time_offset = 0
        
        # WebSocket连接
        self.ws_connection = None
        self.ws_handlers = {}
        self.ws_subscriptions = set()
        
        # Ping/Pong维护（collector核心功能）
        self.ping_interval = 300  # 5分钟
        self.ping_timeout = 10    # 10秒超时
        self.last_ping_time = None
        self.last_pong_time = None
        self.is_connected = False
        
        # 认证和会话管理（collector核心功能）
        self.session_active = False
        self.is_authenticated = False
        
        # 退避策略和错误处理（collector核心功能）
        self.consecutive_failures = 0
        self.max_request_weight = 1200
        
        # collector统计信息
        self.message_stats = {
            'pings_sent': 0,
            'pongs_received': 0,
            'login_attempts': 0,
            'successful_logins': 0,
            'failed_logins': 0
        }
        
        # OKX特定属性
        self.okx_stats = {
            'login_attempts': 0,
            'successful_logins': 0,
            'failed_logins': 0
        }
        self.okx_reconnect_delay = 5  # OKX重连延迟
        
        # 统计信息
        self.stats = {
            'requests_sent': 0,
            'requests_successful': 0,
            'requests_failed': 0,
            'ws_messages_received': 0,
            'ws_reconnections': 0,
            'precision_adjustments': 0,
            'time_syncs': 0,
            'start_time': time.time(),
            'successful_logins': 0,
            'failed_logins': 0,
            'backoff_delays': 0
        }
        
        logger.info(f"增强交易所连接器已初始化: {config.name}")
    
    async def initialize(self):
        """初始化连接器"""
        try:
            # 同步服务器时间
            await self.sync_server_time()
            
            # 测试连接
            await self.test_connectivity()
            
            self.connected = True
            logger.info(f"{self.config.name} 连接器初始化成功")
            
        except Exception as e:
            logger.error(f"{self.config.name} 连接器初始化失败: {e}")
            raise
    
    async def sync_server_time(self):
        """同步服务器时间"""
        try:
            # 不同交易所的时间API
            time_endpoints = {
                'binance': '/api/v3/time',
                'okx': '/api/v5/public/time',
                'deribit': '/api/v2/public/get_time'
            }
            
            endpoint = time_endpoints.get(self.config.name.lower(), '/api/v3/time')
            url = f"{self.config.base_url}{endpoint}"
            
            start_time = time.time() * 1000
            
            response = await self.session_manager.request('GET', url)
            try:
                data = await response.json()

                end_time = time.time() * 1000
                local_time = (start_time + end_time) / 2

                # 解析服务器时间
                if self.config.name.lower() == 'binance':
                    server_time = data['serverTime']
                elif self.config.name.lower() == 'okx':
                    server_time = int(data['data'][0]['ts'])
                elif self.config.name.lower() == 'deribit':
                    server_time = data['result']
                else:
                    server_time = local_time

                self.server_time_offset = server_time - local_time
                self.stats['time_syncs'] += 1

                logger.debug(f"{self.config.name} 时间同步完成，偏移: {self.server_time_offset:.0f}ms")
            finally:
                response.close()
                
        except Exception as e:
            logger.warning(f"{self.config.name} 时间同步失败: {e}")
            self.server_time_offset = 0
    
    async def test_connectivity(self):
        """测试连接性"""
        try:
            # 不同交易所的测试端点
            test_endpoints = {
                'binance': '/api/v3/exchangeInfo',
                'okx': '/api/v5/public/instruments',
                'deribit': '/api/v2/public/get_instruments'
            }
            
            endpoint = test_endpoints.get(self.config.name.lower(), '/api/v3/ping')
            url = f"{self.config.base_url}{endpoint}"
            
            response = await self.session_manager.request('GET', url)
            try:
                if response.status == 200:
                    logger.info(f"{self.config.name} 连接测试成功")
                else:
                    raise Exception(f"HTTP {response.status}")
            finally:
                response.close()
                    
        except Exception as e:
            logger.error(f"{self.config.name} 连接测试失败: {e}")
            raise
    
    def get_server_time(self) -> int:
        """获取服务器时间戳"""
        return int((time.time() * 1000) + self.server_time_offset)
    
    def validate_timestamp(self, timestamp: int) -> bool:
        """验证时间戳（基于Binance最新变更）"""
        server_time = self.get_server_time()
        
        # 检查是否在允许范围内
        min_time = 1483228800000  # 2017年1月1日
        max_time = server_time + 10000  # 当前时间+10秒
        
        if timestamp < min_time:
            logger.warning(f"时间戳过旧: {timestamp} < {min_time}")
            return False
            
        if timestamp > max_time:
            logger.warning(f"时间戳过新: {timestamp} > {max_time}")
            return False
            
        return True
    
    def adjust_precision(self, value: float, precision: int) -> str:
        """调整数值精度（基于Binance精度变更）"""
        self.stats['precision_adjustments'] += 1
        if precision == 0:
            return f"{value:.0f}"
        else:
            formatted = f"{value:.{precision}f}"
            # 只移除小数部分的尾随零，保留整数部分
            if '.' in formatted:
                formatted = formatted.rstrip('0').rstrip('.')
            return formatted
    
    def prepare_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """准备请求参数"""
        prepared = {}
        
        for key, value in params.items():
            if key in BinanceErrorHandler.PRECISION_ERROR_PARAMS:
                if isinstance(value, (int, float)):
                    # 根据参数类型调整精度
                    if 'price' in key.lower():
                        precision = self.config.price_precision
                    else:
                        precision = self.config.quantity_precision
                    
                    prepared[key] = self.adjust_precision(value, precision)
                else:
                    prepared[key] = str(value)
            else:
                prepared[key] = value
        
        return prepared
    
    def create_signature(self, params: Dict[str, Any]) -> str:
        """创建签名"""
        if not self.config.api_secret:
            return ""
        
        query_string = urlencode(sorted(params.items()))
        signature = hmac.new(
            self.config.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    async def make_request(self, method: str, endpoint: str, params: Dict[str, Any] = None,
                          signed: bool = False, stream: bool = False) -> Dict[str, Any]:
        """发送HTTP请求"""
        await self.rate_limiter.acquire()
        
        url = f"{self.config.base_url}{endpoint}"
        params = params or {}
        
        # 准备参数
        params = self.prepare_params(params)
        
        # 添加时间戳
        if signed:
            params['timestamp'] = self.get_server_time()
            
            # 验证时间戳
            if not self.validate_timestamp(params['timestamp']):
                await self.sync_server_time()
                params['timestamp'] = self.get_server_time()
        
        # 创建签名
        if signed and self.config.api_secret:
            params['signature'] = self.create_signature(params)
        
        # 请求头
        headers = {
            'Content-Type': 'application/json',
            'X-MBX-APIKEY': self.config.api_key or '',
            'User-Agent': f'MarketPrism/{self.config.name}/1.0'
        }
        
        # 构建请求参数，包含代理配置
        request_kwargs = {
            'headers': headers
        }
        
        # 添加代理配置
        if self.config.http_proxy:
            request_kwargs['proxy'] = self.config.http_proxy
        
        # 根据方法添加参数
        if method == 'GET':
            request_kwargs['params'] = params
        else:
            request_kwargs['json'] = params
        
        # 发送请求
        try:
            self.stats['requests_sent'] += 1
            
            response = await self.session_manager.request(
                method, url,
                session_name=f"{self.config.name}_session",
                **request_kwargs
            )

            try:
                if response.status == 200:
                    data = await response.json()
                    self.stats['requests_successful'] += 1
                    return data
                else:
                    # 尝试解析错误响应
                    try:
                        error_data = await response.json()
                    except:
                        error_data = {'code': -1000, 'msg': f'HTTP {response.status}'}

                    error_info = BinanceErrorHandler.handle_error(
                        error_data.get('code', -1000),
                        error_data.get('msg', 'Unknown error'),
                        {'endpoint': endpoint, 'params': params}
                    )

                    self.stats['requests_failed'] += 1
                    logger.error(f"API请求失败: {error_info}")

                    # 根据错误类型决定是否重试
                    if error_info['severity'] == 'critical':
                        await self.sync_server_time()

                    raise Exception(f"API Error {error_info['code']}: {error_info['message']}")
            finally:
                response.close()

        except Exception as e:
            # 只有在不是API错误的情况下才增加失败计数
            # API错误已经在上面的代码块中计数了
            if "API Error" not in str(e):
                self.stats['requests_failed'] += 1
            logger.error(f"请求异常: {e}")
            raise
    
    # WebSocket连接管理
    async def connect_websocket(self, streams: List[str] = None):
        """连接WebSocket"""
        if self.ws_connection and not self.ws_connection.closed:
            return
        
        try:
            ws_url = self.config.ws_url
            if streams:
                ws_url += f"/stream?streams={'/'.join(streams)}"
            
            # WebSocket连接参数
            ws_kwargs = {
                'ping_interval': self.config.ws_ping_interval,
                'ping_timeout': self.config.ws_ping_timeout,
                'close_timeout': 10
            }
            
            # 添加代理支持
            if self.config.ws_proxy:
                ws_kwargs['proxy'] = self.config.ws_proxy
            
            self.ws_connection = await websockets.connect(ws_url, **ws_kwargs)
            
            # 启动消息处理循环
            asyncio.create_task(self._ws_message_loop())
            
            logger.info(f"{self.config.name} WebSocket连接成功")
            
        except Exception as e:
            logger.error(f"{self.config.name} WebSocket连接失败: {e}")
            raise
    
    async def _ws_message_loop(self):
        """WebSocket消息处理循环"""
        try:
            async for message in self.ws_connection:
                try:
                    data = json.loads(message)
                    self.stats['ws_messages_received'] += 1
                    
                    # 调用处理器
                    stream = data.get('stream')
                    if stream in self.ws_handlers:
                        await self.ws_handlers[stream](data['data'])
                    
                except json.JSONDecodeError as e:
                    logger.warning(f"WebSocket消息解析失败: {e}")
                except Exception as e:
                    logger.error(f"WebSocket消息处理失败: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning(f"{self.config.name} WebSocket连接关闭")
            self.stats['ws_reconnections'] += 1
            
            # 自动重连
            await asyncio.sleep(5)
            await self.connect_websocket(list(self.ws_subscriptions))
            
        except Exception as e:
            logger.error(f"WebSocket消息循环异常: {e}")
    
    def subscribe(self, stream: str, handler: Callable):
        """订阅WebSocket流"""
        self.ws_handlers[stream] = handler
        self.ws_subscriptions.add(stream)
    
    def unsubscribe(self, stream: str):
        """取消订阅WebSocket流"""
        self.ws_handlers.pop(stream, None)
        self.ws_subscriptions.discard(stream)
    
    async def close_websocket(self):
        """关闭WebSocket连接"""
        if self.ws_connection and not self.ws_connection.closed:
            await self.ws_connection.close()
            logger.info(f"{self.config.name} WebSocket连接已关闭")
    
    # 统一API方法
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """获取行情数据"""
        endpoints = {
            'binance': '/api/v3/ticker/24hr',
            'okx': '/api/v5/market/ticker',
            'deribit': '/api/v2/public/ticker'
        }
        
        endpoint = endpoints.get(self.config.name.lower(), '/api/v3/ticker/24hr')
        params = {'symbol': symbol} if self.config.name.lower() == 'binance' else {'instId': symbol}
        
        return await self.make_request('GET', endpoint, params)
    
    async def get_orderbook(self, symbol: str, limit: int = 100) -> Dict[str, Any]:
        """获取订单簿"""
        endpoints = {
            'binance': '/api/v3/depth',
            'okx': '/api/v5/market/books',
            'deribit': '/api/v2/public/get_order_book'
        }
        
        endpoint = endpoints.get(self.config.name.lower(), '/api/v3/depth')
        params = {
            'symbol': symbol,
            'limit': limit
        }
        
        return await self.make_request('GET', endpoint, params)
    
    async def get_trades(self, symbol: str, limit: int = 500) -> Dict[str, Any]:
        """获取最近交易"""
        endpoints = {
            'binance': '/api/v3/trades',
            'okx': '/api/v5/market/trades',
            'deribit': '/api/v2/public/get_last_trades_by_instrument'
        }
        
        endpoint = endpoints.get(self.config.name.lower(), '/api/v3/trades')
        params = {
            'symbol': symbol,
            'limit': limit
        }
        
        return await self.make_request('GET', endpoint, params)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        uptime = time.time() - self.stats['start_time']
        success_rate = (self.stats['requests_successful'] / 
                       max(1, self.stats['requests_sent']))
        
        return {
            'exchange': self.config.name,
            'uptime_seconds': uptime,
            'connected': self.connected,
            'requests_sent': self.stats['requests_sent'],
            'requests_successful': self.stats['requests_successful'],
            'requests_failed': self.stats['requests_failed'],
            'success_rate': success_rate,
            'requests_per_second': self.stats['requests_sent'] / max(1, uptime),
            'ws_messages_received': self.stats['ws_messages_received'],
            'ws_reconnections': self.stats['ws_reconnections'],
            'precision_adjustments': self.stats['precision_adjustments'],
            'time_syncs': self.stats['time_syncs'],
            'server_time_offset': self.server_time_offset,
            'ws_connected': self.ws_connection and not self.ws_connection.closed,
            'subscriptions': len(self.ws_subscriptions)
        }
    
    async def _ping_loop(self):
        """Ping循环维护连接"""
        while self.connected and self.ws_connection:
            try:
                await asyncio.sleep(300)  # 5分钟间隔
                if self.connected and self.ws_connection:
                    await self._send_ping()
            except asyncio.CancelledError:
                logger.info("Ping循环被取消")
                break
            except Exception as e:
                logger.error(f"Ping循环错误: {e}")
                await asyncio.sleep(30)  # 错误后等待30秒
    
    async def _okx_ping_loop(self):
        """OKX特定的ping循环维护连接"""
        while self.connected and self.ws_connection:
            try:
                await asyncio.sleep(25)  # OKX要求30秒内必须有活动
                if self.connected and self.ws_connection:
                    # OKX使用字符串ping
                    await self.ws_connection.send("ping")
                    self.last_ping_time = time.time()
                    self.message_stats['pings_sent'] += 1
                    logger.debug("发送OKX字符串ping")
            except asyncio.CancelledError:
                logger.info("OKX Ping循环被取消")
                break
            except Exception as e:
                logger.error(f"OKX Ping循环错误: {e}")
                await asyncio.sleep(30)  # 错误后等待30秒

    async def _send_ping(self):
        """发送ping消息"""
        try:
            ping_message = {"method": "ping", "id": int(time.time() * 1000)}
            await self.ws_connection.send(json.dumps(ping_message))
            self.last_ping = time.time()
            self.last_ping_time = self.last_ping
            self.message_stats['pings_sent'] += 1
            logger.debug("发送ping消息")
        except Exception as e:
            logger.error(f"发送ping失败: {e}")

    async def _handle_login_response(self, response_data: Dict[str, Any]):
        """处理登录响应"""
        try:
            if response_data.get("code") == "0" or response_data.get("success"):
                logger.info("登录成功")
                self.stats['successful_logins'] = self.stats.get('successful_logins', 0) + 1
                self.okx_stats['successful_logins'] += 1
                self.message_stats['successful_logins'] += 1
                self.session_active = True
                self.is_authenticated = True
            else:
                logger.error(f"登录失败: {response_data}")
                self.stats['failed_logins'] = self.stats.get('failed_logins', 0) + 1
                self.okx_stats['failed_logins'] += 1
                self.message_stats['failed_logins'] += 1
                self.session_active = False
                self.is_authenticated = False
        except Exception as e:
            logger.error(f"处理登录响应失败: {e}")

    async def _implement_backoff_strategy(self):
        """实现退避策略"""
        try:
            # 获取当前失败次数
            consecutive_failures = getattr(self, 'consecutive_failures', 0)
            
            # 计算退避延迟（指数退避）
            delay = min(300, 5 * (2 ** consecutive_failures))  # 最大5分钟
            
            logger.info(f"实施退避策略，等待 {delay} 秒")
            await asyncio.sleep(delay)
            
            # 增加失败计数
            self.consecutive_failures = consecutive_failures + 1
            self.stats['backoff_delays'] = self.stats.get('backoff_delays', 0) + 1
            
        except Exception as e:
            logger.error(f"退避策略实现失败: {e}")
    
    async def _perform_login(self):
        """执行OKX登录（collector核心功能）"""
        try:
            self.okx_stats['login_attempts'] += 1
            self.message_stats['login_attempts'] += 1
            
            # 构建登录消息
            timestamp = str(int(time.time()))
            method = "GET"
            request_path = "/users/self/verify"
            
            # 构建签名
            sign_str = timestamp + method + request_path
            signature = hmac.new(
                self.config.api_secret.encode('utf-8'),
                sign_str.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            login_message = {
                "op": "login",
                "args": [{
                    "apiKey": self.config.api_key,
                    "passphrase": self.config.passphrase,
                    "timestamp": timestamp,
                    "sign": signature
                }]
            }
            
            if self.ws_connection:
                await self.ws_connection.send(json.dumps(login_message))
                logger.info("OKX登录消息已发送")
            else:
                logger.error("WebSocket连接不可用")
                
        except Exception as e:
            logger.error(f"OKX登录失败: {e}")
    
    async def add_symbol_subscription(self, symbol: str, data_types: List[str]):
        """动态添加符号订阅（collector核心功能）"""
        try:
            # 构建订阅参数
            params = []
            symbol_lower = symbol.lower().replace('-', '')
            
            for data_type in data_types:
                if data_type == "trade":
                    params.append(f"{symbol_lower}@trade")
                elif data_type == "orderbook":
                    params.append(f"{symbol_lower}@depth@100ms")
                elif data_type == "ticker":
                    params.append(f"{symbol_lower}@ticker")
            
            # 发送订阅消息
            subscribe_message = {
                "method": "SUBSCRIBE",
                "params": params,
                "id": int(time.time() * 1000)
            }
            
            if self.ws_connection:
                await self.ws_connection.send(json.dumps(subscribe_message))
                logger.info(f"已添加 {symbol} 的订阅: {data_types}")
            
        except Exception as e:
            logger.error(f"添加符号订阅失败: {e}")
    
    async def remove_symbol_subscription(self, symbol: str, data_types: List[str]):
        """动态移除符号订阅（collector核心功能）"""
        try:
            # 构建取消订阅参数
            params = []
            symbol_lower = symbol.lower().replace('-', '')
            
            for data_type in data_types:
                if data_type == "trade":
                    params.append(f"{symbol_lower}@trade")
                elif data_type == "orderbook":
                    params.append(f"{symbol_lower}@depth@100ms")
                elif data_type == "ticker":
                    params.append(f"{symbol_lower}@ticker")
            
            # 发送取消订阅消息
            unsubscribe_message = {
                "method": "UNSUBSCRIBE",
                "params": params,
                "id": int(time.time() * 1000)
            }
            
            if self.ws_connection:
                await self.ws_connection.send(json.dumps(unsubscribe_message))
                logger.info(f"已移除 {symbol} 的订阅: {data_types}")
            
        except Exception as e:
            logger.error(f"移除符号订阅失败: {e}")
    
    async def _handle_rate_limit_message(self, message: Dict[str, Any]):
        """处理速率限制消息（collector核心功能）"""
        try:
            error_code = message.get("error", {}).get("code")
            if error_code == -1003:
                logger.warning("收到速率限制消息，实施退避策略")
                await self._implement_backoff_strategy()
            else:
                logger.info(f"处理速率限制消息: {message}")
                
        except Exception as e:
            logger.error(f"处理速率限制消息失败: {e}")
    
    def get_enhanced_stats(self) -> Dict[str, Any]:
        """获取增强统计信息（collector核心功能）"""
        base_stats = self.get_statistics()
        
        enhanced_stats = {
            **base_stats,
            "binance_specific": {
                "ping_pong": {
                    "pings_sent": self.message_stats['pings_sent'],
                    "pongs_received": self.message_stats['pongs_received']
                },
                "session": {
                    "session_active": self.session_active
                },
                "connection": {
                    "consecutive_failures": self.consecutive_failures
                }
            },
            "okx_specific": {
                "login_attempts": self.okx_stats['login_attempts'],
                "successful_logins": self.okx_stats['successful_logins'],
                "failed_logins": self.okx_stats['failed_logins']
            },
            "collector_stats": {
                "ping_interval": self.ping_interval,
                "ping_timeout": self.ping_timeout,
                "max_request_weight": self.max_request_weight,
                "is_authenticated": self.is_authenticated
            }
        }
        
        return enhanced_stats

    async def close(self):
        """关闭连接器"""
        await self.close_websocket()
        
        # 如果拥有会话管理器，则关闭它
        if self._owns_session_manager:
            await self.session_manager.close()
        
        self.connected = False
        logger.info(f"{self.config.name} 连接器已关闭")


# 预定义交易所配置
EXCHANGE_CONFIGS = {
    'binance': ExchangeConfig(
        exchange=Exchange.BINANCE,
        base_url='https://api.binance.com',
        ws_url='wss://stream.binance.com:9443/ws',
        price_precision=8,
        quantity_precision=8,
        rate_limit_requests=1200
    ),
    'okx': ExchangeConfig(
        exchange=Exchange.OKX,
        base_url='https://www.okx.com',
        ws_url='wss://ws.okx.com:8443/ws/v5/public',
        price_precision=8,
        quantity_precision=8,
        rate_limit_requests=600
    ),
    'deribit': ExchangeConfig(
        exchange=Exchange.DERIBIT,
        base_url='https://www.deribit.com',
        ws_url='wss://www.deribit.com/ws/api/v2',
        price_precision=4,
        quantity_precision=4,
        rate_limit_requests=1000
    )
}


def create_exchange_connector(exchange: str, config_overrides: Dict[str, Any] = None) -> EnhancedExchangeConnector:
    """创建交易所连接器"""
    if exchange.lower() not in EXCHANGE_CONFIGS:
        raise ValueError(f"不支持的交易所: {exchange}")
    
    config = EXCHANGE_CONFIGS[exchange.lower()]
    
    # 应用配置覆盖
    if config_overrides:
        for key, value in config_overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)
    
    return EnhancedExchangeConnector(config)