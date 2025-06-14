"""
预定义任务配置

提供常用的任务配置和任务工厂方法
"""

from datetime import datetime, time
from typing import Dict, Any, Callable


class ScheduledJobs:
    """预定义任务配置"""
    
    # 资金费率收集配置
    FUNDING_RATE_JOBS = {
        "funding_rate_hourly": {
            "trigger_type": "interval",
            "hours": 1,
            "description": "每小时收集资金费率数据",
            "max_instances": 1
        },
        "funding_rate_cron": {
            "trigger_type": "cron",
            "hour": "*/8",  # 每8小时（符合大多数交易所资金费率结算周期）
            "minute": 0,
            "description": "定时收集资金费率数据（与交易所结算时间同步）",
            "max_instances": 1
        }
    }
    
    # 持仓量收集配置
    OPEN_INTEREST_JOBS = {
        "open_interest_15min": {
            "trigger_type": "interval",
            "minutes": 15,
            "description": "每15分钟收集持仓量数据",
            "max_instances": 1
        },
        "open_interest_5min": {
            "trigger_type": "interval",
            "minutes": 5,
            "description": "每5分钟收集持仓量数据（高频）",
            "max_instances": 1
        }
    }
    
    # 大户持仓比收集配置
    TOP_TRADER_JOBS = {
        "top_trader_5min": {
            "trigger_type": "interval",
            "minutes": 5,
            "description": "每5分钟收集大户持仓比数据",
            "max_instances": 1
        },
        "top_trader_15min": {
            "trigger_type": "interval",
            "minutes": 15,
            "description": "每15分钟收集大户持仓比数据（低频）",
            "max_instances": 1
        },
        "top_trader_cron": {
            "trigger_type": "cron",
            "minute": "*/5",  # 每5分钟
            "description": "定时收集大户持仓比数据（与交易所数据更新同步）",
            "max_instances": 1
        }
    }
    
    # 强平监控配置
    LIQUIDATION_JOBS = {
        "liquidation_monitor": {
            "trigger_type": "interval",
            "minutes": 1,
            "description": "每分钟检查强平数据流状态",
            "max_instances": 1
        },
        "liquidation_stats": {
            "trigger_type": "interval",
            "minutes": 10,
            "description": "每10分钟统计强平数据",
            "max_instances": 1
        }
    }
    
    # 系统维护任务配置
    MAINTENANCE_JOBS = {
        "health_check": {
            "trigger_type": "interval",
            "minutes": 5,
            "description": "每5分钟执行系统健康检查",
            "max_instances": 1
        },
        "connection_check": {
            "trigger_type": "interval",
            "seconds": 30,
            "description": "每30秒检查连接状态",
            "max_instances": 1
        },
        "metrics_update": {
            "trigger_type": "interval",
            "minutes": 1,
            "description": "每分钟更新系统指标",
            "max_instances": 1
        },
        "daily_cleanup": {
            "trigger_type": "cron",
            "hour": 2,
            "minute": 0,
            "description": "每日凌晨2点执行清理任务",
            "max_instances": 1
        },
        "market_long_short_data_collection": {
            "trigger_type": "interval",
            "minutes": 5,
            "description": "每5分钟收集市场多空仓人数比数据",
            "max_instances": 1,
            "coalesce": True,
            "misfire_grace_time": 30,
            "func": "marketprism_collector.market_long_short_collector:MarketLongShortDataCollector.collect_data",
            "args": [["BTC-USDT", "ETH-USDT"]]
        }
    }
    
    @classmethod
    def get_all_job_configs(cls) -> Dict[str, Dict[str, Any]]:
        """获取所有预定义任务配置"""
        all_jobs = {}
        all_jobs.update(cls.FUNDING_RATE_JOBS)
        all_jobs.update(cls.OPEN_INTEREST_JOBS)
        all_jobs.update(cls.TOP_TRADER_JOBS)
        all_jobs.update(cls.LIQUIDATION_JOBS)
        all_jobs.update(cls.MAINTENANCE_JOBS)
        return all_jobs
    
    @classmethod
    def get_jobs_by_category(cls, category: str) -> Dict[str, Dict[str, Any]]:
        """根据类别获取任务配置"""
        categories = {
            "funding_rate": cls.FUNDING_RATE_JOBS,
            "open_interest": cls.OPEN_INTEREST_JOBS,
            "top_trader": cls.TOP_TRADER_JOBS,
            "liquidation": cls.LIQUIDATION_JOBS,
            "maintenance": cls.MAINTENANCE_JOBS
        }
        return categories.get(category, {})
    
    @classmethod
    def create_custom_job_config(
        cls,
        trigger_type: str,
        description: str,
        max_instances: int = 1,
        **trigger_kwargs
    ) -> Dict[str, Any]:
        """创建自定义任务配置"""
        return {
            "trigger_type": trigger_type,
            "description": description,
            "max_instances": max_instances,
            **trigger_kwargs
        }


class JobFactory:
    """任务工厂类"""
    
    @staticmethod
    def create_data_collection_job(
        data_type: str,
        interval_minutes: int,
        description: str = None
    ) -> Dict[str, Any]:
        """创建数据收集任务配置"""
        return {
            "trigger_type": "interval",
            "minutes": interval_minutes,
            "description": description or f"每{interval_minutes}分钟收集{data_type}数据",
            "max_instances": 1,
            "data_type": data_type
        }
    
    @staticmethod
    def create_monitoring_job(
        check_type: str,
        interval_seconds: int,
        description: str = None
    ) -> Dict[str, Any]:
        """创建监控任务配置"""
        return {
            "trigger_type": "interval",
            "seconds": interval_seconds,
            "description": description or f"每{interval_seconds}秒执行{check_type}检查",
            "max_instances": 1,
            "check_type": check_type
        }
    
    @staticmethod
    def create_maintenance_job(
        hour: int,
        minute: int = 0,
        description: str = None
    ) -> Dict[str, Any]:
        """创建维护任务配置"""
        return {
            "trigger_type": "cron",
            "hour": hour,
            "minute": minute,
            "description": description or f"每日{hour:02d}:{minute:02d}执行维护任务",
            "max_instances": 1
        }


# 预定义任务函数映射
TASK_FUNCTION_MAP = {
    "funding_rate_collection": "_collect_funding_rates",
    "open_interest_collection": "_collect_open_interest",
    "top_trader_collection": "_collect_top_trader_data",
    "liquidation_monitoring": "_monitor_liquidations",
    "health_check": "_health_check",
    "connection_check": "_check_connections",
    "metrics_update": "_update_metrics",
    "daily_cleanup": "_daily_cleanup"
} 