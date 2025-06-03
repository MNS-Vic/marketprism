#!/usr/bin/env python3
"""
生产级别WebSocket数据流测试
直接连接真实交易所WebSocket，测试完整数据处理链路

这是一个真正接近实盘的测试：
- 真实的高频交易所WebSocket连接
- 真实的市场数据处理
- 完整的数据分析和统计
- 生产级别的错误处理和监控

使用方法:
    source scripts/proxy_config.sh
    python scripts/production_websocket_test.py --duration 180 --symbols BTC/USDT,ETH/USDT,BNB/USDT
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
import websockets
from collections import defaultdict, deque
import threading
import statistics
import csv

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
        logging.FileHandler(f'production_websocket_test_{int(time.time())}.log')
    ]
)
logger = logging.getLogger(__name__)

class ProductionWebSocketTester:
    """生产级别WebSocket数据流测试器"""
    
    def __init__(self, test_duration: int = 180, symbols: List[str] = None):
        self.test_duration = test_duration
        self.symbols = symbols or ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'ADA/USDT']
        self.running = False
        self.start_time = None
        
        # WebSocket连接池
        self.websocket_connections = {}
        self.connection_status = {}
        
        # 生产级别统计数据
        self.production_metrics = {
            'test_config': {
                'start_time': None,
                'end_time': None,
                'duration_seconds': test_duration,
                'symbols': self.symbols,
                'proxy_used': bool(os.getenv('HTTP_PROXY'))
            },
            
            # 连接统计
            'connection_stats': {
                'total_connections': 0,
                'successful_connections': 0,
                'failed_connections': 0,
                'reconnection_attempts': 0,
                'connection_uptime_seconds': defaultdict(float),
                'connection_errors': defaultdict(int)
            },
            
            # 数据流统计
            'data_flow_stats': {
                'total_messages': 0,
                'messages_per_second_history': deque(maxlen=1000),
                'max_messages_per_second': 0,
                'avg_messages_per_second': 0,
                'total_bytes_received': 0,
                'message_size_history': deque(maxlen=1000)
            },
            
            # 按消息类型统计
            'message_type_stats': {
                'trade_messages': 0,
                'orderbook_messages': 0,
                'ticker_messages': 0,
                'other_messages': 0,
                'invalid_messages': 0
            },
            
            # 按交易对统计
            'symbol_stats': defaultdict(lambda: {
                'trades': 0,
                'orderbooks': 0,
                'tickers': 0,
                'last_price': 0,
                'price_changes': deque(maxlen=100),
                'volume_24h': 0,
                'data_gaps': 0,
                'last_update': None
            }),
            
            # 市场数据质量统计
            'data_quality_stats': {
                'duplicate_messages': 0,
                'out_of_sequence_messages': 0,
                'data_gaps_detected': 0,
                'price_anomalies': 0,
                'latency_samples': deque(maxlen=1000),
                'avg_latency_ms': 0,
                'max_latency_ms': 0
            },
            
            # 错误统计
            'error_stats': {
                'websocket_errors': 0,
                'json_parse_errors': 0,
                'network_timeouts': 0,
                'connection_drops': 0,
                'unknown_errors': 0,
                'error_details': []
            },
            
            # 性能统计
            'performance_stats': {
                'cpu_usage_samples': deque(maxlen=100),
                'memory_usage_samples': deque(maxlen=100),
                'network_latency_samples': deque(maxlen=100),
                'processing_time_samples': deque(maxlen=100)
            }
        }
        
        # 数据处理队列和缓存
        self.message_sequences = defaultdict(int)
        self.last_message_times = defaultdict(float)
        self.price_history = defaultdict(lambda: deque(maxlen=50))
        
        # 实时统计更新
        self.stats_update_interval = 10  # 10秒更新一次统计
        self.last_stats_update = time.time()
        
        # 优雅退出
        self.shutdown_event = threading.Event()
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """信号处理器"""
        logger.info(f"收到信号 {signum}，准备优雅退出...")
        self.shutdown_event.set()
        self.running = False
    
    async def start_production_test(self):
        """启动生产级别测试"""
        logger.info(f"🚀 启动生产级别WebSocket数据流测试")
        logger.info(f"⏱️  测试时长: {self.test_duration} 秒")
        logger.info(f"📊 监控交易对: {', '.join(self.symbols)}")
        logger.info(f"🌐 代理配置: {'是' if self.production_metrics['test_config']['proxy_used'] else '否'}")
        
        self.running = True
        self.start_time = time.time()
        self.production_metrics['test_config']['start_time'] = datetime.now()
        
        try:
            # 启动所有WebSocket连接
            await self._start_all_websocket_connections()
            
            # 启动统计监控任务
            asyncio.create_task(self._stats_monitor())
            
            # 主测试循环
            await self._run_test_loop()
            
        except Exception as e:
            logger.error(f"❌ 生产测试异常: {e}")
            self.production_metrics['error_stats']['unknown_errors'] += 1
            self.production_metrics['error_stats']['error_details'].append(str(e))
        
        finally:
            self.running = False
            self.production_metrics['test_config']['end_time'] = datetime.now()
            
            # 等待连接清理
            await self._cleanup_connections()
            
            # 生成最终报告
            await self._generate_production_report()
    
    async def _start_all_websocket_connections(self):
        """启动所有WebSocket连接"""
        logger.info("🔌 启动WebSocket连接池...")
        
        connection_tasks = []
        for symbol in self.symbols:
            task = asyncio.create_task(self._manage_websocket_connection(symbol))
            connection_tasks.append(task)
            
            # 避免同时启动过多连接
            await asyncio.sleep(0.5)
        
        logger.info(f"✅ 已启动 {len(connection_tasks)} 个WebSocket连接任务")
    
    async def _manage_websocket_connection(self, symbol: str):
        """管理单个WebSocket连接 (包含重连逻辑)"""
        retry_count = 0
        max_retries = 10
        
        while self.running and retry_count < max_retries:
            try:
                await self._connect_binance_websocket(symbol)
                retry_count = 0  # 成功连接后重置重试计数
                
            except Exception as e:
                retry_count += 1
                self.production_metrics['connection_stats']['failed_connections'] += 1
                self.production_metrics['connection_stats']['reconnection_attempts'] += 1
                
                logger.warning(f"⚠️ {symbol} 连接失败 (尝试 {retry_count}/{max_retries}): {e}")
                
                if retry_count < max_retries:
                    wait_time = min(retry_count * 2, 30)  # 指数退避，最多30秒
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"❌ {symbol} 达到最大重试次数，停止连接")
                    break
    
    async def _connect_binance_websocket(self, symbol: str):
        """连接Binance WebSocket"""
        binance_symbol = symbol.replace('/', '').lower()
        
        # 生产级别的流订阅
        streams = [
            f"{binance_symbol}@trade",           # 交易数据
            f"{binance_symbol}@depth@100ms",     # 深度数据
            f"{binance_symbol}@ticker",          # 24h统计
            f"{binance_symbol}@miniTicker"       # 简化Ticker
        ]
        
        ws_url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"
        
        logger.info(f"📡 连接 {symbol} WebSocket...")
        
        connection_start = time.time()
        
        # 生产级别的WebSocket连接参数
        async with websockets.connect(
            ws_url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=10,
            max_size=10**7,  # 10MB 消息限制
            max_queue=1000,  # 消息队列限制
            compression=None  # 禁用压缩提高性能
        ) as websocket:
            
            connection_uptime_start = time.time()
            self.websocket_connections[symbol] = websocket
            self.connection_status[symbol] = 'connected'
            self.production_metrics['connection_stats']['successful_connections'] += 1
            
            logger.info(f"✅ {symbol} WebSocket连接成功")
            
            try:
                # 消息接收循环
                async for message in websocket:
                    if not self.running:
                        break
                    
                    # 记录连接时长
                    current_time = time.time()
                    uptime = current_time - connection_uptime_start
                    self.production_metrics['connection_stats']['connection_uptime_seconds'][symbol] = uptime
                    
                    # 处理消息
                    await self._process_production_message(symbol, message, current_time)
                    
            except websockets.exceptions.ConnectionClosed:
                logger.warning(f"⚠️ {symbol} WebSocket连接关闭")
                self.production_metrics['error_stats']['connection_drops'] += 1
                raise
            
            except asyncio.TimeoutError:
                logger.warning(f"⏰ {symbol} WebSocket超时")
                self.production_metrics['error_stats']['network_timeouts'] += 1
                raise
            
            finally:
                # 清理连接状态
                if symbol in self.websocket_connections:
                    del self.websocket_connections[symbol]
                self.connection_status[symbol] = 'disconnected'
    
    async def _process_production_message(self, symbol: str, message: str, recv_time: float):
        """处理生产级别消息"""
        try:
            # 基础统计
            self.production_metrics['data_flow_stats']['total_messages'] += 1
            self.production_metrics['data_flow_stats']['total_bytes_received'] += len(message)
            self.production_metrics['data_flow_stats']['message_size_history'].append(len(message))
            
            # 解析JSON
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                self.production_metrics['message_type_stats']['invalid_messages'] += 1
                self.production_metrics['error_stats']['json_parse_errors'] += 1
                return
            
            # 处理不同类型的消息
            if 'stream' in data and 'data' in data:
                stream = data['stream']
                message_data = data['data']
                
                # 计算消息延迟
                if 'E' in message_data:  # Binance事件时间
                    event_time = message_data['E'] / 1000
                    latency = (recv_time - event_time) * 1000  # 毫秒
                    if latency > 0 and latency < 10000:  # 合理的延迟范围
                        self.production_metrics['data_quality_stats']['latency_samples'].append(latency)
                
                # 处理不同类型的流
                if '@trade' in stream:
                    await self._process_trade_data(symbol, message_data, recv_time)
                elif '@depth' in stream:
                    await self._process_orderbook_data(symbol, message_data, recv_time)
                elif '@ticker' in stream or '@miniTicker' in stream:
                    await self._process_ticker_data(symbol, message_data, recv_time)
                else:
                    self.production_metrics['message_type_stats']['other_messages'] += 1
            
            # 更新符号统计
            self.production_metrics['symbol_stats'][symbol]['last_update'] = recv_time
            
            # 检测数据中断
            if symbol in self.last_message_times:
                gap = recv_time - self.last_message_times[symbol]
                if gap > 5.0:  # 5秒以上的间隔
                    self.production_metrics['data_quality_stats']['data_gaps_detected'] += 1
                    self.production_metrics['symbol_stats'][symbol]['data_gaps'] += 1
            
            self.last_message_times[symbol] = recv_time
            
        except Exception as e:
            self.production_metrics['error_stats']['websocket_errors'] += 1
            logger.error(f"❌ 处理{symbol}消息失败: {e}")
    
    async def _process_trade_data(self, symbol: str, data: Dict[str, Any], recv_time: float):
        """处理交易数据"""
        try:
            price = float(data['p'])
            quantity = float(data['q'])
            
            # 更新统计
            self.production_metrics['message_type_stats']['trade_messages'] += 1
            self.production_metrics['symbol_stats'][symbol]['trades'] += 1
            self.production_metrics['symbol_stats'][symbol]['last_price'] = price
            
            # 价格变化分析
            self.price_history[symbol].append(price)
            if len(self.price_history[symbol]) >= 2:
                price_change = price - self.price_history[symbol][-2]
                self.production_metrics['symbol_stats'][symbol]['price_changes'].append(price_change)
                
                # 检测价格异常 (超过2%的单次变化)
                if abs(price_change / price) > 0.02:
                    self.production_metrics['data_quality_stats']['price_anomalies'] += 1
                    logger.warning(f"⚠️ {symbol} 价格异常变化: {price_change:.2f} ({price_change/price*100:.1f}%)")
            
        except (KeyError, ValueError) as e:
            self.production_metrics['message_type_stats']['invalid_messages'] += 1
    
    async def _process_orderbook_data(self, symbol: str, data: Dict[str, Any], recv_time: float):
        """处理订单簿数据"""
        try:
            # 更新统计
            self.production_metrics['message_type_stats']['orderbook_messages'] += 1
            self.production_metrics['symbol_stats'][symbol]['orderbooks'] += 1
            
            # 序列号检查 (检测消息乱序)
            if 'u' in data:  # 更新ID
                update_id = data['u']
                if symbol in self.message_sequences:
                    if update_id <= self.message_sequences[symbol]:
                        self.production_metrics['data_quality_stats']['out_of_sequence_messages'] += 1
                self.message_sequences[symbol] = update_id
            
        except (KeyError, ValueError) as e:
            self.production_metrics['message_type_stats']['invalid_messages'] += 1
    
    async def _process_ticker_data(self, symbol: str, data: Dict[str, Any], recv_time: float):
        """处理Ticker数据"""
        try:
            # 更新统计
            self.production_metrics['message_type_stats']['ticker_messages'] += 1
            self.production_metrics['symbol_stats'][symbol]['tickers'] += 1
            
            # 更新24h交易量
            if 'v' in data:
                self.production_metrics['symbol_stats'][symbol]['volume_24h'] = float(data['v'])
            
        except (KeyError, ValueError) as e:
            self.production_metrics['message_type_stats']['invalid_messages'] += 1
    
    async def _stats_monitor(self):
        """统计监控任务"""
        while self.running:
            await asyncio.sleep(self.stats_update_interval)
            
            try:
                await self._update_realtime_stats()
                await self._print_realtime_stats()
            except Exception as e:
                logger.error(f"❌ 统计更新失败: {e}")
    
    async def _update_realtime_stats(self):
        """更新实时统计"""
        current_time = time.time()
        elapsed = current_time - self.start_time
        
        if elapsed > 0:
            # 更新消息频率
            total_messages = self.production_metrics['data_flow_stats']['total_messages']
            current_rate = total_messages / elapsed
            self.production_metrics['data_flow_stats']['avg_messages_per_second'] = current_rate
            self.production_metrics['data_flow_stats']['messages_per_second_history'].append(current_rate)
            
            # 更新最大频率
            if current_rate > self.production_metrics['data_flow_stats']['max_messages_per_second']:
                self.production_metrics['data_flow_stats']['max_messages_per_second'] = current_rate
        
        # 更新延迟统计
        latency_samples = self.production_metrics['data_quality_stats']['latency_samples']
        if latency_samples:
            self.production_metrics['data_quality_stats']['avg_latency_ms'] = statistics.mean(latency_samples)
            self.production_metrics['data_quality_stats']['max_latency_ms'] = max(latency_samples)
    
    async def _print_realtime_stats(self):
        """打印实时统计"""
        elapsed = time.time() - self.start_time
        remaining = max(0, self.test_duration - elapsed)
        
        logger.info(f"\n{'='*80}")
        logger.info(f"📊 生产级别实时统计 (已运行 {elapsed:.0f}秒, 剩余 {remaining:.0f}秒)")
        logger.info(f"{'='*80}")
        
        # 连接统计
        active_connections = len([s for s, status in self.connection_status.items() if status == 'connected'])
        logger.info(f"🔌 连接状态: {active_connections}/{len(self.symbols)} 活跃")
        
        # 数据流统计
        total_msg = self.production_metrics['data_flow_stats']['total_messages']
        avg_rate = self.production_metrics['data_flow_stats']['avg_messages_per_second']
        max_rate = self.production_metrics['data_flow_stats']['max_messages_per_second']
        total_mb = self.production_metrics['data_flow_stats']['total_bytes_received'] / 1024 / 1024
        
        logger.info(f"📈 数据流: {total_msg:,} 条消息 ({avg_rate:.1f} msg/s 平均, {max_rate:.1f} msg/s 峰值)")
        logger.info(f"💾 数据量: {total_mb:.2f} MB")
        
        # 消息类型分布
        trades = self.production_metrics['message_type_stats']['trade_messages']
        orderbooks = self.production_metrics['message_type_stats']['orderbook_messages']
        tickers = self.production_metrics['message_type_stats']['ticker_messages']
        
        logger.info(f"📋 消息类型: 交易={trades:,}, 订单簿={orderbooks:,}, Ticker={tickers:,}")
        
        # 数据质量
        gaps = self.production_metrics['data_quality_stats']['data_gaps_detected']
        anomalies = self.production_metrics['data_quality_stats']['price_anomalies']
        avg_latency = self.production_metrics['data_quality_stats']['avg_latency_ms']
        
        logger.info(f"🎯 数据质量: 中断={gaps}, 价格异常={anomalies}, 平均延迟={avg_latency:.1f}ms")
        
        # 错误统计
        total_errors = sum(self.production_metrics['error_stats'].values()) - len(self.production_metrics['error_stats']['error_details'])
        logger.info(f"❌ 错误: {total_errors} 个")
        
        # 各交易对表现
        logger.info("💹 交易对表现:")
        for symbol, stats in self.production_metrics['symbol_stats'].items():
            if stats['last_update']:
                last_update_ago = time.time() - stats['last_update']
                status = "🟢" if last_update_ago < 10 else "🟡" if last_update_ago < 30 else "🔴"
                logger.info(f"  {status} {symbol}: 价格={stats['last_price']:.2f}, 交易={stats['trades']}, 订单簿={stats['orderbooks']}")
    
    async def _run_test_loop(self):
        """主测试循环"""
        while self.running and (time.time() - self.start_time) < self.test_duration:
            if not self.shutdown_event.is_set():
                await asyncio.sleep(1)
            else:
                logger.info("收到退出信号，正在停止测试...")
                break
        
        logger.info("⏰ 测试时间结束，正在收集最终数据...")
    
    async def _cleanup_connections(self):
        """清理连接"""
        logger.info("🧹 清理WebSocket连接...")
        
        for symbol, ws in self.websocket_connections.items():
            try:
                await ws.close()
            except:
                pass
        
        self.websocket_connections.clear()
        logger.info("✅ 连接清理完成")
    
    async def _generate_production_report(self):
        """生成生产级别报告"""
        logger.info(f"\n{'='*100}")
        logger.info(f"📈 MarketPrism 生产级别WebSocket数据流测试最终报告")
        logger.info(f"{'='*100}")
        
        # 计算测试时长
        start_time = self.production_metrics['test_config']['start_time']
        end_time = self.production_metrics['test_config']['end_time']
        actual_duration = (end_time - start_time).total_seconds()
        
        logger.info(f"🕐 测试时间: {start_time} 到 {end_time}")
        logger.info(f"⏱️  计划时长: {self.test_duration} 秒")
        logger.info(f"⏱️  实际时长: {actual_duration:.1f} 秒")
        logger.info(f"🎯 监控交易对: {', '.join(self.symbols)}")
        logger.info(f"🌐 代理使用: {'是' if self.production_metrics['test_config']['proxy_used'] else '否'}")
        logger.info("")
        
        # 连接性能
        conn_stats = self.production_metrics['connection_stats']
        success_rate = (conn_stats['successful_connections'] / max(conn_stats['total_connections'] or len(self.symbols), 1)) * 100
        
        logger.info("🔌 连接性能:")
        logger.info(f"  成功连接: {conn_stats['successful_connections']}")
        logger.info(f"  失败连接: {conn_stats['failed_connections']}")
        logger.info(f"  重连尝试: {conn_stats['reconnection_attempts']}")
        logger.info(f"  连接成功率: {success_rate:.1f}%")
        logger.info("")
        
        # 数据流性能
        data_stats = self.production_metrics['data_flow_stats']
        logger.info("📊 数据流性能:")
        logger.info(f"  总消息数: {data_stats['total_messages']:,}")
        logger.info(f"  平均频率: {data_stats['avg_messages_per_second']:.1f} 消息/秒")
        logger.info(f"  峰值频率: {data_stats['max_messages_per_second']:.1f} 消息/秒")
        logger.info(f"  数据总量: {data_stats['total_bytes_received']/1024/1024:.2f} MB")
        if data_stats['message_size_history']:
            avg_size = statistics.mean(data_stats['message_size_history'])
            logger.info(f"  平均消息大小: {avg_size:.0f} 字节")
        logger.info("")
        
        # 消息类型分析
        msg_stats = self.production_metrics['message_type_stats']
        total_valid = msg_stats['trade_messages'] + msg_stats['orderbook_messages'] + msg_stats['ticker_messages']
        
        logger.info("📋 消息类型分析:")
        logger.info(f"  交易消息: {msg_stats['trade_messages']:,} ({msg_stats['trade_messages']/max(total_valid,1)*100:.1f}%)")
        logger.info(f"  订单簿消息: {msg_stats['orderbook_messages']:,} ({msg_stats['orderbook_messages']/max(total_valid,1)*100:.1f}%)")
        logger.info(f"  Ticker消息: {msg_stats['ticker_messages']:,} ({msg_stats['ticker_messages']/max(total_valid,1)*100:.1f}%)")
        logger.info(f"  其他消息: {msg_stats['other_messages']:,}")
        logger.info(f"  无效消息: {msg_stats['invalid_messages']:,}")
        logger.info("")
        
        # 数据质量分析
        quality_stats = self.production_metrics['data_quality_stats']
        logger.info("🎯 数据质量分析:")
        logger.info(f"  重复消息: {quality_stats['duplicate_messages']}")
        logger.info(f"  乱序消息: {quality_stats['out_of_sequence_messages']}")
        logger.info(f"  数据中断: {quality_stats['data_gaps_detected']}")
        logger.info(f"  价格异常: {quality_stats['price_anomalies']}")
        logger.info(f"  平均延迟: {quality_stats['avg_latency_ms']:.1f} ms")
        logger.info(f"  最大延迟: {quality_stats['max_latency_ms']:.1f} ms")
        logger.info("")
        
        # 各交易对详细分析
        logger.info("💹 各交易对详细分析:")
        for symbol, stats in self.production_metrics['symbol_stats'].items():
            total_msg = stats['trades'] + stats['orderbooks'] + stats['tickers']
            msg_rate = total_msg / actual_duration if actual_duration > 0 else 0
            
            logger.info(f"  {symbol}:")
            logger.info(f"    总消息: {total_msg:,} ({msg_rate:.1f} msg/s)")
            logger.info(f"    交易: {stats['trades']:,}")
            logger.info(f"    订单簿: {stats['orderbooks']:,}")
            logger.info(f"    Ticker: {stats['tickers']:,}")
            logger.info(f"    最新价格: {stats['last_price']:.2f}")
            logger.info(f"    24h交易量: {stats['volume_24h']:.2f}")
            logger.info(f"    数据中断: {stats['data_gaps']}")
            
            if stats['price_changes']:
                avg_change = statistics.mean([abs(x) for x in stats['price_changes']])
                logger.info(f"    平均价格变化: {avg_change:.4f}")
        logger.info("")
        
        # 错误分析
        error_stats = self.production_metrics['error_stats']
        total_errors = (error_stats['websocket_errors'] + error_stats['json_parse_errors'] + 
                       error_stats['network_timeouts'] + error_stats['connection_drops'])
        
        logger.info("❌ 错误分析:")
        logger.info(f"  WebSocket错误: {error_stats['websocket_errors']}")
        logger.info(f"  JSON解析错误: {error_stats['json_parse_errors']}")
        logger.info(f"  网络超时: {error_stats['network_timeouts']}")
        logger.info(f"  连接中断: {error_stats['connection_drops']}")
        logger.info(f"  总错误数: {total_errors}")
        error_rate = (total_errors / max(data_stats['total_messages'], 1)) * 100
        logger.info(f"  错误率: {error_rate:.3f}%")
        logger.info("")
        
        # 整体评估
        logger.info("🏆 整体评估:")
        
        # 计算综合评分
        connection_score = min(success_rate, 100)
        data_quality_score = max(0, 100 - (quality_stats['data_gaps_detected'] * 2) - (quality_stats['price_anomalies'] * 1))
        error_score = max(0, 100 - (error_rate * 10))
        performance_score = min(data_stats['avg_messages_per_second'] / 10 * 100, 100)  # 假设10 msg/s为满分
        
        overall_score = (connection_score + data_quality_score + error_score + performance_score) / 4
        
        logger.info(f"  连接稳定性: {connection_score:.1f}/100")
        logger.info(f"  数据质量: {data_quality_score:.1f}/100")
        logger.info(f"  错误控制: {error_score:.1f}/100")
        logger.info(f"  性能表现: {performance_score:.1f}/100")
        logger.info(f"  综合评分: {overall_score:.1f}/100")
        
        if overall_score >= 90:
            logger.info("🎉 优秀！系统达到生产级别标准，可以处理真实高频交易数据！")
        elif overall_score >= 80:
            logger.info("✅ 良好！系统基本满足生产要求，建议优化部分性能指标")
        elif overall_score >= 70:
            logger.info("⚠️ 合格！系统可用但需要改进，特别关注错误处理和稳定性")
        else:
            logger.info("❌ 需要改进！系统距离生产级别还有差距，请重点优化")
        
        # 保存详细报告到文件
        await self._save_detailed_report()
    
    async def _save_detailed_report(self):
        """保存详细报告到文件"""
        try:
            timestamp = int(time.time())
            report_file = f"production_websocket_test_report_{timestamp}.json"
            
            with open(report_file, 'w', encoding='utf-8') as f:
                # 转换deque为list以便JSON序列化
                report_data = {}
                for key, value in self.production_metrics.items():
                    if isinstance(value, dict):
                        report_data[key] = {}
                        for k, v in value.items():
                            if isinstance(v, deque):
                                report_data[key][k] = list(v)
                            elif isinstance(v, defaultdict):
                                report_data[key][k] = dict(v)
                            else:
                                report_data[key][k] = v
                    else:
                        report_data[key] = value
                
                json.dump(report_data, f, indent=2, default=str)
            
            logger.info(f"✅ 详细报告已保存: {report_file}")
            
        except Exception as e:
            logger.error(f"❌ 保存报告失败: {e}")

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='MarketPrism 生产级别WebSocket数据流测试')
    parser.add_argument('--duration', type=int, default=180, help='测试持续时间(秒)')
    parser.add_argument('--symbols', default='BTC/USDT,ETH/USDT,BNB/USDT', help='交易对列表(逗号分隔)')
    
    args = parser.parse_args()
    symbols = [s.strip() for s in args.symbols.split(',')]
    
    # 应用代理配置
    AppConfig.detect_system_proxy()
    
    logger.info(f"🚀 启动生产级别WebSocket测试")
    logger.info(f"⏱️  测试时长: {args.duration} 秒")
    logger.info(f"📊 监控交易对: {symbols}")
    
    tester = ProductionWebSocketTester(args.duration, symbols)
    
    try:
        await tester.start_production_test()
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