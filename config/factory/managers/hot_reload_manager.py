"""
配置热重载管理器
"""

import logging
import threading
import time
from pathlib import Path
from typing import Dict, Any, Callable, Optional

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None
    FileSystemEventHandler = None


class ConfigFileHandler:
    """配置文件变更处理器"""
    
    def __init__(self, reload_callback: Callable[[str], None]):
        self.reload_callback = reload_callback
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory and event.src_path.endswith('.yaml'):
            self.logger.info(f"配置文件变更: {event.src_path}")
            self.reload_callback(event.src_path)


class HotReloadManager:
    """配置热重载管理器"""
    
    def __init__(self, config_factory):
        self.config_factory = config_factory
        self.logger = logging.getLogger(__name__)
        self.observer = None
        self.is_running = False
        self.lock = threading.Lock()
        
        # 重载回调
        self.reload_callbacks = []
        
        # 防抖设置
        self.debounce_delay = 1.0  # 秒
        self.last_reload_time = {}
    
    def start(self):
        """启动热重载监控"""
        with self.lock:
            if self.is_running:
                self.logger.warning("热重载管理器已在运行")
                return

            try:
                # 检查watchdog是否可用
                if not WATCHDOG_AVAILABLE:
                    self.logger.warning("watchdog库未安装，热重载功能不可用")
                    return
                
                self.observer = Observer()
                handler = ConfigFileHandler(self._on_config_changed)
                
                # 监控配置目录
                config_root = self.config_factory.config_root
                if config_root.exists():
                    self.observer.schedule(handler, str(config_root), recursive=True)
                    self.observer.start()
                    self.is_running = True
                    self.logger.info(f"热重载监控已启动: {config_root}")
                else:
                    self.logger.error(f"配置目录不存在: {config_root}")
                
            except Exception as e:
                self.logger.error(f"启动热重载监控失败: {e}")
    
    def stop(self):
        """停止热重载监控"""
        with self.lock:
            if not self.is_running:
                return
            
            try:
                if self.observer:
                    self.observer.stop()
                    self.observer.join()
                    self.observer = None
                
                self.is_running = False
                self.logger.info("热重载监控已停止")
                
            except Exception as e:
                self.logger.error(f"停止热重载监控失败: {e}")
    
    def _on_config_changed(self, file_path: str):
        """配置文件变更回调"""
        try:
            # 防抖处理
            current_time = time.time()
            if file_path in self.last_reload_time:
                if current_time - self.last_reload_time[file_path] < self.debounce_delay:
                    return
            
            self.last_reload_time[file_path] = current_time
            
            # 确定受影响的服务
            affected_services = self._determine_affected_services(file_path)
            
            # 重载配置
            for service in affected_services:
                self.logger.info(f"重载服务配置: {service}")
                self.config_factory.reload_config(service)
            
            # 调用注册的回调
            for callback in self.reload_callbacks:
                try:
                    callback(file_path, affected_services)
                except Exception as e:
                    self.logger.error(f"热重载回调失败: {e}")
            
        except Exception as e:
            self.logger.error(f"处理配置变更失败 {file_path}: {e}")
    
    def _determine_affected_services(self, file_path: str) -> list:
        """确定受影响的服务"""
        affected_services = []
        config_path = Path(file_path)
        config_root = self.config_factory.config_root
        
        try:
            relative_path = config_path.relative_to(config_root)
            path_parts = relative_path.parts
            
            if len(path_parts) >= 2:
                if path_parts[0] == 'services':
                    # 服务配置变更
                    service_name = path_parts[1]
                    affected_services.append(service_name)
                elif path_parts[0] in ['core', 'environments']:
                    # 核心或环境配置变更，影响所有服务
                    affected_services = self.config_factory.list_services()
                elif path_parts[0] == 'infrastructure':
                    # 基础设施配置变更，影响依赖的服务
                    component = path_parts[1] if len(path_parts) > 1 else 'unknown'
                    affected_services = self._get_services_depending_on(component)
            
        except ValueError:
            # 文件不在配置根目录下
            self.logger.warning(f"配置文件不在监控目录下: {file_path}")
        
        return affected_services
    
    def _get_services_depending_on(self, component: str) -> list:
        """获取依赖特定组件的服务"""
        # 这里可以根据实际的依赖关系来确定
        dependency_map = {
            'redis': ['monitoring-alerting', 'data-collector', 'api-gateway'],
            'clickhouse': ['monitoring-alerting'],
            'prometheus': ['monitoring-alerting'],
            'grafana': [],
        }
        
        return dependency_map.get(component, [])
    
    def add_reload_callback(self, callback: Callable[[str, list], None]):
        """添加重载回调"""
        self.reload_callbacks.append(callback)
    
    def remove_reload_callback(self, callback: Callable[[str, list], None]):
        """移除重载回调"""
        if callback in self.reload_callbacks:
            self.reload_callbacks.remove(callback)
    
    def force_reload_all(self):
        """强制重载所有配置"""
        self.logger.info("强制重载所有配置")
        self.config_factory.reload_config()
    
    def get_status(self) -> Dict[str, Any]:
        """获取热重载状态"""
        return {
            "is_running": self.is_running,
            "monitored_directory": str(self.config_factory.config_root),
            "callback_count": len(self.reload_callbacks),
            "debounce_delay": self.debounce_delay,
            "last_reload_times": dict(self.last_reload_time)
        }
