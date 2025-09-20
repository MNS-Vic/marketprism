"""
MarketPrism 统一存储配置管理器
支持热/冷数据存储模式的动态配置
"""

import os
import yaml
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional
import structlog

logger = structlog.get_logger(__name__)

class StorageMode(Enum):
    """存储模式枚举"""
    HOT = "hot"      # 热数据存储模式
    COLD = "cold"    # 冷数据存储模式

@dataclass
class ClickHouseConfig:
    """ClickHouse配置"""
    host: str
    port: int
    user: str
    password: str
    database: str
    
@dataclass
class TTLConfig:
    """TTL配置"""
    hot_retention_days: int
    cold_retention_days: int
    cleanup_interval_hours: int
    migration_batch_size: int

@dataclass
class CompressionConfig:
    """压缩配置"""
    hot_codec: str
    cold_codec: str
    hot_level: int
    cold_level: int

@dataclass
class PartitionConfig:
    """分区配置"""
    hot_partition_by: str
    cold_partition_by: str

@dataclass
class MigrationConfig:
    """数据迁移配置"""
    enabled: bool
    schedule_cron: str
    cold_storage_endpoint: str
    batch_size: int
    parallel_workers: int
    verification_enabled: bool

class StorageConfigManager:
    """统一存储配置管理器"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "config/storage_unified.yaml"
        self.storage_mode = self._detect_storage_mode()
        self.config = self._load_config()
        
        logger.info(
            "存储配置管理器初始化完成",
            mode=self.storage_mode.value,
            config_path=self.config_path
        )
    
    def _detect_storage_mode(self) -> StorageMode:
        """检测存储模式"""
        mode = os.getenv('STORAGE_MODE', 'hot').lower()
        
        if mode == 'cold':
            return StorageMode.COLD
        else:
            return StorageMode.HOT
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            
            # 环境变量覆盖
            config = self._apply_env_overrides(config)
            
            logger.info("存储配置加载成功", config_keys=list(config.keys()))
            return config
            
        except FileNotFoundError:
            logger.warning(f"配置文件不存在: {self.config_path}，使用默认配置")
            return self._get_default_config()
        except Exception as e:
            logger.error(f"配置文件加载失败: {e}，使用默认配置")
            return self._get_default_config()
    
    def _apply_env_overrides(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """应用环境变量覆盖"""
        # ClickHouse配置覆盖
        clickhouse_config = config.setdefault('clickhouse', {})
        
        if self.storage_mode == StorageMode.HOT:
            clickhouse_config.update({
                'host': os.getenv('CLICKHOUSE_HOST', clickhouse_config.get('host', 'localhost')),
                'port': int(os.getenv('CLICKHOUSE_PORT', clickhouse_config.get('port', 8123))),
                'user': os.getenv('CLICKHOUSE_USER', clickhouse_config.get('user', 'default')),
                'password': os.getenv('CLICKHOUSE_PASSWORD', clickhouse_config.get('password', '')),
                'database': os.getenv('CLICKHOUSE_DATABASE', clickhouse_config.get('database', 'marketprism'))
            })
        else:  # COLD mode
            clickhouse_config.update({
                'host': os.getenv('COLD_CLICKHOUSE_HOST', clickhouse_config.get('cold_host', 'localhost')),
                'port': int(os.getenv('COLD_CLICKHOUSE_PORT', clickhouse_config.get('cold_port', 8123))),
                'user': os.getenv('COLD_CLICKHOUSE_USER', clickhouse_config.get('cold_user', 'default')),
                'password': os.getenv('COLD_CLICKHOUSE_PASSWORD', clickhouse_config.get('cold_password', '')),
                'database': os.getenv('COLD_CLICKHOUSE_DATABASE', clickhouse_config.get('cold_database', 'marketprism_cold'))
            })
        
        return config
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'clickhouse': {
                'host': 'localhost',
                'port': 8123,
                'user': 'default',
                'password': '',
                'database': 'marketprism_hot' if self.storage_mode == StorageMode.HOT else 'marketprism_cold'
            },
            'ttl': {
                'hot_retention_days': 3,
                'cold_retention_days': 365,
                'cleanup_interval_hours': 6,
                'migration_batch_size': 10000
            },
            'compression': {
                'hot_codec': 'LZ4',
                'cold_codec': 'ZSTD',
                'hot_level': 1,
                'cold_level': 3
            },
            'partition': {
                'hot_partition_by': 'toYYYYMMDD(timestamp), exchange',
                'cold_partition_by': 'toYYYYMM(timestamp), exchange'
            },
            'migration': {
                'enabled': self.storage_mode == StorageMode.HOT,
                'schedule_cron': '0 2 * * *',  # 每天凌晨2点
                'cold_storage_endpoint': 'http://nas-server:8123',
                'batch_size': 10000,
                'parallel_workers': 4,
                'verification_enabled': True
            }
        }
    
    def get_clickhouse_config(self) -> ClickHouseConfig:
        """获取ClickHouse配置"""
        ch_config = self.config['clickhouse']
        return ClickHouseConfig(
            host=ch_config['host'],
            port=ch_config['port'],
            user=ch_config['user'],
            password=ch_config['password'],
            database=ch_config['database']
        )
    
    def get_ttl_config(self) -> TTLConfig:
        """获取TTL配置"""
        ttl_config = self.config['ttl']
        return TTLConfig(
            hot_retention_days=ttl_config['hot_retention_days'],
            cold_retention_days=ttl_config['cold_retention_days'],
            cleanup_interval_hours=ttl_config['cleanup_interval_hours'],
            migration_batch_size=ttl_config['migration_batch_size']
        )
    
    def get_compression_config(self) -> CompressionConfig:
        """获取压缩配置"""
        comp_config = self.config['compression']
        return CompressionConfig(
            hot_codec=comp_config['hot_codec'],
            cold_codec=comp_config['cold_codec'],
            hot_level=comp_config['hot_level'],
            cold_level=comp_config['cold_level']
        )
    
    def get_partition_config(self) -> PartitionConfig:
        """获取分区配置"""
        part_config = self.config['partition']
        return PartitionConfig(
            hot_partition_by=part_config['hot_partition_by'],
            cold_partition_by=part_config['cold_partition_by']
        )
    
    def get_migration_config(self) -> MigrationConfig:
        """获取迁移配置"""
        mig_config = self.config['migration']
        return MigrationConfig(
            enabled=mig_config['enabled'],
            schedule_cron=mig_config['schedule_cron'],
            cold_storage_endpoint=mig_config['cold_storage_endpoint'],
            batch_size=mig_config['batch_size'],
            parallel_workers=mig_config['parallel_workers'],
            verification_enabled=mig_config['verification_enabled']
        )
    
    def is_hot_storage(self) -> bool:
        """是否为热存储模式"""
        return self.storage_mode == StorageMode.HOT
    
    def is_cold_storage(self) -> bool:
        """是否为冷存储模式"""
        return self.storage_mode == StorageMode.COLD
    
    def get_table_prefix(self) -> str:
        """获取表前缀"""
        return "hot_" if self.is_hot_storage() else "cold_"
    
    def get_current_codec(self) -> str:
        """获取当前模式的压缩编码"""
        comp_config = self.get_compression_config()
        return comp_config.hot_codec if self.is_hot_storage() else comp_config.cold_codec
    
    def get_current_partition_by(self) -> str:
        """获取当前模式的分区策略"""
        part_config = self.get_partition_config()
        return part_config.hot_partition_by if self.is_hot_storage() else part_config.cold_partition_by
    
    def get_current_ttl_days(self) -> int:
        """获取当前模式的TTL天数"""
        ttl_config = self.get_ttl_config()
        return ttl_config.hot_retention_days if self.is_hot_storage() else ttl_config.cold_retention_days
