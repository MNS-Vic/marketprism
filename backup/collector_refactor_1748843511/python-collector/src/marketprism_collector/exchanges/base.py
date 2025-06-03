"""
交易所适配器基类

定义了所有交易所适配器的通用接口和基础功能
"""

import asyncio
import json
import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List, Callable
import structlog
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException
import aiohttp

from ..types import (
    NormalizedTrade, NormalizedOrderBook, 
    NormalizedKline, NormalizedTicker,
    ExchangeConfig, DataType
)


class WebSocketWrapper:
    """aiohttp WebSocket包装器，兼容websockets接口"""
    
    def __init__(self, ws: aiohttp.ClientWebSocketResponse, session: aiohttp.ClientSession):
        self.ws = ws
        self.session = session
        self.closed = False
    
    async def send(self, data: str):
        """发送消息"""
        if not self.closed:
            await self.ws.send_str(data)
    
    async def close(self):
        """关闭连接"""
        if not self.closed:
            await self.ws.close()
            await self.session.close()
            self.closed = True
    
    def __aiter__(self):
        """异步迭代器"""
        return self
    
    async def __anext__(self):
        """异步迭代下一个消息"""
        if self.closed:
            raise StopAsyncIteration
        
        try:
            msg = await self.ws.receive()
            
            if msg.type == aiohttp.WSMsgType.TEXT:
                return msg.data
            elif msg.type == aiohttp.WSMsgType.BINARY:
                return msg.data.decode('utf-8')
            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                self.closed = True
                raise StopAsyncIteration
            else:
                # 跳过其他类型的消息
                return await self.__anext__()
                
        except Exception as e:
            self.closed = True
            raise StopAsyncIteration


class ExchangeAdapter(ABC):
    """交易所适配器基类"""
    
    def __init__(self, config: ExchangeConfig):
        self.config = config
        self.logger = structlog.get_logger(__name__).bind(
            exchange=config.exchange.value,
            market_type=config.market_type.value
        )
        
        # WebSocket连接
        self.ws_connection = None
        self.is_connected = False
        self.reconnect_count = 0
        
        # 数据回调
        self.callbacks: Dict[DataType, List[Callable]] = {
            DataType.TRADE: [],
            DataType.ORDERBOOK: [],
            DataType.KLINE: [],
            DataType.TICKER: [],
            DataType.FUNDING_RATE: [],
            DataType.OPEN_INTEREST: [],
            DataType.LIQUIDATION: [],
            DataType.TOP_TRADER_LONG_SHORT_RATIO: [],
            DataType.MARKET_LONG_SHORT_RATIO: []
        }
        
        # 原始数据回调（用于OrderBook Manager）
        self.raw_callbacks: Dict[str, List[Callable]] = {
            'depth': [],  # 深度数据原始回调
            'trade': [],  # 交易数据原始回调
            'ticker': [] # 行情数据原始回调
        }
        
        # 统计信息
        self.stats = {
            'messages_received': 0,
            'messages_processed': 0,
            'errors': 0,
            'last_message_time': None,
            'connected_at': None
        }
    
    async def start(self) -> bool:
        """启动交易所连接"""
        try:
            self.logger.info("启动交易所适配器")
            
            # 建立WebSocket连接
            success = await self.connect()
            if success:
                # 订阅数据流
                await self.subscribe_data_streams()
                return True
            
            return False
            
        except Exception as e:
            self.logger.error("启动适配器失败", error=str(e))
            return False
    
    async def stop(self):
        """停止交易所连接"""
        try:
            self.logger.info("停止交易所适配器")
            
            if self.ws_connection:
                await self.ws_connection.close()
                self.ws_connection = None
            
            self.is_connected = False
            
        except Exception as e:
            self.logger.error("停止适配器失败", error=str(e))
    
    async def connect(self) -> bool:
        """建立WebSocket连接"""
        try:
            self.logger.info("连接WebSocket", url=self.config.ws_url)
            
            # 获取代理设置 - TDD优化：优先使用配置中的代理，然后是环境变量
            proxy_config = self._get_effective_proxy_config()
            
            if proxy_config and proxy_config.get('enabled', True):
                return await self._connect_with_proxy(proxy_config)
            else:
                return await self._connect_direct()
                
        except Exception as e:
            self.logger.error("WebSocket连接失败", error=str(e))
            return False
    
    def _get_effective_proxy_config(self) -> Optional[Dict[str, Any]]:
        """获取有效的代理配置 - TDD优化：配置优先，环境变量备选"""
        # 1. 优先使用ExchangeConfig中的代理配置
        if hasattr(self.config, 'proxy') and self.config.proxy:
            if self.config.proxy.get('enabled', True):
                self.logger.info("使用配置文件中的代理设置")
                return self.config.proxy
            else:
                self.logger.info("代理在配置中被明确禁用")
                return None
        
        # 2. 回退到环境变量（向后兼容）
        env_proxy = self._get_env_proxy_config()
        if env_proxy:
            self.logger.info("使用环境变量中的代理设置")
            return env_proxy
            
        return None
    
    def _get_env_proxy_config(self) -> Optional[Dict[str, Any]]:
        """从环境变量获取代理配置 - 向后兼容"""
        http_proxy = os.getenv('http_proxy') or os.getenv('HTTP_PROXY')
        https_proxy = os.getenv('https_proxy') or os.getenv('HTTPS_PROXY')
        all_proxy = os.getenv('ALL_PROXY') or os.getenv('all_proxy')
        
        if all_proxy:
            if 'socks' in all_proxy.lower():
                return {'enabled': True, 'socks5': all_proxy}
            else:
                return {'enabled': True, 'http': all_proxy}
        elif https_proxy or http_proxy:
            return {
                'enabled': True,
                'http': http_proxy,
                'https': https_proxy or http_proxy
            }
        
        return None
    
    async def _connect_with_proxy(self, proxy_config: Dict[str, Any]) -> bool:
        """通过代理建立连接 - TDD优化：支持多种代理类型"""
        # SOCKS代理优先
        if 'socks5' in proxy_config or 'socks4' in proxy_config:
            socks_url = proxy_config.get('socks5') or proxy_config.get('socks4')
            return await self._connect_socks_proxy(socks_url)
        
        # HTTP/HTTPS代理
        elif 'http' in proxy_config or 'https' in proxy_config:
            proxy_url = proxy_config.get('https') or proxy_config.get('http')
            return await self._connect_http_proxy(proxy_url)
        
        # 未知代理类型，回退到直连
        else:
            self.logger.warning("未知的代理配置，回退到直连", config=proxy_config)
            return await self._connect_direct()
    
    async def _connect_socks_proxy(self, socks_url: str) -> bool:
        """通过SOCKS代理连接"""
        self.logger.info("使用SOCKS代理连接WebSocket", proxy=socks_url)
        
        try:
            import aiohttp_socks
            
            # 创建SOCKS代理连接器
            connector = aiohttp_socks.ProxyConnector.from_url(socks_url)
            session = aiohttp.ClientSession(connector=connector)
            
            # 通过SOCKS代理建立WebSocket连接
            ws = await session.ws_connect(
                self.config.ws_url,
                timeout=aiohttp.ClientTimeout(total=20)
            )
            
            # 包装aiohttp WebSocket为兼容接口
            self.ws_connection = WebSocketWrapper(ws, session)
            return True
            
        except ImportError:
            self.logger.warning("aiohttp_socks库未安装，无法使用SOCKS代理")
            return False
        except Exception as e:
            if 'session' in locals():
                await session.close()
            raise e
    
    async def _connect_http_proxy(self, proxy_url: str) -> bool:
        """通过HTTP代理连接"""
        self.logger.info("使用HTTP代理连接WebSocket", proxy=proxy_url)
        
        try:
            import aiohttp
            
            # 创建代理连接器
            connector = aiohttp.TCPConnector()
            session = aiohttp.ClientSession(connector=connector)
            
            # 通过HTTP代理建立WebSocket连接
            ws = await session.ws_connect(
                self.config.ws_url,
                proxy=proxy_url,
                timeout=aiohttp.ClientTimeout(total=20)
            )
            
            self.ws_connection = WebSocketWrapper(ws, session)
            return True
            
        except Exception as e:
            if 'session' in locals():
                await session.close()
            raise e
    
    async def _connect_direct(self) -> bool:
        """直接连接（无代理）"""
        self.logger.info("直接连接WebSocket（无代理）")
        
        try:
            import websockets
            
            # 直接WebSocket连接
            self.ws_connection = await websockets.connect(
                self.config.ws_url,
                ping_interval=self.config.ping_interval,
                ping_timeout=10
            )
            
            return True
            
        except Exception as e:
            self.logger.error("直接WebSocket连接失败", error=str(e))
            return False
    
    async def _message_loop(self):
        """消息处理循环"""
        try:
            async for message in self.ws_connection:
                await self._process_message(message)
                
        except (ConnectionClosed, StopAsyncIteration):
            self.logger.warning("WebSocket连接已关闭")
            self.is_connected = False
            await self._handle_reconnect()
            
        except (WebSocketException, aiohttp.ClientError) as e:
            self.logger.error("WebSocket错误", error=str(e))
            self.is_connected = False
            await self._handle_reconnect()
            
        except Exception as e:
            self.logger.error("消息循环错误", error=str(e))
            self.stats['errors'] += 1
    
    async def _process_message(self, message: str):
        """处理接收到的消息"""
        try:
            self.stats['messages_received'] += 1
            self.stats['last_message_time'] = datetime.utcnow()
            
            # 添加调试日志
            if self.stats['messages_received'] % 100 == 1:  # 每100条消息记录一次
                self.logger.debug("WebSocket消息接收", 
                                count=self.stats['messages_received'],
                                message_preview=message[:100])
            
            # 解析JSON消息
            data = json.loads(message)
            
            # 处理不同类型的数据
            await self.handle_message(data)
            
            self.stats['messages_processed'] += 1
            
        except Exception as e:
            self.logger.error("处理消息失败", error=str(e), message=message[:200])
            self.stats['errors'] += 1
    
    async def _handle_reconnect(self):
        """处理重连"""
        if self.reconnect_count >= self.config.reconnect_attempts:
            self.logger.error("达到最大重连次数，停止重连")
            return
        
        self.reconnect_count += 1
        self.logger.info(
            "尝试重连", 
            attempt=self.reconnect_count,
            max_attempts=self.config.reconnect_attempts
        )
        
        # 等待重连延迟
        await asyncio.sleep(self.config.reconnect_delay)
        
        # 尝试重连
        success = await self.connect()
        if success:
            await self.subscribe_data_streams()
    
    def register_callback(self, data_type: DataType, callback: Callable):
        """注册数据回调函数"""
        self.callbacks[data_type].append(callback)
    
    def register_raw_callback(self, data_type: str, callback: Callable):
        """注册原始数据回调函数"""
        if data_type in self.raw_callbacks:
            self.raw_callbacks[data_type].append(callback)
    
    async def _emit_data(self, data_type: DataType, data: Any):
        """发送数据到回调函数"""
        for callback in self.callbacks[data_type]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                self.logger.error(
                    "回调函数执行失败",
                    data_type=data_type.value,
                    error=str(e)
                )
    
    async def _emit_raw_data(self, data_type: str, exchange: str, symbol: str, raw_data: Dict[str, Any]):
        """发送原始数据到回调函数"""
        for callback in self.raw_callbacks.get(data_type, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(exchange, symbol, raw_data)
                else:
                    callback(exchange, symbol, raw_data)
            except Exception as e:
                self.logger.error(
                    "原始数据回调函数执行失败",
                    data_type=data_type,
                    error=str(e)
                )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            'is_connected': self.is_connected,
            'reconnect_count': self.reconnect_count,
            'exchange': self.config.exchange.value,
            'market_type': self.config.market_type.value
        }
    
    # 抽象方法 - 子类必须实现
    
    @abstractmethod
    async def handle_message(self, data: Dict[str, Any]):
        """处理消息数据 - 子类实现具体的消息解析逻辑"""
        pass
    
    @abstractmethod
    async def subscribe_data_streams(self):
        """订阅数据流 - 子类实现具体的订阅逻辑"""
        pass
    
    @abstractmethod
    async def normalize_trade(self, raw_data: Dict[str, Any]) -> Optional[NormalizedTrade]:
        """标准化交易数据"""
        pass
    
    @abstractmethod
    async def normalize_orderbook(self, raw_data: Dict[str, Any]) -> Optional[NormalizedOrderBook]:
        """标准化订单簿数据"""
        pass
    
    @abstractmethod
    async def normalize_kline(self, raw_data: Dict[str, Any]) -> Optional[NormalizedKline]:
        """标准化K线数据"""
        pass
    
    @abstractmethod
    async def normalize_ticker(self, raw_data: Dict[str, Any]) -> Optional[NormalizedTicker]:
        """标准化行情数据"""
        pass
    
    # 工具方法
    
    def _safe_decimal(self, value: Any) -> Decimal:
        """安全转换为Decimal"""
        try:
            if value is None or value == '':
                return Decimal('0')
            return Decimal(str(value))
        except:
            return Decimal('0')
    
    def _safe_int(self, value: Any) -> int:
        """安全转换为int"""
        try:
            if value is None or value == '':
                return 0
            return int(float(str(value)))
        except:
            return 0
    
    def _safe_timestamp(self, timestamp: Any) -> datetime:
        """安全转换时间戳"""
        try:
            if isinstance(timestamp, (int, float)):
                # 处理毫秒时间戳
                if timestamp > 1e10:
                    timestamp = timestamp / 1000
                return datetime.utcfromtimestamp(timestamp)
            else:
                return datetime.utcnow()
        except:
            return datetime.utcnow()


# MockExchangeAdapter已移除 - 使用真实的交易所适配器进行测试
# 如需测试数据，请使用真实的交易所API或测试环境