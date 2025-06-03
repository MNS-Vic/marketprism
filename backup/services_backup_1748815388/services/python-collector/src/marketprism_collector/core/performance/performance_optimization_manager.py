"""
🚀 PerformanceOptimizationManager - 性能优化管理器

整合所有性能优化组件，提供统一的性能优化接口
协调缓存、连接池、负载均衡、异步处理、内存和IO优化
"""

import asyncio
import time
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum
import logging

from .cache_optimizer import CacheOptimizer, CacheConfig
from .connection_pool_manager import ConnectionPoolManager, ConnectionConfig
from .load_balancing_optimizer import LoadBalancingOptimizer, LoadBalancingConfig
from .async_processing_engine import AsyncProcessingEngine, ProcessingConfig
from .memory_optimizer import MemoryOptimizer, MemoryConfig
from .io_optimizer import IOOptimizer, IOConfig

logger = logging.getLogger(__name__)


class OptimizationLevel(Enum):
    """优化级别枚举"""
    BASIC = "basic"            # 基础优化
    STANDARD = "standard"      # 标准优化
    AGGRESSIVE = "aggressive"  # 激进优化
    ADAPTIVE = "adaptive"      # 自适应优化


class OptimizationTarget(Enum):
    """优化目标枚举"""
    THROUGHPUT = "throughput"      # 吞吐量
    LATENCY = "latency"           # 延迟
    MEMORY = "memory"             # 内存使用
    CPU = "cpu"                   # CPU使用
    BALANCED = "balanced"         # 平衡优化


@dataclass
class PerformanceConfig:
    """性能优化配置"""
    optimization_level: OptimizationLevel = OptimizationLevel.ADAPTIVE
    optimization_target: OptimizationTarget = OptimizationTarget.BALANCED
    
    # 各组件配置
    cache_config: Optional[CacheConfig] = None
    connection_config: Optional[ConnectionConfig] = None
    load_balancing_config: Optional[LoadBalancingConfig] = None
    processing_config: Optional[ProcessingConfig] = None
    memory_config: Optional[MemoryConfig] = None
    io_config: Optional[IOConfig] = None
    
    # 全局配置
    enable_auto_optimization: bool = True
    optimization_interval: float = 300.0  # 5分钟
    monitoring_interval: float = 60.0     # 1分钟
    metrics_retention_hours: int = 24


@dataclass
class PerformanceMetrics:
    """性能指标"""
    timestamp: float = field(default_factory=time.time)
    
    # 系统级指标
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    disk_usage: float = 0.0
    network_usage: float = 0.0
    
    # 应用级指标
    throughput: float = 0.0          # 请求/秒
    avg_response_time: float = 0.0   # 平均响应时间
    error_rate: float = 0.0          # 错误率
    active_connections: int = 0      # 活跃连接数
    
    # 优化器指标
    cache_hit_rate: float = 0.0
    pool_utilization: float = 0.0
    queue_utilization: float = 0.0
    compression_ratio: float = 0.0
    
    # 性能评分
    overall_score: float = 0.0       # 综合性能评分 (0-100)


class PerformanceOptimizationManager:
    """
    🚀 性能优化管理器
    
    整合所有性能优化组件，提供统一的性能优化和监控接口
    """
    
    def __init__(self, config: Optional[PerformanceConfig] = None):
        self.config = config or PerformanceConfig()
        
        # 初始化各优化组件
        self.cache_optimizer = CacheOptimizer(self.config.cache_config)
        self.connection_manager = ConnectionPoolManager()
        self.load_balancer = LoadBalancingOptimizer(self.config.load_balancing_config)
        self.async_engine = AsyncProcessingEngine(self.config.processing_config)
        self.memory_optimizer = MemoryOptimizer(self.config.memory_config)
        self.io_optimizer = IOOptimizer(self.config.io_config)
        
        # 性能监控
        self.metrics_history: List[PerformanceMetrics] = []
        self.current_metrics = PerformanceMetrics()
        self.optimization_history: List[Dict[str, Any]] = []
        
        # 任务管理
        self.monitoring_task: Optional[asyncio.Task] = None
        self.optimization_task: Optional[asyncio.Task] = None
        self.is_running = False
        
        logger.info(f"PerformanceOptimizationManager初始化: level={self.config.optimization_level.value}")
    
    async def start(self):
        """启动性能优化管理器"""
        if self.is_running:
            return
        
        self.is_running = True
        
        # 启动各优化组件
        await self.cache_optimizer.start()
        await self.connection_manager.start()
        await self.load_balancer.start()
        await self.async_engine.start()
        await self.memory_optimizer.start()
        await self.io_optimizer.start()
        
        # 启动监控任务
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        # 启动自动优化
        if self.config.enable_auto_optimization:
            self.optimization_task = asyncio.create_task(self._optimization_loop())
        
        logger.info("PerformanceOptimizationManager已启动")
    
    async def stop(self):
        """停止性能优化管理器"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # 取消任务
        if self.monitoring_task:
            self.monitoring_task.cancel()
        if self.optimization_task:
            self.optimization_task.cancel()
        
        # 停止各优化组件
        await self.cache_optimizer.stop()
        await self.connection_manager.stop()
        await self.load_balancer.stop()
        await self.async_engine.stop()
        await self.memory_optimizer.stop()
        await self.io_optimizer.stop()
        
        logger.info("PerformanceOptimizationManager已停止")
    
    async def optimize_performance(self) -> Dict[str, Any]:
        """执行性能优化"""
        optimization_start = time.time()
        optimization_result = {
            "timestamp": optimization_start,
            "level": self.config.optimization_level.value,
            "target": self.config.optimization_target.value,
            "actions": [],
            "before_metrics": self.current_metrics,
            "after_metrics": None,
            "improvements": {}
        }
        
        try:
            # 获取当前性能指标
            await self._collect_metrics()
            optimization_result["before_metrics"] = self.current_metrics
            
            # 根据优化级别执行不同策略
            if self.config.optimization_level == OptimizationLevel.BASIC:
                await self._basic_optimization(optimization_result)
            elif self.config.optimization_level == OptimizationLevel.STANDARD:
                await self._standard_optimization(optimization_result)
            elif self.config.optimization_level == OptimizationLevel.AGGRESSIVE:
                await self._aggressive_optimization(optimization_result)
            elif self.config.optimization_level == OptimizationLevel.ADAPTIVE:
                await self._adaptive_optimization(optimization_result)
            
            # 等待优化生效
            await asyncio.sleep(5)
            
            # 收集优化后指标
            await self._collect_metrics()
            optimization_result["after_metrics"] = self.current_metrics
            
            # 计算改进幅度
            optimization_result["improvements"] = self._calculate_improvements(
                optimization_result["before_metrics"],
                optimization_result["after_metrics"]
            )
            
            optimization_result["duration"] = time.time() - optimization_start
            optimization_result["success"] = True
            
            # 记录优化历史
            self.optimization_history.append(optimization_result)
            
            logger.info(f"性能优化完成: {len(optimization_result['actions'])} 个优化动作")
            return optimization_result
        
        except Exception as e:
            optimization_result["error"] = str(e)
            optimization_result["success"] = False
            logger.error(f"性能优化失败: {e}")
            return optimization_result
    
    async def _basic_optimization(self, result: Dict[str, Any]):
        """基础优化"""
        actions = []
        
        # 内存优化
        if self.current_metrics.memory_usage > 80:
            memory_result = self.memory_optimizer.optimize_memory()
            actions.append(f"内存优化: 回收 {memory_result.get('memory_saved', 0)} 字节")
        
        # 缓存清理
        cache_stats = self.cache_optimizer.get_stats()
        if isinstance(cache_stats, dict):
            for level, stats in cache_stats.items():
                if isinstance(stats, dict) and stats.get('hit_rate', 1.0) < 0.5:
                    await self.cache_optimizer.clear()
                    actions.append("清理低效缓存")
                    break
        
        result["actions"].extend(actions)
    
    async def _standard_optimization(self, result: Dict[str, Any]):
        """标准优化"""
        actions = []
        
        # 执行基础优化
        await self._basic_optimization(result)
        
        # 连接池优化
        pool_stats = self.connection_manager.get_global_stats()
        if pool_stats.get("avg_utilization", 0) > 0.8:
            actions.append("连接池利用率优化（需要手动调整配置）")
        
        # 异步处理优化
        async_stats = self.async_engine.get_metrics()
        if async_stats.get("queue_utilization", 0) > 0.8:
            actions.append("异步队列优化（需要增加工作者）")
        
        # 负载均衡优化
        lb_stats = self.load_balancer.get_stats()
        if lb_stats.get("available_servers", 0) < lb_stats.get("total_servers", 1):
            actions.append("负载均衡服务器健康检查")
        
        result["actions"].extend(actions)
    
    async def _aggressive_optimization(self, result: Dict[str, Any]):
        """激进优化"""
        actions = []
        
        # 执行标准优化
        await self._standard_optimization(result)
        
        # 强制垃圾回收
        gc_result = self.memory_optimizer.force_gc()
        actions.append(f"强制垃圾回收: {gc_result}")
        
        # IO优化
        io_optimization = self.io_optimizer.optimize_config()
        if io_optimization.get("optimizations"):
            actions.append(f"IO配置优化: {len(io_optimization['optimizations'])} 项")
        
        result["actions"].extend(actions)
    
    async def _adaptive_optimization(self, result: Dict[str, Any]):
        """自适应优化"""
        actions = []
        
        # 根据当前性能状况选择优化策略
        if self.current_metrics.overall_score < 60:
            # 性能较差，执行激进优化
            await self._aggressive_optimization(result)
            actions.append("执行激进优化（性能评分较低）")
        elif self.current_metrics.overall_score < 80:
            # 性能一般，执行标准优化
            await self._standard_optimization(result)
            actions.append("执行标准优化（性能评分中等）")
        else:
            # 性能良好，执行基础优化
            await self._basic_optimization(result)
            actions.append("执行基础优化（性能评分良好）")
        
        result["actions"].extend(actions)
    
    def get_performance_dashboard(self) -> Dict[str, Any]:
        """获取性能仪表板"""
        dashboard = {
            "timestamp": time.time(),
            "current_metrics": self._metrics_to_dict(self.current_metrics),
            "component_stats": {
                "cache": self.cache_optimizer.get_analysis(),
                "connections": self.connection_manager.get_global_stats(),
                "load_balancer": self.load_balancer.get_stats(),
                "async_engine": self.async_engine.get_metrics(),
                "memory": self.memory_optimizer.get_memory_stats(),
                "io": self.io_optimizer.get_stats()
            },
            "optimization_history": self.optimization_history[-10:],  # 最近10次优化
            "recommendations": self._get_optimization_recommendations()
        }
        
        return dashboard
    
    def get_performance_report(self) -> Dict[str, Any]:
        """生成性能报告"""
        if not self.metrics_history:
            return {"error": "没有足够的性能数据"}
        
        # 计算性能趋势
        recent_metrics = self.metrics_history[-60:]  # 最近60个数据点
        
        report = {
            "period": {
                "start": recent_metrics[0].timestamp if recent_metrics else 0,
                "end": recent_metrics[-1].timestamp if recent_metrics else 0,
                "duration_hours": len(recent_metrics) / 60 if recent_metrics else 0
            },
            "performance_trends": {
                "throughput": self._calculate_trend([m.throughput for m in recent_metrics]),
                "response_time": self._calculate_trend([m.avg_response_time for m in recent_metrics]),
                "memory_usage": self._calculate_trend([m.memory_usage for m in recent_metrics]),
                "error_rate": self._calculate_trend([m.error_rate for m in recent_metrics])
            },
            "peak_performance": {
                "max_throughput": max([m.throughput for m in recent_metrics]) if recent_metrics else 0,
                "min_response_time": min([m.avg_response_time for m in recent_metrics]) if recent_metrics else 0,
                "peak_connections": max([m.active_connections for m in recent_metrics]) if recent_metrics else 0
            },
            "optimization_effectiveness": self._analyze_optimization_effectiveness(),
            "recommendations": self._get_performance_recommendations()
        }
        
        return report
    
    def _metrics_to_dict(self, metrics: PerformanceMetrics) -> Dict[str, Any]:
        """将指标转换为字典"""
        return {
            "timestamp": metrics.timestamp,
            "cpu_usage": metrics.cpu_usage,
            "memory_usage": metrics.memory_usage,
            "disk_usage": metrics.disk_usage,
            "network_usage": metrics.network_usage,
            "throughput": metrics.throughput,
            "avg_response_time": metrics.avg_response_time,
            "error_rate": metrics.error_rate,
            "active_connections": metrics.active_connections,
            "cache_hit_rate": metrics.cache_hit_rate,
            "pool_utilization": metrics.pool_utilization,
            "queue_utilization": metrics.queue_utilization,
            "compression_ratio": metrics.compression_ratio,
            "overall_score": metrics.overall_score
        }
    
    async def _monitoring_loop(self):
        """监控循环"""
        while self.is_running:
            try:
                await asyncio.sleep(self.config.monitoring_interval)
                await self._collect_metrics()
                self._cleanup_old_metrics()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"性能监控失败: {e}")
    
    async def _optimization_loop(self):
        """自动优化循环"""
        while self.is_running:
            try:
                await asyncio.sleep(self.config.optimization_interval)
                if self._should_optimize():
                    await self.optimize_performance()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"自动优化失败: {e}")
    
    async def _collect_metrics(self):
        """收集性能指标"""
        try:
            metrics = PerformanceMetrics()
            
            # 收集各组件指标
            cache_stats = self.cache_optimizer.get_stats()
            if isinstance(cache_stats, dict):
                # 计算整体缓存命中率
                total_hits = 0
                total_requests = 0
                for level_stats in cache_stats.values():
                    if isinstance(level_stats, dict):
                        total_hits += level_stats.get('hits', 0)
                        total_requests += level_stats.get('hits', 0) + level_stats.get('misses', 0)
                
                if total_requests > 0:
                    metrics.cache_hit_rate = total_hits / total_requests
            
            # 连接池指标
            pool_stats = self.connection_manager.get_global_stats()
            metrics.active_connections = pool_stats.get('active_connections', 0)
            metrics.pool_utilization = pool_stats.get('avg_utilization', 0)
            
            # 异步引擎指标
            async_stats = self.async_engine.get_metrics()
            metrics.queue_utilization = async_stats.get('queue_utilization', 0)
            
            # 内存指标
            memory_stats = self.memory_optimizer.get_memory_stats()
            if 'system_memory' in memory_stats:
                metrics.memory_usage = memory_stats['system_memory'].get('percent', 0)
            
            # IO指标
            io_stats = self.io_optimizer.get_stats()
            if 'compression' in io_stats:
                metrics.compression_ratio = io_stats['compression'].get('compression_ratio', 0)
            
            # 计算综合性能评分
            metrics.overall_score = self._calculate_performance_score(metrics)
            
            self.current_metrics = metrics
            self.metrics_history.append(metrics)
            
        except Exception as e:
            logger.error(f"指标收集失败: {e}")
    
    def _calculate_performance_score(self, metrics: PerformanceMetrics) -> float:
        """计算性能评分"""
        # 基础评分100分
        score = 100.0
        
        # 内存使用惩罚
        if metrics.memory_usage > 80:
            score -= (metrics.memory_usage - 80) * 2
        
        # 响应时间惩罚
        if metrics.avg_response_time > 1.0:
            score -= min(metrics.avg_response_time * 10, 30)
        
        # 错误率惩罚
        score -= metrics.error_rate * 50
        
        # 缓存命中率奖励
        score += (metrics.cache_hit_rate - 0.5) * 20 if metrics.cache_hit_rate > 0.5 else 0
        
        # 资源利用率优化
        optimal_utilization = 0.7
        if metrics.pool_utilization > 0:
            utilization_diff = abs(metrics.pool_utilization - optimal_utilization)
            score -= utilization_diff * 30
        
        return max(0.0, min(100.0, score))
    
    def _should_optimize(self) -> bool:
        """判断是否需要优化"""
        if self.current_metrics.overall_score < 70:
            return True
        
        if self.current_metrics.memory_usage > 85:
            return True
        
        if self.current_metrics.error_rate > 0.05:
            return True
        
        return False
    
    def _cleanup_old_metrics(self):
        """清理旧指标"""
        cutoff_time = time.time() - (self.config.metrics_retention_hours * 3600)
        self.metrics_history = [
            m for m in self.metrics_history 
            if m.timestamp > cutoff_time
        ]
    
    def _calculate_trend(self, values: List[float]) -> Dict[str, float]:
        """计算趋势"""
        if len(values) < 2:
            return {"trend": 0.0, "change_percent": 0.0}
        
        recent_avg = sum(values[-10:]) / len(values[-10:])
        earlier_avg = sum(values[:10]) / len(values[:10])
        
        change_percent = ((recent_avg - earlier_avg) / earlier_avg * 100) if earlier_avg != 0 else 0
        
        return {
            "trend": recent_avg - earlier_avg,
            "change_percent": change_percent
        }
    
    def _calculate_improvements(self, before: PerformanceMetrics, 
                              after: PerformanceMetrics) -> Dict[str, float]:
        """计算改进幅度"""
        improvements = {}
        
        # 性能评分改进
        improvements["overall_score"] = after.overall_score - before.overall_score
        
        # 内存使用改进
        improvements["memory_usage"] = before.memory_usage - after.memory_usage
        
        # 缓存命中率改进
        improvements["cache_hit_rate"] = after.cache_hit_rate - before.cache_hit_rate
        
        # 响应时间改进
        improvements["response_time"] = before.avg_response_time - after.avg_response_time
        
        return improvements
    
    def _analyze_optimization_effectiveness(self) -> Dict[str, Any]:
        """分析优化效果"""
        if len(self.optimization_history) < 2:
            return {"insufficient_data": True}
        
        recent_optimizations = self.optimization_history[-5:]
        effectiveness = {
            "total_optimizations": len(self.optimization_history),
            "success_rate": sum(1 for opt in recent_optimizations if opt.get("success", False)) / len(recent_optimizations),
            "avg_improvement": {},
            "best_optimization": None,
            "recommendations": []
        }
        
        # 计算平均改进
        all_improvements = []
        for opt in recent_optimizations:
            if opt.get("success") and "improvements" in opt:
                all_improvements.append(opt["improvements"])
        
        if all_improvements:
            for metric in ["overall_score", "memory_usage", "cache_hit_rate"]:
                values = [imp.get(metric, 0) for imp in all_improvements]
                effectiveness["avg_improvement"][metric] = sum(values) / len(values)
        
        # 找出最佳优化
        best_score = -1
        for opt in recent_optimizations:
            if opt.get("success") and "improvements" in opt:
                score = opt["improvements"].get("overall_score", 0)
                if score > best_score:
                    best_score = score
                    effectiveness["best_optimization"] = opt
        
        return effectiveness
    
    def _get_optimization_recommendations(self) -> List[str]:
        """获取优化建议"""
        recommendations = []
        
        if self.current_metrics.memory_usage > 80:
            recommendations.append("内存使用率过高，建议增加内存或优化内存使用")
        
        if self.current_metrics.cache_hit_rate < 0.7:
            recommendations.append("缓存命中率偏低，建议调整缓存策略或增加缓存容量")
        
        if self.current_metrics.avg_response_time > 2.0:
            recommendations.append("响应时间过长，建议优化处理逻辑或增加处理能力")
        
        if self.current_metrics.pool_utilization > 0.9:
            recommendations.append("连接池利用率过高，建议增加连接池大小")
        
        if self.current_metrics.queue_utilization > 0.8:
            recommendations.append("任务队列利用率过高，建议增加工作者数量")
        
        return recommendations
    
    def _get_performance_recommendations(self) -> List[str]:
        """获取性能建议"""
        recommendations = []
        
        # 基于历史数据的建议
        if len(self.metrics_history) > 10:
            recent_scores = [m.overall_score for m in self.metrics_history[-10:]]
            if all(score < 70 for score in recent_scores):
                recommendations.append("系统性能持续偏低，建议进行全面性能调优")
        
        # 基于优化历史的建议
        if len(self.optimization_history) > 3:
            recent_opts = self.optimization_history[-3:]
            if all(not opt.get("success", False) for opt in recent_opts):
                recommendations.append("最近的优化效果不佳，建议检查系统配置")
        
        return recommendations