#!/usr/bin/env python3
"""
波动率指数数据监控器
监控volatility_index数据流
"""

import asyncio
import nats
import json
from datetime import datetime
import signal
import sys

class VolIndexMonitor:
    def __init__(self):
        self.nc = None
        self.running = True
        self.message_count = 0
        self.exchanges = {}
        
    async def vol_index_handler(self, msg):
        """处理波动率指数消息"""
        try:
            data = json.loads(msg.data.decode())
            subject_parts = msg.subject.split('.')
            
            if len(subject_parts) >= 4:
                exchange = subject_parts[1]
                market_type = subject_parts[2]
                symbol = subject_parts[3]
                
                self.message_count += 1
                if exchange not in self.exchanges:
                    self.exchanges[exchange] = 0
                self.exchanges[exchange] += 1
                
                # 显示波动率指数信息
                vol_index = data.get('volatility_index', 'N/A')
                timestamp = data.get('timestamp', 'N/A')
                
                print(f"📊 [{exchange}] {symbol} 波动率指数:")
                print(f"   波动率指数: {vol_index}")
                print(f"   时间戳: {timestamp}")
                print(f"   消息计数: {self.message_count}")
                print("-" * 50)
                    
        except Exception as e:
            print(f"❌ 解析波动率指数消息失败: {e}")
            
    async def connect_and_subscribe(self):
        """连接NATS并订阅消息"""
        try:
            # 连接NATS
            self.nc = await nats.connect('nats://localhost:4222')
            print('🔗 已连接到NATS服务器')
            
            # 订阅波动率指数数据（新规范）
            await self.nc.subscribe('volatility_index.>', cb=self.vol_index_handler)
            print('📊 开始监听波动率指数数据...')
            print('💡 按 Ctrl+C 停止监听\n')
            
            # 保持运行
            while self.running:
                await asyncio.sleep(1)
                
        except Exception as e:
            print(f"❌ 连接或订阅失败: {e}")
        finally:
            if self.nc:
                await self.nc.close()
                print('🔌 NATS连接已关闭')
                
    def signal_handler(self, signum, frame):
        """信号处理器"""
        print(f'\n📊 最终统计:')
        print(f'   总消息数: {self.message_count}')
        print(f'   交易所统计: {self.exchanges}')
        print('👋 正在优雅停止...')
        self.running = False

async def main():
    monitor = VolIndexMonitor()
    
    # 设置信号处理
    signal.signal(signal.SIGINT, monitor.signal_handler)
    signal.signal(signal.SIGTERM, monitor.signal_handler)
    
    # 开始监控
    await monitor.connect_and_subscribe()

if __name__ == "__main__":
    asyncio.run(main())
