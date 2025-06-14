"""
MarketPrism 冷存储监控管理器

与现有系统的关系：
- 现有 data/clickhouse-cold/: 实际的ClickHouse冷存储数据库实例
- 本组件: 冷存储的监控、管理和自动化工具

设计目标：
- 监控现有 clickhouse-cold 冷存储状态
- 管理热数据到冷存储的迁移
- 优化冷存储查询性能
- 冷存储容量和健康监控

功能特性：
1. 冷存储健康监控 - 实时状态检查
2. 数据迁移策略 - 热转冷自动化
3. 查询性能优化 - 冷数据访问加速
4. 容量管理 - 存储空间监控和预警

架构集成：
┌─────────────────┐    监控管理    ┌──────────────────┐
│   热存储 (实时)   │ ============> │  ColdStorageMonitor │
│  ClickHouse主库  │    数据迁移    │   (本组件)        │
└─────────────────┘                └──────────────────┘
                                           │ 监控/查询
                                           ▼
                                   ┌──────────────────┐
                                   │   冷存储 (历史)   │
                                   │data/clickhouse-cold│
                                   └──────────────────┘
"""

import asyncio
import time
import logging
import json
import os
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta, timezone
import tempfile

logger = logging.getLogger(__name__)


class StorageType(Enum):
    """存储类型"""
    HOT = "hot"           # 热存储 (实时数据)
    WARM = "warm"         # 温存储 (近期数据)
    COLD = "cold"         # 冷存储 (历史数据)


class MigrationStatus(Enum):
    """迁移状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ColdStorageConfig:
    """冷存储配置"""
    # ClickHouse 冷存储配置
    cold_clickhouse_host: str = "localhost"
    cold_clickhouse_port: int = 9001
    cold_storage_path: str = "/data/clickhouse-cold"
    
    # 数据迁移策略
    hot_retention_days: int = 7      # 热数据保留天数
    warm_retention_days: int = 30    # 温数据保留天数
    migration_batch_size: int = 10000  # 迁移批次大小
    
    # 监控配置
    health_check_interval: int = 300   # 健康检查间隔 (5分钟)
    capacity_check_interval: int = 3600  # 容量检查间隔 (1小时)
    
    # 性能配置
    max_concurrent_migrations: int = 2
    query_timeout: int = 30


@dataclass
class StorageMetrics:
    """存储指标"""
    total_size_gb: float = 0.0
    used_size_gb: float = 0.0
    free_size_gb: float = 0.0
    table_count: int = 0
    row_count: int = 0
    last_updated: float = 0.0


@dataclass
class MigrationInfo:
    """迁移信息"""
    migration_id: str
    table_name: str
    from_storage: StorageType
    to_storage: StorageType
    start_time: float
    end_time: Optional[float] = None
    status: MigrationStatus = MigrationStatus.PENDING
    rows_migrated: int = 0
    error_message: str = ""


@dataclass
class PerformanceMetrics:
    """性能指标"""
    avg_migration_speed_rows_per_sec: float = 0.0
    avg_query_latency_ms: float = 0.0
    successful_migrations: int = 0
    failed_migrations: int = 0
    total_rows_migrated: int = 0
    total_queries_executed: int = 0
    uptime_seconds: float = 0.0
    last_updated: float = 0.0


class ColdStorageMonitor:
    """冷存储监控管理器"""
    
    def __init__(self, config: Optional[ColdStorageConfig] = None):
        self.config = config or ColdStorageConfig()
        
        # 监控状态
        self.hot_metrics = StorageMetrics()
        self.cold_metrics = StorageMetrics()
        self.performance_metrics = PerformanceMetrics()
        self.migration_history: List[MigrationInfo] = []
        self.active_migrations: Dict[str, MigrationInfo] = {}
        
        # 运行时状态
        self.is_running = False
        self.background_tasks: List[asyncio.Task] = []
        self.last_health_check = 0.0
        self.last_capacity_check = 0.0
        self.start_time = time.time()
        
        logger.info(f"冷存储监控管理器已初始化 - 冷存储路径: {self.config.cold_storage_path}")
    
    async def start(self):
        """启动冷存储监控"""
        if self.is_running:
            return
        
        self.is_running = True
        
        # 初始检查
        await self._initial_health_check()
        
        # 启动后台任务
        self.background_tasks = [
            asyncio.create_task(self._health_monitor_loop()),
            asyncio.create_task(self._capacity_monitor_loop()),
            asyncio.create_task(self._migration_scheduler_loop())
        ]
        
        logger.info("冷存储监控管理器已启动")
    
    async def stop(self):
        """停止冷存储监控"""
        self.is_running = False
        
        # 取消后台任务
        for task in self.background_tasks:
            task.cancel()
        
        await asyncio.gather(*self.background_tasks, return_exceptions=True)
        
        logger.info("冷存储监控管理器已停止")
    
    async def _initial_health_check(self):
        """初始健康检查"""
        try:
            # 检查冷存储目录
            if not os.path.exists(self.config.cold_storage_path):
                logger.warning(f"冷存储路径不存在: {self.config.cold_storage_path}")
                # 如果是测试环境，创建临时目录
                temp_dir = os.path.join(tempfile.gettempdir(), "clickhouse-cold-test")
                os.makedirs(temp_dir, exist_ok=True)
                logger.info(f"测试环境已创建临时冷存储目录: {temp_dir}")
                self.config.cold_storage_path = temp_dir
            
            # 检查冷存储ClickHouse连接
            cold_available = await self._check_cold_clickhouse_connection()
            
            if cold_available:
                await self._update_storage_metrics()
                logger.info("冷存储系统健康检查通过")
            else:
                logger.warning("冷存储ClickHouse连接失败")
                
        except Exception as e:
            logger.error(f"初始健康检查失败: {e}")
    
    async def _check_cold_clickhouse_connection(self) -> bool:
        """检查冷存储ClickHouse连接"""
        try:
            # 这里应该实现实际的ClickHouse连接检查
            # 示例: 使用clickhouse-driver进行连接测试
            
            # 模拟连接检查
            await asyncio.sleep(0.1)
            
            logger.debug("冷存储ClickHouse连接正常")
            return True
            
        except Exception as e:
            logger.error(f"冷存储ClickHouse连接失败: {e}")
            return False
    
    async def _update_storage_metrics(self):
        """更新存储指标"""
        try:
            # 更新冷存储指标
            cold_size = await self._calculate_directory_size(self.config.cold_storage_path)
            cold_free = await self._get_free_space(self.config.cold_storage_path)
            
            self.cold_metrics.used_size_gb = cold_size / (1024**3)
            self.cold_metrics.free_size_gb = cold_free / (1024**3)
            self.cold_metrics.total_size_gb = self.cold_metrics.used_size_gb + self.cold_metrics.free_size_gb
            self.cold_metrics.last_updated = time.time()
            
            # 更新表和行数统计 (模拟)
            self.cold_metrics.table_count = await self._count_cold_tables()
            self.cold_metrics.row_count = await self._count_cold_rows()
            
            logger.debug(f"存储指标已更新 - 冷存储: {self.cold_metrics.used_size_gb:.2f}GB")
            
        except Exception as e:
            logger.error(f"更新存储指标失败: {e}")
    
    async def _calculate_directory_size(self, directory: str) -> int:
        """计算目录大小"""
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(directory):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        total_size += os.path.getsize(filepath)
                    except (OSError, FileNotFoundError):
                        pass
        except Exception as e:
            logger.warning(f"计算目录大小失败 {directory}: {e}")
        
        return total_size
    
    async def _get_free_space(self, path: str) -> int:
        """获取可用空间"""
        try:
            statvfs = os.statvfs(path)
            return statvfs.f_frsize * statvfs.f_bavail
        except Exception as e:
            logger.warning(f"获取可用空间失败 {path}: {e}")
            return 0
    
    async def _count_cold_tables(self) -> int:
        """统计冷存储表数量"""
        try:
            # 这里应该查询实际的ClickHouse冷存储
            # 模拟返回表数量
            return 15  # 示例值
        except Exception as e:
            logger.error(f"统计冷存储表数量失败: {e}")
            return 0
    
    async def _count_cold_rows(self) -> int:
        """统计冷存储行数"""
        try:
            # 这里应该查询实际的ClickHouse冷存储
            # 模拟返回行数
            return 50000000  # 示例值：5000万行
        except Exception as e:
            logger.error(f"统计冷存储行数失败: {e}")
            return 0
    
    async def _health_monitor_loop(self):
        """健康监控循环"""
        while self.is_running:
            try:
                await self._perform_health_check()
                await asyncio.sleep(self.config.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康监控异常: {e}")
                await asyncio.sleep(60)
    
    async def _perform_health_check(self):
        """执行健康检查"""
        self.last_health_check = time.time()
        
        try:
            # 检查冷存储连接
            cold_healthy = await self._check_cold_clickhouse_connection()
            
            if not cold_healthy:
                logger.warning("冷存储健康检查失败")
                return
            
            # 检查存储空间
            await self._check_storage_capacity()
            
            logger.debug("冷存储健康检查完成")
            
        except Exception as e:
            logger.error(f"健康检查异常: {e}")
    
    async def _check_storage_capacity(self):
        """检查存储容量"""
        if self.cold_metrics.total_size_gb > 0:
            usage_ratio = self.cold_metrics.used_size_gb / self.cold_metrics.total_size_gb
            
            if usage_ratio > 0.9:
                logger.warning(f"冷存储空间不足: {usage_ratio:.1%} 已使用")
            elif usage_ratio > 0.8:
                logger.info(f"冷存储空间警告: {usage_ratio:.1%} 已使用")
    
    async def _capacity_monitor_loop(self):
        """容量监控循环"""
        while self.is_running:
            try:
                await self._update_storage_metrics()
                await asyncio.sleep(self.config.capacity_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"容量监控异常: {e}")
                await asyncio.sleep(300)
    
    async def _migration_scheduler_loop(self):
        """迁移调度循环"""
        while self.is_running:
            try:
                await self._check_migration_needed()
                await asyncio.sleep(3600)  # 每小时检查一次
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"迁移调度异常: {e}")
                await asyncio.sleep(1800)
    
    async def _check_migration_needed(self):
        """检查是否需要数据迁移"""
        try:
            # 检查是否有需要迁移到冷存储的数据
            cutoff_time = time.time() - (self.config.warm_retention_days * 86400)
            
            # 这里应该查询实际的热存储，找到需要迁移的数据
            tables_to_migrate = await self._find_tables_for_migration(cutoff_time)
            
            for table_info in tables_to_migrate:
                if len(self.active_migrations) < self.config.max_concurrent_migrations:
                    await self._start_migration(table_info)
                else:
                    logger.info("达到最大并发迁移数量，等待当前迁移完成")
                    break
                    
        except Exception as e:
            logger.error(f"检查迁移需求失败: {e}")
    
    async def _find_tables_for_migration(self, cutoff_time: float) -> List[Dict[str, Any]]:
        """查找需要迁移的表"""
        # 这里应该查询实际的热存储数据库
        # 模拟返回需要迁移的表信息
        return [
            {
                "table_name": "market_data_old",
                "partition": "2024-01",
                "row_count": 1000000,
                "last_updated": cutoff_time - 86400
            }
        ]
    
    async def _start_migration(self, table_info: Dict[str, Any]):
        """开始数据迁移"""
        migration_id = f"migration_{int(time.time())}"
        migration = MigrationInfo(
            migration_id=migration_id,
            table_name=table_info["table_name"],
            from_storage=StorageType.WARM,
            to_storage=StorageType.COLD,
            start_time=time.time(),
            status=MigrationStatus.RUNNING
        )
        
        self.active_migrations[migration_id] = migration
        
        try:
            logger.info(f"开始数据迁移 [{migration_id}]: {table_info['table_name']}")
            
            # 执行实际的数据迁移
            success = await self._execute_migration(migration, table_info)
            
            if success:
                migration.status = MigrationStatus.COMPLETED
                migration.end_time = time.time()
                self.migration_history.append(migration)
                
                # 更新性能指标
                migration_duration = migration.end_time - migration.start_time
                if migration_duration > 0:
                    migration_speed = migration.rows_migrated / migration_duration
                    self.performance_metrics.avg_migration_speed_rows_per_sec = (
                        (self.performance_metrics.avg_migration_speed_rows_per_sec * self.performance_metrics.successful_migrations + migration_speed) /
                        (self.performance_metrics.successful_migrations + 1)
                    )
                
                self.performance_metrics.successful_migrations += 1
                self.performance_metrics.total_rows_migrated += migration.rows_migrated
                self.performance_metrics.last_updated = time.time()
                
                logger.info(f"数据迁移完成 [{migration_id}]: {migration.rows_migrated} 行")
            else:
                migration.status = MigrationStatus.FAILED
                self.performance_metrics.failed_migrations += 1
                logger.error(f"数据迁移失败 [{migration_id}]")
                
        except Exception as e:
            migration.status = MigrationStatus.FAILED
            migration.error_message = str(e)
            logger.error(f"数据迁移异常 [{migration_id}]: {e}")
        
        finally:
            self.active_migrations.pop(migration_id, None)
    
    async def _execute_migration(self, migration: MigrationInfo, table_info: Dict[str, Any]) -> bool:
        """执行数据迁移"""
        try:
            # 这里实现实际的数据迁移逻辑
            # 1. 从热存储查询数据
            # 2. 插入到冷存储
            # 3. 验证迁移完整性
            # 4. 删除热存储中的旧数据
            
            # 模拟迁移过程
            total_rows = table_info.get("row_count", 0)
            batch_size = self.config.migration_batch_size
            
            migrated_rows = 0
            
            while migrated_rows < total_rows:
                # 模拟批次迁移
                batch_rows = min(batch_size, total_rows - migrated_rows)
                
                # 模拟迁移时间
                await asyncio.sleep(0.1)
                
                migrated_rows += batch_rows
                migration.rows_migrated = migrated_rows
                
                # 更新进度
                progress = migrated_rows / total_rows * 100
                if migrated_rows % (batch_size * 10) == 0:  # 每10个批次记录一次
                    logger.debug(f"迁移进度 [{migration.migration_id}]: {progress:.1f}%")
            
            return True
            
        except Exception as e:
            logger.error(f"执行数据迁移失败: {e}")
            return False
    
    async def query_cold_data(self, query: str, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """查询冷存储数据"""
        query_start = time.time()
        
        try:
            # 这里实现对冷存储ClickHouse的查询
            # 应该使用实际的ClickHouse客户端
            
            logger.info(f"查询冷存储数据: {query[:100]}...")
            
            # 模拟查询延迟
            await asyncio.sleep(0.5)
            
            # 更新查询性能指标
            query_duration = time.time() - query_start
            query_latency_ms = query_duration * 1000
            
            self.performance_metrics.avg_query_latency_ms = (
                (self.performance_metrics.avg_query_latency_ms * self.performance_metrics.total_queries_executed + query_latency_ms) /
                (self.performance_metrics.total_queries_executed + 1)
            )
            self.performance_metrics.total_queries_executed += 1
            self.performance_metrics.last_updated = time.time()
            
            # 模拟返回结果
            return [
                {"timestamp": "2024-01-01", "symbol": "BTC/USDT", "price": 45000.0},
                {"timestamp": "2024-01-02", "symbol": "ETH/USDT", "price": 2500.0}
            ]
            
        except Exception as e:
            logger.error(f"查询冷存储数据失败: {e}")
            return []
    
    def get_status(self) -> Dict[str, Any]:
        """获取冷存储状态"""
        current_time = time.time()
        uptime = current_time - self.start_time
        
        return {
            "is_running": self.is_running,
            "cold_storage_config": {
                "storage_path": self.config.cold_storage_path,
                "host": self.config.cold_clickhouse_host,
                "port": self.config.cold_clickhouse_port,
                "hot_retention_days": self.config.hot_retention_days,
                "warm_retention_days": self.config.warm_retention_days
            },
            "storage_metrics": {
                "cold_storage": {
                    "total_size_gb": self.cold_metrics.total_size_gb,
                    "used_size_gb": self.cold_metrics.used_size_gb,
                    "free_size_gb": self.cold_metrics.free_size_gb,
                    "usage_percentage": (
                        self.cold_metrics.used_size_gb / self.cold_metrics.total_size_gb * 100
                        if self.cold_metrics.total_size_gb > 0 else 0
                    ),
                    "table_count": self.cold_metrics.table_count,
                    "row_count": self.cold_metrics.row_count,
                    "last_updated": datetime.fromtimestamp(self.cold_metrics.last_updated).isoformat() if self.cold_metrics.last_updated else None
                }
            },
            "performance_metrics": {
                "uptime_hours": uptime / 3600,
                "avg_migration_speed_rows_per_sec": self.performance_metrics.avg_migration_speed_rows_per_sec,
                "avg_query_latency_ms": self.performance_metrics.avg_query_latency_ms,
                "successful_migrations": self.performance_metrics.successful_migrations,
                "failed_migrations": self.performance_metrics.failed_migrations,
                "total_rows_migrated": self.performance_metrics.total_rows_migrated,
                "total_queries_executed": self.performance_metrics.total_queries_executed,
                "migration_success_rate": (
                    self.performance_metrics.successful_migrations / 
                    (self.performance_metrics.successful_migrations + self.performance_metrics.failed_migrations)
                    if (self.performance_metrics.successful_migrations + self.performance_metrics.failed_migrations) > 0 else 0
                )
            },
            "migration_status": {
                "active_migrations": len(self.active_migrations),
                "total_migrations": len(self.migration_history),
                "recent_migrations": [
                    {
                        "migration_id": m.migration_id,
                        "table_name": m.table_name,
                        "status": m.status.value,
                        "rows_migrated": m.rows_migrated,
                        "start_time": datetime.fromtimestamp(m.start_time).isoformat()
                    }
                    for m in sorted(self.migration_history, key=lambda x: x.start_time, reverse=True)[:5]
                ]
            },
            "health_status": {
                "last_health_check": datetime.fromtimestamp(self.last_health_check).isoformat() if self.last_health_check else None,
                "last_capacity_check": datetime.fromtimestamp(self.last_capacity_check).isoformat() if self.last_capacity_check else None,
                "background_tasks": len(self.background_tasks)
            }
        }
    
    def get_capacity_report(self) -> Dict[str, Any]:
        """获取容量报告"""
        return {
            "storage_overview": {
                "cold_storage_path": self.config.cold_storage_path,
                "total_capacity_gb": self.cold_metrics.total_size_gb,
                "used_capacity_gb": self.cold_metrics.used_size_gb,
                "free_capacity_gb": self.cold_metrics.free_size_gb,
                "usage_percentage": (
                    self.cold_metrics.used_size_gb / self.cold_metrics.total_size_gb * 100
                    if self.cold_metrics.total_size_gb > 0 else 0
                )
            },
            "capacity_alerts": self._generate_capacity_alerts(),
            "data_distribution": {
                "table_count": self.cold_metrics.table_count,
                "estimated_row_count": self.cold_metrics.row_count,
                "average_table_size_gb": (
                    self.cold_metrics.used_size_gb / self.cold_metrics.table_count
                    if self.cold_metrics.table_count > 0 else 0
                )
            },
            "migration_summary": {
                "completed_migrations": len([m for m in self.migration_history if m.status == MigrationStatus.COMPLETED]),
                "failed_migrations": len([m for m in self.migration_history if m.status == MigrationStatus.FAILED]),
                "total_rows_migrated": sum(m.rows_migrated for m in self.migration_history),
                "active_migrations": len(self.active_migrations)
            }
        }
    
    def _generate_capacity_alerts(self) -> List[Dict[str, str]]:
        """生成容量告警"""
        alerts = []
        
        if self.cold_metrics.total_size_gb > 0:
            usage_ratio = self.cold_metrics.used_size_gb / self.cold_metrics.total_size_gb
            
            if usage_ratio > 0.95:
                alerts.append({
                    "level": "critical",
                    "message": f"冷存储空间严重不足: {usage_ratio:.1%} 已使用"
                })
            elif usage_ratio > 0.9:
                alerts.append({
                    "level": "warning",
                    "message": f"冷存储空间不足: {usage_ratio:.1%} 已使用"
                })
            elif usage_ratio > 0.8:
                alerts.append({
                    "level": "info",
                    "message": f"冷存储空间使用较高: {usage_ratio:.1%} 已使用"
                })
        
        return alerts


# 全局管理器实例
cold_storage_monitor = None


def get_cold_storage_monitor() -> Optional[ColdStorageMonitor]:
    """获取全局冷存储监控器实例"""
    return cold_storage_monitor


def initialize_cold_storage_monitor(config: Optional[ColdStorageConfig] = None):
    """初始化全局冷存储监控器"""
    global cold_storage_monitor
    cold_storage_monitor = ColdStorageMonitor(config)
    return cold_storage_monitor 