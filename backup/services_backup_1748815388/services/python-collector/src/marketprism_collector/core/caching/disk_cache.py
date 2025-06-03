"""
磁盘缓存实现

提供持久化的磁盘缓存，支持文件系统存储、索引管理和压缩。
"""

import os
import pickle
import json
import gzip
import time
import hashlib
import asyncio
import aiofiles
from typing import Any, Optional, Dict, List, Union
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
import logging

try:
    import msgpack
    MSGPACK_AVAILABLE = True
except ImportError:
    msgpack = None
    MSGPACK_AVAILABLE = False

from .cache_interface import (
    Cache, CacheKey, CacheValue, CacheConfig, CacheLevel, 
    SerializationFormat, CacheStatistics
)
from .cache_strategies import CacheStrategy, create_strategy


@dataclass
class DiskCacheConfig(CacheConfig):
    """磁盘缓存配置"""
    level: CacheLevel = CacheLevel.DISK
    
    # 存储路径配置
    cache_dir: str = "./cache"
    create_subdirs: bool = True
    dir_levels: int = 2  # 目录层级深度
    files_per_dir: int = 1000  # 每个目录最大文件数
    
    # 文件配置
    file_extension: str = ".cache"
    temp_extension: str = ".tmp"
    
    # 压缩配置
    enable_compression: bool = True
    compression_threshold: int = 1024  # 超过1KB启用压缩
    
    # 索引配置
    enable_index: bool = True
    index_file: str = "cache_index.json"
    index_sync_interval: int = 300  # 索引同步间隔（秒）
    
    # 清理配置
    auto_cleanup_interval: int = 3600  # 自动清理间隔（秒）
    max_disk_usage_mb: Optional[int] = None
    
    # I/O配置
    async_io: bool = True
    io_chunk_size: int = 8192  # I/O块大小


class DiskIndex:
    """磁盘缓存索引"""
    
    def __init__(self, index_file: str):
        self.index_file = index_file
        self.index: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._dirty = False
        self._logger = logging.getLogger(__name__)
    
    async def load(self):
        """加载索引"""
        async with self._lock:
            if os.path.exists(self.index_file):
                try:
                    async with aiofiles.open(self.index_file, 'r') as f:
                        content = await f.read()
                        self.index = json.loads(content)
                    self._logger.info(f"索引加载成功: {len(self.index)} 项")
                except Exception as e:
                    self._logger.error(f"索引加载失败: {e}")
                    self.index = {}
            else:
                self.index = {}
    
    async def save(self):
        """保存索引"""
        if not self._dirty:
            return
        
        async with self._lock:
            try:
                # 先写入临时文件
                temp_file = f"{self.index_file}.tmp"
                async with aiofiles.open(temp_file, 'w') as f:
                    await f.write(json.dumps(self.index, indent=2))
                
                # 原子性重命名
                os.rename(temp_file, self.index_file)
                self._dirty = False
                self._logger.debug(f"索引保存成功: {len(self.index)} 项")
                
            except Exception as e:
                self._logger.error(f"索引保存失败: {e}")
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """获取索引项"""
        async with self._lock:
            return self.index.get(key)
    
    async def set(self, key: str, entry: Dict[str, Any]):
        """设置索引项"""
        async with self._lock:
            self.index[key] = entry
            self._dirty = True
    
    async def delete(self, key: str) -> bool:
        """删除索引项"""
        async with self._lock:
            if key in self.index:
                del self.index[key]
                self._dirty = True
                return True
            return False
    
    async def keys(self) -> List[str]:
        """获取所有键"""
        async with self._lock:
            return list(self.index.keys())
    
    async def cleanup_expired(self) -> int:
        """清理过期项"""
        now = datetime.now(timezone.utc)
        expired_keys = []
        
        async with self._lock:
            for key, entry in self.index.items():
                expires_at = entry.get('expires_at')
                if expires_at:
                    expire_time = datetime.fromisoformat(expires_at)
                    if now >= expire_time:
                        expired_keys.append(key)
            
            for key in expired_keys:
                del self.index[key]
            
            if expired_keys:
                self._dirty = True
        
        return len(expired_keys)


class DiskCacheFile:
    """磁盘缓存文件管理"""
    
    def __init__(self, config: DiskCacheConfig):
        self.config = config
        self.cache_dir = Path(config.cache_dir)
        self._logger = logging.getLogger(__name__)
    
    def _get_file_path(self, key: CacheKey) -> Path:
        """获取文件路径"""
        # 使用键的哈希值创建分布式目录结构
        key_hash = hashlib.md5(str(key).encode()).hexdigest()
        
        # 创建多级目录
        subdirs = []
        for i in range(self.config.dir_levels):
            start = i * 2
            subdirs.append(key_hash[start:start+2])
        
        subdir_path = self.cache_dir / Path(*subdirs)
        filename = f"{key_hash}{self.config.file_extension}"
        
        return subdir_path / filename
    
    async def _ensure_dir(self, file_path: Path):
        """确保目录存在"""
        if self.config.create_subdirs:
            file_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _serialize_data(self, data: Any) -> bytes:
        """序列化数据"""
        if self.config.serialization_format == SerializationFormat.PICKLE:
            return pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
        elif self.config.serialization_format == SerializationFormat.JSON:
            return json.dumps(data, ensure_ascii=False).encode('utf-8')
        elif self.config.serialization_format == SerializationFormat.MSGPACK:
            if not MSGPACK_AVAILABLE:
                raise ValueError("msgpack not available")
            return msgpack.packb(data)
        else:
            raise ValueError(f"不支持的序列化格式: {self.config.serialization_format}")
    
    def _deserialize_data(self, data: bytes) -> Any:
        """反序列化数据"""
        if self.config.serialization_format == SerializationFormat.PICKLE:
            return pickle.loads(data)
        elif self.config.serialization_format == SerializationFormat.JSON:
            return json.loads(data.decode('utf-8'))
        elif self.config.serialization_format == SerializationFormat.MSGPACK:
            if not MSGPACK_AVAILABLE:
                raise ValueError("msgpack not available")
            return msgpack.unpackb(data, raw=False)
        else:
            raise ValueError(f"不支持的序列化格式: {self.config.serialization_format}")
    
    async def write_file(self, key: CacheKey, value: CacheValue) -> str:
        """写入文件"""
        file_path = self._get_file_path(key)
        await self._ensure_dir(file_path)
        
        # 序列化数据
        data_bytes = self._serialize_data(value.data)
        
        # 压缩（如果启用且数据超过阈值）
        compressed = False
        if (self.config.enable_compression and 
            len(data_bytes) > self.config.compression_threshold):
            data_bytes = gzip.compress(data_bytes)
            compressed = True
        
        # 构建文件内容
        file_content = {
            'data': data_bytes,
            'compressed': compressed,
            'created_at': value.created_at.isoformat(),
            'expires_at': value.expires_at.isoformat() if value.expires_at else None,
            'access_count': value.access_count,
            'metadata': value.metadata
        }
        
        # 写入文件
        temp_path = file_path.with_suffix(self.config.temp_extension)
        
        if self.config.async_io:
            # 异步写入
            serialized_content = pickle.dumps(file_content)
            async with aiofiles.open(temp_path, 'wb') as f:
                await f.write(serialized_content)
        else:
            # 同步写入
            with open(temp_path, 'wb') as f:
                pickle.dump(file_content, f)
        
        # 原子性重命名
        os.rename(temp_path, file_path)
        
        return str(file_path)
    
    async def read_file(self, key: CacheKey) -> Optional[CacheValue]:
        """读取文件"""
        file_path = self._get_file_path(key)
        
        if not file_path.exists():
            return None
        
        try:
            if self.config.async_io:
                # 异步读取
                async with aiofiles.open(file_path, 'rb') as f:
                    content = await f.read()
                file_content = pickle.loads(content)
            else:
                # 同步读取
                with open(file_path, 'rb') as f:
                    file_content = pickle.load(f)
            
            # 解压缩（如果需要）
            data_bytes = file_content['data']
            if file_content.get('compressed', False):
                data_bytes = gzip.decompress(data_bytes)
            
            # 反序列化数据
            data = self._deserialize_data(data_bytes)
            
            # 构建CacheValue
            value = CacheValue(
                data=data,
                created_at=datetime.fromisoformat(file_content['created_at']),
                expires_at=datetime.fromisoformat(file_content['expires_at']) if file_content['expires_at'] else None,
                access_count=file_content.get('access_count', 0),
                metadata=file_content.get('metadata', {})
            )
            
            return value
            
        except Exception as e:
            self._logger.error(f"读取文件失败 {file_path}: {e}")
            return None
    
    async def delete_file(self, key: CacheKey) -> bool:
        """删除文件"""
        file_path = self._get_file_path(key)
        
        if file_path.exists():
            try:
                os.remove(file_path)
                return True
            except Exception as e:
                self._logger.error(f"删除文件失败 {file_path}: {e}")
        
        return False
    
    async def get_disk_usage(self) -> int:
        """获取磁盘使用量（字节）"""
        total_size = 0
        
        for root, dirs, files in os.walk(self.cache_dir):
            for file in files:
                if file.endswith(self.config.file_extension):
                    file_path = Path(root) / file
                    try:
                        total_size += file_path.stat().st_size
                    except Exception:
                        pass
        
        return total_size


class DiskCache(Cache):
    """磁盘缓存
    
    特性：
    - 持久化存储
    - 文件系统索引
    - 数据压缩
    - 异步I/O
    - 自动清理
    """
    
    def __init__(self, config: DiskCacheConfig):
        super().__init__(config)
        self.config: DiskCacheConfig = config
        
        # 文件管理
        self.file_manager = DiskCacheFile(config)
        
        # 索引管理
        if config.enable_index:
            index_path = Path(config.cache_dir) / config.index_file
            self.index = DiskIndex(str(index_path))
        else:
            self.index = None
        
        # 策略
        self.strategy = create_strategy(
            config.eviction_policy,
            config.max_size,
            default_ttl=config.default_ttl
        )
        
        # 清理任务
        self._cleanup_task = None
        self._index_sync_task = None
        
        self._logger = logging.getLogger(__name__)
    
    async def _ensure_initialized(self):
        """确保初始化"""
        if self.index and not hasattr(self.index, '_loaded'):
            await self.index.load()
            self.index._loaded = True
        
        # 确保缓存目录存在
        Path(self.config.cache_dir).mkdir(parents=True, exist_ok=True)
    
    async def get(self, key: CacheKey) -> Optional[CacheValue]:
        """获取缓存值"""
        start_time = time.time()
        
        try:
            await self._ensure_initialized()
            
            # 检查索引
            if self.index:
                index_entry = await self.index.get(str(key))
                if not index_entry:
                    self.stats.misses += 1
                    return None
                
                # 检查过期
                expires_at = index_entry.get('expires_at')
                if expires_at:
                    expire_time = datetime.fromisoformat(expires_at)
                    if datetime.now(timezone.utc) >= expire_time:
                        await self.delete(key)
                        self.stats.misses += 1
                        return None
            
            # 读取文件
            value = await self.file_manager.read_file(key)
            
            if value is None:
                self.stats.misses += 1
                return None
            
            # 检查过期
            if value.is_expired():
                await self.delete(key)
                self.stats.misses += 1
                return None
            
            # 更新访问统计
            value.touch()
            self.strategy.on_access(key, value)
            self.stats.hits += 1
            
            # 更新索引
            if self.index:
                await self.index.set(str(key), {
                    'file_path': str(self.file_manager._get_file_path(key)),
                    'created_at': value.created_at.isoformat(),
                    'expires_at': value.expires_at.isoformat() if value.expires_at else None,
                    'access_count': value.access_count,
                    'size_bytes': value.size_bytes
                })
            
            return value
            
        except Exception as e:
            self.stats.errors += 1
            self._logger.error(f"Disk get失败: {e}")
            raise
        finally:
            self.stats.total_get_time += time.time() - start_time
    
    async def set(self, key: CacheKey, value: CacheValue, ttl: Optional[timedelta] = None) -> bool:
        """设置缓存值"""
        start_time = time.time()
        
        try:
            await self._ensure_initialized()
            
            # 设置TTL
            if ttl is not None:
                value.expires_at = datetime.now(timezone.utc) + ttl
            elif self.config.default_ttl and value.expires_at is None:
                value.expires_at = datetime.now(timezone.utc) + self.config.default_ttl
            
            # 检查磁盘空间
            if self.config.max_disk_usage_mb:
                current_usage = await self.file_manager.get_disk_usage()
                max_usage = self.config.max_disk_usage_mb * 1024 * 1024
                
                if current_usage > max_usage:
                    await self._cleanup_space()
            
            # 写入文件
            file_path = await self.file_manager.write_file(key, value)
            
            # 更新索引
            if self.index:
                await self.index.set(str(key), {
                    'file_path': file_path,
                    'created_at': value.created_at.isoformat(),
                    'expires_at': value.expires_at.isoformat() if value.expires_at else None,
                    'access_count': value.access_count,
                    'size_bytes': value.size_bytes
                })
            
            # 更新策略
            self.strategy.on_insert(key, value)
            self.stats.sets += 1
            
            return True
            
        except Exception as e:
            self.stats.errors += 1
            self._logger.error(f"Disk set失败: {e}")
            raise
        finally:
            self.stats.total_set_time += time.time() - start_time
    
    async def delete(self, key: CacheKey) -> bool:
        """删除缓存值"""
        start_time = time.time()
        
        try:
            await self._ensure_initialized()
            
            # 删除文件
            file_deleted = await self.file_manager.delete_file(key)
            
            # 删除索引
            index_deleted = True
            if self.index:
                index_deleted = await self.index.delete(str(key))
            
            if file_deleted or index_deleted:
                # 创建虚拟value用于策略通知
                dummy_value = CacheValue(data=None)
                self.strategy.on_remove(key, dummy_value)
                self.stats.deletes += 1
                return True
            
            return False
            
        except Exception as e:
            self.stats.errors += 1
            self._logger.error(f"Disk delete失败: {e}")
            raise
        finally:
            self.stats.total_delete_time += time.time() - start_time
    
    async def exists(self, key: CacheKey) -> bool:
        """检查键是否存在"""
        try:
            await self._ensure_initialized()
            
            if self.index:
                index_entry = await self.index.get(str(key))
                if not index_entry:
                    return False
                
                # 检查过期
                expires_at = index_entry.get('expires_at')
                if expires_at:
                    expire_time = datetime.fromisoformat(expires_at)
                    if datetime.now(timezone.utc) >= expire_time:
                        await self.delete(key)
                        return False
                
                return True
            else:
                # 直接检查文件
                file_path = self.file_manager._get_file_path(key)
                return file_path.exists()
                
        except Exception as e:
            self._logger.error(f"Disk exists失败: {e}")
            return False
    
    async def clear(self) -> bool:
        """清空缓存"""
        try:
            await self._ensure_initialized()
            
            if self.index:
                # 使用索引删除所有文件
                keys = await self.index.keys()
                for key_str in keys:
                    try:
                        parts = key_str.split(':', 1)
                        if len(parts) == 2:
                            cache_key = CacheKey(namespace=parts[0], key=parts[1])
                            await self.file_manager.delete_file(cache_key)
                    except Exception:
                        continue
                
                # 清空索引
                self.index.index.clear()
                self.index._dirty = True
            else:
                # 删除整个缓存目录
                import shutil
                if Path(self.config.cache_dir).exists():
                    shutil.rmtree(self.config.cache_dir)
                Path(self.config.cache_dir).mkdir(parents=True, exist_ok=True)
            
            self.strategy.clear()
            return True
            
        except Exception as e:
            self._logger.error(f"Disk clear失败: {e}")
            return False
    
    async def size(self) -> int:
        """获取缓存大小"""
        try:
            await self._ensure_initialized()
            
            if self.index:
                return len(self.index.index)
            else:
                # 遍历文件系统统计
                count = 0
                for root, dirs, files in os.walk(self.config.cache_dir):
                    count += len([f for f in files if f.endswith(self.config.file_extension)])
                return count
                
        except Exception as e:
            self._logger.error(f"Disk size失败: {e}")
            return 0
    
    async def keys(self, pattern: Optional[str] = None) -> List[CacheKey]:
        """获取所有键"""
        try:
            await self._ensure_initialized()
            
            result = []
            
            if self.index:
                keys = await self.index.keys()
                for key_str in keys:
                    try:
                        parts = key_str.split(':', 1)
                        if len(parts) >= 2:
                            cache_key = CacheKey(namespace=parts[0], key=parts[1])
                            if pattern is None or cache_key.matches_pattern(pattern):
                                result.append(cache_key)
                    except Exception:
                        continue
            
            return result
            
        except Exception as e:
            self._logger.error(f"Disk keys失败: {e}")
            return []
    
    async def _cleanup_space(self):
        """清理空间"""
        if not self.index:
            return
        
        # 获取所有键和它们的访问信息
        keys_info = []
        for key_str, entry in self.index.index.items():
            keys_info.append((key_str, entry.get('access_count', 0), entry.get('created_at')))
        
        # 按访问次数和创建时间排序（LRU）
        keys_info.sort(key=lambda x: (x[1], x[2]))
        
        # 删除前20%的文件
        cleanup_count = max(1, len(keys_info) // 5)
        for i in range(cleanup_count):
            key_str = keys_info[i][0]
            try:
                parts = key_str.split(':', 1)
                if len(parts) == 2:
                    cache_key = CacheKey(namespace=parts[0], key=parts[1])
                    await self.delete(cache_key)
            except Exception:
                continue
    
    async def _start_background_tasks(self):
        """启动后台任务"""
        # 清理任务
        if self.config.auto_cleanup_interval > 0:
            async def cleanup_loop():
                while self._enabled:
                    try:
                        await asyncio.sleep(self.config.auto_cleanup_interval)
                        if self.index:
                            expired_count = await self.index.cleanup_expired()
                            if expired_count > 0:
                                self._logger.info(f"清理过期项: {expired_count}")
                    except Exception as e:
                        self._logger.error(f"清理任务失败: {e}")
            
            self._cleanup_task = asyncio.create_task(cleanup_loop())
        
        # 索引同步任务
        if self.index and self.config.index_sync_interval > 0:
            async def sync_loop():
                while self._enabled:
                    try:
                        await asyncio.sleep(self.config.index_sync_interval)
                        await self.index.save()
                    except Exception as e:
                        self._logger.error(f"索引同步失败: {e}")
            
            self._index_sync_task = asyncio.create_task(sync_loop())
    
    # 生命周期管理
    async def start(self):
        """启动缓存"""
        await super().start()
        await self._ensure_initialized()
        await self._start_background_tasks()
    
    async def stop(self):
        """停止缓存"""
        await super().stop()
        
        # 取消后台任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self._index_sync_task:
            self._index_sync_task.cancel()
        
        # 保存索引
        if self.index:
            await self.index.save()
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            await self._ensure_initialized()
            
            # 检查磁盘空间
            disk_usage = await self.file_manager.get_disk_usage()
            cache_size = await self.size()
            
            return {
                "healthy": True,
                "cache_level": self.config.level.value,
                "cache_size": cache_size,
                "disk_usage_bytes": disk_usage,
                "disk_usage_mb": disk_usage / (1024 * 1024),
                "index_enabled": self.config.enable_index,
                "compression_enabled": self.config.enable_compression,
                "statistics": self.stats.to_dict()
            }
            
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
                "cache_level": self.config.level.value
            }


# 便利函数
def create_disk_cache(
    cache_dir: str = "./cache",
    max_size: int = 100000,
    enable_compression: bool = True,
    enable_index: bool = True,
    **kwargs
) -> DiskCache:
    """创建磁盘缓存的便利函数"""
    config = DiskCacheConfig(
        name=f"disk_cache_{cache_dir.replace('/', '_')}",
        cache_dir=cache_dir,
        max_size=max_size,
        enable_compression=enable_compression,
        enable_index=enable_index,
        **kwargs
    )
    return DiskCache(config) 