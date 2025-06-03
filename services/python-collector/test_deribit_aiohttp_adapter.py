#!/usr/bin/env python3
"""
测试Deribit aiohttp适配器

验证使用aiohttp WebSocket的Deribit连接和数据接收
"""

import asyncio
import time
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Any

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from marketprism_collector.types import ExchangeConfig, Exchange, MarketType, DataType
from marketprism_collector.exchanges.deribit import DeribitAdapter


class DeribitAdapterTester:
    """Deribit适配器测试器"""
    
    def __init__(self):
        self.message_count = 0
        self.trade_count = 0
        self.orderbook_count = 0
        self.ticker_count = 0
        self.start_time = time.time()
        self.messages = []
        
    async def test_deribit_adapter(self):
        """测试Deribit适配器"""
        print("🚀 测试Deribit aiohttp适配器")
        print("=" * 80)
        
        # 显示代理设置
        print(f"🔧 代理配置:")
        print(f"   http_proxy: {os.getenv('http_proxy', '未设置')}")
        print(f"   https_proxy: {os.getenv('https_proxy', '未设置')}")
        print(f"   ALL_PROXY: {os.getenv('ALL_PROXY', '未设置')}")
        print()
        
        # 创建Deribit配置
        deribit_config = ExchangeConfig(
            exchange=Exchange.DERIBIT,
            market_type=MarketType.DERIVATIVES,
            enabled=True,
            symbols=["BTC-PERPETUAL", "ETH-PERPETUAL"],
            data_types=[DataType.TRADE, DataType.TICKER],
            ws_url="wss://www.deribit.com/ws/api/v2",
            base_url="https://www.deribit.com",
            ping_interval=20,
            reconnect_attempts=3,
            reconnect_delay=5,
            depth_limit=20
        )
        
        # 创建适配器
        adapter = DeribitAdapter(deribit_config)
        
        # 注册回调函数
        adapter.register_callback(DataType.TRADE, self.on_trade)
        adapter.register_callback(DataType.TICKER, self.on_ticker)
        adapter.register_callback(DataType.ORDERBOOK, self.on_orderbook)
        
        try:
            print("🔌 启动Deribit适配器...")
            success = await adapter.start()
            
            if not success:
                print("❌ Deribit适配器启动失败")
                return
            
            print("✅ Deribit适配器启动成功")
            print("⏳ 等待数据接收...")
            
            # 运行60秒测试
            test_duration = 60
            await asyncio.sleep(test_duration)
            
            # 停止适配器
            print("\n⏹️ 停止Deribit适配器...")
            await adapter.stop()
            
            # 生成报告
            self.generate_report(test_duration)
            
        except KeyboardInterrupt:
            print("\n⏹️ 测试被用户中断")
            await adapter.stop()
        except Exception as e:
            print(f"\n❌ 测试异常: {e}")
            import traceback
            traceback.print_exc()
            await adapter.stop()
    
    async def on_trade(self, trade):
        """处理交易数据"""
        self.message_count += 1
        self.trade_count += 1
        
        # 记录前几条消息
        if len(self.messages) < 10:
            self.messages.append({
                'type': 'trade',
                'data': {
                    'symbol': trade.symbol_name,
                    'price': str(trade.price),
                    'quantity': str(trade.quantity),
                    'timestamp': trade.timestamp.isoformat()
                }
            })
        
        # 每100条消息打印一次进度
        if self.message_count % 100 == 0:
            elapsed = time.time() - self.start_time
            rate = self.message_count / elapsed if elapsed > 0 else 0
            print(f"   📈 已接收 {self.message_count} 条消息 ({rate:.1f} msg/s)")
    
    async def on_ticker(self, ticker):
        """处理行情数据"""
        self.message_count += 1
        self.ticker_count += 1
        
        # 记录前几条消息
        if len(self.messages) < 10:
            self.messages.append({
                'type': 'ticker',
                'data': {
                    'symbol': ticker.symbol_name,
                    'last_price': str(ticker.last_price),
                    'volume': str(ticker.volume),
                    'timestamp': ticker.timestamp.isoformat()
                }
            })
    
    async def on_orderbook(self, orderbook):
        """处理订单簿数据"""
        self.message_count += 1
        self.orderbook_count += 1
        
        # 记录前几条消息
        if len(self.messages) < 10:
            self.messages.append({
                'type': 'orderbook',
                'data': {
                    'symbol': orderbook.symbol_name,
                    'bids_count': len(orderbook.bids),
                    'asks_count': len(orderbook.asks),
                    'timestamp': orderbook.timestamp.isoformat()
                }
            })
    
    def generate_report(self, test_duration: int):
        """生成测试报告"""
        print("\n📊 Deribit aiohttp适配器测试报告")
        print("=" * 80)
        
        elapsed = time.time() - self.start_time
        rate = self.message_count / elapsed if elapsed > 0 else 0
        
        print(f"⏱️ 测试时长: {elapsed:.1f}秒")
        print(f"📨 总消息数: {self.message_count:,}条")
        print(f"🚀 处理速度: {rate:.1f} msg/s")
        print(f"📈 交易数据: {self.trade_count:,}条")
        print(f"📊 行情数据: {self.ticker_count:,}条")
        print(f"📋 订单簿数据: {self.orderbook_count:,}条")
        
        # 连接状态评估
        if self.message_count > 0:
            print(f"\n✅ 连接状态: 成功")
            print(f"✅ 数据接收: 正常")
        else:
            print(f"\n❌ 连接状态: 失败或无数据")
        
        # 性能评估
        if rate > 10:
            performance = "优秀"
        elif rate > 5:
            performance = "良好"
        elif rate > 1:
            performance = "一般"
        else:
            performance = "需改进"
        
        print(f"🎯 性能评估: {performance}")
        
        # 显示示例消息
        if self.messages:
            print(f"\n📝 示例消息 (前{len(self.messages)}条):")
            for i, msg in enumerate(self.messages, 1):
                print(f"   {i}. {msg['type']}: {msg['data']}")
        
        # 保存详细结果
        result = {
            'test_duration': elapsed,
            'total_messages': self.message_count,
            'message_rate': rate,
            'trade_count': self.trade_count,
            'ticker_count': self.ticker_count,
            'orderbook_count': self.orderbook_count,
            'sample_messages': self.messages,
            'timestamp': datetime.now().isoformat()
        }
        
        result_file = f"deribit_aiohttp_test_result_{int(time.time())}.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 详细结果已保存到: {result_file}")
        
        # 总结
        if self.message_count > 0:
            print(f"\n🎉 测试成功！Deribit aiohttp适配器工作正常")
        else:
            print(f"\n⚠️ 测试未接收到数据，请检查连接配置")


async def main():
    """主函数"""
    tester = DeribitAdapterTester()
    await tester.test_deribit_adapter()


if __name__ == "__main__":
    asyncio.run(main())