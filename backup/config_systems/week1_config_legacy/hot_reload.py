"""
配置热重载管理器

监控配置文件变化并自动重新加载配置
"""

import time
import threading
from typing import Dict, Set, Optional, TYPE_CHECKING
from pathlib import Path
from datetime import datetime, timedelta
import structlog
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent

if TYPE_CHECKING:
    from .unified_config_manager import UnifiedConfigManager


class ConfigFileHandler(FileSystemEventHandler):
    """配置文件变更处理器"""
    
    def __init__(self, hot_reload_manager: 'ConfigHotReloadManager'):
        self.hot_reload_manager = hot_reload_manager
        self.logger = structlog.get_logger(__name__)
        
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self.hot_reload_manager.handle_file_change(Path(event.src_path))
            
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self.hot_reload_manager.handle_file_change(Path(event.src_path))


class ConfigHotReloadManager:
    """
    配置热重载管理器
    
    监控配置文件变化，自动重新加载配置
    """
    
    def __init__(self, config_manager: 'UnifiedConfigManager'):
        self.config_manager = config_manager
        self.logger = structlog.get_logger(__name__)
        
        # 文件监控
        self.observer: Optional[Observer] = None
        self.file_handler = ConfigFileHandler(self)
        
        # 重载控制
        self.reload_delay = 1.0  # 重载延迟，避免频繁重载
        self.pending_reloads: Dict[str, datetime] = {}
        self.reload_lock = threading.Lock()
        
        # 重载统计
        self.reload_stats = {
            "file_changes_detected": 0,
            "reload_attempts": 0,
            "successful_reloads": 0,
            "failed_reloads": 0,
            "last_reload_time": None
        }
        
        # 重载线程
        self.reload_thread: Optional[threading.Thread] = None
        self.reload_thread_stop = threading.Event()
        
    def start(self):
        """启动热重载监控"""
        try:
            if self.observer is not None:
                self.logger.warning("热重载监控已经启动")
                return
                
            # 启动文件监控
            self.observer = Observer()
            self.observer.schedule(
                self.file_handler,
                path=str(self.config_manager.config_dir),
                recursive=True
            )
            self.observer.start()
            
            # 启动重载处理线程
            self.reload_thread = threading.Thread(
                target=self._reload_worker,
                name="ConfigHotReload",
                daemon=True
            )
            self.reload_thread.start()
            
            self.logger.info(
                "配置热重载监控已启动",
                config_dir=str(self.config_manager.config_dir)
            )
            
        except Exception as e:
            self.logger.error("启动热重载监控失败", error=str(e))
            self.stop()
            
    def stop(self):
        """停止热重载监控"""
        try:
            # 停止重载线程
            if self.reload_thread:
                self.reload_thread_stop.set()
                self.reload_thread.join(timeout=5.0)
                self.reload_thread = None
                self.reload_thread_stop.clear()
                
            # 停止文件监控
            if self.observer:
                self.observer.stop()
                self.observer.join(timeout=5.0)
                self.observer = None
                
            self.logger.info("配置热重载监控已停止")
            
        except Exception as e:
            self.logger.error("停止热重载监控失败", error=str(e))
            
    def handle_file_change(self, file_path: Path):
        """
        处理文件变更
        
        Args:
            file_path: 变更的文件路径
        """
        try:
            # 检查是否是配置文件
            if not self._is_config_file(file_path):
                return
                
            # 获取配置名称
            config_name = self._get_config_name_from_file(file_path)
            if not config_name:
                return
                
            with self.reload_lock:
                # 记录待重载配置
                self.pending_reloads[config_name] = datetime.utcnow()
                self.reload_stats["file_changes_detected"] += 1
                
            self.logger.debug(
                "检测到配置文件变更",
                config_name=config_name,
                file_path=str(file_path)
            )
            
        except Exception as e:
            self.logger.error("处理文件变更失败", file_path=str(file_path), error=str(e))
            
    def force_reload(self, config_name: str) -> bool:
        """
        强制重载配置
        
        Args:
            config_name: 配置名称
            
        Returns:
            bool: 重载是否成功
        """
        try:
            self.reload_stats["reload_attempts"] += 1
            
            result = self.config_manager.reload_config(config_name)
            
            if result.success:
                self.reload_stats["successful_reloads"] += 1
                self.reload_stats["last_reload_time"] = datetime.utcnow()
                
                self.logger.info(
                    "配置热重载成功",
                    config_name=config_name,
                    warnings=len(result.warnings)
                )
                return True
            else:
                self.reload_stats["failed_reloads"] += 1
                self.logger.error(
                    "配置热重载失败",
                    config_name=config_name,
                    errors=result.errors
                )
                return False
                
        except Exception as e:
            self.reload_stats["failed_reloads"] += 1
            self.logger.error("配置热重载异常", config_name=config_name, error=str(e))
            return False
            
    def get_stats(self) -> Dict[str, any]:
        """获取热重载统计信息"""
        with self.reload_lock:
            stats = self.reload_stats.copy()
            stats["pending_reloads"] = len(self.pending_reloads)
            stats["is_monitoring"] = self.observer is not None and self.observer.is_alive()
            return stats
            
    def _reload_worker(self):
        """重载工作线程"""
        while not self.reload_thread_stop.is_set():
            try:
                # 检查待重载配置
                with self.reload_lock:
                    now = datetime.utcnow()
                    ready_to_reload = []
                    
                    for config_name, change_time in list(self.pending_reloads.items()):
                        # 检查是否已经延迟足够时间
                        if (now - change_time).total_seconds() >= self.reload_delay:
                            ready_to_reload.append(config_name)
                            del self.pending_reloads[config_name]
                            
                # 执行重载
                for config_name in ready_to_reload:
                    self.force_reload(config_name)
                    
                # 等待一段时间再检查
                self.reload_thread_stop.wait(0.5)
                
            except Exception as e:
                self.logger.error("重载工作线程异常", error=str(e))
                self.reload_thread_stop.wait(1.0)
                
    def _is_config_file(self, file_path: Path) -> bool:
        """检查是否是配置文件"""
        # 检查文件扩展名
        if file_path.suffix.lower() not in ['.yaml', '.yml', '.json']:
            return False
            
        # 检查文件是否在配置目录中
        try:
            file_path.relative_to(self.config_manager.config_dir)
            return True
        except ValueError:
            return False
            
    def _get_config_name_from_file(self, file_path: Path) -> Optional[str]:
        """从文件路径获取配置名称"""
        # 查找对应的配置
        for config_name, registered_file in self.config_manager._config_files.items():
            try:
                if file_path.samefile(registered_file):
                    return config_name
            except (OSError, FileNotFoundError):
                # 文件可能不存在，使用路径比较
                if file_path == registered_file:
                    return config_name
                    
        return None