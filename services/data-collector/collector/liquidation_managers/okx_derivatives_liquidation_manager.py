"""
OKXDerivativesLiquidationManager - OKX衍生品强平订单数据管理器

基于OKX官方文档实现：
https://www.okx.com/docs-v5/zh/#public-data-websocket-liquidation-orders-channel

WebSocket频道：liquidation-orders
数据格式：包含instId, side, sz, bkPx, bkLoss, cTime等字段
"""

import asyncio
import json
import websockets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any

from .base_liquidation_manager import BaseLiquidationManager
from collector.data_types import Exchange, MarketType, NormalizedLiquidation


class OKXDerivativesLiquidationManager(BaseLiquidationManager):
    """
    OKX衍生品强平订单数据管理器
    
    订阅OKX的liquidation-orders频道，处理永续合约强平数据
    """
    
    def __init__(self, symbols: List[str], normalizer, nats_publisher, config: dict):
        """
        初始化OKX衍生品强平管理器
        
        Args:
            symbols: 交易对列表（如 ['BTC-USDT-SWAP', 'ETH-USDT-SWAP']）
            normalizer: 数据标准化器
            nats_publisher: NATS发布器
            config: 配置信息
        """
        super().__init__(
            exchange=Exchange.OKX_DERIVATIVES,
            market_type=MarketType.PERPETUAL,
            symbols=symbols,
            normalizer=normalizer,
            nats_publisher=nats_publisher,
            config=config
        )

        # OKX WebSocket配置
        self.ws_url = config.get('ws_url', "wss://ws.okx.com:8443/ws/v5/public")
        
        # OKX特定配置
        self.heartbeat_interval = config.get('heartbeat_interval', 25)  # OKX推荐25秒
        self.connection_timeout = config.get('connection_timeout', 10)
        
        # 消息处理配置
        self.message_queue = asyncio.Queue()
        self.message_processor_task = None

        self.logger.startup(
            "OKX衍生品强平管理器初始化完成",
            symbols=symbols,
            ws_url=self.ws_url,
            heartbeat_interval=self.heartbeat_interval
        )

    async def _connect_and_listen(self):
        """连接OKX WebSocket并监听强平数据"""
        try:
            self.logger.info(
                "连接OKX衍生品强平WebSocket",
                url=self.ws_url,
                symbols=self.symbols
            )
            
            async with websockets.connect(
                self.ws_url,
                timeout=self.connection_timeout,
                ping_interval=self.heartbeat_interval,
                ping_timeout=60
            ) as websocket:
                self.websocket = websocket
                self.last_successful_connection = datetime.now(timezone.utc)
                self.reconnect_attempts = 0  # 重置重连计数
                
                self.logger.info(
                    "OKX衍生品强平WebSocket连接成功",
                    url=self.ws_url
                )
                
                # 启动消息处理器
                self.message_processor_task = asyncio.create_task(self._message_processor())
                
                # 订阅强平数据
                await self._subscribe_liquidation_data()
                
                # 监听消息
                await self._listen_messages()
                
        except websockets.exceptions.ConnectionClosed as e:
            self.logger.warning(
                "OKX WebSocket连接关闭",
                close_code=e.code,
                close_reason=e.reason
            )
            raise
        except Exception as e:
            self.logger.error(
                "OKX WebSocket连接失败",
                error=e,
                url=self.ws_url
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
        """订阅OKX强平数据"""
        try:
            # 构建订阅消息
            subscribe_message = {
                "op": "subscribe",
                "args": [
                    {
                        "channel": "liquidation-orders",
                        "instType": "SWAP"  # 永续合约
                    }
                ]
            }
            
            await self.websocket.send(json.dumps(subscribe_message))
            
            self.logger.info(
                "已订阅OKX强平数据频道",
                channel="liquidation-orders",
                inst_type="SWAP",
                symbols=self.symbols
            )
            
        except Exception as e:
            self.logger.error(
                "订阅OKX强平数据失败",
                error=e
            )
            raise

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
            
            # 检查是否是订阅确认消息
            if data.get('event') == 'subscribe':
                self.logger.info(
                    "OKX强平数据订阅确认",
                    channel=data.get('arg', {}).get('channel'),
                    inst_type=data.get('arg', {}).get('instType')
                )
                return
            
            # 检查是否是错误消息
            if data.get('event') == 'error':
                self.logger.error(
                    "OKX WebSocket错误",
                    error_code=data.get('code'),
                    error_msg=data.get('msg')
                )
                return
            
            # 处理强平数据
            if 'data' in data and data.get('arg', {}).get('channel') == 'liquidation-orders':
                # 遍历所有强平数据项
                for liquidation_item in data['data']:
                    # 检查是否是我们关注的交易对
                    inst_id = liquidation_item.get('instId', '')
                    if inst_id in self.symbols:
                        # 只处理BTC-USDT-SWAP和ETH-USDT-SWAP
                        # 实际的OKX强平数据格式：liquidation_item包含instId和details数组
                        # 但从错误日志看，数据可能已经是扁平格式
                        normalized_liquidation = await self._parse_liquidation_message(liquidation_item)
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

    async def _parse_liquidation_message(self, liquidation_item: dict) -> Optional[NormalizedLiquidation]:
        """
        解析OKX强平消息并返回标准化数据

        实际OKX强平数据格式有两种可能：
        1. 嵌套格式：{"instId": "BTC-USDT-SWAP", "details": [{"side": "buy", ...}]}
        2. 扁平格式：{"instId": "BTC-USDT-SWAP", "side": "buy", "sz": "0.1", ...}

        Args:
            liquidation_item: OKX单个强平数据项

        Returns:
            标准化的强平数据对象
        """
        try:
            # 获取交易对ID
            inst_id = liquidation_item.get('instId', '')
            if not inst_id:
                self.logger.warning("OKX强平数据缺少instId字段", data=liquidation_item)
                return None

            # 检查数据格式：嵌套格式还是扁平格式
            if 'details' in liquidation_item:
                # 嵌套格式：从details数组中获取数据
                details = liquidation_item.get('details', [])
                if not details:
                    self.logger.warning("OKX强平数据details为空", inst_id=inst_id)
                    return None
                detail = details[0]  # 处理第一个详情
            else:
                # 扁平格式：直接使用liquidation_item作为detail
                detail = liquidation_item

            # 构建符合现有标准化方法期望的数据格式
            formatted_data = {
                "data": [{
                    "instId": inst_id,
                    "instType": "SWAP",
                    "side": detail.get("side", ""),
                    "sz": detail.get("sz", "0"),
                    "bkPx": detail.get("bkPx", "0"),
                    "bkLoss": detail.get("bkLoss", "0"),
                    "ts": detail.get("ts", "0"),
                    "state": "filled",  # OKX强平订单通常是已成交状态
                    "fillSz": detail.get("sz", "0"),  # 强平通常全部成交
                    "fillPx": detail.get("bkPx", "0")  # 使用破产价格作为成交价格
                }]
            }

            # 使用现有的OKX强平数据标准化方法
            normalized_liquidation = self.normalizer.normalize_okx_liquidation(formatted_data)

            if normalized_liquidation:
                self.logger.debug(
                    "OKX强平数据解析成功",
                    symbol=normalized_liquidation.symbol_name,
                    side=normalized_liquidation.side.value,
                    quantity=str(normalized_liquidation.quantity),
                    price=str(normalized_liquidation.price)
                )
            else:
                self.logger.warning(
                    "OKX强平数据标准化失败",
                    inst_id=inst_id,
                    detail_preview=str(detail)[:200]
                )

            return normalized_liquidation

        except Exception as e:
            self.logger.error(
                "解析OKX强平消息失败",
                error=e,
                liquidation_item_preview=str(liquidation_item)[:200]
            )
            return None

    async def stop(self):
        """停止OKX强平管理器"""
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
            'heartbeat_interval': self.heartbeat_interval,
            'message_queue_size': self.message_queue.qsize(),
            'last_successful_connection': self.last_successful_connection.isoformat() if self.last_successful_connection else None
        })
        return stats
