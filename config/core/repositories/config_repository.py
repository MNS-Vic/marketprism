"""
配置仓库抽象接口

定义所有配置仓库的统一接口，支持多种配置源。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import asyncio


class ConfigSourceType(Enum):
    """配置源类型"""
    FILE = "file"
    DATABASE = "database"
    REMOTE = "remote"
    MEMORY = "memory"
    ENVIRONMENT = "environment"


class ConfigFormat(Enum):
    """配置格式"""
    YAML = "yaml"
    JSON = "json"
    TOML = "toml"
    INI = "ini"
    XML = "xml"
    PROPERTIES = "properties"


@dataclass
class ConfigSource:
    """配置源定义"""
    name: str
    source_type: ConfigSourceType
    format: ConfigFormat
    location: str  # 文件路径、数据库连接、远程URL等
    priority: int = 100  # 优先级，数字越小优先级越高
    readonly: bool = False
    encrypted: bool = False
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ConfigEntry:
    """配置条目"""
    key: str
    value: Any
    source: str
    format: ConfigFormat
    version: Optional[str] = None
    timestamp: Optional[datetime] = None
    checksum: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ConfigTransaction:
    """配置事务"""
    transaction_id: str
    operations: List[Dict[str, Any]]
    timestamp: datetime
    user: Optional[str] = None
    description: Optional[str] = None
    
    def __post_init__(self):
        if not self.operations:
            self.operations = []


class ConfigRepository(ABC):
    """配置仓库抽象基类
    
    定义了所有配置仓库必须实现的基本接口。
    支持CRUD操作、事务、缓存和监控。
    """
    
    def __init__(self, source: ConfigSource):
        self.source = source
        self.is_connected = False
        self.cache: Dict[str, ConfigEntry] = {}
        self.cache_enabled = True
        self.cache_ttl = 300  # 5分钟缓存
        
    @abstractmethod
    async def connect(self) -> bool:
        """连接到配置源"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """断开配置源连接"""
        pass
    
    @abstractmethod
    async def get(self, key: str) -> Optional[ConfigEntry]:
        """获取配置项"""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """设置配置项"""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """删除配置项"""
        pass
    
    @abstractmethod
    async def list_keys(self, prefix: Optional[str] = None) -> List[str]:
        """列出所有键"""
        pass
    
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        pass
    
    # 批量操作
    async def get_many(self, keys: List[str]) -> Dict[str, Optional[ConfigEntry]]:
        """批量获取配置项"""
        results = {}
        for key in keys:
            results[key] = await self.get(key)
        return results
    
    async def set_many(self, items: Dict[str, Any]) -> Dict[str, bool]:
        """批量设置配置项"""
        results = {}
        for key, value in items.items():
            results[key] = await self.set(key, value)
        return results
    
    async def delete_many(self, keys: List[str]) -> Dict[str, bool]:
        """批量删除配置项"""
        results = {}
        for key in keys:
            results[key] = await self.delete(key)
        return results
    
    # 事务支持
    async def begin_transaction(self) -> str:
        """开始事务"""
        import uuid
        transaction_id = str(uuid.uuid4())
        return transaction_id
    
    async def commit_transaction(self, transaction_id: str) -> bool:
        """提交事务"""
        # 默认实现，子类可以重写
        return True
    
    async def rollback_transaction(self, transaction_id: str) -> bool:
        """回滚事务"""
        # 默认实现，子类可以重写
        return True
    
    # 搜索和过滤
    async def search(self, pattern: str) -> List[ConfigEntry]:
        """搜索配置项"""
        import fnmatch
        keys = await self.list_keys()
        matching_keys = [key for key in keys if fnmatch.fnmatch(key, pattern)]
        
        results = []
        for key in matching_keys:
            entry = await self.get(key)
            if entry:
                results.append(entry)
        return results
    
    async def filter_by_metadata(self, filters: Dict[str, Any]) -> List[ConfigEntry]:
        """根据元数据过滤配置项"""
        keys = await self.list_keys()
        results = []
        
        for key in keys:
            entry = await self.get(key)
            if entry and self._matches_filters(entry.metadata, filters):
                results.append(entry)
        
        return results
    
    def _matches_filters(self, metadata: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """检查元数据是否匹配过滤条件"""
        for filter_key, filter_value in filters.items():
            if filter_key not in metadata:
                return False
            if metadata[filter_key] != filter_value:
                return False
        return True
    
    # 缓存管理
    def enable_cache(self, ttl: int = 300):
        """启用缓存"""
        self.cache_enabled = True
        self.cache_ttl = ttl
    
    def disable_cache(self):
        """禁用缓存"""
        self.cache_enabled = False
        self.cache.clear()
    
    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()
    
    async def refresh_cache(self):
        """刷新缓存"""
        if not self.cache_enabled:
            return
        
        # 重新加载所有缓存的配置项
        keys_to_refresh = list(self.cache.keys())
        for key in keys_to_refresh:
            fresh_entry = await self._get_from_source(key)
            if fresh_entry:
                self.cache[key] = fresh_entry
            else:
                self.cache.pop(key, None)
    
    @abstractmethod
    async def _get_from_source(self, key: str) -> Optional[ConfigEntry]:
        """从配置源直接获取（绕过缓存）"""
        pass
    
    # 健康检查
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            # 测试连接
            if not self.is_connected:
                await self.connect()
            
            # 测试读取操作
            keys = await self.list_keys()
            key_count = len(keys)
            
            # 缓存统计
            cache_stats = {
                "enabled": self.cache_enabled,
                "size": len(self.cache),
                "ttl": self.cache_ttl
            }
            
            return {
                "healthy": True,
                "source": self.source.name,
                "type": self.source.source_type.value,
                "connected": self.is_connected,
                "key_count": key_count,
                "readonly": self.source.readonly,
                "cache": cache_stats,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                "healthy": False,
                "source": self.source.name,
                "type": self.source.source_type.value,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    # 监控指标
    async def get_metrics(self) -> Dict[str, Any]:
        """获取监控指标"""
        try:
            keys = await self.list_keys()
            
            return {
                "source_name": self.source.name,
                "source_type": self.source.source_type.value,
                "total_keys": len(keys),
                "cache_enabled": self.cache_enabled,
                "cache_size": len(self.cache),
                "cache_hit_rate": self._calculate_cache_hit_rate(),
                "is_connected": self.is_connected,
                "readonly": self.source.readonly,
                "priority": self.source.priority
            }
        except Exception:
            return {
                "source_name": self.source.name,
                "source_type": self.source.source_type.value,
                "error": "Failed to collect metrics"
            }
    
    def _calculate_cache_hit_rate(self) -> float:
        """计算缓存命中率"""
        # 这里是简化的实现，实际应该跟踪命中和未命中次数
        return 0.85  # 示例值
    
    # 配置导入导出
    async def export_all(self, format: ConfigFormat = ConfigFormat.YAML) -> str:
        """导出所有配置"""
        keys = await self.list_keys()
        data = {}
        
        for key in keys:
            entry = await self.get(key)
            if entry:
                data[key] = entry.value
        
        return self._serialize_data(data, format)
    
    async def import_from_data(self, data: str, format: ConfigFormat = ConfigFormat.YAML) -> bool:
        """从数据导入配置"""
        parsed_data = self._deserialize_data(data, format)
        
        for key, value in parsed_data.items():
            await self.set(key, value)
        
        return True
    
    def _serialize_data(self, data: Dict[str, Any], format: ConfigFormat) -> str:
        """序列化数据"""
        if format == ConfigFormat.YAML:
            import yaml
            return yaml.dump(data, default_flow_style=False)
        elif format == ConfigFormat.JSON:
            import json
            return json.dumps(data, indent=2, ensure_ascii=False)
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def _deserialize_data(self, data: str, format: ConfigFormat) -> Dict[str, Any]:
        """反序列化数据"""
        if format == ConfigFormat.YAML:
            import yaml
            return yaml.safe_load(data)
        elif format == ConfigFormat.JSON:
            import json
            return json.loads(data)
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def __str__(self) -> str:
        return f"ConfigRepository(source={self.source.name}, type={self.source.source_type.value})"
    
    def __repr__(self) -> str:
        return (f"ConfigRepository(source='{self.source.name}', "
                f"type={self.source.source_type.value}, "
                f"connected={self.is_connected})")


class ConfigRepositoryError(Exception):
    """配置仓库异常"""
    pass


class ConfigRepositoryConnectionError(ConfigRepositoryError):
    """配置仓库连接异常"""
    pass


class ConfigRepositoryPermissionError(ConfigRepositoryError):
    """配置仓库权限异常"""
    pass


class ConfigRepositoryValidationError(ConfigRepositoryError):
    """配置仓库验证异常"""
    pass