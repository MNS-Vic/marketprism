"""
MarketPrism内存管理器
防止内存泄漏，确保长期稳定运行
"""

import asyncio
import gc
import time
import psutil
import threading
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
import structlog


@dataclass
class SystemResourceStats:
    """系统资源统计信息"""
    timestamp: float
    # 内存信息
    rss_mb: float  # 物理内存使用（MB）
    vms_mb: float  # 虚拟内存使用（MB）
    memory_percent: float  # 内存使用百分比
    gc_collections: int  # GC回收次数
    objects_count: int  # 对象数量

    # 🔧 新增：CPU信息
    cpu_percent: float  # CPU使用率
    cpu_count: int  # CPU核心数

    # 🔧 新增：文件描述符信息
    num_fds: int  # 文件描述符数量
    max_fds: int  # 最大文件描述符限制
    fd_usage_percent: float  # 文件描述符使用率

    # 🔧 新增：网络连接信息
    num_connections: int  # 网络连接数
    tcp_connections: int  # TCP连接数

    # 🔧 新增：线程信息
    num_threads: int  # 线程数量

    # 🔧 新增：系统负载信息
    load_avg_1min: float  # 1分钟平均负载
    load_avg_5min: float  # 5分钟平均负载


@dataclass
class SystemResourceConfig:
    """🔧 修复：系统资源监控配置 - 优化内存阈值"""
    # 🔧 修复：大幅提高内存阈值，适应高频数据处理需求
    memory_warning_threshold_mb: int = 1000  # 🔧 修复：从600MB提高到1000MB
    memory_critical_threshold_mb: int = 1400  # 🔧 修复：从900MB提高到1400MB
    memory_max_threshold_mb: int = 1800  # 🔧 修复：从1200MB提高到1800MB

    # 🔧 新增：CPU阈值 - 高频数据处理场景下CPU使用率高是正常的
    cpu_warning_threshold: float = 85.0  # 🔧 修复：从70%提高到85%
    cpu_critical_threshold: float = 95.0  # 🔧 修复：保持95%
    cpu_max_threshold: float = 98.0  # 🔧 修复：从95%提高到98%
    # 多核科学判定：结合 loadavg/核心数 的归一化比例
    cpu_loadavg_warning_ratio: float = 0.70  # 1分钟负载/核心数 ≥ 0.70 视为警告
    cpu_loadavg_critical_ratio: float = 0.90  # 1分钟负载/核心数 ≥ 0.90 视为严重

    # 🔧 新增：文件描述符阈值
    fd_warning_threshold: float = 0.7  # 文件描述符警告阈值70%
    fd_critical_threshold: float = 0.85  # 文件描述符严重阈值85%
    fd_max_threshold: float = 0.95  # 文件描述符最大阈值95%

    # 🔧 新增：连接数阈值
    connection_warning_threshold: int = 50  # 连接数警告阈值
    connection_critical_threshold: int = 100  # 连接数严重阈值

    # 🔧 新增：线程数阈值
    thread_warning_threshold: int = 20  # 线程数警告阈值
    thread_critical_threshold: int = 50  # 线程数严重阈值

    # 监控间隔
    monitor_interval: int = 60  # 监控间隔60秒
    cleanup_interval: int = 300  # 清理间隔5分钟
    gc_interval: int = 120  # GC间隔2分钟

    # 统计数据保留
    max_stats_history: int = 1000  # 最大统计历史记录
    stats_cleanup_size: int = 500  # 清理后保留的记录数

    # 连接清理
    connection_timeout: int = 3600  # 连接超时1小时
    max_idle_connections: int = 10  # 最大空闲连接数

    # 强制清理“冷静期”
    forced_cleanup_cooldown_seconds: int = 60  # 60s 内不重新触发强制清理


class SystemResourceManager:
    """
    系统资源管理器 - 统一监控内存、CPU、文件描述符等系统资源
    """

    def __init__(self, config: SystemResourceConfig = None):
        self.config = config or SystemResourceConfig()
        self.logger = structlog.get_logger(__name__)

        # 资源统计历史
        self.stats_history: List[SystemResourceStats] = []
        self.last_cleanup_time = time.time()
        self.last_gc_time = time.time()

        # 运行状态
        self.is_running = False
        self.monitor_task: Optional[asyncio.Task] = None
        self.cleanup_task: Optional[asyncio.Task] = None

        # 进程信息
        self.process = psutil.Process()

        # 🔧 扩展统计计数器
        self.counters = {
            'total_cleanups': 0,
            'forced_gc_count': 0,
            'memory_warnings': 0,
            'memory_criticals': 0,
            'cpu_warnings': 0,
            'cpu_criticals': 0,
            'fd_warnings': 0,
            'fd_criticals': 0,
            'connection_warnings': 0,
            'connection_criticals': 0,
            'thread_warnings': 0,
            'thread_criticals': 0,
            'forced_cleanup_cooldown_skips': 0
        }
        # 冷静期：防止短时间内重复强制清理导致CPU抖动
        self.last_forced_cleanup_time = 0.0

        # 连接池引用（由外部设置）
        self.connection_pools: List[Any] = []
        self.data_buffers: List[Any] = []

        # 🔧 新增：资源趋势分析
        self.trend_analysis = {
            'memory_trend': 'stable',
            'cpu_trend': 'stable',
            'fd_trend': 'stable',
            'connection_trend': 'stable'
        }

        self.logger.info("系统资源管理器初始化完成", config=self.config)

    async def start(self):
        """启动内存管理器"""
        if self.is_running:
            return

        self.is_running = True

        # 启动监控任务
        self.monitor_task = asyncio.create_task(self._system_monitor_loop())
        self.cleanup_task = asyncio.create_task(self._system_cleanup_loop())

        self.logger.info("系统资源管理器已启动",
                        memory_warning_threshold=f"{self.config.memory_warning_threshold_mb}MB",
                        memory_critical_threshold=f"{self.config.memory_critical_threshold_mb}MB",
                        cpu_critical_threshold=f"{self.config.cpu_critical_threshold}%",
                        fd_critical_threshold=f"{self.config.fd_critical_threshold*100}%")

    async def stop(self):
        """停止内存管理器"""
        self.is_running = False

        # 取消任务
        if self.monitor_task and not self.monitor_task.done():
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass

        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass

        self.logger.info("内存管理器已停止")

    def register_connection_pool(self, pool: Any):
        """注册连接池以便清理"""
        self.connection_pools.append(pool)
        self.logger.debug("注册连接池", pool_type=type(pool).__name__)

    def register_data_buffer(self, buffer: Any):
        """注册数据缓冲区以便清理"""
        self.data_buffers.append(buffer)
        self.logger.debug("注册数据缓冲区", buffer_type=type(buffer).__name__)

    async def _system_monitor_loop(self):
        """系统资源监控循环"""
        while self.is_running:
            try:
                await self._collect_system_stats()
                await self._check_all_resource_thresholds()
                await self._analyze_resource_trends()
                await asyncio.sleep(self.config.monitor_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("系统资源监控异常", error=str(e), exc_info=True)
                await asyncio.sleep(self.config.monitor_interval)

    async def _system_cleanup_loop(self):
        """系统资源清理循环"""
        while self.is_running:
            try:
                await self._perform_system_cleanup()
                await asyncio.sleep(self.config.cleanup_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("系统资源清理异常", error=str(e), exc_info=True)
                await asyncio.sleep(self.config.cleanup_interval)

    async def _collect_system_stats(self):
        """收集完整的系统资源统计信息"""
        try:
            # 内存信息
            memory_info = self.process.memory_info()
            memory_percent = self.process.memory_percent()

            # 🔧 CPU信息
            cpu_percent = self.process.cpu_percent()
            cpu_count = psutil.cpu_count()

            # 🔧 文件描述符信息
            try:
                num_fds = self.process.num_fds()
                # 获取系统文件描述符限制
                import resource
                max_fds = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
                fd_usage_percent = (num_fds / max_fds) * 100
            except (AttributeError, OSError):
                num_fds = 0
                max_fds = 1024  # 默认值
                fd_usage_percent = 0.0

            # 🔧 网络连接信息
            try:
                connections = self.process.connections()
                num_connections = len(connections)
                tcp_connections = len([c for c in connections if c.type == 1])  # SOCK_STREAM
            except (psutil.AccessDenied, OSError):
                num_connections = 0
                tcp_connections = 0

            # 🔧 线程信息
            try:
                num_threads = self.process.num_threads()
            except (psutil.AccessDenied, OSError):
                num_threads = 1

            # 🔧 系统负载信息
            try:
                load_avg = psutil.getloadavg()
                load_avg_1min = load_avg[0]
                load_avg_5min = load_avg[1]
            except (AttributeError, OSError):
                load_avg_1min = 0.0
                load_avg_5min = 0.0

            # 获取GC统计
            gc_stats = gc.get_stats()
            total_collections = sum(stat['collections'] for stat in gc_stats)

            # 获取对象数量
            objects_count = len(gc.get_objects())

            stats = SystemResourceStats(
                timestamp=time.time(),
                rss_mb=memory_info.rss / 1024 / 1024,
                vms_mb=memory_info.vms / 1024 / 1024,
                memory_percent=memory_percent,
                gc_collections=total_collections,
                objects_count=objects_count,
                cpu_percent=cpu_percent,
                cpu_count=cpu_count,
                num_fds=num_fds,
                max_fds=max_fds,
                fd_usage_percent=fd_usage_percent,
                num_connections=num_connections,
                tcp_connections=tcp_connections,
                num_threads=num_threads,
                load_avg_1min=load_avg_1min,
                load_avg_5min=load_avg_5min
            )

            self.stats_history.append(stats)

            # 限制历史记录大小
            if len(self.stats_history) > self.config.max_stats_history:
                self.stats_history = self.stats_history[-self.config.stats_cleanup_size:]
                self.logger.debug("清理系统资源统计历史记录")

        except Exception as e:
            self.logger.error("收集系统资源统计失败", error=str(e), exc_info=True)

    def _get_effective_cpu_cores(self) -> float:
        """基于 cgroup 配额估算容器内可用的“有效CPU核心数”。
        优先读取 cgroups v2 (/sys/fs/cgroup/cpu.max)，回退到 cgroups v1
        (/sys/fs/cgroup/cpu/cpu.cfs_quota_us 与 cpu.cfs_period_us)。
        若无法获取或为“max”，则回退到 psutil.cpu_count()。
        """
        try:
            # cgroups v2
            path_v2 = "/sys/fs/cgroup/cpu.max"
            try:
                with open(path_v2, "r") as f:
                    content = f.read().strip()
                # 格式: "quota period"，例如 "100000 100000"；或 "max 100000"
                parts = content.split()
                if len(parts) >= 2:
                    quota_s, period_s = parts[0], parts[1]
                    if quota_s != "max":
                        quota = float(quota_s)
                        period = float(period_s) if float(period_s) > 0 else 100000.0
                        if quota > 0 and period > 0:
                            eff = max(0.1, quota / period)
                            return eff
            except FileNotFoundError:
                pass
            except Exception:
                pass

            # cgroups v1
            path_quota = "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"
            path_period = "/sys/fs/cgroup/cpu/cpu.cfs_period_us"
            try:
                with open(path_quota, "r") as fq, open(path_period, "r") as fp:
                    quota = float(fq.read().strip())
                    period = float(fp.read().strip())
                if quota > 0 and period > 0:
                    eff = max(0.1, quota / period)
                    return eff
            except FileNotFoundError:
                pass
            except Exception:
                pass
        except Exception:
            pass
        # 回退：使用宿主可见的逻辑核心数
        try:
            return float(psutil.cpu_count() or 1)
        except Exception:
            return 1.0

    async def _check_all_resource_thresholds(self):
        """检查所有系统资源阈值"""
        if not self.stats_history:
            return

        current_stats = self.stats_history[-1]

        # 检查内存阈值
        await self._check_memory_thresholds(current_stats)

        # 🔧 检查CPU阈值
        await self._check_cpu_thresholds(current_stats)

        # 🔧 检查文件描述符阈值
        await self._check_fd_thresholds(current_stats)

        # 🔧 检查连接数阈值
        await self._check_connection_thresholds(current_stats)

        # 🔧 检查线程数阈值
        await self._check_thread_thresholds(current_stats)

    async def _check_memory_thresholds(self, current_stats: SystemResourceStats):
        """检查内存阈值"""
        # 动态阈值调整：基于系统可用内存
        system_memory = psutil.virtual_memory()
        available_memory_gb = system_memory.available / 1024 / 1024 / 1024

        # 如果系统内存充足，提高阈值；如果紧张，降低阈值
        if available_memory_gb > 2.0:  # 系统内存充足
            dynamic_warning_threshold = self.config.memory_warning_threshold_mb * 1.2
            dynamic_critical_threshold = self.config.memory_critical_threshold_mb * 1.2
        elif available_memory_gb < 1.0:  # 系统内存紧张
            dynamic_warning_threshold = self.config.memory_warning_threshold_mb * 0.8
            dynamic_critical_threshold = self.config.memory_critical_threshold_mb * 0.8
        else:
            dynamic_warning_threshold = self.config.memory_warning_threshold_mb
            dynamic_critical_threshold = self.config.memory_critical_threshold_mb

        if current_stats.rss_mb >= dynamic_critical_threshold:
            self.counters['memory_criticals'] += 1
            self.logger.error("🚨 内存使用达到严重阈值",
                            current_mb=current_stats.rss_mb,
                            dynamic_threshold_mb=dynamic_critical_threshold,
                            original_threshold_mb=self.config.memory_critical_threshold_mb,
                            system_available_gb=available_memory_gb,
                            percent=current_stats.memory_percent)

            # 冷静期：避免在极短时间内重复强制清理导致CPU抖动
            now_ts = time.time()
            if now_ts - getattr(self, 'last_forced_cleanup_time', 0.0) < self.config.forced_cleanup_cooldown_seconds:
                self.counters['forced_cleanup_cooldown_skips'] = self.counters.get('forced_cleanup_cooldown_skips', 0) + 1
                self.logger.warning("⏳ 处于清理冷静期，跳过本次强制清理",
                                    cooldown_seconds=self.config.forced_cleanup_cooldown_seconds,
                                    seconds_since_last=now_ts - getattr(self, 'last_forced_cleanup_time', 0.0))
            else:
                await self._force_system_cleanup()
                self.last_forced_cleanup_time = now_ts

        elif current_stats.rss_mb >= dynamic_warning_threshold:
            self.counters['memory_warnings'] += 1
            self.logger.warning("⚠️ 内存使用达到警告阈值",
                              current_mb=current_stats.rss_mb,
                              dynamic_threshold_mb=dynamic_warning_threshold,
                              original_threshold_mb=self.config.memory_warning_threshold_mb,
                              system_available_gb=available_memory_gb,
                              percent=current_stats.memory_percent)

    async def _check_cpu_thresholds(self, current_stats: SystemResourceStats):
        """检查CPU使用率阈值（多核友好）：结合进程CPU%与LoadAvg/CPU核数"""
        normalized_load = 0.0
        try:
            normalized_load = (current_stats.load_avg_1min / max(1, current_stats.cpu_count)) if current_stats.cpu_count else 0.0
        except Exception:
            normalized_load = 0.0

        # 严重：进程CPU占用高 且 系统整体负载归一化也高，避免单核满载误报
        if (current_stats.cpu_percent >= self.config.cpu_critical_threshold \
            and normalized_load >= self.config.cpu_loadavg_critical_ratio):
            self.counters['cpu_criticals'] += 1
            self.logger.error("🚨 CPU使用率达到严重阈值（多核判定）",
                              current_percent=current_stats.cpu_percent,
                              threshold_percent=self.config.cpu_critical_threshold,
                              cpu_count=current_stats.cpu_count,
                              load_avg_1min=current_stats.load_avg_1min,
                              normalized_load=normalized_load,
                              normalized_threshold=self.config.cpu_loadavg_critical_ratio)

        # 警告：同理
        elif (current_stats.cpu_percent >= self.config.cpu_warning_threshold \
              and normalized_load >= self.config.cpu_loadavg_warning_ratio):
            self.counters['cpu_warnings'] += 1
            self.logger.warning("⚠️ CPU使用率达到警告阈值（多核判定）",
                                current_percent=current_stats.cpu_percent,
                                threshold_percent=self.config.cpu_warning_threshold,
                                cpu_count=current_stats.cpu_count,
                                load_avg_1min=current_stats.load_avg_1min,
                                normalized_load=normalized_load,
                                normalized_threshold=self.config.cpu_loadavg_warning_ratio)

    async def _check_fd_thresholds(self, current_stats: SystemResourceStats):
        """检查文件描述符使用率阈值"""
        if current_stats.fd_usage_percent >= self.config.fd_critical_threshold * 100:
            self.counters['fd_criticals'] += 1
            self.logger.error("🚨 文件描述符使用率达到严重阈值",
                            current_fds=current_stats.num_fds,
                            max_fds=current_stats.max_fds,
                            usage_percent=current_stats.fd_usage_percent,
                            threshold_percent=self.config.fd_critical_threshold * 100)

        elif current_stats.fd_usage_percent >= self.config.fd_warning_threshold * 100:
            self.counters['fd_warnings'] += 1
            self.logger.warning("⚠️ 文件描述符使用率达到警告阈值",
                              current_fds=current_stats.num_fds,
                              max_fds=current_stats.max_fds,
                              usage_percent=current_stats.fd_usage_percent,
                              threshold_percent=self.config.fd_warning_threshold * 100)

    async def _check_connection_thresholds(self, current_stats: SystemResourceStats):
        """检查网络连接数阈值"""
        if current_stats.num_connections >= self.config.connection_critical_threshold:
            self.counters['connection_criticals'] += 1
            self.logger.error("🚨 网络连接数达到严重阈值",
                            current_connections=current_stats.num_connections,
                            tcp_connections=current_stats.tcp_connections,
                            threshold=self.config.connection_critical_threshold)

        elif current_stats.num_connections >= self.config.connection_warning_threshold:
            self.counters['connection_warnings'] += 1
            self.logger.warning("⚠️ 网络连接数达到警告阈值",
                              current_connections=current_stats.num_connections,
                              tcp_connections=current_stats.tcp_connections,
                              threshold=self.config.connection_warning_threshold)

    async def _check_thread_thresholds(self, current_stats: SystemResourceStats):
        """检查线程数阈值"""
        if current_stats.num_threads >= self.config.thread_critical_threshold:
            self.counters['thread_criticals'] += 1
            self.logger.error("🚨 线程数达到严重阈值",
                            current_threads=current_stats.num_threads,
                            threshold=self.config.thread_critical_threshold)

        elif current_stats.num_threads >= self.config.thread_warning_threshold:
            self.counters['thread_warnings'] += 1
            self.logger.warning("⚠️ 线程数达到警告阈值",
                              current_threads=current_stats.num_threads,
                              threshold=self.config.thread_warning_threshold)

    async def _analyze_resource_trends(self):
        """分析资源使用趋势"""
        if len(self.stats_history) < 10:  # 需要至少10个数据点
            return

        # 获取最近的统计数据
        recent_stats = self.stats_history[-10:]

        # 分析内存趋势
        memory_values = [stat.rss_mb for stat in recent_stats]
        self.trend_analysis['memory_trend'] = self._calculate_trend(memory_values)

        # 分析CPU趋势
        cpu_values = [stat.cpu_percent for stat in recent_stats]
        self.trend_analysis['cpu_trend'] = self._calculate_trend(cpu_values)

        # 分析文件描述符趋势
        fd_values = [stat.num_fds for stat in recent_stats]
        self.trend_analysis['fd_trend'] = self._calculate_trend(fd_values)

        # 分析连接数趋势
        connection_values = [stat.num_connections for stat in recent_stats]
        self.trend_analysis['connection_trend'] = self._calculate_trend(connection_values)

        # 记录趋势分析结果
        self.logger.debug("资源趋势分析",
                         memory_trend=self.trend_analysis['memory_trend'],
                         cpu_trend=self.trend_analysis['cpu_trend'],
                         fd_trend=self.trend_analysis['fd_trend'],
                         connection_trend=self.trend_analysis['connection_trend'])

        # 检查是否有持续增长的趋势
        await self._check_trend_warnings()

    def _calculate_trend(self, values: List[float]) -> str:
        """计算数值趋势"""
        if len(values) < 3:
            return 'insufficient_data'

        # 计算线性回归斜率
        n = len(values)
        x = list(range(n))

        # 计算斜率
        sum_x = sum(x)
        sum_y = sum(values)
        sum_xy = sum(x[i] * values[i] for i in range(n))
        sum_x2 = sum(x[i] ** 2 for i in range(n))

        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)

        # 判断趋势（阈值更保守，减少误报）
        if abs(slope) < 0.2:
            return 'stable'
        elif slope > 1.0:
            return 'rapidly_increasing'
        elif slope > 0.2:
            return 'slowly_increasing'
        elif slope < -1.0:
            return 'rapidly_decreasing'
        elif slope < -0.2:
            return 'slowly_decreasing'
        else:
            return 'stable'

    async def _check_trend_warnings(self):
        """检查趋势警告（慢增→INFO，快增→WARNING）"""
        rapid_msgs = []
        slow_msgs = []

        if self.trend_analysis['memory_trend'] == 'rapidly_increasing':
            rapid_msgs.append('内存使用呈 rapidly_increasing 趋势')
        elif self.trend_analysis['memory_trend'] == 'slowly_increasing':
            slow_msgs.append('内存使用呈 slowly_increasing 趋势')

        if self.trend_analysis['cpu_trend'] == 'rapidly_increasing':
            rapid_msgs.append('CPU使用率呈 rapidly_increasing 趋势')
        elif self.trend_analysis['cpu_trend'] == 'slowly_increasing':
            slow_msgs.append('CPU使用率呈 slowly_increasing 趋势')

        if self.trend_analysis['fd_trend'] == 'rapidly_increasing':
            rapid_msgs.append('文件描述符使用呈 rapidly_increasing 趋势')
        elif self.trend_analysis['fd_trend'] == 'slowly_increasing':
            slow_msgs.append('文件描述符使用呈 slowly_increasing 趋势')

        if self.trend_analysis['connection_trend'] == 'rapidly_increasing':
            rapid_msgs.append('网络连接数呈 rapidly_increasing 趋势')
        elif self.trend_analysis['connection_trend'] == 'slowly_increasing':
            slow_msgs.append('网络连接数呈 slowly_increasing 趋势')

        if rapid_msgs:
            self.logger.warning('🔍 资源使用趋势警告', warnings=rapid_msgs)
        if slow_msgs:
            self.logger.info('ℹ️ 资源使用趋势提示', infos=slow_msgs)



    async def _perform_system_cleanup(self):
        """🔧 修复：执行系统资源清理 - 增强内存管理"""
        start_time = time.time()

        try:
            # 🔧 修复：检查当前内存使用情况，决定清理强度
            current_memory = self.process.memory_info().rss / 1024 / 1024
            cleanup_intensity = "normal"

            if current_memory > self.config.memory_critical_threshold_mb:
                cleanup_intensity = "aggressive"
            elif current_memory > self.config.memory_warning_threshold_mb:
                cleanup_intensity = "moderate"

            self.logger.debug("开始内存清理",
                            current_memory_mb=current_memory,
                            cleanup_intensity=cleanup_intensity)

            # 1. 清理过期连接
            await self._cleanup_expired_connections()

            # 2. 🔧 修复：根据内存压力调整数据缓冲区清理
            await self._cleanup_data_buffers(intensity=cleanup_intensity)

            # 3. 重置统计计数器
            await self._reset_statistics_counters()

            # 4. 🔧 修复：更频繁的垃圾回收在高内存使用时
            gc_interval = self.config.gc_interval
            if cleanup_intensity == "aggressive":
                gc_interval = min(gc_interval, 30)  # 最多30秒一次
            elif cleanup_intensity == "moderate":
                gc_interval = min(gc_interval, 60)  # 最多60秒一次

            if time.time() - self.last_gc_time > gc_interval:
                await self._force_garbage_collection()
                self.last_gc_time = time.time()

            self.counters['total_cleanups'] += 1
            self.last_cleanup_time = time.time()

            # 🔧 修复：检查清理效果
            after_memory = self.process.memory_info().rss / 1024 / 1024
            memory_freed = current_memory - after_memory

            cleanup_duration = time.time() - start_time
            self.logger.info("内存清理完成",
                           duration_ms=int(cleanup_duration * 1000),
                           memory_before_mb=current_memory,
                           memory_after_mb=after_memory,
                           memory_freed_mb=memory_freed,
                           cleanup_intensity=cleanup_intensity,
                           total_cleanups=self.counters['total_cleanups'])

        except Exception as e:
            self.logger.error("内存清理失败", error=str(e), exc_info=True)

    async def _force_system_cleanup(self):
        """强制系统资源清理（紧急情况）"""
        self.logger.warning("🚨 执行强制内存清理")

        # 立即执行所有清理操作（加大强度，先做渐进压缩再GC）
        await self._cleanup_expired_connections()
        await self._cleanup_data_buffers(intensity="aggressive")
        await self._force_garbage_collection()

        # 如果内存仍然过高，记录详细信息
        current_memory = self.process.memory_info().rss / 1024 / 1024
        if current_memory >= self.config.memory_critical_threshold_mb:
            self.logger.error("🚨 强制清理后内存仍然过高",
                            current_mb=current_memory,
                            objects_count=len(gc.get_objects()))

    async def _cleanup_expired_connections(self):
        """清理过期连接"""
        cleaned_count = 0
        current_time = time.time()

        for pool in self.connection_pools:
            if hasattr(pool, 'connections') and hasattr(pool, 'connection_start_times'):
                expired_keys = []

                for conn_id, start_time in pool.connection_start_times.items():
                    if current_time - start_time > self.config.connection_timeout:
                        expired_keys.append(conn_id)

                for conn_id in expired_keys:
                    try:
                        if conn_id in pool.connections:
                            await pool.connections[conn_id].close()
                            del pool.connections[conn_id]
                            cleaned_count += 1

                        if conn_id in pool.connection_start_times:
                            del pool.connection_start_times[conn_id]

                    except Exception as e:
                        self.logger.warning("清理过期连接失败", conn_id=conn_id, error=str(e))

        if cleaned_count > 0:
            self.logger.info("清理过期连接完成", cleaned_count=cleaned_count)

    async def _cleanup_data_buffers(self, intensity: str = "normal"):
        """🔧 修复：智能清理数据缓冲区 - 支持不同清理强度"""
        cleaned_count = 0
        current_time = time.time()

        # 🔧 修复：根据清理强度设置不同的阈值
        if intensity == "aggressive":
            buffer_size_threshold = 1000
            keep_records = 500
            force_clear_threshold = self.config.memory_warning_threshold_mb * 0.8
        elif intensity == "moderate":
            buffer_size_threshold = 1500
            keep_records = 750
            force_clear_threshold = self.config.memory_warning_threshold_mb
        else:  # normal
            buffer_size_threshold = 2000
            keep_records = 1000
            force_clear_threshold = self.config.memory_warning_threshold_mb * 1.2

        for buffer in self.data_buffers:
            try:
                # 🎯 智能数据生命周期管理（优先低成本→中成本→高成本）
                # Phase 1: 过期项清理（低成本）
                if hasattr(buffer, 'items') and hasattr(buffer, 'get'):
                    # 🔧 字典类型缓存的时间基础清理（若有timestamps）
                    if hasattr(buffer, 'timestamps') and isinstance(buffer.timestamps, dict):
                        expired_keys = []
                        for key, timestamp in list(buffer.timestamps.items()):
                            try:
                                if current_time - float(timestamp) > 3600:  # 1小时过期
                                    expired_keys.append(key)
                            except Exception:
                                continue
                        for key in expired_keys:
                            try:
                                if key in buffer:
                                    del buffer[key]
                                if key in buffer.timestamps:
                                    del buffer.timestamps[key]
                                cleaned_count += 1
                            except Exception:
                                pass

                # Phase 2: 状态对象的暂存/历史压缩（中成本）
                # 例如：orderbook_states: {key->OrderBookState(update_buffer=deque,...)}
                try:
                    sample_val = None
                    if hasattr(buffer, 'values'):
                        for _v in buffer.values():
                            sample_val = _v
                            break
                    if sample_val is not None and sample_val.__class__.__name__ == 'OrderBookState':
                        for state in list(buffer.values()):
                            # 压缩增量缓冲（deque/list）
                            upd_buf = getattr(state, 'update_buffer', None)
                            if upd_buf is not None and hasattr(upd_buf, '__len__'):
                                try:
                                    if len(upd_buf) > keep_records:
                                        if hasattr(upd_buf, 'popleft'):
                                            # deque：弹出旧元素直到目标大小
                                            while len(upd_buf) > keep_records:
                                                upd_buf.popleft()
                                        else:
                                            # list：切片保留
                                            try:
                                                upd_buf[:] = list(upd_buf)[-keep_records:]
                                            except Exception:
                                                upd_buf = list(upd_buf)[-keep_records:]
                                        cleaned_count += 1
                                except Exception:
                                    pass
                            # 长时间未更新的状态：清空增量缓冲以释放内存
                            try:
                                last_upd = getattr(state, 'last_update_time', None)
                                if last_upd is not None:
                                    # 10分钟未更新则清空临时增量缓冲
                                    last_ts = getattr(last_upd, 'timestamp', lambda: None)()
                                    if last_ts is not None and (time.time() - float(last_ts) > 600):
                                        if upd_buf is not None:
                                            if hasattr(upd_buf, 'clear'):
                                                upd_buf.clear()
                                            else:
                                                try:
                                                    while len(upd_buf) > 0:
                                                        if hasattr(upd_buf, 'pop'): upd_buf.pop(0)
                                                        else: break
                                                except Exception:
                                                    pass
                                            cleaned_count += 1
                            except Exception:
                                pass
                except Exception:
                    pass

                # Phase 2.5: 字典型的消息缓冲(dict[str, list[{message,timestamp}]])（中成本）
                try:
                    if isinstance(buffer, dict):
                        for _k, _lst in list(buffer.items()):
                            if isinstance(_lst, list) and len(_lst) > 0:
                                # 先按时间过滤过期项（默认30秒，避免无限增长）
                                try:
                                    _before = len(_lst)
                                    _lst[:] = [it for it in _lst
                                               if not isinstance(it, dict) or 'timestamp' not in it
                                               or (current_time - float(it.get('timestamp', current_time))) < 30.0]
                                    if len(_lst) < _before:
                                        cleaned_count += 1
                                except Exception:
                                    pass
                                # 再按长度限制，仅保留最近 keep_records 条
                                try:
                                    if len(_lst) > keep_records:
                                        buffer[_k] = _lst[-keep_records:]
                                        cleaned_count += 1
                                except Exception:
                                    pass
                except Exception:
                    pass

                # Phase 3: 大型顺序缓冲（中成本）
                if hasattr(buffer, 'data') and isinstance(getattr(buffer, 'data', None), list):
                    if len(buffer.data) > buffer_size_threshold:
                        # 保留最近的记录，确保数据连续性
                        buffer.data = buffer.data[-keep_records:]
                        cleaned_count += 1

                # Phase 4: 高成本/最后兜底（尽量避免）：整体clear仅在极高内存压力下
                if hasattr(buffer, 'clear'):
                    current_memory = self.process.memory_info().rss / 1024 / 1024
                    if current_memory > force_clear_threshold and intensity == 'aggressive':
                        buffer.clear()
                        cleaned_count += 1

            except Exception as e:
                self.logger.warning("清理数据缓冲区失败", buffer_type=type(buffer).__name__, error=str(e))

        if cleaned_count > 0:
            self.logger.info("智能数据缓冲区清理完成", cleaned_count=cleaned_count)

    async def _reset_statistics_counters(self):
        """重置统计计数器"""
        # 每小时重置一次计数器，避免无限增长
        if time.time() - self.last_cleanup_time > 3600:
            old_counters = self.counters.copy()

            # 重置计数器但保留重要统计
            self.counters = {
                'total_cleanups': 0,
                'forced_gc_count': 0,
                'memory_warnings': 0,
                'memory_criticals': 0
            }

            self.logger.info("重置统计计数器", old_counters=old_counters)

    async def _force_garbage_collection(self):
        """强制垃圾回收"""
        try:
            # 执行完整的垃圾回收
            collected = gc.collect()
            self.counters['forced_gc_count'] += 1

            self.logger.debug("强制垃圾回收完成",
                            collected_objects=collected,
                            total_gc_count=self.counters['forced_gc_count'])

        except Exception as e:
            self.logger.error("强制垃圾回收失败", error=str(e))

    def get_system_resource_status(self) -> Dict[str, Any]:
        """获取完整的系统资源状态"""
        if not self.stats_history:
            return {"status": "no_data"}

        current_stats = self.stats_history[-1]

        # 计算各种资源的增长趋势
        memory_trend = "stable"
        cpu_trend = "stable"
        fd_trend = "stable"
        connection_trend = "stable"

        if len(self.stats_history) >= 10:
            # 内存趋势
            recent_memory_avg = sum(s.rss_mb for s in self.stats_history[-5:]) / 5
            older_memory_avg = sum(s.rss_mb for s in self.stats_history[-10:-5]) / 5

            if recent_memory_avg > older_memory_avg * 1.1:
                memory_trend = "increasing"
            elif recent_memory_avg < older_memory_avg * 0.9:
                memory_trend = "decreasing"

            # CPU趋势
            recent_cpu_avg = sum(s.cpu_percent for s in self.stats_history[-5:]) / 5
            older_cpu_avg = sum(s.cpu_percent for s in self.stats_history[-10:-5]) / 5

            if recent_cpu_avg > older_cpu_avg * 1.2:
                cpu_trend = "increasing"
            elif recent_cpu_avg < older_cpu_avg * 0.8:
                cpu_trend = "decreasing"

            # 文件描述符趋势
            recent_fd_avg = sum(s.num_fds for s in self.stats_history[-5:]) / 5
            older_fd_avg = sum(s.num_fds for s in self.stats_history[-10:-5]) / 5

            if recent_fd_avg > older_fd_avg * 1.1:
                fd_trend = "increasing"
            elif recent_fd_avg < older_fd_avg * 0.9:
                fd_trend = "decreasing"

            # 连接数趋势
            recent_conn_avg = sum(s.num_connections for s in self.stats_history[-5:]) / 5
            older_conn_avg = sum(s.num_connections for s in self.stats_history[-10:-5]) / 5

            if recent_conn_avg > older_conn_avg * 1.1:
                connection_trend = "increasing"
            elif recent_conn_avg < older_conn_avg * 0.9:
                connection_trend = "decreasing"

        return {
            # 内存信息
            "current_memory_mb": current_stats.rss_mb,
            "virtual_memory_mb": current_stats.vms_mb,
            "memory_percent": current_stats.memory_percent,
            "objects_count": current_stats.objects_count,
            "memory_trend": memory_trend,

            # CPU信息
            "cpu_percent": current_stats.cpu_percent,
            "cpu_count": current_stats.cpu_count,
            "cpu_effective_cores": self._get_effective_cpu_cores(),
            "cpu_trend": cpu_trend,
            "load_avg_1min": current_stats.load_avg_1min,
            "load_avg_5min": current_stats.load_avg_5min,

            # 文件描述符信息
            "num_fds": current_stats.num_fds,
            "max_fds": current_stats.max_fds,
            "fd_usage_percent": current_stats.fd_usage_percent,
            "fd_trend": fd_trend,

            # 网络连接信息
            "num_connections": current_stats.num_connections,
            "tcp_connections": current_stats.tcp_connections,
            "connection_trend": connection_trend,

            # 线程信息
            "num_threads": current_stats.num_threads,

            # 趋势分析
            "trend_analysis": self.trend_analysis.copy(),

            # 统计计数器
            "counters": self.counters.copy(),
            "last_cleanup": self.last_cleanup_time,
            "is_running": self.is_running,
            "stats_count": len(self.stats_history)
        }

    # 保持向后兼容性
    def get_memory_status(self) -> Dict[str, Any]:
        """获取内存状态（向后兼容）"""
        full_status = self.get_system_resource_status()
        if full_status.get("status") == "no_data":
            return full_status

        # 返回只包含内存相关信息的子集
        return {
            "current_memory_mb": full_status["current_memory_mb"],
            "memory_percent": full_status["memory_percent"],
            "objects_count": full_status["objects_count"],
            "growth_trend": full_status["memory_trend"],
            "counters": {k: v for k, v in full_status["counters"].items() if 'memory' in k or k in ['total_cleanups', 'forced_gc_count']},
            "last_cleanup": full_status["last_cleanup"],
            "is_running": full_status["is_running"]
        }


# 🔧 更新类型别名以保持向后兼容性
MemoryManager = SystemResourceManager
MemoryConfig = SystemResourceConfig
MemoryStats = SystemResourceStats
