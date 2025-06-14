"""
Storage工厂模式

提供统一的writer创建接口，支持不同类型的存储写入器
基于TDD方法论驱动的设计改进
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional, Union
import logging

from .unified_clickhouse_writer import UnifiedClickHouseWriter

logger = logging.getLogger(__name__)

# 向后兼容别名
ClickHouseWriter = UnifiedClickHouseWriter
OptimizedClickHouseWriter = UnifiedClickHouseWriter

# 可用的writer类型
WRITER_TYPES = {
    'clickhouse': UnifiedClickHouseWriter,
    'optimized_clickhouse': UnifiedClickHouseWriter,
    'clickhouse_writer': UnifiedClickHouseWriter,  # 别名
    'optimized': UnifiedClickHouseWriter,  # 别名
    'unified': UnifiedClickHouseWriter,  # 新的统一类型
}


def create_clickhouse_writer(config: Optional[Dict[str, Any]] = None) -> UnifiedClickHouseWriter:
    """TDD改进：创建ClickHouse写入器
    
    Args:
        config: 配置字典
        
    Returns:
        UnifiedClickHouseWriter实例
    """
    logger.info("创建ClickHouse写入器")
    return UnifiedClickHouseWriter(config)


def create_optimized_writer(config: Optional[Dict[str, Any]] = None) -> UnifiedClickHouseWriter:
    """TDD改进：创建优化版ClickHouse写入器
    
    Args:
        config: 配置字典
        
    Returns:
        UnifiedClickHouseWriter实例
    """
    logger.info("创建优化版ClickHouse写入器")
    return UnifiedClickHouseWriter(config)


def get_writer_instance(writer_type: str, config: Optional[Dict[str, Any]] = None) -> UnifiedClickHouseWriter:
    """TDD改进：根据类型获取writer实例
    
    Args:
        writer_type: writer类型 ('clickhouse', 'optimized_clickhouse', 'unified')
        config: 配置字典
        
    Returns:
        UnifiedClickHouseWriter实例
        
    Raises:
        ValueError: 不支持的writer类型
    """
    if writer_type not in WRITER_TYPES:
        available_types = list(WRITER_TYPES.keys())
        raise ValueError(f"不支持的writer类型: {writer_type}. 可用类型: {available_types}")
    
    writer_class = WRITER_TYPES[writer_type]
    logger.info(f"创建writer实例: {writer_type}")
    
    return writer_class(config)


def create_writer_from_config(config: Dict[str, Any]) -> UnifiedClickHouseWriter:
    """TDD改进：从配置创建writer
    
    根据配置中的writer_type字段选择合适的writer类型
    
    Args:
        config: 配置字典，包含writer_type字段
        
    Returns:
        UnifiedClickHouseWriter实例
    """
    writer_type = config.get('writer_type', 'clickhouse')
    optimization_enabled = config.get('optimization', {}).get('enabled', False)
    
    # 如果启用了优化特性，自动选择优化版writer（现在都是统一的）
    if optimization_enabled and writer_type == 'clickhouse':
        writer_type = 'unified'
        logger.info("检测到优化配置，使用统一写入器")
    
    return get_writer_instance(writer_type, config)


def create_writer_pool(pool_size: int = 5, writer_type: str = 'clickhouse', config: Optional[Dict[str, Any]] = None) -> list:
    """TDD改进：创建writer池
    
    Args:
        pool_size: 池大小
        writer_type: writer类型
        config: 配置字典
        
    Returns:
        writer实例列表
    """
    pool = []
    
    for i in range(pool_size):
        writer = get_writer_instance(writer_type, config)
        pool.append(writer)
        
    logger.info(f"创建writer池: {pool_size}个{writer_type}实例")
    return pool


def get_available_writer_types() -> list:
    """获取可用的writer类型列表"""
    return list(WRITER_TYPES.keys())


def is_writer_type_supported(writer_type: str) -> bool:
    """检查writer类型是否支持"""
    return writer_type in WRITER_TYPES


# 向后兼容的工厂函数
def create_storage_writer(config: Optional[Dict[str, Any]] = None) -> UnifiedClickHouseWriter:
    """向后兼容：创建存储写入器"""
    return create_clickhouse_writer(config)


def create_default_writer(config: Optional[Dict[str, Any]] = None) -> UnifiedClickHouseWriter:
    """创建默认writer"""
    return create_clickhouse_writer(config) 