"""
资源管理器 - 监控和限制子进程的资源使用

功能：
1. 内存监控（软限制 + 硬限制）
2. CPU 监控
3. 连接数监控
4. 资源告警
"""

import psutil
import time
from typing import Dict, Optional, Callable
from dataclasses import dataclass
import asyncio


@dataclass
class ResourceLimits:
    """资源限制配置"""
    memory_soft_limit_mb: float   # 内存软限制（MB）
    memory_hard_limit_mb: float   # 内存硬限制（MB）
    cpu_limit_percent: float      # CPU 限制（%）
    max_connections: int          # 最大连接数
    max_file_descriptors: int     # 最大文件描述符数


@dataclass
class ResourceUsage:
    """资源使用情况"""
    cpu_percent: float            # CPU 使用率（%）
    memory_mb: float              # 内存使用（MB）
    memory_percent: float         # 内存使用率（%）
    num_connections: int          # 连接数
    num_file_descriptors: int     # 文件描述符数
    timestamp: float              # 采样时间


class ResourceManager:
    """资源管理器"""
    
    # 预定义的资源限制（按交易所）
    DEFAULT_LIMITS = {
        "okx_derivatives": ResourceLimits(
            memory_soft_limit_mb=150,
            memory_hard_limit_mb=200,
            cpu_limit_percent=80,
            max_connections=20,
            max_file_descriptors=200
        ),
        "okx_spot": ResourceLimits(
            memory_soft_limit_mb=120,
            memory_hard_limit_mb=160,
            cpu_limit_percent=80,
            max_connections=15,
            max_file_descriptors=200
        ),
        "binance_derivatives": ResourceLimits(
            memory_soft_limit_mb=100,
            memory_hard_limit_mb=140,
            cpu_limit_percent=80,
            max_connections=15,
            max_file_descriptors=200
        ),
        "binance_spot": ResourceLimits(
            memory_soft_limit_mb=80,
            memory_hard_limit_mb=120,
            cpu_limit_percent=80,
            max_connections=10,
            max_file_descriptors=200
        ),
        "deribit_derivatives": ResourceLimits(
            memory_soft_limit_mb=60,
            memory_hard_limit_mb=100,
            cpu_limit_percent=80,
            max_connections=5,
            max_file_descriptors=100
        ),
    }
    
    def __init__(
        self,
        exchange: str,
        pid: Optional[int] = None,
        limits: Optional[ResourceLimits] = None,
        on_soft_limit: Optional[Callable] = None,
        on_hard_limit: Optional[Callable] = None
    ):
        """
        初始化资源管理器
        
        Args:
            exchange: 交易所名称
            pid: 进程 ID（None 表示当前进程）
            limits: 资源限制（None 使用默认值）
            on_soft_limit: 软限制触发回调
            on_hard_limit: 硬限制触发回调
        """
        self.exchange = exchange
        self.pid = pid or psutil.Process().pid
        self.process = psutil.Process(self.pid)
        
        # 使用预定义限制或自定义限制
        self.limits = limits or self.DEFAULT_LIMITS.get(
            exchange,
            ResourceLimits(
                memory_soft_limit_mb=100,
                memory_hard_limit_mb=150,
                cpu_limit_percent=80,
                max_connections=10,
                max_file_descriptors=200
            )
        )
        
        self.on_soft_limit = on_soft_limit
        self.on_hard_limit = on_hard_limit
        
        # 状态跟踪
        self.soft_limit_triggered = False
        self.hard_limit_triggered = False
        self.last_check_time = 0
        
    def get_resource_usage(self) -> ResourceUsage:
        """获取当前资源使用情况"""
        try:
            # CPU 使用率（需要一定时间间隔才准确）
            cpu_percent = self.process.cpu_percent(interval=0.1)
            
            # 内存使用
            mem_info = self.process.memory_info()
            memory_mb = mem_info.rss / (1024 * 1024)  # RSS 内存（MB）
            memory_percent = self.process.memory_percent()
            
            # 连接数
            try:
                connections = self.process.connections()
                num_connections = len(connections)
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                num_connections = 0
            
            # 文件描述符数
            try:
                num_fds = self.process.num_fds()
            except (AttributeError, psutil.AccessDenied, psutil.NoSuchProcess):
                # Windows 不支持 num_fds
                num_fds = 0
            
            return ResourceUsage(
                cpu_percent=cpu_percent,
                memory_mb=memory_mb,
                memory_percent=memory_percent,
                num_connections=num_connections,
                num_file_descriptors=num_fds,
                timestamp=time.time()
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            # 进程不存在或无权限
            raise RuntimeError(f"无法获取进程资源使用情况: {e}")
    
    def check_limits(self, usage: ResourceUsage) -> Dict[str, bool]:
        """
        检查资源限制
        
        Returns:
            Dict[str, bool]: 限制检查结果
                - memory_soft_exceeded: 内存软限制超出
                - memory_hard_exceeded: 内存硬限制超出
                - cpu_exceeded: CPU 限制超出
                - connections_exceeded: 连接数限制超出
                - fds_exceeded: 文件描述符限制超出
        """
        results = {
            "memory_soft_exceeded": usage.memory_mb > self.limits.memory_soft_limit_mb,
            "memory_hard_exceeded": usage.memory_mb > self.limits.memory_hard_limit_mb,
            "cpu_exceeded": usage.cpu_percent > self.limits.cpu_limit_percent,
            "connections_exceeded": usage.num_connections > self.limits.max_connections,
            "fds_exceeded": usage.num_file_descriptors > self.limits.max_file_descriptors,
        }
        
        # 触发回调
        if results["memory_soft_exceeded"] and not self.soft_limit_triggered:
            self.soft_limit_triggered = True
            if self.on_soft_limit:
                self.on_soft_limit(self.exchange, "memory", usage)
        
        if results["memory_hard_exceeded"] and not self.hard_limit_triggered:
            self.hard_limit_triggered = True
            if self.on_hard_limit:
                self.on_hard_limit(self.exchange, "memory", usage)
        
        # 重置标志（如果恢复正常）
        if not results["memory_soft_exceeded"]:
            self.soft_limit_triggered = False
        if not results["memory_hard_exceeded"]:
            self.hard_limit_triggered = False
        
        return results
    
    async def monitor_loop(self, interval: float = 10.0):
        """
        资源监控循环
        
        Args:
            interval: 监控间隔（秒）
        """
        while True:
            try:
                usage = self.get_resource_usage()
                self.check_limits(usage)
                self.last_check_time = time.time()
            except RuntimeError:
                # 进程已退出
                break
            except Exception as e:
                # 其他异常，继续监控
                pass
            
            await asyncio.sleep(interval)
    
    def get_limits(self) -> ResourceLimits:
        """获取资源限制配置"""
        return self.limits
    
    def update_limits(self, limits: ResourceLimits):
        """更新资源限制配置"""
        self.limits = limits
        # 重置触发标志
        self.soft_limit_triggered = False
        self.hard_limit_triggered = False


class ResourceMonitor:
    """多进程资源监控器"""
    
    def __init__(self):
        self.managers: Dict[str, ResourceManager] = {}
    
    def add_process(
        self,
        exchange: str,
        pid: int,
        limits: Optional[ResourceLimits] = None,
        on_soft_limit: Optional[Callable] = None,
        on_hard_limit: Optional[Callable] = None
    ):
        """添加进程监控"""
        manager = ResourceManager(
            exchange=exchange,
            pid=pid,
            limits=limits,
            on_soft_limit=on_soft_limit,
            on_hard_limit=on_hard_limit
        )
        self.managers[exchange] = manager
    
    def remove_process(self, exchange: str):
        """移除进程监控"""
        if exchange in self.managers:
            del self.managers[exchange]
    
    def get_all_usage(self) -> Dict[str, ResourceUsage]:
        """获取所有进程的资源使用情况"""
        usage_dict = {}
        for exchange, manager in self.managers.items():
            try:
                usage_dict[exchange] = manager.get_resource_usage()
            except RuntimeError:
                # 进程已退出
                pass
        return usage_dict
    
    def check_all_limits(self) -> Dict[str, Dict[str, bool]]:
        """检查所有进程的资源限制"""
        results = {}
        for exchange, manager in self.managers.items():
            try:
                usage = manager.get_resource_usage()
                results[exchange] = manager.check_limits(usage)
            except RuntimeError:
                # 进程已退出
                pass
        return results

