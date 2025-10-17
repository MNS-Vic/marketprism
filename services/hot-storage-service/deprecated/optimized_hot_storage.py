#!/usr/bin/env python3
"""
MarketPrism优化热存储服务
解决高频INSERT导致的性能问题，使用批处理优化
"""

import asyncio
import aiohttp
import json
import logging
import signal
import sys
from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, List, Any, Optional
import nats
from nats.errors import TimeoutError, NoServersError

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OptimizedHotStorageService:
    """优化的热存储服务，使用批处理减少ClickHouse压力"""
    
    def __init__(self):
        self.nc = None
        self.running = False
        
        # 批处理配置
        self.batch_size = 100  # 每批最多100条记录
        self.batch_timeout = 5.0  # 5秒超时
        self.max_queue_size = 10000  # 最大队列大小
        
        # 数据缓存队列
        self.data_queues = defaultdict(deque)  # 按数据类型分组
        self.last_flush_time = defaultdict(float)
        
        # ClickHouse配置
        self.clickhouse_config = {
            'host': 'localhost',
            'port': 8123,
            'database': 'marketprism_hot'
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

        # 字段过滤 - 移除不存在于表中的字段
        self.excluded_fields = {'data_type', 'exchange_name', 'product_type'}
        
        # 统计信息
        self.stats = {
            'total_received': 0,
            'total_batches': 0,
            'total_inserted': 0,
            'batch_sizes': deque(maxlen=1000),
            'errors': 0
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
            # 订阅所有数据类型
            subjects = [
                "orderbook.>",
                "trade.>",
                "funding_rate.>",
                "open_interest.>",
                "liquidation.>",
                "lsr_top_position.>",
                "lsr_all_account.>",
                "volatility_index.>"
            ]
            
            for subject in subjects:
                await self.nc.subscribe(subject, cb=self.message_handler)
                logger.info(f"✅ 订阅成功: {subject}")
                
            return True
        except Exception as e:
            logger.error(f"❌ 订阅失败: {e}")
            return False
    
    async def message_handler(self, msg):
        """消息处理器 - 添加到批处理队列"""
        try:
            # 解析消息
            data = json.loads(msg.data.decode())
            subject = msg.subject
            
            # 提取数据类型
            data_type = self.extract_data_type(subject)
            if not data_type:
                return
                
            # 添加到队列
            self.data_queues[data_type].append(data)
            self.stats['total_received'] += 1
            
            # 检查是否需要刷新
            await self.check_and_flush(data_type)
            
        except Exception as e:
            logger.error(f"❌ 消息处理失败: {e}")
            self.stats['errors'] += 1
    
    def extract_data_type(self, subject: str) -> Optional[str]:
        """从主题中提取数据类型"""
        try:
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
        except:
            return None
    
    async def check_and_flush(self, data_type: str):
        """检查是否需要刷新批处理"""
        queue = self.data_queues[data_type]
        current_time = asyncio.get_event_loop().time()
        last_flush = self.last_flush_time[data_type]
        
        # 检查刷新条件
        should_flush = (
            len(queue) >= self.batch_size or  # 达到批大小
            (len(queue) > 0 and current_time - last_flush >= self.batch_timeout) or  # 超时
            len(queue) >= self.max_queue_size  # 队列过大
        )
        
        if should_flush:
            await self.flush_batch(data_type)
    
    async def flush_batch(self, data_type: str):
        """刷新批处理数据到ClickHouse"""
        queue = self.data_queues[data_type]
        if not queue:
            return
            
        try:
            # 提取批数据
            batch_data = []
            batch_size = min(len(queue), self.batch_size)
            
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
                self.stats['batch_sizes'].append(len(batch_data))
                logger.info(f"✅ 批处理成功: {data_type} - {len(batch_data)}条记录")
            else:
                # 失败时重新加入队列
                for data in reversed(batch_data):
                    queue.appendleft(data)
                logger.error(f"❌ 批处理失败: {data_type}")
                
            self.last_flush_time[data_type] = asyncio.get_event_loop().time()
            
        except Exception as e:
            logger.error(f"❌ 批处理异常: {data_type} - {e}")
            self.stats['errors'] += 1
    
    async def batch_insert_to_clickhouse(self, data_type: str, batch_data: List[Dict]) -> bool:
        """批量插入数据到ClickHouse"""
        try:
            table_name = self.table_mapping.get(data_type, data_type)
            
            # 构建批量插入SQL
            insert_sql = self.build_batch_insert_sql(table_name, batch_data)
            if not insert_sql:
                return False
                
            # 执行批量插入
            url = f"http://{self.clickhouse_config['host']}:{self.clickhouse_config['port']}/?database={self.clickhouse_config['database']}"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=insert_sql) as response:
                    if response.status == 200:
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ ClickHouse错误: {response.status} - {error_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ 批量插入异常: {e}")
            return False
    
    def build_batch_insert_sql(self, table_name: str, batch_data: List[Dict]) -> Optional[str]:
        """构建批量插入SQL"""
        try:
            if not batch_data:
                return None

            # 使用第一条记录确定字段，过滤掉不需要的字段
            first_record = batch_data[0]
            fields = [f for f in first_record.keys() if f not in self.excluded_fields]
            
            # 构建VALUES部分
            values_list = []
            for data in batch_data:
                values = []
                for field in fields:
                    value = data.get(field)
                    if value is None:
                        values.append('NULL')
                    elif isinstance(value, str):
                        # 转义单引号
                        escaped_value = value.replace("'", "\\'")
                        values.append(f"'{escaped_value}'")
                    elif isinstance(value, (dict, list)):
                        # JSON字段
                        json_str = json.dumps(value).replace("'", "\\'")
                        values.append(f"'{json_str}'")
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
    
    async def periodic_flush(self):
        """定期刷新所有队列"""
        while self.running:
            try:
                current_time = asyncio.get_event_loop().time()
                
                for data_type in list(self.data_queues.keys()):
                    queue = self.data_queues[data_type]
                    last_flush = self.last_flush_time[data_type]
                    
                    # 检查超时的队列
                    if len(queue) > 0 and current_time - last_flush >= self.batch_timeout:
                        await self.flush_batch(data_type)
                
                await asyncio.sleep(1)  # 每秒检查一次
                
            except Exception as e:
                logger.error(f"❌ 定期刷新异常: {e}")
                await asyncio.sleep(5)
    
    async def stats_reporter(self):
        """统计信息报告"""
        while self.running:
            try:
                await asyncio.sleep(60)  # 每分钟报告一次
                
                avg_batch_size = 0
                if self.stats['batch_sizes']:
                    avg_batch_size = sum(self.stats['batch_sizes']) / len(self.stats['batch_sizes'])
                
                queue_sizes = {dt: len(q) for dt, q in self.data_queues.items()}
                
                logger.info(f"📊 统计报告:")
                logger.info(f"   总接收: {self.stats['total_received']}")
                logger.info(f"   总批次: {self.stats['total_batches']}")
                logger.info(f"   总插入: {self.stats['total_inserted']}")
                logger.info(f"   平均批大小: {avg_batch_size:.1f}")
                logger.info(f"   错误数: {self.stats['errors']}")
                logger.info(f"   队列大小: {queue_sizes}")
                
            except Exception as e:
                logger.error(f"❌ 统计报告异常: {e}")
    
    async def start(self):
        """启动服务"""
        logger.info("🚀 启动优化热存储服务...")
        
        # 连接NATS
        if not await self.connect_nats():
            return False
            
        # 订阅数据流
        if not await self.subscribe_to_data_streams():
            return False
            
        self.running = True
        
        # 启动后台任务
        tasks = [
            asyncio.create_task(self.periodic_flush()),
            asyncio.create_task(self.stats_reporter())
        ]
        
        logger.info("✅ 优化热存储服务启动成功")
        
        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            logger.info("收到停止信号")
        finally:
            await self.stop()
    
    async def stop(self):
        """停止服务"""
        logger.info("🛑 停止优化热存储服务...")
        self.running = False
        
        # 刷新所有剩余数据
        for data_type in list(self.data_queues.keys()):
            await self.flush_batch(data_type)
        
        if self.nc:
            await self.nc.close()
        
        logger.info("✅ 优化热存储服务已停止")

async def main():
    """主函数"""
    service = OptimizedHotStorageService()
    
    # 信号处理
    def signal_handler(signum, frame):
        logger.info(f"收到信号 {signum}")
        asyncio.create_task(service.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    await service.start()

if __name__ == "__main__":
    asyncio.run(main())
