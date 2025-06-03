#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MarketPrism 数据吞吐量性能测试
测试数据标准化和存储组件在高负载下的性能表现
"""

import sys
import os
import pytest
import pytest_asyncio
import asyncio
import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Any

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

# 性能测试标记
pytestmark = pytest.mark.performance

class TestDataThroughput:
    """
    数据吞吐量性能测试类
    测试系统在高负载下的数据处理能力
    """
    
    @pytest_asyncio.fixture
    async def setup_performance_test(self, test_config):
        """
        设置性能测试环境
        """
        # 记录开始时间
        start_time = time.time()
        
        # 返回测试配置
        yield {
            "start_time": start_time,
            "test_id": f"perf_test_{int(start_time)}"
        }
        
        # 测试完成后清理
        logging.info(f"性能测试完成，总耗时: {time.time() - start_time:.2f}秒")
    
    @pytest.mark.asyncio
    async def test_normalizer_throughput(self, setup_performance_test, nats_client):
        """
        测试数据标准化服务的吞吐量
        生成大量模拟交易数据并计算标准化处理能力
        """
        test_cfg = setup_performance_test
        
        # 测试参数
        batch_size = 1000  # 每批数据量
        batch_count = 10   # 批次数量
        test_subject = f"PERF.TEST.NORMALIZER.{test_cfg['test_id']}"
        
        # 计数器和计时器
        processed_count = 0
        total_time = 0
        
        # 创建数据标准化处理器
        from services.data_normalizer.internal.normalizer import DataNormalizer
        normalizer = DataNormalizer()
        
        # 批量生成测试数据
        for batch in range(batch_count):
            batch_data = []
            
            # 生成一批测试数据
            for i in range(batch_size):
                trade_data = {
                    "symbol": f"BTC-USDT-{i % 10}",  # 模拟10个不同交易对
                    "price": f"{40000 + (i % 1000)}.{i % 100}",  # 生成不同价格
                    "volume": f"{1 + (i % 10)}.{i % 1000}",  # 生成不同数量
                    "timestamp": int(datetime.now().timestamp() * 1000) + i,
                    "exchange": ["binance", "okex", "deribit"][i % 3],  # 轮换交易所
                    "trade_id": f"perf_test_{batch}_{i}",
                    "side": "buy" if i % 2 == 0 else "sell"  # 交替买卖方向
                }
                batch_data.append(trade_data)
            
            # 记录开始时间
            batch_start = time.time()
            
            # 执行标准化处理
            normalized_data = []
            for trade in batch_data:
                try:
                    normalized = normalizer.normalize_trade(trade)
                    normalized_data.append(normalized)
                    processed_count += 1
                except Exception as e:
                    logging.error(f"标准化处理错误: {e}")
            
            # 计算批次耗时
            batch_time = time.time() - batch_start
            total_time += batch_time
            
            # 输出批次信息
            logging.info(f"批次 {batch+1}/{batch_count} 完成: "
                         f"处理 {len(normalized_data)}/{batch_size} 条数据, "
                         f"耗时 {batch_time:.3f}秒, "
                         f"吞吐量 {len(normalized_data)/batch_time:.1f} 条/秒")
        
        # 计算总吞吐量
        overall_throughput = processed_count / total_time if total_time > 0 else 0
        
        # 输出总体性能数据
        logging.info(f"数据标准化性能测试完成:")
        logging.info(f"总数据量: {processed_count} 条")
        logging.info(f"总耗时: {total_time:.3f} 秒")
        logging.info(f"总吞吐量: {overall_throughput:.1f} 条/秒")
        
        # 确保吞吐量达到基本要求 (根据实际需求调整)
        min_throughput = 1000  # 最低期望吞吐量
        assert overall_throughput >= min_throughput, f"吞吐量 {overall_throughput:.1f} 低于期望的 {min_throughput} 条/秒"
    
    @pytest.mark.asyncio
    async def test_clickhouse_write_performance(self, setup_performance_test, clickhouse_client):
        """
        测试ClickHouse写入性能
        测量大批量数据写入ClickHouse的速度
        """
        test_cfg = setup_performance_test
        
        # 测试参数
        batch_size = 5000  # 每批数据量
        batch_count = 5    # 批次数量
        
        # 创建临时测试表
        test_table = f"market_trades_perf_{test_cfg['test_id'].replace('-', '_')}"
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
            # 计数器和计时器
            inserted_count = 0
            total_time = 0
            
            # 批量插入测试
            for batch in range(batch_count):
                batch_data = []
                
                # 生成一批测试数据
                current_time = int(datetime.now().timestamp())
                for i in range(batch_size):
                    trade_data = (
                        f"BTC-USDT-{i % 10}",  # symbol
                        float(40000 + (i % 1000)) + float(i % 100) / 100,  # price
                        float(1 + (i % 10)) + float(i % 1000) / 1000,  # volume
                        current_time + i,  # timestamp
                        ["binance", "okex", "deribit"][i % 3],  # exchange
                        f"perf_test_{batch}_{i}",  # trade_id
                        "buy" if i % 2 == 0 else "sell"  # side
                    )
                    batch_data.append(trade_data)
                
                # 构建插入查询
                insert_query = f"""
                INSERT INTO {test_table}
                (symbol, price, volume, timestamp, exchange, trade_id, side)
                VALUES
                """
                
                # 记录开始时间
                batch_start = time.time()
                
                # 执行批量插入
                await clickhouse_client.execute(insert_query, batch_data)
                inserted_count += len(batch_data)
                
                # 计算批次耗时
                batch_time = time.time() - batch_start
                total_time += batch_time
                
                # 输出批次信息
                logging.info(f"批次 {batch+1}/{batch_count} 完成: "
                             f"插入 {len(batch_data)} 条数据, "
                             f"耗时 {batch_time:.3f}秒, "
                             f"写入速度 {len(batch_data)/batch_time:.1f} 条/秒")
            
            # 计算总吞吐量
            overall_throughput = inserted_count / total_time if total_time > 0 else 0
            
            # 输出总体性能数据
            logging.info(f"ClickHouse写入性能测试完成:")
            logging.info(f"总数据量: {inserted_count} 条")
            logging.info(f"总耗时: {total_time:.3f} 秒")
            logging.info(f"写入速度: {overall_throughput:.1f} 条/秒")
            
            # 确保写入速度达到基本要求 (根据实际需求调整)
            min_throughput = 5000  # 最低期望写入速度
            assert overall_throughput >= min_throughput, f"写入速度 {overall_throughput:.1f} 低于期望的 {min_throughput} 条/秒"
            
        finally:
            # 测试完成后删除测试表
            drop_table_query = f"DROP TABLE IF EXISTS {test_table}"
            await clickhouse_client.execute(drop_table_query)
    
    @pytest.mark.asyncio
    async def test_nats_throughput(self, setup_performance_test, nats_client):
        """
        测试NATS消息传递性能
        测量NATS在高负载下的消息传递速度
        """
        test_cfg = setup_performance_test
        
        # 测试参数
        batch_size = 10000  # 每批消息数
        test_subject = f"PERF.TEST.NATS.{test_cfg['test_id']}"
        
        # 接收消息计数器
        received_count = 0
        done_event = asyncio.Event()
        
        # 消息处理回调
        async def message_handler(msg):
            nonlocal received_count
            received_count += 1
            
            # 当接收到所有消息时，触发完成事件
            if received_count >= batch_size:
                done_event.set()
        
        # 订阅测试主题
        sub = await nats_client.subscribe(test_subject, cb=message_handler)
        
        # 生成测试消息
        test_messages = []
        for i in range(batch_size):
            message = {
                "id": i,
                "timestamp": int(time.time() * 1000),
                "data": f"performance test message {i}",
                "size": i % 100
            }
            test_messages.append(json.dumps(message).encode())
        
        # 记录开始时间
        start_time = time.time()
        
        # 发布测试消息
        for msg in test_messages:
            await nats_client.publish(test_subject, msg)
        
        # 等待所有消息被接收
        try:
            await asyncio.wait_for(done_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            logging.error(f"等待消息接收超时，只收到 {received_count}/{batch_size} 条消息")
        
        # 取消订阅
        await sub.unsubscribe()
        
        # 计算总耗时和吞吐量
        total_time = time.time() - start_time
        throughput = batch_size / total_time if total_time > 0 else 0
        
        # 输出性能数据
        logging.info(f"NATS消息吞吐量测试完成:")
        logging.info(f"发送消息: {batch_size} 条")
        logging.info(f"接收消息: {received_count} 条")
        logging.info(f"总耗时: {total_time:.3f} 秒")
        logging.info(f"消息吞吐量: {throughput:.1f} 条/秒")
        
        # 验证接收到的消息数量
        assert received_count >= 0.95 * batch_size, f"只收到 {received_count}/{batch_size} 条消息"
        
        # 确保吞吐量达到基本要求
        min_throughput = 5000  # 最低期望吞吐量
        assert throughput >= min_throughput, f"吞吐量 {throughput:.1f} 低于期望的 {min_throughput} 条/秒" 