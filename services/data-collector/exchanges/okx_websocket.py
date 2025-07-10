"""
OKX WebSocket客户端
基于OKX官方文档要求的专用WebSocket实现
支持OKX特有的心跳机制和重连策略，实现统一的WebSocket接口
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional, Callable, List
import structlog
import websockets

# 🔧 标准化导入路径 - 支持动态导入
import sys
from pathlib import Path

# 添加exchanges目录到Python路径以支持动态导入
exchanges_dir = Path(__file__).parent
if str(exchanges_dir) not in sys.path:
    sys.path.insert(0, str(exchanges_dir))

from base_websocket import BaseWebSocketClient


class OKXWebSocketManager(BaseWebSocketClient):
    """
    OKX专用WebSocket管理器
    实现OKX官方文档要求的连接维护和重连机制
    """

    def __init__(self,
                 symbols: List[str],
                 on_orderbook_update: Callable[[str, Dict[str, Any]], None] = None,
                 ws_base_url: str = None,
                 market_type: str = 'spot',
                 websocket_depth: int = 400):
        """
        初始化OKX WebSocket管理器

        Args:
            symbols: 交易对列表
            on_orderbook_update: 订单簿更新回调函数 (symbol, data)
            ws_base_url: WebSocket基础URL
            market_type: 市场类型 ('spot', 'perpetual')
            websocket_depth: WebSocket深度 (OKX最大400)
        """
        # 调用父类构造函数
        super().__init__(symbols, on_orderbook_update, market_type, min(websocket_depth, 400))

        self.ws_base_url = ws_base_url or "wss://ws.okx.com:8443/ws/v5/public"
        # 🔧 统一属性命名：添加ws_url别名以保持兼容性
        self.ws_url = self.ws_base_url
        self.logger = structlog.get_logger(__name__)

        # WebSocket连接管理
        self.websocket = None

        # 任务管理
        self.listen_task = None
        self.heartbeat_task = None
        self.reconnect_task = None

        # OKX特有的心跳机制
        self.last_message_time = 0
        self.heartbeat_interval = 25  # 25秒发送ping（OKX要求30秒内必须有活动）
        self.pong_timeout = 5  # 5秒pong超时
        self.waiting_for_pong = False

        # 重连配置
        self.max_reconnect_attempts = -1  # 无限重连
        self.reconnect_delay = 1.0  # 初始重连延迟
        self.max_reconnect_delay = 30.0  # 最大重连延迟
        self.backoff_multiplier = 1.5  # 退避倍数
        self.current_reconnect_attempts = 0

        # 统计信息
        self.total_messages = 0
        self.reconnect_count = 0
    
    async def start(self):
        """启动OKX WebSocket管理器（orderbook_manager期望的接口）"""
        try:
            self.logger.info("🚀 启动OKX WebSocket管理器",
                           symbols=self.symbols,
                           url=self.ws_base_url,
                           market_type=self.market_type)

            self.is_running = True

            # 启动连接和重连管理
            self.reconnect_task = asyncio.create_task(self._connection_manager())

            # 等待连接管理任务
            await self.reconnect_task

        except Exception as e:
            self.logger.error("OKX WebSocket管理器启动失败", exc_info=True)
            raise

    async def stop(self):
        """停止OKX WebSocket管理器"""
        self.logger.info("🛑 停止OKX WebSocket管理器")

        self.is_running = False

        # 停止所有任务
        if self.heartbeat_task and not self.heartbeat_task.done():
            self.heartbeat_task.cancel()

        if self.listen_task and not self.listen_task.done():
            self.listen_task.cancel()

        if self.reconnect_task and not self.reconnect_task.done():
            self.reconnect_task.cancel()

        # 关闭WebSocket连接
        if self.websocket and not self.websocket.closed:
            await self.websocket.close()

        self.is_connected = False
        self.logger.info("✅ OKX WebSocket管理器已停止")

    async def connect(self) -> bool:
        """建立WebSocket连接"""
        try:
            self.logger.info("🔌 连接OKX WebSocket", url=self.ws_base_url)
            self.websocket = await websockets.connect(self.ws_base_url)
            self.is_connected = True
            self.last_message_time = time.time()

            # 重置重连计数
            self.current_reconnect_attempts = 0

            self.logger.info("✅ OKX WebSocket连接成功")
            return True

        except Exception as e:
            self.logger.error("❌ OKX WebSocket连接失败", error=str(e))
            self.is_connected = False
            return False

    async def _connection_manager(self):
        """连接管理器 - 处理连接和重连"""
        while self.is_running:
            try:
                await self._connect_and_run()
            except Exception as e:
                self.logger.error("OKX WebSocket连接异常", exc_info=True)

                if not self.is_running:
                    break

                # 计算重连延迟
                delay = min(
                    self.reconnect_delay * (self.backoff_multiplier ** self.current_reconnect_attempts),
                    self.max_reconnect_delay
                )

                self.current_reconnect_attempts += 1
                self.reconnect_count += 1

                self.logger.warning(f"🔄 {delay:.1f}秒后重连OKX WebSocket (第{self.reconnect_count}次重连)")
                await asyncio.sleep(delay)

    async def _connect_and_run(self):
        """连接并运行WebSocket"""
        # 连接WebSocket
        self.logger.info("🔌 连接OKX WebSocket", url=self.ws_base_url)
        self.websocket = await websockets.connect(self.ws_base_url)
        self.is_connected = True
        self.last_message_time = time.time()

        # 重置重连计数
        self.current_reconnect_attempts = 0

        try:
            # 订阅订单簿数据
            await self.subscribe_orderbook()

            # 启动心跳任务
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            # 启动消息监听
            self.listen_task = asyncio.create_task(self._listen_messages())

            # 等待任务完成（通常是连接断开）
            await asyncio.gather(self.heartbeat_task, self.listen_task, return_exceptions=True)

        finally:
            # 清理连接
            self.is_connected = False
            if self.websocket and not self.websocket.closed:
                await self.websocket.close()
    
    async def _heartbeat_loop(self):
        """OKX心跳循环 - 按照官方文档要求实现"""
        while self.is_connected and self.is_running:
            try:
                current_time = time.time()

                # 检查是否需要发送ping
                if current_time - self.last_message_time > self.heartbeat_interval:
                    if not self.waiting_for_pong:
                        self.logger.debug("💓 发送OKX心跳ping")
                        await self.websocket.send('ping')
                        self.waiting_for_pong = True
                        self.ping_sent_time = current_time
                    else:
                        # 检查pong超时
                        if current_time - self.ping_sent_time > self.pong_timeout:
                            self.logger.warning("💔 OKX心跳pong超时，触发重连")
                            raise Exception("心跳pong超时")

                await asyncio.sleep(1)  # 每秒检查一次

            except Exception as e:
                self.logger.error("OKX心跳循环异常", exc_info=True)
                break

    async def _listen_messages(self):
        """监听WebSocket消息"""
        self.logger.info("🎧 开始监听OKX WebSocket消息...")

        try:
            async for message in self.websocket:
                try:
                    self.total_messages += 1
                    self.last_message_time = time.time()

                    # 处理心跳响应
                    if message == 'pong':
                        self.logger.debug("💓 收到OKX心跳pong")
                        self.waiting_for_pong = False
                        continue

                    # 记录消息接收
                    if self.total_messages % 100 == 0:  # 每100条消息记录一次
                        self.logger.info(f"📊 已接收 {self.total_messages} 条OKX消息")

                    # 解析JSON消息
                    if isinstance(message, str):
                        data = json.loads(message)
                    else:
                        data = json.loads(message.decode('utf-8'))

                    # 处理消息
                    await self._handle_message(data)

                except json.JSONDecodeError as e:
                    self.logger.warning(f"⚠️ JSON解析失败: {e}")
                    continue
                except Exception as e:
                    self.logger.error(f"❌ 处理消息异常: {e}", exc_info=True)
                    continue

        except websockets.exceptions.ConnectionClosed as e:
            self.logger.warning(f"🔌 OKX WebSocket连接已关闭: {e}")
        except Exception as e:
            self.logger.error(f"❌ OKX WebSocket监听异常: {e}", exc_info=True)
        finally:
            self.logger.info(f"🔌 OKX WebSocket消息监听已停止 total_messages={self.total_messages}")
            self.is_connected = False



    async def disconnect(self):
        """断开WebSocket连接"""
        try:
            if self.websocket and self.is_connected:
                await self.websocket.close()
                self.is_connected = False
                self.logger.info("🔌 OKX WebSocket已断开")
        except Exception as e:
            self.logger.error("❌ 断开OKX WebSocket失败", error=str(e))
    
    async def _handle_message(self, message: Dict[str, Any]):
        """处理WebSocket消息"""
        try:
            self.logger.debug("🔍 处理OKX消息", message_keys=list(message.keys()) if isinstance(message, dict) else "非字典")

            if self.on_orderbook_update:
                # 解析OKX WebSocket消息格式
                if 'data' in message:
                    # 打印完整的外层消息结构用于调试
                    self.logger.info("🔍 完整OKX消息结构", message_keys=list(message.keys()),
                                   arg_info=message.get('arg', {}),
                                   action=message.get('action', 'unknown'))

                    # OKX订单簿数据格式
                    data_list = message['data']
                    self.logger.info("📊 收到OKX订单簿数据", data_count=len(data_list))

                    # 从外层消息中获取instId信息
                    symbol = None
                    if 'arg' in message and 'instId' in message['arg']:
                        symbol = message['arg']['instId']
                        self.logger.info("🎯 从外层消息获取到symbol", symbol=symbol)

                    for item in data_list:
                        self.logger.info("🔍 检查OKX数据项", item_keys=list(item.keys()) if isinstance(item, dict) else f"类型: {type(item)}")

                        # 优先使用数据项中的instId，如果没有则使用外层的
                        item_symbol = item.get('instId', symbol)

                        if item_symbol:
                            self.logger.info("📊 处理OKX订单簿更新", symbol=item_symbol, item_keys=list(item.keys()))

                            # 🎯 新增：确保传递action字段和完整的数据项
                            enhanced_item = item.copy()
                            enhanced_item['action'] = message.get('action', 'unknown')

                            # 🎯 确保seqId、prevSeqId、checksum字段存在
                            if 'seqId' in item:
                                self.logger.debug("✅ OKX数据包含seqId",
                                                symbol=item_symbol,
                                                seqId=item.get('seqId'),
                                                prevSeqId=item.get('prevSeqId'),
                                                checksum=item.get('checksum'))
                            else:
                                self.logger.warning("⚠️ OKX数据缺少seqId字段",
                                                  symbol=item_symbol,
                                                  item_keys=list(item.keys()))

                            # 🔍 调试：记录回调调用
                            self.logger.info(f"🔧 调用OKX WebSocket回调: {item_symbol}")

                            # 调用回调函数，传递symbol和增强的update数据
                            if asyncio.iscoroutinefunction(self.on_orderbook_update):
                                await self.on_orderbook_update(item_symbol, enhanced_item)
                            else:
                                self.on_orderbook_update(item_symbol, enhanced_item)

                            self.logger.debug(f"✅ OKX WebSocket回调完成: {item_symbol}")
                        else:
                            self.logger.warning("❌ OKX数据项和外层消息都缺少instId",
                                              item_keys=list(item.keys()) if isinstance(item, dict) else f"类型: {type(item)}",
                                              message_keys=list(message.keys()))
                            # 打印完整的数据项内容用于调试
                            self.logger.warning("完整数据项内容", item=str(item)[:500])

                elif 'event' in message:
                    # 订阅确认或错误消息
                    if message['event'] == 'subscribe':
                        self.logger.info("OKX订阅成功", message=message)
                    elif message['event'] == 'error':
                        self.logger.error("OKX订阅错误", message=message)
                    else:
                        self.logger.debug("收到OKX事件消息", message=message)
                else:
                    # 其他格式的消息
                    self.logger.warning("收到未知格式的OKX消息", message=str(message)[:200])

        except Exception as e:
            self.logger.error("❌ 处理OKX WebSocket消息失败", error=str(e), message=str(message)[:200])
    
    async def _handle_error(self, error: Exception):
        """处理WebSocket错误"""
        self.logger.error("❌ OKX WebSocket错误", error=str(error))
        self.is_connected = False
    
    async def _handle_close(self, code: int, reason: str):
        """处理WebSocket关闭"""
        self.logger.warning("🔌 OKX WebSocket连接关闭", 
                          code=code, reason=reason)
        self.is_connected = False
    
    def get_connection_status(self) -> Dict[str, Any]:
        """获取连接状态"""
        return {
            'connected': self.is_connected,
            'ws_url': self.ws_base_url,
            'market_type': self.market_type,
            'symbols': self.symbols,
            'websocket_depth': self.websocket_depth
        }

    async def send_message(self, message: Dict[str, Any]):
        """发送消息到WebSocket"""
        try:
            if self.websocket and self.is_connected:
                await self.websocket.send(json.dumps(message))
            else:
                self.logger.warning("⚠️ WebSocket未连接，无法发送消息")
        except Exception as e:
            self.logger.error("❌ 发送WebSocket消息失败", error=str(e))
    
    async def subscribe_orderbook(self, symbols: List[str] = None):
        """订阅订单簿数据"""
        if symbols is None:
            symbols = self.symbols
        
        try:
            # OKX订单簿订阅消息格式
            subscribe_args = []
            for symbol in symbols:
                # 根据市场类型调整symbol格式
                if self.market_type == 'perpetual':
                    # 永续合约格式：BTC-USDT-SWAP
                    if not symbol.endswith('-SWAP'):
                        symbol = f"{symbol}-SWAP"
                
                subscribe_args.append({
                    "channel": "books",
                    "instId": symbol
                })
            
            subscribe_msg = {
                "op": "subscribe",
                "args": subscribe_args
            }
            
            await self.send_message(subscribe_msg)
            self.logger.info("📊 已订阅OKX订单簿数据", symbols=symbols)
            
        except Exception as e:
            self.logger.error("❌ 订阅OKX订单簿失败", error=str(e))
    
    async def unsubscribe_orderbook(self, symbols: List[str] = None):
        """取消订阅订单簿数据"""
        if symbols is None:
            symbols = self.symbols
        
        try:
            unsubscribe_args = []
            for symbol in symbols:
                if self.market_type == 'perpetual':
                    if not symbol.endswith('-SWAP'):
                        symbol = f"{symbol}-SWAP"
                
                unsubscribe_args.append({
                    "channel": "books",
                    "instId": symbol
                })
            
            unsubscribe_msg = {
                "op": "unsubscribe",
                "args": unsubscribe_args
            }
            
            await self.send_message(unsubscribe_msg)
            self.logger.info("📊 已取消订阅OKX订单簿数据", symbols=symbols)
            
        except Exception as e:
            self.logger.error("❌ 取消订阅OKX订单簿失败", error=str(e))


# 向后兼容的别名
OKXWebSocketClient = OKXWebSocketManager
OKXWebSocket = OKXWebSocketManager
