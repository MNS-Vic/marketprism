#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MarketPrism 大批量数据处理负载测试
测试系统在大批量数据处理场景下的稳定性和性能
"""

import sys
import os
import pytest
import asyncio
import json
import time
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any
import uuid

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

# 负载测试标记
pytestmark = pytest.mark.load_testing

class TestLargeDataProcessing:
    """
    大批量数据处理负载测试类
    测试系统处理大批量市场数据的能力
    """
    
    @pytest.fixture
    async def setup_batch_test(self, test_config):
        """
        设置批量数据测试环境
        """
        # 记录开始时间
        start_time = time.time()
        
        # 设置测试参数
        test_id = f"batch_test_{int(start_time)}"
        
        # 返回测试配置
        test_config = {
            "start_time": start_time,
            "test_id": test_id,
            "batch_sizes": [1000, 10000, 50000, 100000],  # 测试的批量大小
            "symbols": ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT"],
            "exchanges": ["binance", "okex", "deribit"]
        }
        
        # 测试开始日志
        logging.info(f"开始大批量数据处理测试 {test_id}")
        logging.info(f"测试批次大小: {test_config['batch_sizes']}")
        
        yield test_config
        
        # 测试完成后记录总时间
        total_time = time.time() - start_time
        logging.info(f"大批量数据处理测试 {test_id} 完成，总耗时: {total_time:.2f}秒")
    
    @pytest.mark.asyncio
    async def test_large_batch_normalization(self, setup_batch_test):
        """
        测试大批量数据标准化
        测量数据标准化服务处理大批量数据的性能和稳定性
        """
        test_cfg = setup_batch_test
        
        # 创建数据标准化处理器
        from services.data_normalizer.internal.normalizer import DataNormalizer
        normalizer = DataNormalizer()
        
        # 为每个批次大小运行测试
        for batch_size in test_cfg["batch_sizes"]:
            logging.info(f"开始测试批次大小: {batch_size}")
            
            # 生成测试数据
            raw_data = self._generate_batch_data(
                batch_size, 
                test_cfg["symbols"], 
                test_cfg["exchanges"]
            )
            
            # 执行批量标准化
            start_time = time.time()
            normalized_count = 0
            error_count = 0
            
            for data in raw_data:
                try:
                    normalized = normalizer.normalize_trade(data)
                    normalized_count += 1
                except Exception as e:
                    error_count += 1
                    if error_count <= 5:  # 只记录前几个错误
                        logging.error(f"标准化错误: {e}")
            
            # 计算处理时间和速度
            process_time = time.time() - start_time
            process_rate = batch_size / process_time if process_time > 0 else 0
            
            # 输出测试结果
            logging.info(f"批次大小 {batch_size} 处理完成:")
            logging.info(f"  处理时间: {process_time:.3f} 秒")
            logging.info(f"  处理速度: {process_rate:.1f} 条/秒")
            logging.info(f"  成功标准化: {normalized_count}/{batch_size}")
            logging.info(f"  错误数: {error_count}")
            
            # 验证处理结果
            assert normalized_count >= 0.99 * batch_size, f"标准化成功率低于99%: {normalized_count}/{batch_size}"
            assert error_count <= 0.01 * batch_size, f"错误率高于1%: {error_count}/{batch_size}"
            
            # 根据批次大小验证最低处理速度
            min_rate = 5000  # 最低处理速度(条/秒)
            if batch_size >= 50000:
                min_rate = 10000  # 大批量下应当有更高吞吐量(优化效果)
            
            assert process_rate >= min_rate, f"处理速度 {process_rate:.1f} 条/秒 低于目标 {min_rate} 条/秒"
    
    @pytest.mark.asyncio
    async def test_large_batch_db_operation(self, setup_batch_test, clickhouse_client):
        """
        测试大批量数据库操作
        测量系统在大批量写入和查询场景下的性能
        """
        test_cfg = setup_batch_test
        
        # 创建临时测试表
        test_table = f"market_trades_batch_{test_cfg['test_id'].replace('-', '_')}"
        create_table_query = f"""
        CREATE TABLE IF NOT EXISTS {test_table} (
            symbol String,
            price Float64,
            volume Float64,
            timestamp UInt64,
            exchange String,
            trade_id String,
            side String,
            received_at DateTime DEFAULT now()
        ) ENGINE = MergeTree()
        ORDER BY (symbol, exchange, timestamp)
        """
        
        await clickhouse_client.execute(create_table_query)
        
        try:
            # 测试1: 大批量数据写入
            for batch_size in test_cfg["batch_sizes"]:
                if batch_size > 50000:  # 限制最大批量，避免测试时间过长
                    continue
                    
                logging.info(f"开始测试批次大小为 {batch_size} 的大批量写入")
                
                # 生成测试数据
                batch_data = []
                current_time = int(datetime.now().timestamp())
                
                for i in range(batch_size):
                    symbol_idx = i % len(test_cfg["symbols"])
                    exchange_idx = i % len(test_cfg["exchanges"])
                    
                    trade_data = (
                        test_cfg["symbols"][symbol_idx],  # symbol
                        40000 + random.uniform(-1000, 1000),  # price
                        random.uniform(0.1, 10.0),  # volume
                        current_time + i,  # timestamp
                        test_cfg["exchanges"][exchange_idx],  # exchange
                        f"batch_test_{batch_size}_{i}",  # trade_id
                        "buy" if i % 2 == 0 else "sell"  # side
                    )
                    batch_data.append(trade_data)
                
                # 构建批量插入查询
                insert_query = f"""
                INSERT INTO {test_table}
                (symbol, price, volume, timestamp, exchange, trade_id, side)
                VALUES
                """
                
                # 执行批量插入并计时
                start_time = time.time()
                await clickhouse_client.execute(insert_query, batch_data)
                insert_time = time.time() - start_time
                
                # 计算写入速度
                insert_rate = batch_size / insert_time if insert_time > 0 else 0
                
                # 输出写入性能结果
                logging.info(f"批次大小 {batch_size} 写入完成:")
                logging.info(f"  写入时间: {insert_time:.3f} 秒")
                logging.info(f"  写入速度: {insert_rate:.1f} 条/秒")
                
                # 验证写入性能
                min_insert_rate = 8000  # 最低写入速度(条/秒)
                assert insert_rate >= min_insert_rate, f"写入速度 {insert_rate:.1f} 条/秒 低于目标 {min_insert_rate} 条/秒"
                
                # 验证写入数据正确性
                count_query = f"SELECT count(*) FROM {test_table} WHERE trade_id LIKE 'batch_test_{batch_size}_%'"
                results = await clickhouse_client.execute(count_query)
                count = results[0][0]
                
                assert count == batch_size, f"写入记录数 {count} 不匹配预期的 {batch_size}"
            
            # 测试2: 大规模数据查询性能
            logging.info("开始测试大规模数据查询性能")
            
            # 执行不同类型的查询
            queries = [
                ("单个交易对查询", f"SELECT count(*) FROM {test_table} WHERE symbol = '{test_cfg['symbols'][0]}'"),
                ("时间范围查询", f"SELECT count(*) FROM {test_table} WHERE timestamp > {int(datetime.now().timestamp()) - 86400}"),
                ("分组统计查询", f"SELECT symbol, exchange, avg(price), sum(volume) FROM {test_table} GROUP BY symbol, exchange"),
                ("多条件复杂查询", f"""
                    SELECT 
                        symbol, 
                        exchange, 
                        min(price) as min_price, 
                        max(price) as max_price, 
                        avg(price) as avg_price,
                        sum(volume) as total_volume,
                        count() as trade_count
                    FROM {test_table}
                    WHERE timestamp > {int(datetime.now().timestamp()) - 86400}
                    GROUP BY symbol, exchange
                    HAVING trade_count > 10
                    ORDER BY total_volume DESC
                """)
            ]
            
            # 执行查询并测量性能
            for query_name, query_sql in queries:
                # 执行查询并计时
                start_time = time.time()
                results = await clickhouse_client.execute(query_sql)
                query_time = time.time() - start_time
                
                # 输出查询性能结果
                logging.info(f"{query_name} 性能:")
                logging.info(f"  查询时间: {query_time:.3f} 秒")
                logging.info(f"  返回记录数: {len(results) if isinstance(results, list) else 1}")
                
                # 验证查询完成
                assert query_time > 0, f"{query_name} 执行失败"
        
        finally:
            # 测试完成后删除测试表
            drop_table_query = f"DROP TABLE IF EXISTS {test_table}"
            await clickhouse_client.execute(drop_table_query)
    
    @pytest.mark.asyncio
    async def test_historical_data_loading(self, setup_batch_test, nats_client, clickhouse_client):
        """
        测试历史数据加载
        模拟系统加载大量历史数据的场景
        """
        test_cfg = setup_batch_test
        
        # 设置测试参数
        days_of_history = 30
        records_per_day = 100000
        batch_size = 10000
        
        # 创建临时测试表
        test_table = f"market_trades_history_{test_cfg['test_id'].replace('-', '_')}"
        create_table_query = f"""
        CREATE TABLE IF NOT EXISTS {test_table} (
            symbol String,
            price Float64,
            volume Float64,
            timestamp UInt64,
            exchange String,
            trade_id String,
            side String,
            day_id Date DEFAULT today(),
            received_at DateTime DEFAULT now()
        ) ENGINE = MergeTree()
        PARTITION BY day_id
        ORDER BY (symbol, exchange, timestamp)
        """
        
        await clickhouse_client.execute(create_table_query)
        
        try:
            # 记录开始时间
            total_start = time.time()
            
            # 为每天生成并加载历史数据
            total_records = 0
            total_load_time = 0
            
            for day in range(days_of_history):
                day_time = datetime.now() - timedelta(days=day)
                day_start = int(day_time.replace(hour=0, minute=0, second=0).timestamp())
                
                logging.info(f"加载 {day_time.date()} 的历史数据")
                
                day_start_time = time.time()
                day_records = 0
                
                # 按批次加载数据
                for batch in range(0, records_per_day, batch_size):
                    # 调整最后一批的大小
                    current_batch_size = min(batch_size, records_per_day - batch)
                    if current_batch_size <= 0:
                        break
                    
                    # 生成批次数据
                    batch_data = []
                    
                    for i in range(current_batch_size):
                        # 随机选择交易对和交易所
                        symbol = test_cfg["symbols"][random.randint(0, len(test_cfg["symbols"]) - 1)]
                        exchange = test_cfg["exchanges"][random.randint(0, len(test_cfg["exchanges"]) - 1)]
                        
                        # 生成该天内的随机时间戳
                        timestamp = day_start + random.randint(0, 86399)
                        
                        # 生成交易数据
                        trade_data = (
                            symbol,  # symbol
                            40000 + random.uniform(-1000, 1000),  # price
                            random.uniform(0.1, 10.0),  # volume
                            timestamp,  # timestamp
                            exchange,  # exchange
                            f"history_{day}_{batch}_{i}",  # trade_id
                            "buy" if random.randint(0, 1) == 0 else "sell",  # side
                            day_time.date()  # day_id
                        )
                        batch_data.append(trade_data)
                    
                    # 构建批量插入查询
                    insert_query = f"""
                    INSERT INTO {test_table}
                    (symbol, price, volume, timestamp, exchange, trade_id, side, day_id)
                    VALUES
                    """
                    
                    # 执行批量插入
                    batch_start = time.time()
                    await clickhouse_client.execute(insert_query, batch_data)
                    batch_time = time.time() - batch_start
                    
                    # 更新计数器
                    day_records += len(batch_data)
                    total_records += len(batch_data)
                    total_load_time += batch_time
                    
                    # 输出批次信息
                    logging.info(f"  批次 {batch//batch_size + 1} 加载完成: "
                                f"{len(batch_data)} 条记录, "
                                f"耗时 {batch_time:.3f}秒, "
                                f"速度 {len(batch_data)/batch_time:.1f} 条/秒")
                
                # 计算当天加载时间和速度
                day_time = time.time() - day_start_time
                day_rate = day_records / day_time if day_time > 0 else 0
                
                logging.info(f"{day_time.date()} 的数据加载完成:")
                logging.info(f"  记录数: {day_records}")
                logging.info(f"  加载时间: {day_time:.3f}秒")
                logging.info(f"  加载速度: {day_rate:.1f} 条/秒")
            
            # 计算总加载时间和速度
            total_time = time.time() - total_start
            total_rate = total_records / total_load_time if total_load_time > 0 else 0
            
            # 输出总体性能结果
            logging.info(f"历史数据加载测试完成:")
            logging.info(f"总记录数: {total_records}")
            logging.info(f"总加载时间: {total_time:.3f}秒")
            logging.info(f"实际数据写入时间: {total_load_time:.3f}秒")
            logging.info(f"平均加载速度: {total_rate:.1f} 条/秒")
            
            # 验证加载性能
            min_total_rate = 8000  # 最低平均加载速度(条/秒)
            assert total_rate >= min_total_rate, f"平均加载速度 {total_rate:.1f} 条/秒 低于目标 {min_total_rate} 条/秒"
            
            # 验证数据量统计正确
            count_query = f"SELECT count(*) FROM {test_table}"
            results = await clickhouse_client.execute(count_query)
            count = results[0][0]
            
            assert count == total_records, f"数据库中记录数 {count} 不匹配预期的 {total_records}"
            
            # 测试历史数据查询性能
            logging.info("测试历史数据查询性能")
            
            # 按天查询性能
            day_query = f"""
            SELECT day_id, count(*) as count
            FROM {test_table}
            GROUP BY day_id
            ORDER BY day_id
            """
            
            start_time = time.time()
            day_results = await clickhouse_client.execute(day_query)
            day_query_time = time.time() - start_time
            
            logging.info(f"按天查询性能:")
            logging.info(f"  查询时间: {day_query_time:.3f}秒")
            logging.info(f"  天数: {len(day_results)}")
            
            # 时间范围聚合查询性能
            range_query = f"""
            SELECT 
                symbol,
                exchange,
                toStartOfDay(fromUnixTimestamp(timestamp)) as day,
                avg(price) as avg_price,
                sum(volume) as total_volume,
                count() as trade_count
            FROM {test_table}
            GROUP BY symbol, exchange, day
            ORDER BY day DESC, total_volume DESC
            """
            
            start_time = time.time()
            range_results = await clickhouse_client.execute(range_query)
            range_query_time = time.time() - start_time
            
            logging.info(f"时间范围聚合查询性能:")
            logging.info(f"  查询时间: {range_query_time:.3f}秒")
            logging.info(f"  结果集大小: {len(range_results)}")
            
        finally:
            # 测试完成后删除测试表
            drop_table_query = f"DROP TABLE IF EXISTS {test_table}"
            await clickhouse_client.execute(drop_table_query)
    
    def _generate_batch_data(self, size, symbols, exchanges):
        """
        生成批量测试数据
        """
        data = []
        current_time = int(datetime.now().timestamp() * 1000)
        
        for i in range(size):
            symbol_idx = i % len(symbols)
            exchange_idx = i % len(exchanges)
            
            trade_data = {
                "symbol": symbols[symbol_idx],
                "price": f"{40000 + random.uniform(-1000, 1000):.2f}",
                "volume": f"{random.uniform(0.1, 10.0):.6f}",
                "timestamp": current_time + i,
                "exchange": exchanges[exchange_idx],
                "trade_id": f"batch_{i}_{uuid.uuid4().hex[:8]}",
                "side": "buy" if i % 2 == 0 else "sell"
            }
            data.append(trade_data)
        
        return data 