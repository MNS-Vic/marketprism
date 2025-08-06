"""
BinanceDerivativesLiquidationManager - Binance衍生品强平订单数据管理器

基于Binance官方文档实现：
https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/websocket-market-streams/Liquidation-Order-Streams

WebSocket频道：<symbol>@forceOrder
数据格式：包含s(symbol), S(side), q(quantity), p(price), ap(average price), T(time)等字段
更新频率：1000ms内最多推送一条
"""

import asyncio
import json
import websockets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any

from .base_liquidation_manager import BaseLiquidationManager
from collector.data_types import Exchange, MarketType, NormalizedLiquidation


class BinanceDerivativesLiquidationManager(BaseLiquidationManager):
    """
    Binance衍生品强平订单数据管理器
    
    订阅Binance的<symbol>@forceOrder频道，处理永续合约强平数据
    """
    
    def __init__(self, symbols: List[str], normalizer, nats_publisher, config: dict):
        """
        初始化Binance衍生品强平管理器
        
        Args:
            symbols: 交易对列表（如 ['BTCUSDT', 'ETHUSDT']）
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
        
        # 构建订阅流名称
        self.stream_names = [f"{symbol.lower()}@forceOrder" for symbol in symbols]

        self.logger.startup(
            "Binance衍生品强平管理器初始化完成",
            symbols=symbols,
            ws_url=self.ws_url,
            stream_names=self.stream_names,
            heartbeat_interval=self.heartbeat_interval
        )

    async def _connect_and_listen(self):
        """连接Binance WebSocket并监听强平数据"""
        try:
            # 构建WebSocket URL（包含流名称）
            streams = "/".join(self.stream_names)
            full_url = f"{self.ws_url}/{streams}"
            
            self.logger.info(
                "连接Binance衍生品强平WebSocket",
                url=full_url,
                symbols=self.symbols
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
                    "Binance衍生品强平WebSocket连接成功",
                    url=full_url
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
        订阅Binance强平数据
        
        注意：Binance通过URL直接订阅，不需要发送订阅消息
        """
        # Binance通过URL直接订阅，这里只是记录日志
        self.logger.info(
            "Binance强平数据通过URL直接订阅",
            stream_names=self.stream_names,
            symbols=self.symbols
        )

    async def _listen_messages(self):
        """监听WebSocket消息"""
        try:
            async for message in self.websocket:
                if not self.is_running:
                    break
                    
                try:
                    # 将消息放入队列异步处理
                    await self.message_queue.put(message)
                    
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
            
            # 检查是否是强平数据
            if data.get('e') == 'forceOrder':
                normalized_liquidation = await self._parse_liquidation_message(data)
                if normalized_liquidation:
                    await self._process_liquidation_data(normalized_liquidation)
                        
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

    async def _parse_liquidation_message(self, raw_data: dict) -> Optional[NormalizedLiquidation]:
        """
        解析Binance强平消息并返回标准化数据

        使用现有的normalizer.normalize_binance_liquidation()方法进行标准化

        Args:
            raw_data: Binance WebSocket完整的原始数据

        Returns:
            标准化的强平数据对象
        """
        try:
            # 使用现有的Binance强平数据标准化方法
            normalized_liquidation = self.normalizer.normalize_binance_liquidation(raw_data)

            if normalized_liquidation:
                self.logger.debug(
                    "Binance强平数据解析成功",
                    symbol=normalized_liquidation.symbol_name,
                    side=normalized_liquidation.side.value,
                    quantity=str(normalized_liquidation.quantity),
                    price=str(normalized_liquidation.price)
                )
            else:
                self.logger.warning(
                    "Binance强平数据标准化失败",
                    raw_data_preview=str(raw_data)[:200]
                )

            return normalized_liquidation

        except Exception as e:
            self.logger.error(
                "解析Binance强平消息失败",
                error=e,
                raw_data_preview=str(raw_data)[:200]
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

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = super().get_stats()
        stats.update({
            'ws_url': self.ws_url,
            'stream_names': self.stream_names,
            'heartbeat_interval': self.heartbeat_interval,
            'message_queue_size': self.message_queue.qsize(),
            'last_successful_connection': self.last_successful_connection.isoformat() if self.last_successful_connection else None
        })
        return stats
