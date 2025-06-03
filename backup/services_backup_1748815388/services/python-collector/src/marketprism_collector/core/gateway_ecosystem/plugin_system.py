#!/usr/bin/env python3
"""
🔌 API网关插件系统

提供可扩展的插件框架，支持动态加载、热插拔插件，
让开发者能够轻松扩展网关功能。
"""

import asyncio
import logging
import importlib
import inspect
import os
import sys
from typing import Dict, List, Any, Optional, Type, Callable
from dataclasses import dataclass
from abc import ABC, abstractmethod
from pathlib import Path
import json

logger = logging.getLogger(__name__)


@dataclass
class PluginMetadata:
    """插件元数据"""
    name: str
    version: str
    description: str
    author: str
    category: str
    dependencies: List[str]
    config_schema: Dict[str, Any]
    entry_point: str


class PluginStatus:
    """插件状态"""
    UNKNOWN = "unknown"
    DISCOVERED = "discovered"
    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


class PluginBase(ABC):
    """🔌 插件基类"""
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        self.name = name
        self.config = config or {}
        self.logger = logging.getLogger(f"plugin.{name}")
        self.enabled = False
        
    @abstractmethod
    async def initialize(self):
        """初始化插件"""
        pass
    
    @abstractmethod
    async def start(self):
        """启动插件"""
        pass
    
    @abstractmethod
    async def stop(self):
        """停止插件"""
        pass
    
    @abstractmethod
    def get_metadata(self) -> PluginMetadata:
        """获取插件元数据"""
        pass
    
    async def is_healthy(self) -> bool:
        """检查插件健康状态"""
        return self.enabled
    
    def get_status(self) -> Dict[str, Any]:
        """获取插件状态"""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "config": self.config
        }


class Plugin:
    """插件包装器"""
    
    def __init__(self, plugin_class: Type[PluginBase], metadata: PluginMetadata, file_path: str):
        self.plugin_class = plugin_class
        self.metadata = metadata
        self.file_path = file_path
        self.instance = None
        self.status = PluginStatus.DISCOVERED
        self.last_error = None
        
    async def load(self, config: Dict[str, Any] = None) -> bool:
        """加载插件实例"""
        try:
            self.instance = self.plugin_class(self.metadata.name, config)
            await self.instance.initialize()
            self.status = PluginStatus.LOADED
            logger.info(f"插件加载成功: {self.metadata.name}")
            return True
            
        except Exception as e:
            self.last_error = str(e)
            self.status = PluginStatus.ERROR
            logger.error(f"插件加载失败 {self.metadata.name}: {e}")
            return False
    
    async def enable(self) -> bool:
        """启用插件"""
        if self.status != PluginStatus.LOADED:
            return False
        
        try:
            await self.instance.start()
            self.instance.enabled = True
            self.status = PluginStatus.ENABLED
            logger.info(f"插件启用成功: {self.metadata.name}")
            return True
            
        except Exception as e:
            self.last_error = str(e)
            self.status = PluginStatus.ERROR
            logger.error(f"插件启用失败 {self.metadata.name}: {e}")
            return False
    
    async def disable(self) -> bool:
        """禁用插件"""
        if self.status != PluginStatus.ENABLED:
            return False
        
        try:
            await self.instance.stop()
            self.instance.enabled = False
            self.status = PluginStatus.DISABLED
            logger.info(f"插件禁用成功: {self.metadata.name}")
            return True
            
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"插件禁用失败 {self.metadata.name}: {e}")
            return False
    
    def get_info(self) -> Dict[str, Any]:
        """获取插件信息"""
        return {
            "metadata": {
                "name": self.metadata.name,
                "version": self.metadata.version,
                "description": self.metadata.description,
                "author": self.metadata.author,
                "category": self.metadata.category,
                "dependencies": self.metadata.dependencies
            },
            "status": self.status,
            "file_path": self.file_path,
            "last_error": self.last_error,
            "instance_status": self.instance.get_status() if self.instance else None
        }


class PluginLoader:
    """🔧 插件加载器"""
    
    def __init__(self):
        self.discovered_plugins = []
        
    def discover_plugins(self, plugin_dirs: List[str]) -> List[Dict[str, Any]]:
        """发现插件"""
        discovered = []
        
        for plugin_dir in plugin_dirs:
            if not os.path.exists(plugin_dir):
                logger.warning(f"插件目录不存在: {plugin_dir}")
                continue
            
            discovered.extend(self._scan_directory(plugin_dir))
        
        self.discovered_plugins = discovered
        logger.info(f"发现 {len(discovered)} 个插件")
        return discovered
    
    def _scan_directory(self, directory: str) -> List[Dict[str, Any]]:
        """扫描目录中的插件"""
        plugins = []
        
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.endswith('.py') and not file.startswith('__'):
                    file_path = os.path.join(root, file)
                    plugin_info = self._inspect_plugin_file(file_path)
                    if plugin_info:
                        plugins.append(plugin_info)
        
        return plugins
    
    def _inspect_plugin_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """检查文件是否包含插件"""
        try:
            # 读取文件内容检查插件标识
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 简单检查是否包含插件基类
            if 'PluginBase' not in content:
                return None
            
            # 动态导入模块
            module_name = os.path.splitext(os.path.basename(file_path))[0]
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # 查找插件类
            plugin_classes = []
            for name, obj in inspect.getmembers(module):
                if (inspect.isclass(obj) and 
                    issubclass(obj, PluginBase) and 
                    obj != PluginBase):
                    plugin_classes.append(obj)
            
            if not plugin_classes:
                return None
            
            plugin_class = plugin_classes[0]  # 取第一个插件类
            
            # 获取插件元数据
            temp_instance = plugin_class("temp", {})
            metadata = temp_instance.get_metadata()
            
            return {
                "class": plugin_class,
                "metadata": metadata,
                "file_path": file_path
            }
            
        except Exception as e:
            logger.warning(f"检查插件文件失败 {file_path}: {e}")
            return None
    
    def load_plugin(self, plugin_info: Dict[str, Any], config: Dict[str, Any] = None) -> Optional[Plugin]:
        """加载插件"""
        try:
            plugin = Plugin(
                plugin_info["class"],
                plugin_info["metadata"],
                plugin_info["file_path"]
            )
            
            return plugin
            
        except Exception as e:
            logger.error(f"创建插件实例失败: {e}")
            return None


class PluginRegistry:
    """📋 插件注册表"""
    
    def __init__(self, plugin_dirs: List[str]):
        self.plugin_dirs = plugin_dirs
        self.plugins = {}  # name -> Plugin
        self.enabled_plugins = set()
        self.plugin_loader = PluginLoader()
        self.config_file = "./config/plugins.json"
        
        logger.info("PluginRegistry初始化完成")
    
    async def initialize(self):
        """初始化插件注册表"""
        logger.info("🔌 初始化插件注册表...")
        
        # 发现插件
        await self._discover_plugins()
        
        # 加载配置
        await self._load_plugin_configs()
        
        # 创建内置插件
        self._register_builtin_plugins()
        
        logger.info("✅ 插件注册表初始化完成")
    
    async def _discover_plugins(self):
        """发现插件"""
        discovered = self.plugin_loader.discover_plugins(self.plugin_dirs)
        
        for plugin_info in discovered:
            plugin = self.plugin_loader.load_plugin(plugin_info)
            if plugin:
                self.plugins[plugin.metadata.name] = plugin
                logger.info(f"插件已注册: {plugin.metadata.name}")
    
    async def _load_plugin_configs(self):
        """加载插件配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    configs = json.load(f)
                
                for plugin_name, config in configs.items():
                    if plugin_name in self.plugins:
                        plugin = self.plugins[plugin_name]
                        await plugin.load(config.get("config", {}))
                        
                        if config.get("enabled", False):
                            await plugin.enable()
                            self.enabled_plugins.add(plugin_name)
                
                logger.info(f"插件配置加载完成: {self.config_file}")
            
        except Exception as e:
            logger.error(f"插件配置加载失败: {e}")
    
    def _register_builtin_plugins(self):
        """注册内置插件"""
        # 日志插件
        logging_plugin = LoggingPlugin()
        self._register_plugin_instance(logging_plugin)
        
        # 监控插件
        metrics_plugin = MetricsPlugin()
        self._register_plugin_instance(metrics_plugin)
        
        # CORS插件
        cors_plugin = CORSPlugin()
        self._register_plugin_instance(cors_plugin)
        
        logger.info("内置插件注册完成")
    
    def _register_plugin_instance(self, plugin_instance: PluginBase):
        """注册插件实例"""
        metadata = plugin_instance.get_metadata()
        plugin = Plugin(type(plugin_instance), metadata, "builtin")
        plugin.instance = plugin_instance
        plugin.status = PluginStatus.LOADED
        
        self.plugins[metadata.name] = plugin
    
    async def enable_plugin(self, plugin_name: str) -> bool:
        """启用插件"""
        if plugin_name not in self.plugins:
            logger.error(f"插件不存在: {plugin_name}")
            return False
        
        plugin = self.plugins[plugin_name]
        
        if plugin.status == PluginStatus.DISCOVERED:
            await plugin.load()
        
        if await plugin.enable():
            self.enabled_plugins.add(plugin_name)
            await self._save_plugin_configs()
            return True
        
        return False
    
    async def disable_plugin(self, plugin_name: str) -> bool:
        """禁用插件"""
        if plugin_name not in self.plugins:
            logger.error(f"插件不存在: {plugin_name}")
            return False
        
        plugin = self.plugins[plugin_name]
        
        if await plugin.disable():
            self.enabled_plugins.discard(plugin_name)
            await self._save_plugin_configs()
            return True
        
        return False
    
    async def _save_plugin_configs(self):
        """保存插件配置"""
        try:
            configs = {}
            for name, plugin in self.plugins.items():
                configs[name] = {
                    "enabled": name in self.enabled_plugins,
                    "config": plugin.instance.config if plugin.instance else {}
                }
            
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(configs, f, indent=2)
            
            logger.info(f"插件配置保存完成: {self.config_file}")
            
        except Exception as e:
            logger.error(f"插件配置保存失败: {e}")
    
    def list_plugins(self) -> Dict[str, Any]:
        """列出所有插件"""
        plugins_info = {}
        
        for name, plugin in self.plugins.items():
            plugins_info[name] = plugin.get_info()
            plugins_info[name]["enabled"] = name in self.enabled_plugins
        
        return plugins_info
    
    def get_plugin(self, plugin_name: str) -> Optional[Plugin]:
        """获取插件"""
        return self.plugins.get(plugin_name)
    
    def get_enabled_plugins(self) -> List[Plugin]:
        """获取启用的插件"""
        return [
            self.plugins[name] for name in self.enabled_plugins 
            if name in self.plugins
        ]
    
    async def reload_plugin(self, plugin_name: str) -> bool:
        """重新加载插件"""
        if plugin_name not in self.plugins:
            return False
        
        plugin = self.plugins[plugin_name]
        was_enabled = plugin_name in self.enabled_plugins
        
        # 禁用插件
        if was_enabled:
            await self.disable_plugin(plugin_name)
        
        # 重新加载
        try:
            # 重新导入模块
            importlib.reload(sys.modules[plugin.plugin_class.__module__])
            
            # 重新创建实例
            await plugin.load(plugin.instance.config if plugin.instance else {})
            
            # 如果之前启用，重新启用
            if was_enabled:
                await self.enable_plugin(plugin_name)
            
            logger.info(f"插件重新加载成功: {plugin_name}")
            return True
            
        except Exception as e:
            logger.error(f"插件重新加载失败 {plugin_name}: {e}")
            return False


# 内置插件实现
class LoggingPlugin(PluginBase):
    """📝 日志插件"""
    
    def __init__(self, name: str = "logging", config: Dict[str, Any] = None):
        super().__init__(name, config)
    
    async def initialize(self):
        """初始化"""
        self.logger.info("日志插件初始化")
    
    async def start(self):
        """启动"""
        self.logger.info("日志插件启动")
    
    async def stop(self):
        """停止"""
        self.logger.info("日志插件停止")
    
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="logging",
            version="1.0.0",
            description="Request and response logging plugin",
            author="MarketPrism Team",
            category="monitoring",
            dependencies=[],
            config_schema={},
            entry_point="LoggingPlugin"
        )


class MetricsPlugin(PluginBase):
    """📊 监控指标插件"""
    
    def __init__(self, name: str = "metrics", config: Dict[str, Any] = None):
        super().__init__(name, config)
        self.request_count = 0
        self.error_count = 0
    
    async def initialize(self):
        """初始化"""
        self.logger.info("监控指标插件初始化")
    
    async def start(self):
        """启动"""
        self.logger.info("监控指标插件启动")
    
    async def stop(self):
        """停止"""
        self.logger.info("监控指标插件停止")
    
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="metrics",
            version="1.0.0",
            description="Metrics collection plugin",
            author="MarketPrism Team",
            category="monitoring",
            dependencies=[],
            config_schema={},
            entry_point="MetricsPlugin"
        )
    
    def record_request(self):
        """记录请求"""
        self.request_count += 1
    
    def record_error(self):
        """记录错误"""
        self.error_count += 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取指标"""
        return {
            "request_count": self.request_count,
            "error_count": self.error_count
        }


class CORSPlugin(PluginBase):
    """🌐 CORS插件"""
    
    def __init__(self, name: str = "cors", config: Dict[str, Any] = None):
        super().__init__(name, config)
        self.allowed_origins = config.get("allowed_origins", ["*"]) if config else ["*"]
    
    async def initialize(self):
        """初始化"""
        self.logger.info("CORS插件初始化")
    
    async def start(self):
        """启动"""
        self.logger.info("CORS插件启动")
    
    async def stop(self):
        """停止"""
        self.logger.info("CORS插件停止")
    
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="cors",
            version="1.0.0",
            description="CORS handling plugin",
            author="MarketPrism Team",
            category="security",
            dependencies=[],
            config_schema={
                "allowed_origins": {"type": "array", "items": {"type": "string"}}
            },
            entry_point="CORSPlugin"
        )
    
    def handle_cors(self, request_headers: Dict[str, str]) -> Dict[str, str]:
        """处理CORS"""
        cors_headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }
        
        return cors_headers