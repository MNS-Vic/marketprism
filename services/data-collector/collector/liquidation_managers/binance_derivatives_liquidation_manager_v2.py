"""
BinanceDerivativesLiquidationManager V2 - 全市场强平数据收集

重构要点：
1. 使用全市场强平流：!forceOrder@arr
2. 接收所有交易对的强平数据
3. 在接收端进行symbol过滤
4. 提高数据流的可观测性和可靠性

基于Binance官方文档：
https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/websocket-market-streams/All-Market-Liquidation-Order-Streams

WebSocket频道：!forceOrder@arr
数据格式：包含所有交易对的强平数据数组
更新频率：实时推送所有市场的强平事件
"""

import asyncio
import json
import websockets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any, Set

from .base_liquidation_manager import BaseLiquidationManager
from collector.data_types import Exchange, MarketType, NormalizedLiquidation
from exchanges.common.ws_message_utils import unwrap_combined_stream_message


class BinanceDerivativesLiquidationManagerV2(BaseLiquidationManager):
    """
    Binance衍生品强平订单数据管理器 V2 - 全市场模式
    
    订阅Binance的!forceOrder@arr频道，接收所有交易对的强平数据
    在接收端进行symbol过滤，只处理指定的交易对
    """
    
    def __init__(self, symbols: List[str], normalizer, nats_publisher, config: dict):
        """
        初始化Binance衍生品强平管理器V2
        
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
            "Binance衍生品强平管理器V2初始化完成",
            mode="全市场模式",
            target_symbols=list(self.target_symbols),
            stream=self.all_market_stream,
            ws_url=self.ws_url,
            heartbeat_interval=self.heartbeat_interval
        )

    async def _connect_and_listen(self):
        """连接Binance WebSocket并监听全市场强平数据"""
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
                
                # 监听消息
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

    async def _listen_messages(self):
        """监听WebSocket消息"""
        try:
            async for message in self.websocket:
                self.stats['total_received'] += 1
                
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
                
        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("WebSocket连接已关闭")
            raise
        except Exception as e:
            self.logger.error("监听消息时发生错误", error=e)
            raise

    async def _message_processor(self):
        """异步消息处理器"""
        while True:
            try:
                # 从队列获取消息
                message = await self.message_queue.get()
                
                # 解析消息
                try:
                    data = json.loads(message)
                except json.JSONDecodeError as e:
                    self.logger.warning("JSON解析失败", message=message[:100], error=e)
                    continue
                
                # 处理全市场强平数据
                await self._process_all_market_liquidation(data)
                
                # 标记任务完成
                self.message_queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("消息处理器错误", error=e)
                continue

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

            payload = unwrap_combined_stream_message(data)
            if not isinstance(payload, dict) or 'o' not in payload:
                return

            liquidation_data = payload['o']
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
            # 标准化数据
            normalized_data = self.normalizer.normalize_binance_liquidation(liquidation_data)
            
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

    def get_stats(self) -> dict:
        """获取统计信息"""
        total = max(self.stats['total_received'], 1)
        return {
            **self.stats,
            'filter_rate': f"{(self.stats['target_symbols_data'] / total * 100):.2f}%",
            'target_symbols': list(self.target_symbols),
            'mode': '全市场模式'
        }
