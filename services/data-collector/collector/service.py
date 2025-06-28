"""
MarketPrism Data Collector Service - 集成微服务
集成了数据收集、OrderBook管理和数据聚合功能的统一微服务
"""

import asyncio
import structlog
from datetime import datetime
from typing import Dict, Any
from pathlib import Path
from aiohttp import web

# 导入BaseService框架
from core.base_service import BaseService
from core.data_collection.public_data_collector import PublicDataCollector

# 导入本地模块
from .config import ConfigManager
from .data_types import Exchange, ExchangeConfig
from .normalizer import DataNormalizer

# 获取项目根目录
project_root = Path(__file__).parent.parent.parent.parent


class DataCollectorService(BaseService):
    """数据收集器微服务 - 收集数据→标准化→推送NATS + OrderBook增量维护"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("market-data-collector", config)
        self.public_collector = None
        self.orderbook_manager = None
        self.data_normalizer = None

        # 功能开关
        self.enable_orderbook = config.get('enable_orderbook', True)
        
        # 数据存储
        self.collected_data = {
            'tickers': {},
            'orderbooks': {},
            'stats': {}
        }

    async def on_startup(self):
        """服务启动初始化"""
        try:
            # 设置API路由
            self.setup_routes()

            # 初始化公开数据收集器
            config_path = project_root / "config" / "public_data_sources.yaml"
            self.public_collector = PublicDataCollector(str(config_path))
            self.public_collector.add_data_callback(self._on_data_received)
            
            # 启动数据收集
            asyncio.create_task(self.public_collector.start())

            # 初始化数据标准化器
            self.data_normalizer = DataNormalizer()

            # 初始化OrderBook Manager（如果启用）
            if self.enable_orderbook:
                await self._init_orderbook_manager()

            self.logger.info("🎉 数据收集器服务初始化成功 (收集→标准化→NATS推送)")

        except Exception as e:
            self.logger.error(f"服务初始化失败: {e}")
            raise

    async def _init_orderbook_manager(self):
        """初始化OrderBook Manager"""
        try:
            from .orderbook_manager import OrderBookManager

            # 创建交易所配置
            exchange_config = ExchangeConfig(
                exchange=Exchange.BINANCE,
                snapshot_interval=60,
                symbols=['BTC-USDT', 'ETH-USDT', 'BNB-USDT']
            )

            # 创建OrderBook Manager（使用共享的normalizer）
            self.orderbook_manager = OrderBookManager(exchange_config, self.data_normalizer)
            asyncio.create_task(self.orderbook_manager.start())
            self.logger.info("✅ OrderBook Manager启动成功")

        except Exception as e:
            self.logger.error(f"OrderBook Manager启动失败: {e}")

    async def _on_data_received(self, data_type: str, exchange: str, data: Dict[str, Any]):
        """数据接收回调"""
        try:
            key = f"{exchange}:{data.get('symbol', 'unknown')}"
            
            if data_type == 'ticker':
                self.collected_data['tickers'][key] = data
            elif data_type == 'orderbook':
                self.collected_data['orderbooks'][key] = data
                
        except Exception as e:
            self.logger.error(f"数据处理失败: {e}")

    async def on_shutdown(self):
        """服务关闭清理"""
        if self.public_collector:
            await self.public_collector.stop()
        self.logger.info("数据收集器服务已关闭")
