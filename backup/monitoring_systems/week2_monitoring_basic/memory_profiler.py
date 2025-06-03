"""
内存使用分析器 - 第二阶段性能优化第一天实施

提供企业级内存监控和分析功能，包括内存泄漏检测、快照分析等
符合MarketPrism性能调优方案 v2.0
"""

import tracemalloc
import gc
import psutil
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
import structlog
from dataclasses import dataclass


@dataclass
class MemorySnapshot:
    """内存快照数据结构"""
    label: str
    timestamp: float
    memory_mb: float
    memory_delta: float
    snapshot: Any
    top_allocations: List[Dict]


class MemoryProfiler:
    """内存使用分析器 - 第一天实施目标"""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
        self.snapshots: List[MemorySnapshot] = []
        self.baseline_memory: Optional[float] = None
        self.is_profiling = False
        self.start_time = None
        
        # TDD改进：添加enabled属性
        self.enabled = True
        
    def start_profiling(self):
        """开始内存分析"""
        if self.is_profiling:
            self.logger.warning("内存分析已在运行中")
            return
            
        tracemalloc.start()
        self.baseline_memory = self._get_memory_usage()
        self.start_time = time.time()
        self.is_profiling = True
        
        self.logger.info(
            "内存分析已启动",
            baseline_mb=self.baseline_memory,
            start_time=datetime.fromtimestamp(self.start_time).isoformat()
        )
    
    def stop_profiling(self):
        """停止内存分析"""
        if not self.is_profiling:
            self.logger.warning("内存分析未在运行")
            return
            
        tracemalloc.stop()
        self.is_profiling = False
        
        duration = time.time() - self.start_time if self.start_time else 0
        final_memory = self._get_memory_usage()
        total_growth = final_memory - self.baseline_memory if self.baseline_memory else 0
        
        self.logger.info(
            "内存分析已停止",
            duration_seconds=duration,
            final_memory_mb=final_memory,
            total_growth_mb=total_growth,
            snapshots_count=len(self.snapshots)
        )
    
    def take_snapshot(self, label: str = "") -> Optional[MemorySnapshot]:
        """拍摄内存快照"""
        if not tracemalloc.is_tracing():
            self.logger.error("内存分析未启动，无法拍摄快照")
            return None
            
        snapshot = tracemalloc.take_snapshot()
        current_memory = self._get_memory_usage()
        memory_delta = current_memory - self.baseline_memory if self.baseline_memory else 0
        
        # 分析内存分配热点
        top_allocations = self._analyze_allocations(snapshot)
        
        snapshot_info = MemorySnapshot(
            label=label or f"snapshot_{len(self.snapshots) + 1}",
            timestamp=time.time(),
            memory_mb=current_memory,
            memory_delta=memory_delta,
            snapshot=snapshot,
            top_allocations=top_allocations
        )
        
        self.snapshots.append(snapshot_info)
        
        self.logger.info(
            "内存快照已拍摄",
            label=snapshot_info.label,
            memory_mb=current_memory,
            delta_mb=memory_delta,
            top_allocation_size_mb=top_allocations[0]['size_mb'] if top_allocations else 0
        )
        
        return snapshot_info
    
    def analyze_top_allocations(self, limit: int = 10) -> List[Dict]:
        """分析内存分配热点"""
        if not self.snapshots:
            return []
            
        latest_snapshot = self.snapshots[-1].snapshot
        return self._analyze_allocations(latest_snapshot, limit)
    
    def _analyze_allocations(self, snapshot, limit: int = 10) -> List[Dict]:
        """分析快照中的内存分配"""
        top_stats = snapshot.statistics('lineno')
        
        allocations = []
        for stat in top_stats[:limit]:
            # 获取文件路径和行号
            traceback_info = stat.traceback.format()
            file_info = traceback_info[0] if traceback_info else "Unknown"
            
            allocations.append({
                'file': file_info,
                'size_mb': stat.size / 1024 / 1024,
                'size_bytes': stat.size,
                'count': stat.count,
                'average_size': stat.size / stat.count if stat.count > 0 else 0
            })
            
        return allocations
    
    def compare_snapshots(self, snapshot1_idx: int = 0, snapshot2_idx: int = -1) -> Dict:
        """比较两个快照的差异"""
        if len(self.snapshots) < 2:
            return {"error": "需要至少2个快照才能进行比较"}
            
        snap1 = self.snapshots[snapshot1_idx]
        snap2 = self.snapshots[snapshot2_idx]
        
        memory_diff = snap2.memory_mb - snap1.memory_mb
        time_diff = snap2.timestamp - snap1.timestamp
        
        return {
            'snapshot1': {
                'label': snap1.label,
                'memory_mb': snap1.memory_mb,
                'timestamp': snap1.timestamp
            },
            'snapshot2': {
                'label': snap2.label,
                'memory_mb': snap2.memory_mb,
                'timestamp': snap2.timestamp
            },
            'difference': {
                'memory_diff_mb': memory_diff,
                'time_diff_seconds': time_diff,
                'memory_growth_rate_mb_per_sec': memory_diff / time_diff if time_diff > 0 else 0
            }
        }
    
    def detect_memory_leaks(self, threshold_mb: float = 10.0) -> List[Dict]:
        """检测潜在的内存泄漏"""
        if len(self.snapshots) < 3:
            return []
            
        leaks = []
        
        # 检查连续增长的内存使用
        for i in range(2, len(self.snapshots)):
            prev_snap = self.snapshots[i-2]
            curr_snap = self.snapshots[i]
            
            growth = curr_snap.memory_mb - prev_snap.memory_mb
            time_span = curr_snap.timestamp - prev_snap.timestamp
            
            if growth > threshold_mb and time_span > 0:
                growth_rate = growth / time_span
                
                leaks.append({
                    'start_snapshot': prev_snap.label,
                    'end_snapshot': curr_snap.label,
                    'memory_growth_mb': growth,
                    'time_span_seconds': time_span,
                    'growth_rate_mb_per_sec': growth_rate,
                    'severity': 'high' if growth_rate > 1.0 else 'medium'
                })
        
        return leaks
    
    def get_memory_summary(self) -> Dict:
        """获取内存使用摘要"""
        current_memory = self._get_memory_usage()
        
        summary = {
            'current_memory_mb': current_memory,
            'baseline_memory_mb': self.baseline_memory,
            'total_growth_mb': current_memory - self.baseline_memory if self.baseline_memory else 0,
            'snapshots_count': len(self.snapshots),
            'is_profiling': self.is_profiling
        }
        
        if self.snapshots:
            memory_values = [s.memory_mb for s in self.snapshots]
            summary.update({
                'min_memory_mb': min(memory_values),
                'max_memory_mb': max(memory_values),
                'avg_memory_mb': sum(memory_values) / len(memory_values),
                'memory_variance': self._calculate_variance(memory_values)
            })
        
        return summary
    
    def _get_memory_usage(self) -> float:
        """获取当前内存使用量(MB)"""
        try:
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except Exception as e:
            self.logger.error("获取内存使用量失败", error=str(e))
            return 0.0
    
    def _calculate_variance(self, values: List[float]) -> float:
        """计算方差"""
        if len(values) < 2:
            return 0.0
            
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance
    
    def force_gc(self) -> Dict:
        """强制垃圾回收并返回统计信息"""
        before_memory = self._get_memory_usage()
        
        # 执行垃圾回收
        collected_objects = gc.collect()
        
        after_memory = self._get_memory_usage()
        memory_freed = before_memory - after_memory
        
        gc_stats = {
            'before_memory_mb': before_memory,
            'after_memory_mb': after_memory,
            'memory_freed_mb': memory_freed,
            'collected_objects': collected_objects,
            'gc_counts': gc.get_count()
        }
        
        self.logger.info(
            "强制垃圾回收完成",
            **gc_stats
        )
        
        return gc_stats
    
    def export_report(self, filepath: str = None) -> str:
        """导出内存分析报告"""
        if not filepath:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"memory_report_{timestamp}.json"
        
        report = {
            'analysis_info': {
                'start_time': self.start_time,
                'baseline_memory_mb': self.baseline_memory,
                'snapshots_count': len(self.snapshots),
                'is_profiling': self.is_profiling
            },
            'memory_summary': self.get_memory_summary(),
            'snapshots': [
                {
                    'label': s.label,
                    'timestamp': s.timestamp,
                    'memory_mb': s.memory_mb,
                    'memory_delta': s.memory_delta,
                    'top_allocations': s.top_allocations[:5]  # 只保存前5个
                }
                for s in self.snapshots
            ],
            'memory_leaks': self.detect_memory_leaks(),
            'recommendations': self._generate_recommendations()
        }
        
        import json
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        self.logger.info("内存分析报告已导出", filepath=filepath)
        return filepath
    
    def _generate_recommendations(self) -> List[str]:
        """生成优化建议"""
        recommendations = []
        summary = self.get_memory_summary()
        
        # 基于内存增长给出建议
        if summary.get('total_growth_mb', 0) > 100:
            recommendations.append("内存增长超过100MB，建议检查是否存在内存泄漏")
        
        # 基于内存方差给出建议
        if summary.get('memory_variance', 0) > 1000:
            recommendations.append("内存使用波动较大，建议优化内存分配策略")
        
        # 检查潜在泄漏
        leaks = self.detect_memory_leaks()
        if leaks:
            recommendations.append(f"检测到{len(leaks)}个潜在内存泄漏，建议详细分析")
        
        # 基于当前内存使用给出建议
        current_memory = summary.get('current_memory_mb', 0)
        if current_memory > 500:
            recommendations.append("当前内存使用超过500MB，建议实施对象池优化")
        
        if not recommendations:
            recommendations.append("内存使用状况良好，可以继续监控")
        
        return recommendations

    # TDD改进：添加期望的方法
    def get_memory_usage(self) -> float:
        """TDD改进：获取当前内存使用量（MB）"""
        return self._get_memory_usage()
    
    def get_stats(self) -> Dict[str, Any]:
        """TDD改进：获取内存统计信息"""
        if not self.is_profiling:
            return {
                'enabled': self.enabled,
                'is_profiling': False,
                'memory_usage_mb': self._get_memory_usage(),
                'snapshots_count': len(self.snapshots),
                'message': '内存分析未启动'
            }
        
        current_memory = self._get_memory_usage()
        memory_delta = current_memory - (self.baseline_memory or 0)
        profiling_duration = time.time() - (self.start_time or time.time())
        
        return {
            'enabled': self.enabled,
            'is_profiling': self.is_profiling,
            'memory_usage_mb': current_memory,
            'baseline_memory_mb': self.baseline_memory,
            'memory_delta_mb': memory_delta,
            'profiling_duration_seconds': profiling_duration,
            'snapshots_count': len(self.snapshots),
            'gc_objects_count': len(gc.get_objects()),
            'start_time': self.start_time
        }


# 全局内存分析器实例
_memory_profiler_instance = None

def get_memory_profiler() -> MemoryProfiler:
    """获取全局内存分析器实例"""
    global _memory_profiler_instance
    if _memory_profiler_instance is None:
        _memory_profiler_instance = MemoryProfiler()
    return _memory_profiler_instance


# 便捷函数
def start_memory_profiling():
    """启动内存分析"""
    profiler = get_memory_profiler()
    profiler.start_profiling()


def take_memory_snapshot(label: str = ""):
    """拍摄内存快照"""
    profiler = get_memory_profiler()
    return profiler.take_snapshot(label)


def get_memory_summary():
    """获取内存摘要"""
    profiler = get_memory_profiler()
    return profiler.get_memory_summary()


def export_memory_report(filepath: str = None):
    """导出内存报告"""
    profiler = get_memory_profiler()
    return profiler.export_report(filepath)