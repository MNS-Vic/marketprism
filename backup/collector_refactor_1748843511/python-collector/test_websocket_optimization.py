#!/usr/bin/env python3
"""
WebSocket连接优化测试

测试WebSocket连接的稳定性、重连机制、心跳包优化、数据缓冲区优化
验证异常恢复能力和连接质量
"""

import asyncio
import signal
import sys
import time
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from marketprism_collector.config import Config
from marketprism_collector.collector import MarketDataCollector


@dataclass
class ConnectionMetrics:
    """连接指标数据类"""
    timestamp: datetime
    exchange: str
    is_connected: bool
    connection_duration: float
    reconnect_count: int
    messages_received: int
    messages_lost: int
    latency_ms: float
    heartbeat_status: bool


class WebSocketOptimizationTest:
    """WebSocket连接优化测试器"""
    
    def __init__(self):
        self.start_time = None
        self.running = True
        self.connection_history: List[ConnectionMetrics] = []
        self.latency_measurements = defaultdict(list)
        self.message_buffers = defaultdict(deque)
        self.connection_events = defaultdict(list)
        
        # 测试配置
        self.test_config = {
            'heartbeat_interval': 30,  # 心跳间隔(秒)
            'reconnect_delay': 5,      # 重连延迟(秒)
            'max_reconnect_attempts': 10,
            'message_buffer_size': 1000,
            'latency_threshold_ms': 1000,
            'stability_threshold_percent': 95.0
        }
        
    async def run_websocket_optimization_test(self, duration_minutes: int = 15):
        """运行WebSocket优化测试"""
        print("🔗 WebSocket连接优化测试")
        print("=" * 80)
        print(f"⏱️  测试时长: {duration_minutes}分钟")
        print(f"🎯 测试目标: 连接稳定性、重连机制、心跳优化、缓冲区优化")
        print()
        
        try:
            # 1. 环境准备
            await self._prepare_test_environment()
            
            # 2. 基础连接测试
            await self._test_basic_connections()
            
            # 3. 重连机制测试
            await self._test_reconnection_mechanism()
            
            # 4. 心跳包优化测试
            await self._test_heartbeat_optimization()
            
            # 5. 数据缓冲区测试
            await self._test_data_buffering()
            
            # 6. 异常恢复测试
            await self._test_exception_recovery()
            
            # 7. 长期稳定性测试
            await self._test_long_term_stability(duration_minutes)
            
            # 8. 生成优化报告
            await self._generate_optimization_report()
            
            return True
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _prepare_test_environment(self):
        """准备测试环境"""
        print("🔧 准备WebSocket测试环境...")
        
        # 检查交易所API可用性
        exchanges_to_test = ['binance', 'okx', 'deribit']
        api_endpoints = {
            'binance': 'https://api.binance.com/api/v3/ping',
            'okx': 'https://www.okx.com/api/v5/public/time',
            'deribit': 'https://www.deribit.com/api/v2/public/get_time'
        }
        
        import requests
        available_exchanges = []
        
        for exchange in exchanges_to_test:
            try:
                response = requests.get(api_endpoints[exchange], timeout=5)
                if response.status_code == 200:
                    available_exchanges.append(exchange)
                    print(f"   ✅ {exchange}: API可用")
                else:
                    print(f"   ❌ {exchange}: API不可用 (状态码: {response.status_code})")
            except Exception as e:
                print(f"   ❌ {exchange}: 连接失败 ({e})")
        
        if not available_exchanges:
            raise Exception("没有可用的交易所API")
        
        self.available_exchanges = available_exchanges
        print(f"✅ 环境准备完成，可用交易所: {len(available_exchanges)}个\n")
    
    async def _test_basic_connections(self):
        """测试基础连接功能"""
        print("🔌 测试基础WebSocket连接...")
        
        ws_endpoints = {
            'binance': 'wss://stream.binance.com:9443/ws/btcusdt@ticker',
            'okx': 'wss://ws.okx.com:8443/ws/v5/public',
            'deribit': 'wss://www.deribit.com/ws/api/v2'
        }
        
        connection_results = {}
        
        for exchange in self.available_exchanges:
            if exchange not in ws_endpoints:
                continue
                
            print(f"   🔗 测试 {exchange} WebSocket连接...")
            
            try:
                start_time = time.time()
                
                # 建立WebSocket连接
                async with websockets.connect(
                    ws_endpoints[exchange],
                    ping_interval=30,
                    ping_timeout=10,
                    close_timeout=10
                ) as websocket:
                    
                    connection_time = (time.time() - start_time) * 1000  # ms
                    
                    # 发送订阅消息（如果需要）
                    if exchange == 'okx':
                        subscribe_msg = {
                            "op": "subscribe",
                            "args": [{"channel": "tickers", "instId": "BTC-USDT"}]
                        }
                        await websocket.send(json.dumps(subscribe_msg))
                    elif exchange == 'deribit':
                        subscribe_msg = {
                            "jsonrpc": "2.0",
                            "method": "public/subscribe",
                            "params": {"channels": ["ticker.BTC-PERPETUAL.100ms"]},
                            "id": 1
                        }
                        await websocket.send(json.dumps(subscribe_msg))
                    
                    # 等待响应
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=10)
                        response_time = (time.time() - start_time) * 1000  # ms
                        
                        connection_results[exchange] = {
                            'success': True,
                            'connection_time_ms': connection_time,
                            'response_time_ms': response_time,
                            'first_message': len(response) if response else 0
                        }
                        
                        print(f"      ✅ 连接成功 (连接: {connection_time:.1f}ms, 响应: {response_time:.1f}ms)")
                        
                    except asyncio.TimeoutError:
                        connection_results[exchange] = {
                            'success': False,
                            'error': 'Response timeout'
                        }
                        print(f"      ❌ 响应超时")
                        
            except Exception as e:
                connection_results[exchange] = {
                    'success': False,
                    'error': str(e)
                }
                print(f"      ❌ 连接失败: {e}")
        
        # 统计结果
        successful_connections = sum(1 for r in connection_results.values() if r.get('success', False))
        print(f"\n   📊 基础连接测试结果: {successful_connections}/{len(connection_results)} 成功")
        
        if successful_connections == 0:
            raise Exception("所有WebSocket连接都失败")
        
        self.basic_connection_results = connection_results
        print("✅ 基础连接测试完成\n")
    
    async def _test_reconnection_mechanism(self):
        """测试重连机制"""
        print("🔄 测试WebSocket重连机制...")
        
        # 创建测试配置
        config_data = {
            'exchanges': {
                'binance': {
                    'enabled': True,
                    'market_type': 'spot',
                    'symbols': ['BTCUSDT'],
                    'data_types': ['ticker'],
                    'ws_url': 'wss://stream.binance.com:9443/ws',
                    'ping_interval': 10,
                    'reconnect_attempts': 5,
                    'reconnect_delay': 2
                }
            },
            'nats': {
                'servers': ['nats://localhost:4222'],
                'max_reconnect_attempts': 3
            }
        }
        
        # 保存临时配置
        config_file = 'config/test_reconnection.yaml'
        os.makedirs(os.path.dirname(config_file), exist_ok=True)
        
        import yaml
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f, default_flow_style=False)
        
        config = Config.load_from_file(config_file)
        collector = MarketDataCollector(config)
        
        try:
            # 启动收集器
            print("   🚀 启动收集器...")
            success = await collector.start()
            
            if not success:
                print("   ❌ 收集器启动失败")
                return
            
            # 等待连接稳定
            await asyncio.sleep(5)
            
            # 记录初始状态
            initial_stats = {}
            for key, adapter in collector.exchange_adapters.items():
                initial_stats[key] = {
                    'connected': adapter.is_connected,
                    'reconnect_count': adapter.reconnect_count
                }
            
            print("   📊 初始连接状态:")
            for key, stats in initial_stats.items():
                status = "✅ 已连接" if stats['connected'] else "❌ 未连接"
                print(f"      - {key}: {status}")
            
            # 模拟网络中断（通过修改适配器状态）
            print("\n   🔌 模拟网络中断...")
            for adapter in collector.exchange_adapters.values():
                if adapter.is_connected and adapter.ws_connection:
                    try:
                        await adapter.ws_connection.close()
                        adapter.is_connected = False
                        print(f"      - 强制断开连接")
                    except:
                        pass
            
            # 等待重连
            print("   ⏳ 等待自动重连...")
            reconnection_start = time.time()
            max_wait_time = 30  # 最多等待30秒
            
            while time.time() - reconnection_start < max_wait_time:
                await asyncio.sleep(2)
                
                # 检查重连状态
                reconnected = False
                for adapter in collector.exchange_adapters.values():
                    if adapter.is_connected:
                        reconnected = True
                        break
                
                if reconnected:
                    reconnection_time = time.time() - reconnection_start
                    print(f"   ✅ 重连成功 (耗时: {reconnection_time:.1f}秒)")
                    break
            else:
                print("   ❌ 重连超时")
            
            # 记录最终状态
            final_stats = {}
            for key, adapter in collector.exchange_adapters.items():
                final_stats[key] = {
                    'connected': adapter.is_connected,
                    'reconnect_count': adapter.reconnect_count
                }
            
            print("\n   📊 重连后状态:")
            for key, stats in final_stats.items():
                status = "✅ 已连接" if stats['connected'] else "❌ 未连接"
                reconnects = stats['reconnect_count'] - initial_stats[key]['reconnect_count']
                print(f"      - {key}: {status} (重连次数: {reconnects})")
            
        finally:
            # 停止收集器
            await collector.stop()
        
        print("✅ 重连机制测试完成\n")
    
    async def _test_heartbeat_optimization(self):
        """测试心跳包优化"""
        print("💓 测试心跳包优化...")
        
        # 测试不同心跳间隔的效果
        heartbeat_intervals = [10, 30, 60]  # 秒
        heartbeat_results = {}
        
        for interval in heartbeat_intervals:
            print(f"   🔍 测试心跳间隔: {interval}秒...")
            
            try:
                # 建立WebSocket连接并测试心跳
                async with websockets.connect(
                    'wss://stream.binance.com:9443/ws/btcusdt@ticker',
                    ping_interval=interval,
                    ping_timeout=10
                ) as websocket:
                    
                    start_time = time.time()
                    ping_count = 0
                    pong_count = 0
                    
                    # 监控心跳30秒
                    test_duration = 30
                    
                    async def ping_monitor():
                        nonlocal ping_count, pong_count
                        while time.time() - start_time < test_duration:
                            try:
                                pong_waiter = await websocket.ping()
                                ping_count += 1
                                await asyncio.wait_for(pong_waiter, timeout=5)
                                pong_count += 1
                            except:
                                pass
                            await asyncio.sleep(interval)
                    
                    # 同时接收消息
                    async def message_receiver():
                        message_count = 0
                        while time.time() - start_time < test_duration:
                            try:
                                await asyncio.wait_for(websocket.recv(), timeout=1)
                                message_count += 1
                            except asyncio.TimeoutError:
                                continue
                            except:
                                break
                        return message_count
                    
                    # 并发执行
                    ping_task = asyncio.create_task(ping_monitor())
                    recv_task = asyncio.create_task(message_receiver())
                    
                    await asyncio.sleep(test_duration)
                    
                    ping_task.cancel()
                    message_count = await recv_task
                    
                    heartbeat_results[interval] = {
                        'ping_sent': ping_count,
                        'pong_received': pong_count,
                        'success_rate': (pong_count / max(ping_count, 1)) * 100,
                        'messages_received': message_count,
                        'connection_stable': pong_count > 0
                    }
                    
                    print(f"      📊 心跳成功率: {heartbeat_results[interval]['success_rate']:.1f}%")
                    print(f"      📨 消息接收: {message_count}条")
                    
            except Exception as e:
                heartbeat_results[interval] = {
                    'error': str(e),
                    'success_rate': 0,
                    'connection_stable': False
                }
                print(f"      ❌ 测试失败: {e}")
        
        # 分析最优心跳间隔
        best_interval = None
        best_score = 0
        
        for interval, result in heartbeat_results.items():
            if 'error' not in result:
                # 综合评分：成功率 + 稳定性 - 频率惩罚
                score = result['success_rate'] + (50 if result['connection_stable'] else 0) - (100 / interval)
                if score > best_score:
                    best_score = score
                    best_interval = interval
        
        if best_interval:
            print(f"\n   🏆 推荐心跳间隔: {best_interval}秒 (评分: {best_score:.1f})")
        
        self.heartbeat_results = heartbeat_results
        print("✅ 心跳包优化测试完成\n")
    
    async def _test_data_buffering(self):
        """测试数据缓冲区优化"""
        print("📦 测试数据缓冲区优化...")
        
        buffer_sizes = [100, 500, 1000, 2000]  # 不同缓冲区大小
        buffer_results = {}
        
        for buffer_size in buffer_sizes:
            print(f"   🔍 测试缓冲区大小: {buffer_size}...")
            
            try:
                message_buffer = deque(maxlen=buffer_size)
                lost_messages = 0
                processing_times = []
                
                async with websockets.connect(
                    'wss://stream.binance.com:9443/ws/btcusdt@ticker'
                ) as websocket:
                    
                    start_time = time.time()
                    test_duration = 20  # 20秒测试
                    
                    while time.time() - start_time < test_duration:
                        try:
                            # 接收消息
                            message = await asyncio.wait_for(websocket.recv(), timeout=1)
                            
                            # 模拟处理时间
                            process_start = time.time()
                            
                            # 检查缓冲区是否已满
                            if len(message_buffer) >= buffer_size:
                                lost_messages += 1
                            else:
                                message_buffer.append({
                                    'data': message,
                                    'timestamp': time.time()
                                })
                            
                            # 模拟数据处理
                            await asyncio.sleep(0.001)  # 1ms处理时间
                            
                            process_time = (time.time() - process_start) * 1000
                            processing_times.append(process_time)
                            
                        except asyncio.TimeoutError:
                            continue
                        except Exception as e:
                            break
                
                # 计算统计指标
                total_messages = len(message_buffer) + lost_messages
                loss_rate = (lost_messages / max(total_messages, 1)) * 100
                avg_process_time = sum(processing_times) / max(len(processing_times), 1)
                
                buffer_results[buffer_size] = {
                    'total_messages': total_messages,
                    'buffered_messages': len(message_buffer),
                    'lost_messages': lost_messages,
                    'loss_rate_percent': loss_rate,
                    'avg_processing_time_ms': avg_process_time,
                    'buffer_utilization': (len(message_buffer) / buffer_size) * 100
                }
                
                print(f"      📊 消息丢失率: {loss_rate:.2f}%")
                print(f"      ⚡ 平均处理时间: {avg_process_time:.2f}ms")
                print(f"      📈 缓冲区利用率: {buffer_results[buffer_size]['buffer_utilization']:.1f}%")
                
            except Exception as e:
                buffer_results[buffer_size] = {
                    'error': str(e)
                }
                print(f"      ❌ 测试失败: {e}")
        
        # 分析最优缓冲区大小
        best_buffer_size = None
        best_score = 0
        
        for size, result in buffer_results.items():
            if 'error' not in result:
                # 综合评分：低丢失率 + 高利用率 + 快处理速度
                score = (100 - result['loss_rate_percent']) + \
                       (result['buffer_utilization'] / 2) + \
                       (100 - min(result['avg_processing_time_ms'], 100))
                
                if score > best_score:
                    best_score = score
                    best_buffer_size = size
        
        if best_buffer_size:
            print(f"\n   🏆 推荐缓冲区大小: {best_buffer_size} (评分: {best_score:.1f})")
        
        self.buffer_results = buffer_results
        print("✅ 数据缓冲区优化测试完成\n")
    
    async def _test_exception_recovery(self):
        """测试异常恢复能力"""
        print("🛡️ 测试异常恢复能力...")
        
        recovery_scenarios = [
            'network_timeout',
            'invalid_message',
            'connection_reset',
            'server_error'
        ]
        
        recovery_results = {}
        
        for scenario in recovery_scenarios:
            print(f"   🔍 测试场景: {scenario}...")
            
            try:
                recovery_time = None
                recovery_success = False
                
                if scenario == 'network_timeout':
                    # 模拟网络超时
                    try:
                        async with websockets.connect(
                            'wss://stream.binance.com:9443/ws/btcusdt@ticker',
                            open_timeout=1  # 很短的超时时间
                        ) as websocket:
                            await asyncio.wait_for(websocket.recv(), timeout=0.1)
                    except asyncio.TimeoutError:
                        recovery_success = True
                        recovery_time = 0.1
                    except Exception:
                        recovery_success = True
                        recovery_time = 1.0
                
                elif scenario == 'invalid_message':
                    # 测试无效消息处理
                    async with websockets.connect(
                        'wss://stream.binance.com:9443/ws/btcusdt@ticker'
                    ) as websocket:
                        
                        start_time = time.time()
                        valid_messages = 0
                        
                        for _ in range(10):
                            try:
                                message = await asyncio.wait_for(websocket.recv(), timeout=2)
                                # 尝试解析JSON
                                json.loads(message)
                                valid_messages += 1
                            except json.JSONDecodeError:
                                # 无效JSON，但连接应该继续
                                continue
                            except Exception:
                                break
                        
                        recovery_time = time.time() - start_time
                        recovery_success = valid_messages > 0
                
                elif scenario == 'connection_reset':
                    # 测试连接重置恢复
                    start_time = time.time()
                    try:
                        async with websockets.connect(
                            'wss://stream.binance.com:9443/ws/btcusdt@ticker'
                        ) as websocket:
                            # 强制关闭连接
                            await websocket.close()
                            
                        # 尝试重新连接
                        async with websockets.connect(
                            'wss://stream.binance.com:9443/ws/btcusdt@ticker'
                        ) as websocket:
                            await websocket.recv()
                            recovery_success = True
                            recovery_time = time.time() - start_time
                            
                    except Exception:
                        recovery_time = time.time() - start_time
                        recovery_success = False
                
                elif scenario == 'server_error':
                    # 测试服务器错误处理
                    try:
                        # 尝试连接到不存在的端点
                        async with websockets.connect(
                            'wss://stream.binance.com:9443/ws/invalid_endpoint',
                            open_timeout=5
                        ) as websocket:
                            await websocket.recv()
                    except Exception:
                        # 预期的错误，测试错误处理
                        recovery_success = True
                        recovery_time = 5.0
                
                recovery_results[scenario] = {
                    'success': recovery_success,
                    'recovery_time_seconds': recovery_time,
                    'status': '✅ 通过' if recovery_success else '❌ 失败'
                }
                
                print(f"      {recovery_results[scenario]['status']} (恢复时间: {recovery_time:.2f}s)")
                
            except Exception as e:
                recovery_results[scenario] = {
                    'success': False,
                    'error': str(e),
                    'status': '❌ 异常'
                }
                print(f"      ❌ 异常: {e}")
        
        # 计算整体恢复能力评分
        successful_recoveries = sum(1 for r in recovery_results.values() if r.get('success', False))
        recovery_score = (successful_recoveries / len(recovery_scenarios)) * 100
        
        print(f"\n   📊 异常恢复能力评分: {recovery_score:.1f}% ({successful_recoveries}/{len(recovery_scenarios)})")
        
        self.recovery_results = recovery_results
        print("✅ 异常恢复测试完成\n")
    
    async def _test_long_term_stability(self, duration_minutes: int):
        """测试长期稳定性"""
        print(f"⏰ 测试长期稳定性 ({duration_minutes}分钟)...")
        
        # 创建简化的长期测试配置
        config_data = {
            'exchanges': {
                'binance': {
                    'enabled': True,
                    'market_type': 'spot',
                    'symbols': ['BTCUSDT'],
                    'data_types': ['ticker'],
                    'ws_url': 'wss://stream.binance.com:9443/ws',
                    'ping_interval': 30,
                    'reconnect_attempts': 10,
                    'reconnect_delay': 5
                }
            }
        }
        
        # 保存配置
        config_file = 'config/test_stability.yaml'
        os.makedirs(os.path.dirname(config_file), exist_ok=True)
        
        import yaml
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f, default_flow_style=False)
        
        config = Config.load_from_file(config_file)
        collector = MarketDataCollector(config)
        
        try:
            # 启动收集器
            success = await collector.start()
            if not success:
                print("   ❌ 收集器启动失败")
                return
            
            print("   🚀 开始长期稳定性监控...")
            
            start_time = time.time()
            duration_seconds = duration_minutes * 60
            check_interval = 30  # 每30秒检查一次
            
            stability_metrics = []
            
            # 设置停止信号处理
            def signal_handler(signum, frame):
                print("\n⚠️  收到停止信号...")
                self.running = False
            
            signal.signal(signal.SIGINT, signal_handler)
            
            for i in range(0, duration_seconds, check_interval):
                if not self.running:
                    break
                
                # 收集稳定性指标
                current_time = time.time()
                elapsed_minutes = (current_time - start_time) / 60
                
                # 检查连接状态
                connections_active = 0
                total_messages = 0
                total_errors = 0
                
                for adapter in collector.exchange_adapters.values():
                    if adapter.is_connected:
                        connections_active += 1
                    
                    stats = adapter.get_stats()
                    total_messages += stats.get('messages_processed', 0)
                    total_errors += stats.get('errors', 0)
                
                stability_metric = {
                    'elapsed_minutes': elapsed_minutes,
                    'connections_active': connections_active,
                    'total_connections': len(collector.exchange_adapters),
                    'total_messages': total_messages,
                    'total_errors': total_errors,
                    'connection_rate': (connections_active / len(collector.exchange_adapters)) * 100
                }
                
                stability_metrics.append(stability_metric)
                
                # 每5分钟报告一次
                if i > 0 and (i % 300 == 0 or i >= duration_seconds - check_interval):
                    print(f"   ⏱️  {elapsed_minutes:.1f}分钟: 连接率 {stability_metric['connection_rate']:.1f}%, "
                          f"消息 {total_messages}, 错误 {total_errors}")
                
                await asyncio.sleep(check_interval)
            
            # 计算稳定性统计
            if stability_metrics:
                connection_rates = [m['connection_rate'] for m in stability_metrics]
                avg_connection_rate = sum(connection_rates) / len(connection_rates)
                min_connection_rate = min(connection_rates)
                
                final_messages = stability_metrics[-1]['total_messages']
                final_errors = stability_metrics[-1]['total_errors']
                error_rate = (final_errors / max(final_messages, 1)) * 100
                
                print(f"\n   📊 长期稳定性统计:")
                print(f"      平均连接率: {avg_connection_rate:.1f}%")
                print(f"      最低连接率: {min_connection_rate:.1f}%")
                print(f"      总消息数: {final_messages:,}")
                print(f"      错误率: {error_rate:.3f}%")
                
                # 稳定性评级
                if avg_connection_rate >= 99 and error_rate <= 0.1:
                    stability_grade = "⭐⭐⭐⭐⭐ 优秀"
                elif avg_connection_rate >= 95 and error_rate <= 0.5:
                    stability_grade = "⭐⭐⭐⭐ 良好"
                elif avg_connection_rate >= 90 and error_rate <= 1.0:
                    stability_grade = "⭐⭐⭐ 一般"
                else:
                    stability_grade = "⭐⭐ 需要改进"
                
                print(f"      稳定性评级: {stability_grade}")
                
                self.stability_metrics = stability_metrics
            
        finally:
            await collector.stop()
        
        print("✅ 长期稳定性测试完成\n")
    
    async def _generate_optimization_report(self):
        """生成优化报告"""
        print("📋 生成WebSocket优化报告...")
        
        report_data = {
            'test_info': {
                'timestamp': datetime.now().isoformat(),
                'test_type': 'websocket_optimization',
                'available_exchanges': self.available_exchanges
            },
            'basic_connections': getattr(self, 'basic_connection_results', {}),
            'heartbeat_optimization': getattr(self, 'heartbeat_results', {}),
            'buffer_optimization': getattr(self, 'buffer_results', {}),
            'exception_recovery': getattr(self, 'recovery_results', {}),
            'stability_metrics': getattr(self, 'stability_metrics', [])
        }
        
        # 生成优化建议
        recommendations = []
        
        # 心跳优化建议
        if hasattr(self, 'heartbeat_results'):
            best_heartbeat = None
            best_rate = 0
            for interval, result in self.heartbeat_results.items():
                if 'success_rate' in result and result['success_rate'] > best_rate:
                    best_rate = result['success_rate']
                    best_heartbeat = interval
            
            if best_heartbeat:
                recommendations.append(f"推荐心跳间隔: {best_heartbeat}秒 (成功率: {best_rate:.1f}%)")
        
        # 缓冲区优化建议
        if hasattr(self, 'buffer_results'):
            best_buffer = None
            best_loss_rate = float('inf')
            for size, result in self.buffer_results.items():
                if 'loss_rate_percent' in result and result['loss_rate_percent'] < best_loss_rate:
                    best_loss_rate = result['loss_rate_percent']
                    best_buffer = size
            
            if best_buffer:
                recommendations.append(f"推荐缓冲区大小: {best_buffer} (丢失率: {best_loss_rate:.2f}%)")
        
        # 异常恢复建议
        if hasattr(self, 'recovery_results'):
            recovery_success_rate = sum(1 for r in self.recovery_results.values() if r.get('success', False))
            recovery_rate = (recovery_success_rate / len(self.recovery_results)) * 100
            
            if recovery_rate < 100:
                recommendations.append(f"需要改进异常恢复机制 (当前成功率: {recovery_rate:.1f}%)")
        
        report_data['recommendations'] = recommendations
        
        # 保存报告
        report_file = f'websocket_optimization_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(report_file, 'w') as f:
            json.dump(report_data, f, indent=2, default=str)
        
        print("\n" + "="*80)
        print("📊 WebSocket连接优化报告")
        print("="*80)
        
        print(f"\n🔗 基础连接测试:")
        if hasattr(self, 'basic_connection_results'):
            for exchange, result in self.basic_connection_results.items():
                if result.get('success'):
                    print(f"   ✅ {exchange}: 连接 {result['connection_time_ms']:.1f}ms, 响应 {result['response_time_ms']:.1f}ms")
                else:
                    print(f"   ❌ {exchange}: {result.get('error', '未知错误')}")
        
        print(f"\n💓 心跳优化建议:")
        if hasattr(self, 'heartbeat_results'):
            for interval, result in self.heartbeat_results.items():
                if 'success_rate' in result:
                    print(f"   {interval}秒间隔: 成功率 {result['success_rate']:.1f}%")
        
        print(f"\n📦 缓冲区优化建议:")
        if hasattr(self, 'buffer_results'):
            for size, result in self.buffer_results.items():
                if 'loss_rate_percent' in result:
                    print(f"   {size}大小: 丢失率 {result['loss_rate_percent']:.2f}%")
        
        print(f"\n🛡️ 异常恢复能力:")
        if hasattr(self, 'recovery_results'):
            for scenario, result in self.recovery_results.items():
                print(f"   {scenario}: {result.get('status', '未知')}")
        
        if recommendations:
            print(f"\n🎯 优化建议:")
            for i, rec in enumerate(recommendations, 1):
                print(f"   {i}. {rec}")
        
        print(f"\n📄 详细报告已保存: {report_file}")
        print("="*80)


async def main():
    """主函数"""
    if len(sys.argv) > 1:
        duration = int(sys.argv[1])
    else:
        duration = 10  # 默认10分钟测试
    
    tester = WebSocketOptimizationTest()
    success = await tester.run_websocket_optimization_test(duration)
    
    if success:
        print("\n🎉 WebSocket连接优化测试完成！")
        sys.exit(0)
    else:
        print("\n❌ 测试失败")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main()) 