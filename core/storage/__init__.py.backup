"""
MarketPrism Collector 存储模块

提供企业级存储功能，包括：
- ClickHouse直接写入
- 优化版ClickHouse写入器
- 工厂模式支持
- 统一存储管理器
- 连接池和事务支持

基于TDD方法论驱动的设计改进
"""

# 核心writer类
from .clickhouse_writer import ClickHouseWriter
from .optimized_clickhouse_writer import OptimizedClickHouseWriter

# 工厂模式
from .factory import (
    create_clickhouse_writer,
    create_optimized_writer,
    get_writer_instance,
    create_writer_from_config,
    create_writer_pool,
    get_available_writer_types,
    is_writer_type_supported,
    create_storage_writer,  # 向后兼容
    create_default_writer
)

# 统一管理器
from .manager import (
    StorageManager,
    ClickHouseManager,
    DatabaseManager,
    WriterManager,
    get_storage_manager,
    initialize_storage_manager
)

__all__ = [
    # 核心writer类
    'ClickHouseWriter',
    'OptimizedClickHouseWriter',
    
    # 工厂函数
    'create_clickhouse_writer',
    'create_optimized_writer',
    'get_writer_instance',
    'create_writer_from_config',
    'create_writer_pool',
    'get_available_writer_types',
    'is_writer_type_supported',
    'create_storage_writer',
    'create_default_writer',
    
    # 管理器类
    'StorageManager',
    'ClickHouseManager',
    'DatabaseManager', 
    'WriterManager',
    'get_storage_manager',
    'initialize_storage_manager'
] 