#!/usr/bin/env python3
"""
进程健康监控和自动重启模块
防止长时间运行导致的性能问题和资源泄漏
"""

import asyncio
import psutil
import os
import signal
import time
import logging
from typing import Dict, Optional, Callable, Any
from datetime import datetime, timedelta
import structlog
from dataclasses import dataclass
from enum import Enum

logger = structlog.get_logger(__name__)


class HealthStatus(Enum):
    """健康状态枚举"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class HealthMetrics:
    """健康指标"""
    cpu_percent: float
    memory_mb: float
    memory_percent: float
    uptime_seconds: int
    thread_count: int
    fd_count: int
    status: HealthStatus
    last_check: datetime
    issues: list


class ProcessHealthMonitor:
    """进程健康监控器"""
    
    def __init__(self,
                 process_name: str,
                 pid: Optional[int] = None,
                 check_interval: int = 60,
                 cpu_threshold: float = 80.0,
                 memory_threshold_mb: int = 500,
                 memory_percent_threshold: float = 10.0,
                 max_uptime_hours: int = 24,
                 max_restart_attempts: int = 3,
                 restart_cooldown: int = 300):
        """
        初始化进程监控器
        
        Args:
            process_name: 进程名称
            pid: 进程ID，如果为None则自动检测
            check_interval: 检查间隔（秒）
            cpu_threshold: CPU使用率阈值（%）
            memory_threshold_mb: 内存使用阈值（MB）
            memory_percent_threshold: 内存使用百分比阈值（%）
            max_uptime_hours: 最大运行时间（小时）
            max_restart_attempts: 最大重启尝试次数
            restart_cooldown: 重启冷却时间（秒）
        """
        self.process_name = process_name
        self.pid = pid or os.getpid()
        self.check_interval = check_interval
        self.cpu_threshold = cpu_threshold
        self.memory_threshold_mb = memory_threshold_mb
        self.memory_percent_threshold = memory_percent_threshold
        self.max_uptime_hours = max_uptime_hours
        self.max_restart_attempts = max_restart_attempts
        self.restart_cooldown = restart_cooldown
        
        self.process: Optional[psutil.Process] = None
        self.is_monitoring = False
        self.restart_count = 0
        self.last_restart_time = 0
        self.health_history = []
        self.max_history_size = 100
        
        # 回调函数
        self.on_health_warning: Optional[Callable] = None
        self.on_health_critical: Optional[Callable] = None
        self.on_restart_needed: Optional[Callable] = None
        self.on_restart_failed: Optional[Callable] = None
        
        # 统计信息
        self.stats = {
            "total_checks": 0,
            "healthy_checks": 0,
            "warning_checks": 0,
            "critical_checks": 0,
            "restart_attempts": 0,
            "successful_restarts": 0,
            "failed_restarts": 0,
            "start_time": datetime.now(),
            "last_check_time": None
        }
    
    async def start_monitoring(self):
        """开始监控"""
        if self.is_monitoring:
            logger.warning("监控已在运行中", process_name=self.process_name)
            return
        
        try:
            self.process = psutil.Process(self.pid)
            self.is_monitoring = True
            
            logger.info("开始进程健康监控",
                       process_name=self.process_name,
                       pid=self.pid,
                       check_interval=self.check_interval)
            
            # 启动监控循环
            asyncio.create_task(self._monitoring_loop())
            
        except psutil.NoSuchProcess:
            logger.error("进程不存在", pid=self.pid)
            raise
        except Exception as e:
            logger.error("启动监控失败", error=str(e))
            raise
    
    async def stop_monitoring(self):
        """停止监控"""
        self.is_monitoring = False
        logger.info("停止进程健康监控", process_name=self.process_name)
    
    async def _monitoring_loop(self):
        """监控循环"""
        while self.is_monitoring:
            try:
                await self._check_health()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error("监控循环异常", error=str(e))
                await asyncio.sleep(self.check_interval)
    
    async def _check_health(self):
        """检查进程健康状态"""
        if not self.process:
            return
        
        try:
            # 检查进程是否还存在
            if not self.process.is_running():
                logger.error("进程已停止运行", process_name=self.process_name)
                return
            
            # 获取进程信息
            cpu_percent = self.process.cpu_percent()
            memory_info = self.process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            memory_percent = self.process.memory_percent()
            
            # 计算运行时间
            create_time = datetime.fromtimestamp(self.process.create_time())
            uptime = datetime.now() - create_time
            uptime_seconds = int(uptime.total_seconds())
            
            # 获取线程和文件描述符数量
            thread_count = self.process.num_threads()
            try:
                fd_count = self.process.num_fds() if hasattr(self.process, 'num_fds') else 0
            except:
                fd_count = 0
            
            # 分析健康状态
            issues = []
            status = HealthStatus.HEALTHY
            
            # CPU检查
            if cpu_percent > self.cpu_threshold:
                issues.append(f"CPU使用率过高: {cpu_percent:.1f}% > {self.cpu_threshold}%")
                status = HealthStatus.CRITICAL
            elif cpu_percent > self.cpu_threshold * 0.8:
                issues.append(f"CPU使用率较高: {cpu_percent:.1f}%")
                if status == HealthStatus.HEALTHY:
                    status = HealthStatus.WARNING
            
            # 内存检查
            if memory_mb > self.memory_threshold_mb:
                issues.append(f"内存使用过高: {memory_mb:.1f}MB > {self.memory_threshold_mb}MB")
                status = HealthStatus.CRITICAL
            elif memory_percent > self.memory_percent_threshold:
                issues.append(f"内存使用百分比过高: {memory_percent:.1f}% > {self.memory_percent_threshold}%")
                status = HealthStatus.CRITICAL
            
            # 运行时间检查
            max_uptime_seconds = self.max_uptime_hours * 3600
            if uptime_seconds > max_uptime_seconds:
                issues.append(f"运行时间过长: {uptime_seconds//3600}小时 > {self.max_uptime_hours}小时")
                if status != HealthStatus.CRITICAL:
                    status = HealthStatus.WARNING
            
            # 线程数检查（可选）
            if thread_count > 50:  # 假设阈值
                issues.append(f"线程数过多: {thread_count}")
                if status == HealthStatus.HEALTHY:
                    status = HealthStatus.WARNING
            
            # 创建健康指标
            metrics = HealthMetrics(
                cpu_percent=cpu_percent,
                memory_mb=memory_mb,
                memory_percent=memory_percent,
                uptime_seconds=uptime_seconds,
                thread_count=thread_count,
                fd_count=fd_count,
                status=status,
                last_check=datetime.now(),
                issues=issues
            )
            
            # 更新历史记录
            self.health_history.append(metrics)
            if len(self.health_history) > self.max_history_size:
                self.health_history.pop(0)
            
            # 更新统计
            self.stats["total_checks"] += 1
            self.stats["last_check_time"] = datetime.now()
            
            if status == HealthStatus.HEALTHY:
                self.stats["healthy_checks"] += 1
            elif status == HealthStatus.WARNING:
                self.stats["warning_checks"] += 1
            elif status == HealthStatus.CRITICAL:
                self.stats["critical_checks"] += 1
            
            # 记录日志
            if status == HealthStatus.HEALTHY:
                logger.debug("进程健康检查正常",
                           process_name=self.process_name,
                           cpu_percent=cpu_percent,
                           memory_mb=memory_mb,
                           uptime_hours=uptime_seconds//3600)
            elif status == HealthStatus.WARNING:
                logger.warning("进程健康状态警告",
                             process_name=self.process_name,
                             issues=issues,
                             cpu_percent=cpu_percent,
                             memory_mb=memory_mb)
                
                if self.on_health_warning:
                    await self._safe_callback(self.on_health_warning, metrics)
            
            elif status == HealthStatus.CRITICAL:
                logger.error("进程健康状态严重",
                           process_name=self.process_name,
                           issues=issues,
                           cpu_percent=cpu_percent,
                           memory_mb=memory_mb)
                
                if self.on_health_critical:
                    await self._safe_callback(self.on_health_critical, metrics)
                
                # 检查是否需要重启
                await self._check_restart_needed(metrics)
        
        except psutil.NoSuchProcess:
            logger.error("进程不存在，停止监控", process_name=self.process_name)
            self.is_monitoring = False
        except Exception as e:
            logger.error("健康检查异常", error=str(e))
    
    async def _check_restart_needed(self, metrics: HealthMetrics):
        """检查是否需要重启进程"""
        # 检查重启冷却时间
        if time.time() - self.last_restart_time < self.restart_cooldown:
            logger.info("重启冷却中，跳过重启检查",
                       cooldown_remaining=self.restart_cooldown - (time.time() - self.last_restart_time))
            return
        
        # 检查重启次数限制
        if self.restart_count >= self.max_restart_attempts:
            logger.error("已达到最大重启次数，停止自动重启",
                        restart_count=self.restart_count,
                        max_attempts=self.max_restart_attempts)
            return
        
        # 判断是否需要重启
        restart_needed = False
        restart_reason = []
        
        # CPU持续过高
        if metrics.cpu_percent > self.cpu_threshold:
            recent_high_cpu = sum(1 for m in self.health_history[-5:] 
                                if m.cpu_percent > self.cpu_threshold)
            if recent_high_cpu >= 3:  # 最近5次检查中有3次CPU过高
                restart_needed = True
                restart_reason.append("CPU持续过高")
        
        # 内存泄漏检测
        if len(self.health_history) >= 10:
            memory_trend = [m.memory_mb for m in self.health_history[-10:]]
            if all(memory_trend[i] <= memory_trend[i+1] for i in range(len(memory_trend)-1)):
                # 内存持续增长
                if memory_trend[-1] > self.memory_threshold_mb:
                    restart_needed = True
                    restart_reason.append("内存泄漏检测")
        
        # 运行时间过长
        if metrics.uptime_seconds > self.max_uptime_hours * 3600:
            restart_needed = True
            restart_reason.append("运行时间过长")
        
        if restart_needed:
            logger.warning("检测到需要重启进程",
                         process_name=self.process_name,
                         reasons=restart_reason,
                         restart_count=self.restart_count)
            
            if self.on_restart_needed:
                await self._safe_callback(self.on_restart_needed, metrics, restart_reason)
    
    async def _safe_callback(self, callback: Callable, *args, **kwargs):
        """安全执行回调函数"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(*args, **kwargs)
            else:
                callback(*args, **kwargs)
        except Exception as e:
            logger.error("回调函数执行失败", error=str(e))
    
    def get_current_metrics(self) -> Optional[HealthMetrics]:
        """获取当前健康指标"""
        return self.health_history[-1] if self.health_history else None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取监控统计信息"""
        current_metrics = self.get_current_metrics()
        
        return {
            **self.stats,
            "current_status": current_metrics.status.value if current_metrics else "unknown",
            "restart_count": self.restart_count,
            "is_monitoring": self.is_monitoring,
            "process_info": {
                "name": self.process_name,
                "pid": self.pid,
                "running": self.process.is_running() if self.process else False
            },
            "thresholds": {
                "cpu_threshold": self.cpu_threshold,
                "memory_threshold_mb": self.memory_threshold_mb,
                "memory_percent_threshold": self.memory_percent_threshold,
                "max_uptime_hours": self.max_uptime_hours
            }
        }


# 全局监控器实例
_global_monitors: Dict[str, ProcessHealthMonitor] = {}


def create_process_monitor(process_name: str, **kwargs) -> ProcessHealthMonitor:
    """创建进程监控器"""
    monitor = ProcessHealthMonitor(process_name, **kwargs)
    _global_monitors[process_name] = monitor
    return monitor


def get_process_monitor(process_name: str) -> Optional[ProcessHealthMonitor]:
    """获取进程监控器"""
    return _global_monitors.get(process_name)


async def start_all_monitors():
    """启动所有监控器"""
    for monitor in _global_monitors.values():
        if not monitor.is_monitoring:
            await monitor.start_monitoring()


async def stop_all_monitors():
    """停止所有监控器"""
    for monitor in _global_monitors.values():
        await monitor.stop_monitoring()


def get_all_stats() -> Dict[str, Any]:
    """获取所有监控器的统计信息"""
    return {name: monitor.get_stats() for name, monitor in _global_monitors.items()}
