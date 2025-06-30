"""
OKX交易所适配器 - 完整功能版本

实现OKX现货交易所的完整数据收集功能，包括：
- OKX特定的ping/pong维护机制（字符串ping）
- 认证和会话管理
- 动态订阅管理
- OKX特定的重连策略
"""

import json
import asyncio
import aiohttp
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, List
import structlog

from .base import ExchangeAdapter
from ..data_types import (
    NormalizedTrade, NormalizedOrderBook, NormalizedKline,
    DataType, OrderBookEntry, Exchange,
    NormalizedFundingRate, NormalizedOpenInterest, NormalizedLiquidation
)


class OKXAdapter(ExchangeAdapter):
    """OKX交易所适配器 - 完整功能版本"""
    
    def __init__(self, config):
        super().__init__(config)
        self.logger = structlog.get_logger(__name__).bind(exchange="okx")
        
        # 添加exchange属性
        self.exchange = Exchange.OKX
        
        # OKX特定配置
        self.symbol_map = {}
        self.subscription_map = {}
        
        # REST API session
        self.session = None
        self.base_url = config.base_url or "https://www.okx.com"
        
        # OKX ping/pong配置 - 覆盖基类默认值
        self.ping_interval = 25   # 25秒（OKX要求30秒内必须有活动）
        self.ping_timeout = 5     # 5秒超时
        
        # OKX认证相关 (整合自enhanced版本)
        self.is_authenticated = False
        self.login_response = None
        self.supports_private_channels = False
        
        # OKX连接维护
        self.last_data_time = None
        self.no_data_threshold = 30  # 30秒无数据触发ping
        
        # OKX统计信息
        self.okx_stats = {
            'login_attempts': 0,
            'successful_logins': 0,
            'data_timeouts': 0,
            'string_pongs': 0,
            'json_pongs': 0
        }
    
    async def get_server_time(self) -> int:
        """获取服务器时间"""
        try:
            if not self.session:
                await self._ensure_session()
            
            url = f"{self.base_url}/api/v5/public/time"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('code') == '0' and data.get('data'):
                        return int(data['data'][0]['ts'])
                    else:
                        raise Exception(f"OKX API error: {data}")
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
            
            url = f"{self.base_url}/api/v5/public/instruments"
            params = {'instType': 'SPOT'}  # 默认获取现货交易对
            
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
            
            url = f"{self.base_url}/api/v5/market/books"
            params = {
                'instId': symbol,
                'sz': str(limit)
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
                self.logger.info("使用代理连接OKX API", proxy=proxy)
            
            # 创建带代理的session（aiohttp自动使用环境变量）
            self.session = aiohttp.ClientSession(timeout=timeout, trust_env=True)
    
    async def subscribe_orderbook(self, symbol: str, depth: int = 20):
        """订阅订单薄数据"""
        try:
            # OKX的订阅方式
            args = [{"channel": "books", "instId": symbol}]
            await self._subscribe_args(args)
            self.logger.info("订阅订单薄", symbol=symbol)
        except Exception as e:
            self.logger.error("订阅订单薄失败", symbol=symbol, exc_info=True)
            raise
    
    async def subscribe_trades(self, symbol: str):
        """订阅交易数据"""
        try:
            args = [{"channel": "trades", "instId": symbol}]
            await self._subscribe_args(args)
            self.logger.info("订阅交易数据", symbol=symbol)
        except Exception as e:
            self.logger.error("订阅交易数据失败", symbol=symbol, exc_info=True)
            raise
    
    async def _subscribe_args(self, args: List[Dict[str, str]]):
        """订阅指定参数"""
        subscribe_msg = {
            "op": "subscribe",
            "args": args
        }
        
        if self.ws_connection:
            await self.ws_connection.send(json.dumps(subscribe_msg))
        else:
            raise Exception("无可用的WebSocket连接")
    
    async def close(self):
        """关闭连接"""
        try:
            if self.session:
                await self.session.close()
                self.session = None
            await super().stop()
        except Exception as e:
            self.logger.error("关闭连接失败", exc_info=True)
        
    async def start(self) -> bool:
        """启动OKX连接 - 完整版本"""
        try:
            self.logger.info("启动OKX适配器（完整功能版本）")
            
            # 初始化HTTP session
            await self._ensure_session()
            
            # 建立WebSocket连接
            success = await super().connect()
            if not success:
                return False
            
            # 启动OKX特定的维持任务
            await self._start_okx_maintenance_tasks()
            
            # 订阅数据流
            await self.subscribe_data_streams()
            
            # 启动消息处理循环
            asyncio.create_task(self._enhanced_message_loop())
            
            self.logger.info("OKX适配器启动成功", 
                           ping_interval=self.ping_interval,
                           authenticated=self.is_authenticated)
            
            return True
            
        except Exception as e:
            self.logger.error("启动OKX适配器失败", exc_info=True)
            return False
    
    async def stop(self):
        """停止OKX连接 - 完整版本"""
        try:
            self.logger.info("停止OKX适配器")
            
            # 停止维持任务
            await self._stop_okx_maintenance_tasks()
            
            # 关闭HTTP session
            if self.session:
                await self.session.close()
                self.session = None
            
            # 停止基础连接
            await super().stop()
            
            self.is_authenticated = False
            
        except Exception as e:
            self.logger.error("停止OKX适配器失败", exc_info=True)
    
    async def _start_okx_maintenance_tasks(self):
        """启动OKX特定的维护任务"""
        try:
            # 启动数据监控任务
            data_monitor_task = asyncio.create_task(self._data_monitor_loop())
            self.maintenance_tasks.append(data_monitor_task)
            
            self.logger.info("OKX特定维护任务已启动")
            
        except Exception as e:
            self.logger.error("启动OKX维持任务失败", exc_info=True)
    
    async def _stop_okx_maintenance_tasks(self):
        """停止OKX特定的维护任务"""
        try:
            # 维护任务已在基类的stop中处理
            self.logger.info("OKX特定维护任务已停止")
            
        except Exception as e:
            self.logger.error("停止OKX维持任务失败", exc_info=True)
    
    async def _data_monitor_loop(self):
        """数据监控循环 - OKX要求30秒内有数据活动"""
        while self.is_connected:
            try:
                await asyncio.sleep(10)  # 每10秒检查一次
                
                if self.last_data_time:
                    time_since_last_data = (datetime.now(timezone.utc) - self.last_data_time).total_seconds()
                    
                    if time_since_last_data > self.no_data_threshold:
                        self.logger.debug("OKX数据超时，发送ping", 
                                        seconds_since_data=time_since_last_data)
                        self.okx_stats['data_timeouts'] += 1
                        await self._send_exchange_ping()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("OKX数据监控失败", exc_info=True)
    
    async def _enhanced_message_loop(self):
        """增强的消息处理循环"""
        try:
            async for message in self.ws_connection:
                if hasattr(message, 'data'):
                    await self._process_enhanced_message(message.data)
                else:
                    await self._process_enhanced_message(str(message))
        except Exception as e:
            self.logger.error("增强消息循环失败", exc_info=True)
    
    async def _process_enhanced_message(self, message: str):
        """处理OKX增强消息"""
        try:
            # 更新数据时间
            self.last_data_time = datetime.now(timezone.utc)
            
            # 检查是否为字符串pong
            if message.strip().lower() == "pong":
                await self._handle_string_pong()
                return
            
            # 尝试解析JSON消息
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                self.logger.warning("收到非JSON消息", message=message[:100])
                return
            
            # 检查是否为JSON pong响应
            if await self._is_pong_message(data):
                await self._handle_pong_response(data)
                return
            
            # 检查是否为登录响应
            if self._is_login_response(data):
                await self._handle_login_response(data)
                return
            
            # 处理其他消息类型
            await self.handle_message(data)
            
        except Exception as e:
            self.logger.error("处理OKX增强消息失败", exc_info=True, message=message[:200])
    
    async def _send_exchange_ping(self):
        """发送OKX特定的字符串ping消息"""
        try:
            # OKX特定的ping格式：直接发送字符串"ping"
            await self.ws_connection.send("ping")
            self.last_ping_time = datetime.now(timezone.utc)
            self.ping_count += 1
            self.enhanced_stats['ping_count'] += 1
            
            self.logger.debug("发送OKX ping")
            
            # 启动pong超时检查
            asyncio.create_task(self._check_pong_timeout())
            
        except Exception as e:
            self.logger.error("发送OKX ping失败", exc_info=True)
            self.enhanced_stats['ping_timeouts'] += 1
            await self._trigger_reconnect("okx_ping_failed")
    
    async def _is_pong_message(self, data: Dict[str, Any]) -> bool:
        """检查是否为OKX pong消息"""
        # OKX pong可能是包含pong字段的JSON
        return isinstance(data, dict) and data.get("pong") is not None
    
    async def _handle_string_pong(self):
        """处理字符串pong响应"""
        self.last_pong_time = datetime.now(timezone.utc)
        self.pong_count += 1
        self.enhanced_stats['pong_count'] += 1
        self.okx_stats['string_pongs'] += 1
        
        self.logger.debug("收到OKX字符串pong响应")
        
        # 计算ping往返时间
        if self.last_ping_time:
            rtt = (self.last_pong_time - self.last_ping_time).total_seconds()
            self.logger.debug("OKX ping往返时间", rtt_seconds=rtt)
    
    async def _handle_pong_response(self, data: Dict[str, Any]):
        """处理JSON pong响应"""
        self.last_pong_time = datetime.now(timezone.utc)
        self.pong_count += 1
        self.enhanced_stats['pong_count'] += 1
        self.okx_stats['json_pongs'] += 1
        
        self.logger.debug("收到OKX JSON pong响应", data=data)
    
    def _is_login_response(self, data: Dict[str, Any]) -> bool:
        """检查是否为登录响应"""
        return (data.get("event") == "login" or 
                data.get("op") == "login")
    
    async def _handle_login_response(self, data: Dict[str, Any]):
        """处理登录响应"""
        if data.get("code") == "0" or data.get("success"):
            self.is_authenticated = True
            self.login_response = data
            self.supports_private_channels = True
            self.okx_stats['successful_logins'] += 1
            self.logger.info("OKX登录成功", response=data)
        else:
            self.logger.error("OKX登录失败", response=data)
            self.is_authenticated = False
    
    def get_enhanced_stats(self) -> Dict[str, Any]:
        """获取增强统计信息"""
        base_stats = super().get_enhanced_stats()
        okx_specific_stats = {
            'okx_stats': self.okx_stats,
            'authenticated': self.is_authenticated,
            'supports_private_channels': self.supports_private_channels,
            'last_data_time': self.last_data_time.isoformat() if self.last_data_time else None,
            'subscribed_symbols': len(self.symbol_map)
        }
        return {**base_stats, **okx_specific_stats}
    
    async def add_symbol_subscription(self, symbol: str, data_types: List[str]):
        """动态添加交易对订阅"""
        try:
            # OKX符号格式保持不变 (BTC-USDT)
            okx_symbol = symbol
            self.symbol_map[symbol] = symbol
            
            # 构建新的订阅请求
            channels = []
            for data_type in data_types:
                if data_type == "trade":
                    channels.append({
                        "channel": "trades",
                        "instId": okx_symbol
                    })
                elif data_type == "orderbook":
                    channels.append({
                        "channel": "books",
                        "instId": okx_symbol
                    })

                elif data_type == "liquidation":
                    channels.append({
                        "channel": "liquidation-orders",
                        "instId": okx_symbol + "-SWAP"
                    })
            
            # 发送订阅消息
            if channels:
                subscribe_msg = {
                    "op": "subscribe",
                    "args": channels
                }
                
                await self.ws_connection.send(json.dumps(subscribe_msg))
                self.logger.info("动态添加OKX订阅", symbol=symbol, channels=channels)
                
        except Exception as e:
            self.logger.error("添加OKX订阅失败", symbol=symbol, exc_info=True)
    
    async def remove_symbol_subscription(self, symbol: str, data_types: List[str]):
        """动态移除交易对订阅"""
        try:
            # 构建要取消的订阅请求
            channels = []
            for data_type in data_types:
                if data_type == "trade":
                    channels.append({
                        "channel": "trades",
                        "instId": symbol
                    })
                elif data_type == "orderbook":
                    channels.append({
                        "channel": "books",
                        "instId": symbol
                    })

                elif data_type == "liquidation":
                    channels.append({
                        "channel": "liquidation-orders",
                        "instId": symbol + "-SWAP"
                    })
            
            # 发送取消订阅消息
            if channels:
                unsubscribe_msg = {
                    "op": "unsubscribe",
                    "args": channels
                }
                
                await self.ws_connection.send(json.dumps(unsubscribe_msg))
                self.logger.info("动态移除OKX订阅", symbol=symbol, channels=channels)
                
                # 从映射中移除
                if symbol in self.symbol_map:
                    del self.symbol_map[symbol]
                
        except Exception as e:
            self.logger.error("移除OKX订阅失败", symbol=symbol, exc_info=True)
    
    async def subscribe_data_streams(self):
        """订阅OKX数据流"""
        try:
            # OKX使用不同的订阅格式
            subscribe_requests = []
            
            for symbol in self.config.symbols:
                # OKX符号格式已经是正确的 (BTC-USDT)
                okx_symbol = symbol
                self.symbol_map[okx_symbol] = symbol
                
                # 根据配置的数据类型订阅相应流
                if DataType.TRADE in self.config.data_types:
                    subscribe_requests.append({
                        "op": "subscribe",
                        "args": [{
                            "channel": "trades",
                            "instId": okx_symbol
                        }]
                    })
                
                if DataType.ORDERBOOK in self.config.data_types:
                    subscribe_requests.append({
                        "op": "subscribe", 
                        "args": [{
                            "channel": "books",
                            "instId": okx_symbol
                        }]
                    })
                

                
                # 订阅期货相关数据流
                if DataType.FUNDING_RATE in self.config.data_types:
                    # 检查是否为期货合约 (SWAP合约)
                    swap_symbol = symbol + "-SWAP"
                    subscribe_requests.append({
                        "op": "subscribe",
                        "args": [{
                            "channel": "funding-rate",
                            "instId": swap_symbol
                        }]
                    })
                
                if DataType.OPEN_INTEREST in self.config.data_types:
                    # 持仓量数据 (期货合约)
                    swap_symbol = symbol + "-SWAP"
                    subscribe_requests.append({
                        "op": "subscribe",
                        "args": [{
                            "channel": "open-interest",
                            "instId": swap_symbol
                        }]
                    })
                
                if DataType.LIQUIDATION in self.config.data_types:
                    # 强平数据
                    swap_symbol = symbol + "-SWAP"
                    subscribe_requests.append({
                        "op": "subscribe",
                        "args": [{
                            "channel": "liquidation-orders",
                            "instId": swap_symbol
                        }]
                    })
            
            # 发送所有订阅请求
            for request in subscribe_requests:
                await self.ws_connection.send(json.dumps(request))
                self.logger.debug("发送OKX订阅请求", request=request)
                
            self.logger.info("已订阅OKX数据流", count=len(subscribe_requests))
            
        except Exception as e:
            self.logger.error("订阅OKX数据流失败", exc_info=True)
            raise
    
    async def handle_message(self, data: Dict[str, Any]):
        """处理OKX消息"""
        try:
            # 跳过订阅确认消息
            if "event" in data:
                if data["event"] == "subscribe":
                    self.logger.info("OKX订阅确认", channel=data.get("arg", {}).get("channel"))
                return
            
            # 处理数据消息
            if "arg" in data and "data" in data:
                channel = data["arg"]["channel"]
                inst_id = data["arg"]["instId"]
                data_list = data["data"]
                
                for item in data_list:
                    if channel == "trades":
                        trade = await self.normalize_trade(item, inst_id)
                        if trade:
                            await self._emit_data(DataType.TRADE, trade)
                    
                    elif channel == "books":
                        orderbook = await self.normalize_orderbook(item, inst_id)
                        if orderbook:
                            await self._emit_data(DataType.ORDERBOOK, orderbook)
                    

                    
                    elif channel == "funding-rate":
                        funding_rate = await self.normalize_funding_rate(item, inst_id)
                        if funding_rate:
                            await self._emit_data(DataType.FUNDING_RATE, funding_rate)
                    
                    elif channel == "open-interest":
                        open_interest = await self.normalize_open_interest(item, inst_id)
                        if open_interest:
                            await self._emit_data(DataType.OPEN_INTEREST, open_interest)
                    
                    elif channel == "liquidation-orders":
                        liquidation = await self.normalize_liquidation(item, inst_id)
                        if liquidation:
                            await self._emit_data(DataType.LIQUIDATION, liquidation)
            
        except Exception as e:
            self.logger.error("处理OKX消息失败", exc_info=True, data=str(data)[:200])
    
    async def normalize_trade(self, raw_data: Dict[str, Any], inst_id: str) -> Optional[NormalizedTrade]:
        """标准化OKX交易数据"""
        try:
            symbol = self.symbol_map.get(inst_id, inst_id)
            
            price = self._safe_decimal(raw_data["px"])
            quantity = self._safe_decimal(raw_data["sz"])
            
            return NormalizedTrade(
                exchange_name="okx",
                symbol_name=symbol,
                trade_id=str(raw_data["tradeId"]),
                price=price,
                quantity=quantity,
                quote_quantity=price * quantity,  # 计算成交金额
                timestamp=self._safe_timestamp(int(raw_data["ts"])),
                side=raw_data["side"]  # OKX直接提供side字段: "buy" 或 "sell"
            )
            
        except Exception as e:
            self.logger.error("标准化OKX交易数据失败", exc_info=True, raw_data=raw_data)
            return None
    
    async def normalize_orderbook(self, raw_data: Dict[str, Any], inst_id: str) -> Optional[NormalizedOrderBook]:
        """标准化OKX订单簿数据"""
        try:
            symbol = self.symbol_map.get(inst_id, inst_id)
            
            # OKX订单簿格式
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
                exchange_name="okx",
                symbol_name=symbol,
                bids=bids,
                asks=asks,
                timestamp=self._safe_timestamp(int(raw_data["ts"]))
            )
            
        except Exception as e:
            self.logger.error("标准化OKX订单簿数据失败", exc_info=True, raw_data=raw_data)
            return None
    
    async def normalize_kline(self, raw_data: Dict[str, Any]) -> Optional[NormalizedKline]:
        """标准化K线数据"""
        try:
            # OKX K线数据格式 [timestamp, open, high, low, close, volume, volCcy]
            return NormalizedKline(
                exchange_name="okx",
                symbol_name=raw_data.get("instId", ""),
                interval="1m",  # 需要从配置获取
                open_time=self._safe_timestamp(int(raw_data[0])),
                close_time=self._safe_timestamp(int(raw_data[0]) + 60000),  # 假设1分钟
                open_price=self._safe_decimal(raw_data[1]),
                high_price=self._safe_decimal(raw_data[2]),
                low_price=self._safe_decimal(raw_data[3]),
                close_price=self._safe_decimal(raw_data[4]),
                volume=self._safe_decimal(raw_data[5]),
                quote_volume=self._safe_decimal(raw_data[6]),
                trade_count=0,  # OKX不提供此字段
                taker_buy_volume=None,
                taker_buy_quote_volume=None,
                is_closed=True
            )
            
        except Exception as e:
            self.logger.error("标准化OKX K线数据失败", exc_info=True, raw_data=raw_data)
            return None
    

    
    async def normalize_funding_rate(self, raw_data: Dict[str, Any], inst_id: str) -> Optional[NormalizedFundingRate]:
        """标准化OKX资金费率数据"""
        try:
            # 处理期货符号 (BTC-USDT-SWAP -> BTC-USDT)
            symbol = inst_id.replace("-SWAP", "")
            symbol = self.symbol_map.get(symbol, symbol)
            
            return NormalizedFundingRate(
                exchange_name="okx",
                symbol_name=symbol,
                funding_rate=self._safe_decimal(raw_data["fundingRate"]),
                next_funding_time=self._safe_timestamp(int(raw_data["nextFundingTime"])),
                timestamp=self._safe_timestamp(int(raw_data["fundingTime"]))
            )
            
        except Exception as e:
            self.logger.error("标准化OKX资金费率数据失败", exc_info=True, raw_data=raw_data)
            return None
    
    async def normalize_open_interest(self, raw_data: Dict[str, Any], inst_id: str) -> Optional[NormalizedOpenInterest]:
        """标准化OKX持仓量数据"""
        try:
            # 处理期货符号
            symbol = inst_id.replace("-SWAP", "")
            symbol = self.symbol_map.get(symbol, symbol)
            
            return NormalizedOpenInterest(
                exchange_name="okx",
                symbol_name=symbol,
                open_interest=self._safe_decimal(raw_data["oi"]),
                open_interest_value=self._safe_decimal(raw_data["oiCcy"]),
                timestamp=self._safe_timestamp(int(raw_data["ts"]))
            )
            
        except Exception as e:
            self.logger.error("标准化OKX持仓量数据失败", exc_info=True, raw_data=raw_data)
            return None
    
    async def normalize_liquidation(self, raw_data: Dict[str, Any], inst_id: str) -> Optional[NormalizedLiquidation]:
        """标准化OKX强平数据"""
        try:
            from ..data_types import NormalizedLiquidation
            
            # 处理期货符号
            symbol = inst_id.replace("-SWAP", "")
            symbol = self.symbol_map.get(symbol, symbol)
            
            # OKX强平数据格式
            price = self._safe_decimal(raw_data.get("bkPx"))
            quantity = self._safe_decimal(raw_data.get("sz"))
            value = price * quantity if price and quantity else None
            
            return NormalizedLiquidation(
                exchange_name="okx",
                symbol_name=symbol,
                liquidation_id=raw_data.get("details", [{}])[0].get("uly") if raw_data.get("details") else None,
                side=raw_data.get("side", "").lower(),
                price=price,
                quantity=quantity,
                value=value,
                leverage=None,  # OKX强平数据不包含杠杆信息
                margin_type=raw_data.get("mgnMode"),
                liquidation_fee=None,
                instrument_type="futures",  # OKX liquidation通常是期货
                user_id=None,  # OKX不提供用户ID
                timestamp=self._safe_timestamp(int(raw_data["ts"]))
            )
            
        except Exception as e:
            self.logger.error("标准化OKX强平数据失败", exc_info=True, raw_data=raw_data)
            return None 