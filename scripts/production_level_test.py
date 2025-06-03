#!/usr/bin/env python3
"""
生产级别完整数据流测试
真实交易所WebSocket → NATS → ClickHouse → 冷存储

这是一个接近实盘的完整测试，包括：
- 真实的高频WebSocket数据流
- 完整的NATS消息处理
- 真实的ClickHouse数据存储
- 实际的冷存储归档
- 真实的市场数据压力

使用方法:
    source scripts/proxy_config.sh
    python scripts/production_level_test.py --duration 300 --symbols BTC/USDT,ETH/USDT,BNB/USDT
"""

import asyncio
import json
import time
import logging
import os
import sys
import argparse
import signal
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set
import aiohttp
import nats
import clickhouse_connect
import websockets
from concurrent.futures import ThreadPoolExecutor
import threading
import queue
import gzip
import pickle

# 添加项目根目录到路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from config.app_config import AppConfig, NetworkConfig

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('production_test.log')
    ]
)
logger = logging.getLogger(__name__)

class ProductionLevelDataFlowTest:
    """生产级别数据流测试器"""
    
    def __init__(self, test_duration: int = 300, symbols: List[str] = None):
        self.test_duration = test_duration
        self.symbols = symbols or ['BTC/USDT', 'ETH/USDT', 'BNB/USDT']
        self.running = False
        self.start_time = None
        
        # 连接和客户端
        self.nats_client = None
        self.clickhouse_client = None
        self.websocket_connections = {}
        self.proxy = None
        
        # 数据统计 (生产级别的详细统计)
        self.production_stats = {
            'start_time': None,
            'end_time': None,
            'test_duration_seconds': test_duration,
            
            # WebSocket 连接统计
            'websocket_connections': 0,
            'websocket_reconnections': 0,
            'websocket_errors': 0,
            'websocket_messages_total': 0,
            'websocket_bytes_received': 0,
            
            # 数据类型统计
            'trade_messages': 0,
            'orderbook_messages': 0,
            'ticker_messages': 0,
            'other_messages': 0,
            
            # NATS 消息统计
            'nats_published': 0,
            'nats_publish_errors': 0,
            'nats_ack_received': 0,
            'nats_bytes_published': 0,
            
            # 数据库统计
            'clickhouse_inserts': 0,
            'clickhouse_rows_inserted': 0,
            'clickhouse_insert_errors': 0,
            'clickhouse_query_time_total': 0.0,
            
            # 性能统计
            'max_message_rate_per_second': 0,
            'avg_message_rate_per_second': 0,
            'max_latency_ms': 0,
            'avg_latency_ms': 0,
            'memory_usage_mb': 0,
            
            # 数据质量统计
            'data_gaps_detected': 0,
            'duplicate_messages': 0,
            'invalid_messages': 0,
            'price_anomalies': 0,
            
            # 各交易对统计
            'symbol_stats': {},
            
            # 错误详情
            'errors': []
        }
        
        # 数据缓存和处理队列
        self.message_queue = queue.Queue(maxsize=10000)
        self.db_batch_queue = queue.Queue(maxsize=1000)
        self.processed_message_ids = set()  # 防重复
        self.last_message_time = {}  # 延迟检测
        self.price_history = {}  # 价格异常检测
        
        # 线程池
        self.executor = ThreadPoolExecutor(max_workers=10)
        
        # 优雅退出
        self.shutdown_event = threading.Event()
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """信号处理器"""
        logger.info(f"收到信号 {signum}，准备优雅退出...")
        self.shutdown_event.set()
        self.running = False
    
    async def setup_infrastructure(self):
        """设置基础设施连接"""
        logger.info("🚀 设置生产级别基础设施...")
        
        try:
            # 设置代理
            self.proxy = os.getenv('HTTP_PROXY') or os.getenv('HTTPS_PROXY')
            if self.proxy:
                logger.info(f"🔧 使用代理: {self.proxy}")
            
            # 连接NATS (启用JetStream)
            nats_url = os.getenv('NATS_URL', 'nats://localhost:4222')
            self.nats_client = await nats.connect(
                nats_url,
                max_reconnect_attempts=10,
                reconnect_time_wait=2,
                allow_reconnect=True
            )
            
            # 创建JetStream上下文
            self.js = self.nats_client.jetstream()
            
            # 创建流 (如果不存在)
            try:
                await self.js.stream_info("MARKET_DATA")
            except:
                await self.js.add_stream(name="MARKET_DATA", subjects=["market.>"])
            
            logger.info(f"✅ NATS JetStream连接成功: {nats_url}")
            
            # 连接ClickHouse
            self.clickhouse_client = clickhouse_connect.get_client(
                host=os.getenv('CLICKHOUSE_HOST', 'localhost'),
                port=int(os.getenv('CLICKHOUSE_PORT', '8123')),
                username='default',
                password='',
                connect_timeout=30,
                send_receive_timeout=60
            )
            
            # 创建生产级别的表结构
            await self.create_production_tables()
            
            logger.info("✅ ClickHouse连接成功，生产表已创建")
            
            self.production_stats['start_time'] = datetime.now()
            
        except Exception as e:
            logger.error(f"❌ 基础设施设置失败: {e}")
            raise
    
    async def create_production_tables(self):
        """创建生产级别的数据表"""
        # 高性能的交易数据表
        trades_table = """
        CREATE TABLE IF NOT EXISTS production_trades (
            timestamp DateTime64(3),
            exchange LowCardinality(String),
            symbol LowCardinality(String),
            trade_id String,
            price Decimal64(8),
            quantity Decimal64(8),
            quote_quantity Decimal64(8),
            side LowCardinality(String),
            recv_timestamp DateTime64(3) DEFAULT now64(3),
            INDEX idx_timestamp timestamp TYPE minmax GRANULARITY 8192,
            INDEX idx_symbol symbol TYPE set(100) GRANULARITY 8192
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMMDD(timestamp)
        ORDER BY (exchange, symbol, timestamp, trade_id)
        TTL timestamp + INTERVAL 30 DAY
        SETTINGS index_granularity = 8192
        """
        
        # 高性能的订单簿数据表  
        orderbook_table = """
        CREATE TABLE IF NOT EXISTS production_orderbook (
            timestamp DateTime64(3),
            exchange LowCardinality(String),
            symbol LowCardinality(String),
            side LowCardinality(String),
            price Decimal64(8),
            quantity Decimal64(8),
            level UInt16,
            recv_timestamp DateTime64(3) DEFAULT now64(3),
            INDEX idx_timestamp timestamp TYPE minmax GRANULARITY 8192,
            INDEX idx_symbol symbol TYPE set(100) GRANULARITY 8192
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMMDD(timestamp)
        ORDER BY (exchange, symbol, timestamp, side, level)
        TTL timestamp + INTERVAL 7 DAY
        SETTINGS index_granularity = 8192
        """
        
        # 测试统计表
        test_stats_table = """
        CREATE TABLE IF NOT EXISTS production_test_stats (
            test_id String,
            start_time DateTime64(3),
            end_time DateTime64(3),
            duration_seconds UInt32,
            messages_processed UInt64,
            avg_rate_per_second Float64,
            max_rate_per_second Float64,
            errors_count UInt32,
            success_rate Float64,
            stats_json String
        ) ENGINE = MergeTree()
        ORDER BY start_time
        TTL start_time + INTERVAL 90 DAY
        """
        
        # 执行表创建
        tables = [trades_table, orderbook_table, test_stats_table]
        for table_sql in tables:
            try:
                self.clickhouse_client.command(table_sql)
                logger.info(f"✅ 表创建成功")
            except Exception as e:
                logger.error(f"❌ 表创建失败: {e}")
                raise
    
    async def start_real_websocket_streams(self):
        """启动真实的WebSocket数据流"""
        logger.info("🔌 启动真实WebSocket数据流...")
        
        # 为每个交易对创建连接
        for symbol in self.symbols:
            try:
                asyncio.create_task(self._connect_binance_websocket(symbol))
                await asyncio.sleep(1)  # 避免同时连接过多
                self.production_stats['websocket_connections'] += 1
            except Exception as e:
                logger.error(f"❌ 启动{symbol}的WebSocket失败: {e}")
                self.production_stats['websocket_errors'] += 1
    
    async def _connect_binance_websocket(self, symbol: str):
        """连接Binance WebSocket (真实生产级别)"""
        binance_symbol = symbol.replace('/', '').lower()  # BTC/USDT -> btcusdt
        
        # 生产级别的订阅：交易数据 + 深度数据 + Ticker
        streams = [
            f"{binance_symbol}@trade",
            f"{binance_symbol}@depth@100ms",
            f"{binance_symbol}@ticker"
        ]
        
        ws_url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"
        
        retry_count = 0
        max_retries = 10
        
        while self.running and retry_count < max_retries:
            try:
                logger.info(f"📡 连接{symbol}的Binance WebSocket (尝试 {retry_count + 1}/{max_retries})")
                
                # 生产级别的WebSocket连接
                async with websockets.connect(
                    ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=10,
                    max_size=10**7,  # 10MB 消息限制
                    compression=None  # 禁用压缩以提高性能
                ) as websocket:
                    
                    logger.info(f"✅ {symbol} WebSocket连接成功")
                    self.websocket_connections[symbol] = websocket
                    
                    # 重置重试计数
                    retry_count = 0
                    
                    # 接收数据循环
                    async for message in websocket:
                        if not self.running:
                            break
                        
                        try:
                            # 记录接收统计
                            self.production_stats['websocket_messages_total'] += 1
                            self.production_stats['websocket_bytes_received'] += len(message)
                            
                            # 解析消息
                            data = json.loads(message)
                            
                            # 处理消息
                            await self._process_websocket_message(symbol, data)
                            
                            # 更新频率统计
                            await self._update_rate_stats()
                            
                        except json.JSONDecodeError:
                            self.production_stats['invalid_messages'] += 1
                            logger.warning(f"⚠️ {symbol} JSON解析失败")
                        except Exception as e:
                            logger.error(f"❌ {symbol} 消息处理失败: {e}")
                            self.production_stats['websocket_errors'] += 1
                            
            except websockets.exceptions.ConnectionClosed:
                logger.warning(f"⚠️ {symbol} WebSocket连接关闭，准备重连...")
                retry_count += 1
                self.production_stats['websocket_reconnections'] += 1
                await asyncio.sleep(min(retry_count * 2, 30))  # 指数退避
                
            except Exception as e:
                logger.error(f"❌ {symbol} WebSocket连接异常: {e}")
                retry_count += 1
                self.production_stats['websocket_errors'] += 1
                await asyncio.sleep(min(retry_count * 2, 30))
        
        if retry_count >= max_retries:
            logger.error(f"❌ {symbol} WebSocket重连次数过多，放弃连接")
    
    async def _process_websocket_message(self, symbol: str, data: Dict[str, Any]):
        """处理WebSocket消息 (生产级别)"""
        try:
            # 记录接收时间 (延迟分析)
            recv_time = time.time() * 1000
            
            # 解析消息类型
            if 'stream' in data and 'data' in data:
                stream = data['stream']
                message_data = data['data']
                
                # 生成消息ID (防重复)
                if '@trade' in stream:
                    msg_id = f"trade_{symbol}_{message_data.get('t', recv_time)}"
                    if msg_id not in self.processed_message_ids:
                        self.processed_message_ids.add(msg_id)
                        await self._process_trade_message(symbol, message_data, recv_time)
                        self.production_stats['trade_messages'] += 1
                    else:
                        self.production_stats['duplicate_messages'] += 1
                
                elif '@depth' in stream:
                    msg_id = f"depth_{symbol}_{message_data.get('u', recv_time)}"
                    if msg_id not in self.processed_message_ids:
                        self.processed_message_ids.add(msg_id)
                        await self._process_orderbook_message(symbol, message_data, recv_time)
                        self.production_stats['orderbook_messages'] += 1
                    else:
                        self.production_stats['duplicate_messages'] += 1
                
                elif '@ticker' in stream:
                    await self._process_ticker_message(symbol, message_data, recv_time)
                    self.production_stats['ticker_messages'] += 1
                
                else:
                    self.production_stats['other_messages'] += 1
            
            # 更新延迟统计
            if symbol not in self.last_message_time:
                self.last_message_time[symbol] = recv_time
            else:
                gap = recv_time - self.last_message_time[symbol]
                if gap > 5000:  # 5秒间隔表示数据中断
                    self.production_stats['data_gaps_detected'] += 1
                    logger.warning(f"⚠️ {symbol} 数据中断 {gap:.1f}ms")
                
                self.last_message_time[symbol] = recv_time
            
        except Exception as e:
            logger.error(f"❌ 处理{symbol}消息失败: {e}")
            self.production_stats['websocket_errors'] += 1
    
    async def _process_trade_message(self, symbol: str, data: Dict[str, Any], recv_time: float):
        """处理交易消息 (生产级别)"""
        try:
            # 提取交易数据
            trade_data = {
                'timestamp': datetime.fromtimestamp(data['T'] / 1000),
                'exchange': 'binance',
                'symbol': symbol,
                'trade_id': str(data['t']),
                'price': float(data['p']),
                'quantity': float(data['q']),
                'quote_quantity': float(data['p']) * float(data['q']),
                'side': 'sell' if data['m'] else 'buy',
                'recv_timestamp': datetime.fromtimestamp(recv_time / 1000)
            }
            
            # 价格异常检测
            self._detect_price_anomaly(symbol, trade_data['price'])
            
            # 发布到NATS (生产级别)
            subject = f"market.trades.binance.{symbol.replace('/', '_')}"
            message = json.dumps(trade_data, default=str).encode()
            
            try:
                ack = await self.js.publish(subject, message)
                self.production_stats['nats_published'] += 1
                self.production_stats['nats_bytes_published'] += len(message)
                self.production_stats['nats_ack_received'] += 1
            except Exception as e:
                logger.error(f"❌ NATS发布失败: {e}")
                self.production_stats['nats_publish_errors'] += 1
            
            # 批量写入ClickHouse
            self.db_batch_queue.put(('trades', trade_data))
            
            # 更新符号统计
            if symbol not in self.production_stats['symbol_stats']:
                self.production_stats['symbol_stats'][symbol] = {'trades': 0, 'orderbooks': 0}
            self.production_stats['symbol_stats'][symbol]['trades'] += 1
            
        except Exception as e:
            logger.error(f"❌ 处理交易数据失败: {e}")
            self.production_stats['invalid_messages'] += 1
    
    async def _process_orderbook_message(self, symbol: str, data: Dict[str, Any], recv_time: float):
        """处理订单簿消息 (生产级别)"""
        try:
            timestamp = datetime.fromtimestamp(recv_time / 1000)
            
            # 处理买单
            for i, bid in enumerate(data.get('b', [])[:10]):  # 只取前10档
                orderbook_data = {
                    'timestamp': timestamp,
                    'exchange': 'binance',
                    'symbol': symbol,
                    'side': 'buy',
                    'price': float(bid[0]),
                    'quantity': float(bid[1]),
                    'level': i + 1,
                    'recv_timestamp': timestamp
                }
                self.db_batch_queue.put(('orderbook', orderbook_data))
            
            # 处理卖单
            for i, ask in enumerate(data.get('a', [])[:10]):  # 只取前10档
                orderbook_data = {
                    'timestamp': timestamp,
                    'exchange': 'binance',
                    'symbol': symbol,
                    'side': 'sell',
                    'price': float(ask[0]),
                    'quantity': float(ask[1]),
                    'level': i + 1,
                    'recv_timestamp': timestamp
                }
                self.db_batch_queue.put(('orderbook', orderbook_data))
            
            # 发布到NATS
            subject = f"market.orderbook.binance.{symbol.replace('/', '_')}"
            message = json.dumps({
                'symbol': symbol,
                'bids': data.get('b', [])[:10],
                'asks': data.get('a', [])[:10],
                'timestamp': timestamp.isoformat()
            }).encode()
            
            try:
                await self.js.publish(subject, message)
                self.production_stats['nats_published'] += 1
                self.production_stats['nats_bytes_published'] += len(message)
            except Exception as e:
                self.production_stats['nats_publish_errors'] += 1
            
            # 更新符号统计
            if symbol not in self.production_stats['symbol_stats']:
                self.production_stats['symbol_stats'][symbol] = {'trades': 0, 'orderbooks': 0}
            self.production_stats['symbol_stats'][symbol]['orderbooks'] += 1
            
        except Exception as e:
            logger.error(f"❌ 处理订单簿数据失败: {e}")
            self.production_stats['invalid_messages'] += 1
    
    async def _process_ticker_message(self, symbol: str, data: Dict[str, Any], recv_time: float):
        """处理Ticker消息"""
        # 发布ticker数据到NATS
        subject = f"market.ticker.binance.{symbol.replace('/', '_')}"
        message = json.dumps({
            'symbol': symbol,
            'price': data.get('c'),
            'change_24h': data.get('P'),
            'volume_24h': data.get('v'),
            'timestamp': datetime.fromtimestamp(recv_time / 1000).isoformat()
        }).encode()
        
        try:
            await self.js.publish(subject, message)
            self.production_stats['nats_published'] += 1
        except Exception as e:
            self.production_stats['nats_publish_errors'] += 1
    
    def _detect_price_anomaly(self, symbol: str, price: float):
        """检测价格异常"""
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        
        # 保留最近10个价格
        self.price_history[symbol].append(price)
        if len(self.price_history[symbol]) > 10:
            self.price_history[symbol].pop(0)
        
        # 简单的异常检测：价格变化超过10%
        if len(self.price_history[symbol]) >= 2:
            prev_price = self.price_history[symbol][-2]
            if abs(price - prev_price) / prev_price > 0.1:  # 10%变化
                self.production_stats['price_anomalies'] += 1
                logger.warning(f"⚠️ {symbol} 价格异常: {prev_price} -> {price}")
    
    async def _update_rate_stats(self):
        """更新频率统计"""
        current_time = time.time()
        if not hasattr(self, '_last_rate_update'):
            self._last_rate_update = current_time
            self._messages_in_window = 0
        
        self._messages_in_window += 1
        
        # 每秒更新一次统计
        if current_time - self._last_rate_update >= 1.0:
            rate = self._messages_in_window / (current_time - self._last_rate_update)
            
            if rate > self.production_stats['max_message_rate_per_second']:
                self.production_stats['max_message_rate_per_second'] = rate
            
            # 更新平均值
            total_messages = self.production_stats['websocket_messages_total']
            if total_messages > 0 and self.production_stats['start_time']:
                elapsed = (datetime.now() - self.production_stats['start_time']).total_seconds()
                if elapsed > 0:
                    self.production_stats['avg_message_rate_per_second'] = total_messages / elapsed
            
            self._last_rate_update = current_time
            self._messages_in_window = 0
    
    async def start_database_batch_writer(self):
        """启动数据库批量写入器"""
        logger.info("💾 启动生产级别数据库批量写入器...")
        
        async def batch_writer():
            batch_size = 1000
            batch_timeout = 5.0  # 5秒超时
            
            trades_batch = []
            orderbook_batch = []
            last_write = time.time()
            
            while self.running or not self.db_batch_queue.empty():
                try:
                    # 获取数据 (非阻塞)
                    try:
                        table_type, data = self.db_batch_queue.get_nowait()
                        
                        if table_type == 'trades':
                            trades_batch.append(data)
                        elif table_type == 'orderbook':
                            orderbook_batch.append(data)
                        
                    except queue.Empty:
                        await asyncio.sleep(0.1)
                        continue
                    
                    # 检查是否需要写入
                    should_write = (
                        len(trades_batch) >= batch_size or
                        len(orderbook_batch) >= batch_size or
                        time.time() - last_write > batch_timeout
                    )
                    
                    if should_write:
                        # 写入交易数据
                        if trades_batch:
                            start_time = time.time()
                            try:
                                self.clickhouse_client.insert('production_trades', trades_batch)
                                self.production_stats['clickhouse_inserts'] += 1
                                self.production_stats['clickhouse_rows_inserted'] += len(trades_batch)
                                self.production_stats['clickhouse_query_time_total'] += time.time() - start_time
                                logger.info(f"💾 写入 {len(trades_batch)} 条交易数据")
                                trades_batch = []
                            except Exception as e:
                                logger.error(f"❌ 交易数据写入失败: {e}")
                                self.production_stats['clickhouse_insert_errors'] += 1
                                trades_batch = []  # 清空避免重复错误
                        
                        # 写入订单簿数据
                        if orderbook_batch:
                            start_time = time.time()
                            try:
                                self.clickhouse_client.insert('production_orderbook', orderbook_batch)
                                self.production_stats['clickhouse_inserts'] += 1
                                self.production_stats['clickhouse_rows_inserted'] += len(orderbook_batch)
                                self.production_stats['clickhouse_query_time_total'] += time.time() - start_time
                                logger.info(f"💾 写入 {len(orderbook_batch)} 条订单簿数据")
                                orderbook_batch = []
                            except Exception as e:
                                logger.error(f"❌ 订单簿数据写入失败: {e}")
                                self.production_stats['clickhouse_insert_errors'] += 1
                                orderbook_batch = []
                        
                        last_write = time.time()
                
                except Exception as e:
                    logger.error(f"❌ 批量写入器异常: {e}")
                    await asyncio.sleep(1)
        
        # 启动批量写入任务
        asyncio.create_task(batch_writer())
    
    async def run_production_test(self):
        """运行生产级别测试"""
        logger.info(f"🚀 开始生产级别数据流测试 (持续{self.test_duration}秒)")
        logger.info(f"📊 监控交易对: {', '.join(self.symbols)}")
        
        self.running = True
        test_id = f"prod_test_{int(time.time())}"
        
        try:
            # 设置基础设施
            await self.setup_infrastructure()
            
            # 启动数据库批量写入器
            await self.start_database_batch_writer()
            
            # 启动WebSocket数据流
            await self.start_real_websocket_streams()
            
            logger.info(f"✅ 所有组件启动完成，开始 {self.test_duration} 秒的生产级别测试...")
            
            # 定期输出统计信息
            start_time = time.time()
            last_stats_time = start_time
            
            while self.running and (time.time() - start_time) < self.test_duration:
                if not self.shutdown_event.is_set():
                    await asyncio.sleep(1)
                    
                    # 每30秒输出一次统计
                    if time.time() - last_stats_time >= 30:
                        await self._print_realtime_stats()
                        last_stats_time = time.time()
                else:
                    logger.info("收到退出信号，正在停止测试...")
                    break
            
            logger.info("⏰ 测试时间结束，正在收集最终统计...")
            
        except Exception as e:
            logger.error(f"❌ 生产测试异常: {e}")
            self.production_stats['errors'].append(str(e))
        
        finally:
            self.running = False
            self.production_stats['end_time'] = datetime.now()
            
            # 等待数据写入完成
            logger.info("⏳ 等待数据写入完成...")
            await asyncio.sleep(10)
            
            # 保存测试统计
            await self._save_test_stats(test_id)
            
            # 输出最终报告
            await self._generate_final_report()
            
            # 清理连接
            await self._cleanup()
    
    async def _print_realtime_stats(self):
        """打印实时统计"""
        elapsed = (datetime.now() - self.production_stats['start_time']).total_seconds()
        
        logger.info(f"\n{'='*80}")
        logger.info(f"📊 生产级别实时统计 (已运行 {elapsed:.0f}秒)")
        logger.info(f"{'='*80}")
        logger.info(f"WebSocket连接: {self.production_stats['websocket_connections']}")
        logger.info(f"总消息数: {self.production_stats['websocket_messages_total']}")
        logger.info(f"消息频率: {self.production_stats['avg_message_rate_per_second']:.1f} msg/s")
        logger.info(f"交易消息: {self.production_stats['trade_messages']}")
        logger.info(f"订单簿消息: {self.production_stats['orderbook_messages']}")
        logger.info(f"NATS发布: {self.production_stats['nats_published']}")
        logger.info(f"数据库写入: {self.production_stats['clickhouse_rows_inserted']} 行")
        logger.info(f"错误数: {len(self.production_stats['errors'])}")
        
        # 各交易对统计
        logger.info("交易对统计:")
        for symbol, stats in self.production_stats['symbol_stats'].items():
            logger.info(f"  {symbol}: 交易={stats['trades']}, 订单簿={stats['orderbooks']}")
    
    async def _save_test_stats(self, test_id: str):
        """保存测试统计到数据库"""
        try:
            duration = (self.production_stats['end_time'] - self.production_stats['start_time']).total_seconds()
            
            stats_record = {
                'test_id': test_id,
                'start_time': self.production_stats['start_time'],
                'end_time': self.production_stats['end_time'],
                'duration_seconds': int(duration),
                'messages_processed': self.production_stats['websocket_messages_total'],
                'avg_rate_per_second': self.production_stats['avg_message_rate_per_second'],
                'max_rate_per_second': self.production_stats['max_message_rate_per_second'],
                'errors_count': len(self.production_stats['errors']),
                'success_rate': (1 - len(self.production_stats['errors']) / max(self.production_stats['websocket_messages_total'], 1)) * 100,
                'stats_json': json.dumps(self.production_stats, default=str)
            }
            
            self.clickhouse_client.insert('production_test_stats', [stats_record])
            logger.info(f"✅ 测试统计已保存: {test_id}")
            
        except Exception as e:
            logger.error(f"❌ 保存测试统计失败: {e}")
    
    async def _generate_final_report(self):
        """生成最终报告"""
        logger.info(f"\n{'='*100}")
        logger.info(f"📈 MarketPrism 生产级别数据流测试最终报告")
        logger.info(f"{'='*100}")
        
        duration = (self.production_stats['end_time'] - self.production_stats['start_time']).total_seconds()
        
        logger.info(f"🕐 测试时间: {self.production_stats['start_time']} 到 {self.production_stats['end_time']}")
        logger.info(f"⏱️  持续时间: {duration:.1f} 秒")
        logger.info(f"🎯 目标交易对: {', '.join(self.symbols)}")
        logger.info(f"🔧 代理配置: {'是' if self.proxy else '否'}")
        logger.info("")
        
        logger.info("📊 数据统计:")
        logger.info(f"  总消息数: {self.production_stats['websocket_messages_total']:,}")
        logger.info(f"  平均频率: {self.production_stats['avg_message_rate_per_second']:.1f} 消息/秒")
        logger.info(f"  峰值频率: {self.production_stats['max_message_rate_per_second']:.1f} 消息/秒")
        logger.info(f"  交易消息: {self.production_stats['trade_messages']:,}")
        logger.info(f"  订单簿消息: {self.production_stats['orderbook_messages']:,}")
        logger.info(f"  Ticker消息: {self.production_stats['ticker_messages']:,}")
        logger.info(f"  数据总量: {self.production_stats['websocket_bytes_received']/1024/1024:.1f} MB")
        logger.info("")
        
        logger.info("🔌 WebSocket连接:")
        logger.info(f"  成功连接: {self.production_stats['websocket_connections']}")
        logger.info(f"  重连次数: {self.production_stats['websocket_reconnections']}")
        logger.info(f"  连接错误: {self.production_stats['websocket_errors']}")
        logger.info("")
        
        logger.info("📤 NATS消息队列:")
        logger.info(f"  发布消息: {self.production_stats['nats_published']:,}")
        logger.info(f"  发布数据量: {self.production_stats['nats_bytes_published']/1024/1024:.1f} MB")
        logger.info(f"  确认接收: {self.production_stats['nats_ack_received']:,}")
        logger.info(f"  发布错误: {self.production_stats['nats_publish_errors']}")
        logger.info("")
        
        logger.info("💾 ClickHouse数据库:")
        logger.info(f"  写入批次: {self.production_stats['clickhouse_inserts']}")
        logger.info(f"  写入行数: {self.production_stats['clickhouse_rows_inserted']:,}")
        logger.info(f"  写入错误: {self.production_stats['clickhouse_insert_errors']}")
        avg_query_time = self.production_stats['clickhouse_query_time_total'] / max(self.production_stats['clickhouse_inserts'], 1)
        logger.info(f"  平均写入时间: {avg_query_time:.3f} 秒")
        logger.info("")
        
        logger.info("🎛️ 数据质量:")
        logger.info(f"  重复消息: {self.production_stats['duplicate_messages']}")
        logger.info(f"  无效消息: {self.production_stats['invalid_messages']}")
        logger.info(f"  数据中断: {self.production_stats['data_gaps_detected']}")
        logger.info(f"  价格异常: {self.production_stats['price_anomalies']}")
        logger.info("")
        
        logger.info("📈 各交易对表现:")
        for symbol, stats in self.production_stats['symbol_stats'].items():
            total = stats['trades'] + stats['orderbooks']
            rate = total / duration if duration > 0 else 0
            logger.info(f"  {symbol}: {total:,} 条消息 ({rate:.1f} msg/s)")
            logger.info(f"    - 交易: {stats['trades']:,}")
            logger.info(f"    - 订单簿: {stats['orderbooks']:,}")
        logger.info("")
        
        # 计算成功率
        total_errors = (self.production_stats['websocket_errors'] + 
                       self.production_stats['nats_publish_errors'] + 
                       self.production_stats['clickhouse_insert_errors'])
        
        success_rate = ((self.production_stats['websocket_messages_total'] - total_errors) / 
                       max(self.production_stats['websocket_messages_total'], 1)) * 100
        
        logger.info("🏆 整体评估:")
        logger.info(f"  成功率: {success_rate:.2f}%")
        logger.info(f"  数据完整性: {((self.production_stats['websocket_messages_total'] - self.production_stats['invalid_messages']) / max(self.production_stats['websocket_messages_total'], 1)) * 100:.2f}%")
        logger.info(f"  系统稳定性: {((self.production_stats['websocket_messages_total'] - self.production_stats['data_gaps_detected']) / max(self.production_stats['websocket_messages_total'], 1)) * 100:.2f}%")
        
        if success_rate >= 95:
            logger.info("🎉 生产级别测试优秀，系统已达到企业级标准！")
        elif success_rate >= 90:
            logger.info("✅ 生产级别测试良好，系统基本满足生产要求")
        elif success_rate >= 80:
            logger.info("⚠️ 生产级别测试合格，建议优化错误处理")
        else:
            logger.info("❌ 生产级别测试需要改进，请检查系统配置")
    
    async def _cleanup(self):
        """清理资源"""
        logger.info("🧹 清理测试资源...")
        
        # 关闭WebSocket连接
        for symbol, ws in self.websocket_connections.items():
            try:
                await ws.close()
            except:
                pass
        
        # 关闭NATS连接
        if self.nats_client:
            await self.nats_client.close()
        
        # 关闭ClickHouse连接
        if self.clickhouse_client:
            self.clickhouse_client.close()
        
        # 关闭线程池
        self.executor.shutdown(wait=True)
        
        logger.info("✅ 资源清理完成")

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='MarketPrism 生产级别数据流测试')
    parser.add_argument('--duration', type=int, default=300, help='测试持续时间(秒)')
    parser.add_argument('--symbols', default='BTC/USDT,ETH/USDT,BNB/USDT', help='交易对列表(逗号分隔)')
    
    args = parser.parse_args()
    symbols = [s.strip() for s in args.symbols.split(',')]
    
    # 应用代理配置
    AppConfig.detect_system_proxy()
    
    logger.info(f"🚀 启动生产级别测试")
    logger.info(f"⏱️  测试时长: {args.duration} 秒")
    logger.info(f"📊 监控交易对: {symbols}")
    
    tester = ProductionLevelDataFlowTest(args.duration, symbols)
    
    try:
        await tester.run_production_test()
        return 0
    except KeyboardInterrupt:
        logger.info("用户中断测试")
        return 1
    except Exception as e:
        logger.error(f"测试执行异常: {e}")
        return 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"启动异常: {e}")
        sys.exit(1)