#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MarketPrism API响应时间性能测试
测试API服务在不同负载下的响应速度
"""

import sys
import os
import pytest
import asyncio
import json
import time
import logging
import random
import statistics
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any
from concurrent.futures import ThreadPoolExecutor

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

# 性能测试标记
pytestmark = pytest.mark.performance

class TestApiResponseTime:
    """
    API响应时间性能测试类
    测试API服务在不同负载下的性能表现
    """
    
    @pytest.fixture
    async def setup_api_test(self, test_config):
        """
        设置API测试环境
        """
        # 记录开始时间
        start_time = time.time()
        
        # 返回测试配置
        yield {
            "start_time": start_time,
            "test_id": f"api_perf_{int(start_time)}"
        }
        
        # 测试完成后清理
        logging.info(f"API性能测试完成，总耗时: {time.time() - start_time:.2f}秒")
    
    @pytest.mark.asyncio
    async def test_trades_query_response_time(self, setup_api_test, clickhouse_client):
        """
        测试交易数据查询API响应时间
        测量在不同查询条件和负载下的响应时间
        """
        test_cfg = setup_api_test
        
        # 测试参数
        query_count = 100      # 查询次数
        concurrent_queries = 10  # 并发查询数
        
        # 测试查询
        test_symbols = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT"]
        test_exchanges = ["binance", "okex", "deribit"]
        
        # 响应时间记录
        response_times = []
        
        # 模拟API查询函数
        async def query_trades(symbol, exchange, start_time, end_time, limit=100):
            # 记录开始时间
            query_start = time.time()
            
            # 构建查询
            query = """
                SELECT 
                    symbol, price, volume, timestamp, exchange, trade_id, side
                FROM market_trades
                WHERE symbol = %(symbol)s
                  AND exchange = %(exchange)s
                  AND timestamp BETWEEN %(start_time)s AND %(end_time)s
                ORDER BY timestamp DESC
                LIMIT %(limit)s
            """
            
            params = {
                "symbol": symbol,
                "exchange": exchange,
                "start_time": int(start_time.timestamp()),
                "end_time": int(end_time.timestamp()),
                "limit": limit
            }
            
            # 执行查询
            results = await clickhouse_client.execute(query, params)
            
            # 计算响应时间
            response_time = time.time() - query_start
            
            return results, response_time
        
        # 生成随机查询参数
        async def generate_random_query():
            symbol = random.choice(test_symbols)
            exchange = random.choice(test_exchanges)
            
            # 随机时间范围(过去30天内)
            end_time = datetime.now()
            start_time = end_time - timedelta(days=random.randint(1, 30))
            
            # 随机限制数量
            limit = random.choice([10, 50, 100, 500, 1000])
            
            return symbol, exchange, start_time, end_time, limit
        
        # 执行单次查询测试
        async def run_single_query():
            # 生成随机查询参数
            symbol, exchange, start_time, end_time, limit = await generate_random_query()
            
            # 执行查询
            _, response_time = await query_trades(symbol, exchange, start_time, end_time, limit)
            
            # 记录响应时间
            response_times.append(response_time)
            
            return response_time
        
        # 执行并发查询测试
        async def run_concurrent_queries(batch_size):
            tasks = []
            for _ in range(batch_size):
                tasks.append(run_single_query())
            
            # 等待所有查询完成
            batch_start = time.time()
            await asyncio.gather(*tasks)
            batch_time = time.time() - batch_start
            
            return batch_time
        
        # 执行所有查询测试
        total_start = time.time()
        batch_times = []
        
        for i in range(0, query_count, concurrent_queries):
            # 调整最后一批的大小
            batch_size = min(concurrent_queries, query_count - i)
            if batch_size <= 0:
                break
                
            # 执行一批并发查询
            batch_time = await run_concurrent_queries(batch_size)
            batch_times.append(batch_time)
            
            # 输出批次信息
            logging.info(f"批次 {i//concurrent_queries + 1} 完成: "
                        f"{batch_size} 个并发查询, 总耗时 {batch_time:.3f}秒")
            
            # 短暂暂停，避免过度负载
            await asyncio.sleep(0.5)
        
        # 统计结果
        total_time = time.time() - total_start
        avg_response = statistics.mean(response_times) if response_times else 0
        median_response = statistics.median(response_times) if response_times else 0
        min_response = min(response_times) if response_times else 0
        max_response = max(response_times) if response_times else 0
        p95_response = sorted(response_times)[int(len(response_times) * 0.95)] if len(response_times) >= 20 else max_response
        
        # 输出性能结果
        logging.info(f"交易数据查询API性能测试结果:")
        logging.info(f"总查询次数: {len(response_times)}")
        logging.info(f"总测试时间: {total_time:.3f} 秒")
        logging.info(f"平均响应时间: {avg_response*1000:.2f} 毫秒")
        logging.info(f"中位响应时间: {median_response*1000:.2f} 毫秒")
        logging.info(f"最小响应时间: {min_response*1000:.2f} 毫秒")
        logging.info(f"最大响应时间: {max_response*1000:.2f} 毫秒")
        logging.info(f"95%响应时间: {p95_response*1000:.2f} 毫秒")
        
        # 验证性能达标
        target_avg_response = 0.2  # 200毫秒
        target_p95_response = 0.5  # 500毫秒
        
        assert avg_response <= target_avg_response, f"平均响应时间 {avg_response*1000:.2f}ms 超过目标 {target_avg_response*1000:.2f}ms"
        assert p95_response <= target_p95_response, f"95%响应时间 {p95_response*1000:.2f}ms 超过目标 {target_p95_response*1000:.2f}ms"
    
    @pytest.mark.asyncio
    async def test_orderbook_query_response_time(self, setup_api_test, clickhouse_client):
        """
        测试订单簿查询API响应时间
        测量订单簿数据查询的响应速度
        """
        test_cfg = setup_api_test
        
        # 测试参数
        query_count = 50       # 查询次数
        concurrent_queries = 5  # 并发查询数
        
        # 测试查询
        test_symbols = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT"]
        test_exchanges = ["binance", "okex", "deribit"]
        
        # 响应时间记录
        response_times = []
        
        # 模拟订单簿查询函数
        async def query_orderbook(symbol, exchange):
            # 记录开始时间
            query_start = time.time()
            
            # 构建查询 - 获取最新订单簿
            query = """
                SELECT 
                    symbol, exchange, timestamp, bids, asks
                FROM orderbook_snapshots
                WHERE symbol = %(symbol)s
                  AND exchange = %(exchange)s
                ORDER BY timestamp DESC
                LIMIT 1
            """
            
            params = {
                "symbol": symbol,
                "exchange": exchange
            }
            
            # 执行查询
            results = await clickhouse_client.execute(query, params)
            
            # 计算响应时间
            response_time = time.time() - query_start
            
            return results, response_time
        
        # 执行单次查询测试
        async def run_single_query():
            # 生成随机查询参数
            symbol = random.choice(test_symbols)
            exchange = random.choice(test_exchanges)
            
            # 执行查询
            _, response_time = await query_orderbook(symbol, exchange)
            
            # 记录响应时间
            response_times.append(response_time)
            
            return response_time
        
        # 执行并发查询测试
        async def run_concurrent_queries(batch_size):
            tasks = []
            for _ in range(batch_size):
                tasks.append(run_single_query())
            
            # 等待所有查询完成
            batch_start = time.time()
            await asyncio.gather(*tasks)
            batch_time = time.time() - batch_start
            
            return batch_time
        
        # 执行所有查询测试
        total_start = time.time()
        
        for i in range(0, query_count, concurrent_queries):
            # 调整最后一批的大小
            batch_size = min(concurrent_queries, query_count - i)
            if batch_size <= 0:
                break
                
            # 执行一批并发查询
            batch_time = await run_concurrent_queries(batch_size)
            
            # 输出批次信息
            logging.info(f"订单簿查询批次 {i//concurrent_queries + 1} 完成: "
                        f"{batch_size} 个并发查询, 总耗时 {batch_time:.3f}秒")
            
            # 短暂暂停，避免过度负载
            await asyncio.sleep(0.5)
        
        # 统计结果
        total_time = time.time() - total_start
        avg_response = statistics.mean(response_times) if response_times else 0
        median_response = statistics.median(response_times) if response_times else 0
        min_response = min(response_times) if response_times else 0
        max_response = max(response_times) if response_times else 0
        p95_response = sorted(response_times)[int(len(response_times) * 0.95)] if len(response_times) >= 20 else max_response
        
        # 输出性能结果
        logging.info(f"订单簿查询API性能测试结果:")
        logging.info(f"总查询次数: {len(response_times)}")
        logging.info(f"总测试时间: {total_time:.3f} 秒")
        logging.info(f"平均响应时间: {avg_response*1000:.2f} 毫秒")
        logging.info(f"中位响应时间: {median_response*1000:.2f} 毫秒")
        logging.info(f"最小响应时间: {min_response*1000:.2f} 毫秒")
        logging.info(f"最大响应时间: {max_response*1000:.2f} 毫秒")
        logging.info(f"95%响应时间: {p95_response*1000:.2f} 毫秒")
        
        # 验证性能达标
        target_avg_response = 0.1  # 100毫秒
        target_p95_response = 0.3  # 300毫秒
        
        assert avg_response <= target_avg_response, f"平均响应时间 {avg_response*1000:.2f}ms 超过目标 {target_avg_response*1000:.2f}ms"
        assert p95_response <= target_p95_response, f"95%响应时间 {p95_response*1000:.2f}ms 超过目标 {target_p95_response*1000:.2f}ms"
    
    @pytest.mark.asyncio
    async def test_market_summary_response_time(self, setup_api_test, clickhouse_client):
        """
        测试市场概况API响应时间
        测量市场概况汇总查询的响应速度
        """
        test_cfg = setup_api_test
        
        # 测试参数
        query_count = 30    # 查询次数
        
        # 响应时间记录
        response_times = []
        
        # 模拟市场概况查询函数
        async def query_market_summary(symbol=None, exchange=None):
            # 记录开始时间
            query_start = time.time()
            
            # 构建基本查询 - 获取市场概况
            base_query = """
                WITH latest_trades AS (
                    SELECT 
                        symbol,
                        exchange,
                        price,
                        volume
                    FROM market_trades
                    WHERE 1=1
            """
            
            # 添加过滤条件
            params = {}
            if symbol:
                base_query += " AND symbol = %(symbol)s"
                params["symbol"] = symbol
                
            if exchange:
                base_query += " AND exchange = %(exchange)s"
                params["exchange"] = exchange
            
            # 完成查询
            query = base_query + """
                    ORDER BY timestamp DESC
                    LIMIT 1000
                )
                SELECT 
                    symbol,
                    exchange,
                    avg(price) as avg_price,
                    sum(volume) as volume_24h,
                    min(price) as low_24h,
                    max(price) as high_24h
                FROM latest_trades
                GROUP BY symbol, exchange
                ORDER BY symbol, exchange
            """
            
            # 执行查询
            results = await clickhouse_client.execute(query, params)
            
            # 计算响应时间
            response_time = time.time() - query_start
            
            return results, response_time
        
        # 执行所有查询测试
        total_start = time.time()
        
        # 1. 测试无过滤条件查询 (全市场概况)
        logging.info("测试全市场概况查询...")
        for i in range(query_count // 3):
            # 执行查询
            _, response_time = await query_market_summary()
            response_times.append(response_time)
            
            # 输出查询信息
            logging.info(f"全市场概况查询 {i+1} 完成: 响应时间 {response_time*1000:.2f}毫秒")
            
            # 短暂暂停，避免过度负载
            await asyncio.sleep(0.2)
        
        # 2. 测试特定交易所查询
        test_exchanges = ["binance", "okex", "deribit"]
        logging.info("测试特定交易所市场概况查询...")
        for i in range(query_count // 3):
            # 随机选择交易所
            exchange = random.choice(test_exchanges)
            
            # 执行查询
            _, response_time = await query_market_summary(exchange=exchange)
            response_times.append(response_time)
            
            # 输出查询信息
            logging.info(f"交易所'{exchange}'市场概况查询 {i+1} 完成: 响应时间 {response_time*1000:.2f}毫秒")
            
            # 短暂暂停，避免过度负载
            await asyncio.sleep(0.2)
        
        # 3. 测试特定交易对查询
        test_symbols = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
        logging.info("测试特定交易对市场概况查询...")
        for i in range(query_count // 3):
            # 随机选择交易对
            symbol = random.choice(test_symbols)
            
            # 执行查询
            _, response_time = await query_market_summary(symbol=symbol)
            response_times.append(response_time)
            
            # 输出查询信息
            logging.info(f"交易对'{symbol}'市场概况查询 {i+1} 完成: 响应时间 {response_time*1000:.2f}毫秒")
            
            # 短暂暂停，避免过度负载
            await asyncio.sleep(0.2)
        
        # 统计结果
        total_time = time.time() - total_start
        avg_response = statistics.mean(response_times) if response_times else 0
        median_response = statistics.median(response_times) if response_times else 0
        min_response = min(response_times) if response_times else 0
        max_response = max(response_times) if response_times else 0
        p95_response = sorted(response_times)[int(len(response_times) * 0.95)] if len(response_times) >= 20 else max_response
        
        # 输出性能结果
        logging.info(f"市场概况API性能测试结果:")
        logging.info(f"总查询次数: {len(response_times)}")
        logging.info(f"总测试时间: {total_time:.3f} 秒")
        logging.info(f"平均响应时间: {avg_response*1000:.2f} 毫秒")
        logging.info(f"中位响应时间: {median_response*1000:.2f} 毫秒")
        logging.info(f"最小响应时间: {min_response*1000:.2f} 毫秒")
        logging.info(f"最大响应时间: {max_response*1000:.2f} 毫秒")
        logging.info(f"95%响应时间: {p95_response*1000:.2f} 毫秒")
        
        # 验证性能达标
        target_avg_response = 0.3  # 300毫秒
        target_p95_response = 0.8  # 800毫秒
        
        assert avg_response <= target_avg_response, f"平均响应时间 {avg_response*1000:.2f}ms 超过目标 {target_avg_response*1000:.2f}ms"
        assert p95_response <= target_p95_response, f"95%响应时间 {p95_response*1000:.2f}ms 超过目标 {target_p95_response*1000:.2f}ms" 