"""
BaseTradesManager - 逐笔成交数据管理器基类
借鉴OrderBook Manager的成功架构模式
"""

import asyncio
from abc import ABC, abstractmethod

# 🔧 迁移到统一日志系统
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from core.observability.logging import (
    get_managed_logger,
    ComponentType
)
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal

from collector.data_types import Exchange, MarketType, DataType
from collector.normalizer import DataNormalizer
from collector.nats_publisher import NATSPublisher
from collector.log_sampler import should_log_data_processing
from exchanges.policies.ws_policy_adapter import WSPolicyContext


class TradeData:
    """统一的成交数据格式"""
    def __init__(self,
                 symbol: str,
                 price: Decimal,
                 quantity: Decimal,
                 timestamp: datetime,
                 side: str,  # 'buy' or 'sell'
                 trade_id: str,
                 exchange: str,
                 market_type: str):
        self.symbol = symbol
        self.price = price
        self.quantity = quantity
        self.timestamp = timestamp
        self.side = side
        self.trade_id = trade_id
        self.exchange = exchange
        self.market_type = market_type

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'symbol': self.symbol,
            'price': str(self.price),
            'quantity': str(self.quantity),
            'timestamp': self.timestamp.isoformat(),
            'side': self.side,
            'trade_id': self.trade_id,
            'exchange': self.exchange,
            'market_type': self.market_type
        }


class BaseTradesManager(ABC):
    """
    逐笔成交数据管理器基类
    借鉴OrderBook Manager的成功架构模式
    """

    def __init__(self,
                 exchange: Exchange,
                 market_type: MarketType,
                 symbols: List[str],
                 normalizer: DataNormalizer,
                 nats_publisher: NATSPublisher,
                 config: dict):
        self.exchange = exchange
        self.market_type = market_type
        self.symbols = symbols
        self.normalizer = normalizer
        self.nats_publisher = nats_publisher
        self.config = config

        # 🔧 迁移到统一日志系统
        self.logger = get_managed_logger(
            ComponentType.TRADES_MANAGER,
            exchange=exchange.value.lower(),
            market_type=market_type.value.lower()
        )

        # 统计信息
        self.stats = {
            'trades_received': 0,
            'trades_processed': 0,
            'trades_published': 0,
            'errors': 0,
            'last_trade_time': None,
            'connection_errors': 0,
            'reconnections': 0
        }

        # 去重与回放控制：按symbol维护最后已发布成交
        self._last_trade_ts: Dict[str, datetime] = {}
        self._last_trade_id: Dict[str, str] = {}

        # 运行状态
        self.is_running = False
        self.websocket_task: Optional[asyncio.Task] = None

        # 统一WebSocket策略上下文（供子类选择使用）
        try:
            self._ws_ctx = WSPolicyContext(exchange.value.lower(), self.logger, config)
        except Exception:
            self._ws_ctx = None

        # 错误处理配置
        self.max_reconnect_attempts = config.get('max_reconnect_attempts', 5)
        self.reconnect_delay = config.get('reconnect_delay', 5)
        self.max_consecutive_errors = config.get('max_consecutive_errors', 10)

        self.logger.info(f"🏭 {self.__class__.__name__}初始化完成",
                        exchange=exchange.value,
                        market_type=market_type.value,
                        symbols=symbols)

    @abstractmethod
    async def start(self) -> bool:
        """启动成交数据管理器"""
        pass

    @abstractmethod
    async def stop(self):
        """停止成交数据管理器"""
        pass

    @abstractmethod
    async def _connect_websocket(self):
        """连接WebSocket"""
        pass

    @abstractmethod
    async def _process_trade_message(self, message: Dict[str, Any]):
        """处理成交消息"""
        pass

    def _should_publish_trade(self, trade: TradeData) -> bool:
        """
        统一的成交发布判定：
        - 初次连接时丢弃“过旧”的初始回放（ts < now-2s）
        - 去重：相同 trade_id 不重复发布
        - 单调：时间戳不回退（ts <= last_ts 跳过）
        """
        try:
            sym = trade.symbol
            ts = trade.timestamp
            tid = trade.trade_id or ""
            now_utc = datetime.now(timezone.utc)

            # 初次基线：仅接受最近2秒内的成交，避免订阅后的历史回放冲击
            if sym not in self._last_trade_ts:
                if ts < now_utc - timedelta(seconds=2):
                    self.logger.debug(
                        "丢弃初次回放的过旧成交", symbol=sym, trade_id=tid,
                        trade_ts=str(ts), now=str(now_utc)
                    )
                    return False

            # 去重：相同trade_id跳过
            if tid and self._last_trade_id.get(sym) == tid:
                return False

            # 单调：时间戳不回退
            last_ts = self._last_trade_ts.get(sym)
            if last_ts and ts <= last_ts:
                return False

            return True
        except Exception:
            # 防御性：异常时不阻断发布
            return True

    async def _on_reconnected(self) -> None:
        """
        重连成功后的统一回调钩子（可由子类重写）。
        用于执行重订阅(replay)或交易所特定的会话恢复逻辑。
        默认不执行操作。
        """
        return

    async def _publish_trade(self, trade_data: TradeData):
        """
        发布成交数据到NATS - 与OrderBook管理器保持一致的推送方式
        """
        try:
            # 发布前过滤：丢弃过旧/重复/时间回退的成交，抑制订阅初期回放造成的延迟告警
            if not self._should_publish_trade(trade_data):
                self.logger.debug(
                    "跳过过旧/重复成交",
                    symbol=trade_data.symbol,
                    trade_id=trade_data.trade_id,
                    trade_ts=str(trade_data.timestamp)
                )
                return

            # 🔧 修复：标准化symbol格式 (BTCUSDT -> BTC-USDT)
            normalized_symbol = self.normalizer.normalize_symbol_format(
                trade_data.symbol, self.exchange.value
            ) if self.normalizer else trade_data.symbol

            # 使用标准化器处理数据
            if self.normalizer:
                # 构建原始数据格式供标准化器处理
                raw_data = {
                #  
                #  

                    'symbol': trade_data.symbol,
                    'price': str(trade_data.price),
                    'quantity': str(trade_data.quantity),
                    'timestamp': trade_data.timestamp.isoformat(),
                    'side': trade_data.side,
                    'trade_id': trade_data.trade_id,
                    'exchange': self.exchange.value,
                    'market_type': self.market_type.value
                }

                # 使用标准化器处理
                normalized_data = self.normalizer.normalize_trade_data(
                    raw_data, self.exchange, self.market_type
                )

                # 确保标准化数据包含正确的symbol格式
                normalized_data['normalized_symbol'] = normalized_symbol

                # 兜底：确保 trade_time 字段存在且有有效值
                if 'trade_time' not in normalized_data or not normalized_data.get('trade_time'):
                    normalized_data['trade_time'] = normalized_data.get('timestamp')
            else:
                # 如果没有标准化器，使用原始数据
                ts_iso = trade_data.timestamp.isoformat()
                normalized_data = {
                    'symbol': trade_data.symbol,
                    'normalized_symbol': normalized_symbol,
                    'price': str(trade_data.price),
                    'quantity': str(trade_data.quantity),
                    'timestamp': ts_iso,
                    'trade_time': ts_iso,  # 补齐 trade_time 字段
                    'side': trade_data.side,
                    'trade_id': trade_data.trade_id,
                    'exchange': self.exchange.value,
                    'market_type': self.market_type.value,
                    'data_type': 'trade'
                }

            # 使用标准化后的symbol发布到NATS（移除误导性错误级调试日志）
            if self.exchange.value == 'binance_spot':
                self.logger.debug("publish_attempt",
                                  subject=f"trade.{self.exchange.value}.{self.market_type.value}.{normalized_symbol}",
                                  symbol=normalized_symbol)
            success = await self.nats_publisher.publish_data(
                data_type='trade',
                exchange=self.exchange.value,
                market_type=self.market_type.value,
                symbol=normalized_symbol,  # 使用标准化后的symbol
                data=normalized_data
            )
            if success:
                self.stats['trades_published'] += 1

                # 更新去重/基线
                sym_key = trade_data.symbol
                self._last_trade_ts[sym_key] = trade_data.timestamp
                if trade_data.trade_id:
                    self._last_trade_id[sym_key] = trade_data.trade_id

                # 抽样日志判定
                should_log = should_log_data_processing(
                    data_type="trade",
                    exchange=self.exchange.value,
                    market_type=self.market_type.value,
                    symbol=normalized_symbol,
                    is_error=False
                )

                if should_log:
                    # 抽样记录成功日志
                    self.logger.data_processed(
                        "Trade data published successfully",
                        symbol=trade_data.symbol,
                        normalized_symbol=normalized_symbol,
                        price=trade_data.price,
                        side=trade_data.side,
                        operation="trade_publish",
                        stats=f"published={self.stats['trades_published']}"
                    )
            else:
                # 🔧 失败日志总是记录（不抽样）
                self.logger.warning(
                    "Trade data publish failed",
                    symbol=trade_data.symbol,
                    normalized_symbol=normalized_symbol,
                    operation="trade_publish"
                )

        except Exception as e:
            self.stats['errors'] += 1
            # 🔧 迁移到统一日志系统 - 标准化错误处理
            self.logger.error(
                "Trade data publish exception",
                error=e,
                symbol=trade_data.symbol,
                operation="trade_publish"
            )

    async def _handle_error(self, symbol: str, operation: str, error: str):
        """统一的错误处理方法"""
        self.stats['errors'] += 1
        # 🔧 迁移到统一日志系统 - 标准化错误处理
        self.logger.error(
            f"{operation} failed",
            error=Exception(error),
            symbol=symbol,
            operation=operation.lower().replace(' ', '_')
        )

        # 如果错误过多，可以考虑重启连接
        if self.stats['errors'] > self.max_consecutive_errors:
            # 🔧 迁移到统一日志系统 - 标准化警告
            self.logger.warning(
                "Too many consecutive errors, considering connection restart",
                error_count=self.stats['errors'],
                max_errors=self.max_consecutive_errors
            )
            self.stats['connection_errors'] += 1

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.stats.copy()

    async def _handle_error(self, symbol: str, error_type: str, error_msg: str):
        """统一错误处理"""
        self.stats['errors'] += 1
        # 🔧 迁移到统一日志系统 - 标准化错误处理
        self.logger.error(
            f"{error_type} error occurred",
            error=Exception(error_msg),
            symbol=symbol,
            error_type=error_type
        )

    async def _on_successful_operation(self, symbol: str, operation: str):
        """成功操作回调"""
        self.logger.debug(f"✅ {symbol} {operation}成功")
