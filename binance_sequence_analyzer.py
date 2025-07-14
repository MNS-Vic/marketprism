#!/usr/bin/env python3
"""
Binance永续合约序列号分析器 - 纯监听模式
用于诊断序列号跳跃的根本原因
"""

import asyncio
import websockets
import json
import time
from datetime import datetime, timezone
from typing import List, Dict, Any
import statistics
from collections import defaultdict

class BinanceSequenceAnalyzer:
    def __init__(self, symbols: List[str]):
        self.symbols = [s.lower() for s in symbols]  # 转换为小写
        self.ws_url = "wss://fstream.binance.com/ws"
        self.messages = []
        self.sequence_data = defaultdict(list)  # 按symbol分组存储序列号数据
        self.start_time = None
        self.message_count = 0
        self.target_messages = 200  # 目标收集消息数
        
    async def start_analysis(self):
        """启动纯监听分析"""
        print("🔍 启动Binance永续合约序列号分析器")
        print(f"📊 监听交易对: {[s.upper() for s in self.symbols]}")
        print(f"🎯 目标收集: {self.target_messages}条消息")
        print("=" * 60)
        
        # 构建订阅消息
        streams = [f"{symbol}@depth" for symbol in self.symbols]
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": 1
        }
        
        self.start_time = time.time()
        
        try:
            async with websockets.connect(self.ws_url) as websocket:
                # 发送订阅消息
                await websocket.send(json.dumps(subscribe_msg))
                print(f"📡 已订阅WebSocket流: {streams}")
                
                # 开始监听
                async for message in websocket:
                    await self._process_message(message)
                    
                    # 达到目标消息数后停止
                    if self.message_count >= self.target_messages:
                        print(f"\n✅ 已收集{self.message_count}条消息，开始分析...")
                        break
                        
        except Exception as e:
            print(f"❌ WebSocket连接错误: {e}")
            
        # 分析结果
        await self._analyze_results()
    
    async def _process_message(self, message: str):
        """处理单条WebSocket消息 - 纯记录模式"""
        try:
            data = json.loads(message)
            
            # 跳过非数据消息（如订阅确认）
            if 'stream' not in data or 'data' not in data:
                return
                
            stream = data['stream']
            msg_data = data['data']
            
            # 只处理depth更新
            if '@depth' not in stream:
                return
                
            # 提取symbol
            symbol = stream.split('@')[0].upper()
            
            # 记录消息
            timestamp = time.time()
            receive_time = datetime.now(timezone.utc)
            
            # 提取序列号字段
            first_update_id = msg_data.get('U')  # firstUpdateId
            final_update_id = msg_data.get('u')  # finalUpdateId  
            prev_update_id = msg_data.get('pu')  # prevUpdateId
            
            # 构建记录
            record = {
                'timestamp': timestamp,
                'receive_time': receive_time,
                'symbol': symbol,
                'stream': stream,
                'U': first_update_id,
                'u': final_update_id,
                'pu': prev_update_id,
                'message_id': self.message_count + 1,
                'bids_count': len(msg_data.get('b', [])),
                'asks_count': len(msg_data.get('a', []))
            }
            
            self.messages.append(record)
            self.sequence_data[symbol].append(record)
            self.message_count += 1
            
            # 实时显示进度
            if self.message_count % 20 == 0:
                elapsed = time.time() - self.start_time
                rate = self.message_count / elapsed
                print(f"📊 已收集 {self.message_count}/{self.target_messages} 条消息 "
                      f"(速率: {rate:.1f} msg/s)")
                
            # 实时显示序列号信息（每10条显示一次）
            if self.message_count % 10 == 0:
                print(f"🔍 {symbol}: U={first_update_id}, u={final_update_id}, pu={prev_update_id}")
                
        except Exception as e:
            print(f"❌ 处理消息失败: {e}")
    
    async def _analyze_results(self):
        """分析收集到的序列号数据"""
        print("\n" + "=" * 60)
        print("📊 序列号分析结果")
        print("=" * 60)
        
        total_elapsed = time.time() - self.start_time
        avg_rate = self.message_count / total_elapsed
        
        print(f"⏱️  总耗时: {total_elapsed:.2f}秒")
        print(f"📈 平均速率: {avg_rate:.2f} 消息/秒")
        print(f"📋 总消息数: {self.message_count}")
        
        # 按交易对分析
        for symbol in self.symbols:
            symbol_upper = symbol.upper()
            if symbol_upper not in self.sequence_data:
                continue
                
            records = self.sequence_data[symbol_upper]
            print(f"\n🎯 {symbol_upper} 分析 ({len(records)}条消息):")
            
            await self._analyze_symbol_sequence(symbol_upper, records)
    
    async def _analyze_symbol_sequence(self, symbol: str, records: List[Dict]):
        """分析单个交易对的序列号序列"""
        if len(records) < 2:
            print("  ❌ 数据不足，无法分析")
            return
            
        # 分析pu连续性（永续合约的关键验证）
        pu_gaps = []
        u_gaps = []
        time_intervals = []
        
        prev_record = None
        consecutive_count = 0
        gap_count = 0
        
        print("  📋 前10条消息的序列号详情:")
        for i, record in enumerate(records[:10]):
            print(f"    {i+1:2d}. U={record['U']:>12}, u={record['U']:>12}, pu={record['pu']:>12}")
        
        print("\n  🔍 序列号连续性分析:")
        
        for record in records:
            if prev_record is not None:
                # 计算时间间隔
                time_diff = record['timestamp'] - prev_record['timestamp']
                time_intervals.append(time_diff * 1000)  # 转换为毫秒
                
                # 分析pu连续性（关键指标）
                if record['pu'] is not None and prev_record['u'] is not None:
                    if record['pu'] == prev_record['u']:
                        consecutive_count += 1
                    else:
                        gap = abs(record['pu'] - prev_record['u'])
                        pu_gaps.append(gap)
                        gap_count += 1
                        
                        # 显示大的跳跃
                        if gap > 1000:
                            print(f"    ⚠️  大跳跃: 消息{record['message_id']}, "
                                  f"pu={record['pu']}, 期望={prev_record['u']}, gap={gap}")
                
                # 分析u序列的增长
                if record['u'] is not None and prev_record['u'] is not None:
                    u_gap = record['u'] - prev_record['u']
                    if u_gap > 0:
                        u_gaps.append(u_gap)
            
            prev_record = record
        
        # 统计结果
        total_pairs = len(records) - 1
        consecutive_rate = (consecutive_count / total_pairs * 100) if total_pairs > 0 else 0
        
        print(f"    ✅ 连续序列号对: {consecutive_count}/{total_pairs} ({consecutive_rate:.1f}%)")
        print(f"    ❌ 序列号跳跃: {gap_count}")
        
        if pu_gaps:
            print(f"    📊 pu跳跃统计:")
            print(f"       最小跳跃: {min(pu_gaps)}")
            print(f"       最大跳跃: {max(pu_gaps)}")
            print(f"       平均跳跃: {statistics.mean(pu_gaps):.1f}")
            print(f"       中位数跳跃: {statistics.median(pu_gaps):.1f}")
            
            # 跳跃分布
            small_gaps = len([g for g in pu_gaps if g < 1000])
            medium_gaps = len([g for g in pu_gaps if 1000 <= g < 10000])
            large_gaps = len([g for g in pu_gaps if g >= 10000])
            
            print(f"    📈 跳跃分布:")
            print(f"       <1000: {small_gaps} ({small_gaps/len(pu_gaps)*100:.1f}%)")
            print(f"       1000-9999: {medium_gaps} ({medium_gaps/len(pu_gaps)*100:.1f}%)")
            print(f"       ≥10000: {large_gaps} ({large_gaps/len(pu_gaps)*100:.1f}%)")
        
        if time_intervals:
            print(f"    ⏱️  消息间隔统计:")
            print(f"       平均间隔: {statistics.mean(time_intervals):.1f}ms")
            print(f"       中位数间隔: {statistics.median(time_intervals):.1f}ms")
            print(f"       最小间隔: {min(time_intervals):.1f}ms")
            print(f"       最大间隔: {max(time_intervals):.1f}ms")
        
        # 保存详细数据到文件
        await self._save_detailed_data(symbol, records)
    
    async def _save_detailed_data(self, symbol: str, records: List[Dict]):
        """保存详细数据到文件供进一步分析"""
        filename = f"binance_{symbol.lower()}_sequence_analysis.txt"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"Binance {symbol} 序列号详细分析\n")
            f.write(f"分析时间: {datetime.now(timezone.utc)}\n")
            f.write(f"消息总数: {len(records)}\n")
            f.write("=" * 80 + "\n\n")
            
            f.write("消息详情:\n")
            f.write("ID\t时间戳\t\t\tU\t\tu\t\tpu\t\tbids\tasks\n")
            f.write("-" * 80 + "\n")
            
            for record in records:
                f.write(f"{record['message_id']}\t"
                       f"{record['receive_time'].strftime('%H:%M:%S.%f')[:-3]}\t"
                       f"{record['U']}\t\t{record['u']}\t\t{record['pu']}\t\t"
                       f"{record['bids_count']}\t{record['asks_count']}\n")
        
        print(f"    💾 详细数据已保存到: {filename}")

async def main():
    """主函数"""
    symbols = ['BTCUSDT', 'ETHUSDT']
    analyzer = BinanceSequenceAnalyzer(symbols)
    await analyzer.start_analysis()

if __name__ == "__main__":
    asyncio.run(main())
