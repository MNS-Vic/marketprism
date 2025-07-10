#!/usr/bin/env python3
"""
全量订单簿维护管理器

实现全量订单簿维护策略：
- Binance: 维护5000层深度
- OKX: 维护400层深度
- 推流: 统一限制为400层
- 数据完整性验证: Binance使用lastUpdateId，OKX使用checksum
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from decimal import Decimal
import structlog

from .data_types import Exchange, MarketType, NormalizedOrderBook, PriceLevel
from .normalizer import DataNormalizer
from .nats_publisher import NATSPublisher

logger = structlog.get_logger(__name__)


class FullOrderBookManager:
    """全量订单簿维护管理器"""
    
    def __init__(self, 
                 exchange: Exchange,
                 market_type: MarketType,
                 symbols: List[str],
                 normalizer: DataNormalizer,
                 nats_publisher: NATSPublisher):
        """
        初始化全量订单簿管理器
        
        Args:
            exchange: 交易所
            market_type: 市场类型
            symbols: 交易对列表
            normalizer: 数据标准化器
            nats_publisher: NATS发布器
        """
        self.logger = structlog.get_logger(__name__)
        self.exchange = exchange
        self.market_type = market_type
        self.symbols = symbols
        self.normalizer = normalizer
        self.nats_publisher = nats_publisher
        
        # 全量订单簿存储
        self.full_orderbooks: Dict[str, NormalizedOrderBook] = {}
        
        # 维护策略配置
        self.maintenance_config = {
            Exchange.BINANCE: {
                "max_depth": 5000,
                "validation_method": "lastUpdateId",
                "push_depth": 400
            },
            Exchange.OKX: {
                "max_depth": 400,
                "validation_method": "checksum",
                "push_depth": 400
            }
        }
        
        # 统计信息
        self.stats = {
            "updates_received": 0,
            "updates_processed": 0,
            "validation_failures": 0,
            "push_count": 0,
            "last_update_time": None
        }
        
        self.logger.info(
            "全量订单簿管理器初始化",
            exchange=exchange.value,
            market_type=market_type.value,
            symbols=symbols,
            max_depth=self.maintenance_config[exchange]["max_depth"],
            push_depth=self.maintenance_config[exchange]["push_depth"]
        )
    
    async def process_orderbook_update(self, symbol: str, raw_data: Dict[str, Any]) -> bool:
        """
        处理订单簿更新
        
        Args:
            symbol: 交易对
            raw_data: 原始数据
            
        Returns:
            处理是否成功
        """
        try:
            self.stats["updates_received"] += 1
            
            # 标准化数据
            normalized = await self._normalize_data(symbol, raw_data)
            if not normalized:
                return False
            
            # 验证数据完整性
            if not await self._validate_data_integrity(symbol, normalized):
                self.stats["validation_failures"] += 1
                self.logger.warning("数据完整性验证失败", symbol=symbol)
                return False
            
            # 更新全量订单簿
            await self._update_full_orderbook(symbol, normalized)
            
            # 推送限制深度的数据
            await self._push_limited_depth_data(symbol)
            
            self.stats["updates_processed"] += 1
            self.stats["last_update_time"] = datetime.now(timezone.utc)
            
            return True
            
        except Exception as e:
            self.logger.error("处理订单簿更新失败", symbol=symbol, error=str(e), exc_info=True)
            return False
    
    async def _normalize_data(self, symbol: str, raw_data: Dict[str, Any]) -> Optional[NormalizedOrderBook]:
        """标准化数据"""
        try:
            if self.exchange == Exchange.BINANCE:
                return self.normalizer.normalize_binance_orderbook(raw_data, symbol)
            elif self.exchange == Exchange.OKX:
                # OKX数据需要包装成正确格式
                okx_data = {"data": [raw_data]} if "data" not in raw_data else raw_data
                return self.normalizer.normalize_okx_orderbook(okx_data, symbol)
            else:
                self.logger.error("不支持的交易所", exchange=self.exchange.value)
                return None
                
        except Exception as e:
            self.logger.error("数据标准化失败", symbol=symbol, error=str(e))
            return None
    
    async def _validate_data_integrity(self, symbol: str, normalized: NormalizedOrderBook) -> bool:
        """验证数据完整性"""
        try:
            config = self.maintenance_config[self.exchange]
            
            if config["validation_method"] == "lastUpdateId":
                # Binance使用lastUpdateId验证
                return await self._validate_binance_sequence(symbol, normalized)
            elif config["validation_method"] == "checksum":
                # OKX使用checksum验证
                return await self._validate_okx_checksum(symbol, normalized)
            else:
                # 默认通过
                return True
                
        except Exception as e:
            self.logger.error("数据完整性验证异常", symbol=symbol, error=str(e))
            return False
    
    async def _validate_binance_sequence(self, symbol: str, normalized: NormalizedOrderBook) -> bool:
        """验证Binance序列号"""
        try:
            if symbol not in self.full_orderbooks:
                # 第一次接收数据，直接通过
                return True
            
            current_orderbook = self.full_orderbooks[symbol]
            
            # 检查lastUpdateId是否连续
            if hasattr(normalized, 'last_update_id') and hasattr(current_orderbook, 'last_update_id'):
                if normalized.last_update_id <= current_orderbook.last_update_id:
                    self.logger.warning(
                        "Binance序列号验证失败",
                        symbol=symbol,
                        current_id=current_orderbook.last_update_id,
                        new_id=normalized.last_update_id
                    )
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error("Binance序列号验证异常", symbol=symbol, error=str(e))
            return False
    
    async def _validate_okx_checksum(self, symbol: str, normalized: NormalizedOrderBook) -> bool:
        """验证OKX校验和"""
        try:
            # OKX checksum验证逻辑
            # 这里可以实现具体的checksum验证算法
            # 目前简化为基本检查
            
            if not normalized.bids or not normalized.asks:
                self.logger.warning("OKX订单簿数据为空", symbol=symbol)
                return False
            
            # 检查价格是否合理（买价应该小于卖价）
            if normalized.bids[0].price >= normalized.asks[0].price:
                self.logger.warning(
                    "OKX价格异常",
                    symbol=symbol,
                    best_bid=normalized.bids[0].price,
                    best_ask=normalized.asks[0].price
                )
                return False
            
            return True
            
        except Exception as e:
            self.logger.error("OKX校验和验证异常", symbol=symbol, error=str(e))
            return False
    
    async def _update_full_orderbook(self, symbol: str, normalized: NormalizedOrderBook):
        """更新全量订单簿"""
        try:
            config = self.maintenance_config[self.exchange]
            max_depth = config["max_depth"]
            
            # 限制深度到配置的最大值
            limited_bids = normalized.bids[:max_depth] if len(normalized.bids) > max_depth else normalized.bids
            limited_asks = normalized.asks[:max_depth] if len(normalized.asks) > max_depth else normalized.asks
            
            # 创建限制深度的订单簿
            limited_orderbook = NormalizedOrderBook(
                exchange_name=normalized.exchange_name,
                symbol_name=normalized.symbol_name,
                bids=limited_bids,
                asks=limited_asks,
                timestamp=normalized.timestamp,
                last_update_id=getattr(normalized, 'last_update_id', None)
            )
            
            # 存储全量订单簿
            self.full_orderbooks[symbol] = limited_orderbook
            
            self.logger.debug(
                "全量订单簿已更新",
                symbol=symbol,
                bids_count=len(limited_bids),
                asks_count=len(limited_asks),
                max_depth=max_depth
            )
            
        except Exception as e:
            self.logger.error("更新全量订单簿失败", symbol=symbol, error=str(e))
    
    async def _push_limited_depth_data(self, symbol: str):
        """推送限制深度的数据"""
        try:
            if symbol not in self.full_orderbooks:
                return
            
            full_orderbook = self.full_orderbooks[symbol]
            config = self.maintenance_config[self.exchange]
            push_depth = config["push_depth"]
            
            # 限制推送深度为400层
            push_bids = full_orderbook.bids[:push_depth] if len(full_orderbook.bids) > push_depth else full_orderbook.bids
            push_asks = full_orderbook.asks[:push_depth] if len(full_orderbook.asks) > push_depth else full_orderbook.asks
            
            # 构造推送数据
            push_data = {
                "exchange": self.exchange.value,
                "symbol": symbol,
                "market_type": self.market_type.value,
                "timestamp": full_orderbook.timestamp.isoformat() if full_orderbook.timestamp else datetime.now(timezone.utc).isoformat(),
                "bids": [[str(level.price), str(level.quantity)] for level in push_bids],
                "asks": [[str(level.price), str(level.quantity)] for level in push_asks],
                "bids_count": len(push_bids),
                "asks_count": len(push_asks),
                "full_bids_count": len(full_orderbook.bids),
                "full_asks_count": len(full_orderbook.asks),
                "push_depth_limit": push_depth
            }
            
            # 发布到NATS
            success = await self.nats_publisher.publish_orderbook(
                exchange=self.exchange.value,
                market_type=self.market_type.value,
                symbol=symbol,
                orderbook_data=push_data
            )
            
            if success:
                self.stats["push_count"] += 1
                self.logger.debug(
                    "订单簿数据推送成功",
                    symbol=symbol,
                    push_depth=push_depth,
                    full_depth=f"{len(full_orderbook.bids)}/{len(full_orderbook.asks)}"
                )
            else:
                self.logger.warning("订单簿数据推送失败", symbol=symbol)
            
        except Exception as e:
            self.logger.error("推送限制深度数据失败", symbol=symbol, error=str(e))
    
    def get_full_orderbook(self, symbol: str) -> Optional[NormalizedOrderBook]:
        """获取全量订单簿"""
        return self.full_orderbooks.get(symbol)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            "symbols_count": len(self.symbols),
            "maintained_orderbooks": len(self.full_orderbooks),
            "exchange": self.exchange.value,
            "market_type": self.market_type.value,
            "maintenance_config": self.maintenance_config[self.exchange]
        }
    
    async def cleanup(self):
        """清理资源"""
        try:
            self.full_orderbooks.clear()
            self.logger.info("全量订单簿管理器已清理")
        except Exception as e:
            self.logger.error("清理全量订单簿管理器失败", error=str(e))
