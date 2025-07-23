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
                 nats_publisher: NATSPublisher):
        self.exchange = exchange
        self.market_type = market_type
        self.symbols = symbols
        self.normalizer = normalizer
        self.nats_publisher = nats_publisher
        
        # 日志器
        self.logger = structlog.get_logger(f"{exchange.value}_{market_type.value}_trades")
        
        # 统计信息
        self.stats = {
            'trades_received': 0,
            'trades_processed': 0,
            'trades_published': 0,
            'errors': 0,
            'last_trade_time': None
        }
        
        # 运行状态
        self.is_running = False
        self.websocket_task: Optional[asyncio.Task] = None
        
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
        发布成交数据到NATS - 优化：延迟标准化到NATS层

        🔧 架构优化：保持原始交易所数据格式到NATS发布层
        确保价格精度、时间戳格式等原始特性得到保持
        """
        try:
            # 🔧 优化：构建原始格式数据，不进行标准化
            # 保持各交易所的原始字段名和数据格式
            raw_trade_data = {
                'exchange': self.exchange.value,
                'market_type': self.market_type.value,
                'symbol': trade_data.symbol,  # 保持原始symbol格式
                'price': str(trade_data.price),  # 保持原始精度
                'quantity': str(trade_data.quantity),  # 保持原始精度
                'timestamp': trade_data.timestamp.isoformat(),  # 保持原始时间戳格式
                'side': trade_data.side,
                'trade_id': trade_data.trade_id,
                'data_type': 'trade',
                'raw_data': True,  # 标记为原始数据
                'exchange_specific': {
                    'original_format': True,
                    'precision_preserved': True
                }
            }

            # 🔧 优化：发布原始数据，标准化在NATS Publisher中统一进行
            await self.nats_publisher.publish_trade_data(
                raw_trade_data,
                self.exchange,
                self.market_type,
                trade_data.symbol  # 使用原始symbol
            )

            self.stats['trades_published'] += 1
            self.stats['last_trade_time'] = datetime.now(timezone.utc)

            self.logger.debug(f"✅ 成交数据发布成功: {trade_data.symbol}",
                            price=str(trade_data.price),
                            quantity=str(trade_data.quantity),
                            side=trade_data.side)

        except Exception as e:
            self.stats['errors'] += 1
            self.logger.error(f"❌ 成交数据发布失败: {trade_data.symbol}",
                            error=str(e))

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
