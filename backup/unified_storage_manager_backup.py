"""
统一存储管理器

整合了ClickHouse管理、数据归档、迁移等所有存储相关功能
提供统一的存储管理接口
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from .manager import StorageManager
from .clickhouse_writer import ClickHouseWriter
from .optimized_clickhouse_writer import OptimizedClickHouseWriter
from .archiver_storage_manager import StorageManager as ArchiverStorageManager

logger = logging.getLogger(__name__)


class UnifiedStorageManager:
    """统一存储管理器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        
        # 初始化子管理器
        self.writer_manager = StorageManager(self.config.get('writer_config'))
        self.archiver_manager = ArchiverStorageManager(self.config.get('archiver_config'))
        
        self.is_running = False
        logger.info("统一存储管理器已初始化")
    
    async def start(self):
        """启动存储管理器"""
        if self.is_running:
            return
        
        await self.writer_manager.start()
        # archiver_manager 是同步的，不需要启动
        
        self.is_running = True
        logger.info("统一存储管理器已启动")
    
    async def stop(self):
        """停止存储管理器"""
        self.is_running = False
        
        await self.writer_manager.stop()
        
        logger.info("统一存储管理器已停止")
    
    async def write_data(self, data: Any, table: str, writer_name: Optional[str] = None) -> bool:
        """统一数据写入接口"""
        return await self.writer_manager._write_data('write_data', data, writer_name)
    
    def query_data(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """统一数据查询接口"""
        return self.archiver_manager.query(query, params)
    
    def cleanup_expired_data(self, **kwargs) -> Dict[str, int]:
        """清理过期数据"""
        return self.archiver_manager.cleanup_expired_data(**kwargs)
    
    def get_comprehensive_status(self) -> Dict[str, Any]:
        """获取综合状态"""
        return {
            "is_running": self.is_running,
            "writer_status": self.writer_manager.get_status(),
            "archiver_status": self.archiver_manager.get_storage_status()
        }
