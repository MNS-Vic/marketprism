"""
MarketPrism 分层存储管理器
实现热端-冷端数据存储架构，支持数据生命周期管理
"""

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum
import structlog

# 适配到统一存储管理器（替代旧的 UnifiedClickHouseWriter 接口）
from .unified_storage_manager import UnifiedStorageManager, UnifiedStorageConfig
from .types import (
    NormalizedOrderBook, NormalizedTrade
)


class StorageTier(Enum):
    """存储层级枚举"""
    HOT = "hot"      # 热端存储：高频访问，短期保留
    COLD = "cold"    # 冷端存储：低频访问，长期保留
    ARCHIVE = "archive"  # 归档存储：极少访问，永久保留


@dataclass
class TierConfig:
    """存储层级配置"""
    tier: StorageTier
    clickhouse_host: str
    clickhouse_port: int
    clickhouse_user: str
    clickhouse_password: str
    clickhouse_database: str
    retention_days: int
    batch_size: int = 1000
    flush_interval: int = 5
    max_retries: int = 3


@dataclass
class DataTransferTask:
    """数据传输任务"""
    task_id: str
    source_tier: StorageTier
    target_tier: StorageTier
    data_type: str
    exchange: str
    symbol: str
    start_time: datetime
    end_time: datetime
    status: str = "pending"  # pending, running, completed, failed
    created_at: datetime = None
    updated_at: datetime = None
    error_message: Optional[str] = None
    records_count: int = 0

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        if self.updated_at is None:
            self.updated_at = self.created_at


class WriterAdapter:
    """将 UnifiedStorageManager 适配为 TieredStorageManager 期望的写入器接口"""
    def __init__(self, tier_cfg: TierConfig):
        storage_type = tier_cfg.tier.value
        uni_cfg = UnifiedStorageConfig(
            storage_type=storage_type,
            clickhouse_host=tier_cfg.clickhouse_host,
            clickhouse_port=tier_cfg.clickhouse_port,
            clickhouse_user=tier_cfg.clickhouse_user,
            clickhouse_password=tier_cfg.clickhouse_password,
            clickhouse_database=tier_cfg.clickhouse_database,
            redis_enabled=False
        )
        self.sm = UnifiedStorageManager(config=uni_cfg, config_path=None, storage_type=storage_type)

    async def initialize(self):
        await self.sm.start()

    async def close(self):
        await self.sm.stop()

    async def health_check(self):
        try:
            st = await self.sm.get_status()
            return {"status": "healthy" if st.get("is_running") else "unhealthy", "details": st}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    # ---------------- 批量存储方法（与旧接口名对齐） ----------------
    async def store_trades(self, data_list):
        for d in data_list:
            await self.sm.store_trade(d)
        return True

    async def store_orderbooks(self, data_list):
        import json as _json
        for d in data_list:
            # 将JSON字符串的bids/asks解析为列表
            try:
                if isinstance(d.get('bids'), str):
                    d['bids'] = _json.loads(d.get('bids') or '[]')
                if isinstance(d.get('asks'), str):
                    d['asks'] = _json.loads(d.get('asks') or '[]')
            except Exception as _e:
                # 保底：解析失败时将其置为空列表，避免写入时出错
                d['bids'] = []
                d['asks'] = []
            await self.sm.store_orderbook(d)
        return True

    async def store_funding_rates(self, data_list):
        for d in data_list:
            await self.sm.store_funding_rate(d)
        return True

    async def store_open_interests(self, data_list):
        for d in data_list:
            await self.sm.store_open_interest(d)
        return True

    async def store_liquidations(self, data_list):
        for d in data_list:
            await self.sm.store_liquidation(d)
        return True

    async def store_lsrs(self, data_list):
        # 兼容两类表：lsr_top_positions 与 lsr_all_accounts
        for d in data_list:
            if 'long_position_ratio' in d or 'short_position_ratio' in d:
                await self.sm.store_lsr_top_position(d)
            elif 'long_account_ratio' in d or 'short_account_ratio' in d:
                await self.sm.store_lsr_all_account(d)
            else:
                # 跳过未知结构
                continue
        return True

    async def store_volatility_indices(self, data_list):
        for d in data_list:
            await self.sm.store_volatility_index(d)
        return True

    # ---------------- 查询适配（仅覆盖本模块用到的几种SQL） ----------------
    async def execute_query(self, query: str, params: Dict[str, Any]):
        # 适配本模块构造的常见 SQL（含 INSERT/SELECT/COUNT/DELETE）
        q = query
        try:
            def _fmt_dt(dt):
                # 统一格式化为秒级（去掉毫秒），ClickHouse 23.8 的 toDateTime 仅接受秒精度
                if isinstance(dt, datetime):
                    return dt.strftime('%Y-%m-%d %H:%M:%S')
                if isinstance(dt, str):
                    s = dt.strip().replace('T', ' ')
                    # 优先尝试 fromisoformat（可含微秒）
                    try:
                        return datetime.fromisoformat(s).strftime('%Y-%m-%d %H:%M:%S')
                    except Exception:
                        # 尝试标准不含微秒格式
                        try:
                            return datetime.strptime(s, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M:%S')
                        except Exception:
                            # 粗略去掉小数秒
                            if '.' in s:
                                base = s.split('.')[0]
                                try:
                                    datetime.strptime(base, '%Y-%m-%d %H:%M:%S')
                                    return base
                                except Exception:
                                    pass
                return str(dt)
            def _q(s: str) -> str:
                return s.replace("'", "\\'")

            up = q.upper()

            # INSERT INTO <cold> SELECT ... FROM <hot> WHERE exchange/symbol/time
            if 'INSERT INTO' in up and 'SELECT' in up and '%(exchange)s' in q:
                exchange = params.get('exchange', '')
                symbol = params.get('symbol', '')
                start_time = _fmt_dt(params.get('start_time'))
                end_time = _fmt_dt(params.get('end_time'))
                # 直接参数替换，避免解析/拼接带来的歧义
                q_final = (
                    q.replace("%(exchange)s", f"'{_q(exchange)}'")
                     .replace("%(symbol)s", f"'{_q(symbol)}'")
                     .replace("%(start_time)s", f"toDateTime('{start_time}')")
                     .replace("%(end_time)s", f"toDateTime('{end_time}')")
                )
                return await self.sm.clickhouse_client.execute(q_final)

            # SELECT ... WHERE exchange/symbol/time 占位符替换
            if 'SELECT' in up and '%(exchange)s' in q and '%(start_time)s' in q:
                exchange = params.get('exchange', '')
                symbol = params.get('symbol', '')
                start_time = _fmt_dt(params.get('start_time'))
                end_time = _fmt_dt(params.get('end_time'))
                q_final = (
                    q.replace("%(exchange)s", f"'{_q(exchange)}'")
                     .replace("%(symbol)s", f"'{_q(symbol)}'")
                     .replace("%(start_time)s", f"toDateTime('{start_time}')")
                     .replace("%(end_time)s", f"toDateTime('{end_time}')")
                )
                return await self.sm.clickhouse_client.fetchall(q_final)

            # ALTER TABLE <table> DELETE WHERE timestamp < %(cutoff_time)s
            if 'ALTER TABLE' in up and 'DELETE' in up and '%(cutoff_time)s' in q:
                tbl = q.split('ALTER TABLE')[1].split('DELETE')[0].strip()
                cutoff = _fmt_dt(params.get('cutoff_time'))
                q = f"ALTER TABLE {tbl} DELETE WHERE timestamp < toDateTime('{cutoff}')"
                return await self.sm.clickhouse_client.execute(q)

            # SELECT count() FROM <table> WHERE timestamp < %(cutoff_time)s
            if 'SELECT' in up and 'COUNT()' in up and '%(cutoff_time)s' in q:
                tbl = q.split('FROM')[1].split('WHERE')[0].strip()
                cutoff = _fmt_dt(params.get('cutoff_time'))
                q = f"SELECT count() FROM {tbl} WHERE timestamp < toDateTime('{cutoff}')"
                rows = await self.sm.clickhouse_client.fetchall(q)
                return rows

            # 兜底：根据语句类型选择执行方法
            if up.strip().startswith('SELECT'):
                return await self.sm.clickhouse_client.fetchall(q)
            else:
                return await self.sm.clickhouse_client.execute(q)
        except Exception as e:
            # 失败抛出，由上层决定回退逻辑
            raise e


class TieredStorageManager:
    """分层存储管理器"""

    def __init__(self, hot_config: TierConfig, cold_config: TierConfig):
        """
        初始化分层存储管理器

        Args:
            hot_config: 热端存储配置
            cold_config: 冷端存储配置
        """
        self.logger = structlog.get_logger("core.storage.tiered_storage_manager")

        # 存储配置
        self.hot_config = hot_config
        self.cold_config = cold_config

        # 适配后的存储管理器（使用统一存储管理器包装成写入器接口）
        self.hot_writer: Optional["WriterAdapter"] = None
        self.cold_writer: Optional["WriterAdapter"] = None

        # 数据传输任务队列
        self.transfer_tasks: Dict[str, DataTransferTask] = {}
        self.transfer_queue = asyncio.Queue()

        # 运行状态
        self.is_running = False
        self.transfer_worker_task: Optional[asyncio.Task] = None

        # 统计信息
        self.stats = {
            "hot_storage": {
                "total_writes": 0,
                "failed_writes": 0,
                "last_write_time": None
            },
            "cold_storage": {
                "total_writes": 0,
                "failed_writes": 0,
                "last_write_time": None
            },
            "data_transfers": {
                "total_tasks": 0,
                "completed_tasks": 0,
                "failed_tasks": 0,
                "last_transfer_time": None
            }
        }

    async def initialize(self):
        """初始化分层存储管理器"""
        try:
            self.logger.info("🚀 初始化分层存储管理器")

            # 初始化热端存储（使用适配器）
            self.hot_writer = WriterAdapter(self.hot_config)
            await self.hot_writer.initialize()
            try:
                hc = await self.hot_writer.health_check()
                self.logger.info("✅ 热端存储初始化成功",
                                 host=self.hot_config.clickhouse_host,
                                 port=self.hot_config.clickhouse_port,
                                 database=self.hot_config.clickhouse_database,
                                 health=hc)
            except Exception:
                self.logger.info("✅ 热端存储初始化成功",
                                 host=self.hot_config.clickhouse_host,
                                 port=self.hot_config.clickhouse_port,
                                 database=self.hot_config.clickhouse_database)

            # 初始化冷端存储（使用适配器）
            self.cold_writer = WriterAdapter(self.cold_config)
            await self.cold_writer.initialize()
            try:
                hc2 = await self.cold_writer.health_check()
                self.logger.info("✅ 冷端存储初始化成功",
                                 host=self.cold_config.clickhouse_host,
                                 port=self.cold_config.clickhouse_port,
                                 database=self.cold_config.clickhouse_database,
                                 health=hc2)
            except Exception:
                self.logger.info("✅ 冷端存储初始化成功",
                                 host=self.cold_config.clickhouse_host,
                                 port=self.cold_config.clickhouse_port,
                                 database=self.cold_config.clickhouse_database)

            # 启动数据传输工作器
            self.is_running = True
            self.transfer_worker_task = asyncio.create_task(self._transfer_worker())

            self.logger.info("✅ 分层存储管理器初始化完成")

        except Exception as e:
            self.logger.error("❌ 分层存储管理器初始化失败", error=str(e))
            raise

    async def close(self):
        """关闭分层存储管理器"""
        try:
            self.logger.info("🛑 关闭分层存储管理器")

            # 停止传输工作器
            self.is_running = False
            if self.transfer_worker_task:
                self.transfer_worker_task.cancel()
                try:
                    await self.transfer_worker_task
                except asyncio.CancelledError:
                    pass

            # 关闭存储写入器
            if self.hot_writer:
                await self.hot_writer.close()
                self.logger.info("✅ 热端存储已关闭")

            if self.cold_writer:
                await self.cold_writer.close()
                self.logger.info("✅ 冷端存储已关闭")

            self.logger.info("✅ 分层存储管理器已关闭")

        except Exception as e:
            self.logger.error("❌ 关闭分层存储管理器失败", error=str(e))

    # ==================== 数据写入方法 ====================

    async def store_to_hot(self, data_type: str, data: Union[Dict, List[Dict]]) -> bool:
        """存储数据到热端"""
        try:
            if not self.hot_writer:
                self.logger.error("❌ 热端存储未初始化")
                return False

            # 根据数据类型选择存储方法
            success = await self._store_by_type(self.hot_writer, data_type, data)

            # 更新统计
            if success:
                self.stats["hot_storage"]["total_writes"] += 1
                self.stats["hot_storage"]["last_write_time"] = datetime.now(timezone.utc)
            else:
                self.stats["hot_storage"]["failed_writes"] += 1

            return success

        except Exception as e:
            self.logger.error("❌ 热端存储失败", data_type=data_type, error=str(e))
            self.stats["hot_storage"]["failed_writes"] += 1
            return False

    async def store_to_cold(self, data_type: str, data: Union[Dict, List[Dict]]) -> bool:
        """存储数据到冷端"""
        try:
            if not self.cold_writer:
                self.logger.error("❌ 冷端存储未初始化")
                return False

            # 根据数据类型选择存储方法
            success = await self._store_by_type(self.cold_writer, data_type, data)

            # 更新统计
            if success:
                self.stats["cold_storage"]["total_writes"] += 1
                self.stats["cold_storage"]["last_write_time"] = datetime.now(timezone.utc)
            else:
                self.stats["cold_storage"]["failed_writes"] += 1

            return success

        except Exception as e:
            self.logger.error("❌ 冷端存储失败", data_type=data_type, error=str(e))
            self.stats["cold_storage"]["failed_writes"] += 1
            return False

    async def _store_by_type(self, writer: "WriterAdapter", data_type: str, data: Union[Dict, List[Dict]]) -> bool:
        """根据数据类型存储数据"""
        try:
            # 确保数据是列表格式
            if isinstance(data, dict):
                data = [data]

            # 根据数据类型调用相应的存储方法
            if data_type == "orderbook":
                # 冷端：优先采用批量 INSERT SELECT，避免逐行转换与schema不一致
                if writer is self.cold_writer and isinstance(data, list) and data:
                    try:
                        exch = data[0].get('exchange')
                        sym = data[0].get('symbol')
                        ts_list = [row.get('timestamp') for row in data if row.get('timestamp') is not None]
                        start_time = min(ts_list)
                        end_time = max(ts_list)
                        sql = (
                            "INSERT INTO marketprism_cold.orderbooks ("
                            "timestamp, exchange, market_type, symbol, last_update_id, bids_count, asks_count, "
                            "best_bid_price, best_ask_price, best_bid_quantity, best_ask_quantity, bids, asks, data_source, created_at) "
                            "SELECT timestamp, exchange, market_type, symbol, last_update_id, bids_count, asks_count, "
                            "best_bid_price, best_ask_price, best_bid_quantity, best_ask_quantity, bids, asks, 'marketprism', now() "
                            "FROM marketprism_hot.orderbooks "
                            "WHERE exchange = %(exchange)s AND symbol = %(symbol)s "
                            "AND timestamp >= %(start_time)s AND timestamp <= %(end_time)s"
                        )
                        params = {"exchange": exch, "symbol": sym, "start_time": start_time, "end_time": end_time}
                        await writer.execute_query(sql, params)
                        return True
                    except Exception as be:
                        self.logger.error("❌ 订单簿批量迁移失败（冷端）", error=str(be))
                        # 冷端不再回退到逐行写入，避免噪音与类型不一致
                        return False
                # 其他情况（热端等）：逐行
                return await writer.store_orderbooks(data)
            elif data_type == "trade":
                if writer is self.cold_writer and isinstance(data, list) and data:
                    try:
                        exch = data[0].get('exchange')
                        sym = data[0].get('symbol')
                        ts_list = [row.get('timestamp') for row in data if row.get('timestamp') is not None]
                        start_time = min(ts_list)
                        end_time = max(ts_list)
                        sql = (
                            "INSERT INTO marketprism_cold.trades ("
                            "timestamp, exchange, market_type, symbol, trade_id, price, quantity, side, is_maker, trade_time, data_source, created_at) "
                            "SELECT timestamp, exchange, market_type, symbol, trade_id, price, quantity, side, is_maker, trade_time, 'marketprism', now() "
                            "FROM marketprism_hot.trades "
                            "WHERE exchange = %(exchange)s AND symbol = %(symbol)s "
                            "AND timestamp >= %(start_time)s AND timestamp <= %(end_time)s"
                        )
                        params = {"exchange": exch, "symbol": sym, "start_time": start_time, "end_time": end_time}
                        await writer.execute_query(sql, params)
                        return True
                    except Exception as be:
                        self.logger.error("❌ 交易数据批量迁移失败（冷端）", error=str(be))
                        # 冷端不再回退到逐行写入，避免噪音与类型不一致
                        return False
                # 其他情况（热端等）：逐行
                return await writer.store_trades(data)
            elif data_type == "funding_rate":
                return await writer.store_funding_rates(data)
            elif data_type == "open_interest":
                return await writer.store_open_interests(data)
            elif data_type == "liquidation":
                return await writer.store_liquidations(data)
            elif data_type == "lsr":
                return await writer.store_lsrs(data)
            elif data_type == "volatility_index":
                return await writer.store_volatility_indices(data)
            else:
                self.logger.error("❌ 不支持的数据类型", data_type=data_type)
                return False

        except Exception as e:
            self.logger.error("❌ 数据存储失败", data_type=data_type, error=str(e))
            return False

    # ==================== 数据传输方法 ====================

    async def schedule_data_transfer(self, data_type: str, exchange: str, symbol: str,
                                   start_time: datetime, end_time: datetime) -> str:
        """调度数据传输任务"""
        try:
            # 生成任务ID
            task_id = f"transfer_{data_type}_{exchange}_{symbol}_{int(time.time())}"

            # 创建传输任务
            task = DataTransferTask(
                task_id=task_id,
                source_tier=StorageTier.HOT,
                target_tier=StorageTier.COLD,
                data_type=data_type,
                exchange=exchange,
                symbol=symbol,
                start_time=start_time,
                end_time=end_time
            )

            # 添加到任务队列
            self.transfer_tasks[task_id] = task
            await self.transfer_queue.put(task)

            self.stats["data_transfers"]["total_tasks"] += 1

            self.logger.info("📋 数据传输任务已调度",
                           task_id=task_id,
                           data_type=data_type,
                           exchange=exchange,
                           symbol=symbol)

            return task_id

        except Exception as e:
            self.logger.error("❌ 调度数据传输任务失败", error=str(e))
            raise

    async def _transfer_worker(self):
        """数据传输工作器"""
        self.logger.info("🔄 数据传输工作器已启动")

        while self.is_running:
            try:
                # 等待传输任务
                task = await asyncio.wait_for(self.transfer_queue.get(), timeout=1.0)

                # 执行数据传输
                await self._execute_transfer_task(task)

            except asyncio.TimeoutError:
                # 超时是正常的，继续循环
                continue
            except Exception as e:
                self.logger.error("❌ 数据传输工作器异常", error=str(e))
                await asyncio.sleep(5)  # 错误时等待5秒

        self.logger.info("🛑 数据传输工作器已停止")

    async def _execute_transfer_task(self, task: DataTransferTask):
        """执行数据传输任务"""
        try:
            self.logger.info("🚀 开始执行数据传输任务", task_id=task.task_id)

            # 更新任务状态
            task.status = "running"
            task.updated_at = datetime.now(timezone.utc)

            # 从热端查询数据
            hot_data = await self._query_hot_data(
                task.data_type, task.exchange, task.symbol,
                task.start_time, task.end_time
            )

            if not hot_data:
                self.logger.warning("⚠️ 未找到需要传输的数据", task_id=task.task_id)
                task.status = "completed"
                task.records_count = 0
                task.updated_at = datetime.now(timezone.utc)
                return

            # 存储到冷端
            success = await self.store_to_cold(task.data_type, hot_data)

            if success:
                task.status = "completed"
                task.records_count = len(hot_data) if isinstance(hot_data, list) else 1
                self.stats["data_transfers"]["completed_tasks"] += 1
                self.stats["data_transfers"]["last_transfer_time"] = datetime.now(timezone.utc)

                self.logger.info("✅ 数据传输任务完成",
                               task_id=task.task_id,
                               records_count=task.records_count)

                # 可选：删除热端数据（根据配置决定）
                # await self._cleanup_hot_data(task)

            else:
                task.status = "failed"
                task.error_message = "冷端存储失败"
                self.stats["data_transfers"]["failed_tasks"] += 1

                self.logger.error("❌ 数据传输任务失败", task_id=task.task_id)

            task.updated_at = datetime.now(timezone.utc)

        except Exception as e:
            task.status = "failed"
            task.error_message = str(e)
            task.updated_at = datetime.now(timezone.utc)
            self.stats["data_transfers"]["failed_tasks"] += 1

            self.logger.error("❌ 执行数据传输任务异常",
                            task_id=task.task_id, error=str(e))

    async def _query_hot_data(self, data_type: str, exchange: str, symbol: str,
                            start_time: datetime, end_time: datetime) -> List[Dict]:
        """从热端查询数据"""
        try:
            if not self.hot_writer:
                return []

            # 构建查询SQL
            table_name = self._get_table_name(data_type)
            query = f"""
                SELECT * FROM {table_name}
                WHERE exchange = %(exchange)s
                AND symbol = %(symbol)s
                AND timestamp >= %(start_time)s
                AND timestamp < %(end_time)s
                ORDER BY timestamp
            """

            params = {
                'exchange': exchange,
                'symbol': symbol,
                'start_time': start_time,
                'end_time': end_time
            }

            # 执行查询
            result = await self.hot_writer.execute_query(query, params)

            self.logger.debug("📊 热端数据查询完成",
                            data_type=data_type,
                            exchange=exchange,
                            symbol=symbol,
                            records_count=len(result))

            return result

        except Exception as e:
            self.logger.error("❌ 热端数据查询失败", error=str(e))
            return []

    def _get_table_name(self, data_type: str) -> str:
        """获取数据类型对应的表名"""
        table_mapping = {
            "orderbook": "orderbooks",
            "trade": "trades",
            "funding_rate": "funding_rates",
            "open_interest": "open_interests",
            "liquidation": "liquidations",
            #   LSR  
            #    "lsrs"   "lsr_top_positions"
            "lsr": "lsr_top_positions",
            "volatility_index": "volatility_indices"
        }
        return table_mapping.get(data_type, data_type)

    # ==================== 数据生命周期管理 ====================

    async def cleanup_expired_hot_data(self) -> Dict[str, Any]:
        """清理过期的热端数据"""
        try:
            self.logger.info("🧹 开始清理过期热端数据")

            cutoff_time = datetime.now(timezone.utc) - timedelta(days=self.hot_config.retention_days)

            cleanup_summary = {
                "cutoff_time": cutoff_time.isoformat(),
                "tables_cleaned": {},
                "total_records_deleted": 0
            }

            # 清理各种数据类型的表
            data_types = ["orderbook", "trade", "funding_rate", "open_interest",
                         "liquidation", "lsr", "volatility_index"]

            for data_type in data_types:
                try:
                    table_name = self._get_table_name(data_type)
                    deleted_count = await self._cleanup_table_data(table_name, cutoff_time)

                    cleanup_summary["tables_cleaned"][table_name] = deleted_count
                    cleanup_summary["total_records_deleted"] += deleted_count

                    self.logger.info("✅ 表数据清理完成",
                                   table=table_name,
                                   deleted_count=deleted_count)

                except Exception as e:
                    self.logger.error("❌ 表数据清理失败",
                                    table=table_name, error=str(e))
                    cleanup_summary["tables_cleaned"][table_name] = f"error: {str(e)}"

            self.logger.info("✅ 热端数据清理完成",
                           total_deleted=cleanup_summary["total_records_deleted"])

            return cleanup_summary

        except Exception as e:
            self.logger.error("❌ 清理过期热端数据失败", error=str(e))
            raise

    async def _cleanup_table_data(self, table_name: str, cutoff_time: datetime) -> int:
        """清理指定表的过期数据"""
        try:
            if not self.hot_writer:
                return 0

            # 构建删除SQL
            delete_query = f"""
                ALTER TABLE {table_name} DELETE
                WHERE timestamp < %(cutoff_time)s
            """

            params = {'cutoff_time': cutoff_time}

            # 执行删除
            await self.hot_writer.execute_query(delete_query, params)

            # 查询删除的记录数（ClickHouse的DELETE是异步的，这里返回估算值）
            count_query = f"""
                SELECT count() FROM {table_name}
                WHERE timestamp < %(cutoff_time)s
            """

            result = await self.hot_writer.execute_query(count_query, params)
            deleted_count = result[0]['count()'] if result else 0

            return deleted_count

        except Exception as e:
            self.logger.error("❌ 清理表数据失败", table=table_name, error=str(e))
            return 0

    # ==================== 状态查询方法 ====================

    def get_transfer_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取传输任务状态"""
        task = self.transfer_tasks.get(task_id)
        if not task:
            return None

        return {
            "task_id": task.task_id,
            "source_tier": task.source_tier.value,
            "target_tier": task.target_tier.value,
            "data_type": task.data_type,
            "exchange": task.exchange,
            "symbol": task.symbol,
            "start_time": task.start_time.isoformat(),
            "end_time": task.end_time.isoformat(),
            "status": task.status,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
            "error_message": task.error_message,
            "records_count": task.records_count
        }

    def get_all_transfer_tasks(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取所有传输任务"""
        tasks = []
        for task in self.transfer_tasks.values():
            if status_filter is None or task.status == status_filter:
                tasks.append(self.get_transfer_task_status(task.task_id))

        # 按创建时间倒序排列
        tasks.sort(key=lambda x: x["created_at"], reverse=True)
        return tasks

    def get_storage_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hot_storage": {
                **self.stats["hot_storage"],
                "config": {
                    "host": self.hot_config.clickhouse_host,
                    "database": self.hot_config.clickhouse_database,
                    "retention_days": self.hot_config.retention_days
                },
                "status": "connected" if self.hot_writer else "disconnected"
            },
            "cold_storage": {
                **self.stats["cold_storage"],
                "config": {
                    "host": self.cold_config.clickhouse_host,
                    "database": self.cold_config.clickhouse_database,
                    "retention_days": self.cold_config.retention_days
                },
                "status": "connected" if self.cold_writer else "disconnected"
            },
            "data_transfers": {
                **self.stats["data_transfers"],
                "pending_tasks": len([t for t in self.transfer_tasks.values() if t.status == "pending"]),
                "running_tasks": len([t for t in self.transfer_tasks.values() if t.status == "running"]),
                "queue_size": self.transfer_queue.qsize()
            },
            "system": {
                "is_running": self.is_running,
                "transfer_worker_active": self.transfer_worker_task is not None and not self.transfer_worker_task.done()
            }
        }

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {}
        }

        # 检查热端存储
        try:
            if self.hot_writer:
                await self.hot_writer.health_check()
                health_status["components"]["hot_storage"] = {"status": "healthy"}
            else:
                health_status["components"]["hot_storage"] = {"status": "not_initialized"}
        except Exception as e:
            health_status["components"]["hot_storage"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "degraded"

        # 检查冷端存储
        try:
            if self.cold_writer:
                await self.cold_writer.health_check()
                health_status["components"]["cold_storage"] = {"status": "healthy"}
            else:
                health_status["components"]["cold_storage"] = {"status": "not_initialized"}
        except Exception as e:
            health_status["components"]["cold_storage"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "degraded"

        # 检查传输工作器
        if self.is_running and self.transfer_worker_task and not self.transfer_worker_task.done():
            health_status["components"]["transfer_worker"] = {"status": "healthy"}
        else:
            health_status["components"]["transfer_worker"] = {"status": "stopped"}
            if health_status["status"] == "healthy":
                health_status["status"] = "degraded"

        return health_status

    # ==================== 便捷方法 ====================

    async def auto_schedule_transfers(self, data_types: List[str] = None,
                                    exchanges: List[str] = None,
                                    lookback_hours: int = 24) -> List[str]:
        """自动调度数据传输任务"""
        try:
            if data_types is None:
                data_types = ["orderbook", "trade", "funding_rate", "open_interest",
                             "liquidation", "lsr", "volatility_index"]

            if exchanges is None:
                exchanges = ["binance_spot", "binance_derivatives", "okx_spot",
                           "okx_derivatives", "deribit_derivatives"]

            # 计算时间范围
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=lookback_hours)

            task_ids = []

            for data_type in data_types:
                for exchange in exchanges:
                    # 这里可以根据实际需求获取symbol列表
                    # 暂时使用通用symbol
                    symbol = "BTC-USDT"  # 可以从配置或数据库获取

                    try:
                        task_id = await self.schedule_data_transfer(
                            data_type, exchange, symbol, start_time, end_time
                        )
                        task_ids.append(task_id)
                    except Exception as e:
                        self.logger.error("❌ 自动调度传输任务失败",
                                        data_type=data_type,
                                        exchange=exchange,
                                        error=str(e))

            self.logger.info("✅ 自动调度传输任务完成",
                           scheduled_tasks=len(task_ids),
                           lookback_hours=lookback_hours)

            return task_ids

        except Exception as e:
            self.logger.error("❌ 自动调度传输任务失败", error=str(e))
            return []
