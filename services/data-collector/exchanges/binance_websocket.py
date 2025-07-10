"""
Binance WebSocket客户端
基于统一WebSocket管理器的Binance特定实现
符合orderbook_manager期望的接口
参考OKX成功经验进行优化，实现统一的WebSocket接口
"""

import asyncio
import json
import ssl
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime, timezone
import structlog

# 使用简化的WebSocket实现，避免复杂的依赖问题
import websockets

# 🔧 标准化导入路径 - 支持动态导入
import sys
from pathlib import Path

# 添加exchanges目录到Python路径以支持动态导入
exchanges_dir = Path(__file__).parent
if str(exchanges_dir) not in sys.path:
    sys.path.insert(0, str(exchanges_dir))

from base_websocket import BaseWebSocketClient


class BinanceWebSocketClient(BaseWebSocketClient):
    """
    Binance WebSocket客户端
    基于统一WebSocket管理器，符合orderbook_manager期望的接口
    """
    
    def __init__(self,
                 symbols: List[str],
                 on_orderbook_update: Callable[[str, Dict[str, Any]], None] = None,
                 ws_base_url: str = None,
                 market_type: str = 'spot',
                 websocket_depth: int = 1000):
        """
        初始化Binance WebSocket客户端

        Args:
            symbols: 交易对列表
            on_orderbook_update: 订单簿更新回调函数 (symbol, data)
            ws_base_url: WebSocket基础URL
            market_type: 市场类型 ('spot', 'perpetual')
            websocket_depth: WebSocket深度（Binance支持更高深度）
        """
        # 调用父类构造函数
        super().__init__(symbols, on_orderbook_update, market_type, websocket_depth)

        self.ws_base_url = ws_base_url or "wss://stream.binance.com:9443/ws"
        self.logger = structlog.get_logger(__name__)

        # WebSocket连接状态
        self.websocket = None
        self.listen_task = None

        # 统计信息（参考OKX的统计管理）
        self.last_message_time = None
        self.connection_start_time = None

        # 构建WebSocket URL（参考OKX的URL管理策略）
        if market_type == 'perpetual':
            self.ws_url = "wss://fstream.binance.com/ws"
        else:
            self.ws_url = "wss://stream.binance.com:9443/ws"
    
    # 移除复杂的配置创建方法
    
    async def start(self):
        """启动WebSocket客户端（orderbook_manager期望的接口）"""
        return await self.connect()

    async def stop(self):
        """停止WebSocket客户端"""
        self.logger.info("🛑 停止Binance WebSocket客户端")
        self.is_running = False

        if self.listen_task and not self.listen_task.done():
            self.listen_task.cancel()
            try:
                await self.listen_task
            except asyncio.CancelledError:
                pass

        await self.disconnect()
    
    async def connect(self):
        """连接到Binance WebSocket（参考OKX连接策略）"""
        try:
            self.logger.info("🔌 连接Binance WebSocket",
                           market_type=self.market_type,
                           symbols=self.symbols,
                           url=self.ws_url)

            # 创建SSL上下文（参考OKX的SSL配置）
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            # 建立WebSocket连接（参考OKX的连接参数）
            self.websocket = await websockets.connect(
                self.ws_url,
                ssl=ssl_context,
                ping_timeout=30,      # 参考OKX的超时设置
                close_timeout=10,
                max_size=2**20,       # 1MB缓冲区，参考OKX的缓冲区配置
                compression=None      # Binance不支持压缩
            )
            self.is_connected = True
            self.connection_start_time = datetime.now(timezone.utc)
            self.last_message_time = asyncio.get_event_loop().time()

            # 订阅订单簿数据
            await self.subscribe_orderbook()

            # 启动消息监听（参考OKX的任务管理）
            self.listen_task = asyncio.create_task(self._listen_messages())
            self.logger.info("🎧 WebSocket消息监听任务已启动")

            self.logger.info("✅ Binance WebSocket连接成功", url=self.ws_url)
            return True

        except Exception as e:
            self.logger.error("❌ Binance WebSocket连接异常", error=str(e), exc_info=True)
            self.is_connected = False
            return False
    
    async def _listen_messages(self):
        """监听WebSocket消息（参考OKX的消息处理逻辑）"""
        self.logger.info("🎧 开始监听Binance WebSocket消息...")

        try:
            # 连接状态检查（参考OKX的状态检查）
            if not self.websocket:
                self.logger.error("❌ WebSocket对象为空，无法监听消息")
                return

            self.logger.info("🔄 进入WebSocket消息循环...")

            async for message in self.websocket:
                try:
                    self.message_count += 1
                    current_time = asyncio.get_event_loop().time()

                    # 更新最后消息时间
                    if self.last_message_time:
                        time_since_last = current_time - self.last_message_time
                    else:
                        time_since_last = 0
                    self.last_message_time = current_time

                    # 定期报告状态（参考OKX的状态报告频率）
                    if self.message_count % 10 == 0:
                        self.logger.info("📊 消息处理状态",
                                       processed=self.message_count,
                                       connection_alive=True,
                                       error_count=self.error_count,
                                       error_rate=f"{self.error_count/max(self.message_count,1)*100:.2f}%")

                    # 解析和处理消息
                    data = json.loads(message)
                    await self._handle_message(data)

                except json.JSONDecodeError as e:
                    self.error_count += 1
                    self.logger.error("❌ JSON解析失败", error=str(e), message=message[:200])
                except Exception as e:
                    self.error_count += 1
                    self.logger.error("❌ 处理消息失败", error=str(e), message_count=self.message_count)

            # 如果循环结束，说明连接断开
            self.logger.warning("🔌 WebSocket消息循环结束，连接可能已断开")

        except Exception as e:
            self.error_count += 1
            self.logger.error("❌ 消息监听失败", error=str(e), message_count=self.message_count)
            self.is_connected = False

        self.logger.warning("🔌 WebSocket消息监听已停止",
                          total_messages=self.message_count,
                          total_errors=self.error_count)

    async def disconnect(self):
        """断开WebSocket连接（参考OKX的清理逻辑）"""
        try:
            # 取消监听任务
            if self.listen_task and not self.listen_task.done():
                self.listen_task.cancel()
                try:
                    await self.listen_task
                except asyncio.CancelledError:
                    pass

            # 关闭WebSocket连接
            if self.websocket and self.is_connected:
                await self.websocket.close()
                self.is_connected = False

            # 记录连接统计信息（参考OKX的统计记录）
            uptime = None
            if self.connection_start_time:
                uptime = (datetime.now(timezone.utc) - self.connection_start_time).total_seconds()

            self.logger.info("🔌 Binance WebSocket已断开",
                           total_messages=self.message_count,
                           total_errors=self.error_count,
                           error_rate=f"{self.error_count/max(self.message_count,1)*100:.2f}%",
                           uptime_seconds=uptime)

        except Exception as e:
            self.logger.error("❌ 断开Binance WebSocket失败", error=str(e))
    
    async def _handle_message(self, message: Dict[str, Any]):
        """处理WebSocket消息（参考OKX的消息处理结构和数据验证）"""
        try:
            # 🔍 调试：记录所有接收到的消息
            self.logger.info("🔍 Binance WebSocket收到消息",
                           message_keys=list(message.keys()) if isinstance(message, dict) else "非字典",
                           market_type=self.market_type,
                           message_preview=str(message)[:200])

            if not self.on_orderbook_update:
                self.logger.warning("❌ 回调函数未设置")
                return

            # 处理订阅确认消息
            if 'result' in message or 'id' in message:
                self.logger.info("📋 收到Binance订阅确认", message=message)
                return

            # 处理多流格式消息
            if 'stream' in message and 'data' in message:
                stream = message['stream']
                data = message['data']
                symbol = stream.split('@')[0].upper()

                self.logger.debug("处理Binance多流消息", symbol=symbol, stream=stream)

                # 验证数据完整性（参考OKX的数据验证）
                if self._validate_orderbook_data(data):
                    await self._call_update_callback(symbol, data)
                else:
                    self.logger.warning("❌ 多流消息数据验证失败", symbol=symbol)

            # 处理单一流深度更新消息
            elif 'e' in message and message.get('e') == 'depthUpdate':
                symbol = message.get('s', '').upper()

                if not symbol:
                    self.logger.warning("❌ 深度更新消息缺少symbol", message=str(message)[:200])
                    return

                # 验证数据完整性（根据官方文档更新）
                if self._validate_orderbook_data(message):
                    # 记录深度更新信息（区分现货和永续合约）
                    log_data = {
                        'symbol': symbol,
                        'update_id': message.get('u', 'N/A'),
                        'first_update_id': message.get('U', 'N/A'),
                        'bids_count': len(message.get('b', [])),
                        'asks_count': len(message.get('a', []))
                    }

                    # 永续合约特有字段
                    if self.market_type == 'perpetual' and 'pu' in message:
                        log_data['prev_update_id'] = message.get('pu', 'N/A')

                    self.logger.debug("📊 处理Binance深度更新", **log_data)

                    await self._call_update_callback(symbol, message)
                else:
                    self.logger.warning("❌ 深度更新数据验证失败", symbol=symbol)

            # 处理完整订单簿快照格式
            elif 'lastUpdateId' in message and 'bids' in message and 'asks' in message:
                symbol = self.symbols[0].upper() if self.symbols else "UNKNOWN"

                # 转换为增量更新格式
                converted_data = {
                    'U': message['lastUpdateId'],
                    'u': message['lastUpdateId'],
                    'b': message['bids'],
                    'a': message['asks']
                }

                self.logger.debug("转换快照为增量格式", symbol=symbol, lastUpdateId=message['lastUpdateId'])
                await self._call_update_callback(symbol, converted_data)

            else:
                # 其他格式的消息
                self.logger.debug("收到其他格式的Binance消息",
                                message_keys=list(message.keys()),
                                message_preview=str(message)[:200])

        except Exception as e:
            self.error_count += 1
            self.logger.error("❌ 处理Binance WebSocket消息失败",
                            error=str(e),
                            message=str(message)[:200])
    
    def _validate_orderbook_data(self, data: Dict[str, Any]) -> bool:
        """验证订单簿数据完整性（根据官方文档更新验证逻辑）"""
        try:
            # 检查必需字段
            if 'e' in data and data.get('e') == 'depthUpdate':
                # 深度更新格式验证（根据官方文档）
                required_fields = ['s', 'U', 'u', 'b', 'a']
                for field in required_fields:
                    if field not in data:
                        self.logger.warning(f"❌ 深度更新缺少必需字段: {field}")
                        return False

                # 永续合约特有字段验证
                if self.market_type == 'perpetual':
                    # 永续合约应该有 'pu' 字段（上一个流的最终更新ID）
                    if 'pu' not in data:
                        self.logger.debug("⚠️ 永续合约深度更新缺少pu字段", symbol=data.get('s'))
                        # 不作为错误，因为可能是第一条消息

            else:
                # 其他格式的基本验证
                if not isinstance(data.get('bids'), list) or not isinstance(data.get('asks'), list):
                    if not isinstance(data.get('b'), list) or not isinstance(data.get('a'), list):
                        self.logger.warning("❌ bids/asks或b/a不是列表类型")
                        return False

            # 检查更新ID的合理性（如果存在）
            if 'U' in data and 'u' in data:
                first_update_id = data.get('U', 0)
                last_update_id = data.get('u', 0)
                if last_update_id < first_update_id:
                    self.logger.warning("❌ 更新ID不合理",
                                      first_id=first_update_id,
                                      last_id=last_update_id)
                    return False

            return True

        except Exception as e:
            self.logger.error("❌ 数据验证异常", error=str(e))
            return False

    async def _call_update_callback(self, symbol: str, data: Dict[str, Any]):
        """调用更新回调函数（参考OKX的回调处理）"""
        try:
            # 🔍 调试：记录回调调用
            self.logger.info(f"🔧 调用Binance WebSocket回调: {symbol}")

            if asyncio.iscoroutinefunction(self.on_orderbook_update):
                await self.on_orderbook_update(symbol, data)
            else:
                self.on_orderbook_update(symbol, data)

            self.logger.debug(f"✅ Binance WebSocket回调完成: {symbol}")
        except Exception as e:
            self.error_count += 1
            self.logger.error("❌ 回调函数执行失败", error=str(e), symbol=symbol)

    async def send_message(self, message: Dict[str, Any]):
        """发送WebSocket消息（添加缺失的方法）"""
        try:
            if self.websocket and self.is_connected:
                message_str = json.dumps(message)
                await self.websocket.send(message_str)
                self.logger.debug("📤 发送WebSocket消息", message=message)
            else:
                self.logger.error("❌ WebSocket未连接，无法发送消息")
        except Exception as e:
            self.error_count += 1
            self.logger.error("❌ 发送WebSocket消息失败", error=str(e), message=message)

    async def _handle_error(self, error: Exception):
        """处理WebSocket错误"""
        self.error_count += 1
        self.logger.error("❌ Binance WebSocket错误", error=str(error))
        self.is_connected = False

    async def _handle_close(self, code: int, reason: str):
        """处理WebSocket关闭"""
        self.logger.warning("🔌 Binance WebSocket连接关闭",
                          code=code, reason=reason)
        self.is_connected = False
    
    def get_connection_status(self) -> Dict[str, Any]:
        """获取连接状态（参考OKX的状态报告格式）"""
        uptime = None
        if self.connection_start_time:
            uptime = (datetime.now(timezone.utc) - self.connection_start_time).total_seconds()

        return {
            'connected': self.is_connected,
            'ws_url': self.ws_url,
            'market_type': self.market_type,
            'symbols': self.symbols,
            'websocket_depth': self.websocket_depth,
            'message_count': self.message_count,
            'error_count': self.error_count,
            'error_rate': self.error_count / max(self.message_count, 1),
            'uptime_seconds': uptime,
            'last_message_time': self.last_message_time,
            'connection_start_time': self.connection_start_time.isoformat() if self.connection_start_time else None
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
        """订阅订单簿数据（根据官方文档修复）"""
        if symbols is None:
            symbols = self.symbols

        try:
            # 构建订阅参数列表
            params = []
            for symbol in symbols:
                # 根据官方文档：现货和永续合约都使用@depth订阅深度更新
                # 现货: <symbol>@depth (推送depthUpdate事件)
                # 永续合约: <symbol>@depth (推送depthUpdate事件，包含pu字段)
                params.append(f"{symbol.lower()}@depth")

            # 发送单个订阅消息包含所有交易对
            subscribe_msg = {
                "method": "SUBSCRIBE",
                "params": params,
                "id": 1
            }
            await self.send_message(subscribe_msg)

            self.logger.info("📊 已订阅Binance订单簿深度更新",
                           symbols=symbols,
                           params=params,
                           market_type=self.market_type)

        except Exception as e:
            self.error_count += 1
            self.logger.error("❌ 订阅Binance订单簿失败", error=str(e))
    
    async def unsubscribe_orderbook(self, symbols: List[str] = None):
        """取消订阅订单簿数据"""
        if symbols is None:
            symbols = self.symbols
        
        try:
            for symbol in symbols:
                unsubscribe_msg = {
                    "method": "UNSUBSCRIBE",
                    # 🔧 修复：使用与订阅一致的流格式
                    "params": [f"{symbol.lower()}@depth"],
                    "id": 2
                }
                await self.send_message(unsubscribe_msg)
                
            self.logger.info("📊 已取消订阅Binance订单簿数据", symbols=symbols)
            
        except Exception as e:
            self.logger.error("❌ 取消订阅Binance订单簿失败", error=str(e))


# 向后兼容的别名
BinanceWebSocket = BinanceWebSocketClient
