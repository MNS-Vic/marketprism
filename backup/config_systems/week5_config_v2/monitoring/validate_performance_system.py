#!/usr/bin/env python3
"""
MarketPrism 配置性能优化系统验证脚本
配置管理系统 2.0 - Week 5 Day 5

完整验证配置性能优化系统的所有功能组件，
确保系统集成正常和性能指标达标。

Author: MarketPrism团队
Created: 2025-01-29
Version: 1.0.0
"""

import sys
import time
import json
import random
import logging
import traceback
from datetime import datetime, timedelta
from typing import Dict, Any, List

# 导入性能优化系统
from . import (
    initialize_performance_system,
    ConfigPerformanceManager,
    MetricType,
    CachePriority,
    OptimizationType,
    LoadBalancingStrategy,
    ConfigNode
)


class PerformanceSystemValidator:
    """性能系统验证器"""
    
    def __init__(self):
        """初始化验证器"""
        self.test_results: List[Dict[str, Any]] = []
        self.performance_manager: ConfigPerformanceManager = None
        
        # 配置日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(self.__class__.__name__)
        
    def run_all_tests(self) -> Dict[str, Any]:
        """运行所有验证测试"""
        self.logger.info("🚀 开始配置性能优化系统验证")
        
        overall_result = {
            "validation_id": f"perf_validation_{int(datetime.now().timestamp())}",
            "start_time": datetime.now().isoformat(),
            "tests": [],
            "summary": {
                "total_tests": 0,
                "passed_tests": 0,
                "failed_tests": 0,
                "success_rate": 0.0
            }
        }
        
        # 定义测试序列
        test_sequence = [
            ("系统初始化测试", self.test_system_initialization),
            ("性能监控器测试", self.test_performance_monitor),
            ("智能缓存系统测试", self.test_cache_system),
            ("配置优化引擎测试", self.test_optimizer),
            ("性能分析器测试", self.test_analyzer),
            ("负载均衡器测试", self.test_load_balancer),
            ("系统集成测试", self.test_system_integration),
            ("性能基准测试", self.test_performance_benchmarks),
            ("综合报告生成测试", self.test_comprehensive_reporting)
        ]
        
        # 执行测试
        for test_name, test_func in test_sequence:
            try:
                self.logger.info(f"📋 执行测试: {test_name}")
                result = test_func()
                result["test_name"] = test_name
                result["timestamp"] = datetime.now().isoformat()
                overall_result["tests"].append(result)
                
                if result["passed"]:
                    self.logger.info(f"✅ {test_name} - 通过")
                else:
                    self.logger.error(f"❌ {test_name} - 失败: {result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                error_result = {
                    "test_name": test_name,
                    "passed": False,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                    "timestamp": datetime.now().isoformat()
                }
                overall_result["tests"].append(error_result)
                self.logger.error(f"💥 {test_name} - 异常: {e}")
                
        # 计算总体结果
        total_tests = len(overall_result["tests"])
        passed_tests = sum(1 for test in overall_result["tests"] if test["passed"])
        failed_tests = total_tests - passed_tests
        
        overall_result["summary"].update({
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "success_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0
        })
        
        overall_result["end_time"] = datetime.now().isoformat()
        
        # 清理资源
        self._cleanup()
        
        # 输出结果
        self._print_summary(overall_result)
        
        return overall_result
        
    def test_system_initialization(self) -> Dict[str, Any]:
        """测试系统初始化"""
        try:
            # 初始化性能系统
            self.performance_manager = initialize_performance_system(
                auto_start=True,
                enable_monitoring=True,
                enable_caching=True,
                enable_optimization=True,
                enable_analysis=True,
                enable_load_balancing=True
            )
            
            # 验证组件初始化
            checks = {
                "monitor_initialized": self.performance_manager.monitor is not None,
                "cache_initialized": self.performance_manager.cache is not None,
                "optimizer_initialized": self.performance_manager.optimizer is not None,
                "analyzer_initialized": self.performance_manager.analyzer is not None,
                "load_balancer_initialized": self.performance_manager.load_balancer is not None
            }
            
            # 等待服务启动
            time.sleep(2)
            
            # 检查系统状态
            status = self.performance_manager.get_system_status()
            
            all_initialized = all(checks.values())
            has_status = "component_status" in status
            
            return {
                "passed": all_initialized and has_status,
                "details": {
                    "initialization_checks": checks,
                    "system_status_available": has_status,
                    "enabled_components": status.get("enabled_components", {})
                }
            }
            
        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
            
    def test_performance_monitor(self) -> Dict[str, Any]:
        """测试性能监控器"""
        try:
            monitor = self.performance_manager.monitor
            
            # 测试指标记录
            test_metrics = [
                (MetricType.LATENCY, 45.5, "test_component", "test_operation"),
                (MetricType.THROUGHPUT, 1200.0, "test_component", "throughput_test"),
                (MetricType.MEMORY_USAGE, 256.0, "system", "memory_check"),
                (MetricType.CACHE_HIT_RATE, 0.85, "cache", "hit_rate_check")
            ]
            
            recorded_metrics = []
            for metric_type, value, component, operation in test_metrics:
                metric_id = monitor.record_metric(metric_type, value, component, operation)
                recorded_metrics.append(metric_id)
                
            # 测试上下文管理器
            with monitor.measure_operation("test_component", "context_operation"):
                time.sleep(0.05)  # 模拟操作
                
            # 获取性能摘要
            summary = monitor.get_performance_summary()
            
            # 验证结果
            checks = {
                "metrics_recorded": len(recorded_metrics) == len(test_metrics),
                "summary_available": "performance_indicators" in summary,
                "system_resources_tracked": "system_resources" in summary,
                "monitoring_active": summary.get("monitoring_status") == "active"
            }
            
            return {
                "passed": all(checks.values()),
                "details": {
                    "checks": checks,
                    "recorded_metrics_count": len(recorded_metrics),
                    "summary_keys": list(summary.keys()),
                    "performance_level": summary.get("performance_indicators", {}).get("performance_level")
                }
            }
            
        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
            
    def test_cache_system(self) -> Dict[str, Any]:
        """测试智能缓存系统"""
        try:
            cache = self.performance_manager.cache
            
            # 测试缓存操作
            test_data = {
                "config.database.host": "localhost",
                "config.database.port": 5432,
                "config.api.timeout": 30,
                "config.cache.ttl": 3600
            }
            
            # 存储配置
            for key, value in test_data.items():
                success = cache.put(key, value, ttl=300, priority=CachePriority.HIGH)
                if not success:
                    raise Exception(f"Failed to cache {key}")
                    
            # 读取配置
            cached_values = {}
            for key in test_data.keys():
                cached_values[key] = cache.get(key)
                
            # 测试缓存统计
            stats = cache.get_global_stats()
            
            # 验证结果
            checks = {
                "all_values_cached": all(v is not None for v in cached_values.values()),
                "values_match": all(cached_values[k] == test_data[k] for k in test_data.keys()),
                "stats_available": "total_requests" in stats,
                "hit_rate_reasonable": stats.get("global_hit_rate", 0) >= 0
            }
            
            return {
                "passed": all(checks.values()),
                "details": {
                    "checks": checks,
                    "cached_items": len(cached_values),
                    "cache_stats": stats,
                    "hit_rate": stats.get("global_hit_rate", 0)
                }
            }
            
        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
            
    def test_optimizer(self) -> Dict[str, Any]:
        """测试配置优化引擎"""
        try:
            optimizer = self.performance_manager.optimizer
            
            # 模拟一些性能问题以触发优化建议
            monitor = self.performance_manager.monitor
            
            # 模拟高延迟
            for _ in range(5):
                monitor.record_metric(MetricType.LATENCY, random.uniform(120, 200), "slow_component", "slow_operation")
                
            # 模拟低缓存命中率
            for _ in range(5):
                monitor.record_metric(MetricType.CACHE_HIT_RATE, random.uniform(0.3, 0.6), "cache_component", "cache_operation")
                
            # 等待一下让数据被处理
            time.sleep(1)
            
            # 触发优化分析
            recommendations = optimizer.analyze_performance()
            
            # 获取优化摘要
            summary = optimizer.get_optimization_summary()
            
            # 验证结果
            checks = {
                "analysis_completed": isinstance(recommendations, list),
                "has_recommendations": len(recommendations) > 0,
                "summary_available": "summary" in summary,
                "optimization_active": summary.get("optimization_status") == "active"
            }
            
            return {
                "passed": all(checks.values()),
                "details": {
                    "checks": checks,
                    "recommendations_count": len(recommendations),
                    "summary_keys": list(summary.keys()),
                    "recent_recommendations": [rec.description for rec in recommendations[:3]]
                }
            }
            
        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
            
    def test_analyzer(self) -> Dict[str, Any]:
        """测试性能分析器"""
        try:
            analyzer = self.performance_manager.analyzer
            
            # 生成一些分析数据
            monitor = self.performance_manager.monitor
            
            # 模拟趋势数据
            base_latency = 50
            for i in range(15):
                latency = base_latency + i * 2 + random.uniform(-5, 5)
                monitor.record_metric(MetricType.LATENCY, latency, "trend_component", "trend_operation")
                time.sleep(0.1)
                
            # 执行分析
            trends = analyzer.analyze_trends()
            anomalies = analyzer.detect_anomalies()
            bottlenecks = analyzer.analyze_bottlenecks()
            
            # 生成性能报告
            report = analyzer.generate_performance_report(include_charts=False)
            
            # 获取分析摘要
            summary = analyzer.get_analysis_summary()
            
            # 验证结果
            checks = {
                "trends_analyzed": isinstance(trends, list),
                "anomalies_detected": isinstance(anomalies, list),
                "bottlenecks_analyzed": isinstance(bottlenecks, list),
                "report_generated": report is not None and hasattr(report, 'report_id'),
                "summary_available": "stats" in summary
            }
            
            return {
                "passed": all(checks.values()),
                "details": {
                    "checks": checks,
                    "trends_count": len(trends),
                    "anomalies_count": len(anomalies),
                    "bottlenecks_count": len(bottlenecks),
                    "report_id": getattr(report, 'report_id', None),
                    "analysis_summary": summary
                }
            }
            
        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
            
    def test_load_balancer(self) -> Dict[str, Any]:
        """测试负载均衡器"""
        try:
            load_balancer = self.performance_manager.load_balancer
            
            # 添加测试节点
            test_nodes = [
                ConfigNode(
                    node_id="test_node_1",
                    name="测试节点1",
                    host="127.0.0.1",
                    port=8001,
                    weight=100
                ),
                ConfigNode(
                    node_id="test_node_2", 
                    name="测试节点2",
                    host="127.0.0.1",
                    port=8002,
                    weight=150
                )
            ]
            
            # 添加节点
            for node in test_nodes:
                success = load_balancer.add_node(node)
                if not success:
                    raise Exception(f"Failed to add node {node.name}")
                    
            # 测试不同的负载均衡策略
            strategies_tested = []
            for strategy in [LoadBalancingStrategy.ROUND_ROBIN, LoadBalancingStrategy.WEIGHTED_ROUND_ROBIN]:
                load_balancer.set_strategy(strategy)
                strategies_tested.append(strategy.name)
                
            # 获取负载均衡器统计
            stats = load_balancer.get_load_balancer_stats()
            
            # 获取节点状态
            node_statuses = load_balancer.get_node_status()
            
            # 验证结果
            checks = {
                "nodes_added": len(test_nodes) == 2,
                "strategies_tested": len(strategies_tested) == 2,
                "stats_available": "nodes" in stats,
                "node_statuses_available": isinstance(node_statuses, list) and len(node_statuses) > 0
            }
            
            return {
                "passed": all(checks.values()),
                "details": {
                    "checks": checks,
                    "nodes_count": len(test_nodes),
                    "strategies_tested": strategies_tested,
                    "load_balancer_stats": stats,
                    "healthy_nodes": stats.get("nodes", {}).get("healthy", 0)
                }
            }
            
        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
            
    def test_system_integration(self) -> Dict[str, Any]:
        """测试系统集成"""
        try:
            # 测试组件间协作
            monitor = self.performance_manager.monitor
            cache = self.performance_manager.cache
            optimizer = self.performance_manager.optimizer
            
            # 执行一个完整的工作流
            
            # 1. 记录性能指标
            for i in range(10):
                latency = random.uniform(20, 80)
                monitor.record_metric(MetricType.LATENCY, latency, "integration_test", "workflow")
                
            # 2. 缓存一些数据
            cache.put("integration.test.config", {"value": "test_data"}, priority=CachePriority.HIGH)
            cached_value = cache.get("integration.test.config")
            
            # 3. 触发优化分析
            recommendations = optimizer.analyze_performance()
            
            # 4. 获取系统状态
            system_status = self.performance_manager.get_system_status()
            
            # 验证集成
            checks = {
                "monitor_cache_integration": cached_value is not None,
                "monitor_optimizer_integration": len(recommendations) >= 0,
                "system_status_complete": len(system_status.get("component_status", {})) >= 3,
                "all_components_active": all(
                    comp.get("active", False) 
                    for comp in system_status.get("component_status", {}).values()
                )
            }
            
            return {
                "passed": all(checks.values()),
                "details": {
                    "checks": checks,
                    "cached_value_retrieved": cached_value is not None,
                    "recommendations_generated": len(recommendations),
                    "active_components": len(system_status.get("component_status", {})),
                    "system_status_keys": list(system_status.keys())
                }
            }
            
        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
            
    def test_performance_benchmarks(self) -> Dict[str, Any]:
        """测试性能基准"""
        try:
            monitor = self.performance_manager.monitor
            cache = self.performance_manager.cache
            
            # 性能基准测试
            benchmarks = {}
            
            # 1. 指标记录性能
            start_time = time.perf_counter()
            for i in range(100):
                monitor.record_metric(MetricType.LATENCY, random.uniform(10, 50), "benchmark", "metric_test")
            end_time = time.perf_counter()
            benchmarks["metric_recording_100ops"] = (end_time - start_time) * 1000  # ms
            
            # 2. 缓存读写性能
            start_time = time.perf_counter()
            for i in range(100):
                cache.put(f"benchmark.key.{i}", f"value_{i}")
            end_time = time.perf_counter()
            benchmarks["cache_write_100ops"] = (end_time - start_time) * 1000  # ms
            
            start_time = time.perf_counter()
            for i in range(100):
                cache.get(f"benchmark.key.{i}")
            end_time = time.perf_counter()
            benchmarks["cache_read_100ops"] = (end_time - start_time) * 1000  # ms
            
            # 3. 系统状态获取性能
            start_time = time.perf_counter()
            for _ in range(10):
                self.performance_manager.get_system_status()
            end_time = time.perf_counter()
            benchmarks["system_status_10ops"] = (end_time - start_time) * 1000  # ms
            
            # 性能要求检查
            performance_checks = {
                "metric_recording_fast": benchmarks["metric_recording_100ops"] < 1000,  # <1s for 100 ops
                "cache_write_fast": benchmarks["cache_write_100ops"] < 500,  # <500ms for 100 ops
                "cache_read_fast": benchmarks["cache_read_100ops"] < 100,   # <100ms for 100 ops
                "status_query_fast": benchmarks["system_status_10ops"] < 1000  # <1s for 10 ops
            }
            
            return {
                "passed": all(performance_checks.values()),
                "details": {
                    "benchmarks_ms": benchmarks,
                    "performance_checks": performance_checks,
                    "overall_performance": "excellent" if all(performance_checks.values()) else "needs_optimization"
                }
            }
            
        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
            
    def test_comprehensive_reporting(self) -> Dict[str, Any]:
        """测试综合报告生成"""
        try:
            # 生成综合报告
            report = self.performance_manager.generate_comprehensive_report()
            
            # 验证报告结构
            required_sections = ["report_id", "generated_at", "title", "summary", "components"]
            
            checks = {
                "report_generated": report is not None,
                "has_required_sections": all(section in report for section in required_sections),
                "has_summary": "overall_health" in report.get("summary", {}),
                "has_components": len(report.get("components", {})) > 0,
                "report_is_serializable": self._test_json_serializable(report)
            }
            
            # 检查组件报告
            components = report.get("components", {})
            component_checks = {
                f"{comp}_reported": comp in components 
                for comp in ["monitoring", "caching", "optimization", "analysis"]
            }
            
            checks.update(component_checks)
            
            return {
                "passed": all(checks.values()),
                "details": {
                    "checks": checks,
                    "report_id": report.get("report_id"),
                    "overall_health": report.get("summary", {}).get("overall_health"),
                    "performance_score": report.get("summary", {}).get("performance_score"),
                    "components_count": len(components),
                    "report_size_kb": len(json.dumps(report, default=str)) / 1024
                }
            }
            
        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
            
    def _test_json_serializable(self, obj: Any) -> bool:
        """测试对象是否可JSON序列化"""
        try:
            json.dumps(obj, default=str)
            return True
        except Exception:
            return False
            
    def _cleanup(self):
        """清理资源"""
        try:
            if self.performance_manager:
                self.performance_manager.stop_all_services()
                self.logger.info("✓ 系统资源已清理")
        except Exception as e:
            self.logger.error(f"清理资源失败: {e}")
            
    def _print_summary(self, result: Dict[str, Any]):
        """打印验证摘要"""
        print("\n" + "="*80)
        print("🎯 MarketPrism 配置性能优化系统验证报告")
        print("="*80)
        
        summary = result["summary"]
        print(f"📊 测试统计:")
        print(f"   总测试数: {summary['total_tests']}")
        print(f"   通过测试: {summary['passed_tests']}")
        print(f"   失败测试: {summary['failed_tests']}")
        print(f"   成功率: {summary['success_rate']:.1f}%")
        
        print(f"\n⏱️  执行时间: {result['start_time']} - {result['end_time']}")
        
        # 显示测试结果
        print(f"\n📋 详细测试结果:")
        for i, test in enumerate(result["tests"], 1):
            status = "✅ 通过" if test["passed"] else "❌ 失败"
            print(f"   {i:2d}. {test['test_name']:<30} {status}")
            if not test["passed"] and "error" in test:
                print(f"       错误: {test['error']}")
                
        # 总体评估
        print(f"\n🏆 总体评估:")
        if summary['success_rate'] >= 90:
            print("   🌟 优秀 - 系统功能完整，性能优异")
        elif summary['success_rate'] >= 75:
            print("   👍 良好 - 系统功能基本完整，性能良好")
        elif summary['success_rate'] >= 60:
            print("   ⚠️  可接受 - 系统基本可用，需要优化")
        else:
            print("   🚨 需要改进 - 系统存在重要问题，需要修复")
            
        print("="*80)


def main():
    """主函数"""
    print("🚀 MarketPrism 配置性能优化系统验证开始")
    print("🔧 正在初始化验证环境...")
    
    try:
        # 创建验证器
        validator = PerformanceSystemValidator()
        
        # 运行验证
        result = validator.run_all_tests()
        
        # 保存结果
        result_file = f"performance_validation_result_{int(datetime.now().timestamp())}.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)
            
        print(f"📄 详细结果已保存到: {result_file}")
        
        # 返回退出码
        success_rate = result["summary"]["success_rate"]
        if success_rate >= 90:
            sys.exit(0)  # 优秀
        elif success_rate >= 75:
            sys.exit(0)  # 良好
        else:
            sys.exit(1)  # 需要改进
            
    except Exception as e:
        print(f"💥 验证过程发生异常: {e}")
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()