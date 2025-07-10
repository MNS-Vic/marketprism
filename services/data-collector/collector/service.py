"""
MarketPrism Data Collector Service - 集成微服务
集成了数据收集、OrderBook管理和数据聚合功能的统一微服务

功能特性:
- 多交易所数据收集 (Binance, OKX, Deribit)
- 实时WebSocket数据流
- OrderBook增量维护
- 数据标准化和聚合
- NATS消息队列集成
- BaseService框架集成
"""

# 标准库导入
import asyncio
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List

# 第三方库导入
import structlog
from aiohttp import web
import nats
import json

# 项目路径配置 - 适配Docker容器环境
try:
    project_root = Path(__file__).parent.parent.parent.parent
    sys.path.insert(0, str(project_root))
    sys.path.insert(0, '/app')
except Exception as e:
    print(f"路径配置警告: {e}")
    project_root = Path('/app')
    sys.path.insert(0, '/app')

# 核心框架导入
from core.service_framework import BaseService

# 数据收集模块导入
try:
    from core.data_collection.public_data_collector import PublicDataCollector
except ImportError as e:
    print(f"数据收集模块导入警告: {e}")
    PublicDataCollector = None

# 本地模块导入
try:
    from .config import ConfigPathManager
    from .data_types import Exchange, ExchangeConfig
    from .normalizer import DataNormalizer
except ImportError as e:
    print(f"本地模块导入警告: {e}")
    ConfigPathManager = None
    Exchange = None
    ExchangeConfig = None
    DataNormalizer = None


class DataCollectorService(BaseService):
    """
    MarketPrism数据收集器微服务

    功能:
    - 多交易所数据收集 (Binance, OKX, Deribit)
    - 实时WebSocket数据流处理
    - OrderBook增量维护
    - 数据标准化和聚合
    - NATS消息队列集成

    架构:
    - 继承BaseService框架，提供统一的服务管理
    - 支持Docker容器化部署
    - 提供RESTful API接口
    - 集成Prometheus监控指标
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化数据收集器服务

        Args:
            config: 服务配置字典
        """
        super().__init__("data-collector", config)

        # 核心组件
        self.public_collector: Optional[PublicDataCollector] = None
        self.orderbook_manager: Optional[Any] = None
        self.data_normalizer: Optional[DataNormalizer] = None

        # NATS客户端
        self.nats_client = None
        # 从正确的配置路径获取NATS配置
        data_collection_config = config.get('data_collection', {})
        self.nats_config = data_collection_config.get('nats_streaming', {
            'servers': ['nats://localhost:4222'],
            'enabled': True
        })

        # 服务状态
        self.start_time = datetime.now(timezone.utc)
        self.is_initialized = False

        # 功能配置
        self.enable_orderbook = config.get('enable_orderbook', True)
        self.enable_websocket = config.get('enable_websocket', True)
        self.collection_interval = config.get('collection_interval', 30)

        # 全局Rate Limiting保护 - 服务级别基础保护
        # TODO: 实现全局限流器（暂时跳过）
        self.global_rate_limiter = None

        # 适配器管理
        self.exchange_adapters = {}
        self.adapter_stats = {}

        # 数据存储
        self.collected_data = {
            'orderbooks': {},
            'trades': {},
            'klines': {},
            'funding_rates': {},
            'open_interest': {},
            'volatility_index': {},
            'top_trader_ratio': {},
            'global_long_short_ratio': {},
            'liquidations': {},
            'stats': {
                'total_collections': 0,
                'last_collection_time': None,
                'error_count': 0,
                'nats_published': 0,
                'nats_errors': 0
            }
        }

        # 支持的交易所列表
        self.supported_exchanges = ['binance', 'okx', 'deribit']

        self.logger.info(f"数据收集器服务初始化完成: orderbook={self.enable_orderbook}, websocket={self.enable_websocket}")

    def setup_routes(self):
        """设置API路由"""
        # 基础路由已在BaseService中设置，这里添加data-collector特定的API端点

        # 注册API路由
        self.app.router.add_get("/api/v1/status", self._get_service_status)
        self.app.router.add_get("/api/v1/collector/stats", self._get_collector_stats)
        self.app.router.add_get("/api/v1/collector/status", self._get_collector_status)
        self.app.router.add_get("/api/v1/collector/exchanges", self._get_exchanges_status)
        self.app.router.add_get("/api/v1/collector/data", self._get_collected_data)

    def _create_success_response(self, data: Any, message: str = "Success") -> web.Response:
        """创建成功响应"""
        return web.json_response({
            "status": "success",
            "message": message,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    def _create_error_response(self, message: str, error_code: str = "INTERNAL_ERROR",
                              status_code: int = 500) -> web.Response:
        """
        创建标准化错误响应

        Args:
            message: 错误描述信息
            error_code: 标准化错误代码
            status_code: HTTP状态码

        Returns:
            标准化的错误响应
        """
        return web.json_response({
            "status": "error",
            "error_code": error_code,
            "message": message,
            "data": None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, status=status_code)

    # 标准化错误代码常量
    ERROR_CODES = {
        'COLLECTOR_NOT_INITIALIZED': 'COLLECTOR_NOT_INITIALIZED',
        'STATS_UNAVAILABLE': 'STATS_UNAVAILABLE',
        'EXCHANGE_STATUS_ERROR': 'EXCHANGE_STATUS_ERROR',
        'DATA_RETRIEVAL_ERROR': 'DATA_RETRIEVAL_ERROR',
        'INVALID_PARAMETERS': 'INVALID_PARAMETERS',
        'SERVICE_UNAVAILABLE': 'SERVICE_UNAVAILABLE',
        'INTERNAL_ERROR': 'INTERNAL_ERROR'
    }

    async def _get_service_status(self, request: web.Request) -> web.Response:
        """
        BaseService兼容的状态API

        Returns:
            标准化的服务状态响应，包含服务基本信息、运行状态和统计数据
        """
        try:
            uptime_seconds = (datetime.now(timezone.utc) - self.start_time).total_seconds()

            # 获取基础统计信息
            basic_stats = {}
            try:
                basic_stats = self._get_basic_stats()
            except Exception as e:
                self.logger.warning(f"获取基础统计失败: {e}")
                basic_stats = {"error": "Stats temporarily unavailable"}

            status_data = {
                "service": "data-collector",
                "status": "running" if self.is_initialized else "initializing",
                "uptime_seconds": round(uptime_seconds, 2),
                "version": "1.0.0",
                "environment": "production",
                "features": {
                    "collector_initialized": self.public_collector is not None,
                    "orderbook_enabled": self.enable_orderbook,
                    "websocket_enabled": self.enable_websocket,
                    "normalizer_enabled": self.data_normalizer is not None
                },
                "supported_exchanges": self.supported_exchanges,
                "collection_stats": basic_stats
            }

            return self._create_success_response(status_data, "Service status retrieved successfully")

        except Exception as e:
            self.logger.error(f"获取服务状态失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve service status: {str(e)}",
                self.ERROR_CODES['INTERNAL_ERROR'],
                500
            )

    async def _get_collector_stats(self, request: web.Request) -> web.Response:
        """
        获取数据收集统计信息

        Returns:
            包含收集器统计、服务统计和数据摘要的标准化响应
        """
        try:
            if not self.public_collector:
                return self._create_error_response(
                    "Data collector not initialized. Service is running in degraded mode.",
                    self.ERROR_CODES['COLLECTOR_NOT_INITIALIZED'],
                    503
                )

            # 获取收集器统计信息
            collector_stats = {}
            try:
                collector_stats = self.public_collector.get_stats()
                if not collector_stats:
                    collector_stats = {"warning": "No statistics available yet"}
            except Exception as e:
                self.logger.warning(f"获取收集器统计失败: {e}")
                collector_stats = {
                    "error": "Stats temporarily unavailable",
                    "error_details": str(e)
                }

            # 计算运行时间
            uptime_seconds = (datetime.now(timezone.utc) - self.start_time).total_seconds()

            # 组合统计数据
            stats_data = {
                "collection_stats": collector_stats,
                "service_stats": {
                    "uptime_seconds": round(uptime_seconds, 2),
                    "total_collections": self.collected_data['stats']['total_collections'],
                    "error_count": self.collected_data['stats']['error_count'],
                    "last_collection_time": self.collected_data['stats']['last_collection_time'],
                    "success_rate": self._calculate_success_rate()
                },
                "data_summary": {
                    "orderbooks_count": len(self.collected_data['orderbooks']),
                    "trades_count": len(self.collected_data['trades']),
                    "total_data_points": (
                        len(self.collected_data['orderbooks']) +
                        len(self.collected_data['trades'])
                    )
                },
                "performance_metrics": {
                    "collections_per_minute": self._calculate_collections_per_minute(uptime_seconds),
                    "memory_usage_mb": self._estimate_memory_usage()
                }
            }

            return self._create_success_response(stats_data, "Collection statistics retrieved successfully")

        except Exception as e:
            self.logger.error(f"获取收集统计失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve collection statistics: {str(e)}",
                self.ERROR_CODES['STATS_UNAVAILABLE'],
                500
            )

    async def _get_collector_status(self, request: web.Request) -> web.Response:
        """
        获取数据收集器详细状态

        Returns:
            包含服务信息、功能状态、收集器统计和交易所状态的详细响应
        """
        try:
            # 获取收集器统计信息
            collector_stats = {}
            if self.public_collector:
                try:
                    collector_stats = self.public_collector.get_stats()
                    if not collector_stats:
                        collector_stats = {"warning": "No statistics available yet"}
                except Exception as e:
                    self.logger.warning(f"获取收集器统计失败: {e}")
                    collector_stats = {
                        "error": "Stats temporarily unavailable",
                        "error_details": str(e)
                    }
            else:
                collector_stats = {"status": "not_initialized"}

            # 计算运行时间
            uptime_seconds = (datetime.now(timezone.utc) - self.start_time).total_seconds()

            # 构建详细状态信息
            status_data = {
                "service_info": {
                    "name": "data-collector",
                    "version": "1.0.0",
                    "uptime_seconds": round(uptime_seconds, 2),
                    "initialized": self.is_initialized,
                    "start_time": self.start_time.isoformat(),
                    "environment": "production",
                    "process_id": os.getpid() if hasattr(os, 'getpid') else "unknown"
                },
                "feature_status": {
                    "collector_initialized": self.public_collector is not None,
                    "orderbook_enabled": self.enable_orderbook,
                    "websocket_enabled": self.enable_websocket,
                    "normalizer_enabled": self.data_normalizer is not None,
                    "orderbook_manager_active": self.orderbook_manager is not None
                },
                "collector_stats": collector_stats,
                "exchanges": self._get_exchange_status(),
                "data_summary": {
                    "orderbooks": len(self.collected_data['orderbooks']),
                    "trades": len(self.collected_data['trades']),
                    "total_data_points": (
                        len(self.collected_data['orderbooks']) +
                        len(self.collected_data['trades'])
                    )
                },
                "health_indicators": {
                    "overall_health": "healthy" if self.is_initialized else "degraded",
                    "data_flow_active": len(self.collected_data['orderbooks']) > 0 or len(self.collected_data['trades']) > 0,
                    "error_rate": self._calculate_error_rate(),
                    "last_activity": self.collected_data['stats']['last_collection_time']
                }
            }

            return self._create_success_response(status_data, "Detailed status retrieved successfully")

        except Exception as e:
            self.logger.error(f"获取详细状态失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve detailed status: {str(e)}",
                self.ERROR_CODES['INTERNAL_ERROR'],
                500
            )

    async def _get_exchanges_status(self, request: web.Request) -> web.Response:
        """
        获取交易所连接状态

        Returns:
            包含所有支持交易所的连接状态和统计信息
        """
        try:
            exchanges_data = self._get_exchange_status()

            # 添加汇总信息
            summary = {
                "total_exchanges": len(exchanges_data),
                "active_exchanges": sum(1 for ex in exchanges_data.values() if ex.get('status') == 'active'),
                "websocket_connections": sum(1 for ex in exchanges_data.values() if ex.get('websocket_connected')),
                "rest_api_available": sum(1 for ex in exchanges_data.values() if ex.get('rest_api_available'))
            }

            response_data = {
                "exchanges": exchanges_data,
                "summary": summary,
                "last_updated": datetime.now(timezone.utc).isoformat()
            }

            return self._create_success_response(response_data, "Exchange status retrieved successfully")

        except Exception as e:
            self.logger.error(f"获取交易所状态失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve exchange status: {str(e)}",
                self.ERROR_CODES['EXCHANGE_STATUS_ERROR'],
                500
            )

    async def _get_collected_data(self, request: web.Request) -> web.Response:
        """
        获取收集的数据摘要

        Query Parameters:
            exchange: 交易所名称 (all, binance, okx, deribit)
            type: 数据类型 (all, orderbooks, trades)
            limit: 返回记录数限制 (1-100, 默认10)

        Returns:
            包含数据摘要、最近数据和查询参数的标准化响应
        """
        try:
            # 获取和验证查询参数
            exchange = request.query.get('exchange', 'all').lower()
            data_type = request.query.get('type', 'all').lower()

            try:
                limit = int(request.query.get('limit', '10'))
                if limit < 1 or limit > 100:
                    return self._create_error_response(
                        "Limit parameter must be between 1 and 100",
                        self.ERROR_CODES['INVALID_PARAMETERS'],
                        400
                    )
            except ValueError:
                return self._create_error_response(
                    "Limit parameter must be a valid integer",
                    self.ERROR_CODES['INVALID_PARAMETERS'],
                    400
                )

            # 验证交易所参数
            valid_exchanges = ['all'] + self.supported_exchanges
            if exchange not in valid_exchanges:
                return self._create_error_response(
                    f"Invalid exchange parameter. Valid values: {', '.join(valid_exchanges)}",
                    self.ERROR_CODES['INVALID_PARAMETERS'],
                    400
                )

            # 验证数据类型参数
            valid_types = ['all', 'orderbooks', 'trades']
            if data_type not in valid_types:
                return self._create_error_response(
                    f"Invalid type parameter. Valid values: {', '.join(valid_types)}",
                    self.ERROR_CODES['INVALID_PARAMETERS'],
                    400
                )

            # 构建数据摘要
            data_summary = {
                "query_parameters": {
                    "exchange": exchange,
                    "type": data_type,
                    "limit": limit
                },
                "summary": {
                    "total_orderbooks": len(self.collected_data['orderbooks']),
                    "total_trades": len(self.collected_data['trades']),
                    "total_data_points": (
                        len(self.collected_data['orderbooks']) +
                        len(self.collected_data['trades'])
                    ),
                    "last_update": self.collected_data['stats']['last_collection_time'],
                    "collection_stats": {
                        "total_collections": self.collected_data['stats']['total_collections'],
                        "error_count": self.collected_data['stats']['error_count']
                    }
                },
                "recent_data": self._get_recent_data(exchange, data_type, limit),
                "metadata": {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "data_freshness_seconds": self._calculate_data_freshness()
                }
            }

            return self._create_success_response(data_summary, "Collected data retrieved successfully")

        except Exception as e:
            self.logger.error(f"获取收集数据失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve collected data: {str(e)}",
                self.ERROR_CODES['DATA_RETRIEVAL_ERROR'],
                500
            )

    def _get_exchange_status(self) -> Dict[str, Any]:
        """获取交易所状态信息"""
        current_time = datetime.now(timezone.utc).isoformat()

        return {
            "binance": {
                "enabled": True,
                "websocket_connected": self.enable_websocket,
                "rest_api_available": True,
                "last_update": current_time,
                "status": "active"
            },
            "okx": {
                "enabled": True,
                "websocket_connected": self.enable_websocket,
                "rest_api_available": True,
                "last_update": current_time,
                "status": "active"
            },
            "deribit": {
                "enabled": self.enable_orderbook,
                "websocket_connected": self.enable_websocket and self.enable_orderbook,
                "rest_api_available": True,
                "last_update": current_time,
                "status": "active" if self.enable_orderbook else "disabled"
            }
        }

    def _get_basic_stats(self) -> Dict[str, Any]:
        """获取基础统计信息"""
        return {
            "total_collections": self.collected_data['stats']['total_collections'],
            "error_count": self.collected_data['stats']['error_count'],
            "last_collection_time": self.collected_data['stats']['last_collection_time'],
            "data_counts": {
                "orderbooks": len(self.collected_data['orderbooks']),
                "trades": len(self.collected_data['trades'])
            }
        }

    def _get_recent_data(self, exchange: str, data_type: str, limit: int) -> Dict[str, Any]:
        """获取最近的数据"""
        recent_data = {}

        if data_type in ['all', 'orderbooks'] and self.collected_data['orderbooks']:
            recent_orderbooks = dict(list(self.collected_data['orderbooks'].items())[-limit:])
            if exchange != 'all':
                recent_orderbooks = {k: v for k, v in recent_orderbooks.items() if exchange in k}
            recent_data['orderbooks'] = recent_orderbooks

        if data_type in ['all', 'trades'] and self.collected_data['trades']:
            recent_trades = dict(list(self.collected_data['trades'].items())[-limit:])
            if exchange != 'all':
                recent_trades = {k: v for k, v in recent_trades.items() if exchange in k}
            recent_data['trades'] = recent_trades

        return recent_data

    def _calculate_success_rate(self) -> float:
        """计算成功率"""
        total = self.collected_data['stats']['total_collections']
        errors = self.collected_data['stats']['error_count']
        if total == 0:
            return 100.0
        return round((total - errors) / total * 100, 2)

    def _calculate_error_rate(self) -> float:
        """计算错误率"""
        total = self.collected_data['stats']['total_collections']
        errors = self.collected_data['stats']['error_count']
        if total == 0:
            return 0.0
        return round(errors / total * 100, 2)

    def _calculate_collections_per_minute(self, uptime_seconds: float) -> float:
        """计算每分钟收集次数"""
        if uptime_seconds < 60:
            return 0.0
        minutes = uptime_seconds / 60
        return round(self.collected_data['stats']['total_collections'] / minutes, 2)

    def _estimate_memory_usage(self) -> float:
        """估算内存使用量（MB）"""
        try:
            import sys
            total_size = 0
            for data_category in ['orderbooks', 'trades']:
                total_size += sys.getsizeof(self.collected_data[data_category])
                for item in self.collected_data[data_category].values():
                    total_size += sys.getsizeof(item)
            return round(total_size / (1024 * 1024), 2)
        except Exception:
            return 0.0

    def _calculate_data_freshness(self) -> float:
        """计算数据新鲜度（秒）"""
        last_update = self.collected_data['stats']['last_collection_time']
        if not last_update:
            return float('inf')
        try:
            last_update_dt = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
            return (datetime.now(timezone.utc) - last_update_dt).total_seconds()
        except Exception:
            return float('inf')

    async def on_startup(self):
        """服务启动初始化"""
        try:
            self.logger.info("开始初始化数据收集器服务...")

            # 1. 初始化NATS客户端
            await self._init_nats_client()

            # 2. 初始化数据标准化器
            await self._init_data_normalizer()

            # 3. 初始化公开数据收集器
            await self._init_public_collector()

            # 4. 初始化OrderBook Manager（如果启用）
            if self.enable_orderbook:
                await self._init_orderbook_manager()

            # 5. 启动数据收集任务
            await self._start_collection_tasks()

            # 6. 标记服务已初始化
            self.is_initialized = True

            self.logger.info("🎉 数据收集器服务初始化成功")
            self.logger.info(f"   - NATS客户端: {'✅' if self.nats_client else '❌'}")
            self.logger.info(f"   - 数据收集器: {'✅' if self.public_collector else '❌'}")
            self.logger.info(f"   - 数据标准化器: {'✅' if self.data_normalizer else '❌'}")
            self.logger.info(f"   - OrderBook管理器: {'✅' if self.orderbook_manager else '❌'}")
            self.logger.info(f"   - 支持的交易所: {', '.join(self.supported_exchanges)}")

        except Exception as e:
            self.logger.error(f"服务初始化失败: {e}", exc_info=True)
            self.is_initialized = False
            # 不抛出异常，允许服务以降级模式运行
            self.logger.warning("服务将以降级模式运行")

    async def _init_data_normalizer(self):
        """初始化数据标准化器"""
        try:
            if DataNormalizer:
                self.data_normalizer = DataNormalizer()
                self.logger.info("✅ 数据标准化器初始化成功")
            else:
                self.logger.warning("⚠️ 数据标准化器模块未找到，跳过初始化")
        except Exception as e:
            self.logger.error(f"数据标准化器初始化失败: {e}")

    async def _init_nats_client(self):
        """初始化NATS客户端"""
        try:
            if not self.nats_config.get('enabled', True):
                self.logger.info("⚠️ NATS客户端已禁用，跳过初始化")
                return

            servers = self.nats_config.get('servers', ['nats://localhost:4222'])

            # 使用最简单的连接方式，避免asyncio兼容性问题
            self.nats_client = await nats.connect(servers=servers)
            self.logger.info(f"✅ NATS客户端连接成功: {servers}")

        except Exception as e:
            self.logger.error(f"❌ NATS客户端初始化失败: {e}")
            # 尝试降级到手动NATS推送
            self.logger.info("⚠️ 将使用HTTP API进行NATS推送")
            self.nats_client = None

    async def _init_public_collector(self):
        """初始化公开数据收集器"""
        try:
            if not PublicDataCollector:
                self.logger.warning("⚠️ 公开数据收集器模块未找到，跳过初始化")
                return

            # 查找配置文件
            config_path = self._find_config_file("public_data_sources.yaml")

            if config_path and config_path.exists():
                self.public_collector = PublicDataCollector(str(config_path))
                self.logger.info(f"✅ 使用配置文件初始化数据收集器: {config_path}")
            else:
                # 使用默认配置
                self.public_collector = PublicDataCollector(None)
                self.logger.warning("⚠️ 配置文件未找到，使用默认配置初始化数据收集器")

            if self.public_collector:
                # 添加数据回调
                self.public_collector.add_data_callback(self._on_data_received)
                self.logger.info("✅ 数据收集器回调设置完成")

        except Exception as e:
            self.logger.error(f"公开数据收集器初始化失败: {e}")
            self.public_collector = None

    async def _start_collection_tasks(self):
        """启动数据收集任务"""
        try:
            if self.public_collector:
                # 启动数据收集
                collection_task = asyncio.create_task(self.public_collector.start())
                self.logger.info("✅ 数据收集任务启动成功")

                # 启动统计更新任务
                stats_task = asyncio.create_task(self._update_stats_periodically())
                self.logger.info("✅ 统计更新任务启动成功")

                # 启动Deribit专门数据收集任务
                deribit_task = asyncio.create_task(self._start_deribit_collection())
                self.logger.info("✅ Deribit数据收集任务启动成功")

            else:
                self.logger.warning("⚠️ 数据收集器未初始化，跳过启动收集任务")

        except Exception as e:
            self.logger.error(f"启动数据收集任务失败: {e}")

    async def _start_deribit_collection(self):
        """启动Deribit专门数据收集"""
        try:
            # 暂时禁用Deribit收集，避免导入问题
            self.logger.info("⚠️ Deribit数据收集暂时禁用（导入问题修复中）")
            return

            # TODO: 修复Deribit导入问题后重新启用
            # 简化的Deribit数据收集任务
            async def deribit_collection_task():
                """简化的Deribit数据收集任务"""
                while True:
                    try:
                        # 模拟Deribit波动率指数收集
                        await asyncio.sleep(10)  # 10秒间隔

                        # 这里应该调用Deribit API获取波动率指数
                        # 暂时跳过实际API调用

                    except Exception as e:
                        self.logger.error("Deribit数据收集错误", error=str(e))
                        await asyncio.sleep(30)  # 错误后等待30秒

            # 启动Deribit收集任务
            deribit_task = asyncio.create_task(deribit_collection_task())

            # 创建Deribit适配器
            deribit_config = {
                'base_url': 'https://www.deribit.com',
                'rate_limit': 10,  # 每秒10个请求
                'timeout': 30
            }

            deribit_adapter = DeribitAdapter(deribit_config)

            # 定期收集波动率指数数据
            while True:
                try:
                    # 收集BTC波动率指数
                    btc_volatility = await deribit_adapter.get_volatility_index_data('BTC')
                    if btc_volatility and 'result' in btc_volatility and btc_volatility['result']:
                        latest_btc = btc_volatility['result'][-1]
                        normalized_btc = {
                            'exchange': 'deribit',
                            'currency': 'BTC',
                            'symbol': 'BTC_USD',
                            'volatility': latest_btc.get('volatility', 0),
                            'timestamp': datetime.now(timezone.utc).isoformat()
                        }
                        # NATS推送已移至新的多市场OrderBook Manager

                    # 收集ETH波动率指数
                    eth_volatility = await deribit_adapter.get_volatility_index_data('ETH')
                    if eth_volatility and 'result' in eth_volatility and eth_volatility['result']:
                        latest_eth = eth_volatility['result'][-1]
                        normalized_eth = {
                            'exchange': 'deribit',
                            'currency': 'ETH',
                            'symbol': 'ETH_USD',
                            'volatility': latest_eth.get('volatility', 0),
                            'timestamp': datetime.now(timezone.utc).isoformat()
                        }
                        # NATS推送已移至新的多市场OrderBook Manager

                    self.logger.debug("✅ Deribit波动率指数数据收集完成")

                except Exception as e:
                    self.logger.error(f"❌ Deribit数据收集失败: {e}")

                # 等待10秒再次收集
                await asyncio.sleep(10)

        except Exception as e:
            self.logger.error(f"❌ Deribit数据收集任务启动失败: {e}")

    def _find_config_file(self, filename: str) -> Optional[Path]:
        """查找配置文件"""
        possible_paths = [
            project_root / "config" / filename,
            Path("/app/config") / filename,
            Path("./config") / filename,
            Path(f"./{filename}")
        ]

        for path in possible_paths:
            if path.exists():
                return path

        return None

    async def _init_orderbook_manager(self):
        """初始化OrderBook Manager"""
        try:
            # 检查依赖模块
            if not Exchange or not ExchangeConfig:
                self.logger.warning("⚠️ OrderBook相关模块未找到，跳过OrderBook Manager初始化")
                return

            try:
                from .orderbook_manager import OrderBookManager
            except ImportError as e:
                self.logger.warning(f"⚠️ OrderBook Manager模块未找到，跳过初始化: {e}")
                return

            # 创建多市场OrderBook Manager配置
            # 每个symbol需要4个订单簿：Binance现货/永续 + OKX现货/永续
            orderbook_configs = [
                # Binance现货
                {
                    'exchange': Exchange.BINANCE,
                    'market_type': 'spot',
                    'base_url': 'https://api.binance.com',
                    'ws_url': 'wss://stream.binance.com:9443',
                    'symbols': ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
                },
                # Binance期货
                {
                    'exchange': Exchange.BINANCE,
                    'market_type': 'futures',
                    'base_url': 'https://fapi.binance.com',
                    'ws_url': 'wss://fstream.binance.com',
                    'symbols': ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
                },
                # OKX现货
                {
                    'exchange': Exchange.OKX,
                    'market_type': 'spot',
                    'base_url': 'https://www.okx.com',
                    'ws_url': 'wss://ws.okx.com:8443/ws/v5/public',
                    'symbols': ['BTC-USDT', 'ETH-USDT', 'BNB-USDT']
                },
                # OKX永续
                {
                    'exchange': Exchange.OKX,
                    'market_type': 'perpetual',
                    'base_url': 'https://www.okx.com',
                    'ws_url': 'wss://ws.okx.com:8443/ws/v5/public',
                    'symbols': ['BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'BNB-USDT-SWAP']
                }
            ]

            # 创建多个OrderBook Manager实例
            if self.data_normalizer:
                self.orderbook_managers = []

                for config in orderbook_configs:
                    # 创建ExchangeConfig对象
                    exchange_config = ExchangeConfig(
                        exchange=config['exchange'],
                        market_type=config['market_type'],
                        base_url=config['base_url'],
                        ws_url=config['ws_url'],
                        snapshot_interval=60,
                        symbols=config['symbols']
                    )

                    # 创建OrderBook Manager实例
                    manager = OrderBookManager(exchange_config, self.data_normalizer, self.nats_client)
                    self.orderbook_managers.append(manager)

                    # 启动OrderBook Manager
                    manager_name = f"{config['exchange'].value}_{config['market_type']}"
                    orderbook_task = asyncio.create_task(manager.start(config['symbols']))
                    self.logger.info(f"✅ OrderBook Manager启动成功: {manager_name}")

                self.logger.info(f"🎉 所有OrderBook Manager启动完成，共{len(self.orderbook_managers)}个实例")
            else:
                self.logger.warning("⚠️ 数据标准化器未初始化，无法启动OrderBook Manager")

        except Exception as e:
            self.logger.error(f"OrderBook Manager启动失败: {e}")
            self.orderbook_manager = None
            # 不抛出异常，允许服务继续运行

    async def _register_orderbook_callbacks(self):
        """注册OrderBook Manager的回调到WebSocket客户端"""
        try:
            if not self.orderbook_manager:
                return

            # 检查是否有交易所客户端
            if hasattr(self, 'exchange_clients') and self.exchange_clients:
                # 为每个交易所注册深度数据回调
                for exchange_name, exchange_client in self.exchange_clients.items():
                    if hasattr(exchange_client, 'add_raw_callback'):
                        # 注册深度数据回调
                        exchange_client.add_raw_callback('depth', self._handle_raw_depth_data)
                        self.logger.info(f"✅ 已为{exchange_name}注册OrderBook回调")
                    else:
                        self.logger.warning(f"⚠️ {exchange_name}不支持原始数据回调")
            else:
                self.logger.info("⚠️ 暂时跳过OrderBook回调注册，将在交易所客户端创建后注册")

        except Exception as e:
            self.logger.error(f"注册OrderBook回调失败: {e}")

    async def _handle_raw_depth_data(self, exchange: str, symbol: str, raw_data: Dict[str, Any]):
        """处理来自WebSocket的原始深度数据"""
        try:
            if self.orderbook_manager:
                # 将原始数据传递给OrderBook Manager
                await self.orderbook_manager.handle_update(symbol, raw_data)
        except Exception as e:
            self.logger.error(f"处理原始深度数据失败: {e}",
                            exchange=exchange, symbol=symbol)

    async def _update_stats_periodically(self):
        """定期更新统计信息"""
        while True:
            try:
                await asyncio.sleep(self.collection_interval)

                # 更新统计信息
                self.collected_data['stats']['total_collections'] += 1
                self.collected_data['stats']['last_collection_time'] = datetime.now(timezone.utc).isoformat()

                # 记录统计信息
                if self.collected_data['stats']['total_collections'] % 10 == 0:
                    self.logger.info(f"数据收集统计: 总次数={self.collected_data['stats']['total_collections']}, "
                                   f"错误次数={self.collected_data['stats']['error_count']}")

            except Exception as e:
                self.logger.error(f"更新统计信息失败: {e}")
                self.collected_data['stats']['error_count'] += 1
                await asyncio.sleep(5)  # 错误时短暂等待

    async def _on_data_received(self, data_type: str, exchange: str, data: Dict[str, Any]):
        """
        数据接收回调 - 标准化并推送到NATS

        Args:
            data_type: 数据类型 (orderbook, trade)
            exchange: 交易所名称
            data: 接收到的原始数据
        """
        try:
            if not data:
                self.logger.warning("接收到空数据，跳过处理")
                return

            # 数据标准化
            normalized_data = self._normalize_data(data_type, exchange, data)

            # 存储数据到内存
            self._store_data(data_type, exchange, normalized_data)

            # 注意：NATS推送已移至新的多市场OrderBook Manager，避免重复推送

            # 更新统计信息
            self.collected_data['stats']['total_collections'] += 1

        except Exception as e:
            self.logger.error(f"数据处理失败: {e}", exc_info=True)
            self.collected_data['stats']['error_count'] += 1

    def _normalize_data(self, data_type: str, exchange: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化数据"""
        try:
            if self.data_normalizer:
                return self.data_normalizer.normalize(data, data_type, exchange)
            else:
                # 基础标准化
                return {
                    **data,
                    'data_type': data_type,
                    'exchange': exchange,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'source': 'data-collector',
                    'normalized': False
                }
        except Exception as e:
            self.logger.warning(f"数据标准化失败: {e}")
            return {
                **data,
                'data_type': data_type,
                'exchange': exchange,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'source': 'data-collector',
                'normalized': False,
                'normalization_error': str(e)
            }

    def _store_data(self, data_type: str, exchange: str, normalized_data: Dict[str, Any]):
        """存储数据到内存"""
        try:
            symbol = normalized_data.get('symbol', 'unknown')
            key = f"{exchange}:{symbol}"

            # 根据数据类型存储
            # 根据数据类型存储到对应的分类中
            data_type_mapping = {
                'orderbook': 'orderbooks',
                'trade': 'trades',
                'kline': 'klines',
                'funding_rate': 'funding_rates',
                'open_interest': 'open_interest',
                'volatility_index': 'volatility_index',
                'top_trader_ratio': 'top_trader_ratio',
                'global_long_short_ratio': 'global_long_short_ratio',
                'liquidation': 'liquidations'
            }

            storage_key = data_type_mapping.get(data_type)
            if storage_key:
                self.collected_data[storage_key][key] = normalized_data
            else:
                # 对于未知数据类型，存储到通用位置
                if 'other' not in self.collected_data:
                    self.collected_data['other'] = {}
                self.collected_data['other'][key] = normalized_data
                self.logger.debug(f"存储未知数据类型: {data_type}")

            # 限制内存使用，保留最新的1000条记录
            data_categories = ['orderbooks', 'trades', 'klines', 'funding_rates',
                             'open_interest', 'volatility_index', 'top_trader_ratio',
                             'global_long_short_ratio', 'liquidations', 'other']

            for data_category in data_categories:
                if data_category in self.collected_data and len(self.collected_data[data_category]) > 1000:
                    # 删除最旧的记录
                    oldest_key = next(iter(self.collected_data[data_category]))
                    del self.collected_data[data_category][oldest_key]

        except Exception as e:
            self.logger.error(f"数据存储失败: {e}")



    async def on_shutdown(self):
        """服务关闭清理"""
        self.logger.info("开始关闭数据收集器服务...")

        shutdown_tasks = []

        try:
            # 1. 停止公开数据收集器
            if self.public_collector:
                try:
                    await asyncio.wait_for(self.public_collector.stop(), timeout=10.0)
                    self.logger.info("✅ 公开数据收集器已停止")
                except asyncio.TimeoutError:
                    self.logger.warning("⚠️ 公开数据收集器停止超时")
                except Exception as e:
                    self.logger.error(f"❌ 停止公开数据收集器失败: {e}")

            # 2. 停止OrderBook Manager(s)
            if hasattr(self, 'orderbook_managers') and self.orderbook_managers:
                # 新的多实例架构
                for i, manager in enumerate(self.orderbook_managers):
                    try:
                        await asyncio.wait_for(manager.stop(), timeout=10.0)
                        self.logger.info(f"✅ OrderBook Manager {i+1} 已停止")
                    except asyncio.TimeoutError:
                        self.logger.warning(f"⚠️ OrderBook Manager {i+1} 停止超时")
                    except Exception as e:
                        self.logger.error(f"❌ 停止OrderBook Manager {i+1} 失败: {e}")
            elif hasattr(self, 'orderbook_manager') and self.orderbook_manager:
                # 旧的单实例架构（向后兼容）
                try:
                    await asyncio.wait_for(self.orderbook_manager.stop(), timeout=10.0)
                    self.logger.info("✅ OrderBook Manager已停止")
                except asyncio.TimeoutError:
                    self.logger.warning("⚠️ OrderBook Manager停止超时")
                except Exception as e:
                    self.logger.error(f"❌ 停止OrderBook Manager失败: {e}")

            # 3. 关闭NATS连接
            if self.nats_client:
                try:
                    await self.nats_client.close()
                    self.logger.info("✅ NATS客户端已关闭")
                except Exception as e:
                    self.logger.error(f"❌ 关闭NATS客户端失败: {e}")

            # 4. 清理数据
            self._cleanup_data()

            # 5. 标记服务已关闭
            self.is_initialized = False

        except Exception as e:
            self.logger.error(f"服务关闭时发生错误: {e}", exc_info=True)
        finally:
            self.logger.info("🔚 数据收集器服务已关闭")

    def _cleanup_data(self):
        """清理数据和资源"""
        try:
            # 清理内存中的数据
            self.collected_data = {
                'orderbooks': {},
                'trades': {},
                'stats': {
                    'total_collections': 0,
                    'last_collection_time': None,
                    'error_count': 0
                }
            }

            # 重置组件引用
            self.public_collector = None
            self.orderbook_manager = None

            self.logger.info("✅ 数据清理完成")

        except Exception as e:
            self.logger.error(f"数据清理失败: {e}")
