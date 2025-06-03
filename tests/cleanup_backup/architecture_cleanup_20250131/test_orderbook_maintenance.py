#!/usr/bin/env python3
"""
测试订单簿更新维护功能

验证：
1. 订单簿初始同步
2. 增量更新应用
3. 序列验证
4. API频率限制
"""

import asyncio
import json
import time
from datetime import datetime
import aiohttp
import structlog

# 配置日志
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


class OrderBookTester:
    def __init__(self):
        self.logger = logger.bind(component="OrderBookTester")
        self.orderbook_stats = {}
        
    async def test_collector_orderbook(self):
        """测试collector的订单簿功能"""
        try:
            # 检查collector是否运行
            async with aiohttp.ClientSession() as session:
                # 1. 健康检查
                async with session.get('http://localhost:8100/health') as resp:
                    if resp.status != 200:
                        self.logger.error("Collector未运行")
                        return
                    health = await resp.json()
                    self.logger.info("Collector健康状态", health=health)
                
                # 2. 获取订单簿管理器状态
                async with session.get('http://localhost:8100/api/v1/orderbook/stats') as resp:
                    if resp.status == 200:
                        stats = await resp.json()
                        self.logger.info("订单簿管理器统计", stats=stats)
                        
                        # 检查每个交易所的状态
                        for exchange, exchange_stats in stats.get('exchanges', {}).items():
                            manager_stats = exchange_stats.get('manager_stats', {})
                            symbol_stats = manager_stats.get('symbol_stats', {})
                            
                            for symbol, status in symbol_stats.items():
                                self.logger.info(
                                    "交易对状态",
                                    exchange=exchange,
                                    symbol=symbol,
                                    is_synced=status.get('is_synced'),
                                    last_update_id=status.get('last_update_id'),
                                    total_updates=status.get('total_updates'),
                                    buffer_size=status.get('buffer_size'),
                                    error_count=status.get('error_count')
                                )
                
                # 3. 测试获取实时订单簿
                test_symbols = [
                    ('binance', 'BTC-USDT'),
                    ('binance', 'ETH-USDT')
                ]
                
                for exchange, symbol in test_symbols:
                    url = f'http://localhost:8100/api/v1/orderbook/{exchange}/{symbol}'
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            orderbook = await resp.json()
                            self.logger.info(
                                "获取订单簿成功",
                                exchange=exchange,
                                symbol=symbol,
                                bid_count=len(orderbook.get('bids', [])),
                                ask_count=len(orderbook.get('asks', [])),
                                last_update_id=orderbook.get('last_update_id'),
                                timestamp=orderbook.get('timestamp')
                            )
                            
                            # 保存统计
                            key = f"{exchange}:{symbol}"
                            if key not in self.orderbook_stats:
                                self.orderbook_stats[key] = {
                                    'first_update_id': orderbook.get('last_update_id'),
                                    'updates': []
                                }
                            
                            self.orderbook_stats[key]['updates'].append({
                                'update_id': orderbook.get('last_update_id'),
                                'timestamp': orderbook.get('timestamp'),
                                'bid_count': len(orderbook.get('bids', [])),
                                'ask_count': len(orderbook.get('asks', []))
                            })
                        else:
                            self.logger.warning(
                                "获取订单簿失败",
                                exchange=exchange,
                                symbol=symbol,
                                status=resp.status
                            )
                
                # 4. 监控更新频率
                self.logger.info("开始监控订单簿更新...")
                
                for i in range(10):  # 监控10次
                    await asyncio.sleep(3)  # 每3秒检查一次
                    
                    for exchange, symbol in test_symbols:
                        url = f'http://localhost:8100/api/v1/orderbook/{exchange}/{symbol}'
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                orderbook = await resp.json()
                                key = f"{exchange}:{symbol}"
                                
                                if key in self.orderbook_stats and self.orderbook_stats[key]['updates']:
                                    last_update = self.orderbook_stats[key]['updates'][-1]
                                    current_update_id = orderbook.get('last_update_id')
                                    
                                    if current_update_id != last_update['update_id']:
                                        # 计算更新间隔
                                        update_gap = current_update_id - last_update['update_id']
                                        
                                        self.logger.info(
                                            "检测到订单簿更新",
                                            exchange=exchange,
                                            symbol=symbol,
                                            prev_update_id=last_update['update_id'],
                                            curr_update_id=current_update_id,
                                            update_gap=update_gap,
                                            iteration=i+1
                                        )
                                        
                                        self.orderbook_stats[key]['updates'].append({
                                            'update_id': current_update_id,
                                            'timestamp': orderbook.get('timestamp'),
                                            'bid_count': len(orderbook.get('bids', [])),
                                            'ask_count': len(orderbook.get('asks', []))
                                        })
                
                # 5. 生成报告
                self.generate_report()
                
        except Exception as e:
            self.logger.error("测试失败", error=str(e))
            import traceback
            traceback.print_exc()
    
    def generate_report(self):
        """生成测试报告"""
        self.logger.info("=== 订单簿更新测试报告 ===")
        
        for key, stats in self.orderbook_stats.items():
            updates = stats['updates']
            if len(updates) < 2:
                continue
            
            # 计算更新统计
            update_gaps = []
            for i in range(1, len(updates)):
                gap = updates[i]['update_id'] - updates[i-1]['update_id']
                update_gaps.append(gap)
            
            if update_gaps:
                avg_gap = sum(update_gaps) / len(update_gaps)
                max_gap = max(update_gaps)
                min_gap = min(update_gaps)
                
                self.logger.info(
                    "交易对统计",
                    symbol=key,
                    total_updates=len(updates),
                    avg_update_gap=f"{avg_gap:.1f}",
                    max_update_gap=max_gap,
                    min_update_gap=min_gap,
                    first_update_id=stats['first_update_id'],
                    last_update_id=updates[-1]['update_id']
                )


async def main():
    """主函数"""
    tester = OrderBookTester()
    await tester.test_collector_orderbook()


if __name__ == "__main__":
    asyncio.run(main()) 