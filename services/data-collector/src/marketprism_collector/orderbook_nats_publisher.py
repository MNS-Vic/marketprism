"""
OrderBook NATS Publisher - 订单簿NATS推送器

每秒将OrderBook Manager维护的标准化订单簿数据推送到NATS
"""

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Set
import structlog

from .orderbook_manager import OrderBookManager
from .nats_client import MarketDataPublisher
from .data_types import EnhancedOrderBook, OrderBookUpdateType
from .config_loader import ConfigLoader


class OrderBookNATSPublisher:
    """订单簿NATS推送器"""
    
    def __init__(self, orderbook_manager: OrderBookManager, nats_publisher: MarketDataPublisher, config: Dict[str, Any] = None):
        self.orderbook_manager = orderbook_manager
        self.nats_publisher = nats_publisher
        self.config = config or {}
        self.logger = structlog.get_logger(__name__)
        
        # 推送配置
        self.publish_interval = self.config.get('publish_interval', 1.0)  # 每秒推送一次
        self.enabled = self.config.get('enabled', True)
        self.symbols = self.config.get('symbols', [])
        
        # 状态管理
        self.is_running = False
        self.publish_task: Optional[asyncio.Task] = None
        self.last_publish_times: Dict[str, datetime] = {}
        self.last_update_ids: Dict[str, int] = {}
        
        # 统计信息
        self.stats = {
            'total_publishes': 0,
            'successful_publishes': 0,
            'failed_publishes': 0,
            'symbols_published': 0,
            'last_publish_time': None,
            'publish_rate': 0.0,
            'errors': 0
        }
        
        self.logger.info(
            "OrderBook NATS推送器初始化",
            publish_interval=self.publish_interval,
            enabled=self.enabled,
            symbols=len(self.symbols)
        )
    
    async def start(self, symbols: List[str] = None) -> bool:
        """启动NATS推送器"""
        if not self.enabled:
            self.logger.info("NATS推送器已禁用")
            return True
        
        if self.is_running:
            self.logger.warning("NATS推送器已在运行")
            return True
        
        try:
            # 使用传入的symbols或配置中的symbols
            self.symbols = symbols or self.symbols
            if not self.symbols:
                self.logger.error("未指定要推送的交易对")
                return False
            
            # 检查NATS连接
            if not self.nats_publisher.is_connected:
                self.logger.error("NATS未连接，无法启动推送器")
                return False
            
            self.is_running = True
            
            # 启动推送任务
            self.publish_task = asyncio.create_task(self._publish_loop())
            
            self.logger.info(
                "OrderBook NATS推送器启动成功",
                symbols=self.symbols,
                publish_interval=self.publish_interval
            )
            
            return True
            
        except Exception as e:
            self.logger.error("启动NATS推送器失败", exc_info=True)
            self.is_running = False
            return False
    
    async def stop(self):
        """停止NATS推送器"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # 取消推送任务
        if self.publish_task and not self.publish_task.done():
            self.publish_task.cancel()
            try:
                await self.publish_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info(
            "OrderBook NATS推送器已停止",
            stats=self.get_stats()
        )
    
    async def _publish_loop(self):
        """推送循环 - 每秒推送一次"""
        self.logger.info("开始订单簿推送循环")
        
        while self.is_running:
            try:
                start_time = time.time()
                
                # 推送所有交易对的订单簿
                await self._publish_all_orderbooks()
                
                # 计算推送耗时
                elapsed = time.time() - start_time
                
                # 等待到下一个推送时间
                sleep_time = max(0, self.publish_interval - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                else:
                    self.logger.warning(
                        "推送耗时超过间隔",
                        elapsed=elapsed,
                        interval=self.publish_interval
                    )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("推送循环异常", exc_info=True)
                self.stats['errors'] += 1
                await asyncio.sleep(1)  # 错误后等待1秒
        
        self.logger.info("推送循环已结束")
    
    async def _publish_all_orderbooks(self):
        """推送所有交易对的订单簿"""
        published_count = 0
        
        for symbol in self.symbols:
            try:
                success = await self._publish_orderbook(symbol)
                if success:
                    published_count += 1
                    
            except Exception as e:
                self.logger.error(
                    "推送订单簿失败",
                    symbol=symbol,
                    exc_info=True
                )
                self.stats['failed_publishes'] += 1
        
        # 更新统计信息
        self.stats['total_publishes'] += 1
        if published_count > 0:
            self.stats['successful_publishes'] += 1
            self.stats['symbols_published'] = published_count
            self.stats['last_publish_time'] = datetime.now(timezone.utc)
        
        # 计算推送频率
        if self.stats['total_publishes'] > 0:
            self.stats['publish_rate'] = self.stats['successful_publishes'] / self.stats['total_publishes']
    
    async def _publish_orderbook(self, symbol: str) -> bool:
        """推送单个交易对的订单簿"""
        try:
            # 获取当前订单簿
            orderbook = self.orderbook_manager.get_current_orderbook(symbol)
            if not orderbook:
                self.logger.debug("订单簿未就绪", symbol=symbol)
                return False
            
            # 检查是否有更新（避免重复推送相同数据）
            current_update_id = orderbook.last_update_id or 0
            last_update_id = self.last_update_ids.get(symbol, 0)
            
            if current_update_id <= last_update_id:
                self.logger.debug(
                    "订单簿无更新，跳过推送",
                    symbol=symbol,
                    current_id=current_update_id,
                    last_id=last_update_id
                )
                return False
            
            # 创建推送数据
            publish_data = self._create_publish_data(orderbook)
            
            # 推送到NATS
            success = await self.nats_publisher.publish_orderbook(publish_data)
            
            if success:
                # 更新推送记录
                self.last_publish_times[symbol] = datetime.now(timezone.utc)
                self.last_update_ids[symbol] = current_update_id
                
                self.logger.debug(
                    "订单簿推送成功",
                    symbol=symbol,
                    update_id=current_update_id,
                    depth_levels=orderbook.depth_levels
                )
                
                return True
            else:
                self.logger.warning("订单簿推送失败", symbol=symbol)
                return False
                
        except Exception as e:
            self.logger.error(
                "推送订单簿异常",
                symbol=symbol,
                exc_info=True
            )
            return False
    
    def _create_publish_data(self, orderbook: EnhancedOrderBook) -> 'NormalizedOrderBook':
        """创建推送数据"""
        from .data_types import NormalizedOrderBook
        
        # 转换为标准化订单簿格式
        normalized_orderbook = NormalizedOrderBook(
            exchange_name=orderbook.exchange_name,
            symbol_name=orderbook.symbol_name,
            bids=orderbook.bids,
            asks=orderbook.asks,
            timestamp=orderbook.timestamp,
            last_update_id=orderbook.last_update_id,
            
            # 添加推送时间戳
            collected_at=datetime.now(timezone.utc)
        )
        
        return normalized_orderbook
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            'is_running': self.is_running,
            'symbols_count': len(self.symbols),
            'publish_interval': self.publish_interval,
            'enabled': self.enabled
        }
    
    def get_symbol_stats(self) -> Dict[str, Any]:
        """获取交易对统计信息"""
        symbol_stats = {}
        
        for symbol in self.symbols:
            orderbook = self.orderbook_manager.get_current_orderbook(symbol)
            last_publish_time = self.last_publish_times.get(symbol)
            last_update_id = self.last_update_ids.get(symbol, 0)
            
            symbol_stats[symbol] = {
                'is_ready': orderbook is not None,
                'last_update_id': last_update_id,
                'last_publish_time': last_publish_time.isoformat() if last_publish_time else None,
                'depth_levels': orderbook.depth_levels if orderbook else 0,
                'best_bid': float(orderbook.bids[0].price) if orderbook and orderbook.bids else None,
                'best_ask': float(orderbook.asks[0].price) if orderbook and orderbook.asks else None
            }
        
        return symbol_stats


class OrderBookNATSConfig:
    """订单簿NATS推送器配置"""
    
    def __init__(self, config_file: str = None):
        self.config_loader = ConfigLoader()
        
        if config_file:
            self.config = self.config_loader.load_config(config_file)
        else:
            # 默认配置
            self.config = {
                'orderbook_nats_publisher': {
                    'enabled': True,
                    'publish_interval': 1.0,
                    'symbols': ['BTCUSDT', 'ETHUSDT'],
                    'quality_control': {
                        'min_depth_levels': 10,
                        'max_age_seconds': 30
                    }
                },
                'nats': {
                    'url': 'nats://localhost:4222',
                    'stream_name': 'MARKET_DATA',
                    'subject_prefix': 'market'
                }
            }
    
    def get_publisher_config(self) -> Dict[str, Any]:
        """获取推送器配置"""
        return self.config.get('orderbook_nats_publisher', {})
    
    def get_nats_config(self) -> Dict[str, Any]:
        """获取NATS配置"""
        return self.config.get('nats', {})


# 工厂函数
async def create_orderbook_nats_publisher(
    orderbook_manager: OrderBookManager,
    nats_config: Dict[str, Any],
    publisher_config: Dict[str, Any] = None
) -> OrderBookNATSPublisher:
    """创建订单簿NATS推送器"""
    
    # 创建NATS发布器
    from .config import NATSConfig
    
    nats_cfg = NATSConfig(
        url=nats_config.get('url', 'nats://localhost:4222'),
        stream_name=nats_config.get('stream_name', 'MARKET_DATA'),
        subject_prefix=nats_config.get('subject_prefix', 'market')
    )
    
    nats_publisher = MarketDataPublisher(nats_cfg)
    await nats_publisher.connect()
    
    # 创建推送器
    publisher = OrderBookNATSPublisher(
        orderbook_manager=orderbook_manager,
        nats_publisher=nats_publisher,
        config=publisher_config or {}
    )
    
    return publisher 