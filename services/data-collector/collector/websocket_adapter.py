"""
WebSocket适配器

为现有的OrderBook Manager提供新的WebSocket连接能力，
保持现有代码逻辑不变，只替换WebSocket连接层。

设计原则：
- 最小化对现有代码的修改
- 保持现有OrderBook Manager的所有功能
- 提供统一的WebSocket连接管理
- 确保向后兼容性
"""

import asyncio
import orjson  # 🚀 性能优化：使用 orjson 替换标准库 json（2-3x 性能提升）
from typing import Dict, Any, Optional, Callable, List
import structlog

# 导入核心网络组件
from core.networking import (
    WebSocketConnectionManager, 
    DataType,
    websocket_manager,
    create_binance_websocket_config,
    create_okx_websocket_config
)

# 导入数据类型
from .data_types import Exchange, MarketType


class WebSocketAdapter:
    """
    WebSocket适配器
    
    为现有的OrderBook Manager提供新的WebSocket连接能力，
    保持现有接口不变。
    """
    
    def __init__(self,
                 exchange: Exchange,
                 market_type: MarketType,
                 symbols: List[str],
                 on_message_callback: Callable[[Dict[str, Any]], None] = None,
                 websocket_depth: int = 20):
        """
        初始化WebSocket适配器

        Args:
            exchange: 交易所
            market_type: 市场类型
            symbols: 交易对列表
            on_message_callback: 消息回调函数
            websocket_depth: WebSocket订阅深度
        """
        self.exchange = exchange
        self.market_type = market_type
        self.symbols = symbols
        self.on_message_callback = on_message_callback
        self.websocket_depth = websocket_depth
        
        # 使用全局WebSocket管理器
        self.websocket_manager = websocket_manager
        
        # 连接状态
        self.connection_key = None
        self.connection = None
        self.is_connected = False
        
        # 日志记录器
        self.logger = structlog.get_logger(__name__).bind(
            exchange=exchange.value,
            market_type=market_type.value
        )
        
        # 统计信息
        self.stats = {
            'messages_received': 0,
            'connection_attempts': 0,
            'successful_connections': 0,
            'connection_errors': 0
        }
    
    async def connect(self) -> bool:
        """
        建立支持长期运行的WebSocket连接

        Returns:
            连接是否成功
        """
        try:
            self.logger.info("建立长期WebSocket连接", symbols=self.symbols)
            self.stats['connection_attempts'] += 1

            # 创建WebSocket配置（启用自动重连）
            ws_config = self._create_websocket_config()
            ws_config.auto_reconnect = True
            ws_config.max_reconnect_attempts = -1  # 无限重连
            ws_config.reconnect_delay = 1.0
            ws_config.max_reconnect_delay = 300.0
            ws_config.backoff_multiplier = 2.0

            # 生成连接标识
            self.connection_key = f"{self.exchange.value}_{self.market_type.value}_{id(self)}"

            # 建立支持自动重连的连接
            success = await self.websocket_manager.connect_with_auto_reconnect(
                connection_id=self.connection_key,
                config=ws_config
            )

            if not success:
                self.logger.error("WebSocket连接建立失败")
                self.stats['connection_errors'] += 1
                return False

            # 获取连接对象
            self.connection = self.websocket_manager.connections.get(self.connection_key)

            # 订阅数据
            self.logger.info("开始订阅数据", exchange=self.exchange.value, market_type=self.market_type.value)
            success = await self._subscribe_data()
            if not success:
                self.logger.error("数据订阅失败，断开连接", exchange=self.exchange.value)
                await self.disconnect()
                return False

            self.logger.info("数据订阅成功", exchange=self.exchange.value)

            # 启动消息处理循环
            asyncio.create_task(self._message_loop())

            self.is_connected = True
            self.stats['successful_connections'] += 1

            self.logger.info("长期WebSocket连接建立成功",
                           connection_key=self.connection_key,
                           auto_reconnect=True)
            return True

        except Exception as e:
            self.logger.error("建立WebSocket连接失败", error=str(e), exc_info=True)
            self.stats['connection_errors'] += 1
            return False
    
    async def disconnect(self):
        """断开WebSocket连接"""
        try:
            self.is_connected = False

            if self.connection_key:
                # 使用新的关闭方法，会自动停止监控任务
                await self.websocket_manager.close_connection(self.connection_key)
                self.connection_key = None

            self.connection = None

            self.logger.info("WebSocket连接已断开")

        except Exception as e:
            self.logger.error("断开WebSocket连接失败", error=str(e))
    
    async def send(self, message: Dict[str, Any]):
        """
        发送消息
        
        Args:
            message: 要发送的消息
        """
        try:
            # 🔧 修复：检查连接状态，但不依赖is_connected标志
            if not self.connection:
                self.logger.error("WebSocket连接对象不存在")
                return False

            # 检查连接是否关闭
            if hasattr(self.connection, 'closed') and self.connection.closed:
                self.logger.error("WebSocket连接已关闭")
                return False

            message_str = orjson.dumps(message).decode('utf-8')  # orjson 返回 bytes，需要 decode
            await self.connection.send(message_str)

            self.logger.debug("消息发送成功", message=message)
            return True

        except Exception as e:
            self.logger.error("发送消息失败", error=str(e), message=message)
            return False
    
    def _create_websocket_config(self):
        """创建WebSocket配置"""
        try:
            # 🔧 修复：支持新的交易所枚举类型
            if self.exchange in [Exchange.BINANCE, Exchange.BINANCE_SPOT, Exchange.BINANCE_DERIVATIVES]:
                return create_binance_websocket_config(
                    market_type=self.market_type.value,
                    symbols=self.symbols,
                    data_types=["orderbook", "trade"],
                    websocket_depth=self.websocket_depth
                )
            elif self.exchange in [Exchange.OKX, Exchange.OKX_SPOT, Exchange.OKX_DERIVATIVES]:
                return create_okx_websocket_config(
                    market_type=self.market_type.value,
                    symbols=self.symbols,
                    data_types=["orderbook", "trade"]
                )
            else:
                raise ValueError(f"不支持的交易所: {self.exchange}")

        except Exception as e:
            self.logger.error("创建WebSocket配置失败", error=str(e))
            raise

    async def subscribe(self) -> bool:
        """订阅数据（公共接口）"""
        return await self._subscribe_data()
    
    async def _subscribe_data(self) -> bool:
        """订阅数据"""
        try:
            # 🔧 修复：支持新的交易所枚举类型
            if self.exchange in [Exchange.BINANCE, Exchange.BINANCE_SPOT, Exchange.BINANCE_DERIVATIVES]:
                # Binance的订阅已经在URL中完成
                return True
            elif self.exchange in [Exchange.OKX, Exchange.OKX_SPOT, Exchange.OKX_DERIVATIVES]:
                # OKX需要发送订阅消息
                return await self._subscribe_okx_data()
            else:
                self.logger.error("不支持的交易所", exchange=self.exchange.value)
                return False

        except Exception as e:
            self.logger.error("订阅数据失败", error=str(e))
            return False
    
    async def _subscribe_okx_data(self) -> bool:
        """订阅OKX数据"""
        try:
            # 构建订阅请求
            subscribe_requests = []
            
            for symbol in self.symbols:
                # 🔧 修复：根据市场类型处理符号格式
                market_type_str = self.market_type.value.lower()
                if market_type_str in ["perpetual", "swap", "futures"]:
                    # 永续合约：确保符号格式为 BTC-USDT-SWAP
                    if symbol.endswith("-SWAP"):
                        okx_symbol = symbol
                    else:
                        okx_symbol = f"{symbol}-SWAP"
                else:
                    # 现货：使用原始符号格式
                    okx_symbol = symbol

                self.logger.debug("OKX符号映射",
                                original=symbol,
                                okx_symbol=okx_symbol,
                                market_type=market_type_str)
                
                # 订阅订单簿数据
                subscribe_requests.append({
                    "op": "subscribe",
                    "args": [{
                        "channel": "books",
                        "instId": okx_symbol
                    }]
                })
                
                # 订阅交易数据
                subscribe_requests.append({
                    "op": "subscribe",
                    "args": [{
                        "channel": "trades",
                        "instId": okx_symbol
                    }]
                })
            
            # 发送订阅请求
            for request in subscribe_requests:
                success = await self.send(request)
                if not success:
                    return False
                
                # 等待一小段时间避免频率限制
                await asyncio.sleep(0.1)
            
            self.logger.info("OKX数据订阅成功", symbols=self.symbols)
            return True
            
        except Exception as e:
            self.logger.error("OKX数据订阅失败", error=str(e))
            return False
    
    async def _message_loop(self):
        """消息处理循环"""
        try:
            self.logger.info("启动消息处理循环")

            while self.is_connected:
                try:
                    # 获取当前连接（可能因重连而变化）
                    current_connection = self.websocket_manager.connections.get(self.connection_key)
                    if not current_connection:
                        self.logger.warning("连接丢失，等待重连")
                        await asyncio.sleep(1)
                        continue

                    # 接收消息
                    async for message in current_connection:
                        if not self.is_connected:
                            break

                        try:
                            # 解析消息
                            if isinstance(message, str):
                                data = orjson.loads(message)
                            else:
                                data = message

                            # 更新统计
                            self.stats['messages_received'] += 1

                            # 使用统一的消息路由
                            await self.websocket_manager.route_message(self.connection_key, data)

                            # 调用回调函数（保持向后兼容）
                            if self.on_message_callback:
                                if asyncio.iscoroutinefunction(self.on_message_callback):
                                    await self.on_message_callback(data)
                                else:
                                    self.on_message_callback(data)

                        except (orjson.JSONDecodeError, ValueError) as e:  # orjson 抛出 ValueError
                            self.logger.error("消息解析失败", error=str(e))
                        except Exception as e:
                            self.logger.error("消息处理失败", error=str(e))

                except Exception as e:
                    self.logger.error("消息循环异常", error=str(e))
                    # 等待一段时间后重试
                    await asyncio.sleep(5)

        except asyncio.CancelledError:
            self.logger.info("消息处理循环已取消")
        except Exception as e:
            self.logger.error("消息处理循环异常", error=str(e))
        finally:
            self.is_connected = False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            'exchange': self.exchange.value,
            'market_type': self.market_type.value,
            'symbols': self.symbols,
            'is_connected': self.is_connected,
            'connection_key': self.connection_key
        }


class OrderBookWebSocketAdapter(WebSocketAdapter):
    """
    专门为OrderBook Manager设计的WebSocket适配器
    
    提供与现有OrderBook Manager兼容的接口
    """
    
    def __init__(self, 
                 exchange: Exchange,
                 market_type: MarketType,
                 symbols: List[str],
                 orderbook_manager=None):
        """
        初始化OrderBook WebSocket适配器
        
        Args:
            exchange: 交易所
            market_type: 市场类型
            symbols: 交易对列表
            orderbook_manager: OrderBook Manager实例
        """
        super().__init__(exchange, market_type, symbols)
        self.orderbook_manager = orderbook_manager
        
        # 设置消息回调
        self.on_message_callback = self._handle_orderbook_message
    
    async def _handle_orderbook_message(self, data: Dict[str, Any]):
        """处理订单簿消息"""
        try:
            if not self.orderbook_manager:
                return
            
            # 根据交易所类型处理消息
            # 🔧 修复：支持新的交易所枚举类型
            if self.exchange in [Exchange.BINANCE, Exchange.BINANCE_SPOT, Exchange.BINANCE_DERIVATIVES]:
                await self._handle_binance_message(data)
            elif self.exchange in [Exchange.OKX, Exchange.OKX_SPOT, Exchange.OKX_DERIVATIVES]:
                await self._handle_okx_message(data)
            
        except Exception as e:
            self.logger.error("订单簿消息处理失败", error=str(e))
    
    async def _handle_binance_message(self, data: Dict[str, Any]):
        """处理Binance消息"""
        try:
            # Binance消息结构: {'stream': 'btcusdt@depth', 'data': {...}}
            # symbol在data字段内部
            symbol = None

            if 'data' in data and isinstance(data['data'], dict):
                # 从data字段中提取symbol
                symbol = data['data'].get('s', '').upper()

            if not symbol:
                # 尝试从stream字段解析symbol
                stream = data.get('stream', '')
                if '@' in stream:
                    symbol_part = stream.split('@')[0].upper()
                    # 转换为标准格式 (例如: btcusdt -> BTC-USDT)
                    if 'usdt' in symbol_part.lower():
                        base = symbol_part.replace('USDT', '').replace('usdt', '')
                        symbol = f"{base}-USDT"
                    elif 'busd' in symbol_part.lower():
                        base = symbol_part.replace('BUSD', '').replace('busd', '')
                        symbol = f"{base}-BUSD"

            if not symbol:
                self.logger.warning("❌ Binance消息缺少symbol字段",
                                  data_keys=list(data.keys()),
                                  stream=data.get('stream', 'N/A'))
                return

            # 调用现有OrderBook Manager的消息处理方法，传递正确的参数
            if hasattr(self.orderbook_manager, '_handle_binance_websocket_update'):
                await self.orderbook_manager._handle_binance_websocket_update(symbol, data)
            elif hasattr(self.orderbook_manager, 'handle_message'):
                await self.orderbook_manager.handle_message(data)

        except Exception as e:
            self.logger.error("Binance消息处理失败", error=str(e))
    
    async def _handle_okx_message(self, data: Dict[str, Any]):
        """处理OKX消息"""
        try:
            # OKX消息结构: {'arg': {'channel': 'books', 'instId': 'BTC-USDT'}, 'action': 'snapshot', 'data': [...]}
            symbol = None

            # 首先尝试从arg字段获取symbol
            if 'arg' in data and isinstance(data['arg'], dict):
                symbol = data['arg'].get('instId', '').upper()

            # 如果arg中没有，尝试从data数组中的第一个item获取
            if not symbol and 'data' in data and isinstance(data['data'], list) and len(data['data']) > 0:
                first_item = data['data'][0]
                if isinstance(first_item, dict):
                    symbol = first_item.get('instId', '').upper()

            if not symbol:
                self.logger.warning("❌ OKX消息缺少symbol字段",
                                  data_keys=list(data.keys()),
                                  arg=data.get('arg', 'N/A'),
                                  action=data.get('action', 'N/A'))
                return

            # 调用现有OrderBook Manager的消息处理方法，传递正确的参数
            if hasattr(self.orderbook_manager, '_handle_okx_websocket_update'):
                await self.orderbook_manager._handle_okx_websocket_update(symbol, data)
            elif hasattr(self.orderbook_manager, 'handle_message'):
                await self.orderbook_manager.handle_message(data)

        except Exception as e:
            self.logger.error("OKX消息处理失败", error=str(e))
