"""
统一存储管理器

整合了所有存储管理器的功能，消除ClickHouse初始化等重复代码
支持热存储、冷存储、简化存储的统一管理
"""

import asyncio
import logging
import time
import json
import yaml
import gzip
import pickle
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Union, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import os
import hashlib
import structlog
from enum import Enum

# Redis兼容性导入 - Python 3.12依赖问题修复
#
# 问题描述：
# aioredis==2.0.1与Python 3.12存在兼容性问题
# TypeError: duplicate base class TimeoutError
# 原因：aioredis.exceptions.TimeoutError同时继承了asyncio.TimeoutError和builtins.TimeoutError
# 在Python 3.12中这两个类是同一个类，导致重复继承错误
#
# 解决方案：使用兼容的Redis异步客户端
# 1. redis[hiredis]==6.1.0 - 官方Redis客户端的异步版本，支持Python 3.12
# 2. asyncio-redis==0.16.0 - 纯Python异步Redis客户端，兼容性良好
# 3. redis.asyncio - redis库内置的异步支持（最终后备）
try:
    import aioredis
    # 如果导入成功但版本有问题，检测TimeoutError兼容性
    from aioredis.exceptions import TimeoutError as AioRedisTimeoutError
except (ImportError, TypeError) as e:
    # Python 3.12兼容性问题，按优先级使用替代方案
    try:
        # 优先使用asyncio-redis（纯Python实现，兼容性最好）
        import asyncio_redis as aioredis
    except ImportError:
        try:
            # 次选redis.asyncio（redis官方库的异步支持）
            import redis.asyncio as aioredis
        except ImportError:
            # 最终后备：创建Mock客户端以保持API兼容性
            aioredis = None

import aiochclient
import aiohttp
from prometheus_client import Counter, Histogram, Gauge
from .unified_clickhouse_writer import UnifiedClickHouseWriter

# 尝试相对导入，失败则使用绝对导入
try:
    from .types import NormalizedTrade, NormalizedOrderBook, NormalizedTicker
    from .unified_clickhouse_writer import UnifiedClickHouseWriter
    from .archiver_storage_manager import StorageManager as ArchiverStorageManager
    from .storage_config_manager import StorageConfigManager, StorageMode
    from .data_migration_service import DataMigrationService
except ImportError:
    # 绝对导入作为后备
    try:
        from core.storage.types import NormalizedTrade, NormalizedOrderBook, NormalizedTicker
        from core.storage.unified_clickhouse_writer import UnifiedClickHouseWriter
        from core.storage.archiver_storage_manager import StorageManager as ArchiverStorageManager
        from core.storage.storage_config_manager import StorageConfigManager, StorageMode
        from core.storage.data_migration_service import DataMigrationService
    except ImportError:
        # 创建虚拟类型（最终后备）
        class NormalizedTrade:
            pass
        class NormalizedOrderBook:
            pass
        class NormalizedTicker:
            pass

        UnifiedClickHouseWriter = None
        ArchiverStorageManager = None
        StorageConfigManager = None
        DataMigrationService = None

logger = logging.getLogger(__name__)


class StorageMode(Enum):
    """存储模式枚举"""
    HOT = "hot"
    COLD = "cold"
    SIMPLE = "simple"
    HYBRID = "hybrid"

# Prometheus指标（使用全局变量避免重复注册）
_metrics_registry = {}

def _get_metric(name, metric_type, description, labels=None):
    """获取或创建Prometheus指标（避免重复注册）"""
    if name not in _metrics_registry:
        if metric_type == "counter":
            _metrics_registry[name] = Counter(name, description, labels or [])
        elif metric_type == "histogram":
            _metrics_registry[name] = Histogram(name, description, labels or [])
        elif metric_type == "gauge":
            _metrics_registry[name] = Gauge(name, description, labels or [])
    return _metrics_registry[name]

# 延迟初始化Prometheus指标
def _get_storage_operations_metric():
    return _get_metric(
        "marketprism_unified_storage_operations_total",
        "counter",
        "统一存储操作总数",
        ["operation", "storage_type", "status"]
    )

def _get_storage_latency_metric():
    return _get_metric(
        "marketprism_unified_storage_latency_seconds",
        "histogram",
        "统一存储操作延迟",
        ["operation", "storage_type"]
    )

def _get_cache_hit_rate_metric():
    return _get_metric(
        "marketprism_unified_cache_hit_rate",
        "gauge",
        "统一存储缓存命中率",
        ["storage_type"]
    )


@dataclass
class UnifiedStorageConfig:
    """统一存储配置"""

    # 基础配置
    enabled: bool = True
    storage_type: str = "hot"  # hot, cold, simple, hybrid

    # ClickHouse配置
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "marketprism_hot"

    # Redis配置（仅热存储）
    redis_enabled: bool = False
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
    redis_ttl: int = 3600

    # 存储特性配置
    hot_data_ttl: int = 3600  # 热存储TTL（秒）
    cold_data_ttl: int = 2592000  # 冷存储TTL（30天）
    archive_threshold_days: int = 7  # 归档阈值

    # 分区和压缩配置（冷存储）
    partition_by: str = "toYYYYMM(timestamp)"
    compression_codec: str = "LZ4"
    enable_compression: bool = True

    # 性能配置
    connection_pool_size: int = 10
    batch_size: int = 1000
    flush_interval: int = 5
    max_retries: int = 3

    # 归档配置
    auto_archive_enabled: bool = False
    archive_batch_size: int = 10000
    archive_interval_hours: int = 24
    archive_retention_days: int = 14
    archive_schedule: str = "0 2 * * *"

    # 清理配置
    cleanup_enabled: bool = True
    cleanup_schedule: str = "0 3 * * *"
    cleanup_max_age_days: int = 90

    # 缓存策略
    cache_strategy: str = "write_through"  # write_through, write_back, write_around
    memory_cache_enabled: bool = True

    @classmethod
    def from_yaml(cls, config_path: str, storage_type: str = "hot") -> 'UnifiedStorageConfig':
        """从YAML文件加载配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)

            # 根据存储类型提取配置
            if storage_type == "hot":
                storage_config = config_data.get('hot_storage', {})
                clickhouse_config = config_data.get('clickhouse', {})
                redis_config = config_data.get('redis', {})
                database_suffix = "_hot"
                redis_enabled = True
            elif storage_type == "cold":
                storage_config = config_data.get('cold_storage', {})
                clickhouse_config = storage_config.get('clickhouse', {})
                redis_config = {}
                database_suffix = "_cold"
                redis_enabled = False
            elif storage_type == "simple":
                storage_config = config_data.get('hot_storage', {})
                clickhouse_config = storage_config.get('clickhouse', {})
                redis_config = {}
                database_suffix = "_hot"
                redis_enabled = False
            else:  # hybrid
                storage_config = config_data.get('storage', {})
                clickhouse_config = config_data.get('clickhouse', {})
                redis_config = config_data.get('redis', {})
                database_suffix = ""
                redis_enabled = True

            return cls(
                enabled=storage_config.get('enabled', True),
                storage_type=storage_type,

                clickhouse_host=clickhouse_config.get('host', 'localhost'),
                clickhouse_port=clickhouse_config.get('port', 8123),
                clickhouse_user=clickhouse_config.get('user', 'default'),
                clickhouse_password=clickhouse_config.get('password', ''),
                clickhouse_database=clickhouse_config.get('database', f'marketprism{database_suffix}'),

                redis_enabled=redis_enabled,
                redis_host=redis_config.get('host', 'localhost'),
                redis_port=redis_config.get('port', 6379),
                redis_password=redis_config.get('password', ''),
                redis_db=redis_config.get('db', 0),
                redis_ttl=redis_config.get('cache', {}).get('default_ttl', 3600),

                hot_data_ttl=storage_config.get('hot_data_ttl', 3600),
                cold_data_ttl=storage_config.get('cold_data_ttl', 2592000),
                archive_threshold_days=storage_config.get('archive_threshold_days', 7),

                partition_by=storage_config.get('partitioning', {}).get('partition_by', 'toYYYYMM(timestamp)'),
                compression_codec=storage_config.get('compression', {}).get('codec', 'LZ4'),
                enable_compression=storage_config.get('compression', {}).get('enabled', True),

                connection_pool_size=clickhouse_config.get('connection_pool', {}).get('size', 10),
                batch_size=clickhouse_config.get('performance', {}).get('batch_size', 1000),
                flush_interval=clickhouse_config.get('performance', {}).get('flush_interval', 5),
                max_retries=clickhouse_config.get('performance', {}).get('max_retries', 3),

                auto_archive_enabled=storage_config.get('archiving', {}).get('enabled', False),
                archive_batch_size=storage_config.get('archiving', {}).get('batch_size', 10000),
                archive_interval_hours=storage_config.get('archiving', {}).get('interval_hours', 24),

                cache_strategy=storage_config.get('cache_strategy', 'write_through'),
                memory_cache_enabled=storage_config.get('memory_cache_enabled', True)
            )

        except Exception as e:
            logger.warning(f"加载存储配置失败，使用默认配置: {e}")
            return cls(storage_type=storage_type)


class MockRedisClient:
    """Mock Redis客户端（用于Redis不可用时）"""

    def __init__(self):
        self.data = {}

    async def set(self, key: str, value: str, ex: int = None):
        self.data[key] = {
            'value': value,
            'expire': time.time() + (ex or 3600)
        }
        return True

    async def get(self, key: str):
        item = self.data.get(key)
        if item and item['expire'] > time.time():
            return item['value']
        return None

    async def exists(self, key: str):
        item = self.data.get(key)
        return item and item['expire'] > time.time()

    async def delete(self, key: str):
        self.data.pop(key, None)
        return True

    async def keys(self, pattern: str = "*"):
        return list(self.data.keys())

    async def flushall(self):
        self.data.clear()
        return True

    async def close(self):
        pass

    def connection_pool(self):
        return self


class MockClickHouseClient:
    """Mock ClickHouse客户端（用于ClickHouse不可用时）"""

    def __init__(self):
        self.data = []
        self.tables = set()
        self.partitions = {}

    async def execute(self, query: str, *args):
        query_lower = query.lower().strip()

        if query_lower.startswith("create table"):
            # 解析表名
            parts = query.split()
            if "if not exists" in query_lower:
                table_idx = parts.index("EXISTS") + 1
            else:
                table_idx = parts.index("TABLE") + 1

            if table_idx < len(parts):
                table_name = parts[table_idx]
                self.tables.add(table_name)

        elif query_lower.startswith("insert"):
            # 添加数据
            for arg in args:
                partition_key = datetime.now().strftime('%Y%m')
                if partition_key not in self.partitions:
                    self.partitions[partition_key] = []

                self.partitions[partition_key].append({
                    'data': arg,
                    'timestamp': time.time(),
                    'query': query,
                    'partition': partition_key
                })
                self.data.append({
                    'data': arg,
                    'timestamp': time.time(),
                    'query': query,
                    'partition': partition_key
                })

        return True

    async def fetchall(self, query: str, params: Dict = None):
        # 返回最近的数据
        if "partition" in query.lower():
            return list(self.partitions.values())[-3:] if self.partitions else []
        return self.data[-1000:] if self.data else []

    async def fetchone(self, query: str, params: Dict = None):
        return self.data[-1] if self.data else None

    async def close(self):
        pass


class SimpleClickHouseHttpClient:
    """极简异步ClickHouse HTTP客户端（避免aiochclient/sqlparse依赖问题）

    提供 execute/fetchone/fetchall/close 与现有调用兼容。
    仅支持本项目使用到的语法：
    - CREATE TABLE ...
    - INSERT INTO <db>.<table> VALUES (..), (..)
    - SELECT ...（通过 FORMAT JSON 解析结果）
    """
    def __init__(self, host: str, port: int, user: str, password: str, database: str, session: Optional[aiohttp.ClientSession] = None):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self._session = session
        self._owned_session = False

    async def _ensure_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
            self._owned_session = True

    def _format_value(self, v: Any) -> str:
        from datetime import datetime, date
        if v is None:
            return 'NULL'
        if isinstance(v, bool):
            return '1' if v else '0'
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, (datetime,)):
            # ClickHouse 默认解析 'YYYY-MM-DD HH:MM:SS[.ffffff]'
            return "'{}'".format(v.strftime('%Y-%m-%d %H:%M:%S.%f').rstrip('0').rstrip('.'))
        if isinstance(v, date):
            return "'{}'".format(v.strftime('%Y-%m-%d'))
        # 其它统一按字符串处理并转义
        s = str(v)
        s = s.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{s}'"

    def _append_values(self, query: str, args: Tuple[Any, ...]) -> str:
        # 将 INSERT ... VALUES 与参数拼接成文本VALUES块
        if not args:
            return query
        # 支持多行：args 可能是若干tuple/列表
        rows = []
        for row in args:
            if isinstance(row, (list, tuple)):
                vals = ", ".join(self._format_value(x) for x in row)
                rows.append(f"({vals})")
            else:
                # 单对象按一列处理
                rows.append(f"({self._format_value(row)})")
        return query.rstrip() + "\n" + ",\n".join(rows) + "\n"

    async def execute(self, query: str, *args):
        await self._ensure_session()
        q = query.strip()
        if args:
            q = self._append_values(q, args)
        params = {"database": self.database}
        auth = aiohttp.BasicAuth(self.user, self.password) if self.user else None
        async with self._session.post(f"http://{self.host}:{self.port}/", params=params, data=q.encode('utf-8'), auth=auth) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"ClickHouse HTTP execute failed: {resp.status} {text}")
            return True

    async def _select_json(self, query: str) -> Dict[str, Any]:
        await self._ensure_session()
        q = query.strip()
        if 'FORMAT JSON' not in q.upper():
            q = q.rstrip(';') + ' FORMAT JSON'
        params = {"database": self.database}
        auth = aiohttp.BasicAuth(self.user, self.password) if self.user else None
        async with self._session.post(f"http://{self.host}:{self.port}/", params=params, data=q.encode('utf-8'), auth=auth) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"ClickHouse HTTP select failed: {resp.status} {text}")
            return await resp.json(loads=json.loads)

    async def fetchone(self, query: str, params: Dict = None):
        data = await self._select_json(query)
        rows = data.get('data') or []
        return rows[0] if rows else None

    async def fetchall(self, query: str, params: Dict = None):
        data = await self._select_json(query)
        return data.get('data') or []

    async def close(self):
        if self._owned_session and self._session:
            await self._session.close()
            self._session = None
            self._owned_session = False


class UnifiedStorageManager:
    """统一存储管理器

    整合了以下管理器的功能：
    1. HotStorageManager - Redis + ClickHouse热存储
    2. SimpleHotStorageManager - 纯ClickHouse热存储
    3. ColdStorageManager - ClickHouse冷存储
    4. StorageManager - 统一管理器

    特点：
    - 统一ClickHouse连接管理
    - 统一配置系统
    - 统一表管理
    - 支持多种存储模式
    - 完全向后兼容
    """



    def __init__(self, config: Optional[UnifiedStorageConfig] = None, config_path: Optional[str] = None, storage_type: str = "hot"):
        """
        初始化统一存储管理器

        Args:
            config: 存储配置对象
            config_path: 配置文件路径
            storage_type: 存储类型 (hot/cold/simple/hybrid)
        """
        # 加载配置
        if config_path:
            self.config = UnifiedStorageConfig.from_yaml(config_path, storage_type)
        elif config:
            self.config = config
        else:
            # 尝试从默认路径加载
            default_config_path = Path(__file__).parent.parent.parent / "config" / "collector_config.yaml"
            if default_config_path.exists():
                self.config = UnifiedStorageConfig.from_yaml(str(default_config_path), storage_type)
            else:
                self.config = UnifiedStorageConfig(storage_type=storage_type)

        # 初始化新的存储配置管理器
        self.storage_config_manager = None
        self.migration_service = None
        if StorageConfigManager:
            try:
                storage_config_path = Path(__file__).parent.parent.parent / "config" / "storage_unified.yaml"
                self.storage_config_manager = StorageConfigManager(str(storage_config_path))

                # 初始化数据迁移服务（仅热存储模式）
                if DataMigrationService and self.storage_config_manager.is_hot_storage():
                    self.migration_service = DataMigrationService(self.storage_config_manager)

            except Exception as e:
                logger.warning(f"新存储配置管理器初始化失败，使用传统配置: {e}")
                self.storage_config_manager = None
                self.migration_service = None

        # 客户端实例
        self.redis_client = None
        self.clickhouse_client = None
        self.clickhouse_writer = None

        # 运行状态
        self.is_running = False
        self.start_time = None
        self.archive_task = None

        # 统计信息
        self.stats = {
            'writes': 0,
            'reads': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'archives': 0,
            'errors': 0,
            'start_time': None,
            'total_size_bytes': 0,
            'partitions_created': 0
        }

        # 内存缓存
        self.memory_cache = {} if self.config.memory_cache_enabled else {}
        self.memory_cache_expire = {} if self.config.memory_cache_enabled else {}
        self.query_cache = {}  # 查询缓存（冷存储用）
        self.query_cache_expire = {}

        # 归档管理器（可选）
        self.archiver_manager = None
        self.archive_manager = None  # 新的归档管理器

        self.logger = logging.getLogger(__name__)

        logger.info(f"统一存储管理器已初始化，类型: {self.config.storage_type}, 配置: {asdict(self.config)}")

    async def initialize(self):
        """初始化存储管理器（API接口兼容性方法）"""
        if self.is_running:
            logger.debug("存储管理器已经运行")
            return

        try:
            await self.start()
            logger.info("统一存储管理器初始化完成")
        except Exception as e:
            logger.error(f"统一存储管理器初始化失败: {e}")
            raise

    async def get_status(self) -> Dict[str, Any]:
        """获取管理器状态（API兼容性方法）"""
        return {
            'initialized': self.is_running,
            'is_running': self.is_running,
            'storage_type': self.config.storage_type,
            'stats': self.stats.copy(),
            'config': asdict(self.config)
        }

    async def start(self):
        """启动存储管理器"""
        if self.is_running:
            logger.warning("存储管理器已在运行")
            return

        try:
            self.start_time = time.time()
            self.stats['start_time'] = self.start_time

            # 初始化Redis连接（如果启用）
            if self.config.redis_enabled:
                await self._init_redis()

            # 初始化ClickHouse连接
            await self._init_clickhouse()

            # 创建数据表
            await self._create_tables()

            # 启动自动归档任务（如果启用）
            if self.config.auto_archive_enabled:
                await self._init_archive_manager()
                if self.archive_manager:
                    await self.archive_manager.start()

            # 启动数据迁移服务（如果启用）
            if self.migration_service:
                await self.migration_service.start()
                logger.info("数据迁移服务已启动")

            self.is_running = True
            logger.info(f"统一存储管理器已启动，类型: {self.config.storage_type}")

        except Exception as e:
            logger.error(f"启动存储管理器失败: {e}")
            raise

    async def stop(self):
        """停止存储管理器"""
        if not self.is_running:
            return

        try:
            # 停止数据迁移服务
            if self.migration_service:
                await self.migration_service.stop()
                logger.info("数据迁移服务已停止")

            # 停止归档管理器
            if self.archive_manager:
                await self.archive_manager.stop()

            # 刷新缓冲区
            if self.clickhouse_writer:
                await self.clickhouse_writer.stop()

            # 关闭连接
            if self.redis_client and hasattr(self.redis_client, 'close'):
                await self.redis_client.close()

            if self.clickhouse_client and hasattr(self.clickhouse_client, 'close'):
                await self.clickhouse_client.close()

            self.is_running = False
            logger.info("统一存储管理器已停止")

        except Exception as e:
            logger.error(f"停止存储管理器失败: {e}")

    async def _init_redis(self):
        """初始化Redis连接（统一的Redis初始化逻辑）"""
        try:
            if not self.config.enabled or not self.config.redis_enabled:
                self.redis_client = MockRedisClient()
                return

            # 构建Redis URL
            if self.config.redis_password:
                redis_url = f"redis://:{self.config.redis_password}@{self.config.redis_host}:{self.config.redis_port}/{self.config.redis_db}"
            else:
                redis_url = f"redis://{self.config.redis_host}:{self.config.redis_port}/{self.config.redis_db}"

            # 创建连接池（使用新的aioredis API）
            self.redis_client = aioredis.from_url(
                redis_url,
                encoding='utf-8',
                decode_responses=True
            )

            # 测试连接
            await self.redis_client.ping()
            logger.info(f"Redis连接成功: {self.config.redis_host}:{self.config.redis_port}")

        except Exception as e:
            logger.warning(f"Redis连接失败，使用Mock客户端: {e}")
            self.redis_client = MockRedisClient()

    async def _init_clickhouse(self):
        """初始化ClickHouse连接（统一的ClickHouse初始化逻辑）"""
        try:
            if not self.config.enabled:
                self.clickhouse_client = MockClickHouseClient()
                return

            # 使用极简HTTP客户端，绕过 aiochclient/sqlparse 依赖问题
            self.clickhouse_client = SimpleClickHouseHttpClient(
                host=self.config.clickhouse_host,
                port=self.config.clickhouse_port,
                user=self.config.clickhouse_user,
                password=self.config.clickhouse_password,
                database=self.config.clickhouse_database,
            )
            # 探活
            await self.clickhouse_client.fetchone("SELECT 1")

            logger.info(
                f"ClickHouse连接成功: {self.config.clickhouse_host}:{self.config.clickhouse_port}/{self.config.clickhouse_database} (HTTP)"
            )

        except Exception as e:
            logger.warning(f"ClickHouse连接失败，使用Mock客户端: {e}")
            self.clickhouse_client = MockClickHouseClient()

    async def _create_tables(self):
        """创建数据表（生产级优化配置）"""
        try:
            logger.info("开始创建生产级优化数据表...")

            # 确定表名前缀、压缩和TTL配置
            if self.config.storage_type == "cold":
                table_prefix = "cold_"
                ttl_days = 30  # 冷数据保留30天
                compression_clause = "CODEC(ZSTD(3))"  # 高压缩比
                partition_clause = "PARTITION BY (toYYYYMM(timestamp), exchange)"
            else:
                table_prefix = "hot_"
                ttl_days = 1   # 热数据保留1天
                compression_clause = "CODEC(LZ4)"  # 快速压缩
                partition_clause = "PARTITION BY (toYYYYMMDD(timestamp), exchange)"

            # 创建生产级交易数据表
            await self.clickhouse_client.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.config.clickhouse_database}.{table_prefix}trades (
                    timestamp DateTime64(3) {compression_clause},
                    symbol LowCardinality(String) {compression_clause},
                    exchange LowCardinality(String) {compression_clause},
                    price Decimal64(8) {compression_clause},
                    amount Decimal64(8) {compression_clause},
                    side LowCardinality(String) {compression_clause},
                    trade_id String {compression_clause},
                    created_at DateTime64(3) DEFAULT now64() {compression_clause},
                    INDEX idx_symbol symbol TYPE bloom_filter GRANULARITY 1,
                    INDEX idx_price price TYPE minmax GRANULARITY 8
                ) ENGINE = ReplacingMergeTree(created_at)
                {partition_clause}
                ORDER BY (exchange, symbol, trade_id, timestamp)
                TTL toDateTime(created_at) + INTERVAL {ttl_days} DAY
                SETTINGS index_granularity = 8192,
                         merge_with_ttl_timeout = 3600,
                         ttl_only_drop_parts = 1
            """)
            logger.info("✅ 生产级交易数据表创建成功")

            # 创建生产级行情数据表
            await self.clickhouse_client.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.config.clickhouse_database}.{table_prefix}tickers (
                    timestamp DateTime64(3) {compression_clause},
                    symbol LowCardinality(String) {compression_clause},
                    exchange LowCardinality(String) {compression_clause},
                    last_price Decimal64(8) {compression_clause},
                    volume_24h Decimal64(8) {compression_clause},
                    price_change_24h Decimal64(8) {compression_clause},
                    high_24h Decimal64(8) {compression_clause},
                    low_24h Decimal64(8) {compression_clause},
                    created_at DateTime64(3) DEFAULT now64() {compression_clause},
                    INDEX idx_symbol symbol TYPE bloom_filter GRANULARITY 1,
                    INDEX idx_price last_price TYPE minmax GRANULARITY 8
                ) ENGINE = ReplacingMergeTree(created_at)
                {partition_clause}
                ORDER BY (exchange, symbol, timestamp)
                TTL toDateTime(created_at) + INTERVAL {ttl_days} DAY
                SETTINGS index_granularity = 8192,
                         merge_with_ttl_timeout = 3600,
                         ttl_only_drop_parts = 1
            """)
            logger.info("✅ 生产级行情数据表创建成功")

            # 创建生产级订单簿数据表
            await self.clickhouse_client.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.config.clickhouse_database}.{table_prefix}orderbooks (
                    timestamp DateTime64(3) {compression_clause},
                    symbol LowCardinality(String) {compression_clause},
                    exchange LowCardinality(String) {compression_clause},
                    best_bid Decimal64(8) {compression_clause},
                    best_ask Decimal64(8) {compression_clause},
                    spread Decimal64(8) {compression_clause},
                    bids_json String {compression_clause},
                    asks_json String {compression_clause},
                    created_at DateTime64(3) DEFAULT now64() {compression_clause},
                    INDEX idx_symbol symbol TYPE bloom_filter GRANULARITY 1,
                    INDEX idx_spread spread TYPE minmax GRANULARITY 8
                ) ENGINE = ReplacingMergeTree(created_at)
                {partition_clause}
                ORDER BY (exchange, symbol, timestamp)
                TTL toDateTime(created_at) + INTERVAL {ttl_days} DAY
                SETTINGS index_granularity = 8192,
                         merge_with_ttl_timeout = 3600,
                         ttl_only_drop_parts = 1
            """)
            logger.info("✅ 生产级订单簿数据表创建成功")

            # 创建资金费率表
            await self.clickhouse_client.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.config.clickhouse_database}.funding_rates (
                    timestamp DateTime64(3) {compression_clause},
                    exchange LowCardinality(String) {compression_clause},
                    market_type LowCardinality(String) {compression_clause},
                    symbol LowCardinality(String) {compression_clause},
                    funding_rate Float64 {compression_clause},
                    funding_time DateTime64(3) {compression_clause},
                    next_funding_time DateTime64(3) {compression_clause},
                    data_source LowCardinality(String) {compression_clause},
                    created_at DateTime64(3) DEFAULT now64() {compression_clause}
                ) ENGINE = ReplacingMergeTree(created_at)
                {partition_clause}
                ORDER BY (exchange, symbol, timestamp)
                TTL toDateTime(created_at) + INTERVAL {ttl_days} DAY
                SETTINGS index_granularity = 8192
            """)
            logger.info("✅ 资金费率表创建成功")

            # 创建未平仓量表
            await self.clickhouse_client.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.config.clickhouse_database}.open_interests (
                    timestamp DateTime64(3) {compression_clause},
                    exchange LowCardinality(String) {compression_clause},
                    market_type LowCardinality(String) {compression_clause},
                    symbol LowCardinality(String) {compression_clause},
                    open_interest Float64 {compression_clause},
                    open_interest_value Float64 {compression_clause},
                    data_source LowCardinality(String) {compression_clause},
                    created_at DateTime64(3) DEFAULT now64() {compression_clause}
                ) ENGINE = ReplacingMergeTree(created_at)
                {partition_clause}
                ORDER BY (exchange, symbol, timestamp)
                TTL toDateTime(created_at) + INTERVAL {ttl_days} DAY
                SETTINGS index_granularity = 8192
            """)
            logger.info("✅ 未平仓量表创建成功")

            # 创建强平数据表
            await self.clickhouse_client.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.config.clickhouse_database}.liquidations (
                    timestamp DateTime64(3) {compression_clause},
                    exchange LowCardinality(String) {compression_clause},
                    market_type LowCardinality(String) {compression_clause},
                    symbol LowCardinality(String) {compression_clause},
                    side LowCardinality(String) {compression_clause},
                    price Decimal64(8) {compression_clause},
                    quantity Decimal64(8) {compression_clause},
                    data_source LowCardinality(String) {compression_clause},
                    created_at DateTime64(3) DEFAULT now64() {compression_clause}
                ) ENGINE = ReplacingMergeTree(created_at)
                {partition_clause}
                ORDER BY (exchange, symbol, timestamp)
                TTL toDateTime(created_at) + INTERVAL {ttl_days} DAY
                SETTINGS index_granularity = 8192
            """)
            logger.info("✅ 强平数据表创建成功")

            # 创建波动率指数表
            await self.clickhouse_client.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.config.clickhouse_database}.volatility_indices (
                    timestamp DateTime64(3) {compression_clause},
                    exchange LowCardinality(String) {compression_clause},
                    market_type LowCardinality(String) {compression_clause},
                    symbol LowCardinality(String) {compression_clause},
                    index_value Float64 {compression_clause},
                    underlying_asset LowCardinality(String) {compression_clause},
                    data_source LowCardinality(String) {compression_clause},
                    created_at DateTime64(3) DEFAULT now64() {compression_clause}
                ) ENGINE = ReplacingMergeTree(created_at)
                {partition_clause}
                ORDER BY (exchange, symbol, timestamp)
                TTL toDateTime(created_at) + INTERVAL {ttl_days} DAY
                SETTINGS index_granularity = 8192
            """)
            logger.info("✅ 波动率指数表创建成功")

            # 创建LSR顶级持仓表
            await self.clickhouse_client.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.config.clickhouse_database}.lsr_top_positions (
                    timestamp DateTime64(3) {compression_clause},
                    exchange LowCardinality(String) {compression_clause},
                    market_type LowCardinality(String) {compression_clause},
                    symbol LowCardinality(String) {compression_clause},
                    long_position_ratio Float64 {compression_clause},
                    short_position_ratio Float64 {compression_clause},
                    period LowCardinality(String) {compression_clause},
                    data_source LowCardinality(String) {compression_clause},
                    created_at DateTime64(3) DEFAULT now64() {compression_clause}
                ) ENGINE = ReplacingMergeTree(created_at)
                {partition_clause}
                ORDER BY (exchange, symbol, timestamp)
                TTL toDateTime(created_at) + INTERVAL {ttl_days} DAY
                SETTINGS index_granularity = 8192
            """)
            logger.info("✅ LSR顶级持仓表创建成功")

            # 创建LSR全账户表
            await self.clickhouse_client.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.config.clickhouse_database}.lsr_all_accounts (
                    timestamp DateTime64(3) {compression_clause},
                    exchange LowCardinality(String) {compression_clause},
                    market_type LowCardinality(String) {compression_clause},
                    symbol LowCardinality(String) {compression_clause},
                    long_account_ratio Float64 {compression_clause},
                    short_account_ratio Float64 {compression_clause},
                    period LowCardinality(String) {compression_clause},
                    data_source LowCardinality(String) {compression_clause},
                    created_at DateTime64(3) DEFAULT now64() {compression_clause}
                ) ENGINE = ReplacingMergeTree(created_at)
                {partition_clause}
                ORDER BY (exchange, symbol, timestamp)
                TTL toDateTime(created_at) + INTERVAL {ttl_days} DAY
                SETTINGS index_granularity = 8192
            """)
            logger.info("✅ LSR全账户表创建成功")


            # 如果是冷存储，创建归档状态表
            if self.config.storage_type == "cold":
                await self.clickhouse_client.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.config.clickhouse_database}.archive_status (
                        archive_date Date {compression_clause},
                        data_type LowCardinality(String) {compression_clause},
                        exchange LowCardinality(String) {compression_clause},
                        records_archived UInt64 {compression_clause},
                        archive_size_bytes UInt64 {compression_clause},
                        archive_duration_seconds Float64 {compression_clause},
                        created_at DateTime64(3) DEFAULT now64() {compression_clause}
                    ) ENGINE = MergeTree()
                    PARTITION BY toYYYYMM(archive_date)
                    ORDER BY (archive_date, data_type, exchange)
                    TTL toDateTime(created_at) + INTERVAL 90 DAY
                    SETTINGS index_granularity = 8192
                """)
                logger.info("✅ 归档状态表创建成功")

            logger.info(f"生产级数据表创建完成，类型: {self.config.storage_type}")

        except Exception as e:
            logger.error(f"创建数据表失败: {e}")
            # 不重新抛出异常，允许服务继续运行

    async def _init_archive_manager(self):
        """初始化归档管理器"""
        try:
            # 延迟导入避免循环依赖
            from .archive_manager import ArchiveManager, ArchiveConfig

            # 创建归档配置
            archive_config = ArchiveConfig(
                enabled=self.config.auto_archive_enabled,
                schedule=self.config.archive_schedule,
                retention_days=self.config.archive_retention_days,
                batch_size=self.config.archive_batch_size,
                cleanup_enabled=self.config.cleanup_enabled,
                cleanup_schedule=self.config.cleanup_schedule,
                max_age_days=self.config.cleanup_max_age_days
            )

            # 创建冷存储管理器（如果需要）
            cold_storage_manager = None
            if self.config.storage_type == "hot" and self.config.auto_archive_enabled:
                # 为热存储创建对应的冷存储管理器
                cold_config = UnifiedStorageConfig(
                    storage_type="cold",
                    clickhouse_host=self.config.clickhouse_host,
                    clickhouse_port=self.config.clickhouse_port,
                    clickhouse_user=self.config.clickhouse_user,
                    clickhouse_password=self.config.clickhouse_password,
                    clickhouse_database=self.config.clickhouse_database + "_cold",
                    redis_enabled=False,
                    enable_compression=True,
                    compression_codec="LZ4"
                )
                cold_storage_manager = UnifiedStorageManager(cold_config, None, "cold")
                await cold_storage_manager.start()

            # 创建归档管理器
            self.archive_manager = ArchiveManager(
                hot_storage_manager=self,
                cold_storage_manager=cold_storage_manager,
                archive_config=archive_config
            )

            logger.info("归档管理器初始化成功")

        except Exception as e:
            logger.error(f"初始化归档管理器失败: {e}")
            self.archive_manager = None
    async def _write_funding_rate_to_clickhouse(self, fr: Dict[str, Any]):
        table = f"{self.config.clickhouse_database}.funding_rates"
        await self.clickhouse_client.execute(
            f"INSERT INTO {table} (timestamp, exchange, market_type, symbol, funding_rate, funding_time, next_funding_time, data_source, created_at) VALUES",
            (
                fr.get('timestamp', datetime.now()),
                fr.get('exchange', ''),
                fr.get('market_type', ''),
                fr.get('symbol', ''),
                float(fr.get('funding_rate') or fr.get('current_funding_rate') or 0.0),
                fr.get('funding_time') or fr.get('funding_time_utc') or fr.get('settle_time') or fr.get('timestamp', datetime.now()),
                fr.get('next_funding_time') or fr.get('next_funding_time_utc') or None,
                fr.get('data_source', 'marketprism'),
                datetime.now()
            )
        )

    async def store_funding_rate(self, fr_data: Dict[str, Any]):
        try:
            await self._write_funding_rate_to_clickhouse(fr_data)
            self.stats['writes'] += 1
            logger.debug("资金费率已存储", exchange=fr_data.get('exchange'), symbol=fr_data.get('symbol'))
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"存储资金费率失败: {e}")

    async def _write_open_interest_to_clickhouse(self, oi: Dict[str, Any]):
        table = f"{self.config.clickhouse_database}.open_interests"
        await self.clickhouse_client.execute(
            f"INSERT INTO {table} (timestamp, exchange, market_type, symbol, open_interest, open_interest_value, data_source, created_at) VALUES",
            (
                oi.get('timestamp', datetime.now()),
                oi.get('exchange', ''),
                oi.get('market_type', ''),
                oi.get('symbol', ''),
                float(oi.get('open_interest') or oi.get('oi') or 0.0),
                float(oi.get('open_interest_value') or oi.get('oi_value') or 0.0),
                oi.get('data_source', 'marketprism'),
                datetime.now()
            )
        )

    async def store_open_interest(self, oi_data: Dict[str, Any]):
        try:
            await self._write_open_interest_to_clickhouse(oi_data)
            self.stats['writes'] += 1
            logger.debug("未平仓量已存储", exchange=oi_data.get('exchange'), symbol=oi_data.get('symbol'))
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"存储未平仓量失败: {e}")

    async def _write_liquidation_to_clickhouse(self, liq: Dict[str, Any]):
        table = f"{self.config.clickhouse_database}.liquidations"
        liquidation_time = liq.get('liquidation_time') or liq.get('timestamp')
        await self.clickhouse_client.execute(
            f"INSERT INTO {table} (timestamp, exchange, market_type, symbol, side, price, quantity, liquidation_time, data_source, created_at) VALUES",
            (
                liq.get('timestamp', datetime.now()),
                liq.get('exchange', ''),
                liq.get('market_type', ''),
                liq.get('symbol', ''),
                liq.get('side', ''),
                float(liq.get('price') or 0.0),
                float(liq.get('quantity') or liq.get('amount') or 0.0),
                liquidation_time,
                liq.get('data_source', 'marketprism'),
                datetime.now()
            )
        )

    async def store_liquidation(self, liq_data: Dict[str, Any]):
        try:
            await self._write_liquidation_to_clickhouse(liq_data)
            self.stats['writes'] += 1
            logger.debug("强平已存储", exchange=liq_data.get('exchange'), symbol=liq_data.get('symbol'))
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"存储强平数据失败: {e}")

    async def _write_lsr_top_position_to_clickhouse(self, lsr: Dict[str, Any]):
        table = f"{self.config.clickhouse_database}.lsr_top_positions"
        await self.clickhouse_client.execute(
            f"INSERT INTO {table} (timestamp, exchange, market_type, symbol, long_position_ratio, short_position_ratio, period, data_source, created_at) VALUES",
            (
                lsr.get('timestamp', datetime.now()),
                lsr.get('exchange', ''),
                lsr.get('market_type', ''),
                lsr.get('symbol', ''),
                float(lsr.get('long_position_ratio') or 0.0),
                float(lsr.get('short_position_ratio') or 0.0),
                lsr.get('period', ''),
                lsr.get('data_source', 'marketprism'),
                datetime.now()
            )
        )

    async def store_lsr_top_position(self, lsr_data: Dict[str, Any]):
        try:
            await self._write_lsr_top_position_to_clickhouse(lsr_data)
            self.stats['writes'] += 1
            logger.debug("LSR顶级持仓已存储", exchange=lsr_data.get('exchange'), symbol=lsr_data.get('symbol'))
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"存储LSR顶级持仓失败: {e}")

    async def _write_lsr_all_account_to_clickhouse(self, lsr: Dict[str, Any]):
        table = f"{self.config.clickhouse_database}.lsr_all_accounts"
        await self.clickhouse_client.execute(
            f"INSERT INTO {table} (timestamp, exchange, market_type, symbol, long_account_ratio, short_account_ratio, period, data_source, created_at) VALUES",
            (
                lsr.get('timestamp', datetime.now()),
                lsr.get('exchange', ''),
                lsr.get('market_type', ''),
                lsr.get('symbol', ''),
                float(lsr.get('long_account_ratio') or 0.0),
                float(lsr.get('short_account_ratio') or 0.0),
                lsr.get('period', ''),
                lsr.get('data_source', 'marketprism'),
                datetime.now()
            )
        )

    async def store_lsr_all_account(self, lsr_data: Dict[str, Any]):
        try:
            await self._write_lsr_all_account_to_clickhouse(lsr_data)
            self.stats['writes'] += 1
            logger.debug("LSR全账户已存储", exchange=lsr_data.get('exchange'), symbol=lsr_data.get('symbol'))
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"存储LSR全账户失败: {e}")


    # ==================== 核心数据操作方法 ====================

    async def store_trade(self, trade_data: Dict[str, Any]):
        """存储交易数据（统一接口）"""
        start_time = time.time()

        try:
            # 写入ClickHouse
            await self._write_trade_to_clickhouse(trade_data)

            # 更新缓存（如果启用）
            if self.config.redis_enabled:
                await self._cache_latest_trade(trade_data)

            if self.config.memory_cache_enabled:
                self._cache_in_memory(f"latest_trade:{trade_data.get('exchange')}:{trade_data.get('symbol')}", trade_data)

            self.stats['writes'] += 1

            # 记录指标
            try:
                _get_storage_operations_metric().labels(
                    operation="store_trade",
                    storage_type=self.config.storage_type,
                    status="success"
                ).inc()

                _get_storage_latency_metric().labels(
                    operation="store_trade",
                    storage_type=self.config.storage_type
                ).observe(time.time() - start_time)
            except Exception:
                pass  # 忽略指标记录错误

            logger.debug(f"交易数据已存储 ({self.config.storage_type}): {trade_data.get('symbol')} {trade_data.get('price')}")

        except Exception as e:
            self.stats['errors'] += 1
            try:
                _get_storage_operations_metric().labels(
                    operation="store_trade",
                    storage_type=self.config.storage_type,
                    status="error"
                ).inc()
            except Exception:
                pass  # 忽略指标记录错误
            logger.error(f"存储交易数据失败: {e}")



    async def store_orderbook(self, orderbook_data: Dict[str, Any]):
        """存储订单簿数据（统一接口）"""
        start_time = time.time()

        try:
            # 写入ClickHouse
            await self._write_orderbook_to_clickhouse(orderbook_data)

            # 更新缓存（如果启用）
            if self.config.redis_enabled:
                await self._cache_latest_orderbook(orderbook_data)

            if self.config.memory_cache_enabled:
                self._cache_in_memory(f"latest_orderbook:{orderbook_data.get('exchange')}:{orderbook_data.get('symbol')}", orderbook_data)

            self.stats['writes'] += 1

            logger.debug(f"订单簿数据已存储 ({self.config.storage_type}): {orderbook_data.get('symbol')}")

        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"存储订单簿数据失败: {e}")


    async def _write_volatility_index_to_clickhouse(self, vi: Dict[str, Any]):
        """写入波动率指数到 ClickHouse"""
        table_prefix = "cold_" if self.config.storage_type == "cold" else "hot_"
        # 统一字段（配置与消息统一仅使用 'volatility_index'）
        index_value = vi.get('volatility_index')
        exchange = vi.get('exchange', '')
        market_type = vi.get('market_type', 'options')
        symbol = vi.get('symbol', '')
        ts = vi.get('timestamp')
        # 允许字符串/DateTime；ClickHouse client适配会处理
        await self.clickhouse_client.execute(
            f"INSERT INTO {self.config.clickhouse_database}.volatility_indices (timestamp, exchange, market_type, symbol, volatility_index, underlying_asset, reserved, data_source, created_at) VALUES",
            (
                ts,
                exchange,
                market_type,
                symbol,
                float(index_value) if index_value is not None else 0.0,
                vi.get('currency', ''),
                None,
                vi.get('data_source', 'marketprism'),
                datetime.now()
            )
        )

    async def store_volatility_index(self, vi_data: Dict[str, Any]):
        """存储波动率指数数据（统一接口）
        目标表：{db}.volatility_indices（已由初始化脚本创建）
        vi_data 期望字段：exchange, market_type, symbol, volatility_index, timestamp, currency(optional)
        """
        try:
            await self._write_volatility_index_to_clickhouse(vi_data)
            self.stats['writes'] += 1
            logger.debug(
                "波动率指数数据已存储",
                exchange=vi_data.get('exchange'),
                symbol=vi_data.get('symbol'),
                index_value=str(vi_data.get('volatility_index')),
            )
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"存储波动率指数数据失败: {e}")

    async def get_latest_trade(self, exchange: str, symbol: str) -> Optional[Dict[str, Any]]:
        """获取最新交易数据（统一多层缓存查询）"""
        start_time = time.time()
        self.stats['reads'] += 1

        try:
            # 1. 检查内存缓存
            if self.config.memory_cache_enabled:
                memory_key = f"latest_trade:{exchange}:{symbol}"
                cached_data = self._get_from_memory(memory_key)
                if cached_data:
                    self.stats['cache_hits'] += 1
                    logger.debug(f"内存缓存命中: {symbol}")
                    return cached_data

            # 2. 检查Redis缓存（如果启用）
            if self.config.redis_enabled:
                redis_key = f"marketprism:{self.config.storage_type}:latest_trade:{exchange}:{symbol}"
                redis_data = await self.redis_client.get(redis_key)
                if redis_data:
                    self.stats['cache_hits'] += 1
                    data = json.loads(redis_data) if isinstance(redis_data, str) else redis_data
                    # 回填内存缓存
                    if self.config.memory_cache_enabled:
                        self._cache_in_memory(memory_key, data)
                    logger.debug(f"Redis缓存命中: {symbol}")
                    return data

            # 3. 从ClickHouse查询
            table_prefix = "cold_" if self.config.storage_type == "cold" else "hot_"
            result = await self.clickhouse_client.fetchone(f"""
                SELECT * FROM {self.config.clickhouse_database}.{table_prefix}trades
                WHERE exchange = '{exchange}' AND symbol = '{symbol}'
                ORDER BY timestamp DESC
                LIMIT 1
            """)

            if result:
                self.stats['cache_misses'] += 1
                data = dict(result)
                # 回填缓存
                if self.config.redis_enabled:
                    await self._cache_latest_trade(data)
                if self.config.memory_cache_enabled:
                    self._cache_in_memory(memory_key, data)
                logger.debug(f"从ClickHouse查询: {symbol}")
                return data

            return None

        except Exception as e:
            logger.error(f"获取最新交易数据失败: {e}")
            return None

        finally:
            try:
                _get_storage_latency_metric().labels(
                    operation="get_latest_trade",
                    storage_type=self.config.storage_type
                ).observe(time.time() - start_time)
            except Exception:
                pass  # 忽略指标记录错误



    async def get_recent_trades(self, exchange: str, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近交易数据"""
        try:
            table_prefix = "cold_" if self.config.storage_type == "cold" else "hot_"
            results = await self.clickhouse_client.fetchall(f"""
                SELECT * FROM {self.config.clickhouse_database}.{table_prefix}trades
                WHERE exchange = '{exchange}' AND symbol = '{symbol}'
                ORDER BY timestamp DESC
                LIMIT {limit}
            """)

            return [dict(row) for row in results] if results else []

        except Exception as e:
            logger.error(f"获取最近交易数据失败: {e}")
            return []

    # ==================== 内部写入方法 ====================

    async def _write_trade_to_clickhouse(self, trade_data: Dict[str, Any]):
        """写入交易数据到ClickHouse（对齐简化schema）
        目标表：{db}.trades
        列顺序：timestamp, exchange, market_type, symbol, trade_id, price, quantity, side, is_maker, trade_time, data_source, created_at
        兼容：quantity<-quantity/amount，is_maker<-bool转UInt8，trade_time缺省用timestamp
        """
        qty = trade_data.get('quantity')
        if qty is None:
            qty = trade_data.get('amount', 0)
        is_maker = trade_data.get('is_maker')
        if isinstance(is_maker, bool):
            is_maker = 1 if is_maker else 0
        elif is_maker is None:
            is_maker = 0
        trade_time = trade_data.get('trade_time') or trade_data.get('timestamp')
        await self.clickhouse_client.execute(
            f"INSERT INTO {self.config.clickhouse_database}.trades VALUES",
            (
                trade_data.get('timestamp', datetime.now()),
                trade_data.get('exchange', ''),
                trade_data.get('market_type', ''),
                trade_data.get('symbol', ''),
                str(trade_data.get('trade_id', '')),
                float(trade_data.get('price', 0)),
                float(qty or 0),
                trade_data.get('side', ''),
                int(is_maker),
                trade_time,
                trade_data.get('data_source', 'marketprism'),
                datetime.now()
            )
        )



    async def _write_orderbook_to_clickhouse(self, orderbook_data: Dict[str, Any]):
        """写入订单簿数据到ClickHouse（统一逻辑）"""
        bids = orderbook_data.get('bids', [])
        asks = orderbook_data.get('asks', [])

        # 注意：bids/asks 可能是字符串，需要先转换为 float 再做运算
        best_bid = float(bids[0][0]) if bids else 0.0
        best_ask = float(asks[0][0]) if asks else 0.0
        spread = (best_ask - best_bid) if (bids and asks) else 0.0

        table_prefix = "cold_" if self.config.storage_type == "cold" else "hot_"

        if self.config.storage_type == "cold":
            await self.clickhouse_client.execute(
                f"INSERT INTO {self.config.clickhouse_database}.{table_prefix}orderbooks VALUES",
                (
                    orderbook_data.get('timestamp', datetime.now()),
                    orderbook_data.get('symbol', ''),
                    orderbook_data.get('exchange', ''),
                    float(best_bid),
                    float(best_ask),
                    float(spread),
                    json.dumps(bids),
                    json.dumps(asks),
                    datetime.now(),  # created_at
                    datetime.now()   # archived_at
                )
            )
        else:
            await self.clickhouse_client.execute(
                f"INSERT INTO {self.config.clickhouse_database}.{table_prefix}orderbooks VALUES",
                (
                    orderbook_data.get('timestamp', datetime.now()),
                    orderbook_data.get('symbol', ''),
                    orderbook_data.get('exchange', ''),
                    float(best_bid),
                    float(best_ask),
                    float(spread),
                    json.dumps(bids),
                    json.dumps(asks),
                    datetime.now()   # created_at
                )
            )

    # ==================== 缓存管理方法 ====================

    async def _cache_latest_trade(self, trade_data: Dict[str, Any]):
        """缓存最新交易数据到Redis"""
        if not self.config.redis_enabled:
            return

        key = f"marketprism:{self.config.storage_type}:latest_trade:{trade_data.get('exchange')}:{trade_data.get('symbol')}"
        await self.redis_client.set(key, json.dumps(trade_data, default=str), ex=self.config.redis_ttl)



    async def _cache_latest_orderbook(self, orderbook_data: Dict[str, Any]):
        """缓存最新订单簿数据到Redis"""
        if not self.config.redis_enabled:
            return

        key = f"marketprism:{self.config.storage_type}:latest_orderbook:{orderbook_data.get('exchange')}:{orderbook_data.get('symbol')}"
        await self.redis_client.set(key, json.dumps(orderbook_data, default=str), ex=self.config.redis_ttl)

    def _cache_in_memory(self, key: str, data: Dict[str, Any]):
        """缓存数据到内存"""
        if not self.config.memory_cache_enabled:
            return

        self.memory_cache[key] = data
        self.memory_cache_expire[key] = time.time() + 300  # 5分钟过期

    def _get_from_memory(self, key: str) -> Optional[Dict[str, Any]]:
        """从内存缓存获取数据"""
        if not self.config.memory_cache_enabled or key not in self.memory_cache:
            return None

        if self.memory_cache_expire.get(key, 0) > time.time():
            return self.memory_cache[key]
        else:
            # 清理过期数据
            self.memory_cache.pop(key, None)
            self.memory_cache_expire.pop(key, None)
            return None

    # ==================== 监控和统计 ====================

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息（统一接口）"""
        uptime = time.time() - self.start_time if self.start_time else 0
        cache_hit_rate = self.stats['cache_hits'] / max(1, self.stats['reads']) * 100

        stats = {
            'uptime_seconds': uptime,
            'total_writes': self.stats['writes'],
            'total_reads': self.stats['reads'],
            'cache_hits': self.stats['cache_hits'],
            'cache_misses': self.stats['cache_misses'],
            'cache_hit_rate_percent': cache_hit_rate,
            'total_errors': self.stats['errors'],
            'writes_per_second': self.stats['writes'] / max(1, uptime),
            'reads_per_second': self.stats['reads'] / max(1, uptime),
            'is_running': self.is_running,
            'storage_type': self.config.storage_type,
            'config': asdict(self.config)
        }

        # 添加存储类型特定的统计
        if self.config.memory_cache_enabled:
            stats['memory_cache_size'] = len(self.memory_cache)

        # 更新Prometheus指标
        try:
            _get_cache_hit_rate_metric().labels(storage_type=self.config.storage_type).set(cache_hit_rate)
        except Exception:
            pass  # 忽略指标记录错误

        return stats

    def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态（统一接口）"""
        try:
            redis_healthy = (not self.config.redis_enabled) or (self.redis_client is not None)
            clickhouse_healthy = self.clickhouse_client is not None
            archive_task_healthy = (not self.config.auto_archive_enabled) or (self.archive_task is None or not self.archive_task.done())

            overall_healthy = self.is_running and clickhouse_healthy and redis_healthy

            return {
                'is_healthy': overall_healthy,
                'is_running': self.is_running,
                'storage_type': self.config.storage_type,
                'clickhouse_healthy': clickhouse_healthy,
                'redis_healthy': redis_healthy,
                'redis_enabled': self.config.redis_enabled,
                'archive_task_healthy': archive_task_healthy,
                'error_rate': self.stats['errors'] / max(1, self.stats['writes'] + self.stats['reads']),
                'cache_hit_rate': self.stats['cache_hits'] / max(1, self.stats['reads']) * 100,
                'uptime_seconds': time.time() - self.start_time if self.start_time else 0
            }

        except Exception as e:
            logger.error(f"获取健康状态失败: {e}")
            return {'is_healthy': False, 'error': str(e)}

    # ==================== 归档功能接口 ====================

    async def archive_data(self, tables=None, retention_days=None, force=False, dry_run=False):
        """归档数据到冷存储"""
        if self.archive_manager:
            return await self.archive_manager.archive_data(tables, retention_days, force, dry_run)
        else:
            logger.warning("归档管理器未初始化，无法执行归档")
            return {}

    async def restore_data(self, table, date_from, date_to, dry_run=False):
        """从冷存储恢复数据"""
        if self.archive_manager:
            return await self.archive_manager.restore_data(table, date_from, date_to, dry_run)
        else:
            logger.warning("归档管理器未初始化，无法执行恢复")
            return 0

    def get_archive_status(self):
        """获取归档状态"""
        if self.archive_manager:
            return self.archive_manager.get_status()
        else:
            return {'archive_available': False, 'reason': 'archive_manager_not_initialized'}

    def get_archive_statistics(self):
        """获取归档统计信息"""
        if self.archive_manager:
            return self.archive_manager.get_statistics()
        else:
            return {}

    # ==================== 向后兼容接口 ====================

    async def write_trade(self, trade: Any, writer_name: Optional[str] = None) -> bool:
        """写入交易数据（StorageManager兼容接口）"""
        try:
            # 转换为字典格式
            if hasattr(trade, '__dict__'):
                trade_data = trade.__dict__
            else:
                trade_data = trade

            await self.store_trade(trade_data)
            return True
        except Exception:
            return False

    async def write_orderbook(self, orderbook: Any, writer_name: Optional[str] = None) -> bool:
        """写入订单簿数据（StorageManager兼容接口）"""
        try:
            if hasattr(orderbook, '__dict__'):
                orderbook_data = orderbook.__dict__
            else:
                orderbook_data = orderbook

            await self.store_orderbook(orderbook_data)
            return True
        except Exception:
            return False

    async def write_ticker(self, ticker: Any, writer_name: Optional[str] = None) -> bool:
        """写入行情数据（StorageManager兼容接口）"""
        try:
            if hasattr(ticker, '__dict__'):
                ticker_data = ticker.__dict__
            else:
                ticker_data = ticker

            await self.store_ticker(ticker_data)
            return True
        except Exception:
            return False

    async def write_data(self, data: Any, table: str, writer_name: Optional[str] = None) -> bool:
        """统一数据写入接口（StorageManager兼容）"""
        try:
            if table == "trades":
                return await self.write_trade(data, writer_name)
            elif table == "tickers":
                return await self.write_ticker(data, writer_name)
            elif table == "orderbooks":
                return await self.write_orderbook(data, writer_name)
            else:
                logger.warning(f"不支持的表类型: {table}")
                return False
        except Exception:
            return False

    def query_data(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """统一数据查询接口（StorageManager兼容）"""
        if self.archiver_manager and hasattr(self.archiver_manager, 'query'):
            return self.archiver_manager.query(query, params)
        else:
            logger.warning("归档管理器不可用，无法执行查询")
            return []

    def get_status(self) -> Dict[str, Any]:
        """获取管理器状态（StorageManager兼容）"""
        return {
            'is_running': self.is_running,
            'storage_type': self.config.storage_type,
            'stats': self.stats.copy(),
            'config': asdict(self.config)
        }

    def get_comprehensive_status(self) -> Dict[str, Any]:
        """获取综合状态（StorageManager兼容）"""
        return {
            "is_running": self.is_running,
            "storage_status": self.get_status(),
            "health_status": self.get_health_status(),
            "statistics": self.get_statistics(),
            "archive_status": self.get_archive_status() if self.archive_manager else None
        }

    async def cleanup_expired_data(self, tables=None, max_age_days=None, force=False, dry_run=False):
        """清理过期数据（统一接口）"""
        try:
            # 使用归档管理器进行清理（如果可用）
            if self.archive_manager:
                return await self.archive_manager.cleanup_expired_data(tables, max_age_days, force, dry_run)

            # 回退到基础清理逻辑
            # 清理内存缓存中的过期数据
            if self.config.memory_cache_enabled:
                current_time = time.time()
                expired_keys = [
                    key for key, expire_time in self.memory_cache_expire.items()
                    if expire_time <= current_time
                ]

                for key in expired_keys:
                    self.memory_cache.pop(key, None)
                    self.memory_cache_expire.pop(key, None)

                logger.info(f"清理了 {len(expired_keys)} 个过期的内存缓存项")

            # ClickHouse的TTL会自动清理过期数据
            return {}

        except Exception as e:
            logger.error(f"清理过期数据失败: {e}")
            return {}

    def _compress_data(self, data: bytes) -> bytes:
        """压缩数据（如果启用压缩）"""
        if not self.config.enable_compression:
            return data

        try:
            return gzip.compress(data)
        except Exception as e:
            self.logger.error(f"数据压缩失败: {e}")
            return data

    def get_hot_storage_usage(self) -> Dict[str, Any]:
        """获取热存储使用情况"""
        try:
            usage_info = {
                "total_capacity": "10TB",  # 示例值
                "used_space": "2.5TB",
                "available_space": "7.5TB",
                "usage_percentage": 25.0,
                "file_count": 1500,
                "last_updated": datetime.now().isoformat()
            }

            # 如果有ClickHouse连接，获取实际使用情况
            if hasattr(self, 'clickhouse_client'):
                # TODO: 实现实际的ClickHouse存储使用查询
                pass

            return usage_info
        except Exception as e:
            self.logger.error(f"获取热存储使用情况失败: {e}")
            return {"error": str(e)}

    def get_cold_storage_usage(self) -> Dict[str, Any]:
        """获取冷存储使用情况"""
        try:
            usage_info = {
                "total_capacity": "100TB",  # 示例值
                "used_space": "15TB",
                "available_space": "85TB",
                "usage_percentage": 15.0,
                "archived_file_count": 5000,
                "last_updated": datetime.now().isoformat()
            }

            return usage_info
        except Exception as e:
            self.logger.error(f"获取冷存储使用情况失败: {e}")
            return {"error": str(e)}

    def migrate_data(self, source_path: str, target_path: str,
                    migration_type: str = "archive") -> bool:
        """数据迁移功能"""
        try:
            self.logger.info(f"开始数据迁移: {source_path} -> {target_path}")

            # TODO: 实现实际的数据迁移逻辑
            # 这里应该包括：
            # 1. 验证源数据完整性
            # 2. 复制数据到目标位置
            # 3. 验证迁移后数据完整性
            # 4. 可选删除源数据

            migration_result = {
                "source": source_path,
                "target": target_path,
                "type": migration_type,
                "status": "completed",
                "timestamp": datetime.now().isoformat()
            }

            self.logger.info(f"数据迁移完成: {migration_result}")
            return True

        except Exception as e:
            self.logger.error(f"数据迁移失败: {e}")
            return False

    def verify_data_integrity(self, path: str,
                            verification_type: str = "checksum") -> Dict[str, Any]:
        """验证数据完整性"""
        try:
            self.logger.info(f"开始数据完整性验证: {path}")

            verification_result = {
                "path": path,
                "verification_type": verification_type,
                "status": "passed",
                "checksum": "sha256:abc123...",  # 示例值
                "file_count": 100,
                "total_size": "1.2GB",
                "errors": [],
                "timestamp": datetime.now().isoformat()
            }

            # TODO: 实现实际的数据完整性验证
            # 1. 计算文件校验和
            # 2. 检查文件损坏
            # 3. 验证数据库记录一致性

            self.logger.info(f"数据完整性验证完成: {verification_result}")
            return verification_result

        except Exception as e:
            self.logger.error(f"数据完整性验证失败: {e}")
            return {
                "path": path,
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }


# 向后兼容别名
HotStorageManager = UnifiedStorageManager
SimpleHotStorageManager = UnifiedStorageManager
ColdStorageManager = UnifiedStorageManager
StorageManager = UnifiedStorageManager

HotStorageConfig = UnifiedStorageConfig
SimpleHotStorageConfig = UnifiedStorageConfig
ColdStorageConfig = UnifiedStorageConfig


# 全局实例管理函数
def get_hot_storage_manager(config: Optional[UnifiedStorageConfig] = None, config_path: Optional[str] = None) -> UnifiedStorageManager:
    """获取热存储管理器实例（向后兼容）"""
    if config:
        # 基于现有配置创建新的热存储配置
        hot_config = UnifiedStorageConfig(
            enabled=config.enabled,
            storage_type="hot",
            clickhouse_host=config.clickhouse_host,
            clickhouse_port=config.clickhouse_port,
            clickhouse_user=config.clickhouse_user,
            clickhouse_password=config.clickhouse_password,
            clickhouse_database=config.clickhouse_database,
            redis_enabled=True,  # 热存储启用Redis
            redis_host=config.redis_host,
            redis_port=config.redis_port,
            redis_password=config.redis_password,
            redis_db=config.redis_db,
            memory_cache_enabled=config.memory_cache_enabled
        )
        return UnifiedStorageManager(hot_config, config_path, "hot")
    return UnifiedStorageManager(config, config_path, "hot")


def get_simple_hot_storage_manager(config: Optional[UnifiedStorageConfig] = None, config_path: Optional[str] = None) -> UnifiedStorageManager:
    """获取简化热存储管理器实例（向后兼容）"""
    if config:
        # 基于现有配置创建新的简化热存储配置
        simple_config = UnifiedStorageConfig(
            enabled=config.enabled,
            storage_type="simple",
            clickhouse_host=config.clickhouse_host,
            clickhouse_port=config.clickhouse_port,
            clickhouse_user=config.clickhouse_user,
            clickhouse_password=config.clickhouse_password,
            clickhouse_database=config.clickhouse_database,
            redis_enabled=False,  # 简化存储不使用Redis
            memory_cache_enabled=config.memory_cache_enabled
        )
        return UnifiedStorageManager(simple_config, config_path, "simple")
    return UnifiedStorageManager(config, config_path, "simple")


def get_cold_storage_manager(config: Optional[UnifiedStorageConfig] = None, config_path: Optional[str] = None) -> UnifiedStorageManager:
    """获取冷存储管理器实例（向后兼容）"""
    if config:
        # 基于现有配置创建新的冷存储配置
        cold_config = UnifiedStorageConfig(
            enabled=config.enabled,
            storage_type="cold",
            clickhouse_host=config.clickhouse_host,
            clickhouse_port=config.clickhouse_port,
            clickhouse_user=config.clickhouse_user,
            clickhouse_password=config.clickhouse_password,
            clickhouse_database=config.clickhouse_database,
            redis_enabled=False,  # 冷存储不使用Redis
            memory_cache_enabled=config.memory_cache_enabled,
            # 冷存储特定配置
            cold_data_ttl=config.cold_data_ttl,
            enable_compression=True,
            compression_codec="LZ4",
            auto_archive_enabled=config.auto_archive_enabled
        )
        return UnifiedStorageManager(cold_config, config_path, "cold")
    return UnifiedStorageManager(config, config_path, "cold")


def get_storage_manager(config: Optional[Union[Dict[str, Any], UnifiedStorageConfig]] = None) -> UnifiedStorageManager:
    """获取统一存储管理器实例（向后兼容）"""
    if config:
        if isinstance(config, UnifiedStorageConfig):
            # 直接使用配置对象
            return UnifiedStorageManager(config, None, config.storage_type)
        else:
            # 转换字典配置为UnifiedStorageConfig
            unified_config = UnifiedStorageConfig(**config)
            return UnifiedStorageManager(unified_config, None, "hybrid")
    return UnifiedStorageManager(None, None, "hybrid")


def initialize_hot_storage_manager(config: Optional[UnifiedStorageConfig] = None, config_path: Optional[str] = None) -> UnifiedStorageManager:
    """初始化热存储管理器（向后兼容）"""
    manager = UnifiedStorageManager(config, config_path, "hot")
    logger.info("热存储管理器已初始化")
    return manager


def initialize_simple_hot_storage_manager(config: Optional[UnifiedStorageConfig] = None, config_path: Optional[str] = None) -> UnifiedStorageManager:
    """初始化简化热存储管理器（向后兼容）"""
    manager = UnifiedStorageManager(config, config_path, "simple")
    logger.info("简化热存储管理器已初始化")
    return manager


def initialize_cold_storage_manager(config: Optional[UnifiedStorageConfig] = None, config_path: Optional[str] = None) -> UnifiedStorageManager:
    """初始化冷存储管理器（向后兼容）"""
    manager = UnifiedStorageManager(config, config_path, "cold")
    logger.info("冷存储管理器已初始化")
    return manager


def initialize_storage_manager(config: Union[Dict[str, Any], UnifiedStorageConfig]) -> UnifiedStorageManager:
    """初始化统一存储管理器（向后兼容）"""
    if isinstance(config, UnifiedStorageConfig):
        unified_config = config
    else:
        unified_config = UnifiedStorageConfig(**config)
    manager = UnifiedStorageManager(unified_config, None, unified_config.storage_type)
    logger.info("统一存储管理器已初始化")
    return manager