#!/usr/bin/env python3
"""
MarketPrism高性能缓存热存储服务
使用内存缓存和批处理优化高频数据写入性能
"""

import asyncio
import aiohttp
import json
import logging
import signal
import sys
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import nats
from nats.errors import TimeoutError, NoServersError

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CachedHotStorageService:
    """高性能缓存热存储服务"""
    
    def __init__(self):
        self.nc = None
        self.running = False
        
        # 缓存配置 - 针对不同数据类型的不同策略
        self.cache_config = {
            # 高频数据 - 大批次，短超时
            'orderbook': {'batch_size': 500, 'timeout': 3.0, 'max_queue': 5000},
            'trade': {'batch_size': 200, 'timeout': 2.0, 'max_queue': 2000},
            
            # 中频数据 - 中批次，中超时
            'funding_rate': {'batch_size': 50, 'timeout': 10.0, 'max_queue': 500},
            'open_interest': {'batch_size': 50, 'timeout': 10.0, 'max_queue': 500},
            'lsr_top_position': {'batch_size': 100, 'timeout': 5.0, 'max_queue': 1000},
            'lsr_all_account': {'batch_size': 100, 'timeout': 5.0, 'max_queue': 1000},
            
            # 低频数据 - 小批次，长超时
            'liquidation': {'batch_size': 20, 'timeout': 30.0, 'max_queue': 200},
            'volatility_index': {'batch_size': 30, 'timeout': 15.0, 'max_queue': 300},
        }
        
        # 数据缓存队列
        self.data_queues = defaultdict(deque)
        self.last_flush_time = defaultdict(float)
        self.flush_locks = defaultdict(asyncio.Lock)
        
        # ClickHouse配置
        self.clickhouse_config = {
            'host': 'localhost',
            'port': 8123,
            'database': 'marketprism_hot'
        }
        
        # 表映射和字段映射
        self.table_mapping = {
            'orderbook': 'orderbooks',
            'trade': 'trades',
            'funding_rate': 'funding_rates',
            'open_interest': 'open_interests',
            'liquidation': 'liquidations',
            'lsr_top_position': 'lsr_top_positions',
            'lsr_all_account': 'lsr_all_accounts',
            'volatility_index': 'volatility_indices'
        }
        
        # 字段映射 - 确保只插入表中存在的字段
        self.field_mapping = {
            'orderbooks': ['timestamp', 'exchange', 'market_type', 'symbol', 'last_update_id',
                          'best_bid_price', 'best_ask_price', 'bids', 'asks', 'data_source'],
            'trades': ['timestamp', 'exchange', 'market_type', 'symbol', 'trade_id',
                      'price', 'quantity', 'side', 'data_source', 'is_maker'],
            'funding_rates': ['timestamp', 'exchange', 'market_type', 'symbol', 
                             'current_funding_rate', 'next_funding_time', 'data_source'],
            'open_interests': ['timestamp', 'exchange', 'market_type', 'symbol', 
                              'open_interest', 'data_source'],
            'liquidations': ['timestamp', 'exchange', 'market_type', 'symbol', 
                            'side', 'quantity', 'price', 'data_source'],
            'lsr_top_positions': ['timestamp', 'exchange', 'market_type', 'symbol', 
                                 'long_position_ratio', 'short_position_ratio', 'period', 'data_source'],
            'lsr_all_accounts': ['timestamp', 'exchange', 'market_type', 'symbol', 
                                'long_account_ratio', 'short_account_ratio', 'period', 'data_source'],
            'volatility_indices': ['timestamp', 'exchange', 'market_type', 'symbol', 
                                  'volatility_index', 'data_source']
        }
        
        # 统计信息
        self.stats = {
            'total_received': 0,
            'total_batches': 0,
            'total_inserted': 0,
            'cache_hits': 0,
            'errors': 0,
            'by_type': defaultdict(lambda: {'received': 0, 'batches': 0, 'inserted': 0})
        }
        
    async def connect_nats(self):
        """连接到NATS服务器"""
        try:
            self.nc = await nats.connect("nats://localhost:4222")
            logger.info("✅ 连接到NATS服务器成功")
            return True
        except Exception as e:
            logger.error(f"❌ 连接NATS失败: {e}")
            return False
    
    async def subscribe_to_data_streams(self):
        """订阅所有数据流"""
        try:
            subjects = [
                "orderbook-data.>",
                "trade-data.>", 
                "funding-rate-data.>",
                "open-interest-data.>",
                "liquidation-data.>",
                "lsr-data.>",
                "volatility-index-data.>"
            ]
            
            for subject in subjects:
                await self.nc.subscribe(subject, cb=self.message_handler)
                logger.info(f"✅ 订阅成功: {subject}")
                
            return True
        except Exception as e:
            logger.error(f"❌ 订阅失败: {e}")
            return False
    
    async def message_handler(self, msg):
        """消息处理器 - 智能缓存"""
        try:
            data = json.loads(msg.data.decode())
            subject = msg.subject
            
            data_type = self.extract_data_type(subject)
            if not data_type:
                return
                
            # 添加到缓存队列
            self.data_queues[data_type].append(data)
            self.stats['total_received'] += 1
            self.stats['by_type'][data_type]['received'] += 1
            
            # 智能刷新检查
            await self.smart_flush_check(data_type)
            
        except Exception as e:
            logger.error(f"❌ 消息处理失败: {e}")
            self.stats['errors'] += 1
    
    def extract_data_type(self, subject: str) -> Optional[str]:
        """从主题中提取数据类型"""
        if subject.startswith("orderbook-data"):
            return "orderbook"
        elif subject.startswith("trade-data"):
            return "trade"
        elif subject.startswith("funding-rate-data"):
            return "funding_rate"
        elif subject.startswith("open-interest-data"):
            return "open_interest"
        elif subject.startswith("liquidation-data"):
            return "liquidation"
        elif subject.startswith("lsr-data"):
            if "top-position" in subject:
                return "lsr_top_position"
            elif "all-account" in subject:
                return "lsr_all_account"
        elif subject.startswith("volatility-index-data"):
            return "volatility_index"
        return None
    
    async def smart_flush_check(self, data_type: str):
        """智能刷新检查 - 根据数据类型使用不同策略"""
        config = self.cache_config.get(data_type, {'batch_size': 100, 'timeout': 5.0, 'max_queue': 1000})
        queue = self.data_queues[data_type]
        current_time = time.time()
        last_flush = self.last_flush_time.get(data_type, 0)
        
        should_flush = (
            len(queue) >= config['batch_size'] or  # 达到批大小
            (len(queue) > 0 and current_time - last_flush >= config['timeout']) or  # 超时
            len(queue) >= config['max_queue']  # 队列过大，强制刷新
        )
        
        if should_flush:
            # 使用锁防止并发刷新
            if not self.flush_locks[data_type].locked():
                asyncio.create_task(self.flush_batch(data_type))
    
    async def flush_batch(self, data_type: str):
        """批量刷新数据到ClickHouse"""
        async with self.flush_locks[data_type]:
            queue = self.data_queues[data_type]
            if not queue:
                return
                
            try:
                config = self.cache_config.get(data_type, {'batch_size': 100})
                batch_data = []
                batch_size = min(len(queue), config['batch_size'])
                
                # 提取批数据
                for _ in range(batch_size):
                    if queue:
                        batch_data.append(queue.popleft())
                
                if not batch_data:
                    return
                    
                # 批量插入
                success = await self.batch_insert_to_clickhouse(data_type, batch_data)
                
                if success:
                    self.stats['total_batches'] += 1
                    self.stats['total_inserted'] += len(batch_data)
                    self.stats['by_type'][data_type]['batches'] += 1
                    self.stats['by_type'][data_type]['inserted'] += len(batch_data)
                    
                    if len(batch_data) >= 100:  # 只记录大批次
                        logger.info(f"✅ 大批次写入: {data_type} - {len(batch_data)}条")
                else:
                    # 失败时重新加入队列头部
                    for data in reversed(batch_data):
                        queue.appendleft(data)
                    logger.error(f"❌ 批处理失败: {data_type}")
                    
                self.last_flush_time[data_type] = time.time()
                
            except Exception as e:
                logger.error(f"❌ 批处理异常: {data_type} - {e}")
                self.stats['errors'] += 1
    
    async def batch_insert_to_clickhouse(self, data_type: str, batch_data: List[Dict]) -> bool:
        """批量插入数据到ClickHouse"""
        try:
            table_name = self.table_mapping.get(data_type)
            if not table_name:
                return False
                
            # 构建批量插入SQL
            insert_sql = self.build_optimized_batch_sql(table_name, batch_data)
            if not insert_sql:
                return False
                
            # 执行批量插入
            url = f"http://{self.clickhouse_config['host']}:{self.clickhouse_config['port']}/?database={self.clickhouse_config['database']}"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=insert_sql) as response:
                    return response.status == 200
                        
        except Exception as e:
            logger.error(f"❌ 批量插入异常: {e}")
            return False
    
    def clean_data_for_table(self, table_name: str, data: Dict) -> Dict:
        """清理数据，只保留表中存在的字段"""
        allowed_fields = self.field_mapping.get(table_name, [])
        if not allowed_fields:
            return data

        cleaned_data = {}
        for field in allowed_fields:
            if field in data:
                cleaned_data[field] = data[field]
            elif field == 'data_source':
                cleaned_data[field] = 'marketprism'  # 默认值
            elif field == 'is_maker':
                cleaned_data[field] = False  # 默认值

        return cleaned_data

    def build_optimized_batch_sql(self, table_name: str, batch_data: List[Dict]) -> Optional[str]:
        """构建优化的批量插入SQL"""
        try:
            if not batch_data:
                return None

            # 获取表的字段映射
            allowed_fields = self.field_mapping.get(table_name, [])
            if not allowed_fields:
                return None

            # 清理并过滤字段
            cleaned_batch = []
            for data in batch_data:
                cleaned_data = self.clean_data_for_table(table_name, data)
                if cleaned_data:
                    cleaned_batch.append(cleaned_data)

            if not cleaned_batch:
                return None

            # 构建VALUES
            values_list = []
            for data in cleaned_batch:
                values = []
                for field in allowed_fields:
                    value = data.get(field)
                    if value is None:
                        values.append('NULL')
                    elif isinstance(value, str):
                        escaped_value = value.replace("'", "\\'").replace("\\", "\\\\")
                        values.append(f"'{escaped_value}'")
                    elif isinstance(value, (dict, list)):
                        json_str = json.dumps(value).replace("'", "\\'").replace("\\", "\\\\")
                        values.append(f"'{json_str}'")
                    elif isinstance(value, bool):
                        values.append('1' if value else '0')
                    else:
                        values.append(str(value))

                values_list.append(f"({', '.join(values)})")

            # 构建完整SQL
            fields_str = ', '.join(allowed_fields)
            values_str = ', '.join(values_list)
            sql = f"INSERT INTO {table_name} ({fields_str}) VALUES {values_str}"

            return sql

        except Exception as e:
            logger.error(f"❌ 构建批量SQL失败: {e}")
            return None
    
    async def periodic_maintenance(self):
        """定期维护任务"""
        while self.running:
            try:
                current_time = time.time()
                
                # 检查超时的队列
                for data_type in list(self.data_queues.keys()):
                    config = self.cache_config.get(data_type, {'timeout': 5.0})
                    queue = self.data_queues[data_type]
                    last_flush = self.last_flush_time.get(data_type, 0)
                    
                    if len(queue) > 0 and current_time - last_flush >= config['timeout']:
                        if not self.flush_locks[data_type].locked():
                            asyncio.create_task(self.flush_batch(data_type))
                
                await asyncio.sleep(1)  # 每秒检查一次
                
            except Exception as e:
                logger.error(f"❌ 定期维护异常: {e}")
                await asyncio.sleep(5)
    
    async def stats_reporter(self):
        """统计信息报告"""
        while self.running:
            try:
                await asyncio.sleep(60)  # 每分钟报告一次
                
                queue_sizes = {dt: len(q) for dt, q in self.data_queues.items() if len(q) > 0}
                
                logger.info(f"📊 缓存统计:")
                logger.info(f"   总接收: {self.stats['total_received']}")
                logger.info(f"   总批次: {self.stats['total_batches']}")
                logger.info(f"   总插入: {self.stats['total_inserted']}")
                logger.info(f"   错误数: {self.stats['errors']}")
                if queue_sizes:
                    logger.info(f"   队列大小: {queue_sizes}")
                
                # 重置计数器
                self.stats['total_received'] = 0
                self.stats['total_batches'] = 0
                self.stats['total_inserted'] = 0
                
            except Exception as e:
                logger.error(f"❌ 统计报告异常: {e}")
    
    async def start(self):
        """启动服务"""
        logger.info("🚀 启动高性能缓存热存储服务...")
        
        if not await self.connect_nats():
            return False
            
        if not await self.subscribe_to_data_streams():
            return False
            
        self.running = True
        
        # 启动后台任务
        tasks = [
            asyncio.create_task(self.periodic_maintenance()),
            asyncio.create_task(self.stats_reporter())
        ]
        
        logger.info("✅ 高性能缓存热存储服务启动成功")
        logger.info("📋 缓存配置:")
        for data_type, config in self.cache_config.items():
            logger.info(f"   {data_type}: 批次{config['batch_size']}, 超时{config['timeout']}s")
        
        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            logger.info("收到停止信号")
        finally:
            await self.stop()
    
    async def stop(self):
        """停止服务"""
        logger.info("🛑 停止缓存热存储服务...")
        self.running = False
        
        # 刷新所有剩余数据
        for data_type in list(self.data_queues.keys()):
            if self.data_queues[data_type]:
                await self.flush_batch(data_type)
        
        if self.nc:
            await self.nc.close()
        
        logger.info("✅ 缓存热存储服务已停止")

async def main():
    service = CachedHotStorageService()
    
    def signal_handler(signum, frame):
        logger.info(f"收到信号 {signum}")
        asyncio.create_task(service.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    await service.start()

if __name__ == "__main__":
    asyncio.run(main())
