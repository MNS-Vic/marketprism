#!/usr/bin/env python3
"""
MarketPrism内存分析脚本
分析当前运行的数据收集器的内存使用情况
"""

import sys
import time
import json
from pathlib import Path

# 添加项目路径
sys.path.append(str(Path(__file__).parent))

from tools.memory_profiler import get_memory_profiler, analyze_target_objects


def main():
    """主分析函数"""
    print("🔍 MarketPrism内存分析报告")
    print("=" * 60)
    
    # 获取内存分析器
    profiler = get_memory_profiler()
    
    # 获取基本内存报告
    print("\n📊 基本内存状态:")
    memory_report = profiler.get_memory_report()
    
    if memory_report.get("status") == "no_data":
        print("❌ 暂无内存分析数据，请等待内存分析器收集数据...")
        return
    
    print(f"当前内存使用: {memory_report['current_memory_mb']:.2f} MB")
    print(f"内存增长趋势: {memory_report['growth_trend']}")
    print(f"总对象数量: {memory_report['total_objects']:,}")
    print(f"分析时长: {memory_report['profiling_duration_minutes']:.1f} 分钟")
    print(f"快照数量: {memory_report['snapshot_count']}")
    
    if memory_report.get('tracemalloc_info'):
        tm_info = memory_report['tracemalloc_info']
        print(f"Tracemalloc当前: {tm_info['current_mb']:.2f} MB")
        print(f"Tracemalloc峰值: {tm_info['peak_mb']:.2f} MB")
    
    # 显示前10个对象类型
    print("\n🔝 前10个对象类型:")
    for i, (obj_type, count) in enumerate(memory_report['top_object_types'], 1):
        print(f"{i:2d}. {obj_type:<20} {count:>8,} 个")
    
    # 分析特定的可疑对象类型
    print("\n🔍 详细对象分析:")
    target_types = ['dict', 'list', 'tuple', 'str', 'coroutine', 'Task']
    
    # 添加MarketPrism特定的对象类型
    marketprism_types = []
    for obj_type, _ in memory_report['top_object_types']:
        if any(keyword in obj_type.lower() for keyword in 
               ['websocket', 'orderbook', 'message', 'buffer', 'queue', 'connection']):
            marketprism_types.append(obj_type)
    
    target_types.extend(marketprism_types[:5])  # 只取前5个
    
    detailed_analysis = analyze_target_objects(target_types)
    
    for obj_type, analysis in detailed_analysis.items():
        if analysis['count'] > 0:
            print(f"\n📋 {obj_type} 对象分析:")
            print(f"   数量: {analysis['count']:,}")
            print(f"   总大小: {analysis['total_size_mb']:.2f} MB")
            print(f"   平均大小: {analysis['total_size_mb']/analysis['count']*1024:.1f} KB")
            
            # 显示样本对象
            if analysis['samples']:
                print("   样本对象:")
                for i, sample in enumerate(analysis['samples'][:3], 1):
                    size_kb = sample['size'] / 1024
                    print(f"     {i}. ID:{sample['id']} 大小:{size_kb:.1f}KB", end="")
                    
                    if 'length' in sample:
                        print(f" 长度:{sample['length']}", end="")
                    if 'first_item_type' in sample:
                        print(f" 首项类型:{sample['first_item_type']}", end="")
                    if 'attributes' in sample:
                        attrs = sample['attributes'][:3]
                        print(f" 属性:{attrs}", end="")
                    print()
    
    # 内存增长分析
    print("\n📈 内存增长分析:")
    if len(profiler.snapshots) >= 3:
        current = profiler.snapshots[-1]
        previous = profiler.snapshots[-3]
        
        time_diff = current.timestamp - previous.timestamp
        memory_diff = current.total_memory_mb - previous.total_memory_mb
        
        print(f"时间间隔: {time_diff:.0f} 秒")
        print(f"内存变化: {memory_diff:+.2f} MB")
        print(f"增长速率: {memory_diff/(time_diff/60):+.2f} MB/分钟")
        
        # 分析对象数量变化
        print("\n📊 对象数量变化 (前5个增长最多的类型):")
        growth_analysis = []
        
        for obj_type, current_count in current.objects_by_type.items():
            previous_count = previous.objects_by_type.get(obj_type, 0)
            growth = current_count - previous_count
            if growth > 0:
                growth_analysis.append((obj_type, growth, current_count))
        
        growth_analysis.sort(key=lambda x: x[1], reverse=True)
        
        for i, (obj_type, growth, total) in enumerate(growth_analysis[:5], 1):
            growth_rate = growth / (time_diff / 60)  # 每分钟增长
            print(f"{i}. {obj_type:<20} +{growth:>6,} (+{growth_rate:>5.1f}/分钟) 总计:{total:>8,}")
    
    else:
        print("数据不足，需要更多快照进行增长分析")
    
    # 内存泄漏风险评估
    print("\n⚠️  内存泄漏风险评估:")
    risk_score = 0
    risk_factors = []
    
    if memory_report['growth_trend'] == 'increasing':
        risk_score += 3
        risk_factors.append("内存持续增长")
    
    if memory_report['current_memory_mb'] > 300:
        risk_score += 2
        risk_factors.append("内存使用量较高")
    
    # 检查可疑对象类型的数量
    suspicious_types = ['coroutine', 'Task', 'function']
    for obj_type, count in memory_report['top_object_types']:
        if obj_type in suspicious_types and count > 1000:
            risk_score += 2
            risk_factors.append(f"{obj_type}对象数量过多({count:,})")
    
    # 风险等级
    if risk_score >= 6:
        risk_level = "🔴 高风险"
    elif risk_score >= 3:
        risk_level = "🟡 中风险"
    else:
        risk_level = "🟢 低风险"
    
    print(f"风险等级: {risk_level} (评分: {risk_score})")
    if risk_factors:
        print("风险因素:")
        for factor in risk_factors:
            print(f"  - {factor}")
    
    # 建议
    print("\n💡 优化建议:")
    
    if memory_report['growth_trend'] == 'increasing':
        print("  - 内存持续增长，建议检查是否存在内存泄漏")
        print("  - 重点关注dict、list、coroutine等对象的增长")
    
    if memory_report['current_memory_mb'] > 200:
        print("  - 内存使用较高，建议启用更频繁的内存清理")
    
    # 检查特定的MarketPrism对象
    for obj_type, analysis in detailed_analysis.items():
        if 'websocket' in obj_type.lower() and analysis['count'] > 10:
            print(f"  - {obj_type}对象数量较多({analysis['count']}), 检查WebSocket连接是否正确关闭")
        
        if 'orderbook' in obj_type.lower() and analysis['total_size_mb'] > 50:
            print(f"  - {obj_type}占用内存较大({analysis['total_size_mb']:.1f}MB), 考虑优化订单簿缓存策略")
    
    print("\n" + "=" * 60)
    print("分析完成")


if __name__ == "__main__":
    main()
