"""
Mock数据归档器

用于测试和开发环境的模拟归档器实现
提供真实的归档器接口，但使用内存存储和模拟操作
"""

import os
import datetime
import logging
from typing import List, Dict, Any, Optional, Tuple
from .archiver import DataArchiver

logger = logging.getLogger(__name__)

class MockDataArchiver(DataArchiver):
    """
    模拟数据归档器类
    继承自真实归档器，但使用内存存储和模拟操作
    """
    
    def __init__(self, config_path=None):
        """
        初始化模拟数据归档器
        
        参数:
            config_path: 配置路径（可选）
        """
        # 使用模拟配置初始化
        mock_config = self._get_mock_config()
        super().__init__(mock_config)
        
        # 模拟存储
        self.mock_hot_storage = {}
        self.mock_cold_storage = {}
        self.mock_archived_tables = []
        self.mock_stats = {
            'archived_records': 0,
            'archived_size': 0,
            'last_archive_time': None
        }
        
        logger.info("模拟数据归档器已初始化")
    
    def _get_mock_config(self) -> Dict[str, Any]:
        """获取模拟配置"""
        return {
            'storage': {
                'hot_storage': {
                    'host': 'mock-hot-storage',
                    'port': 9000,
                    'retention_days': 7
                },
                'cold_storage': {
                    'host': 'mock-cold-storage', 
                    'port': 9001,
                    'enabled': True
                },
                'archiver': {
                    'batch_size': 1000,
                    'schedule': '0 2 * * *'
                }
            }
        }
    
    def _create_client(self, config: Dict[str, Any]):
        """创建模拟客户端"""
        class MockClient:
            def __init__(self, config):
                self.config = config
                self.connected = True
                
            def execute(self, query, *args, **kwargs):
                # 模拟查询执行
                return []
                
            def ping(self):
                return True
                
        return MockClient(config)
    
    def archive_data(self, data_path: str = None, table_name: str = None) -> Dict[str, Any]:
        """模拟归档数据操作"""
        # 模拟归档过程
        archived_records = 5000
        archived_size = 2.5  # GB
        
        if table_name:
            self.mock_archived_tables.append(table_name)
        
        self.mock_stats['archived_records'] += archived_records
        self.mock_stats['archived_size'] += archived_size
        self.mock_stats['last_archive_time'] = datetime.datetime.now().isoformat()
        
        result = {
            'status': 'success',
            'data_path': data_path or '/mock/data',
            'table_name': table_name or 'mock_table',
            'archived_records': archived_records,
            'archived_size': f'{archived_size}GB',
            'message': '模拟数据归档操作完成'
        }
        
        logger.info(f"模拟归档完成: {result}")
        return result
    
    def archive_tables(self, tables: Optional[List[str]] = None, days: Optional[int] = None,
                      force: bool = False, dry_run: bool = False) -> Dict[str, int]:
        """模拟批量归档表"""
        if tables is None:
            tables = ['trades', 'orderbook', 'tickers']
        
        results = {}
        for table in tables:
            if dry_run:
                results[table] = 0  # 干运行模式
            else:
                # 模拟归档记录数
                archived_count = len(table) * 1000  # 基于表名长度的模拟数据
                results[table] = archived_count
                self.mock_archived_tables.append(table)
        
        logger.info(f"模拟批量归档完成: {results}")
        return results
    
    def cleanup_old_data(self, retention_days: int = None) -> Dict[str, Any]:
        """模拟清理旧数据"""
        if retention_days is None:
            retention_days = self.retention_days
            
        # 模拟清理操作
        cleaned_records = retention_days * 100
        
        result = {
            'status': 'success',
            'retention_days': retention_days,
            'cleaned_records': cleaned_records,
            'message': f'模拟清理{retention_days}天前的旧数据，清理{cleaned_records}条记录'
        }
        
        logger.info(f"模拟清理完成: {result}")
        return result
    
    def get_archive_stats(self) -> Dict[str, Any]:
        """获取模拟归档统计"""
        return {
            'hot_storage_size': '5.2GB',
            'cold_storage_size': '125.8GB', 
            'archived_tables': len(self.mock_archived_tables),
            'total_records': self.mock_stats['archived_records'],
            'last_archive_time': self.mock_stats['last_archive_time'] or 'Never',
            'mock_mode': True,
            'archived_table_list': self.mock_archived_tables
        }
    
    def get_status(self) -> Dict[str, Any]:
        """获取模拟状态"""
        return {
            'archiver_type': 'MockDataArchiver',
            'hot_storage': {
                'host': 'mock-hot-storage',
                'status': 'connected',
                'tables': len(self.mock_hot_storage)
            },
            'cold_storage': {
                'host': 'mock-cold-storage', 
                'status': 'connected',
                'tables': len(self.mock_cold_storage)
            },
            'statistics': self.get_archive_stats(),
            'mock_mode': True
        }
    
    def restore_data(self, table: str, date_from: str, date_to: str, dry_run: bool = False) -> int:
        """模拟数据恢复"""
        # 模拟恢复操作
        if dry_run:
            restored_count = 0
        else:
            restored_count = len(table) * 500  # 基于表名的模拟数据
        
        logger.info(f"模拟恢复表 {table} 从 {date_from} 到 {date_to}: {restored_count} 条记录")
        return restored_count
    
    def verify_archive(self, table: str) -> bool:
        """模拟归档验证"""
        # 简单验证逻辑
        is_valid = table in self.mock_archived_tables
        logger.info(f"模拟验证表 {table}: {'通过' if is_valid else '失败'}")
        return is_valid
    
    def reset_mock_data(self):
        """重置模拟数据"""
        self.mock_hot_storage.clear()
        self.mock_cold_storage.clear()
        self.mock_archived_tables.clear()
        self.mock_stats = {
            'archived_records': 0,
            'archived_size': 0,
            'last_archive_time': None
        }
        logger.info("模拟数据已重置")
    
    def add_mock_table(self, table_name: str, record_count: int = 1000):
        """添加模拟表数据"""
        self.mock_hot_storage[table_name] = {
            'records': record_count,
            'size': f'{record_count * 0.001}GB',
            'created': datetime.datetime.now().isoformat()
        }
        logger.info(f"添加模拟表: {table_name} ({record_count} 条记录)")
    
    def get_mock_tables(self) -> Dict[str, Any]:
        """获取所有模拟表"""
        return {
            'hot_storage': self.mock_hot_storage,
            'cold_storage': self.mock_cold_storage,
            'archived_tables': self.mock_archived_tables
        }