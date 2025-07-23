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

# 🔧 新增：NATS订阅支持
import nats
from nats.js import JetStreamContext

# 确保能正确找到项目根目录并添加到sys.path
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.service_framework import BaseService
from core.storage.unified_storage_manager import UnifiedStorageManager
from core.storage.types import NormalizedTrade, NormalizedTicker, NormalizedOrderBook

class DataStorageService(BaseService):
    """数据存储微服务 - 整合NATS订阅和HTTP API"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("data-storage-service", config)
        self.storage_manager: Optional[UnifiedStorageManager] = None

        # 🔧 新增：NATS订阅支持
        self.nats_client: Optional[nats.NATS] = None
        self.jetstream: Optional[JetStreamContext] = None
        self.subscriptions = []
        self.nats_enabled = config.get('nats', {}).get('enabled', True)

        # 统计信息
        self.nats_stats = {
            'messages_received': 0,
            'messages_stored': 0,
            'storage_errors': 0,
            'start_time': None
        }

    def setup_routes(self):
        """设置API路由"""
        # 添加标准状态API路由
        self.app.router.add_get('/api/v1/storage/status', self.get_storage_status)
        
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
            # 初始化存储管理器
            self.storage_manager = UnifiedStorageManager()
            await self.storage_manager.initialize()
            self.logger.info("✅ UnifiedStorageManager初始化成功")

            # 🔧 新增：初始化NATS订阅
            if self.nats_enabled:
                await self._initialize_nats_subscription()
            else:
                self.logger.info("📡 NATS订阅已禁用，仅提供HTTP API服务")

        except Exception as e:
            self.logger.warning(f"⚠️ 存储管理器初始化失败，运行在降级模式: {e}")
            self.storage_manager = None


    async def on_shutdown(self):
        """服务停止清理"""
        # 🔧 新增：清理NATS订阅
        if self.subscriptions:
            for sub in self.subscriptions:
                await sub.unsubscribe()
            self.logger.info("📡 NATS订阅已清理")

        if self.nats_client:
            await self.nats_client.close()
            self.logger.info("📡 NATS连接已关闭")

        if self.storage_manager and hasattr(self.storage_manager, 'close'):
            try:
                await self.storage_manager.close()
                self.logger.info("💾 存储管理器已关闭")
            except Exception as e:
                self.logger.warning(f"⚠️ 存储管理器关闭失败: {e}")
        else:
            self.logger.info("💾 存储服务已停止 (降级模式)")

    # ==================== NATS订阅方法 ====================

    async def _initialize_nats_subscription(self):
        """初始化NATS订阅"""
        try:
            nats_config = self.config.get('nats', {})
            servers = nats_config.get('servers', ['nats://localhost:4222'])

            # 连接NATS
            self.nats_client = await nats.connect(
                servers=servers,
                name="data-storage-service",
                error_cb=self._nats_error_handler,
                closed_cb=self._nats_closed_handler,
                reconnected_cb=self._nats_reconnected_handler
            )

            # 获取JetStream上下文
            self.jetstream = self.nats_client.jetstream()
            self.logger.info("✅ NATS JetStream连接成功", servers=servers)

            # 订阅数据流
            await self._subscribe_to_data_streams()

            self.nats_stats['start_time'] = datetime.now()
            self.logger.info("✅ NATS数据流订阅完成")

        except Exception as e:
            self.logger.error("❌ NATS订阅初始化失败", error=str(e))
            self.nats_enabled = False

    async def _subscribe_to_data_streams(self):
        """订阅数据流"""
        try:
            # 订阅订单簿数据
            orderbook_sub = await self.jetstream.subscribe(
                "orderbook-data.>",
                cb=self._handle_orderbook_message,
                durable="storage-service-orderbook-consumer",
                stream="MARKET_DATA"
            )
            self.subscriptions.append(orderbook_sub)

            # 订阅交易数据
            trade_sub = await self.jetstream.subscribe(
                "trade-data.>",
                cb=self._handle_trade_message,
                durable="storage-service-trade-consumer",
                stream="MARKET_DATA"
            )
            self.subscriptions.append(trade_sub)

            # 订阅其他数据类型
            other_subjects = [
                "funding-rate.>",
                "open-interest.>",
                "liquidation-orders.>",
                "kline-data.>"
            ]

            for subject in other_subjects:
                sub = await self.jetstream.subscribe(
                    subject,
                    cb=self._handle_generic_message,
                    durable=f"storage-service-{subject.split('.')[0]}-consumer",
                    stream="MARKET_DATA"
                )
                self.subscriptions.append(sub)

            self.logger.info("📡 数据流订阅成功", subscriptions=len(self.subscriptions))

        except Exception as e:
            self.logger.error("❌ 数据流订阅失败", error=str(e))

    async def _handle_orderbook_message(self, msg):
        """处理订单簿消息"""
        try:
            if not self.storage_manager:
                await msg.ack()  # 降级模式下直接确认
                return

            # 解析消息
            data = json.loads(msg.data.decode())

            # 存储到数据库
            await self.storage_manager.store_orderbook(data)

            # 确认消息
            await msg.ack()

            # 更新统计
            self.nats_stats['messages_received'] += 1
            self.nats_stats['messages_stored'] += 1

            self.logger.debug("📊 订单簿数据已存储",
                            exchange=data.get('exchange'),
                            symbol=data.get('symbol'))

        except Exception as e:
            self.logger.error("❌ 订单簿消息处理失败", error=str(e))
            self.nats_stats['storage_errors'] += 1
            # 不确认消息，让它重新投递

    async def _handle_trade_message(self, msg):
        """处理交易消息"""
        try:
            if not self.storage_manager:
                await msg.ack()  # 降级模式下直接确认
                return

            # 解析消息
            data = json.loads(msg.data.decode())

            # 存储到数据库
            await self.storage_manager.store_trade(data)

            # 确认消息
            await msg.ack()

            # 更新统计
            self.nats_stats['messages_received'] += 1
            self.nats_stats['messages_stored'] += 1

            self.logger.debug("💰 交易数据已存储",
                            exchange=data.get('exchange'),
                            symbol=data.get('symbol'),
                            price=data.get('price'))

        except Exception as e:
            self.logger.error("❌ 交易消息处理失败", error=str(e))
            self.nats_stats['storage_errors'] += 1

    async def _handle_generic_message(self, msg):
        """处理通用消息"""
        try:
            # 解析消息
            data = json.loads(msg.data.decode())

            # 根据主题确定数据类型
            subject = msg.subject
            if "funding-rate" in subject:
                # TODO: 实现资金费率存储
                pass
            elif "open-interest" in subject:
                # TODO: 实现持仓量存储
                pass
            # ... 其他数据类型

            # 确认消息
            await msg.ack()

            self.nats_stats['messages_received'] += 1

        except Exception as e:
            self.logger.error("❌ 通用消息处理失败", error=str(e))
            self.nats_stats['storage_errors'] += 1

    async def _nats_error_handler(self, e):
        """NATS错误处理"""
        self.logger.error("📡 NATS错误", error=str(e))

    async def _nats_closed_handler(self):
        """NATS连接关闭处理"""
        self.logger.warning("📡 NATS连接已关闭")

    async def _nats_reconnected_handler(self):
        """NATS重连处理"""
        self.logger.info("📡 NATS重连成功")

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

    async def get_storage_status(self, request: web.Request) -> web.Response:
        """获取存储服务状态"""
        try:
            status_info = {
                "status": "success",
                "service": "data-storage-service",
                "timestamp": datetime.now().isoformat(),
                "storage_manager": {
                    "initialized": self.storage_manager is not None,
                    "mode": "normal" if self.storage_manager else "degraded"
                },
                # 🔧 新增：NATS订阅状态
                "nats_subscription": {
                    "enabled": self.nats_enabled,
                    "connected": self.nats_client is not None and not self.nats_client.is_closed,
                    "subscriptions": len(self.subscriptions),
                    "stats": self.nats_stats.copy()
                }
            }
            
            if self.storage_manager:
                try:
                    # 尝试获取基本统计信息
                    stats = await self.storage_manager.get_stats()
                    status_info["storage_stats"] = stats
                except Exception as e:
                    status_info["storage_stats"] = {"error": str(e)}
            
            return web.json_response(status_info)
        except Exception as e:
            self.logger.error(f"Failed to get storage status: {e}", exc_info=True)
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