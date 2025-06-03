"""
文件配置仓库

支持多种文件格式的配置存储和管理。
"""

import os
import aiofiles
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import hashlib
import yaml
import json
import configparser
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .config_repository import (
    ConfigRepository, ConfigSource, ConfigEntry, ConfigFormat,
    ConfigRepositoryError, ConfigRepositoryConnectionError
)


class FileChangeHandler(FileSystemEventHandler):
    """文件变更处理器"""
    
    def __init__(self, repository: 'FileConfigRepository'):
        self.repository = repository
        
    def on_modified(self, event):
        """文件修改时的回调"""
        if not event.is_directory and event.src_path == self.repository.file_path:
            asyncio.create_task(self.repository._handle_file_change())


class FileConfigRepository(ConfigRepository):
    """文件配置仓库
    
    支持YAML、JSON、TOML、INI等多种文件格式的配置管理。
    提供文件监控、自动重载、原子写入等高级功能。
    """
    
    def __init__(self, source: ConfigSource):
        super().__init__(source)
        self.file_path = source.location
        self.file_format = source.format
        self.data: Dict[str, Any] = {}
        self.file_observer = None
        self.last_modified = None
        self.file_checksum = None
        self.auto_reload = True
        self.backup_enabled = True
        self.backup_count = 5
        
    async def connect(self) -> bool:
        """连接到文件配置源"""
        try:
            # 检查文件是否存在
            if not os.path.exists(self.file_path):
                if self.source.readonly:
                    raise ConfigRepositoryConnectionError(
                        f"File not found and repository is readonly: {self.file_path}"
                    )
                # 创建空配置文件
                await self._create_empty_file()
            
            # 加载配置文件
            await self._load_file()
            
            # 启动文件监控
            if self.auto_reload:
                await self._start_file_monitoring()
            
            self.is_connected = True
            return True
            
        except Exception as e:
            raise ConfigRepositoryConnectionError(f"Failed to connect to file: {e}")
    
    async def disconnect(self) -> bool:
        """断开文件配置源连接"""
        try:
            # 停止文件监控
            if self.file_observer:
                self.file_observer.stop()
                self.file_observer.join()
                self.file_observer = None
            
            # 清空数据
            self.data.clear()
            self.cache.clear()
            
            self.is_connected = False
            return True
            
        except Exception as e:
            raise ConfigRepositoryError(f"Failed to disconnect from file: {e}")
    
    async def get(self, key: str) -> Optional[ConfigEntry]:
        """获取配置项"""
        if not self.is_connected:
            await self.connect()
        
        # 检查缓存
        if self.cache_enabled and key in self.cache:
            return self.cache[key]
        
        # 从文件数据获取
        value = self._get_nested_value(self.data, key)
        if value is None:
            return None
        
        # 创建配置条目
        entry = ConfigEntry(
            key=key,
            value=value,
            source=self.source.name,
            format=self.file_format,
            timestamp=self.last_modified,
            checksum=self._calculate_value_checksum(value)
        )
        
        # 更新缓存
        if self.cache_enabled:
            self.cache[key] = entry
        
        return entry
    
    async def set(self, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """设置配置项"""
        if self.source.readonly:
            raise ConfigRepositoryError("Repository is readonly")
        
        if not self.is_connected:
            await self.connect()
        
        # 创建备份
        if self.backup_enabled:
            await self._create_backup()
        
        try:
            # 设置嵌套值
            self._set_nested_value(self.data, key, value)
            
            # 保存到文件
            await self._save_file()
            
            # 更新缓存
            if self.cache_enabled:
                entry = ConfigEntry(
                    key=key,
                    value=value,
                    source=self.source.name,
                    format=self.file_format,
                    timestamp=datetime.utcnow(),
                    checksum=self._calculate_value_checksum(value),
                    metadata=metadata or {}
                )
                self.cache[key] = entry
            
            return True
            
        except Exception as e:
            # 恢复备份
            if self.backup_enabled:
                await self._restore_backup()
            raise ConfigRepositoryError(f"Failed to set config: {e}")
    
    async def delete(self, key: str) -> bool:
        """删除配置项"""
        if self.source.readonly:
            raise ConfigRepositoryError("Repository is readonly")
        
        if not self.is_connected:
            await self.connect()
        
        # 创建备份
        if self.backup_enabled:
            await self._create_backup()
        
        try:
            # 删除嵌套值
            if self._delete_nested_value(self.data, key):
                # 保存到文件
                await self._save_file()
                
                # 清除缓存
                self.cache.pop(key, None)
                
                return True
            
            return False
            
        except Exception as e:
            # 恢复备份
            if self.backup_enabled:
                await self._restore_backup()
            raise ConfigRepositoryError(f"Failed to delete config: {e}")
    
    async def list_keys(self, prefix: Optional[str] = None) -> List[str]:
        """列出所有键"""
        if not self.is_connected:
            await self.connect()
        
        keys = self._get_all_keys(self.data)
        
        if prefix:
            keys = [key for key in keys if key.startswith(prefix)]
        
        return sorted(keys)
    
    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        if not self.is_connected:
            await self.connect()
        
        return self._get_nested_value(self.data, key) is not None
    
    async def _get_from_source(self, key: str) -> Optional[ConfigEntry]:
        """从配置源直接获取（绕过缓存）"""
        value = self._get_nested_value(self.data, key)
        if value is None:
            return None
        
        return ConfigEntry(
            key=key,
            value=value,
            source=self.source.name,
            format=self.file_format,
            timestamp=self.last_modified,
            checksum=self._calculate_value_checksum(value)
        )
    
    # 文件操作方法
    async def _create_empty_file(self):
        """创建空配置文件"""
        # 确保目录存在
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        
        empty_data = {}
        serialized = self._serialize_config(empty_data)
        
        async with aiofiles.open(self.file_path, 'w', encoding='utf-8') as f:
            await f.write(serialized)
    
    async def _load_file(self):
        """加载配置文件"""
        try:
            async with aiofiles.open(self.file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            
            self.data = self._deserialize_config(content)
            self.last_modified = datetime.fromtimestamp(os.path.getmtime(self.file_path))
            self.file_checksum = self._calculate_file_checksum()
            
        except Exception as e:
            raise ConfigRepositoryError(f"Failed to load file {self.file_path}: {e}")
    
    async def _save_file(self):
        """保存配置文件"""
        try:
            serialized = self._serialize_config(self.data)
            
            # 原子写入：先写临时文件，再重命名
            temp_path = f"{self.file_path}.tmp"
            async with aiofiles.open(temp_path, 'w', encoding='utf-8') as f:
                await f.write(serialized)
            
            # 原子重命名
            os.rename(temp_path, self.file_path)
            
            # 更新元数据
            self.last_modified = datetime.fromtimestamp(os.path.getmtime(self.file_path))
            self.file_checksum = self._calculate_file_checksum()
            
        except Exception as e:
            # 清理临时文件
            temp_path = f"{self.file_path}.tmp"
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise ConfigRepositoryError(f"Failed to save file {self.file_path}: {e}")
    
    async def _create_backup(self):
        """创建备份文件"""
        if not os.path.exists(self.file_path):
            return
        
        backup_dir = f"{self.file_path}.backups"
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"config_{timestamp}.backup")
        
        # 复制当前文件到备份
        async with aiofiles.open(self.file_path, 'rb') as src:
            async with aiofiles.open(backup_path, 'wb') as dst:
                content = await src.read()
                await dst.write(content)
        
        # 清理旧备份
        await self._cleanup_old_backups(backup_dir)
    
    async def _restore_backup(self):
        """恢复最新备份"""
        backup_dir = f"{self.file_path}.backups"
        if not os.path.exists(backup_dir):
            return
        
        # 找到最新的备份文件
        backup_files = [f for f in os.listdir(backup_dir) if f.endswith('.backup')]
        if not backup_files:
            return
        
        latest_backup = max(backup_files, key=lambda f: os.path.getmtime(os.path.join(backup_dir, f)))
        backup_path = os.path.join(backup_dir, latest_backup)
        
        # 恢复备份
        async with aiofiles.open(backup_path, 'rb') as src:
            async with aiofiles.open(self.file_path, 'wb') as dst:
                content = await src.read()
                await dst.write(content)
        
        # 重新加载文件
        await self._load_file()
    
    async def _cleanup_old_backups(self, backup_dir: str):
        """清理旧备份文件"""
        backup_files = [f for f in os.listdir(backup_dir) if f.endswith('.backup')]
        if len(backup_files) <= self.backup_count:
            return
        
        # 按修改时间排序，删除最旧的文件
        backup_files.sort(key=lambda f: os.path.getmtime(os.path.join(backup_dir, f)))
        files_to_delete = backup_files[:-self.backup_count]
        
        for file_name in files_to_delete:
            file_path = os.path.join(backup_dir, file_name)
            os.remove(file_path)
    
    async def _start_file_monitoring(self):
        """启动文件监控"""
        if self.file_observer:
            return
        
        self.file_observer = Observer()
        handler = FileChangeHandler(self)
        
        watch_dir = os.path.dirname(self.file_path)
        self.file_observer.schedule(handler, watch_dir, recursive=False)
        self.file_observer.start()
    
    async def _handle_file_change(self):
        """处理文件变更"""
        try:
            # 检查文件是否真的变更了
            new_checksum = self._calculate_file_checksum()
            if new_checksum == self.file_checksum:
                return
            
            # 重新加载文件
            await self._load_file()
            
            # 清空缓存
            self.cache.clear()
            
        except Exception as e:
            # 记录错误，但不中断程序
            print(f"Error handling file change: {e}")
    
    # 数据操作辅助方法
    def _get_nested_value(self, data: Dict[str, Any], key: str) -> Any:
        """获取嵌套值"""
        keys = key.split('.')
        current = data
        
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return None
        
        return current
    
    def _set_nested_value(self, data: Dict[str, Any], key: str, value: Any):
        """设置嵌套值"""
        keys = key.split('.')
        current = data
        
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        current[keys[-1]] = value
    
    def _delete_nested_value(self, data: Dict[str, Any], key: str) -> bool:
        """删除嵌套值"""
        keys = key.split('.')
        current = data
        
        # 导航到父级
        for k in keys[:-1]:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return False
        
        # 删除最后的键
        if isinstance(current, dict) and keys[-1] in current:
            del current[keys[-1]]
            return True
        
        return False
    
    def _get_all_keys(self, data: Dict[str, Any], prefix: str = "") -> List[str]:
        """获取所有键"""
        keys = []
        
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            keys.append(full_key)
            
            if isinstance(value, dict):
                keys.extend(self._get_all_keys(value, full_key))
        
        return keys
    
    # 序列化方法
    def _serialize_config(self, data: Dict[str, Any]) -> str:
        """序列化配置数据"""
        if self.file_format == ConfigFormat.YAML:
            return yaml.dump(data, default_flow_style=False, allow_unicode=True)
        elif self.file_format == ConfigFormat.JSON:
            return json.dumps(data, indent=2, ensure_ascii=False)
        elif self.file_format == ConfigFormat.INI:
            return self._serialize_ini(data)
        else:
            raise ValueError(f"Unsupported file format: {self.file_format}")
    
    def _deserialize_config(self, content: str) -> Dict[str, Any]:
        """反序列化配置数据"""
        if self.file_format == ConfigFormat.YAML:
            return yaml.safe_load(content) or {}
        elif self.file_format == ConfigFormat.JSON:
            return json.loads(content) or {}
        elif self.file_format == ConfigFormat.INI:
            return self._deserialize_ini(content)
        else:
            raise ValueError(f"Unsupported file format: {self.file_format}")
    
    def _serialize_ini(self, data: Dict[str, Any]) -> str:
        """序列化为INI格式"""
        config = configparser.ConfigParser()
        
        for key, value in data.items():
            if isinstance(value, dict):
                config[key] = value
            else:
                if 'DEFAULT' not in config:
                    config['DEFAULT'] = {}
                config['DEFAULT'][key] = str(value)
        
        from io import StringIO
        output = StringIO()
        config.write(output)
        return output.getvalue()
    
    def _deserialize_ini(self, content: str) -> Dict[str, Any]:
        """反序列化INI格式"""
        config = configparser.ConfigParser()
        config.read_string(content)
        
        result = {}
        for section_name in config.sections():
            result[section_name] = dict(config[section_name])
        
        # 处理DEFAULT节
        if config.defaults():
            result.update(dict(config.defaults()))
        
        return result
    
    # 工具方法
    def _calculate_file_checksum(self) -> str:
        """计算文件校验和"""
        if not os.path.exists(self.file_path):
            return ""
        
        with open(self.file_path, 'rb') as f:
            content = f.read()
            return hashlib.md5(content).hexdigest()
    
    def _calculate_value_checksum(self, value: Any) -> str:
        """计算值的校验和"""
        value_str = json.dumps(value, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(value_str.encode('utf-8')).hexdigest()
    
    # 配置方法
    def enable_auto_reload(self):
        """启用自动重载"""
        self.auto_reload = True
        if self.is_connected and not self.file_observer:
            asyncio.create_task(self._start_file_monitoring())
    
    def disable_auto_reload(self):
        """禁用自动重载"""
        self.auto_reload = False
        if self.file_observer:
            self.file_observer.stop()
            self.file_observer.join()
            self.file_observer = None
    
    def enable_backup(self, backup_count: int = 5):
        """启用备份"""
        self.backup_enabled = True
        self.backup_count = backup_count
    
    def disable_backup(self):
        """禁用备份"""
        self.backup_enabled = False