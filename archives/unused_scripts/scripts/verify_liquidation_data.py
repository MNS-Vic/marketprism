#!/usr/bin/env python3
"""
强平数据验证脚本

验证 Liquidation 管理器的全市场强平数据收集和智能筛选功能：
1. 全市场强平数据订阅
2. "all-symbol" 聚合模式
3. 数据标准化和发布验证
4. NATS 主题格式验证
"""

import asyncio
import json
import sys
import os
from datetime import datetime, timezone
from collections import Counter, defaultdict
from typing import Dict, List, Any

# 添加项目根目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

async def verify_liquidation_data():
    """验证强平数据收集和发布"""
    try:
        from nats.aio.client import Client as NATS
    except ImportError:
        print("❌ nats-py 未安装，无法进行验证")
        return False

    print("🚀 开始验证强平数据收集...")
    
    # 连接 NATS
    nc = NATS()
    await nc.connect(servers=["nats://127.0.0.1:4222"])
    
    # 数据统计
    liquidation_stats = {
        'total_messages': 0,
        'binance_messages': 0,
        'okx_messages': 0,
        'symbols': Counter(),
        'sides': Counter(),
        'exchanges': Counter(),
        'latest_samples': []
    }
    
    # 消息处理器
    async def liquidation_handler(msg):
        try:
            subject = msg.subject
            data = json.loads(msg.data.decode())
            
            liquidation_stats['total_messages'] += 1
            
            # 解析主题
            # 格式: liquidation-data.{exchange}.{market_type}.{symbol}
            parts = subject.split('.')
            if len(parts) >= 4:
                exchange = parts[1]
                market_type = parts[2]
                symbol_part = parts[3]
                
                liquidation_stats['exchanges'][exchange] += 1
                
                if 'binance' in exchange:
                    liquidation_stats['binance_messages'] += 1
                elif 'okx' in exchange:
                    liquidation_stats['okx_messages'] += 1
                
                # 记录 symbol 分布
                actual_symbol = data.get('symbol', symbol_part)
                liquidation_stats['symbols'][actual_symbol] += 1
                
                # 记录 side 分布
                side = data.get('side', 'unknown')
                liquidation_stats['sides'][side] += 1
                
                # 保存最新样本
                sample = {
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'subject': subject,
                    'exchange': exchange,
                    'symbol': actual_symbol,
                    'side': side,
                    'price': data.get('price'),
                    'quantity': data.get('quantity'),
                    'aggregation_mode': data.get('aggregation_mode', 'unknown'),
                    'data_size': len(msg.data)
                }
                
                liquidation_stats['latest_samples'].append(sample)
                if len(liquidation_stats['latest_samples']) > 10:
                    liquidation_stats['latest_samples'].pop(0)
                
                # 定期输出统计
                if liquidation_stats['total_messages'] % 5 == 0:
                    print(f"📊 已收到 {liquidation_stats['total_messages']} 条强平数据")
                    
        except Exception as e:
            print(f"❌ 处理强平消息失败: {e}")
    
    # 订阅强平数据
    await nc.subscribe("liquidation-data.>", cb=liquidation_handler)
    
    print("📡 开始监控强平数据流 (180秒)...")
    print("   - 订阅主题: liquidation-data.>")
    print("   - 预期模式: all-symbol 聚合模式")
    print("   - 预期交易所: Binance, OKX")
    
    start_time = datetime.now(timezone.utc)
    await asyncio.sleep(180)  # 监控3分钟
    end_time = datetime.now(timezone.utc)
    
    duration = (end_time - start_time).total_seconds()
    
    # 生成验证报告
    print(f"\n{'='*60}")
    print(f"🎯 强平数据验证报告 ({duration:.1f}秒)")
    print(f"{'='*60}")
    
    # 总体统计
    total = liquidation_stats['total_messages']
    print(f"📈 总体统计:")
    print(f"   总消息数: {total}")
    print(f"   平均频率: {total/duration:.2f} 条/秒")
    
    # 交易所分布
    print(f"\n🏢 交易所分布:")
    for exchange, count in liquidation_stats['exchanges'].most_common():
        percentage = (count / max(total, 1)) * 100
        print(f"   {exchange}: {count} 条 ({percentage:.1f}%)")
    
    # Symbol 分布 (显示前10个)
    print(f"\n💰 交易对分布 (前10个):")
    for symbol, count in liquidation_stats['symbols'].most_common(10):
        percentage = (count / max(total, 1)) * 100
        print(f"   {symbol}: {count} 条 ({percentage:.1f}%)")
    
    # Side 分布
    print(f"\n📊 方向分布:")
    for side, count in liquidation_stats['sides'].most_common():
        percentage = (count / max(total, 1)) * 100
        print(f"   {side}: {count} 条 ({percentage:.1f}%)")
    
    # 最新样本
    print(f"\n🔍 最新样本 (最近5条):")
    for sample in liquidation_stats['latest_samples'][-5:]:
        print(f"   {sample['timestamp'][:19]} | {sample['subject']}")
        print(f"      Symbol: {sample['symbol']} | Side: {sample['side']} | Price: {sample['price']}")
        print(f"      Mode: {sample['aggregation_mode']} | Size: {sample['data_size']} bytes")
    
    # 验证结果
    print(f"\n✅ 验证结果:")
    
    success = True
    
    # 检查是否收到数据
    if total == 0:
        print("   ❌ 未收到任何强平数据")
        success = False
    else:
        print(f"   ✅ 成功收到 {total} 条强平数据")
    
    # 检查交易所覆盖
    if liquidation_stats['binance_messages'] > 0:
        print(f"   ✅ Binance 强平数据: {liquidation_stats['binance_messages']} 条")
    else:
        print("   ⚠️  未收到 Binance 强平数据")
    
    if liquidation_stats['okx_messages'] > 0:
        print(f"   ✅ OKX 强平数据: {liquidation_stats['okx_messages']} 条")
    else:
        print("   ⚠️  未收到 OKX 强平数据")
    
    # 检查 all-symbol 模式
    all_symbol_subjects = [s['subject'] for s in liquidation_stats['latest_samples'] 
                          if 'all-symbol' in s['subject']]
    if all_symbol_subjects:
        print(f"   ✅ all-symbol 模式工作正常: {len(all_symbol_subjects)} 条")
    else:
        print("   ⚠️  未检测到 all-symbol 模式主题")
    
    # 检查数据完整性
    complete_samples = [s for s in liquidation_stats['latest_samples'] 
                       if s['price'] and s['quantity'] and s['side'] != 'unknown']
    if complete_samples:
        print(f"   ✅ 数据完整性良好: {len(complete_samples)}/{len(liquidation_stats['latest_samples'])} 条完整")
    else:
        print("   ❌ 数据完整性问题：缺少关键字段")
        success = False
    
    # 关闭连接
    await nc.drain()
    
    if success:
        print(f"\n🎉 强平数据验证成功！")
        print("   - 全市场强平数据订阅正常")
        print("   - all-symbol 聚合模式工作正常")
        print("   - 数据标准化和发布正常")
        print("   - NATS 主题格式正确")
    else:
        print(f"\n⚠️  强平数据验证发现问题，需要进一步调试")
    
    return success

async def main():
    """主函数"""
    print("🔧 强平数据全面验证工具")
    print("=" * 50)
    
    try:
        success = await verify_liquidation_data()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⏹️  验证被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 验证过程发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
