"""
MarketPrism 冷端数据归档服务
定时从热端ClickHouse同步历史数据到本地NAS进行永久存储
"""

import asyncio
import signal
import os
import fcntl
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import structlog

from core.storage.tiered_storage_manager import TieredStorageManager, TierConfig, StorageTier
from core.observability.logging.unified_logger import UnifiedLogger
from aiohttp import web



class ColdStorageService:
    """冷端数据归档服务"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化冷端归档服务

        Args:
            config: 服务配置
        """
        # 初始化日志
        self.logger = structlog.get_logger("services.data_storage.cold_storage")

        # 配置
        self.config = config
        self.hot_storage_config = config.get('hot_storage', {})
        self.cold_storage_config = config.get('cold_storage', {})
        self.sync_config = config.get('sync', {})

        # 分层存储管理器
        self.storage_manager: Optional[TieredStorageManager] = None

        # 同步任务配置
        self.sync_interval = self.sync_config.get('interval_hours', 6)  # 默认6小时同步一次
        self.sync_batch_hours = self.sync_config.get('batch_hours', 24)  # 默认每次同步24小时数据
        # 缓冲时间，避免同步正在写入的最新数据，默认60分钟，可通过配置sync.buffer_minutes调整
        self.sync_buffer_minutes = self.sync_config.get('buffer_minutes', 60)
        self.cleanup_enabled = self.sync_config.get('cleanup_enabled', True)
        self.cleanup_delay_hours = self.sync_config.get('cleanup_delay_hours', 48)  # 同步后48小时清理热端

        # 运行状态
        self.is_running = False
        self.shutdown_event = asyncio.Event()

        # 实例锁（防止多实例同时运行）
        self._lock_fd = None
        self._lock_path = None
        self.sync_task: Optional[asyncio.Task] = None
        # HTTP 服务
        self.app = None
        self.http_runner = None
        # 冷端健康检查端口（来自配置 cold_storage.http_port，默认 8086）
        self.http_port = self.cold_storage_config.get('http_port', 8086)

        self.cleanup_task: Optional[asyncio.Task] = None

        # 统计信息
        self.stats = {
            "sync_cycles": 0,
            "successful_syncs": 0,
            "failed_syncs": 0,
            "last_sync_time": None,
            "last_sync_duration": None,
            "total_records_synced": 0,
            "cleanup_cycles": 0,
            "last_cleanup_time": None,
            "total_records_cleaned": 0,
            "data_types": {
                "orderbook": {"synced": 0, "failed": 0},
                "trade": {"synced": 0, "failed": 0},
                "funding_rate": {"synced": 0, "failed": 0},
                "open_interest": {"synced": 0, "failed": 0},
                "liquidation": {"synced": 0, "failed": 0},
                "lsr_top_position": {"synced": 0, "failed": 0},
                "lsr_all_account": {"synced": 0, "failed": 0},
                "volatility_index": {"synced": 0, "failed": 0}
            }
        }

    async def initialize(self):
        """初始化冷端归档服务"""
        try:
            self.logger.info("🚀 初始化冷端数据归档服务")

            # 初始化分层存储管理器
            await self._initialize_storage_manager()

            self.logger.info("✅ 冷端数据归档服务初始化完成")

        except Exception as e:
            self.logger.error("❌ 冷端数据归档服务初始化失败", error=str(e))
            raise

    async def _initialize_storage_manager(self):
        """初始化分层存储管理器"""
        try:
            # 创建热端配置
            hot_config = TierConfig(
                tier=StorageTier.HOT,
                clickhouse_host=self.hot_storage_config.get('clickhouse_host', 'localhost'),
                clickhouse_port=self.hot_storage_config.get('clickhouse_http_port', 8123),
                clickhouse_user=self.hot_storage_config.get('clickhouse_user', 'default'),
                clickhouse_password=self.hot_storage_config.get('clickhouse_password', ''),
                clickhouse_database=self.hot_storage_config.get('clickhouse_database', 'marketprism_hot'),
                retention_days=self.hot_storage_config.get('retention_days', 3),
                batch_size=self.hot_storage_config.get('batch_size', 1000),
                flush_interval=self.hot_storage_config.get('flush_interval', 5)
            )

            # 创建冷端配置
            cold_config = TierConfig(
                tier=StorageTier.COLD,
                clickhouse_host=self.cold_storage_config.get('clickhouse_host', 'localhost'),
                clickhouse_port=self.cold_storage_config.get('clickhouse_http_port', 8123),
                clickhouse_user=self.cold_storage_config.get('clickhouse_user', 'default'),
                clickhouse_password=self.cold_storage_config.get('clickhouse_password', ''),
                clickhouse_database=self.cold_storage_config.get('clickhouse_database', 'marketprism_cold'),
                retention_days=self.cold_storage_config.get('retention_days', 365),
                batch_size=self.cold_storage_config.get('batch_size', 5000),
                flush_interval=self.cold_storage_config.get('flush_interval', 30)
            )

            # 初始化分层存储管理器
            self.storage_manager = TieredStorageManager(hot_config, cold_config)
            await self.storage_manager.initialize()

            self.logger.info("✅ 分层存储管理器初始化完成")

        except Exception as e:
            self.logger.error("❌ 分层存储管理器初始化失败", error=str(e))
            raise

    def _acquire_singleton_lock(self) -> bool:
        """获取单实例文件锁，防止同机多开"""
        try:
            self._lock_path = os.getenv('MARKETPRISM_COLD_STORAGE_LOCK', '/tmp/marketprism_cold_storage.lock')
            self._lock_fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR, 0o644)
            # 非阻塞独占锁
            fcntl.lockf(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            # 写入PID
            try:
                os.ftruncate(self._lock_fd, 0)
                os.write(self._lock_fd, str(os.getpid()).encode('utf-8'))
            except Exception:
                pass

            self.logger.info("✅ 获取冷端存储服务单实例锁成功", lock_path=self._lock_path)
            return True

        except BlockingIOError:
            self.logger.warning("⚠️ 检测到已有冷端存储服务实例在运行，跳过启动", lock_path=self._lock_path)
            return False
        except Exception as e:
            self.logger.error("❌ 获取冷端存储服务单实例锁失败", error=str(e))
            return False

    def _release_singleton_lock(self):
        """释放单实例文件锁"""
        try:
            if self._lock_fd is not None:
                fcntl.lockf(self._lock_fd, fcntl.LOCK_UN)
                os.close(self._lock_fd)
                self._lock_fd = None
            if self._lock_path and os.path.exists(self._lock_path):
                os.unlink(self._lock_path)
                self._lock_path = None
            self.logger.info("✅ 冷端存储服务单实例锁已释放")
        except Exception as e:
            self.logger.warning("⚠️ 释放单实例锁时出现问题", error=str(e))

    async def start(self):
        """启动冷端归档服务"""
        try:
            self.logger.info("🚀 启动冷端数据归档服务")

            # 获取单实例锁
            if not self._acquire_singleton_lock():
                self.logger.error("❌ 无法获取冷端存储服务单实例锁，退出")
                return

            self.is_running = True

            # 设置信号处理
            # 启动HTTP健康检查服务
            await self.setup_http_server()

            self._setup_signal_handlers()

            # 启动同步任务
            self.sync_task = asyncio.create_task(self._sync_worker())

            # 启动清理任务（如果启用）
            if self.cleanup_enabled:
                self.cleanup_task = asyncio.create_task(self._cleanup_worker())

            self.logger.info("✅ 冷端数据归档服务已启动",
                           sync_interval_hours=self.sync_interval,
                           cleanup_enabled=self.cleanup_enabled)

            # 等待关闭信号
            await self.shutdown_event.wait()

        except Exception as e:
            self.logger.error("❌ 冷端数据归档服务启动失败", error=str(e))
            raise

    async def stop(self):
        """停止冷端归档服务"""
        try:
            self.logger.info("🛑 停止冷端数据归档服务")

            self.is_running = False

            # 停止同步任务
            if self.sync_task:
                self.sync_task.cancel()
                try:
                    await self.sync_task
                except asyncio.CancelledError:
                    pass
                self.logger.info("✅ 同步任务已停止")

            # 停止清理任务
            if self.cleanup_task:
                self.cleanup_task.cancel()
                try:
                    await self.cleanup_task
                except asyncio.CancelledError:
                    pass
                self.logger.info("✅ 清理任务已停止")

            # 关闭HTTP服务
            try:
                if self.http_runner:
                    await self.http_runner.cleanup()
                    self.logger.info("✅ HTTP服务器已关闭")
            except Exception as _e:
                self.logger.warning("⚠️ 关闭HTTP服务器时出现问题", error=str(_e))

            # 关闭存储管理器
            if self.storage_manager:
                await self.storage_manager.close()
                self.logger.info("✅ 存储管理器已关闭")

            # 释放单实例锁
            self._release_singleton_lock()

            # 设置关闭事件
            self.shutdown_event.set()

            self.logger.info("✅ 冷端数据归档服务已停止")

        except Exception as e:
            self.logger.error("❌ 停止冷端数据归档服务失败", error=str(e))
            # 确保释放锁
            self._release_singleton_lock()

    async def _sync_worker(self):
        """数据同步工作器"""
        self.logger.info("🔄 数据同步工作器已启动",
                        interval_hours=self.sync_interval)

        while self.is_running:
            try:
                # 执行数据同步
                await self._perform_sync_cycle()

                # 等待下次同步
                await asyncio.sleep(self.sync_interval * 3600)  # 转换为秒

            except asyncio.CancelledError:
                self.logger.info("🛑 数据同步工作器被取消")
                break
            except Exception as e:
                self.logger.error("❌ 数据同步工作器异常", error=str(e))
                # 错误时等待较短时间再重试
                await asyncio.sleep(300)  # 5分钟

        self.logger.info("🛑 数据同步工作器已停止")

    async def _cleanup_worker(self):
        """数据清理工作器"""
        self.logger.info("🧹 数据清理工作器已启动")

        # 等待一段时间后开始清理（避免与同步冲突）
        await asyncio.sleep(3600)  # 1小时后开始

        while self.is_running:
            try:
                # 执行数据清理
                await self._perform_cleanup_cycle()

                # 等待下次清理（每天清理一次）
                await asyncio.sleep(24 * 3600)  # 24小时

            except asyncio.CancelledError:
                self.logger.info("🛑 数据清理工作器被取消")
                break
            except Exception as e:
                self.logger.error("❌ 数据清理工作器异常", error=str(e))
                # 错误时等待较短时间再重试
                await asyncio.sleep(3600)  # 1小时

        self.logger.info("🛑 数据清理工作器已停止")

    async def _perform_sync_cycle(self):
        """执行一次数据同步周期"""
        try:
            sync_start = datetime.now(timezone.utc)
            self.logger.info("🔄 开始数据同步周期")

            self.stats["sync_cycles"] += 1

            # 计算同步时间范围
            end_time = sync_start - timedelta(minutes=self.sync_buffer_minutes)  # 留缓冲时间
            start_time = end_time - timedelta(hours=self.sync_batch_hours)

            # 获取需要同步的数据类型和交易所
            data_types = self.sync_config.get('data_types', [
                "orderbook", "trade", "funding_rate", "open_interest",
                "liquidation", "lsr_top_position", "lsr_all_account", "volatility_index"
            ])

            exchanges = self.sync_config.get('exchanges', [
                "binance_spot", "binance_derivatives", "okx_spot",
                "okx_derivatives", "deribit_derivatives"
            ])

            # 调度传输任务
            task_ids = []
            for data_type in data_types:
                for exchange in exchanges:
                    # 这里可以根据实际需求获取symbol列表
                    symbols = self._get_symbols_for_exchange(exchange)

                    for symbol in symbols:
                        try:
                            task_id = await self.storage_manager.schedule_data_transfer(
                                data_type, exchange, symbol, start_time, end_time
                            )
                            task_ids.append(task_id)
                        except Exception as e:
                            self.logger.error("❌ 调度传输任务失败",
                                            data_type=data_type,
                                            exchange=exchange,
                                            symbol=symbol,
                                            error=str(e))
                            self.stats["data_types"][data_type]["failed"] += 1

            # 等待所有传输任务完成
            await self._wait_for_transfer_completion(task_ids)

            # 更新统计
            sync_duration = (datetime.now(timezone.utc) - sync_start).total_seconds()
            self.stats["last_sync_time"] = sync_start
            self.stats["last_sync_duration"] = sync_duration
            self.stats["successful_syncs"] += 1

            self.logger.info("✅ 数据同步周期完成",
                           duration_seconds=sync_duration,
                           tasks_scheduled=len(task_ids))

        except Exception as e:
            self.stats["failed_syncs"] += 1
            self.logger.error("❌ 数据同步周期失败", error=str(e))

    async def _perform_cleanup_cycle(self):
        """执行一次数据清理周期"""
        try:
            cleanup_start = datetime.now(timezone.utc)
            self.logger.info("🧹 开始数据清理周期")

            self.stats["cleanup_cycles"] += 1

            # 执行热端数据清理
            cleanup_summary = await self.storage_manager.cleanup_expired_hot_data()

            # 更新统计
            self.stats["last_cleanup_time"] = cleanup_start
            self.stats["total_records_cleaned"] += cleanup_summary.get("total_records_deleted", 0)

            self.logger.info("✅ 数据清理周期完成",
                           records_deleted=cleanup_summary.get("total_records_deleted", 0))

        except Exception as e:
            self.logger.error("❌ 数据清理周期失败", error=str(e))

    def _get_symbols_for_exchange(self, exchange: str) -> List[str]:
        """获取交易所的交易对列表"""
        # 这里可以从配置文件或数据库获取
        # 暂时返回默认的主要交易对
        return self.sync_config.get('symbols', {}).get(exchange, ["BTC-USDT"])

    async def _wait_for_transfer_completion(self, task_ids: List[str], timeout_minutes: int = 60):
        """等待传输任务完成"""
        try:
            timeout_seconds = timeout_minutes * 60
            start_time = datetime.now(timezone.utc)

            while (datetime.now(timezone.utc) - start_time).total_seconds() < timeout_seconds:
                # 检查所有任务状态
                pending_tasks = []
                completed_tasks = 0
                failed_tasks = 0

                for task_id in task_ids:
                    status = self.storage_manager.get_transfer_task_status(task_id)
                    if status:
                        if status["status"] == "pending" or status["status"] == "running":
                            pending_tasks.append(task_id)
                        elif status["status"] == "completed":
                            completed_tasks += 1
                        elif status["status"] == "failed":
                            failed_tasks += 1

                # 如果所有任务都完成了
                if not pending_tasks:
                    self.logger.info("✅ 所有传输任务已完成",
                                   total_tasks=len(task_ids),
                                   completed=completed_tasks,
                                   failed=failed_tasks)
                    return

                # 等待一段时间再检查
                await asyncio.sleep(30)  # 30秒检查一次

            # 超时
            self.logger.warning("⚠️ 传输任务等待超时",
                              timeout_minutes=timeout_minutes,
                              pending_tasks=len(pending_tasks))

        except Exception as e:
            self.logger.error("❌ 等待传输任务完成失败", error=str(e))

    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(signum, frame):
            self.logger.info("📡 收到停止信号", signal=signum)
            asyncio.create_task(self.stop())

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def setup_http_server(self):
        """设置并启动HTTP服务器（/health, /stats）"""
        try:
            self.app = web.Application()
            self.app.router.add_get('/health', self.handle_health)
            self.app.router.add_get('/stats', self.handle_stats)
            runner = web.AppRunner(self.app)
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', self.http_port)
            await site.start()
            self.http_runner = runner
            self.logger.info(f"✅ HTTP服务器启动成功，端口: {self.http_port}")
        except Exception as e:
            self.logger.error("❌ 启动HTTP服务器失败", error=str(e))

    async def handle_health(self, request):
        health = await self.health_check()
        status = health.get("status", "unhealthy")
        code = 200 if status in ("healthy", "degraded") else 503
        return web.json_response(health, status=code)

    async def handle_stats(self, request):
        return web.json_response(self.get_stats(), status=200)

    def get_stats(self) -> Dict[str, Any]:
        """获取服务统计信息"""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service_status": {
                "is_running": self.is_running,
                "sync_task_active": self.sync_task is not None and not self.sync_task.done(),
                "cleanup_task_active": self.cleanup_task is not None and not self.cleanup_task.done()
            },
            "sync_stats": self.stats,
            "storage_stats": self.storage_manager.get_storage_stats() if self.storage_manager else None
        }

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {}
        }

        # 检查存储管理器
        if self.storage_manager:
            storage_health = await self.storage_manager.health_check()
            health_status["components"]["storage"] = storage_health
            if storage_health["status"] != "healthy":
                health_status["status"] = "degraded"
        else:
            health_status["components"]["storage"] = {"status": "not_initialized"}
            health_status["status"] = "unhealthy"

        # 检查同步任务
        if self.sync_task and not self.sync_task.done():
            health_status["components"]["sync_worker"] = {"status": "healthy"}
        else:
            health_status["components"]["sync_worker"] = {"status": "stopped"}
            if health_status["status"] == "healthy":
                health_status["status"] = "degraded"

        return health_status
