"""
BaseLiquidationManager - 强平订单数据管理器基类

基于现有trades_managers的成功架构模式，提供统一的强平数据处理框架。
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

# 🔧 统一日志系统集成
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from core.observability.logging import (
    get_managed_logger,
    ComponentType
)

from collector.data_types import Exchange, MarketType, DataType, NormalizedLiquidation
from collector.normalizer import DataNormalizer
from collector.nats_publisher import NATSPublisher


class BaseLiquidationManager(ABC):
    """
    强平订单数据管理器基类
    
    基于现有trades_managers的成功架构模式，提供统一的强平数据处理框架。
    包含WebSocket连接管理、数据标准化、NATS发布等核心功能。
    """
    
    def __init__(self,
                 exchange: Exchange,
                 market_type: MarketType,
                 symbols: List[str],
                 normalizer: DataNormalizer,
                 nats_publisher: NATSPublisher,
                 config: dict):
        """
        初始化强平数据管理器
        
        Args:
            exchange: 交易所枚举
            market_type: 市场类型枚举
            symbols: 交易对列表
            normalizer: 数据标准化器
            nats_publisher: NATS发布器
            config: 配置信息
        """
        self.exchange = exchange
        self.market_type = market_type
        self.symbols = symbols
        self.normalizer = normalizer
        self.nats_publisher = nats_publisher
        self.config = config

        # 🔧 统一日志系统集成
        self.logger = get_managed_logger(
            ComponentType.LIQUIDATION_MANAGER,
            exchange=exchange.value.lower(),
            market_type=market_type.value.lower()
        )

        # 统计信息
        self.stats = {
            'liquidations_received': 0,
            'liquidations_processed': 0,
            'liquidations_published': 0,
            'errors': 0,
            'last_liquidation_time': None,
            'connection_errors': 0,
            'reconnections': 0,
            'data_validation_errors': 0,
            'nats_publish_errors': 0
        }

        # 运行状态
        self.is_running = False
        self.websocket_task = None
        self.websocket = None

        # WebSocket连接配置
        self.connection_config = {
            'timeout': config.get('connection_timeout', 10),
            'heartbeat_interval': config.get('heartbeat_interval', 30),
            'max_reconnect_attempts': config.get('max_reconnect_attempts', -1),
            'reconnect_delay': config.get('reconnect_delay', 1.0),
            'max_reconnect_delay': config.get('max_reconnect_delay', 30.0),
            'backoff_multiplier': config.get('backoff_multiplier', 2.0)
        }

        # 重连状态
        self.reconnect_attempts = 0
        self.is_reconnecting = False
        self.last_successful_connection = None

        self.logger.startup(
            "强平数据管理器初始化完成",
            exchange=exchange.value,
            market_type=market_type.value,
            symbols=symbols,
            config_keys=list(config.keys())
        )

    @property
    def is_connected(self) -> bool:
        """检查WebSocket连接状态"""
        return self.websocket is not None and not self.websocket.closed

    async def start(self) -> bool:
        """
        启动强平数据管理器
        
        Returns:
            bool: 启动是否成功
        """
        try:
            self.logger.startup(
                "启动强平数据管理器",
                exchange=self.exchange.value,
                market_type=self.market_type.value
            )
            
            if self.is_running:
                self.logger.warning("强平数据管理器已在运行中")
                return True
            
            self.is_running = True
            
            # 启动WebSocket连接任务
            self.websocket_task = asyncio.create_task(self._websocket_connection_loop())
            
            self.logger.startup(
                "强平数据管理器启动成功",
                exchange=self.exchange.value,
                market_type=self.market_type.value
            )
            return True
            
        except Exception as e:
            self.logger.error(
                "强平数据管理器启动失败",
                error=e,
                exchange=self.exchange.value,
                market_type=self.market_type.value
            )
            self.stats['errors'] += 1
            return False

    async def stop(self):
        """停止强平数据管理器"""
        try:
            self.logger.info(
                "停止强平数据管理器",
                exchange=self.exchange.value,
                market_type=self.market_type.value
            )
            
            self.is_running = False
            
            # 关闭WebSocket连接
            if self.websocket and not self.websocket.closed:
                await self.websocket.close()
                
            # 取消WebSocket任务
            if self.websocket_task and not self.websocket_task.done():
                self.websocket_task.cancel()
                try:
                    await self.websocket_task
                except asyncio.CancelledError:
                    pass
                    
            self.logger.info(
                "强平数据管理器已停止",
                exchange=self.exchange.value,
                market_type=self.market_type.value,
                final_stats=self.stats
            )
            
        except Exception as e:
            self.logger.error(
                "停止强平数据管理器失败",
                error=e,
                exchange=self.exchange.value,
                market_type=self.market_type.value
            )

    async def _websocket_connection_loop(self):
        """WebSocket连接循环，包含重连逻辑"""
        while self.is_running:
            try:
                await self._connect_and_listen()
            except Exception as e:
                self.logger.error(
                    "WebSocket连接异常",
                    error=e,
                    exchange=self.exchange.value,
                    reconnect_attempts=self.reconnect_attempts
                )
                self.stats['connection_errors'] += 1
                
                if self.is_running:
                    await self._handle_reconnection()

    async def _handle_reconnection(self):
        """处理重连逻辑"""
        if not self.is_running:
            return
            
        self.is_reconnecting = True
        self.reconnect_attempts += 1
        self.stats['reconnections'] += 1
        
        # 计算重连延迟（指数退避）
        delay = min(
            self.connection_config['reconnect_delay'] * 
            (self.connection_config['backoff_multiplier'] ** (self.reconnect_attempts - 1)),
            self.connection_config['max_reconnect_delay']
        )
        
        self.logger.warning(
            "准备重连WebSocket",
            exchange=self.exchange.value,
            reconnect_attempts=self.reconnect_attempts,
            delay_seconds=delay
        )
        
        await asyncio.sleep(delay)
        self.is_reconnecting = False

    @abstractmethod
    async def _connect_and_listen(self):
        """连接WebSocket并监听消息（子类实现）"""
        pass

    @abstractmethod
    async def _subscribe_liquidation_data(self):
        """订阅强平数据（子类实现）"""
        pass

    @abstractmethod
    async def _parse_liquidation_message(self, message: dict) -> Optional[NormalizedLiquidation]:
        """解析强平消息并返回标准化数据（子类实现）"""
        pass

    async def _process_liquidation_data(self, normalized_liquidation: NormalizedLiquidation):
        """处理标准化的强平数据"""
        try:
            self.stats['liquidations_received'] += 1
            self.stats['last_liquidation_time'] = datetime.now(timezone.utc)

            # 验证数据
            if not normalized_liquidation:
                self.stats['data_validation_errors'] += 1
                return

            self.stats['liquidations_processed'] += 1

            # 发布到NATS
            await self._publish_to_nats(normalized_liquidation)
            self.stats['liquidations_published'] += 1

            self.logger.data_processed(
                "强平数据处理完成",
                exchange=normalized_liquidation.exchange_name,
                symbol=normalized_liquidation.symbol_name,
                side=normalized_liquidation.side.value,
                quantity=str(normalized_liquidation.quantity),
                price=str(normalized_liquidation.price)
            )

        except Exception as e:
            self.logger.error(
                "处理强平数据失败",
                error=e,
                liquidation_data=str(normalized_liquidation)
            )
            self.stats['errors'] += 1

    async def _publish_to_nats(self, normalized_liquidation: NormalizedLiquidation):
        """发布标准化强平数据到NATS"""
        try:
            # 构建NATS主题
            topic = f"liquidation-data.{normalized_liquidation.exchange_name}.{normalized_liquidation.product_type.value}.{normalized_liquidation.symbol_name}"

            # 转换为字典格式用于NATS发布
            data_dict = {
                'exchange': normalized_liquidation.exchange_name,
                'symbol': normalized_liquidation.symbol_name,
                'product_type': normalized_liquidation.product_type.value,
                'instrument_id': normalized_liquidation.instrument_id,
                'liquidation_id': normalized_liquidation.liquidation_id,
                'side': normalized_liquidation.side.value,
                'status': normalized_liquidation.status.value,
                'price': str(normalized_liquidation.price),
                'quantity': str(normalized_liquidation.quantity),
                'filled_quantity': str(normalized_liquidation.filled_quantity),
                'notional_value': str(normalized_liquidation.notional_value),
                'liquidation_time': normalized_liquidation.liquidation_time.isoformat(),
                'timestamp': normalized_liquidation.timestamp.isoformat(),
                'collected_at': normalized_liquidation.collected_at.isoformat(),
                'data_type': 'liquidation'
            }

            # 添加可选字段
            if normalized_liquidation.average_price is not None:
                data_dict['average_price'] = str(normalized_liquidation.average_price)
            if normalized_liquidation.margin_ratio is not None:
                data_dict['margin_ratio'] = str(normalized_liquidation.margin_ratio)
            if normalized_liquidation.bankruptcy_price is not None:
                data_dict['bankruptcy_price'] = str(normalized_liquidation.bankruptcy_price)

            # 发布到NATS
            success = await self.nats_publisher.publish_data(
                data_type="liquidation",
                exchange=normalized_liquidation.exchange_name,
                market_type=normalized_liquidation.product_type.value,
                symbol=normalized_liquidation.symbol_name,
                data=data_dict
            )

            if success:
                self.logger.debug("NATS发布成功",
                                symbol=normalized_liquidation.symbol_name,
                                topic=topic)
            else:
                self.logger.warning("NATS发布失败",
                                  symbol=normalized_liquidation.symbol_name,
                                  topic=topic)

        except Exception as e:
            self.logger.error(
                "NATS发布失败",
                error=e,
                topic=topic if 'topic' in locals() else 'unknown',
                exchange=normalized_liquidation.exchange_name,
                symbol=normalized_liquidation.symbol_name
            )
            self.stats['nats_publish_errors'] += 1
            raise

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            'is_running': self.is_running,
            'is_connected': self.is_connected,
            'reconnect_attempts': self.reconnect_attempts,
            'is_reconnecting': self.is_reconnecting,
            'symbols_count': len(self.symbols),
            'exchange': self.exchange.value,
            'market_type': self.market_type.value
        }
