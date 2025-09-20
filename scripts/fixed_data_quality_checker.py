#!/usr/bin/env python3
"""
修复后的数据质量检测器
检测时间戳和数据类型字段的修复效果
"""

import asyncio
import json
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import nats
from nats.js.api import StreamInfo


class FixedDataQualityChecker:
    def __init__(self):
        self.nc = None
        self.js = None
        self.stats = defaultdict(lambda: {
            'count': 0,
            'last_timestamp': None,
            'gaps': [],
            'duplicates': 0,
            'invalid_data': 0,
            'latency_samples': deque(maxlen=100),
            'size_samples': deque(maxlen=100),
            'timestamp_formats': set(),
            'data_type_values': set()
        })
        self.subjects = [
            "orderbook.>",
            "trade.>", 
            "funding_rate.>",
            "open_interest.>",
            "liquidation.>",
            "lsr_top_position.>",
            "lsr_all_account.>",
            "volatility_index.>"
        ]
        
    async def connect(self):
        """连接到 NATS"""
        self.nc = await nats.connect("nats://localhost:4222")
        self.js = self.nc.jetstream()
        print("✅ 已连接到 NATS JetStream")
        
    async def check_data_quality(self, duration_seconds: int = 30):
        """检查数据质量"""
        print(f"🔍 开始修复后数据质量检测 ({duration_seconds}秒)...")
        
        # 订阅所有主题
        subscribers = []
        for subject in self.subjects:
            durable = f"fixed_quality_check_{subject.replace('.>', '').replace('_', '')}"
            sub = await self.js.subscribe(
                subject, 
                cb=self._message_callback,
                durable=durable,
                stream="MARKET_DATA"
            )
            subscribers.append(sub)
            
        print(f"📡 已订阅 {len(subscribers)} 个主题")
        
        # 运行检测
        start_time = time.time()
        await asyncio.sleep(duration_seconds)
        
        # 停止订阅
        for sub in subscribers:
            await sub.drain()
            
        # 分析结果
        await self._analyze_results(duration_seconds)
        
    async def _message_callback(self, msg):
        """消息回调处理"""
        try:
            subject = msg.subject
            data = json.loads(msg.data.decode())
            current_time = time.time()
            
            # 更新统计
            stats = self.stats[subject]
            stats['count'] += 1
            
            # 记录时间戳格式
            if 'timestamp' in data:
                timestamp_str = str(data['timestamp'])
                stats['timestamp_formats'].add(timestamp_str[:20] + "..." if len(timestamp_str) > 20 else timestamp_str)
                
                # 解析时间戳并计算延迟
                msg_timestamp = self._parse_timestamp(data['timestamp'])
                if msg_timestamp:
                    latency = current_time - msg_timestamp
                    stats['latency_samples'].append(latency)
                    
                    # 检查时间间隔
                    if stats['last_timestamp']:
                        gap = msg_timestamp - stats['last_timestamp']
                        if gap > 10:  # 超过10秒的间隔认为是异常
                            stats['gaps'].append(gap)
                    
                    stats['last_timestamp'] = msg_timestamp
            
            # 记录 data_type 值
            if 'data_type' in data:
                stats['data_type_values'].add(data['data_type'])
            
            # 检查数据大小
            data_size = len(msg.data)
            stats['size_samples'].append(data_size)
            
            # 检查数据完整性
            if not self._validate_data_structure(subject, data):
                stats['invalid_data'] += 1
                
        except json.JSONDecodeError:
            self.stats[msg.subject]['invalid_data'] += 1
        except Exception as e:
            print(f"⚠️ 处理消息异常: {e}")
            
    def _parse_timestamp(self, timestamp_str: str) -> Optional[float]:
        """解析时间戳 - 支持ISO格式"""
        try:
            if isinstance(timestamp_str, (int, float)):
                return float(timestamp_str)
            
            # 尝试解析 ISO 格式
            if isinstance(timestamp_str, str):
                if 'T' in timestamp_str:
                    # ISO 8601格式: 2024-12-07T10:30:45.123Z
                    dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    return dt.timestamp()
                elif ' ' in timestamp_str and ':' in timestamp_str:
                    # 自定义格式: 2024-12-07 10:30:45.123
                    try:
                        dt = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
                        return dt.timestamp()
                    except:
                        dt = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                        return dt.timestamp()
            
            return None
        except Exception as e:
            print(f"时间戳解析失败: {timestamp_str}, 错误: {e}")
            return None
            
    def _validate_data_structure(self, subject: str, data: dict) -> bool:
        """验证数据结构"""
        try:
            # 基本字段检查
            required_fields = ['timestamp', 'exchange', 'symbol']
            for field in required_fields:
                if field not in data:
                    return False
                    
            # 根据数据类型检查特定字段
            if 'orderbook' in subject:
                return 'bids' in data and 'asks' in data
            elif 'trade' in subject:
                return 'price' in data and 'quantity' in data
            elif 'funding_rate' in subject:
                return 'current_funding_rate' in data or 'funding_rate' in data
            elif 'open_interest' in subject:
                return 'open_interest_value' in data or 'open_interest' in data
            elif 'liquidation' in subject:
                return 'price' in data and 'quantity' in data
            elif 'lsr_' in subject:
                return 'long_short_ratio' in data
            elif 'volatility_index' in subject:
                return 'volatility_index' in data
                
            return True
        except:
            return False
            
    async def _analyze_results(self, duration: int):
        """分析检测结果"""
        print("\n" + "="*80)
        print("📊 修复后数据质量检测报告")
        print("="*80)
        
        total_messages = sum(stats['count'] for stats in self.stats.values())
        print(f"📈 总消息数: {total_messages:,}")
        print(f"⏱️  检测时长: {duration}秒")
        print(f"📊 平均速率: {total_messages/duration:.1f} 消息/秒")
        
        print("\n🔍 各主题详细统计:")
        print("-" * 80)
        
        issues_found = []
        improvements = []
        
        for subject, stats in sorted(self.stats.items()):
            if stats['count'] == 0:
                continue
                
            print(f"\n📡 {subject}")
            print(f"   消息数量: {stats['count']:,}")
            print(f"   消息速率: {stats['count']/duration:.1f}/秒")
            
            # 时间戳格式分析
            if stats['timestamp_formats']:
                print(f"   时间戳格式: {list(stats['timestamp_formats'])}")
                
            # data_type 值分析
            if stats['data_type_values']:
                print(f"   data_type值: {list(stats['data_type_values'])}")
                
            # 延迟分析
            if stats['latency_samples']:
                latencies = list(stats['latency_samples'])
                avg_latency = sum(latencies) / len(latencies)
                max_latency = max(latencies)
                print(f"   平均延迟: {avg_latency:.3f}秒")
                print(f"   最大延迟: {max_latency:.3f}秒")
                
                if avg_latency < 1.0:
                    improvements.append(f"{subject}: 延迟已优化 ({avg_latency:.3f}秒)")
                elif avg_latency > 5.0:
                    issues_found.append(f"{subject}: 仍有高延迟 ({avg_latency:.3f}秒)")
                    
            # 数据间隔分析
            if stats['gaps']:
                print(f"   ⚠️  发现 {len(stats['gaps'])} 个数据间隔异常")
                issues_found.append(f"{subject}: {len(stats['gaps'])} 个数据间隔异常")
                
            # 无效数据
            if stats['invalid_data'] > 0:
                invalid_rate = stats['invalid_data'] / stats['count'] * 100
                print(f"   ❌ 无效数据: {stats['invalid_data']} ({invalid_rate:.1f}%)")
                if invalid_rate > 0:
                    issues_found.append(f"{subject}: {invalid_rate:.1f}% 无效数据")
            else:
                improvements.append(f"{subject}: 数据验证100%通过")
                
        # 总结
        print("\n" + "="*80)
        if improvements:
            print("✅ 修复成功的改进:")
            for i, improvement in enumerate(improvements, 1):
                print(f"   {i}. {improvement}")
                
        if issues_found:
            print("\n⚠️  仍需解决的问题:")
            for i, issue in enumerate(issues_found, 1):
                print(f"   {i}. {issue}")
        else:
            print("\n🎉 所有数据质量问题已修复！")
            
        print("="*80)
        
    async def disconnect(self):
        """断开连接"""
        if self.nc:
            await self.nc.close()
            print("🔌 已断开 NATS 连接")


async def main():
    checker = FixedDataQualityChecker()
    
    try:
        await checker.connect()
        await checker.check_data_quality(duration_seconds=30)
    except KeyboardInterrupt:
        print("\n⏹️  检测被用户中断")
    except Exception as e:
        print(f"❌ 检测过程中出现错误: {e}")
    finally:
        await checker.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
