"""
简化热数据存储管理器

纯ClickHouse存储方案，去除Redis依赖
专注于高性能数据写入和查询
"""

import asyncio
import logging
import time
import json
import yaml
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

import aiochclient
import aiohttp
from prometheus_client import Counter, Histogram, Gauge

from .types import NormalizedTrade, NormalizedOrderBook, NormalizedTicker
from .optimized_clickhouse_writer import OptimizedClickHouseWriter

logger = logging.getLogger(__name__)

# Prometheus指标
HOT_STORAGE_OPERATIONS = Counter(
    "marketprism_simple_hot_storage_operations_total",
    "简化热存储操作总数",
    ["operation", "status"]
)

HOT_STORAGE_LATENCY = Histogram(
    "marketprism_simple_hot_storage_latency_seconds",
    "简化热存储操作延迟",
    ["operation"]
)


@dataclass
class SimpleHotStorageConfig:
    """简化热数据存储配置"""
    
    # 基础配置
    enabled: bool = True
    hot_data_ttl: int = 3600  # 1小时
    
    # ClickHouse配置
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "marketprism_hot"
    
    # 性能配置
    connection_pool_size: int = 10
    batch_size: int = 1000
    flush_interval: int = 5
    max_retries: int = 3
    
    @classmethod
    def from_yaml(cls, config_path: str) -> 'SimpleHotStorageConfig':
        """从YAML文件加载配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            hot_config = config_data.get('hot_storage', {})
            clickhouse_config = hot_config.get('clickhouse', {})
            
            return cls(
                enabled=hot_config.get('enabled', True),
                hot_data_ttl=hot_config.get('hot_data_ttl', 3600),
                
                clickhouse_host=clickhouse_config.get('host', 'localhost'),
                clickhouse_port=clickhouse_config.get('port', 8123),
                clickhouse_user=clickhouse_config.get('user', 'default'),
                clickhouse_password=clickhouse_config.get('password', ''),
                clickhouse_database=clickhouse_config.get('database', 'marketprism_hot'),
                
                connection_pool_size=clickhouse_config.get('connection_pool_size', 10),
                batch_size=clickhouse_config.get('batch_size', 1000),
                flush_interval=clickhouse_config.get('flush_interval', 5),
                max_retries=clickhouse_config.get('max_retries', 3)
            )
            
        except Exception as e:
            logger.warning(f"加载热存储配置失败，使用默认配置: {e}")
            return cls()


class MockClickHouseClient:
    """Mock ClickHouse客户端（用于ClickHouse不可用时）"""
    
    def __init__(self):
        self.data = []
        self.tables = set()
        
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
                self.data.append({
                    'data': arg,
                    'timestamp': time.time(),
                    'query': query
                })
                
        return True
        
    async def fetchall(self, query: str, params: Dict = None):
        # 返回最近的数据
        return self.data[-100:] if self.data else []
        
    async def fetchone(self, query: str, params: Dict = None):
        return self.data[-1] if self.data else None
        
    async def close(self):
        pass


class SimpleHotStorageManager:
    """简化热数据存储管理器
    
    纯ClickHouse存储方案：
    1. 直接写入ClickHouse热数据表
    2. 内存缓存最近查询结果
    3. 优化的批量写入
    4. 性能监控
    """
    
    def __init__(self, config: Optional[SimpleHotStorageConfig] = None, config_path: Optional[str] = None):
        """
        初始化简化热存储管理器
        
        Args:
            config: 热存储配置对象
            config_path: 配置文件路径
        """
        # 加载配置
        if config_path:
            self.config = SimpleHotStorageConfig.from_yaml(config_path)
        elif config:
            self.config = config
        else:
            # 尝试从默认路径加载
            default_config_path = Path(__file__).parent.parent.parent / "config" / "collector_config.yaml"
            if default_config_path.exists():
                self.config = SimpleHotStorageConfig.from_yaml(str(default_config_path))
            else:
                self.config = SimpleHotStorageConfig()
        
        # 客户端实例
        self.clickhouse_client = None
        self.clickhouse_writer = None
        
        # 运行状态
        self.is_running = False
        self.start_time = None
        
        # 统计信息
        self.stats = {
            'writes': 0,
            'reads': 0,
            'errors': 0,
            'start_time': None
        }
        
        # 内存缓存（减少ClickHouse查询频率）
        self.memory_cache = {}
        self.memory_cache_expire = {}
        
        logger.info(f"简化热存储管理器已初始化，配置: {asdict(self.config)}")
    
    async def start(self):
        """启动热存储管理器"""
        if self.is_running:
            logger.warning("热存储管理器已在运行")
            return
        
        try:
            self.start_time = time.time()
            self.stats['start_time'] = self.start_time
            
            # 初始化ClickHouse连接
            await self._init_clickhouse()
            
            # 创建热数据表
            await self._create_hot_tables()
            
            self.is_running = True
            logger.info("简化热存储管理器已启动")
            
        except Exception as e:
            logger.error(f"启动热存储管理器失败: {e}")
            raise
    
    async def stop(self):
        """停止热存储管理器"""
        if not self.is_running:
            return
        
        try:
            # 刷新缓冲区
            if self.clickhouse_writer:
                await self.clickhouse_writer.stop()
            
            # 关闭连接
            if self.clickhouse_client and hasattr(self.clickhouse_client, 'close'):
                await self.clickhouse_client.close()
            
            self.is_running = False
            logger.info("简化热存储管理器已停止")
            
        except Exception as e:
            logger.error(f"停止热存储管理器失败: {e}")
    
    async def _init_clickhouse(self):
        """初始化ClickHouse连接"""
        try:
            if not self.config.enabled:
                self.clickhouse_client = MockClickHouseClient()
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
            logger.info(f"ClickHouse连接成功: {self.config.clickhouse_host}:{self.config.clickhouse_port}")
            
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
            logger.warning(f"ClickHouse连接失败，使用Mock客户端: {e}")
            self.clickhouse_client = MockClickHouseClient()
    
    async def _create_hot_tables(self):
        """创建热数据表"""
        try:
            # 创建热交易数据表
            await self.clickhouse_client.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.config.clickhouse_database}.hot_trades (
                    timestamp DateTime64(3),
                    symbol String,
                    exchange String,
                    price Float64,
                    amount Float64,
                    side String,
                    trade_id String,
                    created_at DateTime64(3) DEFAULT now64()
                ) ENGINE = MergeTree()
                ORDER BY (exchange, symbol, timestamp)
                TTL created_at + INTERVAL {self.config.hot_data_ttl} SECOND
                SETTINGS index_granularity = 8192
            """)
            
            # 创建热行情数据表
            await self.clickhouse_client.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.config.clickhouse_database}.hot_tickers (
                    timestamp DateTime64(3),
                    symbol String,
                    exchange String,
                    last_price Float64,
                    volume_24h Float64,
                    price_change_24h Float64,
                    high_24h Float64,
                    low_24h Float64,
                    created_at DateTime64(3) DEFAULT now64()
                ) ENGINE = ReplacingMergeTree()
                ORDER BY (exchange, symbol, timestamp)
                TTL created_at + INTERVAL {self.config.hot_data_ttl} SECOND
                SETTINGS index_granularity = 8192
            """)
            
            # 创建热订单簿数据表
            await self.clickhouse_client.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.config.clickhouse_database}.hot_orderbooks (
                    timestamp DateTime64(3),
                    symbol String,
                    exchange String,
                    best_bid Float64,
                    best_ask Float64,
                    spread Float64,
                    bids_json String,
                    asks_json String,
                    created_at DateTime64(3) DEFAULT now64()
                ) ENGINE = ReplacingMergeTree()
                ORDER BY (exchange, symbol, timestamp)
                TTL created_at + INTERVAL {self.config.hot_data_ttl} SECOND
                SETTINGS index_granularity = 8192
            """)
            
            logger.info("热数据表创建完成")
            
        except Exception as e:
            logger.error(f"创建热数据表失败: {e}")
    
    # 写入操作
    async def store_trade(self, trade_data: Dict[str, Any]):
        """存储交易数据"""
        start_time = time.time()
        
        try:
            # 直接写入ClickHouse
            await self.clickhouse_client.execute(
                f"INSERT INTO {self.config.clickhouse_database}.hot_trades VALUES",
                (
                    trade_data.get('timestamp', datetime.now()),
                    trade_data.get('symbol', ''),
                    trade_data.get('exchange', ''),
                    float(trade_data.get('price', 0)),
                    float(trade_data.get('amount', 0)),
                    trade_data.get('side', ''),
                    trade_data.get('trade_id', ''),
                    datetime.now()
                )
            )
            
            # 更新内存缓存
            self._cache_in_memory(f"latest_trade:{trade_data.get('exchange')}:{trade_data.get('symbol')}", trade_data)
            
            self.stats['writes'] += 1
            
            # 记录指标
            HOT_STORAGE_OPERATIONS.labels(operation="store_trade", status="success").inc()
            HOT_STORAGE_LATENCY.labels(operation="store_trade").observe(time.time() - start_time)
            
            logger.debug(f"交易数据已存储: {trade_data.get('symbol')} {trade_data.get('price')}")
            
        except Exception as e:
            self.stats['errors'] += 1
            HOT_STORAGE_OPERATIONS.labels(operation="store_trade", status="error").inc()
            logger.error(f"存储交易数据失败: {e}")
    
    async def store_ticker(self, ticker_data: Dict[str, Any]):
        """存储行情数据"""
        start_time = time.time()
        
        try:
            # 直接写入ClickHouse
            await self.clickhouse_client.execute(
                f"INSERT INTO {self.config.clickhouse_database}.hot_tickers VALUES",
                (
                    ticker_data.get('timestamp', datetime.now()),
                    ticker_data.get('symbol', ''),
                    ticker_data.get('exchange', ''),
                    float(ticker_data.get('last_price', 0)),
                    float(ticker_data.get('volume_24h', 0)),
                    float(ticker_data.get('price_change_24h', 0)),
                    float(ticker_data.get('high_24h', 0)),
                    float(ticker_data.get('low_24h', 0)),
                    datetime.now()
                )
            )
            
            # 更新内存缓存
            self._cache_in_memory(f"latest_ticker:{ticker_data.get('exchange')}:{ticker_data.get('symbol')}", ticker_data)
            
            self.stats['writes'] += 1
            
            # 记录指标
            HOT_STORAGE_OPERATIONS.labels(operation="store_ticker", status="success").inc()
            HOT_STORAGE_LATENCY.labels(operation="store_ticker").observe(time.time() - start_time)
            
            logger.debug(f"行情数据已存储: {ticker_data.get('symbol')} {ticker_data.get('last_price')}")
            
        except Exception as e:
            self.stats['errors'] += 1
            HOT_STORAGE_OPERATIONS.labels(operation="store_ticker", status="error").inc()
            logger.error(f"存储行情数据失败: {e}")
    
    async def store_orderbook(self, orderbook_data: Dict[str, Any]):
        """存储订单簿数据"""
        start_time = time.time()
        
        try:
            bids = orderbook_data.get('bids', [])
            asks = orderbook_data.get('asks', [])
            
            best_bid = bids[0][0] if bids else 0
            best_ask = asks[0][0] if asks else 0
            spread = best_ask - best_bid if best_bid and best_ask else 0
            
            # 直接写入ClickHouse
            await self.clickhouse_client.execute(
                f"INSERT INTO {self.config.clickhouse_database}.hot_orderbooks VALUES",
                (
                    orderbook_data.get('timestamp', datetime.now()),
                    orderbook_data.get('symbol', ''),
                    orderbook_data.get('exchange', ''),
                    float(best_bid),
                    float(best_ask),
                    float(spread),
                    json.dumps(bids),
                    json.dumps(asks),
                    datetime.now()
                )
            )
            
            # 更新内存缓存
            self._cache_in_memory(f"latest_orderbook:{orderbook_data.get('exchange')}:{orderbook_data.get('symbol')}", orderbook_data)
            
            self.stats['writes'] += 1
            
            # 记录指标
            HOT_STORAGE_OPERATIONS.labels(operation="store_orderbook", status="success").inc()
            HOT_STORAGE_LATENCY.labels(operation="store_orderbook").observe(time.time() - start_time)
            
            logger.debug(f"订单簿数据已存储: {orderbook_data.get('symbol')}")
            
        except Exception as e:
            self.stats['errors'] += 1
            HOT_STORAGE_OPERATIONS.labels(operation="store_orderbook", status="error").inc()
            logger.error(f"存储订单簿数据失败: {e}")
    
    # 读取操作
    async def get_latest_trade(self, exchange: str, symbol: str) -> Optional[Dict[str, Any]]:
        """获取最新交易数据"""
        start_time = time.time()
        self.stats['reads'] += 1
        
        try:
            # 1. 检查内存缓存
            memory_key = f"latest_trade:{exchange}:{symbol}"
            cached_data = self._get_from_memory(memory_key)
            if cached_data:
                logger.debug(f"内存缓存命中: {symbol}")
                return cached_data
            
            # 2. 从ClickHouse查询
            result = await self.clickhouse_client.fetchone(f"""
                SELECT * FROM {self.config.clickhouse_database}.hot_trades
                WHERE exchange = '{exchange}' AND symbol = '{symbol}'
                ORDER BY timestamp DESC
                LIMIT 1
            """)
            
            if result:
                data = dict(result)
                # 缓存到内存
                self._cache_in_memory(memory_key, data)
                logger.debug(f"从ClickHouse查询: {symbol}")
                return data
            
            return None
            
        except Exception as e:
            logger.error(f"获取最新交易数据失败: {e}")
            return None
        
        finally:
            HOT_STORAGE_LATENCY.labels(operation="get_latest_trade").observe(time.time() - start_time)
    
    async def get_latest_ticker(self, exchange: str, symbol: str) -> Optional[Dict[str, Any]]:
        """获取最新行情数据"""
        start_time = time.time()
        self.stats['reads'] += 1
        
        try:
            # 1. 检查内存缓存
            memory_key = f"latest_ticker:{exchange}:{symbol}"
            cached_data = self._get_from_memory(memory_key)
            if cached_data:
                return cached_data
            
            # 2. 从ClickHouse查询
            result = await self.clickhouse_client.fetchone(f"""
                SELECT * FROM {self.config.clickhouse_database}.hot_tickers
                WHERE exchange = '{exchange}' AND symbol = '{symbol}'
                ORDER BY timestamp DESC
                LIMIT 1
            """)
            
            if result:
                data = dict(result)
                self._cache_in_memory(memory_key, data)
                return data
            
            return None
            
        except Exception as e:
            logger.error(f"获取最新行情数据失败: {e}")
            return None
        
        finally:
            HOT_STORAGE_LATENCY.labels(operation="get_latest_ticker").observe(time.time() - start_time)
    
    async def get_recent_trades(self, exchange: str, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近交易数据"""
        try:
            results = await self.clickhouse_client.fetchall(f"""
                SELECT * FROM {self.config.clickhouse_database}.hot_trades
                WHERE exchange = '{exchange}' AND symbol = '{symbol}'
                ORDER BY timestamp DESC
                LIMIT {limit}
            """)
            
            return [dict(row) for row in results] if results else []
            
        except Exception as e:
            logger.error(f"获取最近交易数据失败: {e}")
            return []
    
    async def get_price_history(self, exchange: str, symbol: str, hours: int = 1) -> List[Dict[str, Any]]:
        """获取价格历史"""
        try:
            results = await self.clickhouse_client.fetchall(f"""
                SELECT 
                    timestamp,
                    last_price,
                    volume_24h,
                    price_change_24h
                FROM {self.config.clickhouse_database}.hot_tickers
                WHERE exchange = '{exchange}' 
                  AND symbol = '{symbol}'
                  AND timestamp >= now() - INTERVAL {hours} HOUR
                ORDER BY timestamp DESC
            """)
            
            return [dict(row) for row in results] if results else []
            
        except Exception as e:
            logger.error(f"获取价格历史失败: {e}")
            return []
    
    # 内部方法
    def _cache_in_memory(self, key: str, data: Dict[str, Any]):
        """缓存数据到内存"""
        self.memory_cache[key] = data
        self.memory_cache_expire[key] = time.time() + 300  # 5分钟过期
    
    def _get_from_memory(self, key: str) -> Optional[Dict[str, Any]]:
        """从内存缓存获取数据"""
        if key in self.memory_cache:
            if self.memory_cache_expire.get(key, 0) > time.time():
                return self.memory_cache[key]
            else:
                # 清理过期数据
                self.memory_cache.pop(key, None)
                self.memory_cache_expire.pop(key, None)
        return None
    
    # 监控和统计
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        uptime = time.time() - self.start_time if self.start_time else 0
        
        return {
            'uptime_seconds': uptime,
            'total_writes': self.stats['writes'],
            'total_reads': self.stats['reads'],
            'total_errors': self.stats['errors'],
            'writes_per_second': self.stats['writes'] / max(1, uptime),
            'reads_per_second': self.stats['reads'] / max(1, uptime),
            'memory_cache_size': len(self.memory_cache),
            'is_running': self.is_running,
            'config': asdict(self.config)
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        try:
            clickhouse_healthy = self.clickhouse_client is not None
            
            return {
                'is_healthy': self.is_running and clickhouse_healthy,
                'is_running': self.is_running,
                'clickhouse_healthy': clickhouse_healthy,
                'error_rate': self.stats['errors'] / max(1, self.stats['writes'] + self.stats['reads']),
                'uptime_seconds': time.time() - self.start_time if self.start_time else 0
            }
            
        except Exception as e:
            logger.error(f"获取健康状态失败: {e}")
            return {'is_healthy': False, 'error': str(e)}
    
    async def cleanup_expired_data(self):
        """清理过期数据"""
        try:
            # 清理内存缓存中的过期数据
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
            
        except Exception as e:
            logger.error(f"清理过期数据失败: {e}")


# 全局实例管理
_simple_hot_storage_manager = None


def get_simple_hot_storage_manager(config: Optional[SimpleHotStorageConfig] = None, config_path: Optional[str] = None) -> SimpleHotStorageManager:
    """获取全局简化热存储管理器实例"""
    global _simple_hot_storage_manager
    if _simple_hot_storage_manager is None:
        _simple_hot_storage_manager = SimpleHotStorageManager(config, config_path)
    return _simple_hot_storage_manager


def initialize_simple_hot_storage_manager(config: Optional[SimpleHotStorageConfig] = None, config_path: Optional[str] = None) -> SimpleHotStorageManager:
    """初始化简化热存储管理器"""
    global _simple_hot_storage_manager
    _simple_hot_storage_manager = SimpleHotStorageManager(config, config_path)
    logger.info("简化热存储管理器已初始化")
    return _simple_hot_storage_manager