"""
MarketPrism订单簿管理系统HTTP服务器

提供健康检查、监控指标和API端点。
"""

import asyncio
import json
import time
import tracemalloc
import gc
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from aiohttp import web, web_request
import structlog
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from .health_check import HealthChecker
from .metrics import MetricsCollector

logger = structlog.get_logger(__name__)


class HTTPServer:
    """HTTP服务器类"""
    
    def __init__(self, 
                 health_check_port: int = 8080,
                 metrics_port: int = 8081,
                 health_checker: Optional[HealthChecker] = None,
                 metrics_collector: Optional[MetricsCollector] = None):
        self.health_check_port = health_check_port
        self.metrics_port = metrics_port
        self.health_checker = health_checker or HealthChecker()
        self.metrics_collector = metrics_collector
        self.logger = structlog.get_logger(__name__)
        
        # 服务器实例
        self.health_app = None
        self.metrics_app = None
        self.health_runner = None
        self.metrics_runner = None
        
        # 外部依赖引用
        self.nats_client = None
        self.websocket_connections = None
        self.orderbook_manager = None
        self.orderbook_managers = None
        self.manager_launcher = None  # 新增：ParallelManagerLauncher 引用

        # 启动时间
        self.start_time = time.time()

        # tracemalloc 快照存储
        self.tracemalloc_snapshots = []
        self.tracemalloc_enabled = False

    def set_dependencies(self,
                        nats_client=None,
                        websocket_connections=None,
                        orderbook_manager=None,
                        orderbook_managers=None,
                        memory_manager=None,
                        manager_launcher=None):
        """设置外部依赖"""
        self.nats_client = nats_client
        self.websocket_connections = websocket_connections
        self.orderbook_manager = orderbook_manager
        self.orderbook_managers = orderbook_managers
        self.memory_manager = memory_manager
        self.manager_launcher = manager_launcher  # 新增：保存 manager_launcher 引用

    async def health_handler(self, request: web_request.Request) -> web.Response:
        """健康检查处理器（增强：按交易所×数据类型的覆盖与新鲜度）"""
        try:
            # 🔧 修复：使用 manager_launcher 中的 OrderBook 管理器进行健康检查
            # 而不是使用单个 orderbook_manager（可能已经停止更新）
            orderbook_manager_to_check = None
            if self.manager_launcher and hasattr(self.manager_launcher, 'active_managers'):
                # 从 manager_launcher 中获取第一个 OrderBook 管理器
                # ManagerType 定义在 main.py 中，需要动态导入
                try:
                    # 尝试从 main 模块导入 ManagerType
                    import sys
                    if 'main' in sys.modules:
                        ManagerType = sys.modules['main'].ManagerType
                    else:
                        # 如果 main 模块未加载，尝试导入
                        from main import ManagerType

                    for exchange_name, managers in self.manager_launcher.active_managers.items():
                        if ManagerType.ORDERBOOK in managers:
                            orderbook_manager_to_check = managers[ManagerType.ORDERBOOK]
                            break
                except (ImportError, AttributeError) as e:
                    self.logger.warning(f"无法导入 ManagerType: {e}")

            if not orderbook_manager_to_check and self.orderbook_manager:
                # 向后兼容：如果没有 manager_launcher，使用旧的 orderbook_manager
                orderbook_manager_to_check = self.orderbook_manager

            # 执行基础健康检查
            health_report = await self.health_checker.perform_comprehensive_health_check(
                nats_client=self.nats_client,
                websocket_connections=self.websocket_connections,
                orderbook_manager=orderbook_manager_to_check
            )

            # 覆盖明细：整合 orderbook 管理器信息 + 采集层“最后成功时间”快照
            coverage: Dict[str, Dict[str, Any]] = {}

            # 1) orderbook：保持现有逻辑（包含 active_symbols）
            try:
                coverage["orderbook"] = {}
                managers = self.orderbook_managers or {}
                for ex_name, mgr in managers.items():
                    states = getattr(mgr, 'orderbook_states', {}) or {}
                    active = len(states)
                    # 计算该交易所最近一次更新时间
                    last_ts = None
                    for _, state in states.items():
                        ts = getattr(state, 'last_snapshot_time', None)
                        if ts is None:
                            continue
                        if getattr(ts, 'tzinfo', None) is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        if (last_ts is None) or (ts > last_ts):
                            last_ts = ts
                    age_sec = None
                    last_ts_iso = None
                    if last_ts is not None:
                        age_sec = (datetime.now(timezone.utc) - last_ts).total_seconds()
                        last_ts_iso = last_ts.isoformat()
                    status = 'unhealthy'
                    if active > 0:
                        status = 'healthy' if (age_sec is not None and age_sec < 60) else 'degraded'
                    coverage["orderbook"][ex_name] = {
                        "active_symbols": active,
                        "last_success_ts": last_ts_iso,
                        "age_seconds": age_sec,
                        "status": status
                    }
            except Exception:
                pass

            # 2) 其他数据类型：来源于 MetricsCollector 的“最后成功”快照
            try:
                if self.metrics_collector and hasattr(self.metrics_collector, 'get_last_success_snapshot'):
                    snapshot = self.metrics_collector.get_last_success_snapshot() or {}
                    # 阈值（秒）：高频60s；低频8h；事件（liquidation）1h
                    thresholds = {
                        'trade': 60,
                        'orderbook': 60,
                        'funding_rate': 8 * 3600,
                        'open_interest': 8 * 3600,
                        'volatility_index': 8 * 3600,
                        'lsr_top_position': 8 * 3600,
                        'lsr_all_account': 8 * 3600,
                        'liquidation': 3600,
                    }
                    for dt, ex_map in snapshot.items():
                        if dt not in coverage:
                            coverage[dt] = {}
                        for ex_name, ts in ex_map.items():
                            try:
                                ts_dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
                                age_sec = (datetime.now(timezone.utc) - ts_dt).total_seconds()
                                status = 'healthy' if age_sec < thresholds.get(dt, 3600) else 'degraded'
                                coverage[dt][ex_name] = {
                                    "last_success_ts": ts_dt.isoformat(),
                                    "age_seconds": age_sec,
                                    "status": status
                                }
                            except Exception:
                                pass
            except Exception:
                pass

            # 合并覆盖信息
            health_report["coverage"] = coverage

            # 确定HTTP状态码（保持与基础一致）并增加冷启动宽限期
            status = health_report.get("status")
            uptime = health_report.get("uptime") or health_report.get("metrics", {}).get("uptime_seconds")
            try:
                grace_sec = int((__import__('os').getenv('HEALTH_GRACE_SECONDS') or '120').strip())
            except Exception:
                grace_sec = 120
            if status != "healthy" and isinstance(uptime, (int, float)) and uptime < grace_sec:
                health_report["grace"] = {"applied": True, "uptime": uptime, "grace_seconds": grace_sec}
                status_code = 200
            else:
                # degraded 状态也视为可接受（部分数据源暂时中断不影响整体可用性）
                status_code = 200 if status in ["healthy", "degraded"] else 503
            return web.json_response(health_report, status=status_code)

        except Exception as e:
            self.logger.error("健康检查处理失败", error=str(e), exc_info=True)
            error_response = {
                "status": "unhealthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": f"Health check handler failed: {str(e)}"
            }
            return web.json_response(error_response, status=503)
    
    async def metrics_handler(self, request: web_request.Request) -> web.Response:
        """Prometheus指标处理器"""
        try:
            # 更新指标
            if self.metrics_collector:
                await self.metrics_collector.update_metrics(
                    nats_client=self.nats_client,
                    websocket_connections=self.websocket_connections,
                    orderbook_manager=self.orderbook_manager,
                    orderbook_managers=self.orderbook_managers,
                    memory_manager=getattr(self, 'memory_manager', None)
                )

            # 生成Prometheus格式的指标
            metrics_data = generate_latest()
            
            return web.Response(
                body=metrics_data,
                headers={"Content-Type": CONTENT_TYPE_LATEST}
            )
            
        except Exception as e:
            self.logger.error("指标处理失败", error=str(e), exc_info=True)
            
            # 返回基本的错误指标
            error_metrics = f"""# HELP marketprism_metrics_error Metrics collection error
# TYPE marketprism_metrics_error gauge
marketprism_metrics_error 1
# HELP marketprism_uptime_seconds System uptime in seconds
# TYPE marketprism_uptime_seconds gauge
marketprism_uptime_seconds {time.time() - self.start_time}
"""
            
            return web.Response(
                body=error_metrics,
                headers={"Content-Type": CONTENT_TYPE_LATEST}
            )
    
    async def status_handler(self, request: web_request.Request) -> web.Response:
        """系统状态处理器"""
        try:
            # 获取查询参数
            detailed = request.query.get('detailed', 'false').lower() == 'true'
            
            # 基础状态信息
            status_info = {
                "service": "MarketPrism OrderBook Manager",
                "version": "1.0.0",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "uptime": time.time() - self.start_time,
                "status": "running"
            }
            
            if detailed:
                # 详细状态信息
                health_report = await self.health_checker.perform_comprehensive_health_check(
                    nats_client=self.nats_client,
                    websocket_connections=self.websocket_connections,
                    orderbook_manager=self.orderbook_manager
                )
                
                status_info.update({
                    "detailed_health": health_report,
                    "active_symbols": len(getattr(self.orderbook_manager, 'orderbook_states', {})) if self.orderbook_manager else 0,
                    "nats_connected": (self.nats_client.is_connected if self.nats_client else False),
                    "websocket_connections": len(self.websocket_connections) if self.websocket_connections else 0
                })
            
            return web.json_response(status_info)
            
        except Exception as e:
            self.logger.error("状态处理失败", error=str(e), exc_info=True)
            
            error_response = {
                "service": "MarketPrism OrderBook Manager",
                "status": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            }
            
            return web.json_response(error_response, status=500)
    
    async def ping_handler(self, request: web_request.Request) -> web.Response:
        """简单ping处理器"""
        return web.json_response({
            "pong": True,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    async def version_handler(self, request: web_request.Request) -> web.Response:
        """版本信息处理器"""
        version_info = {
            "service": "MarketPrism OrderBook Manager",
            "version": "1.0.0",
            "build_time": "2025-07-03T12:00:00Z",
            "git_commit": "latest",
            "python_version": "3.11+",
            "features": [
                "Real-time OrderBook Management",
                "Multi-Exchange Support",
                "NATS Message Publishing",
                "Prometheus Metrics",
                "Health Monitoring"
            ]
        }

        return web.json_response(version_info)

    async def tracemalloc_start_handler(self, request: web_request.Request) -> web.Response:
        """启动 tracemalloc 追踪"""
        try:
            if self.tracemalloc_enabled:
                return web.json_response({
                    "status": "already_running",
                    "message": "tracemalloc is already enabled"
                })

            # 启动 tracemalloc
            tracemalloc.start()
            self.tracemalloc_enabled = True
            self.tracemalloc_snapshots = []

            self.logger.info("tracemalloc 已启动")

            return web.json_response({
                "status": "started",
                "message": "tracemalloc tracking started",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

        except Exception as e:
            self.logger.error("启动 tracemalloc 失败", error=str(e), exc_info=True)
            return web.json_response({
                "status": "error",
                "error": str(e)
            }, status=500)

    async def tracemalloc_snapshot_handler(self, request: web_request.Request) -> web.Response:
        """获取当前内存快照"""
        try:
            if not self.tracemalloc_enabled:
                return web.json_response({
                    "status": "not_enabled",
                    "message": "tracemalloc is not enabled. Call /tracemalloc/start first"
                }, status=400)

            # 强制 GC
            gc.collect()

            # 获取快照
            snapshot = tracemalloc.take_snapshot()
            self.tracemalloc_snapshots.append({
                "snapshot": snapshot,
                "timestamp": time.time()
            })

            # 只保留最近 5 个快照
            if len(self.tracemalloc_snapshots) > 5:
                self.tracemalloc_snapshots = self.tracemalloc_snapshots[-5:]

            # 获取当前内存统计
            current, peak = tracemalloc.get_traced_memory()

            # 获取 top 20 内存分配
            top_stats = snapshot.statistics('lineno')[:20]

            top_allocations = []
            for stat in top_stats:
                top_allocations.append({
                    "file": stat.traceback.format()[0] if stat.traceback else "unknown",
                    "size_mb": stat.size / 1024 / 1024,
                    "count": stat.count
                })

            self.logger.info("tracemalloc 快照已采集",
                           snapshot_count=len(self.tracemalloc_snapshots),
                           current_mb=current / 1024 / 1024,
                           peak_mb=peak / 1024 / 1024)

            return web.json_response({
                "status": "success",
                "snapshot_id": len(self.tracemalloc_snapshots) - 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "memory": {
                    "current_mb": current / 1024 / 1024,
                    "peak_mb": peak / 1024 / 1024
                },
                "top_allocations": top_allocations,
                "total_snapshots": len(self.tracemalloc_snapshots)
            })

        except Exception as e:
            self.logger.error("获取 tracemalloc 快照失败", error=str(e), exc_info=True)
            return web.json_response({
                "status": "error",
                "error": str(e)
            }, status=500)

    async def tracemalloc_compare_handler(self, request: web_request.Request) -> web.Response:
        """对比两次快照，找出内存增长点"""
        try:
            if not self.tracemalloc_enabled:
                return web.json_response({
                    "status": "not_enabled",
                    "message": "tracemalloc is not enabled. Call /tracemalloc/start first"
                }, status=400)

            if len(self.tracemalloc_snapshots) < 2:
                return web.json_response({
                    "status": "insufficient_snapshots",
                    "message": f"Need at least 2 snapshots, but only have {len(self.tracemalloc_snapshots)}",
                    "total_snapshots": len(self.tracemalloc_snapshots)
                }, status=400)

            # 对比最后两个快照
            snapshot1 = self.tracemalloc_snapshots[-2]["snapshot"]
            snapshot2 = self.tracemalloc_snapshots[-1]["snapshot"]
            timestamp1 = self.tracemalloc_snapshots[-2]["timestamp"]
            timestamp2 = self.tracemalloc_snapshots[-1]["timestamp"]

            # 计算差异
            top_stats = snapshot2.compare_to(snapshot1, 'lineno')

            # 获取增长最多的 top 30
            growth_stats = []
            for stat in top_stats[:30]:
                if stat.size_diff > 0:  # 只关注增长的部分
                    growth_stats.append({
                        "file": stat.traceback.format()[0] if stat.traceback else "unknown",
                        "size_diff_mb": stat.size_diff / 1024 / 1024,
                        "size_mb": stat.size / 1024 / 1024,
                        "count_diff": stat.count_diff,
                        "count": stat.count
                    })

            # 按类型统计
            type_stats = {}
            for stat in top_stats:
                if stat.size_diff > 0:
                    traceback_str = stat.traceback.format()[0] if stat.traceback else "unknown"
                    # 尝试提取对象类型（简单启发式）
                    obj_type = "unknown"
                    if "deque" in traceback_str.lower():
                        obj_type = "deque"
                    elif "dict" in traceback_str.lower() or "orderbook" in traceback_str.lower():
                        obj_type = "dict/orderbook"
                    elif "list" in traceback_str.lower() or "queue" in traceback_str.lower():
                        obj_type = "list/queue"
                    elif "str" in traceback_str.lower() or "bytes" in traceback_str.lower():
                        obj_type = "str/bytes"

                    if obj_type not in type_stats:
                        type_stats[obj_type] = {"size_diff_mb": 0, "count_diff": 0}

                    type_stats[obj_type]["size_diff_mb"] += stat.size_diff / 1024 / 1024
                    type_stats[obj_type]["count_diff"] += stat.count_diff

            time_diff = timestamp2 - timestamp1

            self.logger.info("tracemalloc 快照对比完成",
                           time_diff_sec=time_diff,
                           growth_items=len(growth_stats))

            return web.json_response({
                "status": "success",
                "comparison": {
                    "snapshot1_timestamp": datetime.fromtimestamp(timestamp1, tz=timezone.utc).isoformat(),
                    "snapshot2_timestamp": datetime.fromtimestamp(timestamp2, tz=timezone.utc).isoformat(),
                    "time_diff_seconds": time_diff
                },
                "top_growth": growth_stats,
                "type_summary": type_stats,
                "total_growth_items": len(growth_stats)
            })

        except Exception as e:
            self.logger.error("对比 tracemalloc 快照失败", error=str(e), exc_info=True)
            return web.json_response({
                "status": "error",
                "error": str(e)
            }, status=500)
    
    def create_health_app(self) -> web.Application:
        """创建健康检查应用"""
        # 配置连接管理参数，防止 CLOSE_WAIT 连接泄漏
        app = web.Application(
            client_max_size=1024 * 1024,  # 1MB 最大请求体
            handler_args={
                'keepalive_timeout': 15,  # Keep-Alive 超时 15 秒
                'tcp_keepalive': True,    # 启用 TCP Keep-Alive
            }
        )

        # 添加路由
        app.router.add_get('/health', self.health_handler)
        app.router.add_get('/status', self.status_handler)
        app.router.add_get('/ping', self.ping_handler)
        app.router.add_get('/version', self.version_handler)
        app.router.add_get('/tracemalloc/start', self.tracemalloc_start_handler)
        app.router.add_get('/tracemalloc/snapshot', self.tracemalloc_snapshot_handler)
        app.router.add_get('/tracemalloc/compare', self.tracemalloc_compare_handler)
        app.router.add_get('/', self.ping_handler)  # 根路径也返回ping

        return app

    def create_metrics_app(self) -> web.Application:
        """创建指标应用"""
        # 配置连接管理参数，防止 CLOSE_WAIT 连接泄漏
        app = web.Application(
            client_max_size=1024 * 1024,  # 1MB 最大请求体
            handler_args={
                'keepalive_timeout': 15,  # Keep-Alive 超时 15 秒
                'tcp_keepalive': True,    # 启用 TCP Keep-Alive
            }
        )

        # 添加路由
        app.router.add_get('/metrics', self.metrics_handler)
        app.router.add_get('/', self.metrics_handler)  # 根路径也返回指标

        return app
    
    async def start(self):
        """启动HTTP服务器"""
        try:
            # 创建应用
            self.health_app = self.create_health_app()
            self.metrics_app = self.create_metrics_app()
            
            # 创建运行器，配置连接管理参数
            self.health_runner = web.AppRunner(
                self.health_app,
                keepalive_timeout=15.0,  # Keep-Alive 超时 15 秒
                tcp_keepalive=True,      # 启用 TCP Keep-Alive
                shutdown_timeout=10.0    # 关闭超时 10 秒
            )
            self.metrics_runner = web.AppRunner(
                self.metrics_app,
                keepalive_timeout=15.0,
                tcp_keepalive=True,
                shutdown_timeout=10.0
            )

            # 设置运行器
            await self.health_runner.setup()
            await self.metrics_runner.setup()

            # 创建站点，配置 backlog 和 reuse_port
            health_site = web.TCPSite(
                self.health_runner,
                '0.0.0.0',
                self.health_check_port,
                backlog=128,      # 连接队列大小
                reuse_port=True   # 允许端口复用
            )

            metrics_site = web.TCPSite(
                self.metrics_runner,
                '0.0.0.0',
                self.metrics_port,
                backlog=128,
                reuse_port=True
            )
            
            # 启动站点
            await health_site.start()
            await metrics_site.start()
            
            self.logger.info(
                "HTTP服务器启动成功",
                health_port=self.health_check_port,
                metrics_port=self.metrics_port
            )
            
        except Exception as e:
            self.logger.error("HTTP服务器启动失败", error=str(e), exc_info=True)
            raise
    
    async def stop(self):
        """停止HTTP服务器"""
        try:
            if self.health_runner:
                await self.health_runner.cleanup()
                self.health_runner = None
            
            if self.metrics_runner:
                await self.metrics_runner.cleanup()
                self.metrics_runner = None
            
            self.logger.info("HTTP服务器已停止")
            
        except Exception as e:
            self.logger.error("HTTP服务器停止失败", error=str(e), exc_info=True)
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.stop()
