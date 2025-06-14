"""
OKX WebSocket客户端

实现OKX WebSocket连接，维护400档实时订单簿
支持books频道的订阅和增量更新处理
"""

import asyncio
import json
import time
import websockets
import structlog
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable, Any
from decimal import Decimal

from .data_types import PriceLevel, OrderBookDelta
from .orderbook_manager import OrderBookUpdate


class OKXWebSocketClient:
    """OKX WebSocket客户端"""
    
    def __init__(self, symbols: List[str], on_orderbook_update: Callable):
        self.symbols = symbols
        self.on_orderbook_update = on_orderbook_update
        self.logger = structlog.get_logger(__name__)
        
        # WebSocket连接
        self.ws_url = "wss://ws.okx.com:8443/ws/v5/public"
        self.websocket = None
        self.is_connected = False
        self.is_running = False
        
        # 订单簿状态
        self.orderbook_states = {}
        
        # 重连参数
        self.reconnect_interval = 5
        self.max_reconnect_attempts = 10
        self.reconnect_count = 0
        
    async def start(self):
        """启动WebSocket客户端"""
        self.is_running = True
        self.logger.info("启动OKX WebSocket客户端", symbols=self.symbols)
        
        while self.is_running:
            try:
                await self._connect_and_run()
            except Exception as e:
                self.logger.error("WebSocket连接异常", exc_info=True)
                if self.is_running:
                    await asyncio.sleep(self.reconnect_interval)
                    self.reconnect_count += 1
                    if self.reconnect_count >= self.max_reconnect_attempts:
                        self.logger.error("达到最大重连次数，停止重连")
                        break
    
    async def stop(self):
        """停止WebSocket客户端"""
        self.is_running = False
        if self.websocket:
            await self.websocket.close()
        self.logger.info("OKX WebSocket客户端已停止")
    
    async def _connect_and_run(self):
        """连接并运行WebSocket"""
        try:
            self.logger.info("连接OKX WebSocket", url=self.ws_url)
            
            async with websockets.connect(
                self.ws_url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            ) as websocket:
                self.websocket = websocket
                self.is_connected = True
                self.reconnect_count = 0
                
                self.logger.info("OKX WebSocket连接成功")
                
                # 订阅订单簿频道
                await self._subscribe_orderbooks()
                
                # 处理消息
                async for message in websocket:
                    if not self.is_running:
                        break
                    await self._handle_message(message)
                    
        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("WebSocket连接关闭")
            self.is_connected = False
        except Exception as e:
            self.logger.error("WebSocket连接错误", exc_info=True)
            self.is_connected = False
            raise
    
    async def _subscribe_orderbooks(self):
        """订阅订单簿频道"""
        # 构建订阅请求
        args = []
        for symbol in self.symbols:
            args.append({
                "channel": "books",  # 400档深度频道
                "instId": symbol
            })
        
        subscribe_msg = {
            "op": "subscribe",
            "args": args
        }
        
        await self.websocket.send(json.dumps(subscribe_msg))
        self.logger.info("发送订单簿订阅请求", symbols=self.symbols)
    
    async def _handle_message(self, message: str):
        """处理WebSocket消息"""
        try:
            data = json.loads(message)
            
            # 处理订阅确认
            if data.get("event") == "subscribe":
                self.logger.info("订阅确认", channel=data.get("arg", {}).get("channel"))
                return
            
            # 处理错误消息
            if data.get("event") == "error":
                self.logger.error("WebSocket错误", error=data)
                return
            
            # 处理订单簿数据
            if "data" in data and "arg" in data:
                arg = data["arg"]
                if arg.get("channel") == "books":
                    await self._handle_orderbook_data(data)
            
        except Exception as e:
            self.logger.error("处理WebSocket消息失败", exc_info=True, message=message[:200])
    
    async def _handle_orderbook_data(self, data: Dict[str, Any]):
        """处理订单簿数据"""
        try:
            arg = data["arg"]
            symbol = arg["instId"]
            orderbook_data = data["data"][0]  # OKX返回数组，取第一个元素
            
            # 检查是否为快照或增量更新
            action = data.get("action", "snapshot")
            
            if action == "snapshot":
                await self._handle_snapshot(symbol, orderbook_data)
            elif action == "update":
                await self._handle_update(symbol, orderbook_data)
            
        except Exception as e:
            self.logger.error("处理订单簿数据失败", exc_info=True, data=str(data)[:200])
    
    async def _handle_snapshot(self, symbol: str, data: Dict[str, Any]):
        """处理订单簿快照"""
        try:
            # 解析快照数据
            bids_data = data.get("bids", [])
            asks_data = data.get("asks", [])
            timestamp_ms = int(data.get("ts", 0))
            seq_id = int(data.get("seqId", 0))
            
            # 解析买盘
            bids = []
            for bid in bids_data:
                price = Decimal(bid[0])
                quantity = Decimal(bid[1])
                if quantity > 0:
                    bids.append(PriceLevel(price=price, quantity=quantity))
            
            # 解析卖盘
            asks = []
            for ask in asks_data:
                price = Decimal(ask[0])
                quantity = Decimal(ask[1])
                if quantity > 0:
                    asks.append(PriceLevel(price=price, quantity=quantity))
            
            # 创建订单簿更新
            update = OrderBookUpdate(
                symbol=symbol,
                exchange="okx",
                first_update_id=seq_id,
                last_update_id=seq_id,
                bids=bids,
                asks=asks,
                timestamp=datetime.fromtimestamp(timestamp_ms / 1000.0)
            )
            
            # 更新本地状态
            self.orderbook_states[symbol] = {
                'last_seq_id': seq_id,
                'last_timestamp': timestamp_ms
            }
            
            self.logger.info(
                "收到OKX订单簿快照",
                symbol=symbol,
                seq_id=seq_id,
                bids_count=len(bids),
                asks_count=len(asks)
            )
            
            # 回调处理
            await self.on_orderbook_update(symbol, update)
            
        except Exception as e:
            self.logger.error("处理快照失败", exc_info=True, symbol=symbol)
    
    async def _handle_update(self, symbol: str, data: Dict[str, Any]):
        """处理订单簿增量更新"""
        try:
            # 解析增量数据
            bids_data = data.get("bids", [])
            asks_data = data.get("asks", [])
            timestamp_ms = int(data.get("ts", 0))
            seq_id = int(data.get("seqId", 0))
            prev_seq_id = int(data.get("prevSeqId", 0))
            
            # 检查序列连续性
            state = self.orderbook_states.get(symbol, {})
            last_seq_id = state.get('last_seq_id', 0)
            
            if prev_seq_id != last_seq_id:
                self.logger.warning(
                    "OKX序列不连续",
                    symbol=symbol,
                    expected_prev=last_seq_id,
                    actual_prev=prev_seq_id,
                    current_seq=seq_id
                )
                # 可能需要重新获取快照
                return
            
            # 解析买盘更新
            bid_updates = []
            for bid in bids_data:
                price = Decimal(bid[0])
                quantity = Decimal(bid[1])
                bid_updates.append(PriceLevel(price=price, quantity=quantity))
            
            # 解析卖盘更新
            ask_updates = []
            for ask in asks_data:
                price = Decimal(ask[0])
                quantity = Decimal(ask[1])
                ask_updates.append(PriceLevel(price=price, quantity=quantity))
            
            # 创建订单簿更新
            update = OrderBookUpdate(
                symbol=symbol,
                exchange="okx",
                first_update_id=seq_id,
                last_update_id=seq_id,
                bids=bid_updates,
                asks=ask_updates,
                timestamp=datetime.fromtimestamp(timestamp_ms / 1000.0),
                prev_update_id=prev_seq_id
            )
            
            # 更新本地状态
            self.orderbook_states[symbol]['last_seq_id'] = seq_id
            self.orderbook_states[symbol]['last_timestamp'] = timestamp_ms
            
            self.logger.debug(
                "收到OKX订单簿更新",
                symbol=symbol,
                seq_id=seq_id,
                prev_seq_id=prev_seq_id,
                bid_updates=len(bid_updates),
                ask_updates=len(ask_updates)
            )
            
            # 回调处理
            await self.on_orderbook_update(symbol, update)
            
        except Exception as e:
            self.logger.error("处理增量更新失败", exc_info=True, symbol=symbol)
    
    def get_connection_status(self) -> Dict[str, Any]:
        """获取连接状态"""
        return {
            'is_connected': self.is_connected,
            'is_running': self.is_running,
            'reconnect_count': self.reconnect_count,
            'symbols': self.symbols,
            'orderbook_states': self.orderbook_states
        } 