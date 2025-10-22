#!/usr/bin/env python3
"""
内存泄漏分析脚本

使用 memory_profiler 和 objgraph 分析 collector 的内存使用情况
"""

import gc
import sys
import time
import psutil
import tracemalloc
from datetime import datetime
from typing import Dict, List, Tuple
import json


class MemoryAnalyzer:
    """内存分析器"""
    
    def __init__(self):
        self.process = psutil.Process()
        self.snapshots = []
        
    def get_memory_info(self) -> Dict:
        """获取当前内存信息"""
        mem_info = self.process.memory_info()
        return {
            "timestamp": datetime.now().isoformat(),
            "rss_mb": mem_info.rss / 1024 / 1024,
            "vms_mb": mem_info.vms / 1024 / 1024,
            "percent": self.process.memory_percent(),
        }
    
    def get_object_counts(self) -> Dict[str, int]:
        """获取各类型对象的数量"""
        gc.collect()
        
        type_counts = {}
        for obj in gc.get_objects():
            obj_type = type(obj).__name__
            type_counts[obj_type] = type_counts.get(obj_type, 0) + 1
        
        # 按数量排序，返回前 20 个
        sorted_counts = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
        return dict(sorted_counts[:20])
    
    def get_gc_stats(self) -> Dict:
        """获取 GC 统计信息"""
        gc_stats = gc.get_stats()
        return {
            "gen0": gc_stats[0] if len(gc_stats) > 0 else {},
            "gen1": gc_stats[1] if len(gc_stats) > 1 else {},
            "gen2": gc_stats[2] if len(gc_stats) > 2 else {},
            "count": gc.get_count(),
            "threshold": gc.get_threshold(),
        }
    
    def take_snapshot(self) -> Dict:
        """拍摄内存快照"""
        snapshot = {
            "memory": self.get_memory_info(),
            "objects": self.get_object_counts(),
            "gc": self.get_gc_stats(),
        }
        self.snapshots.append(snapshot)
        return snapshot
    
    def compare_snapshots(self, idx1: int = -2, idx2: int = -1) -> Dict:
        """比较两个快照"""
        if len(self.snapshots) < 2:
            return {"error": "需要至少 2 个快照"}
        
        snap1 = self.snapshots[idx1]
        snap2 = self.snapshots[idx2]
        
        # 内存变化
        mem_diff = {
            "rss_mb_diff": snap2["memory"]["rss_mb"] - snap1["memory"]["rss_mb"],
            "vms_mb_diff": snap2["memory"]["vms_mb"] - snap1["memory"]["vms_mb"],
            "percent_diff": snap2["memory"]["percent"] - snap1["memory"]["percent"],
        }
        
        # 对象数量变化
        obj_diff = {}
        all_types = set(snap1["objects"].keys()) | set(snap2["objects"].keys())
        for obj_type in all_types:
            count1 = snap1["objects"].get(obj_type, 0)
            count2 = snap2["objects"].get(obj_type, 0)
            diff = count2 - count1
            if diff != 0:
                obj_diff[obj_type] = {
                    "before": count1,
                    "after": count2,
                    "diff": diff,
                }
        
        # 按变化量排序
        sorted_obj_diff = dict(sorted(obj_diff.items(), key=lambda x: abs(x[1]["diff"]), reverse=True)[:20])
        
        return {
            "memory_diff": mem_diff,
            "object_diff": sorted_obj_diff,
            "time_diff": snap2["memory"]["timestamp"],
        }
    
    def print_snapshot(self, snapshot: Dict):
        """打印快照信息"""
        print("\n" + "=" * 80)
        print(f"📊 内存快照 - {snapshot['memory']['timestamp']}")
        print("=" * 80)
        
        print(f"\n💾 内存使用:")
        print(f"  RSS: {snapshot['memory']['rss_mb']:.2f} MB")
        print(f"  VMS: {snapshot['memory']['vms_mb']:.2f} MB")
        print(f"  Percent: {snapshot['memory']['percent']:.2f}%")
        
        print(f"\n🔢 对象数量 (Top 10):")
        for i, (obj_type, count) in enumerate(list(snapshot['objects'].items())[:10], 1):
            print(f"  {i:2d}. {obj_type:30s}: {count:>10,}")
        
        print(f"\n🗑️  GC 统计:")
        gc_info = snapshot['gc']
        print(f"  Count: {gc_info['count']}")
        print(f"  Threshold: {gc_info['threshold']}")
    
    def print_comparison(self, comparison: Dict):
        """打印比较结果"""
        print("\n" + "=" * 80)
        print(f"📈 快照比较 - {comparison['time_diff']}")
        print("=" * 80)
        
        mem_diff = comparison['memory_diff']
        print(f"\n💾 内存变化:")
        print(f"  RSS: {mem_diff['rss_mb_diff']:+.2f} MB")
        print(f"  VMS: {mem_diff['vms_mb_diff']:+.2f} MB")
        print(f"  Percent: {mem_diff['percent_diff']:+.2f}%")
        
        print(f"\n🔢 对象数量变化 (Top 10):")
        for i, (obj_type, info) in enumerate(list(comparison['object_diff'].items())[:10], 1):
            print(f"  {i:2d}. {obj_type:30s}: {info['before']:>10,} → {info['after']:>10,} ({info['diff']:+,})")
    
    def save_report(self, filename: str = "memory_analysis_report.json"):
        """保存分析报告"""
        report = {
            "analysis_time": datetime.now().isoformat(),
            "snapshots": self.snapshots,
            "summary": {
                "total_snapshots": len(self.snapshots),
                "memory_growth": None,
                "top_growing_objects": None,
            }
        }
        
        if len(self.snapshots) >= 2:
            first = self.snapshots[0]
            last = self.snapshots[-1]
            report["summary"]["memory_growth"] = {
                "rss_mb": last["memory"]["rss_mb"] - first["memory"]["rss_mb"],
                "vms_mb": last["memory"]["vms_mb"] - first["memory"]["vms_mb"],
            }
            
            comparison = self.compare_snapshots(0, -1)
            report["summary"]["top_growing_objects"] = list(comparison["object_diff"].items())[:10]
        
        with open(filename, "w") as f:
            json.dump(report, f, indent=2)
        
        print(f"\n✅ 报告已保存到: {filename}")


def analyze_tracemalloc(duration: int = 60):
    """使用 tracemalloc 分析内存分配"""
    print(f"\n🔍 开始 tracemalloc 分析 (持续 {duration} 秒)...")
    
    tracemalloc.start()
    
    # 拍摄初始快照
    snapshot1 = tracemalloc.take_snapshot()
    print(f"  ✅ 初始快照已拍摄")
    
    # 等待一段时间
    print(f"  ⏳ 等待 {duration} 秒...")
    time.sleep(duration)
    
    # 拍摄最终快照
    snapshot2 = tracemalloc.take_snapshot()
    print(f"  ✅ 最终快照已拍摄")
    
    # 比较快照
    top_stats = snapshot2.compare_to(snapshot1, 'lineno')
    
    print(f"\n📊 内存分配增长 Top 10:")
    print("=" * 80)
    for i, stat in enumerate(top_stats[:10], 1):
        print(f"{i:2d}. {stat}")
    
    tracemalloc.stop()


def main():
    """主函数"""
    print("=" * 80)
    print("🔬 MarketPrism Collector 内存分析工具")
    print("=" * 80)
    
    analyzer = MemoryAnalyzer()
    
    # 拍摄初始快照
    print("\n📸 拍摄初始快照...")
    snapshot1 = analyzer.take_snapshot()
    analyzer.print_snapshot(snapshot1)
    
    # 等待 30 秒
    print("\n⏳ 等待 30 秒...")
    time.sleep(30)
    
    # 拍摄第二个快照
    print("\n📸 拍摄第二个快照...")
    snapshot2 = analyzer.take_snapshot()
    analyzer.print_snapshot(snapshot2)
    
    # 比较快照
    print("\n🔍 比较快照...")
    comparison = analyzer.compare_snapshots()
    analyzer.print_comparison(comparison)
    
    # 等待 30 秒
    print("\n⏳ 等待 30 秒...")
    time.sleep(30)
    
    # 拍摄第三个快照
    print("\n📸 拍摄第三个快照...")
    snapshot3 = analyzer.take_snapshot()
    analyzer.print_snapshot(snapshot3)
    
    # 比较快照
    print("\n🔍 比较快照...")
    comparison = analyzer.compare_snapshots()
    analyzer.print_comparison(comparison)
    
    # 保存报告
    analyzer.save_report("/app/memory_analysis_report.json")
    
    # 使用 tracemalloc 进行更详细的分析
    if "--tracemalloc" in sys.argv:
        analyze_tracemalloc(duration=60)
    
    print("\n✅ 分析完成！")


if __name__ == "__main__":
    main()

