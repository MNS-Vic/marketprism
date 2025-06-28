"""
NATS客户端模块

负责与NATS服务器的连接和消息发布
"""

from datetime import datetime, timezone
import asyncio
import json
import structlog
from typing import Dict, Any, Optional, List

import nats
from nats.aio.client import Client as NATSClient
from nats.js.api import StreamConfig, RetentionPolicy

from .data_types import (
    NormalizedTrade, NormalizedOrderBook, 
    NormalizedKline, NormalizedTicker,
    NormalizedFundingRate, NormalizedOpenInterest, NormalizedLiquidation,
    NormalizedTopTraderLongShortRatio,
    EnhancedOrderBook, OrderBookDelta, OrderBookUpdateType
)
from .config import NATSConfig


class MarketDataPublisher:
    """市场数据发布器"""
    
    def __init__(self, config: NATSConfig):
        self.config = config
        self.logger = structlog.get_logger(__name__)
        self.client: Optional[NATSClient] = None
        self.js = None  # JetStream context
        self.is_connected = False
        
        # 主题格式
        self.trade_subject_format = "market.{exchange}.{symbol}.trade"
        self.orderbook_subject_format = "market.{exchange}.{symbol}.orderbook"
        self.kline_subject_format = "market.{exchange}.{symbol}.kline.{interval}"
        self.ticker_subject_format = "market.{exchange}.{symbol}.ticker"
        self.funding_rate_subject_format = "market.{exchange}.{symbol}.funding_rate"
        self.open_interest_subject_format = "market.{exchange}.{symbol}.open_interest"
        self.liquidation_subject_format = "market.{exchange}.{symbol}.liquidation"
        self.top_trader_subject_format = "market.{exchange}.{symbol}.top_trader_long_short_ratio"
    
    async def connect(self) -> bool:
        """连接到NATS服务器"""
        try:
            self.logger.info("连接到NATS服务器", url=self.config.url)
            
            # 创建NATS客户端
            self.client = await nats.connect(
                servers=[self.config.url],
                name=self.config.client_name,
                error_cb=self._error_handler,
                closed_cb=self._closed_handler,
                reconnected_cb=self._reconnected_handler,
                max_reconnect_attempts=5,
                reconnect_time_wait=2,
            )
            
            # 获取JetStream上下文
            self.js = self.client.jetstream()
            
            # 确保流存在
            await self._ensure_streams()
            
            self.is_connected = True
            self.logger.info("NATS连接成功")
            return True
            
        except Exception as e:
            self.logger.error("NATS连接失败", exc_info=True)
            self.is_connected = False
            return False
    
    async def disconnect(self):
        """断开NATS连接"""
        try:
            self.is_connected = False
            
            if self.client and not self.client.is_closed:
                # 先停止JetStream
                if self.js:
                    self.js = None
                
                # 关闭客户端连接
                await asyncio.wait_for(self.client.close(), timeout=5.0)
                self.logger.info("NATS连接已断开")
                
        except asyncio.TimeoutError:
            self.logger.warning("NATS断开连接超时")
        except Exception as e:
            self.logger.error("断开NATS连接时出错", exc_info=True)
        finally:
            self.client = None
            self.js = None
            self.is_connected = False
    
    async def _ensure_streams(self):
        """确保所需的流存在"""
        for stream_name, stream_config in self.config.streams.items():
            try:
                # 尝试获取流信息
                try:
                    await self.js.stream_info(stream_name)
                    self.logger.debug("流已存在", stream=stream_name)
                except:
                    # 流不存在，创建流
                    config = StreamConfig(
                        name=stream_config["name"],
                        subjects=stream_config["subjects"],
                        retention=RetentionPolicy.LIMITS,
                        max_msgs=stream_config["max_msgs"],
                        max_bytes=stream_config["max_bytes"],
                        max_age=stream_config["max_age"],
                        max_consumers=stream_config["max_consumers"],
                        num_replicas=stream_config["replicas"]
                    )
                    
                    await self.js.add_stream(config)
                    self.logger.info("创建NATS流", stream=stream_name)
                    
            except Exception as e:
                self.logger.error("创建流失败", stream=stream_name, exc_info=True)
                raise
    
    async def publish_trade(self, trade: NormalizedTrade) -> bool:
        """发布标准化交易数据到JetStream"""
        subject = self.trade_subject_format.format(
            exchange=trade.exchange_name.lower(),
            symbol=trade.symbol_name.lower()
        )
        
        return await self._publish_data(subject, trade)
    
    async def publish_orderbook(self, orderbook: NormalizedOrderBook) -> bool:
        """发布标准化订单簿数据到JetStream"""
        subject = self.orderbook_subject_format.format(
            exchange=orderbook.exchange_name.lower(),
            symbol=orderbook.symbol_name.lower()
        )
        
        return await self._publish_data(subject, orderbook)
    
    async def publish_kline(self, kline: NormalizedKline) -> bool:
        """发布K线数据"""
        subject = self.kline_subject_format.format(
            exchange=kline.exchange_name.lower(),
            symbol=kline.symbol_name.lower(),
            interval=kline.interval
        )
        
        return await self._publish_data(subject, kline)
    
    async def publish_ticker(self, ticker: NormalizedTicker) -> bool:
        """发布标准化行情数据到JetStream"""
        subject = self.ticker_subject_format.format(
            exchange=ticker.exchange_name.lower(),
            symbol=ticker.symbol_name.lower()
        )
        
        return await self._publish_data(subject, ticker)
    
    async def publish_funding_rate(self, funding_rate: NormalizedFundingRate) -> bool:
        """发布资金费率数据到JetStream"""
        subject = self.funding_rate_subject_format.format(
            exchange=funding_rate.exchange_name.lower(),
            symbol=funding_rate.symbol_name.lower().replace('-', '_')
        )
        
        return await self._publish_data(subject, funding_rate)
    
    async def publish_open_interest(self, open_interest: NormalizedOpenInterest) -> bool:
        """发布持仓量数据到JetStream"""
        subject = self.open_interest_subject_format.format(
            exchange=open_interest.exchange_name.lower(),
            symbol=open_interest.symbol_name.lower().replace('-', '_')
        )
        
        return await self._publish_data(subject, open_interest)
    
    async def publish_liquidation(self, liquidation: NormalizedLiquidation) -> bool:
        """发布强平数据到JetStream"""
        subject = self.liquidation_subject_format.format(
            exchange=liquidation.exchange_name.lower(),
            symbol=liquidation.symbol_name.lower().replace('-', '_')
        )
        
        return await self._publish_data(subject, liquidation)
    
    async def publish_top_trader_long_short_ratio(self, top_trader_data: NormalizedTopTraderLongShortRatio) -> bool:
        """发布大户持仓比数据到JetStream"""
        subject = self.top_trader_subject_format.format(
            exchange=top_trader_data.exchange_name.lower(),
            symbol=top_trader_data.symbol_name.lower().replace('-', '_')
        )
        
        return await self._publish_data(subject, top_trader_data)
    
    async def _publish_data(self, subject: str, data: Any) -> bool:
        """发布数据到NATS"""
        if not self.is_connected or not self.js:
            self.logger.warning("NATS未连接，无法发布消息", subject=subject)
            return False
        
        try:
            # 序列化数据
            if hasattr(data, 'json'):
                # Pydantic model
                message_data = data.json().encode('utf-8')
            else:
                # 普通字典
                message_data = json.dumps(data, default=str).encode('utf-8')
            
            # 发布到JetStream
            ack = await self.js.publish(subject, message_data)
            
            self.logger.debug(
                "发布消息成功",
                subject=subject,
                sequence=ack.seq
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "发布消息失败",
                subject=subject,
                exc_info=True
            )
            return False
    
    async def _error_handler(self, error):
        """错误处理器"""
        self.logger.error("NATS错误", error=str(error))
    
    async def _closed_handler(self):
        """连接关闭处理器"""
        self.is_connected = False
        self.logger.warning("NATS连接已关闭")
    
    async def _reconnected_handler(self):
        """重连处理器"""
        self.is_connected = True
        self.logger.info("NATS重连成功")
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        return {
            "connected": self.is_connected,
            "server_url": self.config.url,
            "client_name": self.config.client_name,
            "last_check": datetime.now(timezone.utc).isoformat()
        }


class NATSManager:
    """NATS管理器"""
    
    def __init__(self, config: NATSConfig):
        self.config = config
        self.logger = structlog.get_logger(__name__)
        self.publisher = MarketDataPublisher(config)
    
    async def start(self) -> bool:
        """启动NATS服务"""
        return await self.publisher.connect()
    
    async def stop(self):
        """停止NATS服务"""
        await self.publisher.disconnect()
    
    def get_publisher(self) -> MarketDataPublisher:
        """获取发布器实例"""
        return self.publisher
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        return {
            "nats": self.publisher.get_health_status(),
            "status": "healthy" if self.publisher.is_connected else "unhealthy"
        }


class EnhancedMarketDataPublisher(MarketDataPublisher):
    """增强的市场数据发布器 - 专注增量深度数据"""
    
    def __init__(self, base_publisher: MarketDataPublisher):
        # 继承基础发布器的配置和连接
        self.config = base_publisher.config
        self.logger = base_publisher.logger
        self.client = base_publisher.client
        self.js = base_publisher.js
        self.is_connected = base_publisher.is_connected
        
        # 继承基础主题格式
        self.trade_subject_format = base_publisher.trade_subject_format
        self.orderbook_subject_format = base_publisher.orderbook_subject_format
        self.kline_subject_format = base_publisher.kline_subject_format
        self.ticker_subject_format = base_publisher.ticker_subject_format
        self.funding_rate_subject_format = base_publisher.funding_rate_subject_format
        self.open_interest_subject_format = base_publisher.open_interest_subject_format
        self.liquidation_subject_format = base_publisher.liquidation_subject_format
        
        # 新增：增量深度专用主题
        self.orderbook_delta_subject = "market.{exchange}.{symbol}.orderbook.delta"
        self.depth_update_subject = "market.depth.{exchange}.{symbol}"

        # 新增：大户持仓比数据主题
        self.top_trader_subject_format = "market.{exchange}.{symbol}.top_trader_ratio"
    
    async def publish_orderbook_delta(self, delta: OrderBookDelta) -> bool:
        """发布增量订单簿数据 - 核心功能"""
        subject = self.orderbook_delta_subject.format(
            exchange=delta.exchange_name.lower(),
            symbol=delta.symbol_name.lower()
        )
        
        # 创建轻量级增量数据
        delta_data = {
            "exchange": delta.exchange_name,
            "symbol": delta.symbol_name,
            "update_id": delta.update_id,
            "prev_update_id": delta.prev_update_id,
            "timestamp": delta.timestamp.isoformat() + 'Z',
            "update_type": "delta",
            
            # 只包含变化的价位
            "bid_changes": delta.bid_updates,
            "ask_changes": delta.ask_updates,
            
            # 统计信息
            "total_bid_changes": delta.total_bid_changes,
            "total_ask_changes": delta.total_ask_changes
        }
        
        return await self._publish_data(subject, delta_data)
    
    async def publish_depth_update(self, update: 'EnhancedOrderBookUpdate') -> bool:
        """发布增量深度更新"""
        subject = self.depth_update_subject.format(
            exchange=update.exchange_name.lower(),
            symbol=update.symbol_name.lower().replace('-', '_')
        )
        
        return await self._publish_data(subject, update)

    async def publish_top_trader_ratio(self, top_trader_data: 'NormalizedTopTraderLongShortRatio') -> bool:
        """发布大户持仓比数据"""
        subject = self.top_trader_subject_format.format(
            exchange=top_trader_data.exchange_name.lower(),
            symbol=top_trader_data.symbol_name.lower().replace('-', '_')
        )

        return await self._publish_data(subject, top_trader_data)

    async def publish_enhanced_orderbook(self, orderbook: EnhancedOrderBook) -> bool:
        """智能发布订单簿数据 - 简化版本"""
        success_count = 0
        
        # 1. 发布完整订单簿数据（主要流）
        if await self.publish_orderbook(self._to_normalized_orderbook(orderbook)):
            success_count += 1
        
        return success_count > 0
    
    def _to_normalized_orderbook(self, enhanced: EnhancedOrderBook) -> NormalizedOrderBook:
        """转换为标准订单簿格式 (向后兼容)"""
        return NormalizedOrderBook(
            exchange_name=enhanced.exchange_name,
            symbol_name=enhanced.symbol_name,
            last_update_id=enhanced.last_update_id,
            bids=enhanced.bids,
            asks=enhanced.asks,
            timestamp=enhanced.timestamp,
            collected_at=enhanced.collected_at
        ) 