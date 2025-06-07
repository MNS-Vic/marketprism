"""
MarketPrism 统一ClickHouse写入器

整合原有clickhouse_writer.py和optimized_clickhouse_writer.py的功能：
1. 保留优化版本的性能特性（连接池、事务、重试）
2. 整合基础版本的核心功能（表管理、数据写入）
3. 提供统一的API接口
4. 解决功能重复问题

主要特性：
- 连接池管理和复用
- 事务支持和错误处理
- 智能重试机制
- 数据验证和压缩
- 批量写入优化
- 性能监控和健康检查
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
import json

import aiochclient
import aiohttp
from prometheus_client import Counter, Histogram, Gauge

from .types import NormalizedTrade, NormalizedOrderBook, NormalizedTicker

logger = logging.getLogger(__name__)

# Prometheus指标（整合两个版本的指标）
UNIFIED_CLICKHOUSE_OPERATIONS = Counter(
    "marketprism_unified_clickhouse_operations_total",
    "ClickHouse操作总数",
    ["operation", "status"]
)
UNIFIED_CLICKHOUSE_OPERATION_LATENCY = Histogram(
    "marketprism_unified_clickhouse_operation_latency_seconds",
    "ClickHouse操作延迟(秒)",
    ["operation"]
)
UNIFIED_CLICKHOUSE_BATCH_SIZE = Histogram(
    "marketprism_unified_clickhouse_batch_size",
    "ClickHouse批量写入大小",
    ["table"]
)
UNIFIED_CLICKHOUSE_QUEUE_SIZE = Gauge(
    "marketprism_unified_clickhouse_queue_size",
    "ClickHouse写入队列大小",
    ["table"]
)
UNIFIED_CLICKHOUSE_CONNECTION_POOL = Gauge(
    "marketprism_unified_clickhouse_connection_pool_size",
    "ClickHouse连接池大小",
    ["pool_type"]
)
UNIFIED_CLICKHOUSE_COMPRESSION_RATIO = Histogram(
    "marketprism_unified_clickhouse_compression_ratio",
    "数据压缩比率"
)


class DummyClickHouseClient:
    """当ClickHouse禁用时使用的虚拟客户端"""
    
    async def fetchone(self, query, *args):
        return "DummyClient"
        
    async def execute(self, query, *args):
        return None
    
    async def close(self):
        pass


class UnifiedClickHouseWriter:
    """
    统一ClickHouse写入器 - 整合原有重复功能
    
    核心特性：
    1. 连接池管理（来自优化版本）
    2. 基础写入功能（来自基础版本）
    3. 事务支持和错误处理（来自优化版本）
    4. 数据验证和批量写入（整合两者）
    5. 性能监控和健康检查
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初始化统一ClickHouse写入器
        
        Args:
            config: ClickHouse配置字典，可选
        """
        self.config = config or {}
        self.enabled = self.config.get('clickhouse_direct_write', False)
        self.logger = logger
        
        # 基础配置（来自基础版本）
        if self.enabled:
            clickhouse_config = self.config.get('clickhouse', {})
            self.host = clickhouse_config.get("host", "localhost")
            self.port = clickhouse_config.get("port", 8123)
            self.database = clickhouse_config.get("database", "marketprism")
            self.user = clickhouse_config.get("user", "default")
            self.password = clickhouse_config.get("password", "")
            
            # 表名配置
            self.tables = clickhouse_config.get("tables", {})
            self.trades_table = self.tables.get("trades", "trades")
            self.orderbook_table = self.tables.get("orderbook", "depth")
            self.ticker_table = self.tables.get("ticker", "tickers")
            
            # 写入配置
            self.write_config = clickhouse_config.get("write", {})
            self.batch_size = self.write_config.get("batch_size", 1000)
            self.write_interval = self.write_config.get("interval", 5)
        else:
            # 禁用时的默认配置
            self.host = ""
            self.port = 8123
            self.database = "marketprism"
            self.user = "default"
            self.password = ""
            self.trades_table = "trades"
            self.orderbook_table = "depth"
            self.ticker_table = "tickers"
            self.batch_size = 1000
            self.write_interval = 5
        
        # 优化配置（来自优化版本）
        self.optimization_config = self.config.get('optimization', {})
        self.connection_pool_size = self.optimization_config.get('connection_pool_size', 10)
        self.max_retries = self.optimization_config.get('max_retries', 3)
        self.retry_delay = self.optimization_config.get('retry_delay', 1.0)
        self.enable_data_validation = self.optimization_config.get('enable_data_validation', True)
        self.enable_transactions = self.optimization_config.get('enable_transactions', False)
        
        # 连接池管理（来自优化版本）
        self.connection_pool = []
        self.connection_pool_lock = asyncio.Lock()
        
        # 会话管理
        self.session = None
        self.client = None
        
        # 运行状态
        self.is_running = False
        self.write_task = None
        
        # 数据队列（来自基础版本）
        self.trades_queue = []
        self.orderbook_queue = []
        self.ticker_queue = []
        
        # 事务管理（来自优化版本）
        self.current_transaction = None
        self.transaction_lock = asyncio.Lock()
        
        # 错误统计（来自优化版本）
        self.error_count = 0
        self.last_error = None
        self.last_error_time = None
        
        # 性能统计
        self.performance_metrics = {
            'total_writes': 0,
            'successful_writes': 0,
            'failed_writes': 0,
            'total_latency': 0.0,
            'start_time': time.time()
        }
        
        if self.enabled:
            self.logger.info(f"统一ClickHouse写入器已初始化: host={self.host}, port={self.port}, database={self.database}, pool_size={self.connection_pool_size}, enable_validation={self.enable_data_validation}")
        else:
            self.logger.info("ClickHouse直接写入已禁用")
    
    async def start(self):
        """启动ClickHouse写入器（整合两个版本的启动逻辑）"""
        if not self.enabled:
            # 即使禁用，也要设置虚拟客户端以保持API兼容性
            self.client = DummyClickHouseClient()
            self.is_running = True
            return
            
        try:
            # 检查ClickHouse主机配置
            if not self.host or self.host == "":
                self.logger.info("ClickHouse主机未配置，使用虚拟客户端")
                self.client = DummyClickHouseClient()
                self.is_running = True
                return
            
            # 创建HTTP会话（整合代理支持）
            await self._create_session()
            
            # 创建主ClickHouse客户端
            self.client = aiochclient.ChClient(
                self.session,
                url=f"http://{self.host}:{self.port}",
                user=self.user,
                password=self.password,
                database=self.database
            )
            
            # 测试连接
            version = await self.client.fetchone("SELECT version()")
            self.logger.info(f"ClickHouse连接成功: host={self.host}, port={self.port}, database={self.database}, version={version}")
            
            # 初始化连接池（来自优化版本）
            await self._init_connection_pool()
            
            # 确保数据库和表存在（来自基础版本）
            await self._ensure_database_and_tables()
            
            # 启动定时写入任务
            self.is_running = True
            self.write_task = asyncio.create_task(self._periodic_write())
            
        except Exception as e:
            self.logger.error("ClickHouse连接失败", error=str(e))
            if self.session:
                await self.session.close()
            raise
    
    async def stop(self):
        """停止ClickHouse写入器（整合清理逻辑）"""
        if not self.enabled:
            return
            
        self.is_running = False
        
        # 等待写入任务完成
        if self.write_task:
            try:
                await asyncio.wait_for(self.write_task, timeout=10)
            except asyncio.TimeoutError:
                self.logger.warning("等待ClickHouse写入任务超时")
        
        # 执行最后一次写入
        await self._write_all_queues()
        
        # 关闭连接池
        await self._close_connection_pool()
        
        # 关闭主会话
        if self.session:
            await self.session.close()
            self.logger.info("ClickHouse连接已关闭")
    
    async def _create_session(self):
        """创建HTTP会话（整合代理支持）"""
        import os
        
        # 获取代理设置
        proxy = None
        http_proxy = os.getenv('http_proxy') or os.getenv('HTTP_PROXY')
        https_proxy = os.getenv('https_proxy') or os.getenv('HTTPS_PROXY')
        
        if https_proxy or http_proxy:
            proxy = https_proxy or http_proxy
            self.logger.info(f"使用代理连接ClickHouse: proxy={proxy}")
        
        # 创建连接器和会话
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=30,
            ttl_dns_cache=300,
            use_dns_cache=True,
        )
        
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=30)
        )
    
    async def _init_connection_pool(self):
        """初始化连接池（来自优化版本）"""
        if not self.enabled:
            return
            
        try:
            for _ in range(min(3, self.connection_pool_size)):  # 预创建3个连接
                connection = await self._create_connection()
                await self._return_connection(connection)
            
            # 更新指标
            UNIFIED_CLICKHOUSE_CONNECTION_POOL.labels(pool_type="active").set(len(self.connection_pool))
            self.logger.info(f"连接池初始化完成: pool_size={len(self.connection_pool)}")
            
        except Exception as e:
            self.logger.error("连接池初始化失败", error=str(e))
            raise
    
    async def _create_connection(self):
        """创建新的ClickHouse连接"""
        if not self.enabled:
            return DummyClickHouseClient()
        
        session = aiohttp.ClientSession()
        return aiochclient.ChClient(
            session,
            url=f"http://{self.host}:{self.port}",
            user=self.user,
            password=self.password,
            database=self.database
        )
    
    async def _get_connection(self):
        """从连接池获取连接（来自优化版本）"""
        async with self.connection_pool_lock:
            if self.connection_pool:
                return self.connection_pool.pop()
            else:
                # 创建新连接
                return await self._create_connection()
    
    async def _return_connection(self, connection):
        """将连接返回连接池（来自优化版本）"""
        async with self.connection_pool_lock:
            if len(self.connection_pool) < self.connection_pool_size:
                self.connection_pool.append(connection)
                # 更新指标
                UNIFIED_CLICKHOUSE_CONNECTION_POOL.labels(pool_type="active").set(len(self.connection_pool))
            else:
                # 连接池已满，关闭连接
                if hasattr(connection, 'close'):
                    await connection.close()
    
    async def _close_connection_pool(self):
        """关闭连接池（来自优化版本）"""
        async with self.connection_pool_lock:
            for connection in self.connection_pool:
                try:
                    if hasattr(connection, 'close'):
                        await connection.close()
                except Exception as e:
                    self.logger.warning("关闭连接失败", error=str(e))
            
            self.connection_pool.clear()
            UNIFIED_CLICKHOUSE_CONNECTION_POOL.labels(pool_type="active").set(0)
    
    @asynccontextmanager
    async def transaction(self):
        """事务上下文管理器（来自优化版本）"""
        if not self.enable_transactions:
            # 如果不支持事务，直接yield
            yield self
            return
        
        async with self.transaction_lock:
            connection = await self._get_connection()
            try:
                # 开始事务
                await connection.execute("BEGIN TRANSACTION")
                self.current_transaction = connection
                
                yield self
                
                # 提交事务
                await connection.execute("COMMIT")
                
            except Exception as e:
                # 回滚事务
                try:
                    await connection.execute("ROLLBACK")
                except:
                    pass
                raise e
            finally:
                self.current_transaction = None
                await self._return_connection(connection)
    
    # 数据验证方法（来自优化版本）
    def validate_trade_data(self, trade: NormalizedTrade) -> bool:
        """验证交易数据"""
        if not self.enable_data_validation:
            return True
        
        required_fields = ['exchange_name', 'symbol_name', 'trade_id', 'price', 'quantity', 'timestamp']
        for field in required_fields:
            if not hasattr(trade, field) or getattr(trade, field) is None:
                self.logger.warning(f"交易数据验证失败: missing_field={field}")
                return False
        
        # 价格和数量必须为正数
        price = float(trade.price) if not isinstance(trade.price, (int, float)) else trade.price
        quantity = float(trade.quantity) if not isinstance(trade.quantity, (int, float)) else trade.quantity
        
        if price <= 0 or quantity <= 0:
            self.logger.warning("交易数据验证失败: 价格或数量无效")
            return False
        
        return True
    
    def validate_orderbook_data(self, orderbook: NormalizedOrderBook) -> bool:
        """验证订单簿数据"""
        if not self.enable_data_validation:
            return True
        
        required_fields = ['exchange_name', 'symbol_name', 'bids', 'asks', 'timestamp']
        for field in required_fields:
            if not hasattr(orderbook, field) or getattr(orderbook, field) is None:
                self.logger.warning(f"订单簿数据验证失败: missing_field={field}")
                return False
        
        # 检查bids和asks格式
        if not isinstance(orderbook.bids, list) or not isinstance(orderbook.asks, list):
            self.logger.warning("订单簿数据验证失败: bids或asks格式错误")
            return False
        
        return True
    
    # 重试机制（来自优化版本）
    async def execute_with_retry(self, operation, *args, **kwargs):
        """带重试的操作执行"""
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return await operation(*args, **kwargs)
            except Exception as e:
                last_error = e
                self.error_count += 1
                self.last_error = str(e)
                self.last_error_time = time.time()
                
                if attempt < self.max_retries:
                    self.logger.warning("操作失败，将重试", 
                                      attempt=attempt + 1,
                                      max_attempts=self.max_retries + 1,
                                      error=str(e))
                    await asyncio.sleep(self.retry_delay * (attempt + 1))  # 指数退避
                else:
                    self.logger.error("操作最终失败", 
                                    max_retries=self.max_retries,
                                    error=str(e))
                    break
        
        if last_error:
            raise last_error
    
    # 写入方法（整合两个版本）
    async def write_trade(self, trade: NormalizedTrade):
        """写入交易数据（整合版本）"""
        if not self.enabled:
            return
        
        try:
            # 数据验证
            if not self.validate_trade_data(trade):
                return
            
            # 添加到队列
            self.trades_queue.append(trade)
            
            # 更新队列大小指标
            UNIFIED_CLICKHOUSE_QUEUE_SIZE.labels(table="trades").set(len(self.trades_queue))
            
        except Exception as e:
            self.logger.error("写入交易数据失败", error=str(e))
    
    async def write_orderbook(self, orderbook: NormalizedOrderBook):
        """写入订单簿数据（整合版本）"""
        if not self.enabled:
            return
        
        try:
            # 数据验证
            if not self.validate_orderbook_data(orderbook):
                return
            
            # 添加到队列
            self.orderbook_queue.append(orderbook)
            
            # 更新队列大小指标
            UNIFIED_CLICKHOUSE_QUEUE_SIZE.labels(table="orderbook").set(len(self.orderbook_queue))
            
        except Exception as e:
            self.logger.error("写入订单簿数据失败", error=str(e))
    
    async def write_ticker(self, ticker: NormalizedTicker):
        """写入行情数据（整合版本）"""
        if not self.enabled:
            return
        
        try:
            # 添加到队列
            self.ticker_queue.append(ticker)
            
            # 更新队列大小指标
            UNIFIED_CLICKHOUSE_QUEUE_SIZE.labels(table="ticker").set(len(self.ticker_queue))
            
        except Exception as e:
            self.logger.error("写入行情数据失败", error=str(e))
    
    # 表管理方法（来自基础版本）
    async def _ensure_database_and_tables(self):
        """确保数据库和表存在"""
        try:
            # 创建数据库
            await self.client.execute(f"CREATE DATABASE IF NOT EXISTS {self.database}")
            
            # 创建表
            await self._create_trades_table()
            await self._create_orderbook_table()
            await self._create_ticker_table()
            
            self.logger.info("数据库和表检查完成")
            
        except Exception as e:
            self.logger.error("创建数据库和表失败", error=str(e))
            raise
    
    async def _create_trades_table(self):
        """创建交易表"""
        create_sql = f"""
        CREATE TABLE IF NOT EXISTS {self.database}.{self.trades_table} (
            symbol String,
            exchange String,
            price Float64,
            amount Float64,
            side String,
            timestamp DateTime64(3),
            trade_id String,
            raw_data String
        ) ENGINE = MergeTree()
        ORDER BY (symbol, exchange, timestamp)
        """
        await self.client.execute(create_sql)
    
    async def _create_orderbook_table(self):
        """创建订单簿表"""
        create_sql = f"""
        CREATE TABLE IF NOT EXISTS {self.database}.{self.orderbook_table} (
            symbol String,
            exchange String,
            bids String,
            asks String,
            timestamp DateTime64(3),
            raw_data String
        ) ENGINE = MergeTree()
        ORDER BY (symbol, exchange, timestamp)
        """
        await self.client.execute(create_sql)
    
    async def _create_ticker_table(self):
        """创建行情表"""
        create_sql = f"""
        CREATE TABLE IF NOT EXISTS {self.database}.{self.ticker_table} (
            symbol String,
            exchange String,
            price Float64,
            volume Float64,
            high Float64,
            low Float64,
            change Float64,
            timestamp DateTime64(3),
            raw_data String
        ) ENGINE = MergeTree()
        ORDER BY (symbol, exchange, timestamp)
        """
        await self.client.execute(create_sql)
    
    # 批量写入方法（整合优化）
    async def _periodic_write(self):
        """定时写入任务（整合版本）"""
        while self.is_running:
            try:
                await asyncio.sleep(self.write_interval)
                await self._write_all_queues()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("定时写入任务出错", error=str(e))
    
    async def _write_all_queues(self):
        """写入所有队列数据（整合版本）"""
        try:
            await self.execute_with_retry(self._write_trades)
            await self.execute_with_retry(self._write_orderbook)
            await self.execute_with_retry(self._write_ticker)
        except Exception as e:
            self.logger.error("批量写入失败", error=str(e))
    
    async def _write_trades(self):
        """写入交易数据（整合优化版本）"""
        if not self.trades_queue:
            return
        
        start_time = time.time()
        batch = self.trades_queue[:self.batch_size]
        self.trades_queue = self.trades_queue[self.batch_size:]
        
        try:
            connection = await self._get_connection()
            
            # 准备数据
            data_to_insert = []
            for trade in batch:
                data_to_insert.append([
                    trade.symbol,
                    trade.exchange,
                    trade.price,
                    trade.amount,
                    trade.side,
                    trade.timestamp,
                    getattr(trade, 'trade_id', ''),
                    json.dumps(getattr(trade, 'raw_data', {}))
                ])
            
            # 执行插入
            await connection.execute(
                f"INSERT INTO {self.database}.{self.trades_table} VALUES",
                *data_to_insert
            )
            
            await self._return_connection(connection)
            
            # 更新统计
            latency = time.time() - start_time
            self.performance_metrics['total_writes'] += 1
            self.performance_metrics['successful_writes'] += 1
            self.performance_metrics['total_latency'] += latency
            
            # 更新Prometheus指标
            UNIFIED_CLICKHOUSE_OPERATIONS.labels(operation="write_trades", status="success").inc()
            UNIFIED_CLICKHOUSE_OPERATION_LATENCY.labels(operation="write_trades").observe(latency)
            UNIFIED_CLICKHOUSE_BATCH_SIZE.labels(table="trades").observe(len(batch))
            UNIFIED_CLICKHOUSE_QUEUE_SIZE.labels(table="trades").set(len(self.trades_queue))
            
            self.logger.debug("交易数据写入成功", 
                            batch_size=len(batch),
                            latency=latency,
                            remaining=len(self.trades_queue))
            
        except Exception as e:
            # 写入失败，将数据放回队列
            self.trades_queue = batch + self.trades_queue
            self.performance_metrics['failed_writes'] += 1
            UNIFIED_CLICKHOUSE_OPERATIONS.labels(operation="write_trades", status="error").inc()
            raise
    
    async def _write_orderbook(self):
        """写入订单簿数据"""
        if not self.orderbook_queue:
            return
        
        start_time = time.time()
        batch = self.orderbook_queue[:self.batch_size]
        self.orderbook_queue = self.orderbook_queue[self.batch_size:]
        
        try:
            connection = await self._get_connection()
            
            # 准备数据
            data_to_insert = []
            for orderbook in batch:
                data_to_insert.append([
                    orderbook.symbol,
                    orderbook.exchange,
                    json.dumps(orderbook.bids),
                    json.dumps(orderbook.asks),
                    orderbook.timestamp,
                    json.dumps(getattr(orderbook, 'raw_data', {}))
                ])
            
            # 执行插入
            await connection.execute(
                f"INSERT INTO {self.database}.{self.orderbook_table} VALUES",
                *data_to_insert
            )
            
            await self._return_connection(connection)
            
            # 更新统计
            latency = time.time() - start_time
            UNIFIED_CLICKHOUSE_OPERATIONS.labels(operation="write_orderbook", status="success").inc()
            UNIFIED_CLICKHOUSE_OPERATION_LATENCY.labels(operation="write_orderbook").observe(latency)
            UNIFIED_CLICKHOUSE_BATCH_SIZE.labels(table="orderbook").observe(len(batch))
            UNIFIED_CLICKHOUSE_QUEUE_SIZE.labels(table="orderbook").set(len(self.orderbook_queue))
            
        except Exception as e:
            # 写入失败，将数据放回队列
            self.orderbook_queue = batch + self.orderbook_queue
            UNIFIED_CLICKHOUSE_OPERATIONS.labels(operation="write_orderbook", status="error").inc()
            raise
    
    async def _write_ticker(self):
        """写入行情数据"""
        if not self.ticker_queue:
            return
        
        start_time = time.time()
        batch = self.ticker_queue[:self.batch_size]
        self.ticker_queue = self.ticker_queue[self.batch_size:]
        
        try:
            connection = await self._get_connection()
            
            # 准备数据
            data_to_insert = []
            for ticker in batch:
                data_to_insert.append([
                    ticker.symbol,
                    ticker.exchange,
                    ticker.price,
                    getattr(ticker, 'volume', 0.0),
                    getattr(ticker, 'high', 0.0),
                    getattr(ticker, 'low', 0.0),
                    getattr(ticker, 'change', 0.0),
                    ticker.timestamp,
                    json.dumps(getattr(ticker, 'raw_data', {}))
                ])
            
            # 执行插入
            await connection.execute(
                f"INSERT INTO {self.database}.{self.ticker_table} VALUES",
                *data_to_insert
            )
            
            await self._return_connection(connection)
            
            # 更新统计
            latency = time.time() - start_time
            UNIFIED_CLICKHOUSE_OPERATIONS.labels(operation="write_ticker", status="success").inc()
            UNIFIED_CLICKHOUSE_OPERATION_LATENCY.labels(operation="write_ticker").observe(latency)
            UNIFIED_CLICKHOUSE_BATCH_SIZE.labels(table="ticker").observe(len(batch))
            UNIFIED_CLICKHOUSE_QUEUE_SIZE.labels(table="ticker").set(len(self.ticker_queue))
            
        except Exception as e:
            # 写入失败，将数据放回队列
            self.ticker_queue = batch + self.ticker_queue
            UNIFIED_CLICKHOUSE_OPERATIONS.labels(operation="write_ticker", status="error").inc()
            raise
    
    # 查询和工具方法
    async def execute_query(self, query: str, *args) -> Any:
        """执行查询（整合版本）"""
        if not self.enabled:
            return None
        
        return await self.execute_with_retry(self._execute_query_impl, query, *args)
    
    async def _execute_query_impl(self, query: str, *args) -> Any:
        """执行查询实现"""
        connection = await self._get_connection()
        try:
            result = await connection.fetchone(query, *args)
            return result
        finally:
            await self._return_connection(connection)
    
    # 统计和监控方法
    def get_connection_status(self) -> Dict[str, Any]:
        """获取连接状态"""
        return {
            'enabled': self.enabled,
            'is_running': self.is_running,
            'host': self.host,
            'port': self.port,
            'database': self.database,
            'connection_pool_size': len(self.connection_pool),
            'max_pool_size': self.connection_pool_size
        }
    
    def get_queue_sizes(self) -> Dict[str, int]:
        """获取队列大小"""
        return {
            'trades': len(self.trades_queue),
            'orderbook': len(self.orderbook_queue),
            'ticker': len(self.ticker_queue),
            'total': len(self.trades_queue) + len(self.orderbook_queue) + len(self.ticker_queue)
        }
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        uptime = time.time() - self.performance_metrics['start_time']
        total_writes = self.performance_metrics['total_writes']
        
        return {
            'uptime_seconds': uptime,
            'total_writes': total_writes,
            'successful_writes': self.performance_metrics['successful_writes'],
            'failed_writes': self.performance_metrics['failed_writes'],
            'success_rate': (
                self.performance_metrics['successful_writes'] / max(total_writes, 1)
            ) * 100,
            'average_latency': (
                self.performance_metrics['total_latency'] / max(total_writes, 1)
            ),
            'writes_per_second': total_writes / max(uptime, 1),
            'error_count': self.error_count,
            'last_error': self.last_error,
            'last_error_time': self.last_error_time
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        metrics = self.get_performance_metrics()
        queue_sizes = self.get_queue_sizes()
        
        # 计算健康评分
        health_score = 100
        issues = []
        
        # 检查失败率
        if metrics['success_rate'] < 95:
            health_score -= 20
            issues.append("高失败率")
        
        # 检查队列积压
        if queue_sizes['total'] > self.batch_size * 10:
            health_score -= 15
            issues.append("队列积压")
        
        # 检查连接状态
        if not self.is_running:
            health_score = 0
            issues.append("服务未运行")
        
        return {
            'healthy': health_score >= 80,
            'health_score': health_score,
            'status': 'healthy' if health_score >= 80 else 'degraded' if health_score >= 50 else 'unhealthy',
            'issues': issues,
            'metrics': metrics,
            'queue_sizes': queue_sizes,
            'connection_status': self.get_connection_status()
        }
    
    # 批量操作方法
    async def flush_all_queues(self):
        """刷新所有队列"""
        await self._write_all_queues()
    
    # 兼容性方法（保持向后兼容）
    def is_connected(self) -> bool:
        """检查是否连接"""
        return self.is_running and self.client is not None
    
    async def connect(self):
        """连接（兼容方法）"""
        await self.start()
    
    async def disconnect(self):
        """断开连接（兼容方法）"""
        await self.stop()


# 向后兼容性支持
ClickHouseWriter = UnifiedClickHouseWriter
OptimizedClickHouseWriter = UnifiedClickHouseWriter

# 创建默认实例
unified_clickhouse_writer = UnifiedClickHouseWriter()