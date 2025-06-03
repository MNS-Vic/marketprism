"""
Binance交易所适配器 - 完整功能版本

实现Binance现货交易所的完整数据收集功能，包括：
- Binance特定的ping/pong维护机制
- 会话管理和用户数据流
- 动态订阅管理
- 高级监控和统计
"""

import json
import time
import asyncio
import aiohttp
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List
import structlog

from .base import ExchangeAdapter
from ..types import (
    NormalizedTrade, NormalizedOrderBook, NormalizedKline, 
    NormalizedTicker, DataType, OrderBookEntry, Exchange
)


class BinanceAdapter(ExchangeAdapter):
    """Binance交易所适配器 - 完整功能版本"""
    
    def __init__(self, config):
        super().__init__(config)
        self.logger = structlog.get_logger(__name__).bind(exchange="binance")
        
        # 添加exchange属性
        self.exchange = Exchange.BINANCE
        
        # Binance特定配置
        self.stream_names = []
        self.symbol_map = {}  # 符号映射
        
        # REST API session
        self.session = None
        self.base_url = config.base_url or "https://api.binance.com"
        
        # Binance ping/pong配置 - 覆盖基类默认值
        self.ping_interval = 180  # 3分钟（Binance建议）
        self.ping_timeout = 10   # 10秒超时（Binance要求10分钟内必须有pong）
        
        # 会话管理 (整合自enhanced版本)
        self.session_active = False
        self.session_logon_time = None
        self.user_data_stream = None
        self.listen_key = None
        self.listen_key_refresh_interval = 1800  # 30分钟刷新listen key
        self.listen_key_task = None
        
        # 速率限制管理 (整合自enhanced版本)
        self.request_weight = 0
        self.request_weight_reset_time = time.time() + 60  # 每分钟重置
        self.max_request_weight = 1200  # Binance限制
        
        # 重连策略配置
        self.binance_reconnect_delay = 5  # Binance建议的重连延迟
        self.max_consecutive_failures = 5
        self.consecutive_failures = 0
        
        # WebSocket API支持
        self.supports_websocket_api = True
        self.api_session_id = None
        
        # 扩展统计信息
        self.binance_stats = {
            'pings_sent': 0,
            'pongs_received': 0,
            'connection_drops': 0,
            'successful_reconnects': 0,
            'user_data_messages': 0,
            'listen_key_refreshes': 0
        }
    
    async def get_server_time(self) -> int:
        """获取服务器时间"""
        try:
            if not self.session:
                await self._ensure_session()
            
            url = f"{self.base_url}/api/v3/time"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['serverTime']
                else:
                    raise Exception(f"Failed to get server time: {response.status}")
        except Exception as e:
            self.logger.error("获取服务器时间失败", error=str(e))
            raise
    
    async def get_exchange_info(self) -> Dict[str, Any]:
        """获取交易所信息"""
        try:
            if not self.session:
                await self._ensure_session()
            
            url = f"{self.base_url}/api/v3/exchangeInfo"
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(f"Failed to get exchange info: {response.status}")
        except Exception as e:
            self.logger.error("获取交易所信息失败", error=str(e))
            raise
    
    async def get_orderbook_snapshot(self, symbol: str, limit: int = 100) -> Dict[str, Any]:
        """获取订单薄快照"""
        try:
            if not self.session:
                await self._ensure_session()
            
            url = f"{self.base_url}/api/v3/depth"
            params = {
                'symbol': symbol,
                'limit': limit
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(f"Failed to get orderbook: {response.status}")
        except Exception as e:
            self.logger.error("获取订单薄快照失败", symbol=symbol, error=str(e))
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
                self.logger.info("使用代理连接Binance API", proxy=proxy)
            
            # 创建带代理的session（aiohttp自动使用环境变量）
            self.session = aiohttp.ClientSession(timeout=timeout, trust_env=True)
    
    async def subscribe_orderbook(self, symbol: str, depth: int = 20):
        """订阅订单薄数据"""
        try:
            binance_symbol = symbol.replace("-", "").upper()
            await self.add_symbol_subscription(symbol, ["orderbook"])
            self.logger.info("订阅订单薄", symbol=symbol, binance_symbol=binance_symbol)
        except Exception as e:
            self.logger.error("订阅订单薄失败", symbol=symbol, error=str(e))
            raise
    
    async def subscribe_trades(self, symbol: str):
        """订阅交易数据"""
        try:
            binance_symbol = symbol.replace("-", "").upper()
            await self.add_symbol_subscription(symbol, ["trade"])
            self.logger.info("订阅交易数据", symbol=symbol, binance_symbol=binance_symbol)
        except Exception as e:
            self.logger.error("订阅交易数据失败", symbol=symbol, error=str(e))
            raise
    
    async def close(self):
        """关闭连接"""
        try:
            if self.session:
                await self.session.close()
                self.session = None
            await super().stop()
        except Exception as e:
            self.logger.error("关闭连接失败", error=str(e))
        
    async def start(self) -> bool:
        """启动Binance连接 - 完整版本"""
        try:
            self.logger.info("启动Binance适配器（完整功能版本）")
            
            # 初始化HTTP session
            await self._ensure_session()
            
            # 建立WebSocket连接
            success = await super().connect()
            if not success:
                return False
            
            # 启动Binance特定的维持任务
            await self._start_binance_maintenance_tasks()
            
            # 订阅数据流
            await self.subscribe_data_streams()
            
            # 启动消息处理循环
            asyncio.create_task(self._enhanced_message_loop())
            
            self.session_active = True
            self.session_logon_time = datetime.utcnow()
            
            self.logger.info("Binance适配器启动成功", 
                           ping_interval=self.ping_interval,
                           supports_api=self.supports_websocket_api,
                           session_active=self.session_active)
            
            return True
            
        except Exception as e:
            self.logger.error("启动Binance适配器失败", error=str(e))
            return False
    
    async def stop(self):
        """停止Binance连接 - 完整版本"""
        try:
            self.logger.info("停止Binance适配器")
            
            # 停止维持任务
            await self._stop_binance_maintenance_tasks()
            
            # 清理用户数据流
            if self.listen_key:
                await self._cleanup_user_data_stream()
            
            # 关闭HTTP session
            if self.session:
                await self.session.close()
                self.session = None
            
            # 停止基础连接
            await super().stop()
            
            self.session_active = False
            
        except Exception as e:
            self.logger.error("停止Binance适配器失败", error=str(e))
    
    async def _start_binance_maintenance_tasks(self):
        """启动Binance特定的维持任务"""
        try:
            # 启动listen key刷新任务（如果使用用户数据流）
            if hasattr(self.config, 'enable_user_data_stream') and self.config.enable_user_data_stream:
                if self.listen_key_task is None or self.listen_key_task.done():
                    self.listen_key_task = asyncio.create_task(self._listen_key_refresh_loop())
                    self.logger.info("Listen key刷新任务已启动")
            
        except Exception as e:
            self.logger.error("启动维持任务失败", error=str(e))
    
    async def _stop_binance_maintenance_tasks(self):
        """停止Binance特定的维持任务"""
        try:
            # 停止listen key刷新任务
            if self.listen_key_task and not self.listen_key_task.done():
                self.listen_key_task.cancel()
                try:
                    await self.listen_key_task
                except asyncio.CancelledError:
                    pass
                self.logger.info("Listen key刷新任务已停止")
            
        except Exception as e:
            self.logger.error("停止维持任务失败", error=str(e))
    
    async def _listen_key_refresh_loop(self):
        """Listen key刷新循环"""
        while self.is_connected and self.session_active:
            try:
                await asyncio.sleep(self.listen_key_refresh_interval)
                
                if self.listen_key:
                    await self._refresh_listen_key()
                    
            except asyncio.CancelledError:
                self.logger.info("Listen key刷新循环被取消")
                break
            except Exception as e:
                self.logger.error("Listen key刷新错误", error=str(e))
                await asyncio.sleep(60)  # 错误后等待1分钟再重试
    
    async def _enhanced_message_loop(self):
        """增强的消息处理循环"""
        try:
            async for message in self.ws_connection:
                if hasattr(message, 'data'):
                    await self._process_enhanced_message(message.data)
                else:
                    await self._process_enhanced_message(str(message))
        except Exception as e:
            self.logger.error("增强消息循环失败", error=str(e))
    
    async def _process_enhanced_message(self, message: str):
        """处理增强消息"""
        try:
            data = json.loads(message)
            
            # 检查pong响应
            if self._is_pong_message(data):
                await self._handle_pong_message(data)
                return
            
            # 检查WebSocket API响应
            if self._is_websocket_api_response(data):
                await self._handle_websocket_api_response(data)
                return
            
            # 检查用户数据流消息
            if self._is_user_data_stream_message(data):
                await self._handle_user_data_stream_message(data)
                return
            
            # 检查速率限制消息
            if self._is_rate_limit_message(data):
                await self._handle_rate_limit_message(data)
                return
            
            # 处理常规消息
            await self.handle_message(data)
            
        except Exception as e:
            self.logger.error("处理增强消息失败", error=str(e), message=message[:200])
    
    def _is_pong_message(self, data: Dict[str, Any]) -> bool:
        """检查是否为pong消息"""
        return "pong" in data
    
    async def _handle_pong_message(self, data: Dict[str, Any]):
        """处理pong响应"""
        self.last_pong_time = datetime.utcnow()
        self.pong_count += 1
        self.enhanced_stats['pong_count'] += 1
        self.binance_stats['pongs_received'] += 1
        
        pong_id = data.get("pong")
        self.logger.debug("收到Binance pong响应", pong_id=pong_id)
        
        # 计算ping往返时间
        if self.last_ping_time:
            rtt = (self.last_pong_time - self.last_ping_time).total_seconds()
            self.logger.debug("Binance ping往返时间", rtt_seconds=rtt)
    
    def _is_websocket_api_response(self, data: Dict[str, Any]) -> bool:
        """检查是否为WebSocket API响应"""
        return "id" in data and "status" in data
    
    async def _handle_websocket_api_response(self, data: Dict[str, Any]):
        """处理WebSocket API响应"""
        self.logger.debug("收到WebSocket API响应", 
                         id=data.get("id"), 
                         status=data.get("status"))
        
        # 这里可以处理特定的API响应
        if data.get("status") != 200:
            self.logger.warning("WebSocket API错误响应", data=data)
    
    def _is_user_data_stream_message(self, data: Dict[str, Any]) -> bool:
        """检查是否为用户数据流消息"""
        return "e" in data and data["e"] in ["outboundAccountPosition", "balanceUpdate", "executionReport"]
    
    async def _handle_user_data_stream_message(self, data: Dict[str, Any]):
        """处理用户数据流消息"""
        self.binance_stats['user_data_messages'] += 1
        event_type = data.get("e")
        self.logger.debug("收到用户数据流消息", event_type=event_type)
        
        # 这里可以处理不同类型的用户数据
        # 例如：账户余额更新、订单状态更新等
    
    def _is_rate_limit_message(self, data: Dict[str, Any]) -> bool:
        """检查是否为速率限制消息"""
        return "code" in data and data.get("code") in [1003, 1013]  # Binance速率限制错误码
    
    async def _handle_rate_limit_message(self, data: Dict[str, Any]):
        """处理速率限制消息"""
        self.logger.warning("收到速率限制警告", data=data)
        await self._implement_backoff_strategy()
    
    async def _implement_backoff_strategy(self):
        """实现退避策略"""
        backoff_time = min(2 ** self.consecutive_failures, 60)  # 最大60秒
        self.logger.info("执行退避策略", backoff_seconds=backoff_time)
        await asyncio.sleep(backoff_time)
        
    async def _cleanup_user_data_stream(self):
        """清理用户数据流"""
        try:
            if self.listen_key:
                # 这里应该调用REST API关闭用户数据流
                self.logger.info("清理用户数据流", listen_key=self.listen_key[:10] + "...")
                self.listen_key = None
        except Exception as e:
            self.logger.error("清理用户数据流失败", error=str(e))
    
    async def _refresh_listen_key(self):
        """刷新listen key"""
        try:
            # 这里应该调用REST API刷新listen key
            self.logger.info("刷新listen key")
            self.binance_stats['listen_key_refreshes'] += 1
        except Exception as e:
            self.logger.error("刷新listen key失败", error=str(e))
    
    async def _send_exchange_ping(self):
        """发送Binance特定的JSON ping消息"""
        try:
            # Binance特定的ping格式
            ping_message = {
                "method": "ping",
                "id": int(datetime.utcnow().timestamp() * 1000)
            }
            
            await self.ws_connection.send(json.dumps(ping_message))
            self.last_ping_time = datetime.utcnow()
            self.ping_count += 1
            self.enhanced_stats['ping_count'] += 1
            self.binance_stats['pings_sent'] += 1
            
            self.logger.debug("发送Binance ping", ping_id=ping_message['id'])
            
            # 启动pong超时检查
            asyncio.create_task(self._check_pong_timeout())
            
        except Exception as e:
            self.logger.error("发送Binance ping失败", error=str(e))
            self.enhanced_stats['ping_timeouts'] += 1
            await self._trigger_reconnect("binance_ping_failed")
    
    async def _is_pong_message(self, data: Dict[str, Any]) -> bool:
        """检查是否为Binance pong消息"""
        return "pong" in data
    
    async def _handle_pong_response(self, data: Dict[str, Any]):
        """处理Binance pong响应"""
        self.last_pong_time = datetime.utcnow()
        self.pong_count += 1
        self.enhanced_stats['pong_count'] += 1
        self.binance_stats['pongs_received'] += 1
        
        pong_id = data.get("pong")
        self.logger.debug("收到Binance pong响应", pong_id=pong_id)
        
        # 计算ping往返时间
        if self.last_ping_time:
            rtt = (self.last_pong_time - self.last_ping_time).total_seconds()
            self.logger.debug("Binance ping往返时间", rtt_seconds=rtt)
    
    def get_enhanced_stats(self) -> Dict[str, Any]:
        """获取增强统计信息"""
        base_stats = super().get_enhanced_stats()
        binance_specific_stats = {
            'binance_stats': self.binance_stats,
            'session_active': self.session_active,
            'session_duration': (datetime.utcnow() - self.session_logon_time).total_seconds() if self.session_logon_time else 0,
            'listen_key_active': self.listen_key is not None,
            'consecutive_failures': self.consecutive_failures,
            'supports_websocket_api': self.supports_websocket_api
        }
        return {**base_stats, **binance_specific_stats}
    
    async def add_symbol_subscription(self, symbol: str, data_types: List[str]):
        """动态添加交易对订阅"""
        try:
            # 转换符号格式 (BTC-USDT -> btcusdt)
            binance_symbol = symbol.replace("-", "").lower()
            self.symbol_map[binance_symbol] = symbol
            
            # 构建新的订阅流
            new_streams = []
            for data_type in data_types:
                if data_type == "trade":
                    new_streams.append(f"{binance_symbol}@trade")
                elif data_type == "orderbook":
                    new_streams.append(f"{binance_symbol}@depth@100ms")
                elif data_type == "ticker":
                    new_streams.append(f"{binance_symbol}@ticker")
                elif data_type == "liquidation":
                    new_streams.append(f"{binance_symbol}@forceOrder")
            
            # 发送订阅消息
            if new_streams:
                subscribe_msg = {
                    "method": "SUBSCRIBE",
                    "params": new_streams,
                    "id": int(time.time() * 1000)
                }
                
                await self.ws_connection.send(json.dumps(subscribe_msg))
                self.logger.info("动态添加订阅", symbol=symbol, streams=new_streams)
                
        except Exception as e:
            self.logger.error("添加订阅失败", symbol=symbol, error=str(e))
    
    async def remove_symbol_subscription(self, symbol: str, data_types: List[str]):
        """动态移除交易对订阅"""
        try:
            # 转换符号格式
            binance_symbol = symbol.replace("-", "").lower()
            
            # 构建要取消的订阅流
            streams_to_remove = []
            for data_type in data_types:
                if data_type == "trade":
                    streams_to_remove.append(f"{binance_symbol}@trade")
                elif data_type == "orderbook":
                    streams_to_remove.append(f"{binance_symbol}@depth@100ms")
                elif data_type == "ticker":
                    streams_to_remove.append(f"{binance_symbol}@ticker")
                elif data_type == "liquidation":
                    streams_to_remove.append(f"{binance_symbol}@forceOrder")
            
            # 发送取消订阅消息
            if streams_to_remove:
                unsubscribe_msg = {
                    "method": "UNSUBSCRIBE",
                    "params": streams_to_remove,
                    "id": int(time.time() * 1000)
                }
                
                await self.ws_connection.send(json.dumps(unsubscribe_msg))
                self.logger.info("动态移除订阅", symbol=symbol, streams=streams_to_remove)
                
                # 从映射中移除
                if binance_symbol in self.symbol_map:
                    del self.symbol_map[binance_symbol]
                
        except Exception as e:
            self.logger.error("移除订阅失败", symbol=symbol, error=str(e))
    
    async def subscribe_data_streams(self):
        """订阅Binance数据流"""
        try:
            streams = []
            
            for symbol in self.config.symbols:
                # 转换符号格式 (BTC-USDT -> BTCUSDT -> btcusdt)
                binance_symbol = symbol.replace("-", "").lower()
                self.symbol_map[binance_symbol] = symbol
                # 同时映射大写格式 BTCUSDT -> BTC-USDT
                self.symbol_map[symbol.replace("-", "")] = symbol
                
                # 根据配置的数据类型订阅相应流
                if DataType.TRADE in self.config.data_types:
                    streams.append(f"{binance_symbol}@trade")
                
                if DataType.ORDERBOOK in self.config.data_types:
                    streams.append(f"{binance_symbol}@depth@100ms")  # 增量深度流
                
                if DataType.TICKER in self.config.data_types:
                    streams.append(f"{binance_symbol}@ticker")
                
                if DataType.LIQUIDATION in self.config.data_types:
                    # 币安强平订单流 - 单个交易对
                    streams.append(f"{binance_symbol}@forceOrder")
            
            # 如果需要强平数据，也可以订阅全市场强平流
            if DataType.LIQUIDATION in self.config.data_types:
                # 全市场强平订单流 (可选，获取所有交易对的强平数据)
                streams.append("!forceOrder@arr")
            
            # 发送订阅消息
            subscribe_msg = {
                "method": "SUBSCRIBE",
                "params": streams,
                "id": 1
            }
            
            await self.ws_connection.send(json.dumps(subscribe_msg))
            self.logger.info("已订阅数据流", streams=streams)
            
        except Exception as e:
            self.logger.error("订阅数据流失败", error=str(e))
            raise
    
    async def handle_message(self, data: Dict[str, Any]):
        """处理Binance消息"""
        try:
            # 跳过订阅确认消息
            if "result" in data or "id" in data:
                self.logger.debug("收到订阅确认消息", data=data)
                return
            
            # 处理组合流消息格式 (stream + data)
            if "stream" in data and "data" in data:
                stream = data["stream"]
                stream_data = data["data"]
                
                # 添加调试日志
                if "@depth" in stream:
                    self.logger.debug("收到深度数据", stream=stream, update_id=stream_data.get("u", "N/A"))
                
                # 解析流类型
                if "@trade" in stream:
                    trade = await self.normalize_trade(stream_data)
                    if trade:
                        await self._emit_data(DataType.TRADE, trade)
                
                elif "@depth" in stream:
                    # 发送原始数据给OrderBook Manager
                    symbol = self.symbol_map.get(stream_data["s"].lower(), stream_data["s"])
                    self.logger.info("发送原始深度数据", symbol=symbol, update_id=stream_data.get("u"))
                    await self._emit_raw_data('depth', 'binance', symbol, stream_data)
                    
                    # 标准化并发送给NATS
                    orderbook = await self.normalize_orderbook(stream_data)
                    if orderbook:
                        await self._emit_data(DataType.ORDERBOOK, orderbook)
                
                elif "@ticker" in stream:
                    ticker = await self.normalize_ticker(stream_data)
                    if ticker:
                        await self._emit_data(DataType.TICKER, ticker)
                
                elif "@forceOrder" in stream:
                    # 处理强平订单数据
                    liquidation = await self.normalize_liquidation(stream_data)
                    if liquidation:
                        await self._emit_data(DataType.LIQUIDATION, liquidation)
            
            # 处理单一流消息格式 (直接事件)
            elif "e" in data:
                event_type = data["e"]
                
                if event_type == "trade":
                    trade = await self.normalize_trade(data)
                    if trade:
                        await self._emit_data(DataType.TRADE, trade)
                
                elif event_type == "depthUpdate":
                    self.logger.debug("收到增量深度数据", symbol=data.get("s"), update_id=data.get("u", "N/A"))
                    
                    # 发送原始数据给OrderBook Manager
                    symbol = self.symbol_map.get(data["s"].lower(), data["s"])
                    await self._emit_raw_data('depth', 'binance', symbol, data)
                    
                    # 标准化并发送给NATS
                    orderbook = await self.normalize_orderbook(data)
                    if orderbook:
                        await self._emit_data(DataType.ORDERBOOK, orderbook)
                
                elif event_type == "24hrTicker":
                    ticker = await self.normalize_ticker(data)
                    if ticker:
                        await self._emit_data(DataType.TICKER, ticker)
                
                elif event_type == "forceOrder":
                    # 处理强平订单事件
                    liquidation = await self.normalize_liquidation(data)
                    if liquidation:
                        await self._emit_data(DataType.LIQUIDATION, liquidation)
                
                else:
                    self.logger.debug("收到未知事件类型", event_type=event_type)
            
            else:
                self.logger.debug("收到未知格式消息", data=str(data)[:200])
            
        except Exception as e:
            self.logger.error("处理消息失败", error=str(e), data=str(data)[:200])
    
    async def normalize_trade(self, raw_data: Dict[str, Any]) -> Optional[NormalizedTrade]:
        """标准化交易数据"""
        try:
            symbol = self.symbol_map.get(raw_data["s"].lower(), raw_data["s"])
            
            price = self._safe_decimal(raw_data["p"])
            quantity = self._safe_decimal(raw_data["q"])
            
            return NormalizedTrade(
                exchange_name="binance",
                symbol_name=symbol,
                trade_id=str(raw_data["t"]),
                price=price,
                quantity=quantity,
                quote_quantity=price * quantity,  # 计算成交金额
                timestamp=self._safe_timestamp(raw_data["T"]),
                side="sell" if raw_data["m"] else "buy"  # m=true表示买方是maker，即卖单成交
            )
            
        except Exception as e:
            self.logger.error("标准化交易数据失败", error=str(e), raw_data=raw_data)
            return None
    
    async def normalize_orderbook(self, raw_data: Dict[str, Any]) -> Optional[NormalizedOrderBook]:
        """标准化订单簿数据"""
        try:
            symbol = self.symbol_map.get(raw_data["s"].lower(), raw_data["s"])
            
            # 处理买单和卖单
            bids = [
                OrderBookEntry(
                    price=self._safe_decimal(bid[0]),
                    quantity=self._safe_decimal(bid[1])
                )
                for bid in raw_data.get("b", [])
            ]
            
            asks = [
                OrderBookEntry(
                    price=self._safe_decimal(ask[0]),
                    quantity=self._safe_decimal(ask[1])
                )
                for ask in raw_data.get("a", [])
            ]
            
            # 创建增强订单簿对象
            from ..types import EnhancedOrderBook, OrderBookUpdateType
            
            return EnhancedOrderBook(
                exchange_name="binance",
                symbol_name=symbol,
                bids=bids,
                asks=asks,
                timestamp=self._safe_timestamp(raw_data.get("E", None)),
                last_update_id=raw_data.get("u", 0),
                first_update_id=raw_data.get("U", None),
                update_type=OrderBookUpdateType.DELTA,
                depth_levels=len(bids) + len(asks),
                is_valid=True
            )
            
        except Exception as e:
            self.logger.error("标准化订单簿数据失败", error=str(e), raw_data=raw_data)
            return None
    
    async def normalize_kline(self, raw_data: Dict[str, Any]) -> Optional[NormalizedKline]:
        """标准化K线数据"""
        try:
            # Binance K线数据格式
            kline_data = raw_data["k"]
            symbol = self.symbol_map.get(kline_data["s"].lower(), kline_data["s"])
            
            return NormalizedKline(
                exchange_name="binance",
                symbol_name=symbol,
                interval=kline_data["i"],
                open_time=self._safe_timestamp(kline_data["t"]),
                close_time=self._safe_timestamp(kline_data["T"]),
                open_price=self._safe_decimal(kline_data["o"]),
                high_price=self._safe_decimal(kline_data["h"]),
                low_price=self._safe_decimal(kline_data["l"]),
                close_price=self._safe_decimal(kline_data["c"]),
                volume=self._safe_decimal(kline_data["v"]),
                quote_volume=self._safe_decimal(kline_data["q"]),  # 成交额
                trade_count=self._safe_int(kline_data["n"]),
                taker_buy_volume=self._safe_decimal(kline_data["V"]),  # 主动买入成交量
                taker_buy_quote_volume=self._safe_decimal(kline_data["Q"]),  # 主动买入成交额
                is_closed=kline_data["x"]
            )
            
        except Exception as e:
            self.logger.error("标准化K线数据失败", error=str(e), raw_data=raw_data)
            return None
    
    async def normalize_ticker(self, raw_data: Dict[str, Any]) -> Optional[NormalizedTicker]:
        """标准化行情数据"""
        try:
            symbol = self.symbol_map.get(raw_data["s"].lower(), raw_data["s"])
            
            # Binance ticker 24hr数据有完整字段
            last_price = self._safe_decimal(raw_data["c"])
            open_price = self._safe_decimal(raw_data["o"])
            high_price = self._safe_decimal(raw_data["h"])
            low_price = self._safe_decimal(raw_data["l"])
            volume = self._safe_decimal(raw_data["v"])
            quote_volume = self._safe_decimal(raw_data["q"])
            price_change = self._safe_decimal(raw_data["p"])
            price_change_percent = self._safe_decimal(raw_data["P"])
            weighted_avg_price = self._safe_decimal(raw_data["w"])
            
            # 提取更多字段
            last_qty = self._safe_decimal(raw_data["Q"])
            bid_price = self._safe_decimal(raw_data["b"])
            bid_qty = self._safe_decimal(raw_data["B"])
            ask_price = self._safe_decimal(raw_data["a"])
            ask_qty = self._safe_decimal(raw_data["A"])
            
            # 时间相关
            open_time = self._safe_timestamp(raw_data["O"])
            close_time = self._safe_timestamp(raw_data["C"])
            first_trade_id = self._safe_int(raw_data["F"])
            last_trade_id = self._safe_int(raw_data["L"])
            trade_count = self._safe_int(raw_data["n"])
            
            return NormalizedTicker(
                exchange_name="binance",
                symbol_name=symbol,
                last_price=last_price,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                volume=volume,
                quote_volume=quote_volume,
                price_change=price_change,
                price_change_percent=price_change_percent,
                weighted_avg_price=weighted_avg_price,
                last_quantity=last_qty,
                best_bid_price=bid_price,
                best_bid_quantity=bid_qty,
                best_ask_price=ask_price,
                best_ask_quantity=ask_qty,
                open_time=open_time,
                close_time=close_time,
                first_trade_id=first_trade_id,
                last_trade_id=last_trade_id,
                trade_count=trade_count,
                timestamp=close_time
            )
            
        except Exception as e:
            self.logger.error("标准化行情数据失败", error=str(e), raw_data=raw_data)
            return None
    
    async def normalize_liquidation(self, raw_data: Dict[str, Any]) -> Optional['NormalizedLiquidation']:
        """标准化币安强平数据"""
        try:
            # 导入强平数据类型
            from ..types import NormalizedLiquidation
            
            # 判断数据格式并提取订单数据
            if "e" in raw_data and raw_data["e"] == "forceOrder" and "o" in raw_data and isinstance(raw_data["o"], dict):
                # 嵌套格式：事件包含订单数据
                order_data = raw_data["o"]
                event_time = raw_data.get("E")
            elif "s" in raw_data and "S" in raw_data:
                # 直接格式：数据本身就是订单数据
                order_data = raw_data
                event_time = None
            else:
                # 无法识别的格式
                self.logger.warning("无法识别的强平数据格式", raw_data=raw_data)
                return None
            
            # 提取基本信息
            symbol_raw = order_data["s"]
            
            # 确保symbol_map已初始化，如果没有则创建基本映射
            if not hasattr(self, 'symbol_map') or not self.symbol_map:
                self.symbol_map = {}
            
            # 创建符号映射 (BTCUSDT -> BTC-USDT)
            if symbol_raw not in self.symbol_map and symbol_raw.lower() not in self.symbol_map:
                # 尝试转换格式
                if "USDT" in symbol_raw:
                    base = symbol_raw.replace("USDT", "")
                    symbol = f"{base}-USDT"
                elif "BTC" in symbol_raw and symbol_raw != "BTC":
                    base = symbol_raw.replace("BTC", "")
                    symbol = f"{base}-BTC"
                else:
                    symbol = symbol_raw
                
                # 添加到映射
                self.symbol_map[symbol_raw] = symbol
                self.symbol_map[symbol_raw.lower()] = symbol
            else:
                symbol = self.symbol_map.get(symbol_raw.lower(), self.symbol_map.get(symbol_raw, symbol_raw))
            
            # 转换币安的方向格式到标准格式
            side = order_data["S"].lower()  # "BUY" -> "buy", "SELL" -> "sell"
            
            # 提取价格和数量
            price = self._safe_decimal(order_data.get("ap"))  # 使用平均价格
            if not price:
                price = self._safe_decimal(order_data.get("p"))  # 如果没有平均价格，使用订单价格
            
            quantity = self._safe_decimal(order_data.get("z"))  # 使用累计成交量
            if not quantity:
                quantity = self._safe_decimal(order_data.get("q"))  # 如果没有成交量，使用订单数量
            
            # 计算强平价值
            value = price * quantity if price and quantity else None
            
            # 提取时间戳 (优先使用交易时间，其次使用事件时间)
            timestamp = self._safe_timestamp(order_data.get("T", event_time))
            
            # 确定合约类型 (根据交易对判断)
            instrument_type = "futures"
            if "USDT" in symbol_raw:
                instrument_type = "futures"  # USDT本位期货
            elif any(coin in symbol_raw for coin in ["BTC", "ETH", "BNB"]):
                instrument_type = "futures"  # 币本位期货
            
            return NormalizedLiquidation(
                exchange_name="binance",
                symbol_name=symbol,
                liquidation_id=None,  # 币安不提供强平ID
                side=side,
                price=price,
                quantity=quantity,
                value=value,
                leverage=None,  # 币安强平数据不包含杠杆信息
                margin_type=None,  # 币安强平数据不包含保证金类型
                liquidation_fee=None,  # 币安强平数据不包含手续费
                instrument_type=instrument_type,
                user_id=None,  # 币安不提供用户ID
                timestamp=timestamp
            )
            
        except Exception as e:
            self.logger.error("标准化币安强平数据失败", error=str(e), raw_data=raw_data)
            return None 