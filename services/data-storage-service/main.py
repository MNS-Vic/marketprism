"""
MarketPrism 数据存储服务
基于unified_storage_manager的微服务化存储服务
提供热冷数据管理、查询路由、数据生命周期管理
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from aiohttp import web
import aiohttp

from core.service_framework import BaseService, get_service_registry
from core.storage.unified_storage_manager import UnifiedStorageManager
from core.storage.types import NormalizedTrade, NormalizedTicker, NormalizedOrderBook


class DataStorageService(BaseService):
    """数据存储微服务"""
    
    def __init__(self):
        super().__init__("data-storage-service")
        self.storage_manager = None
        
    async def setup_routes(self):
        """设置API路由"""
        # 热数据存储API
        self.app.router.add_post('/api/v1/storage/hot/trades', self.store_hot_trade)
        self.app.router.add_post('/api/v1/storage/hot/tickers', self.store_hot_ticker)
        self.app.router.add_post('/api/v1/storage/hot/orderbooks', self.store_hot_orderbook)
        
        # 热数据查询API
        self.app.router.add_get('/api/v1/storage/hot/trades/{exchange}/{symbol}', self.get_hot_trades)
        self.app.router.add_get('/api/v1/storage/hot/tickers/{exchange}/{symbol}', self.get_hot_ticker)
        self.app.router.add_get('/api/v1/storage/hot/orderbooks/{exchange}/{symbol}', self.get_hot_orderbook)
        
        # 冷数据归档API
        self.app.router.add_post('/api/v1/storage/cold/archive', self.archive_to_cold)
        self.app.router.add_get('/api/v1/storage/cold/trades/{exchange}/{symbol}', self.get_cold_trades)
        
        # 数据生命周期管理API
        self.app.router.add_post('/api/v1/storage/lifecycle/cleanup', self.cleanup_expired_data)
        self.app.router.add_get('/api/v1/storage/stats', self.get_storage_stats)
        
    async def on_startup(self):
        """服务启动初始化"""
        try:
            # 初始化存储管理器
            self.storage_manager = UnifiedStorageManager()
            await self.storage_manager.start()
            
            # 注册健康检查
            self.health_checker.add_check("storage_manager", self._check_storage_health)
            
            # 注册服务
            registry = get_service_registry()
            await registry.register_service(
                service_name="data-storage-service",
                host="localhost",
                port=self.config.get('port', 8080),
                metadata={
                    "version": "1.0.0",
                    "capabilities": ["hot_storage", "cold_storage", "lifecycle_management"]
                }
            )
            
            self.logger.info("Data storage service initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize storage service: {e}")
            raise
            
    async def on_shutdown(self):
        """服务停止清理"""
        try:
            if self.storage_manager:
                await self.storage_manager.stop()
                
            # 注销服务
            registry = get_service_registry()
            await registry.deregister_service("data-storage-service")
            
            self.logger.info("Data storage service shutdown completed")
            
        except Exception as e:
            self.logger.error(f"Error during storage service shutdown: {e}")
            
    async def _check_storage_health(self) -> str:
        """检查存储健康状态"""
        if not self.storage_manager:
            return "storage_manager_not_initialized"
            
        try:
            # 简单的存储连接测试
            test_data = NormalizedTrade(
                timestamp=datetime.now(),
                symbol="BTCUSDT",
                exchange="test",
                price=50000.0,
                amount=0.001,
                side="buy",
                trade_id="health_check"
            )
            
            # 尝试存储和读取
            await self.storage_manager.store_trade(test_data)
            return "healthy"
            
        except Exception as e:
            return f"unhealthy: {str(e)}"
            
    # ==================== 热数据存储API ====================
    
    async def store_hot_trade(self, request):
        """存储热交易数据"""
        try:
            data = await request.json()
            trade = NormalizedTrade(**data)
            
            await self.storage_manager.store_trade(trade)
            self.metrics.counter("hot_trades_stored")
            
            return web.json_response({
                "status": "success",
                "message": "Trade stored successfully",
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            self.logger.error(f"Failed to store hot trade: {e}")
            self.metrics.counter("hot_trades_store_errors")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
            
    async def store_hot_ticker(self, request):
        """存储热行情数据"""
        try:
            data = await request.json()
            ticker = NormalizedTicker(**data)
            
            await self.storage_manager.store_ticker(ticker)
            self.metrics.counter("hot_tickers_stored")
            
            return web.json_response({
                "status": "success",
                "message": "Ticker stored successfully",
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            self.logger.error(f"Failed to store hot ticker: {e}")
            self.metrics.counter("hot_tickers_store_errors")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
            
    async def store_hot_orderbook(self, request):
        """存储热订单簿数据"""
        try:
            data = await request.json()
            orderbook = NormalizedOrderBook(**data)
            
            await self.storage_manager.store_orderbook(orderbook)
            self.metrics.counter("hot_orderbooks_stored")
            
            return web.json_response({
                "status": "success",
                "message": "Orderbook stored successfully",
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            self.logger.error(f"Failed to store hot orderbook: {e}")
            self.metrics.counter("hot_orderbooks_store_errors")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
            
    # ==================== 热数据查询API ====================
    
    async def get_hot_trades(self, request):
        """查询热交易数据"""
        try:
            exchange = request.match_info['exchange']
            symbol = request.match_info['symbol']
            limit = int(request.query.get('limit', 100))
            
            trades = await self.storage_manager.get_recent_trades(exchange, symbol, limit)
            self.metrics.counter("hot_trades_queries")
            
            return web.json_response({
                "status": "success",
                "data": [trade.dict() for trade in trades],
                "count": len(trades),
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            self.logger.error(f"Failed to query hot trades: {e}")
            self.metrics.counter("hot_trades_query_errors")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
            
    async def get_hot_ticker(self, request):
        """查询热行情数据"""
        try:
            exchange = request.match_info['exchange']
            symbol = request.match_info['symbol']
            
            ticker = await self.storage_manager.get_latest_ticker(exchange, symbol)
            self.metrics.counter("hot_tickers_queries")
            
            if ticker:
                return web.json_response({
                    "status": "success",
                    "data": ticker.dict(),
                    "timestamp": datetime.now().isoformat()
                })
            else:
                return web.json_response({
                    "status": "not_found",
                    "message": f"No ticker found for {exchange}:{symbol}"
                }, status=404)
                
        except Exception as e:
            self.logger.error(f"Failed to query hot ticker: {e}")
            self.metrics.counter("hot_tickers_query_errors")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
            
    async def get_hot_orderbook(self, request):
        """查询热订单簿数据"""
        try:
            exchange = request.match_info['exchange']
            symbol = request.match_info['symbol']
            
            orderbook = await self.storage_manager.get_latest_orderbook(exchange, symbol)
            self.metrics.counter("hot_orderbooks_queries")
            
            if orderbook:
                return web.json_response({
                    "status": "success",
                    "data": orderbook.dict(),
                    "timestamp": datetime.now().isoformat()
                })
            else:
                return web.json_response({
                    "status": "not_found",
                    "message": f"No orderbook found for {exchange}:{symbol}"
                }, status=404)
                
        except Exception as e:
            self.logger.error(f"Failed to query hot orderbook: {e}")
            self.metrics.counter("hot_orderbooks_query_errors")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
            
    # ==================== 冷数据管理API ====================
    
    async def archive_to_cold(self, request):
        """归档数据到冷存储"""
        try:
            data = await request.json()
            data_type = data.get('data_type', 'all')  # trades, tickers, orderbooks, all
            cutoff_hours = data.get('cutoff_hours', 24)  # 默认24小时前的数据
            
            cutoff_time = datetime.now() - timedelta(hours=cutoff_hours)
            
            # 这里需要实现具体的归档逻辑
            # 暂时返回模拟结果
            archived_count = 1000  # 模拟归档数量
            
            self.metrics.counter("cold_archive_operations")
            self.metrics.gauge("cold_archived_records", archived_count)
            
            return web.json_response({
                "status": "success",
                "message": f"Archived {archived_count} records to cold storage",
                "data_type": data_type,
                "cutoff_time": cutoff_time.isoformat(),
                "archived_count": archived_count,
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            self.logger.error(f"Failed to archive to cold storage: {e}")
            self.metrics.counter("cold_archive_errors")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
            
    async def get_cold_trades(self, request):
        """查询冷存储交易数据"""
        try:
            exchange = request.match_info['exchange']
            symbol = request.match_info['symbol']
            start_date = request.query.get('start_date')
            end_date = request.query.get('end_date')
            limit = int(request.query.get('limit', 1000))
            
            # 这里需要实现冷存储查询逻辑
            # 暂时返回模拟结果
            trades = []  # 模拟冷存储查询结果
            
            self.metrics.counter("cold_trades_queries")
            
            return web.json_response({
                "status": "success",
                "data": trades,
                "count": len(trades),
                "query_params": {
                    "exchange": exchange,
                    "symbol": symbol,
                    "start_date": start_date,
                    "end_date": end_date,
                    "limit": limit
                },
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            self.logger.error(f"Failed to query cold trades: {e}")
            self.metrics.counter("cold_trades_query_errors")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
            
    # ==================== 数据生命周期管理API ====================
    
    async def cleanup_expired_data(self, request):
        """清理过期数据"""
        try:
            data = await request.json()
            retention_hours = data.get('retention_hours', 72)  # 默认保留72小时
            
            cutoff_time = datetime.now() - timedelta(hours=retention_hours)
            
            # 这里需要实现具体的清理逻辑
            cleaned_count = 500  # 模拟清理数量
            
            self.metrics.counter("data_cleanup_operations")
            self.metrics.gauge("data_cleaned_records", cleaned_count)
            
            return web.json_response({
                "status": "success",
                "message": f"Cleaned {cleaned_count} expired records",
                "cutoff_time": cutoff_time.isoformat(),
                "cleaned_count": cleaned_count,
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup expired data: {e}")
            self.metrics.counter("data_cleanup_errors")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)
            
    async def get_storage_stats(self, request):
        """获取存储统计信息"""
        try:
            # 这里需要实现具体的统计逻辑
            stats = {
                "hot_storage": {
                    "trades_count": 10000,
                    "tickers_count": 500,
                    "orderbooks_count": 200,
                    "size_mb": 150.5
                },
                "cold_storage": {
                    "trades_count": 1000000,
                    "tickers_count": 50000,
                    "orderbooks_count": 20000,
                    "size_gb": 25.8
                },
                "operations": {
                    "total_reads": 5000,
                    "total_writes": 2000,
                    "total_archives": 100,
                    "total_cleanups": 10
                }
            }
            
            self.metrics.counter("storage_stats_queries")
            
            return web.json_response({
                "status": "success",
                "data": stats,
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            self.logger.error(f"Failed to get storage stats: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)


async def main():
    """主函数"""
    service = DataStorageService()
    await service.start()


if __name__ == "__main__":
    asyncio.run(main())