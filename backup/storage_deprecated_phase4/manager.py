"""
Storage统一管理器

提供统一的存储管理接口，支持多writer管理、负载均衡、健康检查等
基于TDD方法论驱动的设计改进
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Optional, Union
from datetime import datetime

from .clickhouse_writer import ClickHouseWriter
from .optimized_clickhouse_writer import OptimizedClickHouseWriter
from .factory import create_writer_from_config, get_writer_instance
from .types import NormalizedTrade, NormalizedOrderBook, NormalizedTicker

# 尝试导入归档管理器（可选）
try:
    from .archiver_storage_manager import StorageManager as ArchiverStorageManager
except ImportError:
    ArchiverStorageManager = None

logger = logging.getLogger(__name__)


class StorageManager:
    """TDD改进：存储统一管理器 - 整合了UnifiedStorageManager的功能"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化存储管理器
        
        Args:
            config: 管理器配置
        """
        self.config = config or {}
        self.writers: Dict[str, Union[ClickHouseWriter, OptimizedClickHouseWriter]] = {}
        self.is_running = False
        self.start_time = None
        
        # 管理器配置
        self.load_balancing_enabled = self.config.get('load_balancing', False)
        self.health_check_interval = self.config.get('health_check_interval', 60)
        self.auto_failover = self.config.get('auto_failover', True)
        
        # 初始化归档管理器（如果可用）
        self.archiver_manager = None
        if ArchiverStorageManager and self.config.get('archiver_config'):
            try:
                self.archiver_manager = ArchiverStorageManager(self.config.get('archiver_config'))
                logger.info("归档管理器已初始化")
            except Exception as e:
                logger.warning(f"归档管理器初始化失败: {e}")
        
        # 统计信息
        self.stats = {
            'total_writes': 0,
            'successful_writes': 0,
            'failed_writes': 0,
            'start_time': None,
            'last_write_time': None
        }
        
        # 健康检查任务
        self.health_check_task = None
        
        logger.info("存储管理器已初始化", config=self.config)
    
    def add_writer(self, name: str, writer: Union[ClickHouseWriter, OptimizedClickHouseWriter]):
        """添加writer实例"""
        self.writers[name] = writer
        logger.info(f"添加writer: {name} ({type(writer).__name__})")
    
    def remove_writer(self, name: str) -> bool:
        """移除writer实例"""
        if name in self.writers:
            del self.writers[name]
            logger.info(f"移除writer: {name}")
            return True
        return False
    
    def get_writer(self, name: str) -> Optional[Union[ClickHouseWriter, OptimizedClickHouseWriter]]:
        """获取指定的writer实例"""
        return self.writers.get(name)
    
    def list_writers(self) -> List[str]:
        """列出所有writer名称"""
        return list(self.writers.keys())
    
    async def start(self):
        """启动管理器"""
        if self.is_running:
            logger.warning("存储管理器已在运行")
            return
        
        self.is_running = True
        self.start_time = time.time()
        self.stats['start_time'] = self.start_time
        
        # 启动所有writer
        for name, writer in self.writers.items():
            try:
                if hasattr(writer, 'start'):
                    await writer.start()
                logger.info(f"启动writer: {name}")
            except Exception as e:
                logger.error(f"启动writer失败: {name} - {e}")
        
        # 启动健康检查
        if self.health_check_interval > 0:
            self.health_check_task = asyncio.create_task(self._health_check_loop())
        
        # 注意：archiver_manager 是同步的，不需要启动
        
        logger.info("存储管理器已启动")
    
    async def stop(self):
        """停止管理器"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # 停止健康检查
        if self.health_check_task:
            self.health_check_task.cancel()
            try:
                await self.health_check_task
            except asyncio.CancelledError:
                pass
        
        # 停止所有writer
        for name, writer in self.writers.items():
            try:
                if hasattr(writer, 'stop'):
                    await writer.stop()
                logger.info(f"停止writer: {name}")
            except Exception as e:
                logger.error(f"停止writer失败: {name} - {e}")
        
        logger.info("存储管理器已停止")
    
    async def write_trade(self, trade: NormalizedTrade, writer_name: Optional[str] = None) -> bool:
        """写入交易数据"""
        return await self._write_data('write_trade', trade, writer_name)
    
    async def write_orderbook(self, orderbook: NormalizedOrderBook, writer_name: Optional[str] = None) -> bool:
        """写入订单簿数据"""
        return await self._write_data('write_orderbook', orderbook, writer_name)
    
    async def write_ticker(self, ticker: NormalizedTicker, writer_name: Optional[str] = None) -> bool:
        """写入行情数据"""
        return await self._write_data('write_ticker', ticker, writer_name)
    
    # UnifiedStorageManager的统一接口方法
    async def write_data(self, data: Any, table: str, writer_name: Optional[str] = None) -> bool:
        """统一数据写入接口"""
        return await self._write_data('write_data', data, writer_name)
    
    def query_data(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """统一数据查询接口"""
        if self.archiver_manager and hasattr(self.archiver_manager, 'query'):
            return self.archiver_manager.query(query, params)
        else:
            logger.warning("归档管理器不可用，无法执行查询")
            return []
    
    def cleanup_expired_data(self, **kwargs) -> Dict[str, int]:
        """清理过期数据"""
        if self.archiver_manager and hasattr(self.archiver_manager, 'cleanup_expired_data'):
            return self.archiver_manager.cleanup_expired_data(**kwargs)
        else:
            logger.warning("归档管理器不可用，无法执行数据清理")
            return {}
    
    async def _write_data(self, method_name: str, data: Any, writer_name: Optional[str] = None) -> bool:
        """内部数据写入方法"""
        self.stats['total_writes'] += 1
        self.stats['last_write_time'] = time.time()
        
        # 选择writer
        target_writers = []
        if writer_name:
            if writer_name in self.writers:
                target_writers = [self.writers[writer_name]]
        else:
            # 使用所有可用的writer
            target_writers = list(self.writers.values())
        
        if not target_writers:
            logger.warning(f"没有可用的writer进行{method_name}操作")
            self.stats['failed_writes'] += 1
            return False
        
        # 负载均衡或广播写入
        success = False
        if self.load_balancing_enabled and len(target_writers) > 1:
            # 负载均衡：选择一个健康的writer
            writer = self._select_healthy_writer(target_writers)
            if writer:
                success = await self._execute_write(writer, method_name, data)
        else:
            # 广播写入：写入所有writer
            results = []
            for writer in target_writers:
                result = await self._execute_write(writer, method_name, data)
                results.append(result)
            success = any(results)  # 至少有一个成功
        
        if success:
            self.stats['successful_writes'] += 1
        else:
            self.stats['failed_writes'] += 1
        
        return success
    
    async def _execute_write(self, writer: Union[ClickHouseWriter, OptimizedClickHouseWriter], method_name: str, data: Any) -> bool:
        """执行写入操作"""
        try:
            if hasattr(writer, method_name):
                method = getattr(writer, method_name)
                await method(data)
                return True
            else:
                logger.warning(f"Writer不支持方法: {method_name}")
                return False
        except Exception as e:
            logger.error(f"写入操作失败: {method_name} - {e}")
            return False
    
    def _select_healthy_writer(self, writers: List[Union[ClickHouseWriter, OptimizedClickHouseWriter]]) -> Optional[Union[ClickHouseWriter, OptimizedClickHouseWriter]]:
        """选择健康的writer（负载均衡）"""
        for writer in writers:
            if self._is_writer_healthy(writer):
                return writer
        
        # 如果没有健康的writer，返回第一个
        return writers[0] if writers else None
    
    def _is_writer_healthy(self, writer: Union[ClickHouseWriter, OptimizedClickHouseWriter]) -> bool:
        """检查writer健康状态"""
        try:
            if hasattr(writer, 'get_health_status'):
                health = writer.get_health_status()
                return health.get('is_healthy', False)
            elif hasattr(writer, 'is_connected'):
                return writer.is_connected()
            else:
                return getattr(writer, 'is_running', False)
        except Exception:
            return False
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while self.is_running:
            try:
                await self._perform_health_check()
                await asyncio.sleep(self.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查失败: {e}")
                await asyncio.sleep(self.health_check_interval)
    
    async def _perform_health_check(self):
        """执行健康检查"""
        unhealthy_writers = []
        
        for name, writer in self.writers.items():
            if not self._is_writer_healthy(writer):
                unhealthy_writers.append(name)
                logger.warning(f"检测到不健康的writer: {name}")
                
                # 自动故障转移
                if self.auto_failover:
                    try:
                        if hasattr(writer, 'restart'):
                            await writer.restart()
                        elif hasattr(writer, 'start'):
                            await writer.start()
                        logger.info(f"尝试重启writer: {name}")
                    except Exception as e:
                        logger.error(f"重启writer失败: {name} - {e}")
        
        if unhealthy_writers:
            logger.warning(f"不健康的writers: {unhealthy_writers}")
    
    def get_status(self) -> Dict[str, Any]:
        """获取管理器状态"""
        uptime = time.time() - self.start_time if self.start_time else 0
        
        writer_status = {}
        for name, writer in self.writers.items():
            writer_status[name] = {
                'type': type(writer).__name__,
                'healthy': self._is_writer_healthy(writer),
                'enabled': getattr(writer, 'enabled', False),
                'running': getattr(writer, 'is_running', False)
            }
        
        return {
            'is_running': self.is_running,
            'uptime_seconds': uptime,
            'writers_count': len(self.writers),
            'writers': writer_status,
            'stats': self.stats.copy(),
            'config': {
                'load_balancing_enabled': self.load_balancing_enabled,
                'health_check_interval': self.health_check_interval,
                'auto_failover': self.auto_failover
            }
        }
    
    def get_comprehensive_status(self) -> Dict[str, Any]:
        """获取综合状态 - UnifiedStorageManager接口兼容"""
        status = {
            "is_running": self.is_running,
            "writer_status": self.get_status()
        }
        
        # 添加归档管理器状态
        if self.archiver_manager:
            try:
                if hasattr(self.archiver_manager, 'get_storage_status'):
                    status["archiver_status"] = self.archiver_manager.get_storage_status()
                else:
                    status["archiver_status"] = {"available": True}
            except Exception as e:
                status["archiver_status"] = {"error": str(e)}
        else:
            status["archiver_status"] = {"available": False, "reason": "not_configured"}
        
        return status
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        uptime = time.time() - self.start_time if self.start_time else 1
        
        metrics = {
            'total_writes': self.stats['total_writes'],
            'successful_writes': self.stats['successful_writes'],
            'failed_writes': self.stats['failed_writes'],
            'success_rate': self.stats['successful_writes'] / max(self.stats['total_writes'], 1),
            'writes_per_second': self.stats['total_writes'] / uptime,
            'uptime_seconds': uptime,
            'writers_count': len(self.writers),
            'healthy_writers_count': sum(1 for writer in self.writers.values() if self._is_writer_healthy(writer))
        }
        
        # 收集writer级别的指标
        writer_metrics = {}
        for name, writer in self.writers.items():
            if hasattr(writer, 'get_performance_metrics'):
                writer_metrics[name] = writer.get_performance_metrics()
            else:
                writer_metrics[name] = {
                    'type': type(writer).__name__,
                    'enabled': getattr(writer, 'enabled', False)
                }
        
        metrics['writers'] = writer_metrics
        return metrics


# TDD改进：单例管理器实例
_storage_manager_instance = None


def get_storage_manager(config: Optional[Dict[str, Any]] = None) -> StorageManager:
    """获取全局存储管理器实例"""
    global _storage_manager_instance
    if _storage_manager_instance is None:
        _storage_manager_instance = StorageManager(config)
    return _storage_manager_instance


def initialize_storage_manager(config: Dict[str, Any]) -> StorageManager:
    """初始化存储管理器"""
    global _storage_manager_instance
    _storage_manager_instance = StorageManager(config)
    
    # 根据配置创建writers
    writers_config = config.get('writers', {})
    for name, writer_config in writers_config.items():
        try:
            writer = create_writer_from_config(writer_config)
            _storage_manager_instance.add_writer(name, writer)
        except Exception as e:
            logger.error(f"创建writer失败: {name} - {e}")
    
    logger.info("存储管理器已初始化")
    return _storage_manager_instance


# TDD改进：别名管理器类
class ClickHouseManager(StorageManager):
    """ClickHouse管理器别名"""
    pass


class DatabaseManager(StorageManager):
    """数据库管理器别名"""
    pass


class WriterManager(StorageManager):
    """写入器管理器别名"""
    pass


# 向后兼容性别名
UnifiedStorageManager = StorageManager