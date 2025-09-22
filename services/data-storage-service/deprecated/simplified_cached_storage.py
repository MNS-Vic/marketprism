#!/usr/bin/env python3
"""
MarketPrism简化版高性能缓存热存储服务
基于修复后的Normalizer，移除复杂的字段转换逻辑
"""

import asyncio
import aiohttp
import json
import logging
import signal
import time
from collections import defaultdict, deque
from typing import Dict, List, Any, Optional
import nats

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SimplifiedCachedStorageService:
    """简化版高性能缓存热存储服务"""
    
    def __init__(self):
        self.nc = None
        self.running = False
        
        # 智能缓存配置 - 基于数据频率优化
        self.cache_config = {
            # 超高频数据 - 大批次，短超时
            'orderbooks': {'batch_size': 1000, 'timeout': 2.0, 'max_queue': 10000},
            'trades': {'batch_size': 500, 'timeout': 1.5, 'max_queue': 5000},
            
            # 中频数据 - 小批次，短超时（修复funding rate问题）
            'funding_rates': {'batch_size': 10, 'timeout': 2.0, 'max_queue': 500},
            'open_interests': {'batch_size': 20, 'timeout': 5.0, 'max_queue': 500},
            'lsr_top_positions': {'batch_size': 50, 'timeout': 5.0, 'max_queue': 1000},
            'lsr_all_accounts': {'batch_size': 50, 'timeout': 5.0, 'max_queue': 1000},
            
            # 低频数据 - 小批次，短超时（修复liquidation问题）
            'liquidations': {'batch_size': 5, 'timeout': 10.0, 'max_queue': 200},
            'volatility_indices': {'batch_size': 10, 'timeout': 10.0, 'max_queue': 300},
        }
        
        # 表映射
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
        
        # 缓存队列和锁
        self.data_queues = defaultdict(deque)
        self.last_flush_time = defaultdict(float)
        self.flush_locks = defaultdict(asyncio.Lock)
        
        # ClickHouse配置
        self.clickhouse_config = {
            'host': 'localhost',
            'port': 8123,
            'database': 'marketprism_hot'
        }
        
        # 统计信息
        self.stats = {
            'total_received': 0,
            'total_batches': 0,
            'total_inserted': 0,
            'errors': 0,
            'by_type': defaultdict(lambda: {'received': 0, 'batches': 0, 'inserted': 0, 'errors': 0})
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
        """消息处理器 - 简化版，假设数据已经标准化"""
        try:
            data = json.loads(msg.data.decode())
            subject = msg.subject
            
            data_type = self.extract_data_type(subject)
            if not data_type:
                return
                
            # 直接添加到缓存队列（假设数据已经标准化）
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
        """智能刷新检查"""
        config = self.cache_config.get(data_type, {'batch_size': 100, 'timeout': 5.0, 'max_queue': 1000})
        queue = self.data_queues[data_type]
        current_time = time.time()
        last_flush = self.last_flush_time.get(data_type, 0)
        
        should_flush = (
            len(queue) >= config['batch_size'] or  # 达到批大小
            (len(queue) > 0 and current_time - last_flush >= config['timeout']) or  # 超时
            len(queue) >= config['max_queue']  # 队列过大，强制刷新
        )
        
        if should_flush and not self.flush_locks[data_type].locked():
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
                    
                    # 记录批处理成功
                    if len(batch_data) >= 10:  # 记录较大批次
                        logger.info(f"✅ 批处理成功: {data_type} - {len(batch_data)}条")
                else:
                    # 失败时重新加入队列头部
                    for data in reversed(batch_data):
                        queue.appendleft(data)
                    self.stats['by_type'][data_type]['errors'] += 1
                    logger.error(f"❌ 批处理失败: {data_type} - {len(batch_data)}条")
                    
                self.last_flush_time[data_type] = time.time()
                
            except Exception as e:
                logger.error(f"❌ 批处理异常: {data_type} - {e}")
                self.stats['errors'] += 1
    
    async def batch_insert_to_clickhouse(self, data_type: str, batch_data: List[Dict]) -> bool:
        """批量插入数据到ClickHouse - 简化版，假设数据已经标准化"""
        try:
            table_name = self.table_mapping.get(data_type)
            if not table_name:
                return False
                
            # 构建批量插入SQL - 简化版
            insert_sql = self.build_simple_batch_sql(table_name, batch_data)
            if not insert_sql:
                return False
                
            # 执行批量插入
            url = f"http://{self.clickhouse_config['host']}:{self.clickhouse_config['port']}/?database={self.clickhouse_config['database']}"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=insert_sql) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"❌ ClickHouse错误: {response.status} - {error_text[:200]}")
                        return False
                    return True
                        
        except Exception as e:
            logger.error(f"❌ 批量插入异常: {e}")
            return False
    
    def build_simple_batch_sql(self, table_name: str, batch_data: List[Dict]) -> Optional[str]:
        """构建简化的批量插入SQL - 假设数据已经标准化"""
        try:
            if not batch_data:
                return None
                
            # 使用第一条记录的字段作为模板
            first_record = batch_data[0]
            fields = list(first_record.keys())
            
            # 构建VALUES
            values_list = []
            for data in batch_data:
                values = []
                for field in fields:
                    value = data.get(field)
                    if value is None:
                        values.append('NULL')
                    elif isinstance(value, str):
                        # 转义字符串
                        escaped_value = value.replace("\\", "\\\\").replace("'", "\\'")
                        values.append(f"'{escaped_value}'")
                    elif isinstance(value, (dict, list)):
                        # JSON字段
                        json_str = json.dumps(value).replace("\\", "\\\\").replace("'", "\\'")
                        values.append(f"'{json_str}'")
                    elif isinstance(value, bool):
                        values.append('1' if value else '0')
                    else:
                        values.append(str(value))
                
                values_list.append(f"({', '.join(values)})")
            
            # 构建完整SQL
            fields_str = ', '.join(fields)
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
                
                await asyncio.sleep(0.5)  # 每0.5秒检查一次
                
            except Exception as e:
                logger.error(f"❌ 定期维护异常: {e}")
                await asyncio.sleep(5)
    
    async def stats_reporter(self):
        """统计信息报告"""
        while self.running:
            try:
                await asyncio.sleep(60)  # 每分钟报告一次
                
                # 计算队列大小
                queue_sizes = {}
                total_queue_size = 0
                for dt, q in self.data_queues.items():
                    size = len(q)
                    if size > 0:
                        queue_sizes[dt] = size
                        total_queue_size += size
                
                # 计算批处理效率
                total_received = sum(stats['received'] for stats in self.stats['by_type'].values())
                total_inserted = sum(stats['inserted'] for stats in self.stats['by_type'].values())
                efficiency = (total_inserted / total_received * 100) if total_received > 0 else 0
                
                logger.info(f"📊 简化版性能统计 (过去1分钟):")
                logger.info(f"   接收: {total_received} | 插入: {total_inserted} | 效率: {efficiency:.1f}%")
                logger.info(f"   批次: {self.stats['total_batches']} | 错误: {self.stats['errors']}")
                if queue_sizes:
                    logger.info(f"   队列: {queue_sizes} (总计: {total_queue_size})")
                
                # 显示各数据类型统计
                for data_type, stats in self.stats['by_type'].items():
                    if stats['received'] > 0:
                        logger.info(f"   {data_type}: 接收{stats['received']} 插入{stats['inserted']} 批次{stats['batches']} 错误{stats['errors']}")
                
                # 重置计数器
                for stats in self.stats['by_type'].values():
                    stats['received'] = 0
                    stats['inserted'] = 0
                    stats['batches'] = 0
                    stats['errors'] = 0
                self.stats['total_batches'] = 0
                self.stats['errors'] = 0
                
            except Exception as e:
                logger.error(f"❌ 统计报告异常: {e}")
    
    async def start(self):
        """启动服务"""
        logger.info("🚀 启动简化版高性能缓存热存储服务...")
        
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
        
        logger.info("✅ 简化版缓存热存储服务启动成功")
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
        logger.info("🛑 停止简化版缓存热存储服务...")
        self.running = False
        
        # 刷新所有剩余数据
        logger.info("📤 刷新剩余缓存数据...")
        for data_type in list(self.data_queues.keys()):
            if self.data_queues[data_type]:
                await self.flush_batch(data_type)
        
        if self.nc:
            await self.nc.close()
        
        logger.info("✅ 简化版缓存热存储服务已停止")

async def main():
    service = SimplifiedCachedStorageService()
    
    def signal_handler(signum, frame):
        logger.info(f"收到信号 {signum}")
        asyncio.create_task(service.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    await service.start()

if __name__ == "__main__":
    asyncio.run(main())
