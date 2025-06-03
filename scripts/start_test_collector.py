#!/usr/bin/env python3
"""
测试数据收集器启动脚本
启动一个简化的数据收集器来支持端到端测试

使用方法:
    python scripts/start_test_collector.py
"""

import asyncio
import json
import logging
import os
import sys
import signal
from datetime import datetime
from typing import Dict, Any
import aiohttp
from aiohttp import web
import nats

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

class TestDataCollector:
    """测试数据收集器"""
    
    def __init__(self):
        self.nats_client = None
        self.web_app = None
        self.web_runner = None
        self.web_site = None
        self.running = False
        
        # 模拟交易所数据
        self.mock_exchanges = ['binance', 'okx', 'deribit']
        self.mock_symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT']
        
        # 统计信息
        self.stats = {
            'start_time': None,
            'messages_sent': 0,
            'api_requests': 0,
            'errors': 0
        }
    
    async def setup_nats(self):
        """设置NATS连接"""
        try:
            nats_url = os.getenv('NATS_URL', 'nats://localhost:4222')
            self.nats_client = await nats.connect(nats_url)
            logger.info(f"✅ NATS连接成功: {nats_url}")
            return True
        except Exception as e:
            logger.error(f"❌ NATS连接失败: {e}")
            return False
    
    async def setup_web_api(self):
        """设置Web API服务"""
        self.web_app = web.Application()
        
        # 添加路由
        self.web_app.router.add_get('/health', self.health_handler)
        self.web_app.router.add_get('/stats', self.stats_handler)
        self.web_app.router.add_get('/api/v1/orderbook/{exchange}/{symbol}', self.orderbook_handler)
        self.web_app.router.add_get('/api/v1/trades/{exchange}/{symbol}', self.trades_handler)
        
        # 启动Web服务器
        self.web_runner = web.AppRunner(self.web_app)
        await self.web_runner.setup()
        
        port = int(os.getenv('COLLECTOR_PORT', '8081'))
        self.web_site = web.TCPSite(self.web_runner, 'localhost', port)
        await self.web_site.start()
        
        logger.info(f"✅ Web API服务启动: http://localhost:{port}")
        return True
    
    async def health_handler(self, request):
        """健康检查处理器"""
        self.stats['api_requests'] += 1
        
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'nats_connected': self.nats_client is not None and not self.nats_client.is_closed,
            'uptime_seconds': (datetime.now() - self.stats['start_time']).total_seconds() if self.stats['start_time'] else 0,
            'messages_sent': self.stats['messages_sent'],
            'api_requests': self.stats['api_requests'],
            'errors': self.stats['errors'],
            'proxy_config': {
                'use_proxy': NetworkConfig.USE_PROXY,
                'http_proxy': NetworkConfig.HTTP_PROXY,
                'https_proxy': NetworkConfig.HTTPS_PROXY
            }
        }
        
        return web.json_response(health_status)
    
    async def stats_handler(self, request):
        """统计信息处理器"""
        self.stats['api_requests'] += 1
        
        return web.json_response({
            'statistics': self.stats,
            'exchanges': self.mock_exchanges,
            'symbols': self.mock_symbols,
            'current_time': datetime.now().isoformat()
        })
    
    async def orderbook_handler(self, request):
        """订单簿数据处理器"""
        self.stats['api_requests'] += 1
        
        exchange = request.match_info['exchange']
        symbol = request.match_info['symbol']
        
        # 生成模拟订单簿数据
        mock_orderbook = {
            'exchange': exchange,
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'bids': [
                [50000.0, 1.0],
                [49990.0, 2.0],
                [49980.0, 1.5]
            ],
            'asks': [
                [50010.0, 1.0],
                [50020.0, 2.0],
                [50030.0, 1.5]
            ],
            'last_update_id': int(datetime.now().timestamp() * 1000)
        }
        
        return web.json_response(mock_orderbook)
    
    async def trades_handler(self, request):
        """交易数据处理器"""
        self.stats['api_requests'] += 1
        
        exchange = request.match_info['exchange']
        symbol = request.match_info['symbol']
        
        # 生成模拟交易数据
        mock_trades = [
            {
                'id': f"{exchange}_{int(datetime.now().timestamp())}_{i}",
                'exchange': exchange,
                'symbol': symbol,
                'price': 50000.0 + (i * 10),
                'quantity': 0.001 + (i * 0.0001),
                'side': 'buy' if i % 2 == 0 else 'sell',
                'timestamp': datetime.now().isoformat()
            }
            for i in range(10)
        ]
        
        return web.json_response({'trades': mock_trades})
    
    async def start_mock_data_publishing(self):
        """开始发布模拟数据"""
        logger.info("🚀 开始发布模拟数据到NATS...")
        
        counter = 0
        while self.running:
            try:
                for exchange in self.mock_exchanges:
                    for symbol in self.mock_symbols:
                        # 发布交易数据
                        trade_data = {
                            'type': 'trade',
                            'exchange': exchange,
                            'symbol': symbol,
                            'price': 50000.0 + (counter % 100),
                            'quantity': 0.001 + (counter % 10) * 0.0001,
                            'side': 'buy' if counter % 2 == 0 else 'sell',
                            'timestamp': int(datetime.now().timestamp() * 1000),
                            'trade_id': f"{exchange}_{counter}"
                        }
                        
                        subject = f"market.trades.{exchange}.{symbol.replace('/', '_')}"
                        await self.nats_client.publish(
                            subject,
                            json.dumps(trade_data).encode()
                        )
                        
                        self.stats['messages_sent'] += 1
                        
                        # 发布订单簿数据
                        orderbook_data = {
                            'type': 'orderbook',
                            'exchange': exchange,
                            'symbol': symbol,
                            'timestamp': int(datetime.now().timestamp() * 1000),
                            'bids': [[50000.0 - i, 1.0 + i * 0.1] for i in range(5)],
                            'asks': [[50010.0 + i, 1.0 + i * 0.1] for i in range(5)],
                            'last_update_id': counter
                        }
                        
                        subject = f"market.orderbook.{exchange}.{symbol.replace('/', '_')}"
                        await self.nats_client.publish(
                            subject,
                            json.dumps(orderbook_data).encode()
                        )
                        
                        self.stats['messages_sent'] += 1
                        counter += 1
                
                # 每2秒发布一轮数据
                await asyncio.sleep(2)
                
                if counter % 50 == 0:
                    logger.info(f"📊 已发布 {self.stats['messages_sent']} 条消息")
                    
            except Exception as e:
                logger.error(f"❌ 发布数据时出错: {e}")
                self.stats['errors'] += 1
                await asyncio.sleep(1)
    
    async def start(self):
        """启动收集器"""
        logger.info("🚀 启动测试数据收集器...")
        
        self.stats['start_time'] = datetime.now()
        self.running = True
        
        # 设置NATS连接
        if not await self.setup_nats():
            logger.error("❌ NATS设置失败，退出")
            return False
        
        # 设置Web API
        if not await self.setup_web_api():
            logger.error("❌ Web API设置失败，退出")
            return False
        
        # 开始发布模拟数据
        asyncio.create_task(self.start_mock_data_publishing())
        
        logger.info("✅ 测试数据收集器启动完成！")
        logger.info("   健康检查: http://localhost:8081/health")
        logger.info("   统计信息: http://localhost:8081/stats")
        logger.info("   代理配置: USE_PROXY={}, HTTP_PROXY={}".format(
            NetworkConfig.USE_PROXY, NetworkConfig.HTTP_PROXY
        ))
        
        return True
    
    async def stop(self):
        """停止收集器"""
        logger.info("🛑 停止测试数据收集器...")
        
        self.running = False
        
        if self.nats_client:
            await self.nats_client.close()
        
        if self.web_site:
            await self.web_site.stop()
        
        if self.web_runner:
            await self.web_runner.cleanup()
        
        logger.info("✅ 测试数据收集器已停止")

async def main():
    """主函数"""
    # 应用代理配置
    AppConfig.detect_system_proxy()
    
    collector = TestDataCollector()
    
    # 设置信号处理器用于优雅退出
    def signal_handler():
        logger.info("收到退出信号，正在关闭...")
        asyncio.create_task(collector.stop())
    
    # 注册信号处理器
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            asyncio.get_event_loop().add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows不支持信号处理器
            pass
    
    try:
        if await collector.start():
            logger.info("🎉 测试数据收集器运行中，按 Ctrl+C 退出")
            
            # 保持运行直到被中断
            while collector.running:
                await asyncio.sleep(1)
        else:
            logger.error("❌ 启动失败")
            return 1
            
    except KeyboardInterrupt:
        logger.info("收到键盘中断信号")
    except Exception as e:
        logger.error(f"运行时异常: {e}")
        return 1
    finally:
        await collector.stop()
    
    return 0

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"启动异常: {e}")
        sys.exit(1)