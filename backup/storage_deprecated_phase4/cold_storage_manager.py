"""
MarketPrism 冷数据存储管理器

冷存储系统用于长期数据归档和历史数据查询：
1. 长期数据保存（30-365天）
2. 数据压缩和分区优化
3. 历史数据分析查询
4. 与热存储的分层管理
5. 成本优化的存储方案
"""

import asyncio
import logging
import time
import json
import yaml
import gzip
import pickle
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, asdict
from pathlib import Path

import aiochclient
import aiohttp
from prometheus_client import Counter, Histogram, Gauge

from .types import NormalizedTrade, NormalizedOrderBook, NormalizedTicker
from .optimized_clickhouse_writer import OptimizedClickHouseWriter

logger = logging.getLogger(__name__)

# Prometheus指标
COLD_STORAGE_OPERATIONS = Counter(
    "marketprism_cold_storage_operations_total",
    "冷存储操作总数",
    ["operation", "status"]
)

COLD_STORAGE_LATENCY = Histogram(
    "marketprism_cold_storage_latency_seconds",
    "冷存储操作延迟",
    ["operation"]
)

COLD_STORAGE_SIZE = Gauge(
    "marketprism_cold_storage_size_bytes",
    "冷存储数据大小",
    ["data_type"]
)

COLD_STORAGE_ARCHIVE_COUNT = Counter(
    "marketprism_cold_storage_archive_total",
    "冷存储归档操作总数",
    ["data_type", "status"]
)


@dataclass
class ColdStorageConfig:
    """冷数据存储配置"""
    
    # 基础配置
    enabled: bool = True
    cold_data_ttl: int = 2592000  # 30天（秒）
    archive_threshold_days: int = 7  # 7天后从热存储迁移到冷存储
    
    # ClickHouse配置
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "marketprism_cold"
    
    # 分区和压缩配置
    partition_by: str = "toYYYYMM(timestamp)"  # 按月分区
    compression_codec: str = "LZ4"  # 压缩算法
    enable_compression: bool = True
    
    # 性能配置
    connection_pool_size: int = 5
    batch_size: int = 5000  # 冷存储使用更大的批量
    flush_interval: int = 60  # 更长的刷新间隔
    max_retries: int = 3
    
    # 归档配置
    auto_archive_enabled: bool = True
    archive_batch_size: int = 10000
    archive_interval_hours: int = 24  # 每24小时执行一次归档
    
    @classmethod
    def from_yaml(cls, config_path: str) -> 'ColdStorageConfig':
        """从YAML文件加载配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            cold_config = config_data.get('cold_storage', {})
            clickhouse_config = cold_config.get('clickhouse', {})
            partition_config = cold_config.get('partitioning', {})
            compression_config = cold_config.get('compression', {})
            archive_config = cold_config.get('archiving', {})
            
            return cls(
                enabled=cold_config.get('enabled', True),
                cold_data_ttl=cold_config.get('cold_data_ttl', 2592000),
                archive_threshold_days=cold_config.get('archive_threshold_days', 7),
                
                clickhouse_host=clickhouse_config.get('host', 'localhost'),
                clickhouse_port=clickhouse_config.get('port', 8123),
                clickhouse_user=clickhouse_config.get('user', 'default'),
                clickhouse_password=clickhouse_config.get('password', ''),
                clickhouse_database=clickhouse_config.get('database', 'marketprism_cold'),
                
                partition_by=partition_config.get('partition_by', 'toYYYYMM(timestamp)'),
                compression_codec=compression_config.get('codec', 'LZ4'),
                enable_compression=compression_config.get('enabled', True),
                
                connection_pool_size=clickhouse_config.get('connection_pool_size', 5),
                batch_size=clickhouse_config.get('batch_size', 5000),
                flush_interval=clickhouse_config.get('flush_interval', 60),
                max_retries=clickhouse_config.get('max_retries', 3),
                
                auto_archive_enabled=archive_config.get('enabled', True),
                archive_batch_size=archive_config.get('batch_size', 10000),
                archive_interval_hours=archive_config.get('interval_hours', 24)
            )
            
        except Exception as e:
            logger.warning(f"加载冷存储配置失败，使用默认配置: {e}")
            return cls()


class MockColdClickHouseClient:
    """Mock冷存储ClickHouse客户端（用于ClickHouse不可用时）"""
    
    def __init__(self):
        self.cold_data = []
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
            # 添加数据到冷存储
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
                self.cold_data.append({
                    'data': arg,
                    'timestamp': time.time(),
                    'query': query,
                    'partition': partition_key
                })
                
        return True
        
    async def fetchall(self, query: str, params: Dict = None):
        # 返回分区数据
        if "partition" in query.lower():
            return list(self.partitions.values())[-3:] if self.partitions else []
        return self.cold_data[-1000:] if self.cold_data else []
        
    async def fetchone(self, query: str, params: Dict = None):
        return self.cold_data[-1] if self.cold_data else None
        
    async def close(self):
        pass


class ColdStorageManager:
    """冷数据存储管理器
    
    冷存储系统特点：
    1. 长期数据保存（30-365天）
    2. 数据压缩和分区优化
    3. 历史数据分析查询
    4. 批量数据归档
    5. 成本优化的存储方案
    """
    
    def __init__(self, config: Optional[ColdStorageConfig] = None, config_path: Optional[str] = None):
        """
        初始化冷存储管理器
        
        Args:
            config: 冷存储配置对象
            config_path: 配置文件路径
        """
        # 加载配置
        if config_path:
            self.config = ColdStorageConfig.from_yaml(config_path)
        elif config:
            self.config = config
        else:
            # 尝试从默认路径加载
            default_config_path = Path(__file__).parent.parent.parent / "config" / "collector_config.yaml"
            if default_config_path.exists():
                self.config = ColdStorageConfig.from_yaml(str(default_config_path))
            else:
                self.config = ColdStorageConfig()
        
        # 客户端实例
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
            'archives': 0,
            'errors': 0,
            'start_time': None,
            'total_size_bytes': 0,
            'partitions_created': 0
        }
        
        # 数据缓存（减少查询频率）
        self.query_cache = {}
        self.query_cache_expire = {}
        
        logger.info(f"冷存储管理器已初始化，配置: {asdict(self.config)}")
    
    async def start(self):
        """启动冷存储管理器"""
        if self.is_running:
            logger.warning("冷存储管理器已在运行")
            return
        
        try:
            self.start_time = time.time()
            self.stats['start_time'] = self.start_time
            
            # 初始化ClickHouse连接
            await self._init_clickhouse()
            
            # 创建冷数据表
            await self._create_cold_tables()
            
            # 启动自动归档任务
            if self.config.auto_archive_enabled:
                self.archive_task = asyncio.create_task(self._auto_archive_loop())
            
            self.is_running = True
            logger.info("冷存储管理器已启动")
            
        except Exception as e:
            logger.error(f"启动冷存储管理器失败: {e}")
            raise
    
    async def stop(self):
        """停止冷存储管理器"""
        if not self.is_running:
            return
        
        try:
            # 停止归档任务
            if self.archive_task and not self.archive_task.done():
                self.archive_task.cancel()
                try:
                    await self.archive_task
                except asyncio.CancelledError:
                    pass
            
            # 刷新缓冲区
            if self.clickhouse_writer:
                await self.clickhouse_writer.stop()
            
            # 关闭连接
            if self.clickhouse_client and hasattr(self.clickhouse_client, 'close'):
                await self.clickhouse_client.close()
            
            self.is_running = False
            logger.info("冷存储管理器已停止")
            
        except Exception as e:
            logger.error(f"停止冷存储管理器失败: {e}")
    
    async def _init_clickhouse(self):
        """初始化ClickHouse连接"""
        try:
            if not self.config.enabled:
                self.clickhouse_client = MockColdClickHouseClient()
                return
            
            # 创建HTTP会话
            session = aiohttp.ClientSession()
            
            # 创建ClickHouse客户端
            self.clickhouse_client = aiochclient.ChClient(
                session,
                url=f"http://{self.config.clickhouse_host}:{self.config.clickhouse_port}",
                user=self.config.clickhouse_user,
                password=self.config.clickhouse_password,
                database=self.config.clickhouse_database
            )
            
            # 测试连接
            await self.clickhouse_client.execute("SELECT 1")
            logger.info(f"冷存储ClickHouse连接成功: {self.config.clickhouse_host}:{self.config.clickhouse_port}")
            
            # 创建优化写入器
            clickhouse_config = {
                'host': self.config.clickhouse_host,
                'port': self.config.clickhouse_port,
                'user': self.config.clickhouse_user,
                'password': self.config.clickhouse_password,
                'database': self.config.clickhouse_database,
                'enabled': True,
                'optimization': {
                    'connection_pool_size': self.config.connection_pool_size,
                    'batch_size': self.config.batch_size,
                    'max_retries': self.config.max_retries
                }
            }
            
            self.clickhouse_writer = OptimizedClickHouseWriter(clickhouse_config)
            await self.clickhouse_writer.start()
            
        except Exception as e:
            logger.warning(f"冷存储ClickHouse连接失败，使用Mock客户端: {e}")
            self.clickhouse_client = MockColdClickHouseClient()
    
    async def _create_cold_tables(self):
        """创建冷数据表"""
        try:
            compression_clause = f"CODEC({self.config.compression_codec})" if self.config.enable_compression else ""
            
            # 创建冷交易数据表
            await self.clickhouse_client.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.config.clickhouse_database}.cold_trades (
                    timestamp DateTime64(3) {compression_clause},
                    symbol String {compression_clause},
                    exchange String {compression_clause},
                    price Float64 {compression_clause},
                    amount Float64 {compression_clause},
                    side String {compression_clause},
                    trade_id String {compression_clause},
                    created_at DateTime64(3) DEFAULT now64(),
                    archived_at DateTime64(3) DEFAULT now64()
                ) ENGINE = MergeTree()
                PARTITION BY {self.config.partition_by}
                ORDER BY (exchange, symbol, timestamp)
                TTL archived_at + INTERVAL {self.config.cold_data_ttl} SECOND
                SETTINGS index_granularity = 8192
            """)
            
            # 创建冷行情数据表
            await self.clickhouse_client.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.config.clickhouse_database}.cold_tickers (
                    timestamp DateTime64(3) {compression_clause},
                    symbol String {compression_clause},
                    exchange String {compression_clause},
                    last_price Float64 {compression_clause},
                    volume_24h Float64 {compression_clause},
                    price_change_24h Float64 {compression_clause},
                    high_24h Float64 {compression_clause},
                    low_24h Float64 {compression_clause},
                    created_at DateTime64(3) DEFAULT now64(),
                    archived_at DateTime64(3) DEFAULT now64()
                ) ENGINE = ReplacingMergeTree()
                PARTITION BY {self.config.partition_by}
                ORDER BY (exchange, symbol, timestamp)
                TTL archived_at + INTERVAL {self.config.cold_data_ttl} SECOND
                SETTINGS index_granularity = 8192
            """)
            
            # 创建冷订单簿数据表
            await self.clickhouse_client.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.config.clickhouse_database}.cold_orderbooks (
                    timestamp DateTime64(3) {compression_clause},
                    symbol String {compression_clause},
                    exchange String {compression_clause},
                    best_bid Float64 {compression_clause},
                    best_ask Float64 {compression_clause},
                    spread Float64 {compression_clause},
                    bids_json String {compression_clause},
                    asks_json String {compression_clause},
                    created_at DateTime64(3) DEFAULT now64(),
                    archived_at DateTime64(3) DEFAULT now64()
                ) ENGINE = ReplacingMergeTree()
                PARTITION BY {self.config.partition_by}
                ORDER BY (exchange, symbol, timestamp)
                TTL archived_at + INTERVAL {self.config.cold_data_ttl} SECOND
                SETTINGS index_granularity = 8192
            """)
            
            # 创建数据归档状态表
            await self.clickhouse_client.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.config.clickhouse_database}.archive_status (
                    archive_date Date,
                    data_type String,
                    exchange String,
                    records_archived UInt64,
                    archive_size_bytes UInt64,
                    archive_duration_seconds Float64,
                    created_at DateTime64(3) DEFAULT now64()
                ) ENGINE = MergeTree()
                ORDER BY (archive_date, data_type, exchange)
                SETTINGS index_granularity = 8192
            """)
            
            logger.info("冷数据表创建完成")
            
        except Exception as e:
            logger.error(f"创建冷数据表失败: {e}")
    
    # 数据归档操作
    async def archive_from_hot_storage(self, hot_storage_manager, data_type: str = "all") -> Dict[str, int]:
        """从热存储归档数据到冷存储"""
        start_time = time.time()
        archive_stats = {'trades': 0, 'tickers': 0, 'orderbooks': 0}
        
        try:
            cutoff_date = datetime.now() - timedelta(days=self.config.archive_threshold_days)
            
            # 归档交易数据
            if data_type in ["all", "trades"]:
                archive_stats['trades'] = await self._archive_trades_from_hot(
                    hot_storage_manager, cutoff_date
                )
            
            # 归档行情数据
            if data_type in ["all", "tickers"]:
                archive_stats['tickers'] = await self._archive_tickers_from_hot(
                    hot_storage_manager, cutoff_date
                )
            
            # 归档订单簿数据
            if data_type in ["all", "orderbooks"]:
                archive_stats['orderbooks'] = await self._archive_orderbooks_from_hot(
                    hot_storage_manager, cutoff_date
                )
            
            # 记录归档状态
            await self._record_archive_status(archive_stats, time.time() - start_time)
            
            self.stats['archives'] += sum(archive_stats.values())
            
            # 记录指标
            for dtype, count in archive_stats.items():
                if count > 0:
                    COLD_STORAGE_ARCHIVE_COUNT.labels(data_type=dtype, status="success").inc(count)
            
            logger.info(f"数据归档完成: {archive_stats}")
            return archive_stats
            
        except Exception as e:
            self.stats['errors'] += 1
            COLD_STORAGE_ARCHIVE_COUNT.labels(data_type=data_type, status="error").inc()
            logger.error(f"数据归档失败: {e}")
            return archive_stats
        
        finally:
            COLD_STORAGE_LATENCY.labels(operation="archive").observe(time.time() - start_time)
    
    async def _archive_trades_from_hot(self, hot_storage_manager, cutoff_date: datetime) -> int:
        """归档交易数据"""
        try:
            # 从热存储查询要归档的数据
            query = f"""
                SELECT * FROM {hot_storage_manager.config.clickhouse_database}.hot_trades
                WHERE created_at < '{cutoff_date.isoformat()}'
                ORDER BY timestamp
                LIMIT {self.config.archive_batch_size}
            """
            
            hot_trades = await hot_storage_manager.clickhouse_client.fetchall(query)
            
            if not hot_trades:
                return 0
            
            # 批量插入到冷存储
            for trade in hot_trades:
                await self.clickhouse_client.execute(
                    f"INSERT INTO {self.config.clickhouse_database}.cold_trades VALUES",
                    (
                        trade.get('timestamp'),
                        trade.get('symbol'),
                        trade.get('exchange'),
                        float(trade.get('price', 0)),
                        float(trade.get('amount', 0)),
                        trade.get('side'),
                        trade.get('trade_id'),
                        trade.get('created_at'),
                        datetime.now()  # archived_at
                    )
                )
            
            # 从热存储删除已归档的数据
            delete_query = f"""
                DELETE FROM {hot_storage_manager.config.clickhouse_database}.hot_trades
                WHERE created_at < '{cutoff_date.isoformat()}'
            """
            await hot_storage_manager.clickhouse_client.execute(delete_query)
            
            return len(hot_trades)
            
        except Exception as e:
            logger.error(f"归档交易数据失败: {e}")
            return 0
    
    async def _archive_tickers_from_hot(self, hot_storage_manager, cutoff_date: datetime) -> int:
        """归档行情数据"""
        try:
            query = f"""
                SELECT * FROM {hot_storage_manager.config.clickhouse_database}.hot_tickers
                WHERE created_at < '{cutoff_date.isoformat()}'
                ORDER BY timestamp
                LIMIT {self.config.archive_batch_size}
            """
            
            hot_tickers = await hot_storage_manager.clickhouse_client.fetchall(query)
            
            if not hot_tickers:
                return 0
            
            for ticker in hot_tickers:
                await self.clickhouse_client.execute(
                    f"INSERT INTO {self.config.clickhouse_database}.cold_tickers VALUES",
                    (
                        ticker.get('timestamp'),
                        ticker.get('symbol'),
                        ticker.get('exchange'),
                        float(ticker.get('last_price', 0)),
                        float(ticker.get('volume_24h', 0)),
                        float(ticker.get('price_change_24h', 0)),
                        float(ticker.get('high_24h', 0)),
                        float(ticker.get('low_24h', 0)),
                        ticker.get('created_at'),
                        datetime.now()
                    )
                )
            
            delete_query = f"""
                DELETE FROM {hot_storage_manager.config.clickhouse_database}.hot_tickers
                WHERE created_at < '{cutoff_date.isoformat()}'
            """
            await hot_storage_manager.clickhouse_client.execute(delete_query)
            
            return len(hot_tickers)
            
        except Exception as e:
            logger.error(f"归档行情数据失败: {e}")
            return 0
    
    async def _archive_orderbooks_from_hot(self, hot_storage_manager, cutoff_date: datetime) -> int:
        """归档订单簿数据"""
        try:
            query = f"""
                SELECT * FROM {hot_storage_manager.config.clickhouse_database}.hot_orderbooks
                WHERE created_at < '{cutoff_date.isoformat()}'
                ORDER BY timestamp
                LIMIT {self.config.archive_batch_size}
            """
            
            hot_orderbooks = await hot_storage_manager.clickhouse_client.fetchall(query)
            
            if not hot_orderbooks:
                return 0
            
            for orderbook in hot_orderbooks:
                await self.clickhouse_client.execute(
                    f"INSERT INTO {self.config.clickhouse_database}.cold_orderbooks VALUES",
                    (
                        orderbook.get('timestamp'),
                        orderbook.get('symbol'),
                        orderbook.get('exchange'),
                        float(orderbook.get('best_bid', 0)),
                        float(orderbook.get('best_ask', 0)),
                        float(orderbook.get('spread', 0)),
                        orderbook.get('bids_json'),
                        orderbook.get('asks_json'),
                        orderbook.get('created_at'),
                        datetime.now()
                    )
                )
            
            delete_query = f"""
                DELETE FROM {hot_storage_manager.config.clickhouse_database}.hot_orderbooks
                WHERE created_at < '{cutoff_date.isoformat()}'
            """
            await hot_storage_manager.clickhouse_client.execute(delete_query)
            
            return len(hot_orderbooks)
            
        except Exception as e:
            logger.error(f"归档订单簿数据失败: {e}")
            return 0
    
    async def _record_archive_status(self, archive_stats: Dict[str, int], duration: float):
        """记录归档状态"""
        try:
            today = datetime.now().date()
            
            for data_type, count in archive_stats.items():
                if count > 0:
                    # 估算数据大小（简化估算）
                    estimated_size = count * 100  # 每条记录约100字节
                    
                    await self.clickhouse_client.execute(
                        f"INSERT INTO {self.config.clickhouse_database}.archive_status VALUES",
                        (
                            today,
                            data_type,
                            "all_exchanges",
                            count,
                            estimated_size,
                            duration,
                            datetime.now()
                        )
                    )
                    
                    # 更新Prometheus指标
                    COLD_STORAGE_SIZE.labels(data_type=data_type).set(estimated_size)
            
        except Exception as e:
            logger.error(f"记录归档状态失败: {e}")
    
    async def _auto_archive_loop(self):
        """自动归档循环任务"""
        while self.is_running:
            try:
                # 等待归档间隔
                await asyncio.sleep(self.config.archive_interval_hours * 3600)
                
                if not self.is_running:
                    break
                
                logger.info("开始自动归档任务")
                
                # 这里需要热存储管理器实例，实际使用时需要从外部传入
                # 或者通过全局管理器获取
                # await self.archive_from_hot_storage(hot_storage_manager)
                
                logger.info("自动归档任务完成")
                
            except asyncio.CancelledError:
                logger.info("自动归档任务已取消")
                break
            except Exception as e:
                logger.error(f"自动归档任务失败: {e}")
                # 继续运行，不中断归档循环
    
    # 查询操作
    async def get_historical_trades(self, exchange: str, symbol: str, 
                                   start_date: datetime, end_date: datetime,
                                   limit: int = 1000) -> List[Dict[str, Any]]:
        """获取历史交易数据"""
        start_time = time.time()
        self.stats['reads'] += 1
        
        try:
            # 构建缓存键
            cache_key = f"hist_trades:{exchange}:{symbol}:{start_date.date()}:{end_date.date()}:{limit}"
            cached_data = self._get_from_cache(cache_key)
            if cached_data:
                return cached_data
            
            results = await self.clickhouse_client.fetchall(f"""
                SELECT * FROM {self.config.clickhouse_database}.cold_trades
                WHERE exchange = '{exchange}' 
                  AND symbol = '{symbol}'
                  AND timestamp >= '{start_date.isoformat()}'
                  AND timestamp <= '{end_date.isoformat()}'
                ORDER BY timestamp
                LIMIT {limit}
            """)
            
            data = [dict(row) for row in results] if results else []
            
            # 缓存结果（历史数据缓存更长时间）
            self._cache_data(cache_key, data, ttl=3600)  # 1小时缓存
            
            return data
            
        except Exception as e:
            logger.error(f"获取历史交易数据失败: {e}")
            return []
        
        finally:
            COLD_STORAGE_LATENCY.labels(operation="get_historical_trades").observe(time.time() - start_time)
    
    async def get_price_trends(self, exchange: str, symbol: str,
                              start_date: datetime, end_date: datetime,
                              interval: str = "1h") -> List[Dict[str, Any]]:
        """获取价格趋势数据"""
        start_time = time.time()
        self.stats['reads'] += 1
        
        try:
            # 根据间隔构建聚合查询
            if interval == "1h":
                time_group = "toStartOfHour(timestamp)"
            elif interval == "1d":
                time_group = "toStartOfDay(timestamp)"
            elif interval == "1w":
                time_group = "toMonday(timestamp)"
            else:
                time_group = "toStartOfHour(timestamp)"
            
            results = await self.clickhouse_client.fetchall(f"""
                SELECT 
                    {time_group} AS period,
                    avg(last_price) AS avg_price,
                    min(low_24h) AS min_price,
                    max(high_24h) AS max_price,
                    sum(volume_24h) AS total_volume,
                    count() AS data_points
                FROM {self.config.clickhouse_database}.cold_tickers
                WHERE exchange = '{exchange}' 
                  AND symbol = '{symbol}'
                  AND timestamp >= '{start_date.isoformat()}'
                  AND timestamp <= '{end_date.isoformat()}'
                GROUP BY period
                ORDER BY period
            """)
            
            return [dict(row) for row in results] if results else []
            
        except Exception as e:
            logger.error(f"获取价格趋势失败: {e}")
            return []
        
        finally:
            COLD_STORAGE_LATENCY.labels(operation="get_price_trends").observe(time.time() - start_time)
    
    async def get_archive_statistics(self, days: int = 30) -> Dict[str, Any]:
        """获取归档统计信息"""
        try:
            start_date = datetime.now().date() - timedelta(days=days)
            
            results = await self.clickhouse_client.fetchall(f"""
                SELECT 
                    data_type,
                    count() AS archive_sessions,
                    sum(records_archived) AS total_records,
                    sum(archive_size_bytes) AS total_size_bytes,
                    avg(archive_duration_seconds) AS avg_duration
                FROM {self.config.clickhouse_database}.archive_status
                WHERE archive_date >= '{start_date}'
                GROUP BY data_type
                ORDER BY data_type
            """)
            
            stats = {}
            for row in results:
                stats[row['data_type']] = {
                    'archive_sessions': row['archive_sessions'],
                    'total_records': row['total_records'],
                    'total_size_bytes': row['total_size_bytes'],
                    'avg_duration_seconds': row['avg_duration']
                }
            
            return stats
            
        except Exception as e:
            logger.error(f"获取归档统计失败: {e}")
            return {}
    
    # 内部缓存方法
    def _cache_data(self, key: str, data: Any, ttl: int = 3600):
        """缓存数据"""
        self.query_cache[key] = data
        self.query_cache_expire[key] = time.time() + ttl
    
    def _get_from_cache(self, key: str) -> Optional[Any]:
        """从缓存获取数据"""
        if key in self.query_cache:
            if self.query_cache_expire.get(key, 0) > time.time():
                return self.query_cache[key]
            else:
                # 清理过期数据
                self.query_cache.pop(key, None)
                self.query_cache_expire.pop(key, None)
        return None
    
    # 监控和统计
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        uptime = time.time() - self.start_time if self.start_time else 0
        
        return {
            'uptime_seconds': uptime,
            'total_writes': self.stats['writes'],
            'total_reads': self.stats['reads'],
            'total_archives': self.stats['archives'],
            'total_errors': self.stats['errors'],
            'writes_per_second': self.stats['writes'] / max(1, uptime),
            'reads_per_second': self.stats['reads'] / max(1, uptime),
            'archives_per_day': self.stats['archives'] / max(1, uptime / 86400),
            'query_cache_size': len(self.query_cache),
            'is_running': self.is_running,
            'auto_archive_enabled': self.config.auto_archive_enabled,
            'config': asdict(self.config)
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        try:
            clickhouse_healthy = self.clickhouse_client is not None
            archive_task_healthy = self.archive_task is None or not self.archive_task.done()
            
            return {
                'is_healthy': self.is_running and clickhouse_healthy,
                'is_running': self.is_running,
                'clickhouse_healthy': clickhouse_healthy,
                'archive_task_healthy': archive_task_healthy,
                'error_rate': self.stats['errors'] / max(1, self.stats['writes'] + self.stats['reads']),
                'uptime_seconds': time.time() - self.start_time if self.start_time else 0,
                'archive_enabled': self.config.auto_archive_enabled
            }
            
        except Exception as e:
            logger.error(f"获取健康状态失败: {e}")
            return {'is_healthy': False, 'error': str(e)}
    
    async def cleanup_expired_data(self):
        """清理过期数据"""
        try:
            # 清理查询缓存中的过期数据
            current_time = time.time()
            expired_keys = [
                key for key, expire_time in self.query_cache_expire.items()
                if expire_time <= current_time
            ]
            
            for key in expired_keys:
                self.query_cache.pop(key, None)
                self.query_cache_expire.pop(key, None)
            
            logger.info(f"清理了 {len(expired_keys)} 个过期的查询缓存项")
            
            # ClickHouse的TTL会自动清理过期数据
            
        except Exception as e:
            logger.error(f"清理过期数据失败: {e}")


# 全局实例管理
_cold_storage_manager = None


def get_cold_storage_manager(config: Optional[ColdStorageConfig] = None, config_path: Optional[str] = None) -> ColdStorageManager:
    """获取全局冷存储管理器实例"""
    global _cold_storage_manager
    if _cold_storage_manager is None:
        _cold_storage_manager = ColdStorageManager(config, config_path)
    return _cold_storage_manager


def initialize_cold_storage_manager(config: Optional[ColdStorageConfig] = None, config_path: Optional[str] = None) -> ColdStorageManager:
    """初始化冷存储管理器"""
    global _cold_storage_manager
    _cold_storage_manager = ColdStorageManager(config, config_path)
    logger.info("冷存储管理器已初始化")
    return _cold_storage_manager