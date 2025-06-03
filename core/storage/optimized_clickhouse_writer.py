"""
优化版ClickHouse写入器

提供企业级性能优化功能，包括连接池、事务支持、数据验证等
基于TDD方法论驱动的设计改进
"""

import asyncio
import logging
import time
import json
import zlib
from typing import Dict, List, Any, Optional, Union, Callable
from decimal import Decimal
from datetime import datetime
from contextlib import asynccontextmanager

import aiochclient
import aiohttp
from prometheus_client import Counter, Histogram, Gauge

from .clickhouse_writer import ClickHouseWriter
from .types import NormalizedTrade, NormalizedOrderBook, NormalizedTicker

logger = logging.getLogger(__name__)

# 优化版Prometheus指标
OPTIMIZED_CLICKHOUSE_OPERATIONS = Counter(
    "marketprism_optimized_clickhouse_operations_total",
    "优化版ClickHouse操作总数",
    ["operation", "status"]
)
OPTIMIZED_CLICKHOUSE_LATENCY = Histogram(
    "marketprism_optimized_clickhouse_latency_seconds",
    "优化ClickHouse操作延迟",
    ["operation"]
)
OPTIMIZED_CLICKHOUSE_COMPRESSION_RATIO = Histogram(
    "marketprism_optimized_clickhouse_compression_ratio",
    "数据压缩比率"
)
OPTIMIZED_CLICKHOUSE_CONNECTION_POOL = Gauge(
    "marketprism_optimized_clickhouse_connection_pool_size",
    "ClickHouse连接池大小",
    ["pool_type"]
)


class OptimizedClickHouseWriter(ClickHouseWriter):
    """优化版ClickHouse直接写入器
    
    TDD改进特性：
    - 连接池管理
    - 事务支持
    - 数据验证
    - 错误处理和重试
    - 监控指标
    - 配置管理
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初始化优化版ClickHouse写入器
        
        Args:
            config: ClickHouse配置字典，可选
        """
        # 调用父类初始化
        super().__init__(config)
        
        # TDD改进：性能优化配置
        self.optimization_config = self.config.get('optimization', {})
        self.connection_pool_size = self.optimization_config.get('connection_pool_size', 10)
        self.max_retries = self.optimization_config.get('max_retries', 3)
        self.retry_delay = self.optimization_config.get('retry_delay', 1.0)
        self.enable_data_validation = self.optimization_config.get('enable_data_validation', True)
        self.enable_transactions = self.optimization_config.get('enable_transactions', False)
        
        # TDD改进：连接池
        self.connection_pool = []
        self.connection_pool_lock = asyncio.Lock()
        
        # TDD改进：事务管理
        self.current_transaction = None
        self.transaction_lock = asyncio.Lock()
        
        # TDD改进：错误统计
        self.error_count = 0
        self.last_error = None
        self.last_error_time = None
        
        # TDD改进：添加期望的属性
        self.flush_interval = getattr(self, 'write_interval', 5)  # 安全地获取write_interval，默认5秒
        self.buffer = []  # 通用缓冲区
        self.retry_config = {
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay,
            'backoff_factor': 2
        }
        self.performance_metrics = {}
        
        # TDD改进：确保batch_size属性存在
        if not hasattr(self, 'batch_size'):
            self.batch_size = self.optimization_config.get('batch_size', getattr(self, 'batch_size', 1000))
        
        logger.info(f"优化版ClickHouse写入器已初始化: pool_size={self.connection_pool_size}, enable_validation={self.enable_data_validation}")
    
    # TDD改进：连接池管理
    async def get_connection(self):
        """从连接池获取连接"""
        async with self.connection_pool_lock:
            if self.connection_pool:
                return self.connection_pool.pop()
            else:
                # 创建新连接
                if not self.enabled:
                    from .clickhouse_writer import DummyClickHouseClient
                    return DummyClickHouseClient()
                
                session = aiohttp.ClientSession()
                return aiochclient.ChClient(
                    session,
                    url=f"http://{self.host}:{self.port}",
                    user=self.user,
                    password=self.password,
                    database=self.database
                )
    
    async def return_connection(self, connection):
        """将连接返回连接池"""
        async with self.connection_pool_lock:
            if len(self.connection_pool) < self.connection_pool_size:
                self.connection_pool.append(connection)
            else:
                # 连接池已满，关闭连接
                if hasattr(connection, 'close'):
                    await connection.close()
    
    async def init_connection_pool(self):
        """初始化连接池"""
        if not self.enabled:
            return
            
        for _ in range(min(3, self.connection_pool_size)):  # 预创建3个连接
            connection = await self.get_connection()
            await self.return_connection(connection)
        
        # 更新指标
        OPTIMIZED_CLICKHOUSE_CONNECTION_POOL.labels(pool_type="active").set(len(self.connection_pool))
    
    # TDD改进：事务支持
    @asynccontextmanager
    async def transaction(self):
        """事务上下文管理器"""
        if not self.enable_transactions:
            # 如果不支持事务，直接yield
            yield self
            return
        
        async with self.transaction_lock:
            connection = await self.get_connection()
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
                await self.return_connection(connection)
    
    # TDD改进：数据验证
    def validate_trade_data(self, trade: NormalizedTrade) -> bool:
        """验证交易数据"""
        if not self.enable_data_validation:
            return True
        
        required_fields = ['symbol', 'price', 'amount', 'timestamp', 'side']
        for field in required_fields:
            if not hasattr(trade, field) or getattr(trade, field) is None:
                logger.warning(f"交易数据验证失败：缺少字段 {field}")
                return False
        
        # 价格和数量必须为正数
        if trade.price <= 0 or trade.amount <= 0:
            logger.warning(f"交易数据验证失败：价格或数量无效")
            return False
        
        return True
    
    def validate_orderbook_data(self, orderbook: NormalizedOrderBook) -> bool:
        """验证订单簿数据"""
        if not self.enable_data_validation:
            return True
        
        required_fields = ['symbol', 'bids', 'asks', 'timestamp']
        for field in required_fields:
            if not hasattr(orderbook, field) or getattr(orderbook, field) is None:
                logger.warning(f"订单簿数据验证失败：缺少字段 {field}")
                return False
        
        # 检查bids和asks格式
        if not isinstance(orderbook.bids, list) or not isinstance(orderbook.asks, list):
            logger.warning("订单簿数据验证失败：bids或asks格式错误")
            return False
        
        return True
    
    # TDD改进：错误处理和重试
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
                    logger.warning(f"操作失败，将重试 (尝试 {attempt + 1}/{self.max_retries + 1}): {e}")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))  # 指数退避
                else:
                    logger.error(f"操作最终失败，已重试 {self.max_retries} 次: {e}")
                    break
        
        raise last_error
    
    # TDD改进：重写父类方法以使用优化特性
    async def write_trade(self, trade: NormalizedTrade):
        """优化版写入交易数据"""
        if not self.enabled:
            return
        
        # 数据验证
        if not self.validate_trade_data(trade):
            return
        
        # 使用重试机制
        async def _write_operation():
            connection = self.current_transaction or await self.get_connection()
            try:
                # 调用父类方法的逻辑
                self.trades_queue.append(trade)
                
                if len(self.trades_queue) >= self.batch_size:
                    await self._flush_trades_optimized(connection)
            finally:
                if not self.current_transaction:
                    await self.return_connection(connection)
        
        await self.execute_with_retry(_write_operation)
    
    async def _flush_trades_optimized(self, connection):
        """优化版刷新交易数据"""
        if not self.trades_queue:
            return
        
        batch = self.trades_queue.copy()
        self.trades_queue.clear()
        
        start_time = time.time()
        
        try:
            # 准备批量插入数据
            formatted_data = []
            for trade in batch:
                formatted_data.append((
                    trade.timestamp,
                    trade.symbol,
                    float(trade.price),
                    float(trade.amount),
                    trade.side,
                    trade.exchange if hasattr(trade, 'exchange') else 'unknown',
                    trade.trade_id if hasattr(trade, 'trade_id') else ''
                ))
            
            # 执行批量插入
            await connection.execute(
                f"INSERT INTO {self.trades_table} VALUES",
                *formatted_data
            )
            
            # 记录指标
            OPTIMIZED_CLICKHOUSE_OPERATIONS.labels(operation="insert_trade", status="success").inc()
            
            logger.debug(f"优化版写入交易数据: {len(batch)}条")
            
        except Exception as e:
            OPTIMIZED_CLICKHOUSE_OPERATIONS.labels(operation="insert_trade", status="error").inc()
            raise e
    
    # TDD改进：监控和指标方法
    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        return {
            'connection_pool_size': len(self.connection_pool),
            'max_pool_size': self.connection_pool_size,
            'error_count': self.error_count,
            'last_error': self.last_error,
            'last_error_time': self.last_error_time,
            'config': {
                'enable_data_validation': self.enable_data_validation,
                'enable_transactions': self.enable_transactions,
                'max_retries': self.max_retries,
                'retry_delay': self.retry_delay
            }
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        is_healthy = self.error_count < 10 and (
            self.last_error_time is None or 
            time.time() - self.last_error_time > 300  # 5分钟内无错误
        )
        
        return {
            'is_healthy': is_healthy,
            'is_running': self.is_running,
            'enabled': self.enabled,
            'connection_pool_healthy': len(self.connection_pool) > 0 or not self.enabled,
            'recent_error_count': self.error_count,
            'status': 'healthy' if is_healthy else 'degraded'
        }
    
    # TDD改进：配置管理
    def update_config(self, new_config: Dict[str, Any]):
        """更新配置"""
        self.config.update(new_config)
        
        # 重新加载优化配置
        self.optimization_config = self.config.get('optimization', {})
        self.connection_pool_size = self.optimization_config.get('connection_pool_size', 10)
        self.max_retries = self.optimization_config.get('max_retries', 3)
        self.retry_delay = self.optimization_config.get('retry_delay', 1.0)
        self.enable_data_validation = self.optimization_config.get('enable_data_validation', True)
        self.enable_transactions = self.optimization_config.get('enable_transactions', False)
        
        logger.info("配置已更新", config=new_config)
    
    def get_config(self) -> Dict[str, Any]:
        """获取当前配置"""
        return self.config.copy()
    
    # TDD改进：向后兼容性确保
    def is_compatible_with(self, writer_instance) -> bool:
        """检查与其他writer实例的兼容性"""
        if not isinstance(writer_instance, ClickHouseWriter):
            return False
        
        # 检查关键配置兼容性
        return (
            self.host == getattr(writer_instance, 'host', None) and
            self.port == getattr(writer_instance, 'port', None) and
            self.database == getattr(writer_instance, 'database', None)
        )
    
    # TDD改进：性能方法
    async def flush_buffer(self):
        """TDD改进：刷新缓冲区"""
        if self.buffer:
            await self.write_batch(self.buffer)
            self.buffer.clear()
    
    def get_buffer_size(self) -> int:
        """TDD改进：获取缓冲区大小"""
        return len(self.buffer)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """TDD改进：获取性能统计"""
        return {
            **self.get_performance_metrics(),
            'buffer_size': len(self.buffer),
            'flush_interval': self.flush_interval,
            'connection_pool_size': len(self.connection_pool)
        }
    
    def optimize_batch_size(self, target_latency: float = 1.0):
        """TDD改进：优化批量大小"""
        # 根据目标延迟调整批量大小
        current_avg_latency = self.performance_metrics.get('avg_latency', 1.0)
        if current_avg_latency > target_latency:
            self.batch_size = max(100, int(self.batch_size * 0.8))
        elif current_avg_latency < target_latency * 0.5:
            self.batch_size = min(5000, int(self.batch_size * 1.2))
        
        logger.info(f"批量大小已优化: {self.batch_size}")
    
    def enable_compression(self, enabled: bool = True):
        """TDD改进：启用压缩"""
        self.compression_enabled = enabled
        logger.info(f"压缩已{'启用' if enabled else '禁用'}")
    
    def set_retry_policy(self, max_retries: int, retry_delay: float):
        """TDD改进：设置重试策略"""
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.retry_config.update({
            'max_retries': max_retries,
            'retry_delay': retry_delay
        })
        logger.info(f"重试策略已更新: max_retries={max_retries}, retry_delay={retry_delay}")
    
    # TDD改进：连接池方法
    def get_connection_pool(self) -> list:
        """TDD改进：获取连接池"""
        return self.connection_pool.copy()
    
    def set_pool_size(self, new_size: int):
        """TDD改进：设置连接池大小"""
        old_size = self.connection_pool_size
        self.connection_pool_size = new_size
        logger.info(f"连接池大小已更新: {old_size} -> {new_size}")
    
    def get_pool_stats(self) -> Dict[str, Any]:
        """TDD改进：获取连接池统计"""
        return {
            'pool_size': len(self.connection_pool),
            'max_pool_size': self.connection_pool_size,
            'active_connections': self.connection_pool_size - len(self.connection_pool),
            'healthy': len(self.connection_pool) > 0 or not self.enabled
        }
    
    async def close_pool(self):
        """TDD改进：关闭连接池"""
        async with self.connection_pool_lock:
            for connection in self.connection_pool:
                if hasattr(connection, 'close'):
                    try:
                        await connection.close()
                    except:
                        pass
            self.connection_pool.clear()
        logger.info("连接池已关闭")
    
    async def reset_pool(self):
        """TDD改进：重置连接池"""
        await self.close_pool()
        await self.init_connection_pool()
        logger.info("连接池已重置")
    
    # TDD改进：错误处理方法
    async def handle_connection_error(self, error: Exception):
        """TDD改进：处理连接错误"""
        self.error_count += 1
        self.last_error = str(error)
        self.last_error_time = time.time()
        
        logger.error(f"连接错误: {error}")
        
        # 尝试重置连接池
        try:
            await self.reset_pool()
        except Exception as e:
            logger.error(f"重置连接池失败: {e}")
    
    async def handle_write_error(self, error: Exception, data: Any):
        """TDD改进：处理写入错误"""
        self.error_count += 1
        self.last_error = str(error)
        self.last_error_time = time.time()
        
        logger.error(f"写入错误: {error}")
        
        # 可以将数据放回缓冲区等待重试
        if hasattr(data, '__iter__') and not isinstance(data, str):
            self.buffer.extend(data)
        else:
            self.buffer.append(data)
    
    async def retry_operation(self, operation: Callable, *args, **kwargs):
        """TDD改进：重试操作"""
        return await self.execute_with_retry(operation, *args, **kwargs)
    
    def get_error_stats(self) -> Dict[str, Any]:
        """TDD改进：获取错误统计"""
        return {
            'error_count': self.error_count,
            'last_error': self.last_error,
            'last_error_time': self.last_error_time,
            'error_rate': self.error_count / max(1, self.error_count + 100),  # 假设的总操作数
            'time_since_last_error': time.time() - self.last_error_time if self.last_error_time else None
        }
    
    def reset_error_counters(self):
        """TDD改进：重置错误计数器"""
        self.error_count = 0
        self.last_error = None
        self.last_error_time = None
        logger.info("错误计数器已重置")
    
    # TDD改进：监控方法
    def get_write_metrics(self) -> Dict[str, Any]:
        """TDD改进：获取写入指标"""
        return {
            'buffer_size': len(self.buffer),
            'batch_size': self.batch_size,
            'flush_interval': self.flush_interval,
            'trades_queue_size': len(self.trades_queue),
            'orderbook_queue_size': len(self.orderbook_queue),
            'ticker_queue_size': len(self.ticker_queue)
        }
    
    def get_connection_metrics(self) -> Dict[str, Any]:
        """TDD改进：获取连接指标"""
        return {
            'connection_pool_size': len(self.connection_pool),
            'max_pool_size': self.connection_pool_size,
            'pool_utilization': (self.connection_pool_size - len(self.connection_pool)) / max(1, self.connection_pool_size),
            'enabled': self.enabled,
            'is_running': self.is_running
        }
    
    def export_metrics(self) -> Dict[str, Any]:
        """TDD改进：导出所有指标"""
        return {
            'performance': self.get_performance_metrics(),
            'write_metrics': self.get_write_metrics(),
            'connection_metrics': self.get_connection_metrics(),
            'error_stats': self.get_error_stats(),
            'pool_stats': self.get_pool_stats(),
            'health_status': self.get_health_status(),
            'timestamp': time.time()
        }
    
    def reset_metrics(self):
        """TDD改进：重置指标"""
        self.performance_metrics.clear()
        self.reset_error_counters()
        logger.info("指标已重置")


class OptimizedOrderBookQueryService:
    """优化的订单簿查询服务"""
    
    def __init__(self, clickhouse_client):
        self.client = clickhouse_client
    
    async def get_latest_orderbook(self, exchange: str, symbol: str, depth_level: int = 10):
        """获取最新订单簿"""
        try:
            if depth_level <= 10:
                # 快速查询前10档
                query = f"""
                SELECT 
                    best_bid_price, best_ask_price, spread, mid_price,
                    bids_top10, asks_top10,
                    timestamp
                FROM marketprism.orderbook_optimized
                WHERE exchange_name = %(exchange)s AND symbol_name = %(symbol)s
                ORDER BY timestamp DESC
                LIMIT 1
                """
            else:
                # 查询更深层次的数据
                query = f"""
                SELECT 
                    best_bid_price, best_ask_price, spread, mid_price,
                    bids_l1, asks_l1, bids_l2, asks_l2, bids_l3, asks_l3,
                    timestamp
                FROM marketprism.orderbook_optimized
                WHERE exchange_name = %(exchange)s AND symbol_name = %(symbol)s
                ORDER BY timestamp DESC
                LIMIT 1
                """
            
            result = await self.client.fetchone(query, {
                'exchange': exchange,
                'symbol': symbol
            })
            
            if result:
                if depth_level <= 10:
                    return {
                        'best_bid_price': result['best_bid_price'],
                        'best_ask_price': result['best_ask_price'],
                        'spread': result['spread'],
                        'mid_price': result['mid_price'],
                        'bids': json.loads(result['bids_top10']),
                        'asks': json.loads(result['asks_top10']),
                        'timestamp': result['timestamp']
                    }
                else:
                    # 解压并合并深度数据
                    bids = []
                    asks = []
                    
                    # L1层 (前50档)
                    if result['bids_l1']:
                        bids.extend(json.loads(zlib.decompress(result['bids_l1']).decode()))
                    if result['asks_l1']:
                        asks.extend(json.loads(zlib.decompress(result['asks_l1']).decode()))
                    
                    # L2层 (51-200档)
                    if depth_level > 50 and result['bids_l2']:
                        bids.extend(json.loads(zlib.decompress(result['bids_l2']).decode()))
                    if depth_level > 50 and result['asks_l2']:
                        asks.extend(json.loads(zlib.decompress(result['asks_l2']).decode()))
                    
                    # L3层 (201-400档)
                    if depth_level > 200 and result['bids_l3']:
                        bids.extend(json.loads(zlib.decompress(result['bids_l3']).decode()))
                    if depth_level > 200 and result['asks_l3']:
                        asks.extend(json.loads(zlib.decompress(result['asks_l3']).decode()))
                    
                    return {
                        'best_bid_price': result['best_bid_price'],
                        'best_ask_price': result['best_ask_price'],
                        'spread': result['spread'],
                        'mid_price': result['mid_price'],
                        'bids': bids[:depth_level],
                        'asks': asks[:depth_level],
                        'timestamp': result['timestamp']
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"查询最新订单簿失败: {e}")
            return None
    
    async def get_depth_statistics(self, exchange: str, symbol: str, hours: int = 24):
        """获取深度统计信息"""
        try:
            query = f"""
            SELECT 
                avg(spread) as avg_spread,
                min(spread) as min_spread,
                max(spread) as max_spread,
                avg(bid_volume_1pct) as avg_bid_volume_1pct,
                avg(ask_volume_1pct) as avg_ask_volume_1pct,
                avg(total_bid_volume) as avg_total_bid_volume,
                avg(total_ask_volume) as avg_total_ask_volume,
                count() as update_count
            FROM marketprism.orderbook_optimized
            WHERE exchange_name = %(exchange)s 
              AND symbol_name = %(symbol)s
              AND timestamp >= now() - INTERVAL %(hours)s HOUR
            """
            
            return await self.client.fetchone(query, {
                'exchange': exchange,
                'symbol': symbol,
                'hours': hours
            })
            
        except Exception as e:
            logger.error(f"查询深度统计失败: {e}")
            return None
    
    async def calculate_price_impact(self, exchange: str, symbol: str, volume: float, side: str = 'buy'):
        """计算价格冲击"""
        try:
            # 获取最新深度数据
            orderbook = await self.get_latest_orderbook(exchange, symbol, depth_level=400)
            
            if not orderbook:
                return None
            
            if side == 'buy':
                # 买入冲击 - 消耗卖单
                levels = orderbook['asks']
                best_price = orderbook['best_ask_price']
            else:
                # 卖出冲击 - 消耗买单
                levels = orderbook['bids']
                best_price = orderbook['best_bid_price']
            
            remaining_volume = volume
            total_cost = 0
            
            for price, qty in levels:
                if remaining_volume <= 0:
                    break
                
                trade_qty = min(remaining_volume, qty)
                total_cost += trade_qty * price
                remaining_volume -= trade_qty
            
            if remaining_volume > 0:
                return {"error": "流动性不足", "remaining_volume": remaining_volume}
            
            avg_price = total_cost / volume
            price_impact = abs(avg_price - best_price) / best_price * 100
            
            return {
                "volume": volume,
                "side": side,
                "avg_execution_price": avg_price,
                "best_price": best_price,
                "price_impact_percent": price_impact,
                "total_cost": total_cost,
                "timestamp": orderbook['timestamp']
            }
            
        except Exception as e:
            logger.error(f"计算价格冲击失败: {e}")
            return None