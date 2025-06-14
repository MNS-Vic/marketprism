"""
MarketPrism 数据存储服务
基于unified_storage_manager的微服务化存储服务
提供热冷数据管理、查询路由、数据生命周期管理
"""

import asyncio
import json
import signal
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from aiohttp import web
import aiohttp
import yaml
import sys
from pathlib import Path
import traceback
import logging

# 确保能正确找到项目根目录并添加到sys.path
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.service_framework import BaseService
from core.storage.unified_storage_manager import UnifiedStorageManager
from core.storage.types import NormalizedTrade, NormalizedTicker, NormalizedOrderBook

class DataStorageService(BaseService):
    """数据存储微服务"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("data-storage-service", config)
        self.storage_manager: Optional[UnifiedStorageManager] = None

    def setup_routes(self):
        """设置API路由"""
        self.app.router.add_post('/api/v1/storage/hot/trades', self.store_hot_trade)
        self.app.router.add_post('/api/v1/storage/hot/tickers', self.store_hot_ticker)
        self.app.router.add_post('/api/v1/storage/hot/orderbooks', self.store_hot_orderbook)
        self.app.router.add_get('/api/v1/storage/hot/trades/{exchange}/{symbol}', self.get_hot_trades)
        self.app.router.add_get('/api/v1/storage/hot/tickers/{exchange}/{symbol}', self.get_hot_ticker)
        self.app.router.add_get('/api/v1/storage/hot/orderbooks/{exchange}/{symbol}', self.get_hot_orderbook)
        self.app.router.add_post('/api/v1/storage/cold/archive', self.archive_to_cold)
        self.app.router.add_get('/api/v1/storage/cold/trades/{exchange}/{symbol}', self.get_cold_trades)
        self.app.router.add_post('/api/v1/storage/lifecycle/cleanup', self.cleanup_expired_data)
        self.app.router.add_get('/api/v1/storage/stats', self.get_storage_stats)

    async def on_startup(self):
        """服务启动初始化"""
        try:
            self.storage_manager = UnifiedStorageManager()
            await self.storage_manager.initialize()
            self.logger.info("Data storage service's UnifiedStorageManager initialized successfully")
        except Exception as e:
            self.logger.warning(f"UnifiedStorageManager初始化失败，运行在降级模式: {e}")
            self.storage_manager = None


    async def on_shutdown(self):
        """服务停止清理"""
        if self.storage_manager and hasattr(self.storage_manager, 'close'):
            try:
                await self.storage_manager.close()
                self.logger.info("Data storage service's UnifiedStorageManager shutdown completed")
            except Exception as e:
                self.logger.warning(f"UnifiedStorageManager关闭失败: {e}")
        else:
            self.logger.info("Data storage service shutdown completed (degraded mode)")

    # ==================== API Handlers ====================

    async def store_hot_trade(self, request: web.Request) -> web.Response:
        """存储热交易数据"""
        if not self.storage_manager:
            return web.json_response({"status": "degraded", "message": "Storage service running in degraded mode"}, status=503)
        try:
            data = await request.json()
            trade = NormalizedTrade(**data)
            await self.storage_manager.store_trade(trade)
            return web.json_response({"status": "success", "message": "Trade stored successfully"})
        except Exception as e:
            self.logger.error(f"Failed to store hot trade: {e}", exc_info=True)
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def store_hot_ticker(self, request: web.Request) -> web.Response:
        """存储热行情数据"""
        try:
            data = await request.json()
            ticker = NormalizedTicker(**data)
            await self.storage_manager.store_ticker(ticker)
            return web.json_response({"status": "success", "message": "Ticker stored successfully"})
        except Exception as e:
            self.logger.error(f"Failed to store hot ticker: {e}", exc_info=True)
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def store_hot_orderbook(self, request: web.Request) -> web.Response:
        """存储热订单簿数据"""
        try:
            data = await request.json()
            orderbook = NormalizedOrderBook(**data)
            await self.storage_manager.store_orderbook(orderbook)
            return web.json_response({"status": "success", "message": "Orderbook stored successfully"})
        except Exception as e:
            self.logger.error(f"Failed to store hot orderbook: {e}", exc_info=True)
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def get_hot_trades(self, request: web.Request) -> web.Response:
        """查询热交易数据"""
        try:
            exchange = request.match_info['exchange']
            symbol = request.match_info['symbol']
            limit = int(request.query.get('limit', '100'))
            trades = await self.storage_manager.get_recent_trades(exchange, symbol, limit)
            return web.json_response([trade.dict() for trade in trades])
        except Exception as e:
            self.logger.error(f"Failed to query hot trades for {exchange}:{symbol}: {e}", exc_info=True)
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def get_hot_ticker(self, request: web.Request) -> web.Response:
        """查询热行情数据"""
        try:
            exchange = request.match_info['exchange']
            symbol = request.match_info['symbol']
            ticker = await self.storage_manager.get_latest_ticker(exchange, symbol)
            if ticker:
                return web.json_response(ticker.dict())
            return web.json_response({"status": "not_found"}, status=404)
        except Exception as e:
            self.logger.error(f"Failed to query hot ticker for {exchange}:{symbol}: {e}", exc_info=True)
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def get_hot_orderbook(self, request: web.Request) -> web.Response:
        """查询热订单簿数据"""
        try:
            exchange = request.match_info['exchange']
            symbol = request.match_info['symbol']
            orderbook = await self.storage_manager.get_latest_orderbook(exchange, symbol)
            if orderbook:
                return web.json_response(orderbook.dict())
            return web.json_response({"status": "not_found"}, status=404)
        except Exception as e:
            self.logger.error(f"Failed to query hot orderbook for {exchange}:{symbol}: {e}", exc_info=True)
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def archive_to_cold(self, request: web.Request) -> web.Response:
        """将热数据归档到冷存储"""
        try:
            # 这里的具体逻辑可以根据需求实现，例如按时间范围归档
            cutoff_days = int(request.query.get('days', '30'))
            cutoff_date = datetime.now() - timedelta(days=cutoff_days)
            summary = await self.storage_manager.archive_data(cutoff_date)
            return web.json_response({"status": "success", "summary": summary})
        except Exception as e:
            self.logger.error(f"Failed to archive data: {e}", exc_info=True)
            return web.json_response({"status": "error", "message": str(e)}, status=500)
    
    async def get_cold_trades(self, request: web.Request) -> web.Response:
        # 实际的冷数据查询逻辑会更复杂，这里仅为示例
        return web.json_response({"status": "error", "message": "Not implemented"}, status=501)

    async def cleanup_expired_data(self, request: web.Request) -> web.Response:
        """清理过期数据"""
        try:
            summary = await self.storage_manager.cleanup_data()
            return web.json_response({"status": "success", "summary": summary})
        except Exception as e:
            self.logger.error(f"Failed to cleanup data: {e}", exc_info=True)
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def get_storage_stats(self, request: web.Request) -> web.Response:
        """获取存储统计信息"""
        if not self.storage_manager:
            return web.json_response({
                "status": "degraded",
                "mode": "degraded",
                "message": "Storage service running in degraded mode",
                "hot_storage": {"status": "unavailable"},
                "cold_storage": {"status": "unavailable"}
            })
        try:
            stats = await self.storage_manager.get_stats()
            return web.json_response(stats)
        except Exception as e:
            self.logger.error(f"Failed to get storage stats: {e}", exc_info=True)
            return web.json_response({"status": "error", "message": str(e)}, status=500)


async def main():
    """服务主入口点"""
    try:
        project_root = Path(__file__).resolve().parents[2]
        config_path = project_root / 'config' / 'services.yaml'

        with open(config_path, 'r', encoding='utf-8') as f:
            # 如果文件为空或无效，则视为空字典
            full_config = yaml.safe_load(f) or {}
        
        # 获取本服务的特定配置, 如果没有则返回空字典
        service_config = full_config.get('services', {}).get('data-storage-service', {})
        
        service = DataStorageService(config=service_config)
        await service.run()

    except Exception:
        # 强制将完整的堆栈跟踪打印到stderr，以便调试
        logging.basicConfig()
        logging.critical("Data Storage Service failed to start", exc_info=True)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())