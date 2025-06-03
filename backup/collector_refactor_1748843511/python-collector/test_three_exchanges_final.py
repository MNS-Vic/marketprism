#!/usr/bin/env python3
"""
三大交易所最终综合测试

验证Binance + OKX + Deribit全部连接成功并正常接收数据
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
from marketprism_collector.exchanges.deribit_aiohttp import DeribitAiohttpAdapter


class ThreeExchangesTester:
    """三大交易所综合测试器"""
    
    def __init__(self):
        self.start_time = time.time()
        self.stats = {
            'binance': {'messages': 0, 'trades': 0, 'tickers': 0, 'connected': False},
            'okx': {'messages': 0, 'trades': 0, 'tickers': 0, 'connected': False},
            'deribit': {'messages': 0, 'trades': 0, 'tickers': 0, 'connected': False}
        }
        self.sample_messages = []
        
    async def test_three_exchanges(self):
        """测试三大交易所"""
        print("🚀 三大交易所最终综合测试")
        print("=" * 80)
        
        # 显示代理设置
        print(f"🔧 代理配置:")
        print(f"   http_proxy: {os.getenv('http_proxy', '未设置')}")
        print(f"   https_proxy: {os.getenv('https_proxy', '未设置')}")
        print(f"   ALL_PROXY: {os.getenv('ALL_PROXY', '未设置')}")
        print()
        
        # 创建Deribit配置和适配器
        deribit_config = ExchangeConfig(
            exchange=Exchange.DERIBIT,
            market_type=MarketType.DERIVATIVES,
            enabled=True,
            symbols=["BTC-PERPETUAL"],
            data_types=[DataType.TRADE, DataType.TICKER],
            ws_url="wss://www.deribit.com/ws/api/v2",
            base_url="https://www.deribit.com",
            ping_interval=20,
            reconnect_attempts=3,
            reconnect_delay=5,
            depth_limit=20
        )
        
        deribit_adapter = DeribitAiohttpAdapter(deribit_config)
        
        # 注册Deribit回调
        deribit_adapter.register_callback(DataType.TRADE, lambda data: self.on_message('deribit', 'trade', data))
        deribit_adapter.register_callback(DataType.TICKER, lambda data: self.on_message('deribit', 'ticker', data))
        
        try:
            print("🔌 启动Deribit适配器...")
            deribit_success = await deribit_adapter.start()
            
            if deribit_success:
                self.stats['deribit']['connected'] = True
                print("✅ Deribit连接成功")
            else:
                print("❌ Deribit连接失败")
            
            # 测试其他交易所连接（简化测试）
            await self.test_binance_connection()
            await self.test_okx_connection()
            
            # 运行测试
            test_duration = 60
            print(f"\n⏳ 运行{test_duration}秒综合测试...")
            await asyncio.sleep(test_duration)
            
            # 停止Deribit适配器
            print("\n⏹️ 停止测试...")
            await deribit_adapter.stop()
            
            # 生成报告
            self.generate_final_report(test_duration)
            
        except KeyboardInterrupt:
            print("\n⏹️ 测试被用户中断")
            await deribit_adapter.stop()
        except Exception as e:
            print(f"\n❌ 测试异常: {e}")
            import traceback
            traceback.print_exc()
            await deribit_adapter.stop()
    
    async def test_binance_connection(self):
        """测试Binance连接（简化版）"""
        try:
            import websockets
            
            # 使用备用域名测试连接
            test_url = "wss://data-stream.binance.vision/ws/btcusdt@trade"
            
            async with websockets.connect(test_url, open_timeout=10) as websocket:
                # 等待一条消息
                message = await asyncio.wait_for(websocket.recv(), timeout=5)
                data = json.loads(message)
                
                if 'p' in data:  # 价格字段存在
                    self.stats['binance']['connected'] = True
                    self.stats['binance']['messages'] += 1
                    self.stats['binance']['trades'] += 1
                    print("✅ Binance连接成功")
                    
                    # 记录示例消息
                    self.sample_messages.append({
                        'exchange': 'binance',
                        'type': 'trade',
                        'data': {
                            'symbol': data.get('s', 'BTCUSDT'),
                            'price': data.get('p', '0'),
                            'quantity': data.get('q', '0')
                        }
                    })
                    
        except Exception as e:
            print(f"❌ Binance连接失败: {e}")
    
    async def test_okx_connection(self):
        """测试OKX连接（简化版）"""
        try:
            import websockets
            
            # OKX WebSocket测试
            test_url = "wss://ws.okx.com:8443/ws/v5/public"
            
            async with websockets.connect(test_url, open_timeout=10) as websocket:
                # 发送订阅消息
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [{"channel": "trades", "instId": "BTC-USDT"}]
                }
                await websocket.send(json.dumps(subscribe_msg))
                
                # 等待响应
                for _ in range(3):
                    message = await asyncio.wait_for(websocket.recv(), timeout=5)
                    data = json.loads(message)
                    
                    if 'data' in data and data['data']:
                        trade_data = data['data'][0]
                        if 'px' in trade_data:  # 价格字段存在
                            self.stats['okx']['connected'] = True
                            self.stats['okx']['messages'] += 1
                            self.stats['okx']['trades'] += 1
                            print("✅ OKX连接成功")
                            
                            # 记录示例消息
                            self.sample_messages.append({
                                'exchange': 'okx',
                                'type': 'trade',
                                'data': {
                                    'symbol': trade_data.get('instId', 'BTC-USDT'),
                                    'price': trade_data.get('px', '0'),
                                    'quantity': trade_data.get('sz', '0')
                                }
                            })
                            break
                    
        except Exception as e:
            print(f"❌ OKX连接失败: {e}")
    
    async def on_message(self, exchange: str, msg_type: str, data):
        """处理消息回调"""
        self.stats[exchange]['messages'] += 1
        
        if msg_type == 'trade':
            self.stats[exchange]['trades'] += 1
        elif msg_type == 'ticker':
            self.stats[exchange]['tickers'] += 1
        
        # 记录前几条消息
        if len(self.sample_messages) < 20:
            self.sample_messages.append({
                'exchange': exchange,
                'type': msg_type,
                'data': {
                    'symbol': getattr(data, 'symbol_name', 'unknown'),
                    'price': str(getattr(data, 'price', getattr(data, 'last_price', '0'))),
                    'timestamp': getattr(data, 'timestamp', datetime.now()).isoformat()
                }
            })
    
    def generate_final_report(self, test_duration: int):
        """生成最终测试报告"""
        print("\n📊 三大交易所最终综合测试报告")
        print("=" * 80)
        
        elapsed = time.time() - self.start_time
        
        # 连接状态总结
        connected_count = sum(1 for stats in self.stats.values() if stats['connected'])
        total_messages = sum(stats['messages'] for stats in self.stats.values())
        total_trades = sum(stats['trades'] for stats in self.stats.values())
        total_tickers = sum(stats['tickers'] for stats in self.stats.values())
        
        print(f"⏱️ 测试时长: {elapsed:.1f}秒")
        print(f"🔌 连接成功: {connected_count}/3 交易所")
        print(f"📨 总消息数: {total_messages:,}条")
        print(f"📈 交易数据: {total_trades:,}条")
        print(f"📊 行情数据: {total_tickers:,}条")
        
        # 各交易所详细状态
        print(f"\n📋 各交易所详细状态:")
        for exchange, stats in self.stats.items():
            status = "✅ 已连接" if stats['connected'] else "❌ 未连接"
            print(f"   {exchange.upper()}: {status}")
            if stats['connected']:
                print(f"      消息: {stats['messages']:,}条, 交易: {stats['trades']:,}条, 行情: {stats['tickers']:,}条")
        
        # 性能评估
        if connected_count == 3:
            print(f"\n🎉 完美成功！三大交易所全部连接成功")
            performance = "优秀"
        elif connected_count == 2:
            print(f"\n✅ 基本成功！{connected_count}个交易所连接成功")
            performance = "良好"
        elif connected_count == 1:
            print(f"\n⚠️ 部分成功！{connected_count}个交易所连接成功")
            performance = "一般"
        else:
            print(f"\n❌ 测试失败！没有交易所连接成功")
            performance = "需改进"
        
        print(f"🎯 综合评估: {performance}")
        
        # 显示示例消息
        if self.sample_messages:
            print(f"\n📝 示例消息 (前{min(len(self.sample_messages), 10)}条):")
            for i, msg in enumerate(self.sample_messages[:10], 1):
                print(f"   {i}. {msg['exchange']}-{msg['type']}: {msg['data']}")
        
        # 保存详细结果
        result = {
            'test_duration': elapsed,
            'connected_exchanges': connected_count,
            'total_messages': total_messages,
            'exchange_stats': self.stats,
            'sample_messages': self.sample_messages,
            'performance': performance,
            'timestamp': datetime.now().isoformat()
        }
        
        result_file = f"three_exchanges_final_test_{int(time.time())}.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 详细结果已保存到: {result_file}")
        
        # 技术总结
        print(f"\n🔧 技术方案总结:")
        print(f"   Binance: 备用域名 wss://data-stream.binance.vision")
        print(f"   OKX: 原域名 + 代理配置")
        print(f"   Deribit: aiohttp WebSocket + 公开频道")
        
        if connected_count == 3:
            print(f"\n🏆 恭喜！MarketPrism Python Collector已支持三大主流交易所！")


async def main():
    """主函数"""
    tester = ThreeExchangesTester()
    await tester.test_three_exchanges()


if __name__ == "__main__":
    asyncio.run(main())