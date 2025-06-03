#!/usr/bin/env python3
"""
MarketPrism 配置性能优化系统
配置管理系统 2.0 - Week 5 Day 5

统一性能优化模块入口，提供配置性能监控、智能缓存、
优化引擎、性能分析和负载均衡的完整解决方案。

Author: MarketPrism团队
Created: 2025-01-29
Version: 1.0.0
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

# 导入核心组件
from .config_performance_monitor import (
    ConfigPerformanceMonitor,
    MetricType,
    AlertSeverity,
    PerformanceMetric,
    PerformanceAlert,
    get_performance_monitor,
    monitor_performance
)

from .config_cache import (
    MultiLevelConfigCache,
    CachePriority,
    CacheStrategy,
    CacheLevel,
    get_config_cache,
    cache_config
)

from .config_optimizer import (
    ConfigOptimizer,
    OptimizationType,
    OptimizationSeverity,
    OptimizationAction,
    OptimizationRecommendation,
    get_config_optimizer,
    optimize_config
)

from .performance_analyzer import (
    PerformanceAnalyzer,
    AnalysisType,
    TrendType,
    AnomalyType,
    BottleneckType,
    TrendAnalysis,
    AnomalyDetection,
    BottleneckAnalysis,
    PerformanceReport,
    get_performance_analyzer
)

from .config_load_balancer import (
    ConfigLoadBalancer,
    LoadBalancingStrategy,
    NodeStatus,
    FailoverStrategy,
    ConfigNode,
    LoadBalancingRequest,
    LoadBalancingResponse,
    get_config_load_balancer,
    load_balance_request
)


class ConfigPerformanceManager:
    """配置性能管理器
    
    统一管理所有性能优化组件，提供一站式的配置性能优化解决方案。
    包括监控、缓存、优化、分析和负载均衡功能。
    """
    
    def __init__(self,
                 enable_monitoring: bool = True,
                 enable_caching: bool = True,
                 enable_optimization: bool = True,
                 enable_analysis: bool = True,
                 enable_load_balancing: bool = False):
        """初始化配置性能管理器
        
        Args:
            enable_monitoring: 启用性能监控
            enable_caching: 启用智能缓存
            enable_optimization: 启用自动优化
            enable_analysis: 启用性能分析
            enable_load_balancing: 启用负载均衡
        """
        self.enable_monitoring = enable_monitoring
        self.enable_caching = enable_caching
        self.enable_optimization = enable_optimization
        self.enable_analysis = enable_analysis
        self.enable_load_balancing = enable_load_balancing
        
        # 组件实例
        self._monitor: Optional[ConfigPerformanceMonitor] = None
        self._cache: Optional[MultiLevelConfigCache] = None
        self._optimizer: Optional[ConfigOptimizer] = None
        self._analyzer: Optional[PerformanceAnalyzer] = None
        self._load_balancer: Optional[ConfigLoadBalancer] = None
        
        # 日志
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 初始化组件
        self._initialize_components()
        
    def _initialize_components(self):
        """初始化组件"""
        try:
            # 性能监控器
            if self.enable_monitoring:
                self._monitor = get_performance_monitor()
                self.logger.info("✓ 性能监控器已初始化")
                
            # 智能缓存
            if self.enable_caching:
                self._cache = get_config_cache()
                self.logger.info("✓ 智能缓存系统已初始化")
                
            # 配置优化器
            if self.enable_optimization:
                self._optimizer = get_config_optimizer()
                self.logger.info("✓ 配置优化引擎已初始化")
                
            # 性能分析器
            if self.enable_analysis:
                self._analyzer = get_performance_analyzer()
                self.logger.info("✓ 性能分析器已初始化")
                
            # 负载均衡器
            if self.enable_load_balancing:
                self._load_balancer = get_config_load_balancer()
                self.logger.info("✓ 配置负载均衡器已初始化")
                
        except Exception as e:
            self.logger.error(f"组件初始化失败: {e}")
            raise
            
    def start_all_services(self):
        """启动所有服务"""
        try:
            if self._monitor:
                self._monitor.start_monitoring()
                self.logger.info("✓ 性能监控服务已启动")
                
            if self._optimizer:
                self._optimizer.start_optimization()
                self.logger.info("✓ 优化引擎服务已启动")
                
            if self._analyzer:
                self._analyzer.start_analysis(interval_minutes=30)
                self.logger.info("✓ 性能分析服务已启动")
                
            if self._load_balancer:
                self._load_balancer.start_health_checks()
                self.logger.info("✓ 负载均衡服务已启动")
                
            self.logger.info("🚀 配置性能优化系统全部启动完成")
            
        except Exception as e:
            self.logger.error(f"服务启动失败: {e}")
            raise
            
    def stop_all_services(self):
        """停止所有服务"""
        try:
            if self._monitor:
                self._monitor.stop_monitoring()
                self.logger.info("✓ 性能监控服务已停止")
                
            if self._optimizer:
                self._optimizer.stop_optimization()
                self.logger.info("✓ 优化引擎服务已停止")
                
            if self._analyzer:
                self._analyzer.stop_analysis()
                self.logger.info("✓ 性能分析服务已停止")
                
            if self._load_balancer:
                self._load_balancer.stop_health_checks()
                self.logger.info("✓ 负载均衡服务已停止")
                
            if self._cache:
                self._cache.stop()
                self.logger.info("✓ 缓存服务已停止")
                
            self.logger.info("🛑 配置性能优化系统全部停止完成")
            
        except Exception as e:
            self.logger.error(f"服务停止失败: {e}")
            
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        status = {
            "timestamp": datetime.now().isoformat(),
            "enabled_components": {
                "monitoring": self.enable_monitoring,
                "caching": self.enable_caching,
                "optimization": self.enable_optimization,
                "analysis": self.enable_analysis,
                "load_balancing": self.enable_load_balancing
            },
            "component_status": {}
        }
        
        try:
            # 监控器状态
            if self._monitor:
                status["component_status"]["monitor"] = {
                    "active": True,
                    "summary": self._monitor.get_performance_summary()
                }
                
            # 缓存状态
            if self._cache:
                status["component_status"]["cache"] = {
                    "active": True,
                    "stats": self._cache.get_global_stats()
                }
                
            # 优化器状态
            if self._optimizer:
                status["component_status"]["optimizer"] = {
                    "active": True,
                    "summary": self._optimizer.get_optimization_summary()
                }
                
            # 分析器状态
            if self._analyzer:
                status["component_status"]["analyzer"] = {
                    "active": True,
                    "summary": self._analyzer.get_analysis_summary()
                }
                
            # 负载均衡器状态
            if self._load_balancer:
                status["component_status"]["load_balancer"] = {
                    "active": True,
                    "stats": self._load_balancer.get_load_balancer_stats()
                }
                
        except Exception as e:
            self.logger.error(f"获取系统状态失败: {e}")
            status["error"] = str(e)
            
        return status
        
    def generate_comprehensive_report(self) -> Dict[str, Any]:
        """生成综合性能报告"""
        report = {
            "report_id": f"perf_report_{int(datetime.now().timestamp())}",
            "generated_at": datetime.now().isoformat(),
            "title": "MarketPrism 配置性能综合报告",
            "summary": {},
            "components": {}
        }
        
        try:
            # 性能监控报告
            if self._monitor:
                monitor_summary = self._monitor.get_performance_summary()
                report["components"]["monitoring"] = {
                    "status": "active",
                    "summary": monitor_summary,
                    "key_metrics": {
                        "avg_latency_ms": monitor_summary.get("performance_indicators", {}).get("avg_latency_ms", 0),
                        "avg_throughput_ops": monitor_summary.get("performance_indicators", {}).get("avg_throughput_ops", 0),
                        "performance_level": monitor_summary.get("performance_indicators", {}).get("performance_level", "unknown")
                    }
                }
                
            # 缓存性能报告
            if self._cache:
                cache_stats = self._cache.get_global_stats()
                report["components"]["caching"] = {
                    "status": "active",
                    "stats": cache_stats,
                    "key_metrics": {
                        "global_hit_rate": cache_stats.get("global_hit_rate", 0),
                        "total_requests": cache_stats.get("total_requests", 0),
                        "cache_efficiency": "excellent" if cache_stats.get("global_hit_rate", 0) > 0.9 else "good" if cache_stats.get("global_hit_rate", 0) > 0.7 else "needs_improvement"
                    }
                }
                
            # 优化建议报告
            if self._optimizer:
                optimizer_summary = self._optimizer.get_optimization_summary()
                recent_recommendations = self._optimizer.get_recommendations(limit=10)
                report["components"]["optimization"] = {
                    "status": "active",
                    "summary": optimizer_summary,
                    "recent_recommendations": [rec.to_dict() for rec in recent_recommendations],
                    "key_metrics": {
                        "total_recommendations": optimizer_summary.get("summary", {}).get("total_recommendations", 0),
                        "applied_recommendations": optimizer_summary.get("summary", {}).get("applied_recommendations", 0),
                        "success_rate": optimizer_summary.get("summary", {}).get("success_rate", 0)
                    }
                }
                
            # 性能分析报告
            if self._analyzer:
                analyzer_summary = self._analyzer.get_analysis_summary()
                performance_report = self._analyzer.generate_performance_report(include_charts=False)
                report["components"]["analysis"] = {
                    "status": "active",
                    "summary": analyzer_summary,
                    "performance_report": performance_report.to_dict(),
                    "key_metrics": {
                        "recent_trends": analyzer_summary.get("recent_trends", 0),
                        "recent_anomalies": analyzer_summary.get("recent_anomalies", 0),
                        "active_bottlenecks": analyzer_summary.get("active_bottlenecks", 0)
                    }
                }
                
            # 负载均衡报告
            if self._load_balancer:
                lb_stats = self._load_balancer.get_load_balancer_stats()
                report["components"]["load_balancing"] = {
                    "status": "active",
                    "stats": lb_stats,
                    "key_metrics": {
                        "healthy_nodes": lb_stats.get("nodes", {}).get("healthy", 0),
                        "total_nodes": lb_stats.get("nodes", {}).get("total", 0),
                        "success_rate": lb_stats.get("performance", {}).get("success_rate", 0)
                    }
                }
                
            # 生成总体摘要
            report["summary"] = self._generate_overall_summary(report["components"])
            
        except Exception as e:
            self.logger.error(f"生成综合报告失败: {e}")
            report["error"] = str(e)
            
        return report
        
    def _generate_overall_summary(self, components: Dict[str, Any]) -> Dict[str, Any]:
        """生成总体摘要"""
        summary = {
            "overall_health": "unknown",
            "performance_score": 0,
            "key_insights": [],
            "recommendations": []
        }
        
        try:
            scores = []
            insights = []
            recommendations = []
            
            # 监控组件评分
            if "monitoring" in components:
                perf_level = components["monitoring"]["key_metrics"]["performance_level"]
                if perf_level == "excellent":
                    scores.append(100)
                elif perf_level == "good":
                    scores.append(80)
                elif perf_level == "acceptable":
                    scores.append(60)
                else:
                    scores.append(40)
                    
                insights.append(f"系统性能水平: {perf_level}")
                
            # 缓存组件评分
            if "caching" in components:
                hit_rate = components["caching"]["key_metrics"]["global_hit_rate"]
                cache_score = int(hit_rate * 100)
                scores.append(cache_score)
                
                insights.append(f"缓存命中率: {hit_rate:.1%}")
                
                if hit_rate < 0.7:
                    recommendations.append("缓存命中率较低，建议优化缓存策略")
                    
            # 优化组件评分
            if "optimization" in components:
                success_rate = components["optimization"]["key_metrics"]["success_rate"]
                opt_score = int(success_rate)
                scores.append(opt_score)
                
                insights.append(f"优化成功率: {success_rate:.1f}%")
                
            # 分析组件评分
            if "analysis" in components:
                active_bottlenecks = components["analysis"]["key_metrics"]["active_bottlenecks"]
                recent_anomalies = components["analysis"]["key_metrics"]["recent_anomalies"]
                
                analysis_score = max(0, 100 - active_bottlenecks * 20 - recent_anomalies * 10)
                scores.append(analysis_score)
                
                if active_bottlenecks > 0:
                    insights.append(f"发现 {active_bottlenecks} 个活跃瓶颈")
                    recommendations.append("建议立即调查并解决系统瓶颈")
                    
                if recent_anomalies > 0:
                    insights.append(f"最近检测到 {recent_anomalies} 个性能异常")
                    
            # 负载均衡组件评分
            if "load_balancing" in components:
                healthy_nodes = components["load_balancing"]["key_metrics"]["healthy_nodes"]
                total_nodes = components["load_balancing"]["key_metrics"]["total_nodes"]
                
                if total_nodes > 0:
                    node_health_ratio = healthy_nodes / total_nodes
                    lb_score = int(node_health_ratio * 100)
                    scores.append(lb_score)
                    
                    insights.append(f"健康节点比例: {node_health_ratio:.1%}")
                    
                    if node_health_ratio < 0.8:
                        recommendations.append("部分配置节点不健康，建议检查节点状态")
                        
            # 计算总体评分
            if scores:
                overall_score = sum(scores) / len(scores)
                summary["performance_score"] = int(overall_score)
                
                if overall_score >= 90:
                    summary["overall_health"] = "excellent"
                elif overall_score >= 75:
                    summary["overall_health"] = "good"
                elif overall_score >= 60:
                    summary["overall_health"] = "acceptable"
                else:
                    summary["overall_health"] = "needs_attention"
                    
            summary["key_insights"] = insights
            summary["recommendations"] = recommendations
            
        except Exception as e:
            self.logger.error(f"生成总体摘要失败: {e}")
            
        return summary
        
    @property
    def monitor(self) -> Optional[ConfigPerformanceMonitor]:
        """获取性能监控器"""
        return self._monitor
        
    @property
    def cache(self) -> Optional[MultiLevelConfigCache]:
        """获取智能缓存"""
        return self._cache
        
    @property
    def optimizer(self) -> Optional[ConfigOptimizer]:
        """获取配置优化器"""
        return self._optimizer
        
    @property
    def analyzer(self) -> Optional[PerformanceAnalyzer]:
        """获取性能分析器"""
        return self._analyzer
        
    @property
    def load_balancer(self) -> Optional[ConfigLoadBalancer]:
        """获取负载均衡器"""
        return self._load_balancer


# 全局性能管理器实例
_global_performance_manager: Optional[ConfigPerformanceManager] = None


def get_performance_manager(**kwargs) -> ConfigPerformanceManager:
    """获取全局性能管理器实例"""
    global _global_performance_manager
    if _global_performance_manager is None:
        _global_performance_manager = ConfigPerformanceManager(**kwargs)
    return _global_performance_manager


def initialize_performance_system(auto_start: bool = True, **kwargs) -> ConfigPerformanceManager:
    """初始化配置性能优化系统
    
    Args:
        auto_start: 是否自动启动所有服务
        **kwargs: 传递给 ConfigPerformanceManager 的参数
        
    Returns:
        性能管理器实例
    """
    manager = get_performance_manager(**kwargs)
    
    if auto_start:
        manager.start_all_services()
        
    return manager


# 导出所有公共接口
__all__ = [
    # 核心组件类
    'ConfigPerformanceMonitor',
    'MultiLevelConfigCache', 
    'ConfigOptimizer',
    'PerformanceAnalyzer',
    'ConfigLoadBalancer',
    
    # 管理器类
    'ConfigPerformanceManager',
    
    # 枚举类
    'MetricType',
    'AlertSeverity',
    'CachePriority',
    'CacheStrategy',
    'CacheLevel',
    'OptimizationType',
    'OptimizationSeverity',
    'OptimizationAction',
    'AnalysisType',
    'TrendType',
    'AnomalyType',
    'BottleneckType',
    'LoadBalancingStrategy',
    'NodeStatus',
    'FailoverStrategy',
    
    # 数据结构类
    'PerformanceMetric',
    'PerformanceAlert',
    'OptimizationRecommendation',
    'TrendAnalysis',
    'AnomalyDetection',
    'BottleneckAnalysis',
    'PerformanceReport',
    'ConfigNode',
    'LoadBalancingRequest',
    'LoadBalancingResponse',
    
    # 工厂函数
    'get_performance_monitor',
    'get_config_cache',
    'get_config_optimizer',
    'get_performance_analyzer',
    'get_config_load_balancer',
    'get_performance_manager',
    'initialize_performance_system',
    
    # 装饰器
    'monitor_performance',
    'cache_config',
    'optimize_config',
    'load_balance_request'
]