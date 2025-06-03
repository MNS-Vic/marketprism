#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MarketPrism 高频数据采集负载测试
测试系统在高频数据采集下的稳定性和性能
"""

import sys
import os
import pytest
import asyncio
import json
import time
import logging
import random
from datetime import datetime
from typing import Dict, List, Any
from concurrent.futures import ThreadPoolExecutor

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

# 负载测试标记
pytestmark = pytest.mark.load_testing

class TestHighFrequencyCollection:
    """
    高频数据采集负载测试类
    测试系统在高频数据场景下的稳定性
    """
    
    @pytest.fixture
    async def setup_load_test(self, test_config):
        """
        设置负载测试环境
        """
        # 记录开始时间
        start_time = time.time()
        
        # 设置测试参数
        test_id = f"load_test_{int(start_time)}"
        test_duration = 60  # 测试持续时间(秒)
        
        # 返回测试配置
        test_config = {
            "start_time": start_time,
            "test_id": test_id,
            "duration": test_duration,
            "max_frequency": 10000  # 最大模拟频率(条/秒)
        }
        
        # 测试开始日志
        logging.info(f"开始负载测试 {test_id}")
        logging.info(f"测试持续时间: {test_duration}秒")
        logging.info(f"最大数据频率: {test_config['max_frequency']}条/秒")
        
        yield test_config
        
        # 测试完成后记录总时间
        total_time = time.time() - start_time
        logging.info(f"负载测试 {test_id} 完成，总耗时: {total_time:.2f}秒")
    
    @pytest.mark.asyncio
    async def test_high_frequency_data_collection(self, setup_load_test, nats_client, clickhouse_client):
        """
        测试高频数据采集
        模拟生成高频交易数据，检测系统处理能力和稳定性
        """
        test_cfg = setup_load_test
        
        # 测试参数
        frequency = test_cfg["max_frequency"]  # 每秒数据量
        duration = test_cfg["duration"]        # 测试持续时间(秒)
        raw_subject = f"LOAD.RAW.{test_cfg['test_id']}"
        normalized_subject = f"LOAD.NORMALIZED.{test_cfg['test_id']}"
        
        # 创建临时测试表
        test_table = f"market_trades_load_{test_cfg['test_id'].replace('-', '_')}"
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
            # 统计计数器
            sent_count = 0
            normalized_count = 0
            stored_count = 0
            error_count = 0
            
            # 完成事件
            test_completed = asyncio.Event()
            
            # 创建数据标准化处理器
            from services.data_normalizer.internal.normalizer import DataNormalizer
            normalizer = DataNormalizer()
            
            # 标准化和存储处理函数
            async def process_and_store(msg):
                nonlocal normalized_count, stored_count, error_count
                
                try:
                    # 解析原始数据
                    raw_data = json.loads(msg.data.decode())
                    
                    # 标准化数据
                    normalized_data = normalizer.normalize_trade(raw_data)
                    normalized_count += 1
                    
                    # 发布到标准化主题
                    await nats_client.publish(
                        normalized_subject,
                        json.dumps(normalized_data).encode()
                    )
                    
                    # 存储到数据库
                    query = f"""
                    INSERT INTO {test_table}
                    (symbol, price, volume, timestamp, exchange, trade_id, side)
                    VALUES
                    """
                    
                    values = [(
                        normalized_data["symbol"],
                        float(normalized_data["price"]),
                        float(normalized_data["volume"]),
                        int(normalized_data["timestamp"]),
                        normalized_data["exchange"],
                        normalized_data["trade_id"],
                        normalized_data["side"]
                    )]
                    
                    await clickhouse_client.execute(query, values)
                    stored_count += 1
                    
                except Exception as e:
                    error_count += 1
                    logging.error(f"处理数据错误: {e}")
            
            # 订阅原始数据主题
            sub = await nats_client.subscribe(raw_subject, cb=process_and_store)
            
            # 状态监控任务
            async def monitor_status():
                last_sent = 0
                last_normalized = 0
                last_stored = 0
                start = time.time()
                
                while not test_completed.is_set():
                    await asyncio.sleep(1.0)
                    now = time.time()
                    elapsed = now - start
                    
                    # 计算每秒处理量
                    sent_rate = sent_count - last_sent
                    normalized_rate = normalized_count - last_normalized
                    stored_rate = stored_count - last_stored
                    
                    # 更新计数器
                    last_sent = sent_count
                    last_normalized = normalized_count
                    last_stored = stored_count
                    
                    # 输出状态
                    logging.info(f"状态 [{elapsed:.1f}s]: "
                                f"发送 {sent_rate}/s (总计:{sent_count}), "
                                f"标准化 {normalized_rate}/s (总计:{normalized_count}), "
                                f"存储 {stored_rate}/s (总计:{stored_count}), "
                                f"错误 {error_count}")
                    
                    # 检查是否测试完成
                    if elapsed >= duration:
                        test_completed.set()
            
            # 启动监控任务
            monitor_task = asyncio.create_task(monitor_status())
            
            # 数据生成和发送任务
            async def generate_and_send():
                nonlocal sent_count
                start_time = time.time()
                
                while not test_completed.is_set():
                    batch_size = frequency // 100  # 将频率分成较小的批次
                    batch_interval = 0.01  # 每批次间隔(秒)
                    
                    batch_start = time.time()
                    batch_data = []
                    
                    # 生成一批测试数据
                    for i in range(batch_size):
                        # 为了模拟真实场景，使用随机值
                        symbol_idx = random.randint(0, 9)
                        price_base = 40000 + random.randint(-500, 500)
                        price_fraction = random.randint(0, 99)
                        volume = random.uniform(0.1, 10.0)
                        
                        # 创建交易数据
                        trade_data = {
                            "symbol": f"BTC-USDT-{symbol_idx}",
                            "price": f"{price_base}.{price_fraction:02d}",
                            "volume": f"{volume:.6f}",
                            "timestamp": int(time.time() * 1000),
                            "exchange": ["binance", "okex", "deribit"][random.randint(0, 2)],
                            "trade_id": f"load_test_{sent_count}",
                            "side": "buy" if random.randint(0, 1) == 0 else "sell"
                        }
                        
                        # 发布到原始数据主题
                        await nats_client.publish(
                            raw_subject,
                            json.dumps(trade_data).encode()
                        )
                        
                        sent_count += 1
                        
                        # 如果测试完成，提前退出
                        if test_completed.is_set():
                            break
                    
                    # 控制发送速率
                    elapsed = time.time() - batch_start
                    if elapsed < batch_interval:
                        await asyncio.sleep(batch_interval - elapsed)
            
            # 启动数据生成任务
            sender_task = asyncio.create_task(generate_and_send())
            
            # 等待测试完成
            try:
                await asyncio.wait_for(test_completed.wait(), timeout=duration + 5)
            except asyncio.TimeoutError:
                logging.error("测试超时")
                
            # 取消任务
            sender_task.cancel()
            monitor_task.cancel()
            
            # 取消订阅
            await sub.unsubscribe()
            
            # 等待任务完成
            try:
                await asyncio.gather(sender_task, monitor_task, return_exceptions=True)
            except asyncio.CancelledError:
                pass
            
            # 统计测试结果
            total_time = time.time() - test_cfg["start_time"]
            actual_send_rate = sent_count / total_time if total_time > 0 else 0
            normalized_rate = normalized_count / total_time if total_time > 0 else 0
            stored_rate = stored_count / total_time if total_time > 0 else 0
            
            # 输出测试结果
            logging.info(f"高频数据采集负载测试完成:")
            logging.info(f"总发送数据: {sent_count} 条 ({actual_send_rate:.1f} 条/秒)")
            logging.info(f"总标准化数据: {normalized_count} 条 ({normalized_rate:.1f} 条/秒)")
            logging.info(f"总存储数据: {stored_count} 条 ({stored_rate:.1f} 条/秒)")
            logging.info(f"总错误数: {error_count} 条")
            
            # 验证系统性能和稳定性
            assert normalized_count >= 0.95 * sent_count, f"标准化率低于95%: {normalized_count}/{sent_count}"
            assert stored_count >= 0.95 * normalized_count, f"存储率低于95%: {stored_count}/{normalized_count}"
            assert error_count <= 0.01 * sent_count, f"错误率高于1%: {error_count}/{sent_count}"
            
        finally:
            # 测试完成后删除测试表
            drop_table_query = f"DROP TABLE IF EXISTS {test_table}"
            await clickhouse_client.execute(drop_table_query)
    
    @pytest.mark.asyncio
    async def test_multi_exchange_concurrent_collection(self, setup_load_test, nats_client):
        """
        测试多交易所并发数据采集
        同时模拟多个交易所的数据流，测试系统处理并发能力
        """
        test_cfg = setup_load_test
        
        # 测试参数
        exchanges = ["binance", "okex", "deribit", "huobi", "ftx"]  # 多个交易所
        symbols_per_exchange = 20  # 每个交易所的交易对数量
        frequency_per_exchange = 2000  # 每个交易所每秒数据量
        duration = test_cfg["duration"] // 2  # 缩短测试时间
        
        # 交易所主题
        exchange_subjects = {
            ex: f"LOAD.{ex.upper()}.{test_cfg['test_id']}" for ex in exchanges
        }
        
        # 接收计数器
        received_counts = {ex: 0 for ex in exchanges}
        error_counts = {ex: 0 for ex in exchanges}
        
        # 完成事件
        test_completed = asyncio.Event()
        
        # 为每个交易所创建数据处理函数
        async def create_exchange_handler(exchange):
            async def handler(msg):
                try:
                    data = json.loads(msg.data.decode())
                    received_counts[exchange] += 1
                except Exception as e:
                    error_counts[exchange] += 1
                    logging.error(f"处理{exchange}消息错误: {e}")
            
            return handler
        
        # 订阅每个交易所的主题
        subscriptions = []
        for exchange in exchanges:
            handler = await create_exchange_handler(exchange)
            sub = await nats_client.subscribe(exchange_subjects[exchange], cb=handler)
            subscriptions.append(sub)
        
        # 状态监控任务
        async def monitor_exchange_status():
            last_counts = {ex: 0 for ex in exchanges}
            start = time.time()
            
            while not test_completed.is_set():
                await asyncio.sleep(1.0)
                now = time.time()
                elapsed = now - start
                
                # 计算每个交易所的接收率
                rates = {}
                for ex in exchanges:
                    rates[ex] = received_counts[ex] - last_counts[ex]
                    last_counts[ex] = received_counts[ex]
                
                # 输出状态
                status = ", ".join([f"{ex}: {rates[ex]}/s" for ex in exchanges])
                total_rate = sum(rates.values())
                logging.info(f"多交易所状态 [{elapsed:.1f}s]: 总计 {total_rate}/s ({status})")
                
                # 检查是否测试完成
                if elapsed >= duration:
                    test_completed.set()
        
        # 启动监控任务
        monitor_task = asyncio.create_task(monitor_exchange_status())
        
        # 为每个交易所创建数据生成和发送任务
        async def generate_for_exchange(exchange, symbols, frequency):
            sent_count = 0
            start_time = time.time()
            
            # 交易对列表
            symbols = [f"{exchange}-{i}" for i in range(symbols)]
            
            while not test_completed.is_set():
                batch_size = frequency // 20  # 将频率分成较小的批次
                batch_interval = 0.05  # 每批次间隔(秒)
                
                batch_start = time.time()
                
                # 生成一批测试数据
                for i in range(batch_size):
                    # 随机选择交易对
                    symbol = symbols[random.randint(0, len(symbols) - 1)]
                    
                    # 创建交易数据
                    trade_data = {
                        "symbol": symbol,
                        "price": f"{random.uniform(100, 50000):.2f}",
                        "volume": f"{random.uniform(0.001, 100):.6f}",
                        "timestamp": int(time.time() * 1000),
                        "exchange": exchange,
                        "trade_id": f"{exchange}_test_{sent_count}",
                        "side": "buy" if random.randint(0, 1) == 0 else "sell"
                    }
                    
                    # 发布到交易所主题
                    await nats_client.publish(
                        exchange_subjects[exchange],
                        json.dumps(trade_data).encode()
                    )
                    
                    sent_count += 1
                    
                    # 如果测试完成，提前退出
                    if test_completed.is_set():
                        break
                
                # 控制发送速率
                elapsed = time.time() - batch_start
                if elapsed < batch_interval:
                    await asyncio.sleep(batch_interval - elapsed)
        
        # 启动交易所数据生成任务
        exchange_tasks = []
        for exchange in exchanges:
            task = asyncio.create_task(
                generate_for_exchange(
                    exchange, 
                    symbols_per_exchange, 
                    frequency_per_exchange
                )
            )
            exchange_tasks.append(task)
        
        # 等待测试完成
        try:
            await asyncio.wait_for(test_completed.wait(), timeout=duration + 5)
        except asyncio.TimeoutError:
            logging.error("多交易所测试超时")
        
        # 取消任务
        monitor_task.cancel()
        for task in exchange_tasks:
            task.cancel()
        
        # 取消订阅
        for sub in subscriptions:
            await sub.unsubscribe()
        
        # 等待任务完成
        try:
            await asyncio.gather(monitor_task, *exchange_tasks, return_exceptions=True)
        except asyncio.CancelledError:
            pass
        
        # 统计测试结果
        total_time = time.time() - test_cfg["start_time"]
        total_received = sum(received_counts.values())
        total_errors = sum(error_counts.values())
        actual_rate = total_received / total_time if total_time > 0 else 0
        
        # 输出测试结果
        logging.info(f"多交易所并发数据采集测试完成:")
        for ex in exchanges:
            ex_rate = received_counts[ex] / total_time if total_time > 0 else 0
            logging.info(f"  {ex}: 接收 {received_counts[ex]} 条 ({ex_rate:.1f} 条/秒), 错误 {error_counts[ex]} 条")
        
        logging.info(f"总接收数据: {total_received} 条 ({actual_rate:.1f} 条/秒)")
        logging.info(f"总错误数: {total_errors} 条")
        
        # 验证系统并发处理能力
        target_rate = sum([frequency_per_exchange for _ in exchanges]) * 0.8
        assert actual_rate >= target_rate, f"实际接收率 {actual_rate:.1f} 低于目标 {target_rate:.1f} 条/秒"
        assert total_errors <= 0.01 * total_received, f"错误率高于1%: {total_errors}/{total_received}" 