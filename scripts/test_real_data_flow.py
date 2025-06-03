#!/usr/bin/env python3
"""
真实数据流测试脚本
使用真实的交易所数据进行完整数据流测试

使用方法:
    # 先设置代理
    python scripts/setup_proxy_for_testing.py
    
    # 运行真实数据测试
    python scripts/test_real_data_flow.py
    
    # 或者指定特定交易所
    python scripts/test_real_data_flow.py --exchange binance --symbol BTC/USDT
"""

import asyncio
import json
import time
import logging
import os
import sys
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import aiohttp
import nats
import clickhouse_connect
import websockets

# 添加项目根目录到路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from config.app_config import AppConfig, NetworkConfig

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RealDataFlowTester:
    """真实数据流测试器"""
    
    def __init__(self, exchange: str = "binance", symbol: str = "BTC/USDT"):
        self.exchange = exchange.lower()
        self.symbol = symbol
        self.nats_client = None
        self.clickhouse_client = None
        self.test_start_time = None
        
        # 真实数据统计
        self.real_data_stats = {
            'trades_received': 0,
            'orderbooks_received': 0,
            'api_calls': 0,
            'errors': 0,
            'start_time': None
        }
        
        # 交易所WebSocket URLs
        self.ws_urls = {
            'binance': 'wss://stream.binance.com:9443/ws',
            'okx': 'wss://ws.okx.com:8443/ws/v5/public',
            'deribit': 'wss://www.deribit.com/ws/api/v2'
        }
        
        # 交易所REST URLs
        self.rest_urls = {
            'binance': 'https://api.binance.com',
            'okx': 'https://www.okx.com',
            'deribit': 'https://www.deribit.com'
        }
    
    async def setup(self):
        """初始化测试环境"""
        logger.info("🚀 初始化真实数据流测试环境...")
        
        try:
            # 连接NATS
            nats_url = os.getenv('NATS_URL', 'nats://localhost:4222')
            self.nats_client = await nats.connect(nats_url)
            logger.info(f"✅ NATS连接成功: {nats_url}")
            
            # 连接ClickHouse
            self.clickhouse_client = clickhouse_connect.get_client(
                host=os.getenv('CLICKHOUSE_HOST', 'localhost'),
                port=int(os.getenv('CLICKHOUSE_PORT', '8123')),
                username='default',
                password=''
            )
            logger.info("✅ ClickHouse连接成功")
            
            self.test_start_time = datetime.now()
            self.real_data_stats['start_time'] = self.test_start_time
            
        except Exception as e:
            logger.error(f"❌ 初始化失败: {e}")
            raise
    
    async def cleanup(self):
        """清理测试环境"""
        logger.info("🧹 清理测试环境...")
        
        if self.nats_client:
            await self.nats_client.close()
        
        if self.clickhouse_client:
            self.clickhouse_client.close()
    
    async def test_real_exchange_connection(self) -> bool:
        """测试真实交易所连接"""
        logger.info(f"🔍 测试真实交易所连接: {self.exchange}")
        
        try:
            # 检查代理配置
            proxy = None
            if NetworkConfig.USE_PROXY and NetworkConfig.HTTP_PROXY:
                proxy = NetworkConfig.HTTP_PROXY
                logger.info(f"使用代理: {proxy}")
            
            # 测试REST API连接
            rest_url = self.rest_urls.get(self.exchange)
            if not rest_url:
                logger.error(f"❌ 不支持的交易所: {self.exchange}")
                return False
            
            # 构建测试URL
            if self.exchange == 'binance':
                test_url = f"{rest_url}/api/v3/time"
            elif self.exchange == 'okx':
                test_url = f"{rest_url}/api/v5/public/time"
            elif self.exchange == 'deribit':
                test_url = f"{rest_url}/api/v2/public/get_time"
            else:
                logger.error(f"❌ 未知交易所: {self.exchange}")
                return False
            
            # 发送HTTP请求
            timeout = aiohttp.ClientTimeout(total=10)
            connector = None
            
            # 设置代理连接器
            if proxy and proxy.startswith('socks'):
                try:
                    import aiohttp_socks
                    connector = aiohttp_socks.ProxyConnector.from_url(proxy)
                except ImportError:
                    logger.warning("aiohttp_socks未安装，跳过SOCKS代理")
                    proxy = None
            
            async with aiohttp.ClientSession(
                timeout=timeout,
                connector=connector
            ) as session:
                async with session.get(test_url, proxy=proxy) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ {self.exchange}交易所REST API连接成功")
                        logger.info(f"   服务器时间: {data}")
                        self.real_data_stats['api_calls'] += 1
                        return True
                    else:
                        logger.error(f"❌ {self.exchange}交易所REST API连接失败: HTTP {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ 测试交易所连接失败: {e}")
            self.real_data_stats['errors'] += 1
            return False
    
    async def test_real_websocket_data(self, duration: int = 30) -> bool:
        """测试真实WebSocket数据流"""
        logger.info(f"🔍 测试真实WebSocket数据流: {self.exchange} {self.symbol} ({duration}秒)")
        
        try:
            ws_url = self.ws_urls.get(self.exchange)
            if not ws_url:
                logger.error(f"❌ 不支持的交易所WebSocket: {self.exchange}")
                return False
            
            # 准备订阅消息
            subscribe_msg = None
            if self.exchange == 'binance':
                # Binance订阅格式
                binance_symbol = self.symbol.replace('/', '').lower()  # BTC/USDT -> btcusdt
                subscribe_msg = {
                    "method": "SUBSCRIBE",
                    "params": [
                        f"{binance_symbol}@trade",
                        f"{binance_symbol}@depth@100ms"
                    ],
                    "id": 1
                }
            elif self.exchange == 'okx':
                # OKX订阅格式
                okx_symbol = self.symbol.replace('/', '-')  # BTC/USDT -> BTC-USDT
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [
                        {
                            "channel": "trades",
                            "instId": okx_symbol
                        },
                        {
                            "channel": "books",
                            "instId": okx_symbol
                        }
                    ]
                }
            elif self.exchange == 'deribit':
                # Deribit订阅格式
                deribit_symbol = self.symbol.replace('/', '-')  # BTC/USDT -> BTC-USDT
                subscribe_msg = {
                    "jsonrpc": "2.0",
                    "method": "public/subscribe",
                    "params": {
                        "channels": [
                            f"trades.{deribit_symbol}.raw",
                            f"book.{deribit_symbol}.none.1.100ms"
                        ]
                    },
                    "id": 1
                }
            
            if not subscribe_msg:
                logger.error(f"❌ 无法构建{self.exchange}的订阅消息")
                return False
            
            # 设置代理
            proxy = None
            if NetworkConfig.USE_PROXY and NetworkConfig.HTTP_PROXY:
                # WebSocket代理需要特殊处理
                if not NetworkConfig.HTTP_PROXY.startswith('socks'):
                    # HTTP代理可以直接使用
                    proxy_parts = NetworkConfig.HTTP_PROXY.replace('http://', '').split(':')
                    if len(proxy_parts) == 2:
                        proxy = f"http://{proxy_parts[0]}:{proxy_parts[1]}"
            
            # 连接WebSocket
            extra_headers = {}
            if proxy:
                logger.info(f"使用HTTP代理连接WebSocket: {proxy}")
                # 注意：websockets库的代理支持有限，可能需要其他解决方案
            
            logger.info(f"连接到 {ws_url}")
            async with websockets.connect(
                ws_url,
                extra_headers=extra_headers,
                ping_interval=20,
                ping_timeout=10
            ) as websocket:
                
                # 发送订阅消息
                await websocket.send(json.dumps(subscribe_msg))
                logger.info(f"✅ 已发送订阅消息到{self.exchange}")
                
                # 接收数据
                start_time = time.time()
                message_count = 0
                
                while time.time() - start_time < duration:
                    try:
                        # 设置接收超时
                        message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                        data = json.loads(message)
                        
                        # 发布到NATS
                        await self.publish_real_data_to_nats(data)
                        
                        message_count += 1
                        
                        # 分析消息类型
                        if self.is_trade_message(data):
                            self.real_data_stats['trades_received'] += 1
                        elif self.is_orderbook_message(data):
                            self.real_data_stats['orderbooks_received'] += 1
                        
                        # 定期输出统计
                        if message_count % 10 == 0:
                            logger.info(f"📊 已接收 {message_count} 条消息 "
                                      f"(交易: {self.real_data_stats['trades_received']}, "
                                      f"订单簿: {self.real_data_stats['orderbooks_received']})")
                    
                    except asyncio.TimeoutError:
                        logger.warning("⏰ 接收消息超时，继续等待...")
                        continue
                    except Exception as e:
                        logger.error(f"❌ 处理消息失败: {e}")
                        self.real_data_stats['errors'] += 1
                        continue
                
                logger.info(f"✅ WebSocket数据测试完成，共接收 {message_count} 条消息")
                return message_count > 0
                
        except Exception as e:
            logger.error(f"❌ WebSocket数据测试失败: {e}")
            self.real_data_stats['errors'] += 1
            return False
    
    def is_trade_message(self, data: Dict[str, Any]) -> bool:
        """判断是否为交易消息"""
        if self.exchange == 'binance':
            return 'stream' in data and '@trade' in data.get('stream', '')
        elif self.exchange == 'okx':
            return data.get('arg', {}).get('channel') == 'trades'
        elif self.exchange == 'deribit':
            return 'params' in data and 'trades.' in data.get('params', {}).get('channel', '')
        return False
    
    def is_orderbook_message(self, data: Dict[str, Any]) -> bool:
        """判断是否为订单簿消息"""
        if self.exchange == 'binance':
            return 'stream' in data and '@depth' in data.get('stream', '')
        elif self.exchange == 'okx':
            return data.get('arg', {}).get('channel') == 'books'
        elif self.exchange == 'deribit':
            return 'params' in data and 'book.' in data.get('params', {}).get('channel', '')
        return False
    
    async def publish_real_data_to_nats(self, data: Dict[str, Any]):
        """将真实数据发布到NATS"""
        try:
            # 构建NATS主题
            if self.is_trade_message(data):
                subject = f"market.trades.{self.exchange}.{self.symbol.replace('/', '_')}.real"
            elif self.is_orderbook_message(data):
                subject = f"market.orderbook.{self.exchange}.{self.symbol.replace('/', '_')}.real"
            else:
                subject = f"market.raw.{self.exchange}.{self.symbol.replace('/', '_')}.real"
            
            # 添加元数据
            enhanced_data = {
                'source': 'real_exchange',
                'exchange': self.exchange,
                'symbol': self.symbol,
                'timestamp': int(time.time() * 1000),
                'raw_data': data
            }
            
            # 发布到NATS
            await self.nats_client.publish(
                subject,
                json.dumps(enhanced_data).encode()
            )
            
        except Exception as e:
            logger.error(f"❌ 发布真实数据到NATS失败: {e}")
            self.real_data_stats['errors'] += 1
    
    async def run_complete_real_test(self, duration: int = 60) -> Dict[str, Any]:
        """运行完整的真实数据测试"""
        logger.info(f"🚀 开始真实数据流测试: {self.exchange} {self.symbol}")
        
        test_results = {
            'start_time': datetime.now(),
            'exchange': self.exchange,
            'symbol': self.symbol,
            'duration': duration,
            'tests': {},
            'real_data_stats': self.real_data_stats,
            'summary': {
                'total': 3,
                'passed': 0,
                'failed': 0
            }
        }
        
        try:
            await self.setup()
            
            # 测试1: 交易所连接
            logger.info(f"\n{'='*60}")
            logger.info("🔍 测试1: 真实交易所连接测试")
            try:
                result = await self.test_real_exchange_connection()
                test_results['tests']['exchange_connection'] = {
                    'status': 'PASSED' if result else 'FAILED',
                    'timestamp': datetime.now()
                }
                if result:
                    test_results['summary']['passed'] += 1
                else:
                    test_results['summary']['failed'] += 1
            except Exception as e:
                logger.error(f"❌ 交易所连接测试异常: {e}")
                test_results['tests']['exchange_connection'] = {
                    'status': 'ERROR',
                    'error': str(e),
                    'timestamp': datetime.now()
                }
                test_results['summary']['failed'] += 1
            
            # 测试2: 真实WebSocket数据流
            logger.info(f"\n{'='*60}")
            logger.info(f"🔍 测试2: 真实WebSocket数据流测试 ({duration}秒)")
            try:
                result = await self.test_real_websocket_data(duration)
                test_results['tests']['websocket_data'] = {
                    'status': 'PASSED' if result else 'FAILED',
                    'timestamp': datetime.now(),
                    'messages_received': self.real_data_stats['trades_received'] + self.real_data_stats['orderbooks_received']
                }
                if result:
                    test_results['summary']['passed'] += 1
                else:
                    test_results['summary']['failed'] += 1
            except Exception as e:
                logger.error(f"❌ WebSocket数据测试异常: {e}")
                test_results['tests']['websocket_data'] = {
                    'status': 'ERROR',
                    'error': str(e),
                    'timestamp': datetime.now()
                }
                test_results['summary']['failed'] += 1
            
            # 测试3: NATS数据验证
            logger.info(f"\n{'='*60}")
            logger.info("🔍 测试3: NATS真实数据验证")
            try:
                result = await self.verify_nats_real_data()
                test_results['tests']['nats_verification'] = {
                    'status': 'PASSED' if result else 'FAILED',
                    'timestamp': datetime.now()
                }
                if result:
                    test_results['summary']['passed'] += 1
                else:
                    test_results['summary']['failed'] += 1
            except Exception as e:
                logger.error(f"❌ NATS数据验证异常: {e}")
                test_results['tests']['nats_verification'] = {
                    'status': 'ERROR',
                    'error': str(e),
                    'timestamp': datetime.now()
                }
                test_results['summary']['failed'] += 1
            
            test_results['end_time'] = datetime.now()
            test_results['total_duration'] = (test_results['end_time'] - test_results['start_time']).total_seconds()
            
            # 输出测试结果
            self.print_real_test_summary(test_results)
            
            return test_results
            
        finally:
            await self.cleanup()
    
    async def verify_nats_real_data(self) -> bool:
        """验证NATS中的真实数据"""
        logger.info("🔍 验证NATS中的真实数据...")
        
        received_messages = []
        
        async def real_data_handler(msg):
            try:
                data = json.loads(msg.data.decode())
                if data.get('source') == 'real_exchange':
                    received_messages.append(data)
                    logger.debug(f"收到真实数据: {msg.subject}")
            except Exception as e:
                logger.warning(f"解析真实数据消息失败: {e}")
        
        try:
            # 订阅真实数据主题
            subject_pattern = f"market.*.{self.exchange}.{self.symbol.replace('/', '_')}.real"
            subscription = await self.nats_client.subscribe(
                subject_pattern,
                cb=real_data_handler
            )
            
            # 等待接收数据
            await asyncio.sleep(10)
            
            # 取消订阅
            await subscription.unsubscribe()
            
            if received_messages:
                logger.info(f"✅ NATS真实数据验证通过，收到 {len(received_messages)} 条真实消息")
                
                # 分析消息类型
                trade_count = sum(1 for msg in received_messages if 'trades' in msg.get('raw_data', {}))
                orderbook_count = len(received_messages) - trade_count
                
                logger.info(f"   交易消息: {trade_count}")
                logger.info(f"   订单簿消息: {orderbook_count}")
                return True
            else:
                logger.warning("⚠️ NATS真实数据验证失败，未收到真实消息")
                return False
                
        except Exception as e:
            logger.error(f"❌ NATS数据验证失败: {e}")
            return False
    
    def print_real_test_summary(self, results: Dict[str, Any]):
        """打印真实测试结果摘要"""
        logger.info(f"\n{'='*80}")
        logger.info("📊 真实数据流测试结果摘要")
        logger.info(f"{'='*80}")
        
        logger.info(f"交易所: {results['exchange']}")
        logger.info(f"交易对: {results['symbol']}")
        logger.info(f"测试时长: {results['duration']}秒")
        logger.info(f"开始时间: {results['start_time']}")
        logger.info(f"结束时间: {results['end_time']}")
        logger.info(f"总耗时: {results['total_duration']:.2f}秒")
        logger.info("")
        
        logger.info("真实数据统计:")
        stats = results['real_data_stats']
        logger.info(f"  交易消息: {stats['trades_received']}条")
        logger.info(f"  订单簿消息: {stats['orderbooks_received']}条")
        logger.info(f"  API调用: {stats['api_calls']}次")
        logger.info(f"  错误: {stats['errors']}次")
        logger.info("")
        
        logger.info("测试项目结果:")
        for test_name, test_result in results['tests'].items():
            status_icon = {
                'PASSED': '✅',
                'FAILED': '❌',
                'ERROR': '💥'
            }.get(test_result['status'], '❓')
            
            logger.info(f"  {status_icon} {test_name}: {test_result['status']}")
            if 'error' in test_result:
                logger.info(f"     错误: {test_result['error']}")
            if 'messages_received' in test_result:
                logger.info(f"     接收消息: {test_result['messages_received']}条")
        
        logger.info("")
        summary = results['summary']
        success_rate = (summary['passed'] / summary['total']) * 100
        
        logger.info(f"总结: {summary['passed']}/{summary['total']} 通过 ({success_rate:.1f}%)")
        
        if success_rate >= 80:
            logger.info("🎉 真实数据流测试通过，系统与真实交易所集成良好！")
        elif success_rate >= 60:
            logger.info("⚠️ 真实数据流测试部分通过，建议检查失败项目")
        else:
            logger.info("❌ 真实数据流测试大部分失败，需要检查网络和代理配置")

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='MarketPrism 真实数据流测试')
    parser.add_argument('--exchange', default='binance', help='交易所名称 (binance/okx/deribit)')
    parser.add_argument('--symbol', default='BTC/USDT', help='交易对')
    parser.add_argument('--duration', type=int, default=30, help='测试持续时间(秒)')
    
    args = parser.parse_args()
    
    # 应用代理配置
    AppConfig.detect_system_proxy()
    
    tester = RealDataFlowTester(args.exchange, args.symbol)
    results = await tester.run_complete_real_test(args.duration)
    
    # 根据测试结果设置退出码
    success_rate = (results['summary']['passed'] / results['summary']['total']) * 100
    exit_code = 0 if success_rate >= 60 else 1
    
    return exit_code

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("测试被用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"测试执行异常: {e}")
        sys.exit(1)