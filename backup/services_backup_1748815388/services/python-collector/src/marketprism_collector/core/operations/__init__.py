"""
智能化运维和自动化管理系统 - Week 5 Day 8
统一初始化模块
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional

# 导入所有核心组件
from .intelligent_monitoring import IntelligentMonitoring, generate_sample_metrics
from .automation_deployment import AutomationDeployment, generate_sample_deployments
from .capacity_management import CapacityManagement, generate_sample_capacity_data
from .self_healing_engine import SelfHealingEngine, generate_sample_faults
from .performance_optimization import PerformanceOptimization, generate_sample_performance_data

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OperationsManager:
    """运维管理系统统一管理器"""
    
    def __init__(self):
        """初始化所有运维组件"""
        self.intelligent_monitoring = IntelligentMonitoring()
        self.automation_deployment = AutomationDeployment()
        self.capacity_management = CapacityManagement()
        self.self_healing_engine = SelfHealingEngine()
        self.performance_optimization = PerformanceOptimization()
        
        logger.info("运维管理系统统一管理器初始化完成")
    
    def initialize_with_sample_data(self):
        """使用示例数据初始化所有系统"""
        try:
            logger.info("开始加载示例数据...")
            
            # 生成监控数据
            generate_sample_metrics(self.intelligent_monitoring, 150)
            logger.info("✅ 智能监控示例数据加载完成")
            
            # 生成部署数据
            generate_sample_deployments(self.automation_deployment, 20)
            logger.info("✅ 自动化部署示例数据加载完成")
            
            # 生成容量数据
            generate_sample_capacity_data(self.capacity_management, 200)
            logger.info("✅ 容量管理示例数据加载完成")
            
            # 生成故障数据
            generate_sample_faults(self.self_healing_engine, 25)
            logger.info("✅ 故障自愈示例数据加载完成")
            
            # 生成性能数据
            generate_sample_performance_data(self.performance_optimization, 180)
            logger.info("✅ 性能优化示例数据加载完成")
            
            logger.info("🎉 所有示例数据加载完成")
            
        except Exception as e:
            logger.error(f"加载示例数据失败: {e}")
    
    def get_unified_stats(self) -> Dict[str, Any]:
        """获取统一的运维统计信息"""
        try:
            stats = {
                "system_overview": {
                    "timestamp": datetime.now().isoformat(),
                    "status": "operational",
                    "components": {
                        "intelligent_monitoring": "active",
                        "automation_deployment": "active", 
                        "capacity_management": "active",
                        "self_healing_engine": "active",
                        "performance_optimization": "active"
                    }
                },
                "intelligent_monitoring": self.intelligent_monitoring.get_monitoring_stats(),
                "automation_deployment": self.automation_deployment.get_deployment_stats(),
                "capacity_management": self.capacity_management.get_capacity_stats(),
                "self_healing_engine": self.self_healing_engine.get_healing_stats(),
                "performance_optimization": self.performance_optimization.get_optimization_stats()
            }
            
            # 计算整体健康度
            total_alerts = stats["intelligent_monitoring"].get("active_alerts", 0)
            failed_deployments = stats["automation_deployment"].get("task_status_counts", {}).get("failed", 0)
            unresolved_faults = stats["self_healing_engine"].get("total_fault_events", 0) - stats["self_healing_engine"].get("resolved_faults", 0)
            
            health_score = 100
            if total_alerts > 5:
                health_score -= min(20, total_alerts * 2)
            if failed_deployments > 2:
                health_score -= min(15, failed_deployments * 5)
            if unresolved_faults > 3:
                health_score -= min(25, unresolved_faults * 8)
            
            stats["system_overview"]["health_score"] = max(0, health_score)
            
            return stats
            
        except Exception as e:
            logger.error(f"获取统一统计信息失败: {e}")
            return {}
    
    def get_system_health_summary(self) -> Dict[str, Any]:
        """获取系统健康状况摘要"""
        try:
            monitoring_stats = self.intelligent_monitoring.get_monitoring_stats()
            deployment_stats = self.automation_deployment.get_deployment_stats()
            capacity_stats = self.capacity_management.get_capacity_stats()
            healing_stats = self.self_healing_engine.get_healing_stats()
            optimization_stats = self.performance_optimization.get_optimization_stats()
            
            summary = {
                "timestamp": datetime.now().isoformat(),
                "overall_status": "healthy",
                "key_metrics": {
                    "active_alerts": monitoring_stats.get("active_alerts", 0),
                    "active_deployments": deployment_stats.get("active_deployments", 0),
                    "unresolved_faults": healing_stats.get("total_fault_events", 0) - healing_stats.get("resolved_faults", 0),
                    "optimization_recommendations": optimization_stats.get("optimization_recommendations", 0),
                    "system_utilization": {
                        "cpu_pools": capacity_stats.get("resource_pool_utilization", {}),
                        "scaling_actions_today": len([a for a in self.capacity_management.scaling_actions if a.triggered_at.date() == datetime.now().date()])
                    }
                },
                "component_status": {
                    "monitoring": "operational" if monitoring_stats.get("total_metrics", 0) > 0 else "warning",
                    "deployment": "operational" if deployment_stats.get("total_tasks", 0) > 0 else "info",
                    "capacity": "operational" if capacity_stats.get("resource_pools", 0) > 0 else "warning",
                    "healing": "operational" if healing_stats.get("healing_rules", 0) > 0 else "warning",
                    "optimization": "operational" if optimization_stats.get("performance_benchmarks", 0) > 0 else "info"
                },
                "recent_activities": {
                    "latest_alert": len(self.intelligent_monitoring.alert_history) > 0,
                    "latest_deployment": len(self.automation_deployment.deployment_tasks) > 0,
                    "latest_scaling": len(self.capacity_management.scaling_actions) > 0,
                    "latest_healing": len(self.self_healing_engine.healing_tasks) > 0,
                    "latest_optimization": len(self.performance_optimization.optimization_recommendations) > 0
                }
            }
            
            # 确定整体状态
            component_statuses = list(summary["component_status"].values())
            if "warning" in component_statuses:
                summary["overall_status"] = "warning"
            elif all(status == "operational" for status in component_statuses):
                summary["overall_status"] = "healthy"
            else:
                summary["overall_status"] = "info"
            
            return summary
            
        except Exception as e:
            logger.error(f"获取系统健康摘要失败: {e}")
            return {"overall_status": "error", "error": str(e)}
    
    def perform_health_check(self) -> bool:
        """执行系统健康检查"""
        try:
            logger.info("开始执行系统健康检查...")
            
            # 检查各个组件
            components = [
                ("智能监控", self.intelligent_monitoring),
                ("自动化部署", self.automation_deployment),
                ("容量管理", self.capacity_management),
                ("故障自愈", self.self_healing_engine),
                ("性能优化", self.performance_optimization)
            ]
            
            all_healthy = True
            
            for name, component in components:
                try:
                    # 尝试获取统计信息作为健康检查
                    if hasattr(component, 'get_monitoring_stats'):
                        stats = component.get_monitoring_stats()
                    elif hasattr(component, 'get_deployment_stats'):
                        stats = component.get_deployment_stats()
                    elif hasattr(component, 'get_capacity_stats'):
                        stats = component.get_capacity_stats()
                    elif hasattr(component, 'get_healing_stats'):
                        stats = component.get_healing_stats()
                    elif hasattr(component, 'get_optimization_stats'):
                        stats = component.get_optimization_stats()
                    else:
                        stats = {}
                    
                    if stats:
                        logger.info(f"✅ {name} 健康检查通过")
                    else:
                        logger.warning(f"⚠️ {name} 健康检查警告 - 无数据")
                        
                except Exception as e:
                    logger.error(f"❌ {name} 健康检查失败: {e}")
                    all_healthy = False
            
            logger.info(f"系统健康检查完成 - 结果: {'健康' if all_healthy else '异常'}")
            return all_healthy
            
        except Exception as e:
            logger.error(f"系统健康检查失败: {e}")
            return False


# 全局运维管理器实例
operations_manager: Optional[OperationsManager] = None


def get_operations_manager() -> OperationsManager:
    """获取全局运维管理器实例"""
    global operations_manager
    if operations_manager is None:
        operations_manager = OperationsManager()
    return operations_manager


def initialize_operations_system(with_sample_data: bool = True) -> OperationsManager:
    """初始化运维系统"""
    manager = get_operations_manager()
    
    if with_sample_data:
        manager.initialize_with_sample_data()
    
    # 执行健康检查
    manager.perform_health_check()
    
    return manager


# 导出主要类和函数
__all__ = [
    'OperationsManager',
    'IntelligentMonitoring',
    'AutomationDeployment', 
    'CapacityManagement',
    'SelfHealingEngine',
    'PerformanceOptimization',
    'get_operations_manager',
    'initialize_operations_system'
]