"""
Deribit交易所适配器 - 统一版本

实现Deribit衍生品交易所的数据收集功能
整合aiohttp WebSocket支持、代理配置、重连机制
"""

import json
import asyncio
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, List
import structlog
import aiohttp

from .base import ExchangeAdapter
from ..data_types import (
    NormalizedTrade, NormalizedOrderBook, NormalizedKline, 
    NormalizedTicker, DataType, OrderBookEntry, Exchange
)

# 导入统一代理配置
# 使用统一的NetworkConfig
import sys
sys.path.append('/Users/yao/Documents/GitHub/marketprism')
from config.app_config import NetworkConfig


class DeribitAdapter(ExchangeAdapter):
    """Deribit交易所适配器 - 统一增强版本"""
    
    def __init__(self, config):
        super().__init__(config)
        self.logger = structlog.get_logger(__name__).bind(exchange="deribit")
        
        # 添加exchange属性
        self.exchange = Exchange.DERIBIT
        
        # Deribit特定配置
        self.request_id = 1
        self.access_token = None
        self.token_expires_at = None

        # REST API session
        self.session = None
        self.base_url = config.base_url or "https://www.deribit.com"

        # aiohttp WebSocket支持
        self.aiohttp_session = None
        self.aiohttp_ws = None

        # 心跳配置
        self.heartbeat_interval = 60  # 60秒心跳间隔
        self.last_heartbeat = None
        
        # 统计信息增强
        self.enhanced_stats = {
            'messages_received': 0,
            'messages_processed': 0,
            'subscription_errors': 0,
            'reconnect_attempts': 0,
            'data_quality_score': 100.0
        }
        
        self.logger.info("Deribit统一适配器初始化完成")
    
    async def get_server_time(self) -> int:
        """获取服务器时间"""
        try:
            if not self.session:
                await self._ensure_session()
            
            url = f"{self.base_url}/api/v2/public/get_time"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'result' in data:
                        return data['result']
                    else:
                        raise Exception(f"Deribit API error: {data}")
                else:
                    raise Exception(f"Failed to get server time: {response.status}")
        except Exception as e:
            self.logger.error("获取服务器时间失败", exc_info=True)
            raise
    
    async def get_exchange_info(self) -> Dict[str, Any]:
        """获取交易所信息"""
        try:
            if not self.session:
                await self._ensure_session()
            
            url = f"{self.base_url}/api/v2/public/get_instruments"
            params = {'currency': 'BTC', 'kind': 'future'}  # 默认获取BTC期货
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(f"Failed to get exchange info: {response.status}")
        except Exception as e:
            self.logger.error("获取交易所信息失败", exc_info=True)
            raise
    
    async def get_orderbook_snapshot(self, symbol: str, limit: int = 100) -> Dict[str, Any]:
        """获取订单薄快照"""
        try:
            if not self.session:
                await self._ensure_session()
            
            url = f"{self.base_url}/api/v2/public/get_order_book"
            params = {
                'instrument_name': symbol,
                'depth': limit
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(f"Failed to get orderbook: {response.status}")
        except Exception as e:
            self.logger.error("获取订单薄快照失败", symbol=symbol, exc_info=True)
            raise
    
    async def _ensure_session(self):
        """确保HTTP session存在（包含代理配置）"""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30)
            
            # 从环境变量获取代理配置
            import os
            proxy = None
            https_proxy = os.getenv('https_proxy') or os.getenv('HTTPS_PROXY')
            http_proxy = os.getenv('http_proxy') or os.getenv('HTTP_PROXY')
            
            if https_proxy or http_proxy:
                proxy = https_proxy or http_proxy
                self.logger.info("使用代理连接Deribit API", proxy=proxy)
            
            # 创建带代理的session（aiohttp自动使用环境变量）
            self.session = aiohttp.ClientSession(timeout=timeout, trust_env=True)

    async def authenticate(self) -> bool:
        """Deribit认证 - 符合官方API规范"""
        try:
            # 如果已有有效token，直接返回
            if self.access_token and self.token_expires_at:
                if datetime.now(timezone.utc) < self.token_expires_at:
                    return True

            # 构建认证请求（JSON-RPC格式）
            auth_request = {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": "public/auth",
                "params": {
                    "grant_type": "client_credentials",
                    "client_id": getattr(self.config, 'api_key', ''),
                    "client_secret": getattr(self.config, 'api_secret', ''),
                    "scope": "session:test trade:read"  # 基础权限
                }
            }

            # 如果没有API密钥，跳过认证（仅使用公共方法）
            if not auth_request["params"]["client_id"]:
                self.logger.info("未配置API密钥，仅使用公共方法")
                return True

            # 发送认证请求
            if self.aiohttp_ws:
                await self.aiohttp_ws.send_str(json.dumps(auth_request))
                self.request_id += 1

                # 等待认证响应
                async for msg in self.aiohttp_ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        response = json.loads(msg.data)
                        if response.get('id') == auth_request['id']:
                            if 'result' in response:
                                result = response['result']
                                self.access_token = result.get('access_token')
                                expires_in = result.get('expires_in', 3600)
                                self.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                                self.logger.info("Deribit认证成功", expires_in=expires_in)
                                return True
                            else:
                                error = response.get('error', {})
                                self.logger.error("Deribit认证失败", error=error)
                                return False
                        break

            return False

        except Exception as e:
            self.logger.error("Deribit认证异常", exc_info=True)
            return False

    async def setup_heartbeat(self) -> bool:
        """设置心跳机制 - 符合Deribit API规范"""
        try:
            heartbeat_request = {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": "public/set_heartbeat",
                "params": {
                    "interval": self.heartbeat_interval
                }
            }

            if self.aiohttp_ws:
                await self.aiohttp_ws.send_str(json.dumps(heartbeat_request))
                self.request_id += 1
                self.last_heartbeat = datetime.now(timezone.utc)
                self.logger.info("Deribit心跳设置成功", interval=self.heartbeat_interval)
                return True

            return False

        except Exception as e:
            self.logger.error("设置Deribit心跳失败", exc_info=True)
            return False

    async def send_heartbeat(self):
        """发送心跳响应"""
        try:
            if not self.aiohttp_ws:
                return

            # Deribit心跳响应格式
            heartbeat_response = {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": "public/test",
                "params": {}
            }

            await self.aiohttp_ws.send_str(json.dumps(heartbeat_response))
            self.request_id += 1
            self.last_heartbeat = datetime.now(timezone.utc)
            self.logger.debug("发送Deribit心跳响应")

        except Exception as e:
            self.logger.error("发送心跳失败", exc_info=True)
    
    async def subscribe_orderbook(self, symbol: str, depth: int = 20):
        """订阅订单薄数据"""
        try:
            # Deribit的订阅方式
            channels = [f"book.{symbol}.none.{depth}.100ms"]
            await self._subscribe_channels(channels)
            self.logger.info("订阅订单薄", symbol=symbol)
        except Exception as e:
            self.logger.error("订阅订单薄失败", symbol=symbol, exc_info=True)
            raise
    
    async def subscribe_trades(self, symbol: str):
        """订阅交易数据"""
        try:
            channels = [f"trades.{symbol}.100ms"]
            await self._subscribe_channels(channels)
            self.logger.info("订阅交易数据", symbol=symbol)
        except Exception as e:
            self.logger.error("订阅交易数据失败", symbol=symbol, exc_info=True)
            raise
    
    async def _subscribe_channels(self, channels: List[str]):
        """订阅指定通道"""
        subscribe_msg = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "public/subscribe",
            "params": {
                "channels": channels
            }
        }
        
        # 根据连接类型发送消息
        if self.aiohttp_ws:
            await self.aiohttp_ws.send_str(json.dumps(subscribe_msg))
        elif self.ws_connection:
            await self.ws_connection.send(json.dumps(subscribe_msg))
        else:
            raise Exception("无可用的WebSocket连接")
            
        self.request_id += 1
    
    async def close(self):
        """关闭连接"""
        try:
            if self.session:
                await self.session.close()
                self.session = None
            await self.disconnect()
        except Exception as e:
            self.logger.error("关闭连接失败", exc_info=True)
    
    async def connect(self) -> bool:
        """简化的WebSocket连接方法 - 参考成功的测试脚本"""
        try:
            self.logger.info("连接Deribit WebSocket", url=self.config.ws_url)
            
            # 直接使用环境变量获取代理（和测试脚本一致）
            import os
            proxy_url = os.getenv('https_proxy') or os.getenv('http_proxy')
            
            if proxy_url:
                self.logger.info("使用代理连接Deribit", proxy=proxy_url)
            else:
                self.logger.info("无代理直接连接Deribit")
            
            # 创建aiohttp会话（和测试脚本一致）
            timeout = aiohttp.ClientTimeout(total=10)  # 缩短超时时间
            self.aiohttp_session = aiohttp.ClientSession(timeout=timeout)
            
            self.logger.info("开始WebSocket连接...")
            
            # 使用aiohttp连接WebSocket（符合Deribit API规范）
            # 根据环境决定SSL配置
            ssl_context = None
            if self.config.ws_url.startswith('wss://'):
                # 生产环境启用SSL验证，测试环境可以禁用
                is_test_env = 'test.deribit.com' in self.config.ws_url
                ssl_context = False if is_test_env else None

            self.aiohttp_ws = await self.aiohttp_session.ws_connect(
                self.config.ws_url,
                proxy=proxy_url,
                ssl=ssl_context
            )
            
            self.is_connected = True
            self.stats['connected_at'] = datetime.now(timezone.utc)
            self.enhanced_stats['reconnect_attempts'] = 0
            
            self.logger.info("Deribit WebSocket连接成功！")

            # 执行认证
            auth_success = await self.authenticate()
            if not auth_success:
                self.logger.warning("Deribit认证失败，仅使用公共方法")

            # 设置心跳
            await self.setup_heartbeat()

            # 启动消息处理循环
            asyncio.create_task(self._aiohttp_message_loop())

            return True
            
        except asyncio.TimeoutError as e:
            self.logger.error("Deribit连接超时", error=f"TimeoutError: {str(e)}", timeout="10s")
            if self.aiohttp_session:
                await self.aiohttp_session.close()
            self.is_connected = False
            return False
        except Exception as e:
            self.logger.error("Deribit WebSocket连接失败", 
                            error_type=type(e).__name__, 
                            error_msg=str(e), 
                            error_repr=repr(e))
            if self.aiohttp_session:
                await self.aiohttp_session.close()
            self.is_connected = False
            return False
    
    async def disconnect(self):
        """增强的断开连接方法"""
        try:
            await super().disconnect()
            
            # 关闭aiohttp WebSocket连接
            if self.aiohttp_ws:
                await self.aiohttp_ws.close()
                self.aiohttp_ws = None
            
            # 关闭aiohttp会话
            if self.aiohttp_session:
                await self.aiohttp_session.close()
                self.aiohttp_session = None
                
            self.logger.info("Deribit适配器已断开连接")
            
        except Exception as e:
            self.logger.error("断开Deribit连接失败", exc_info=True)
    
    async def _aiohttp_message_loop(self):
        """aiohttp消息处理循环"""
        try:
            async for msg in self.aiohttp_ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._process_aiohttp_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.logger.error("aiohttp WebSocket错误", error=msg.data)
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSE:
                    self.logger.warning("aiohttp WebSocket连接关闭")
                    break
                    
        except Exception as e:
            self.logger.error("aiohttp消息循环错误", exc_info=True)
            self.enhanced_stats['subscription_errors'] += 1
        finally:
            self.is_connected = False
            if self.is_running:
                await self._handle_aiohttp_reconnect()
    
    async def _process_aiohttp_message(self, message: str):
        """处理aiohttp接收到的消息 - 符合Deribit API规范"""
        try:
            self.enhanced_stats['messages_received'] += 1
            self.stats['last_message_time'] = datetime.now(timezone.utc)

            # 解析JSON消息
            data = json.loads(message)

            # 处理心跳请求
            if data.get('method') == 'heartbeat':
                await self.send_heartbeat()
                return

            # 处理认证响应
            if 'result' in data and 'access_token' in data.get('result', {}):
                self.logger.debug("收到认证响应", token_type=data['result'].get('token_type'))
                return

            # 处理心跳响应
            if data.get('method') == 'public/test' or 'test' in str(data.get('result', '')):
                self.logger.debug("收到心跳响应")
                return

            # 处理订阅通知和其他消息
            await self.handle_message(data)

            self.enhanced_stats['messages_processed'] += 1

        except Exception as e:
            self.logger.error("处理aiohttp消息失败", exc_info=True, message=message[:200])
            self.enhanced_stats['subscription_errors'] += 1
    
    async def _handle_aiohttp_reconnect(self):
        """处理aiohttp重连"""
        if self.enhanced_stats['reconnect_attempts'] >= getattr(self.config, 'reconnect_attempts', 5):
            self.logger.error("达到最大重连次数，停止重连")
            return
        
        self.enhanced_stats['reconnect_attempts'] += 1
        self.logger.info(
            "尝试重连Deribit（aiohttp）", 
            attempt=self.enhanced_stats['reconnect_attempts'],
            max_attempts=getattr(self.config, 'reconnect_attempts', 5)
        )
        
        # 等待重连延迟
        await asyncio.sleep(getattr(self.config, 'reconnect_delay', 5))
        
        # 尝试重连
        success = await self.connect()
        if success:
            await self.subscribe_data_streams()
        
    async def subscribe_data_streams(self):
        """订阅Deribit数据流"""
        try:
            # Deribit使用JSON-RPC 2.0格式
            channels = []
            
            for symbol in self.config.symbols:
                # 根据配置的数据类型订阅相应流
                if DataType.TRADE in self.config.data_types:
                    # 使用高频交易数据流
                    channels.append(f"trades.{symbol}.100ms")
                
                if DataType.ORDERBOOK in self.config.data_types:
                    channels.append(f"book.{symbol}.none.20.100ms")
                
                if DataType.TICKER in self.config.data_types:
                    # 使用高频ticker数据流
                    channels.append(f"ticker.{symbol}.100ms")
            
            # 发送订阅请求
            subscribe_msg = {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": "public/subscribe",
                "params": {
                    "channels": channels
                }
            }
            
            # 根据连接类型发送消息
            if self.aiohttp_ws:
                await self.aiohttp_ws.send_str(json.dumps(subscribe_msg))
            elif self.ws_connection:
                await self.ws_connection.send(json.dumps(subscribe_msg))
            else:
                raise Exception("无可用的WebSocket连接")
                
            self.request_id += 1
            
            self.logger.info("已订阅Deribit数据流", channels=channels, connection_type="aiohttp" if self.aiohttp_ws else "standard")
            
        except Exception as e:
            self.logger.error("订阅Deribit数据流失败", exc_info=True)
            self.enhanced_stats['subscription_errors'] += 1
            raise
    
    async def handle_message(self, data: Dict[str, Any]):
        """处理Deribit消息"""
        try:
            # 记录消息接收（使用安全的debug检查）
            debug_enabled = getattr(self.config, 'debug', False)
            if debug_enabled:
                self.logger.info("收到Deribit消息", message_type=type(data).__name__,
                               data_keys=list(data.keys()) if isinstance(data, dict) else "non-dict")
            
            # 跳过RPC响应消息
            if "id" in data and "result" in data:
                self.logger.info("Deribit订阅确认", result=data["result"])
                return
            
            # 处理通知消息
            if "method" in data and data["method"] == "subscription":
                params = data["params"]
                channel = params["channel"]
                data_item = params["data"]
                
                if debug_enabled:
                    self.logger.info("处理订阅数据", channel=channel, data_type=type(data_item).__name__)
                
                if channel.startswith("trades."):
                    # 处理交易数据（支持单个和批量）
                    if isinstance(data_item, list):
                        for trade_data in data_item:
                            trade = await self.normalize_trade(trade_data, channel)
                            if trade:
                                await self._emit_data(DataType.TRADE, trade)
                    else:
                        trade = await self.normalize_trade(data_item, channel)
                        if trade:
                            await self._emit_data(DataType.TRADE, trade)
                
                elif channel.startswith("book."):
                    # 处理订单簿数据
                    orderbook = await self.normalize_orderbook(data_item, channel)
                    if orderbook:
                        await self._emit_data(DataType.ORDERBOOK, orderbook)
                
                elif channel.startswith("ticker."):
                    # 处理行情数据
                    ticker = await self.normalize_ticker(data_item, channel)
                    if ticker:
                        await self._emit_data(DataType.TICKER, ticker)
            else:
                # 记录未处理的消息类型
                if debug_enabled:
                    self.logger.warning("未处理的消息类型", data=str(data)[:500])
            
        except Exception as e:
            self.logger.error("处理Deribit消息失败", exc_info=True, data=str(data)[:200])
            self.enhanced_stats['subscription_errors'] += 1
    
    async def normalize_trade(self, raw_data: Dict[str, Any], channel: str) -> Optional[NormalizedTrade]:
        """标准化Deribit交易数据"""
        try:
            # 从channel中提取symbol
            symbol = channel.split(".")[1]
            
            price = self._safe_decimal(raw_data["price"])
            quantity = self._safe_decimal(raw_data["amount"])
            
            return NormalizedTrade(
                exchange_name="deribit",
                symbol_name=symbol,
                trade_id=str(raw_data["trade_id"]),
                price=price,
                quantity=quantity,
                quote_quantity=price * quantity,  # 计算成交金额
                timestamp=self._safe_timestamp(raw_data["timestamp"]),
                side=raw_data["direction"],  # 添加必需的side字段
                is_buyer_maker=raw_data["direction"] == "sell"  # Deribit: sell=maker买入
            )
            
        except Exception as e:
            self.logger.error("标准化Deribit交易数据失败", exc_info=True, raw_data=raw_data)
            return None
    
    async def normalize_orderbook(self, raw_data: Dict[str, Any], channel: str) -> Optional[NormalizedOrderBook]:
        """标准化Deribit订单簿数据"""
        try:
            # 从channel中提取symbol
            symbol = channel.split(".")[1]
            
            # Deribit订单簿格式
            bids = [
                OrderBookEntry(
                    price=self._safe_decimal(bid[0]),
                    quantity=self._safe_decimal(bid[1])
                )
                for bid in raw_data.get("bids", [])
            ]
            
            asks = [
                OrderBookEntry(
                    price=self._safe_decimal(ask[0]),
                    quantity=self._safe_decimal(ask[1])
                )
                for ask in raw_data.get("asks", [])
            ]
            
            return NormalizedOrderBook(
                exchange_name="deribit",
                symbol_name=symbol,
                bids=bids,
                asks=asks,
                timestamp=self._safe_timestamp(raw_data["timestamp"])
            )
            
        except Exception as e:
            self.logger.error("标准化Deribit订单簿数据失败", exc_info=True, raw_data=raw_data)
            return None
    
    async def normalize_kline(self, raw_data: Dict[str, Any]) -> Optional[NormalizedKline]:
        """标准化Deribit K线数据"""
        try:
            # Deribit暂不支持K线数据流，需要通过API获取
            return None
            
        except Exception as e:
            self.logger.error("标准化Deribit K线数据失败", exc_info=True, raw_data=raw_data)
            return None
    
    async def normalize_ticker(self, raw_data: Dict[str, Any], channel: str) -> Optional[NormalizedTicker]:
        """标准化Deribit行情数据"""
        try:
            # 从channel中提取symbol
            symbol = channel.split(".")[1]
            
            last_price = self._safe_decimal(raw_data["last_price"])
            
            # Deribit提供的字段有限，需要计算或使用默认值
            price_change = self._safe_decimal(raw_data.get("price_change", "0"))
            price_change_percent = self._safe_decimal(raw_data.get("price_change_percent", "0"))
            high_price = self._safe_decimal(raw_data.get("high", last_price))
            low_price = self._safe_decimal(raw_data.get("low", last_price))
            volume = self._safe_decimal(raw_data.get("volume", "0"))
            volume_usd = self._safe_decimal(raw_data.get("volume_usd", "0"))
            
            # Deribit不提供的字段使用合理默认值
            open_price = last_price - price_change if price_change else last_price
            weighted_avg = volume_usd / volume if volume > 0 else last_price
            
            # 买卖盘信息（如果没有提供使用last_price）
            bid_price = self._safe_decimal(raw_data.get("best_bid_price", last_price))
            ask_price = self._safe_decimal(raw_data.get("best_ask_price", last_price))
            bid_amount = self._safe_decimal(raw_data.get("best_bid_amount", "0"))
            ask_amount = self._safe_decimal(raw_data.get("best_ask_amount", "0"))
            
            ts = self._safe_timestamp(raw_data["timestamp"])
            
            return NormalizedTicker(
                exchange_name="deribit",
                symbol_name=symbol,
                last_price=last_price,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                volume=volume,
                quote_volume=volume_usd,
                price_change=price_change,
                price_change_percent=price_change_percent,
                weighted_avg_price=weighted_avg,
                last_quantity=Decimal("0"),  # Deribit不提供
                best_bid_price=bid_price,
                best_bid_quantity=bid_amount,
                best_ask_price=ask_price,
                best_ask_quantity=ask_amount,
                open_time=ts - timedelta(hours=24),  # 24小时前
                close_time=ts,
                first_trade_id=None,  # Deribit不提供
                last_trade_id=None,   # Deribit不提供
                trade_count=0,        # Deribit不提供
                timestamp=ts
            )
            
        except Exception as e:
            self.logger.error("标准化Deribit行情数据失败", exc_info=True, raw_data=raw_data)
            return None
    
    def get_enhanced_stats(self) -> Dict[str, Any]:
        """获取增强统计信息"""
        base_stats = super().get_stats()
        return {
            **base_stats,
            **self.enhanced_stats,
            'connection_type': 'aiohttp' if self.aiohttp_ws else 'standard',
            'proxy_enabled': NetworkConfig.get_proxy_url() is not None,
            'proxy_url': NetworkConfig.get_proxy_url()
        } 