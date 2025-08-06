"""
BinanceDerivativesLiquidationManager - Binance衍生品强平订单数据管理器

重构为全市场模式，基于Binance官方文档：
https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Liquidation-Order-Streams

WebSocket频道：!forceOrder@arr (全市场强平流)
数据格式：包含所有交易对的强平数据，客户端进行过滤
更新频率：实时推送所有市场的强平事件
优势：持续的数据流，便于区分技术问题和市场现象
"""

import asyncio
import json
import websockets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any, Set

from .base_liquidation_manager import BaseLiquidationManager
from collector.data_types import Exchange, MarketType, NormalizedLiquidation


class BinanceDerivativesLiquidationManager(BaseLiquidationManager):
    """
    Binance衍生品强平订单数据管理器 - 全市场模式

    订阅Binance的!forceOrder@arr频道，接收所有交易对的强平数据
    在接收端进行symbol过滤，只处理指定的交易对
    """
    
    def __init__(self, symbols: List[str], normalizer, nats_publisher, config: dict):
        """
        初始化Binance衍生品强平管理器 - 全市场模式

        Args:
            symbols: 目标交易对列表（如 ['BTCUSDT', 'ETHUSDT']）- 用于过滤
            normalizer: 数据标准化器
            nats_publisher: NATS发布器
            config: 配置信息
        """
        super().__init__(
            exchange=Exchange.BINANCE_DERIVATIVES,
            market_type=MarketType.PERPETUAL,
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher,
            config=config
        )

        # Binance WebSocket配置
        self.ws_url = config.get('ws_url', "wss://fstream.binance.com/ws")
        
        # Binance特定配置
        self.heartbeat_interval = config.get('heartbeat_interval', 180)  # Binance衍生品推荐180秒
        self.connection_timeout = config.get('connection_timeout', 10)
        
        # 消息处理配置
        self.message_queue = asyncio.Queue()
        self.message_processor_task = None

        # 全市场模式配置
        self.all_market_stream = "!forceOrder@arr"  # 全市场强平流
        self.target_symbols = set(symbol.upper() for symbol in symbols)  # 目标交易对集合

        # 统计信息
        self.stats = {
            'total_received': 0,      # 总接收消息数
            'filtered_messages': 0,   # 过滤后的消息数
            'target_symbols_data': 0, # 目标交易对数据数
            'other_symbols_data': 0   # 其他交易对数据数
        }

        self.logger.startup(
            "Binance衍生品强平管理器初始化完成",
            mode="全市场模式",
            target_symbols=list(self.target_symbols),
            stream=self.all_market_stream,
            ws_url=self.ws_url,
            heartbeat_interval=self.heartbeat_interval
        )

    async def _connect_and_listen(self):
        """连接Binance WebSocket并监听强平数据"""
        try:
            # 构建全市场WebSocket URL
            full_url = f"{self.ws_url}/{self.all_market_stream}"

            self.logger.info(
                "连接Binance全市场强平WebSocket",
                url=full_url,
                mode="全市场模式",
                target_symbols=list(self.target_symbols)
            )
            
            # 使用asyncio.wait_for实现连接超时
            websocket = await asyncio.wait_for(
                websockets.connect(
                    full_url,
                    ping_interval=self.heartbeat_interval,
                    ping_timeout=60,
                    close_timeout=10
                ),
                timeout=self.connection_timeout
            )

            async with websocket:
                self.websocket = websocket
                self.last_successful_connection = datetime.now(timezone.utc)
                self.reconnect_attempts = 0  # 重置重连计数
                
                self.logger.info(
                    "Binance全市场强平WebSocket连接成功",
                    url=full_url,
                    mode="全市场模式"
                )
                
                # 启动消息处理器
                self.message_processor_task = asyncio.create_task(self._message_processor())
                
                # 监听消息（Binance不需要额外订阅，URL中已包含流名称）
                await self._listen_messages()
                
        except websockets.exceptions.ConnectionClosed as e:
            self.logger.warning(
                "Binance WebSocket连接关闭",
                close_code=e.code,
                close_reason=e.reason
            )
            raise
        except Exception as e:
            self.logger.error(
                "Binance WebSocket连接失败",
                error=e,
                url=full_url
            )
            raise
        finally:
            # 清理消息处理器
            if self.message_processor_task and not self.message_processor_task.done():
                self.message_processor_task.cancel()
                try:
                    await self.message_processor_task
                except asyncio.CancelledError:
                    pass

    async def _subscribe_liquidation_data(self):
        """
        订阅Binance全市场强平数据

        注意：Binance通过URL直接订阅，不需要发送订阅消息
        """
        # Binance通过URL直接订阅，这里只是记录日志
        self.logger.info(
            "Binance全市场强平数据通过URL直接订阅",
            stream=self.all_market_stream,
            target_symbols=list(self.target_symbols)
        )

    async def _listen_messages(self):
        """监听WebSocket消息"""
        try:
            async for message in self.websocket:
                if not self.is_running:
                    break

                self.stats['total_received'] += 1

                try:
                    # 将消息放入队列异步处理
                    await self.message_queue.put(message)

                    # 定期输出统计信息
                    if self.stats['total_received'] % 100 == 0:
                        self.logger.info(
                            "全市场强平数据统计",
                            total_received=self.stats['total_received'],
                            target_symbols_data=self.stats['target_symbols_data'],
                            other_symbols_data=self.stats['other_symbols_data'],
                            filter_rate=f"{(self.stats['target_symbols_data'] / max(self.stats['total_received'], 1) * 100):.2f}%"
                        )
                    
                except Exception as e:
                    self.logger.error(
                        "处理WebSocket消息失败",
                        error=e,
                        message_preview=message[:200] if len(message) > 200 else message
                    )
                    self.stats['errors'] += 1
                    
        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("WebSocket连接已关闭")
            raise
        except Exception as e:
            self.logger.error(
                "监听WebSocket消息失败",
                error=e
            )
            raise

    async def _message_processor(self):
        """异步消息处理器"""
        while self.is_running:
            try:
                # 从队列获取消息（带超时）
                message = await asyncio.wait_for(
                    self.message_queue.get(),
                    timeout=1.0
                )
                
                await self._process_message(message)
                
            except asyncio.TimeoutError:
                # 超时是正常的，继续循环
                continue
            except Exception as e:
                self.logger.error(
                    "消息处理器异常",
                    error=e
                )
                self.stats['errors'] += 1

    async def _process_message(self, message: str):
        """处理单个WebSocket消息"""
        try:
            data = json.loads(message)

            # 处理全市场强平数据
            await self._process_all_market_liquidation(data)
                        
        except json.JSONDecodeError as e:
            self.logger.error(
                "JSON解析失败",
                error=e,
                message_preview=message[:200] if len(message) > 200 else message
            )
            self.stats['errors'] += 1
        except Exception as e:
            self.logger.error(
                "处理消息失败",
                error=e,
                message_preview=message[:200] if len(message) > 200 else message
            )
            self.stats['errors'] += 1



    async def _parse_liquidation_message(self, message: dict) -> Optional[NormalizedLiquidation]:
        """
        解析Binance强平消息并返回标准化数据

        注意：在全市场模式下，这个方法主要用于兼容基类接口
        实际的数据处理在_process_all_market_liquidation中进行

        Args:
            message: Binance WebSocket原始消息

        Returns:
            标准化的强平数据对象（全市场模式下可能返回None）
        """
        try:
            # 在全市场模式下，我们在_process_all_market_liquidation中处理数据
            # 这个方法主要用于兼容基类接口
            if 'data' in message and 'o' in message['data']:
                liquidation_data = message['data']['o']
                symbol = liquidation_data.get('s', '').upper()

                # 只处理目标交易对
                if symbol in self.target_symbols:
                    # 标准化器期望完整的消息格式，包含"o"字段
                    return self.normalizer.normalize_binance_liquidation(message['data'])

            return None

        except Exception as e:
            self.logger.error(
                "解析Binance强平消息失败",
                error=e,
                message_preview=str(message)[:200]
            )
            return None

    async def stop(self):
        """停止Binance强平管理器"""
        # 停止消息处理器
        if self.message_processor_task and not self.message_processor_task.done():
            self.message_processor_task.cancel()
            try:
                await self.message_processor_task
            except asyncio.CancelledError:
                pass

        # 调用父类停止方法
        await super().stop()

    async def _process_all_market_liquidation(self, data: dict):
        """处理全市场强平数据"""
        try:
            # Binance全市场强平数据格式：
            # {
            #   "stream": "!forceOrder@arr",
            #   "data": {
            #     "e": "forceOrder",
            #     "E": 1568014460893,
            #     "o": {
            #       "s": "BTCUSDT",
            #       "S": "SELL",
            #       "o": "LIMIT",
            #       "f": "IOC",
            #       "q": "0.014",
            #       "p": "9910",
            #       "ap": "9910",
            #       "X": "FILLED",
            #       "l": "0.014",
            #       "z": "0.014",
            #       "T": 1568014460893
            #     }
            #   }
            # }

            if 'data' not in data or 'o' not in data['data']:
                return

            liquidation_data = data['data']['o']
            symbol = liquidation_data.get('s', '').upper()

            # 统计所有接收到的数据
            if symbol in self.target_symbols:
                self.stats['target_symbols_data'] += 1
                # 处理目标交易对的数据
                await self._process_target_liquidation(liquidation_data)
            else:
                self.stats['other_symbols_data'] += 1
                # 记录其他交易对的数据（用于监控）
                if self.stats['other_symbols_data'] % 50 == 0:  # 每50条记录一次
                    self.logger.debug(
                        "接收到其他交易对强平数据",
                        symbol=symbol,
                        side=liquidation_data.get('S'),
                        quantity=liquidation_data.get('q'),
                        price=liquidation_data.get('p')
                    )

        except Exception as e:
            self.logger.error("处理全市场强平数据失败", error=e, data=data)

    async def _process_target_liquidation(self, liquidation_data: dict):
        """处理目标交易对的强平数据"""
        try:
            # 构造标准化器期望的格式（包含"o"字段）
            formatted_data = {"o": liquidation_data}
            # 标准化数据
            normalized_data = self.normalizer.normalize_binance_liquidation(formatted_data)

            if normalized_data:
                # 发布到NATS
                await self._publish_to_nats(normalized_data)

                self.logger.info(
                    "目标交易对强平数据处理完成",
                    symbol=normalized_data.symbol,
                    side=normalized_data.side,
                    quantity=str(normalized_data.quantity),
                    price=str(normalized_data.price),
                    timestamp=normalized_data.timestamp
                )

        except Exception as e:
            self.logger.error("处理目标强平数据失败", error=e, data=liquidation_data)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = max(self.stats['total_received'], 1)
        return {
            **self.stats,
            'filter_rate': f"{(self.stats['target_symbols_data'] / total * 100):.2f}%",
            'target_symbols': list(self.target_symbols),
            'mode': '全市场模式',
            'ws_url': self.ws_url,
            'stream': self.all_market_stream,
            'heartbeat_interval': self.heartbeat_interval,
            'message_queue_size': self.message_queue.qsize(),
            'last_successful_connection': self.last_successful_connection.isoformat() if self.last_successful_connection else None
        }
