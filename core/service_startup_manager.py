"""
MarketPrism 服务启动管理器
自动检测和启动系统所需的组件
"""

from datetime import datetime, timezone
import asyncio
import logging
import time
import subprocess
import socket
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class ServiceStatus(Enum):
    """服务状态枚举"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    FAILED = "failed"
    UNKNOWN = "unknown"

@dataclass
class ServiceConfig:
    """服务配置"""
    name: str
    port: Optional[int] = None
    host: str = "localhost"
    start_command: Optional[str] = None
    health_check_url: Optional[str] = None
    required: bool = True
    startup_timeout: int = 30
    dependencies: List[str] = None

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []

class ServiceStartupManager:
    """服务启动管理器"""
    
    def __init__(self):
        self.services: Dict[str, ServiceConfig] = {}
        self.service_status: Dict[str, ServiceStatus] = {}
        self.service_processes: Dict[str, subprocess.Popen] = {}
        self._initialize_default_services()
    
    def _initialize_default_services(self):
        """初始化默认服务配置"""
        # NATS 服务
        self.services["nats"] = ServiceConfig(
            name="nats",
            port=4222,
            start_command="nats-server --port 4222",
            required=False  # 可选服务
        )
        
        # Redis 服务
        self.services["redis"] = ServiceConfig(
            name="redis",
            port=6379,
            start_command="redis-server --port 6379",
            required=False
        )
        
        # ClickHouse 服务 (通常作为外部服务)
        self.services["clickhouse"] = ServiceConfig(
            name="clickhouse",
            port=8123,
            required=False
        )
    
    def register_service(self, config: ServiceConfig):
        """注册服务"""
        self.services[config.name] = config
        self.service_status[config.name] = ServiceStatus.UNKNOWN
        logger.info(f"注册服务: {config.name}")
    
    def check_port_available(self, host: str, port: int) -> bool:
        """检查端口是否可用"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex((host, port))
                return result == 0  # 0表示连接成功，端口被占用
        except Exception:
            return False
    
    def get_service_status(self, service_name: str) -> ServiceStatus:
        """获取服务状态"""
        if service_name not in self.services:
            return ServiceStatus.UNKNOWN
        
        config = self.services[service_name]
        
        # 检查端口状态
        if config.port:
            if self.check_port_available(config.host, config.port):
                self.service_status[service_name] = ServiceStatus.RUNNING
                return ServiceStatus.RUNNING
            else:
                self.service_status[service_name] = ServiceStatus.STOPPED
                return ServiceStatus.STOPPED
        
        # 检查进程状态
        if service_name in self.service_processes:
            process = self.service_processes[service_name]
            if process.poll() is None:  # 进程仍在运行
                self.service_status[service_name] = ServiceStatus.RUNNING
                return ServiceStatus.RUNNING
            else:
                self.service_status[service_name] = ServiceStatus.FAILED
                return ServiceStatus.FAILED
        
        return self.service_status.get(service_name, ServiceStatus.UNKNOWN)
    
    async def start_service(self, service_name: str) -> bool:
        """启动服务"""
        if service_name not in self.services:
            logger.error(f"未知服务: {service_name}")
            return False
        
        config = self.services[service_name]
        
        # 检查依赖
        for dep in config.dependencies:
            if self.get_service_status(dep) != ServiceStatus.RUNNING:
                logger.info(f"启动依赖服务: {dep}")
                if not await self.start_service(dep):
                    logger.error(f"依赖服务启动失败: {dep}")
                    return False
        
        # 检查当前状态
        current_status = self.get_service_status(service_name)
        if current_status == ServiceStatus.RUNNING:
            logger.info(f"服务已运行: {service_name}")
            return True
        
        # 启动服务
        if config.start_command:
            try:
                logger.info(f"启动服务: {service_name} - {config.start_command}")
                self.service_status[service_name] = ServiceStatus.STARTING
                
                process = subprocess.Popen(
                    config.start_command.split(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True
                )
                
                self.service_processes[service_name] = process
                
                # 等待服务启动
                for i in range(config.startup_timeout):
                    await asyncio.sleep(1)
                    if self.get_service_status(service_name) == ServiceStatus.RUNNING:
                        logger.info(f"服务启动成功: {service_name}")
                        return True
                
                logger.error(f"服务启动超时: {service_name}")
                self.service_status[service_name] = ServiceStatus.FAILED
                return False
                
            except Exception as e:
                logger.error(f"服务启动失败: {service_name} - {e}")
                self.service_status[service_name] = ServiceStatus.FAILED
                return False
        else:
            logger.warning(f"服务无启动命令: {service_name}")
            return False
    
    async def stop_service(self, service_name: str) -> bool:
        """停止服务"""
        if service_name in self.service_processes:
            try:
                process = self.service_processes[service_name]
                process.terminate()
                
                # 等待进程结束
                for _ in range(10):
                    if process.poll() is not None:
                        break
                    await asyncio.sleep(0.5)
                else:
                    # 强制结束
                    process.kill()
                
                del self.service_processes[service_name]
                self.service_status[service_name] = ServiceStatus.STOPPED
                logger.info(f"服务已停止: {service_name}")
                return True
                
            except Exception as e:
                logger.error(f"停止服务失败: {service_name} - {e}")
                return False
        
        return True
    
    async def start_required_services(self) -> Dict[str, bool]:
        """启动所有必需的服务"""
        results = {}
        
        for service_name, config in self.services.items():
            if config.required:
                logger.info(f"启动必需服务: {service_name}")
                results[service_name] = await self.start_service(service_name)
            else:
                # 可选服务，尝试启动但不强制
                status = self.get_service_status(service_name)
                if status == ServiceStatus.STOPPED:
                    logger.info(f"尝试启动可选服务: {service_name}")
                    results[service_name] = await self.start_service(service_name)
                else:
                    results[service_name] = status == ServiceStatus.RUNNING
        
        return results
    
    async def stop_all_services(self):
        """停止所有服务"""
        for service_name in self.services:
            await self.stop_service(service_name)
    
    def get_services_report(self) -> Dict[str, Any]:
        """获取服务状态报告"""
        report = {}
        for service_name, config in self.services.items():
            status = self.get_service_status(service_name)
            report[service_name] = {
                "status": status.value,
                "required": config.required,
                "port": config.port,
                "has_start_command": bool(config.start_command)
            }
        return report

# 全局服务管理器实例
startup_manager = ServiceStartupManager()

async def ensure_services_running() -> bool:
    """确保所有服务都在运行"""
    try:
        logger.info("检查和启动必需服务...")
        results = await startup_manager.start_required_services()
        
        failed_services = [name for name, success in results.items() 
                          if not success and startup_manager.services[name].required]
        
        if failed_services:
            logger.error(f"必需服务启动失败: {failed_services}")
            return False
        
        logger.info("所有必需服务已运行")
        return True
        
    except Exception as e:
        logger.error(f"服务启动检查失败: {e}")
        return False

async def cleanup_services():
    """清理所有服务"""
    try:
        logger.info("清理所有服务...")
        await startup_manager.stop_all_services()
        logger.info("服务清理完成")
    except Exception as e:
        logger.error(f"服务清理失败: {e}") 