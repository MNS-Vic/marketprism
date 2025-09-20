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
# 异步任务安全封装（本地定义，避免跨模块依赖）
import asyncio as _aio

def _log_task_exception(task: _aio.Task, name: str, logger) -> None:
    try:
        if task.cancelled():
            return
        exc = task.exception()
    except Exception as _e:
        try:
            logger.error("任务异常检查失败", task=name, error=str(_e))
        except Exception:
            pass
        return
    if exc:
        try:
            logger.error("后台任务异常未捕获", task=name, error=str(exc), exc_info=True)
        except Exception:
            pass

def _create_logged_task(coro, name: str, logger) -> _aio.Task:
    t = _aio.create_task(coro)
    try:
        t.add_done_callback(lambda task: _log_task_exception(task, name, logger))
    except Exception:
        pass
    return t


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

        # 🔧 新增：Symbol 筛选配置
        self.symbol_filter_config = config.get('symbol_filter', {})
        self.target_symbols = set()
        self.all_symbol_mode = False

        # 解析 symbol 筛选配置
        if symbols and len(symbols) > 0:
            # 有指定 symbols，使用筛选模式
            self.target_symbols = set(symbols)
            self.all_symbol_mode = False
        else:
            # 没有指定 symbols，使用 all-symbol 聚合模式
            self.all_symbol_mode = True

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
            all_symbol_mode=self.all_symbol_mode,
            target_symbols=list(self.target_symbols) if not self.all_symbol_mode else "all",
            config_keys=list(config.keys())
        )
        # 事件计数（心跳窗口）
        self._hb_window_events = 0
        self._hb_task = None


    @property
    def is_connected(self) -> bool:
        """检查WebSocket连接状态 (兼容 websockets 12)
        websockets 12 的连接对象为 ClientConnection，
        使用 .closed 属性不可用，改为 .close_code 判定是否已关闭。
        """
        if self.websocket is None:
            return False
        # 优先使用 close_code 判定；为 None 表示未关闭
        try:
            return getattr(self.websocket, 'close_code', None) is None
        except Exception:
            # 回退：若有 closed 属性则使用
            return not getattr(self.websocket, 'closed', True)

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
            self.websocket_task = _create_logged_task(self._websocket_connection_loop(), name=f"liquidation_ws:{self.exchange.value}", logger=self.logger)

            # 启动心跳任务（30s）
            async def _heartbeat():
                while self.is_running:
                    try:
                        self.logger.info(
                            "liquidation 心跳",
                            exchange=self.exchange.value,
                            market_type=self.market_type.value,
                            is_connected=self.is_connected,
                            window_events=self._hb_window_events,
                            total_received=self.stats['liquidations_received'],
                            published=self.stats['liquidations_published'],
                            reconnections=self.stats['reconnections']
                        )
                        self._hb_window_events = 0
                        await asyncio.sleep(self.connection_config.get('heartbeat_interval', 30))
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        self.logger.warning("liquidation 心跳异常", error=str(e))
                        await asyncio.sleep(5)
            self._hb_task = _create_logged_task(_heartbeat(), name=f"liquidation_hb:{self.exchange.value}", logger=self.logger)

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
            if self.websocket:
                try:
                    await self.websocket.close()
                except Exception:
                    pass

            # 取消心跳任务
            if self._hb_task and not self._hb_task.done():
                self._hb_task.cancel()
                try:
                    await self._hb_task
                except asyncio.CancelledError:
                    pass

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

    def _should_process_symbol(self, symbol: str) -> bool:
        """
        判断是否应该处理该 symbol 的强平数据

        Args:
            symbol: 交易对名称

        Returns:
            bool: 是否应该处理
        """
        if self.all_symbol_mode:
            # all-symbol 模式，处理所有 symbol
            return True

        # 筛选模式，检查是否在目标列表中
        # 支持多种格式匹配（如 BTC-USDT 匹配 BTCUSDT）
        normalized_symbol = symbol.replace('-', '').replace('_', '').upper()

        for target in self.target_symbols:
            normalized_target = target.replace('-', '').replace('_', '').upper()
            if normalized_symbol == normalized_target:
                return True

            # 也检查原始格式
            if symbol == target:
                return True

        return False

    async def _process_liquidation_data(self, normalized_liquidation: NormalizedLiquidation):
        """处理标准化的强平数据"""
        try:
            self.stats['liquidations_received'] += 1
            self._hb_window_events += 1
            self.stats['last_liquidation_time'] = datetime.now(timezone.utc)

            # 验证数据
            if not normalized_liquidation:
                self.stats['data_validation_errors'] += 1
                return

            # 🔧 新增：Symbol 筛选检查
            if not self._should_process_symbol(normalized_liquidation.symbol_name):
                self.logger.debug(
                    "强平数据被筛选跳过",
                    symbol=normalized_liquidation.symbol_name,
                    target_symbols=list(self.target_symbols) if not self.all_symbol_mode else "all",
                    aggregation_mode='all-symbol' if self.all_symbol_mode else 'filtered'
                )
                self.stats['liquidations_filtered'] = self.stats.get('liquidations_filtered', 0) + 1
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
                price=str(normalized_liquidation.price),
                aggregation_mode='all-symbol' if self.all_symbol_mode else 'filtered'
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
            # 🔧 新增：根据模式构建NATS主题
            if self.all_symbol_mode:
                # all-symbol 聚合模式
                symbol_part = "all-symbol"
            else:
                # 特定 symbol 模式
                symbol_part = normalized_liquidation.symbol_name

            topic = f"liquidation.{normalized_liquidation.exchange_name}.{normalized_liquidation.product_type.value}.{symbol_part}"

            # 转换为字典格式用于NATS发布（不在Manager层做时间/数值字符串格式化）
            data_dict = {
                'exchange': normalized_liquidation.exchange_name,
                'market_type': normalized_liquidation.product_type.value,
                'symbol': normalized_liquidation.symbol_name,
                'instrument_id': normalized_liquidation.instrument_id,
                'liquidation_id': normalized_liquidation.liquidation_id,
                'side': normalized_liquidation.side.value,
                'status': normalized_liquidation.status.value,
                'price': normalized_liquidation.price,
                'quantity': normalized_liquidation.quantity,
                'filled_quantity': normalized_liquidation.filled_quantity,
                'notional_value': normalized_liquidation.notional_value,
                'liquidation_time': normalized_liquidation.liquidation_time,
                'timestamp': normalized_liquidation.timestamp,
                'collected_at': normalized_liquidation.collected_at,
                'data_type': 'liquidation',
                'aggregation_mode': 'all-symbol' if self.all_symbol_mode else 'filtered'
            }

            # 添加可选字段
            if normalized_liquidation.average_price is not None:
                data_dict['average_price'] = str(normalized_liquidation.average_price)
            if normalized_liquidation.margin_ratio is not None:
                data_dict['margin_ratio'] = str(normalized_liquidation.margin_ratio)
            if normalized_liquidation.bankruptcy_price is not None:
                data_dict['bankruptcy_price'] = str(normalized_liquidation.bankruptcy_price)

            # 发布到NATS（统一 publish_liquidation 方法 + 统一模板）
            success = await self.nats_publisher.publish_liquidation(
                exchange=normalized_liquidation.exchange_name,
                market_type=normalized_liquidation.product_type.value,
                symbol=normalized_liquidation.symbol_name,
                liquidation_data=data_dict
            )

            if success:
                self.logger.debug("NATS发布成功",
                                symbol=normalized_liquidation.symbol_name,
                                final_subject=topic)
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
