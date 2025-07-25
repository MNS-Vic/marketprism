"""
BaseTradesManager - 逐笔成交数据管理器基类
借鉴OrderBook Manager的成功架构模式
"""

import asyncio
import structlog
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from decimal import Decimal

from collector.data_types import Exchange, MarketType, DataType
from collector.normalizer import DataNormalizer
from collector.nats_publisher import NATSPublisher


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

        # 日志器
        self.logger = structlog.get_logger(f"{exchange.value}_{market_type.value}_trades")

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

        # 运行状态
        self.is_running = False
        self.websocket_task: Optional[asyncio.Task] = None

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

    async def _publish_trade(self, trade_data: TradeData):
        """
        发布成交数据到NATS - 与OrderBook管理器保持一致的推送方式
        """
        try:
            # 使用标准化器处理数据
            if self.normalizer:
                # 构建原始数据格式供标准化器处理
                raw_data = {
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
            else:
                # 如果没有标准化器，使用原始数据
                normalized_data = {
                    'symbol': trade_data.symbol,
                    'price': str(trade_data.price),
                    'quantity': str(trade_data.quantity),
                    'timestamp': trade_data.timestamp.isoformat(),
                    'side': trade_data.side,
                    'trade_id': trade_data.trade_id,
                    'exchange': self.exchange.value,
                    'market_type': self.market_type.value,
                    'data_type': 'trade'
                }

            # 使用统一的NATS推送方法
            success = await self.nats_publisher.publish_data(
                data_type='trade',
                exchange=self.exchange.value,
                market_type=self.market_type.value,
                symbol=trade_data.symbol,
                data=normalized_data
            )

            if success:
                self.stats['trades_published'] += 1
                self.logger.debug(f"✅ 成交数据推送成功: {trade_data.symbol}")
            else:
                self.logger.warning(f"⚠️ 成交数据推送失败: {trade_data.symbol}")

        except Exception as e:
            self.stats['errors'] += 1
            self.logger.error(f"❌ 成交数据推送异常: {trade_data.symbol}", error=str(e))

    async def _handle_error(self, symbol: str, operation: str, error: str):
        """统一的错误处理方法"""
        self.stats['errors'] += 1
        self.logger.error(f"❌ {operation}失败: {symbol}", error=error)

        # 如果错误过多，可以考虑重启连接
        if self.stats['errors'] > self.max_consecutive_errors:
            self.logger.warning(f"⚠️ 连续错误过多({self.stats['errors']})，考虑重启连接")
            self.stats['connection_errors'] += 1

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.stats.copy()

    async def _handle_error(self, symbol: str, error_type: str, error_msg: str):
        """统一错误处理"""
        self.stats['errors'] += 1
        self.logger.error(f"❌ {symbol} {error_type}错误: {error_msg}")

    async def _on_successful_operation(self, symbol: str, operation: str):
        """成功操作回调"""
        self.logger.debug(f"✅ {symbol} {operation}成功")
