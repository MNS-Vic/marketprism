#!/usr/bin/env python3
"""
MarketPrism 服务管理器
自动重启、健康检查、故障恢复
"""

import asyncio
import os
import signal
import subprocess
import time
import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import structlog
from dataclasses import dataclass
from enum import Enum

# 添加项目根目录到路径
import sys
sys.path.append(str(Path(__file__).parent.parent))

from services.common.process_monitor import ProcessHealthMonitor, HealthStatus

logger = structlog.get_logger(__name__)


class ServiceStatus(Enum):
    """服务状态"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"
    RESTARTING = "restarting"


@dataclass
class ServiceConfig:
    """服务配置"""
    name: str
    command: str
    working_dir: str
    env_vars: Dict[str, str]
    log_file: str
    pid_file: str
    auto_restart: bool = True
    max_restart_attempts: int = 5
    restart_delay: int = 10
    health_check_url: Optional[str] = None
    health_check_interval: int = 60
    cpu_threshold: float = 80.0
    memory_threshold_mb: int = 500
    max_uptime_hours: int = 24


class ServiceManager:
    """服务管理器"""
    
    def __init__(self, config_file: str = "config/services.yaml"):
        self.config_file = Path(config_file)
        self.services: Dict[str, ServiceConfig] = {}
        self.processes: Dict[str, subprocess.Popen] = {}
        self.monitors: Dict[str, ProcessHealthMonitor] = {}
        self.service_status: Dict[str, ServiceStatus] = {}
        self.restart_counts: Dict[str, int] = {}
        self.last_restart_times: Dict[str, float] = {}
        
        # 统计信息
        self.stats = {
            "start_time": datetime.now(),
            "total_restarts": 0,
            "successful_restarts": 0,
            "failed_restarts": 0,
            "services_managed": 0
        }
        
        self.is_running = False
        self.management_task: Optional[asyncio.Task] = None
    
    def load_config(self):
        """加载服务配置"""
        if not self.config_file.exists():
            # 创建默认配置
            self._create_default_config()
        
        with open(self.config_file, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        self.services = {}
        for service_name, service_config in config_data.get('services', {}).items():
            self.services[service_name] = ServiceConfig(
                name=service_name,
                **service_config
            )
            self.service_status[service_name] = ServiceStatus.STOPPED
            self.restart_counts[service_name] = 0
            self.last_restart_times[service_name] = 0
        
        self.stats["services_managed"] = len(self.services)
        logger.info("服务配置加载完成", services=list(self.services.keys()))
    
    def _create_default_config(self):
        """创建默认服务配置"""
        default_config = {
            "services": {
                "message-broker": {
                    "command": "python3 services/message-broker/main.py -c services/message-broker/config/unified_message_broker.yaml",
                    "working_dir": "/home/ubuntu/marketprism",
                    "env_vars": {},
                    "log_file": "services/message-broker/logs/broker_managed.log",
                    "pid_file": "services/message-broker/logs/broker.pid",
                    "health_check_url": "http://127.0.0.1:8086/api/v1/status",
                    "cpu_threshold": 50.0,
                    "memory_threshold_mb": 200,
                    "max_uptime_hours": 48
                },
                "data-collector": {
                    "command": "python3 services/data-collector/unified_collector_main.py",
                    "working_dir": "/home/ubuntu/marketprism",
                    "env_vars": {"COLLECTOR_ENABLE_HTTP": "0"},
                    "log_file": "services/data-collector/logs/collector_managed.log",
                    "pid_file": "services/data-collector/logs/collector.pid",
                    "cpu_threshold": 70.0,
                    "memory_threshold_mb": 300,
                    "max_uptime_hours": 24
                },
                "data-storage-service": {
                    "command": "python3 services/data-storage-service/main.py",
                    "working_dir": "/home/ubuntu/marketprism",
                    "env_vars": {},
                    "log_file": "services/data-storage-service/logs/storage_managed.log",
                    "pid_file": "services/data-storage-service/logs/storage.pid",
                    "health_check_url": "http://127.0.0.1:8081/health",
                    "cpu_threshold": 30.0,
                    "memory_threshold_mb": 200,
                    "max_uptime_hours": 48
                }
            }
        }
        
        # 确保配置目录存在
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)
        
        logger.info("创建默认服务配置", config_file=str(self.config_file))
    
    async def start_service(self, service_name: str) -> bool:
        """启动服务"""
        if service_name not in self.services:
            logger.error("服务不存在", service_name=service_name)
            return False
        
        service = self.services[service_name]
        
        # 检查是否已在运行
        if self.service_status[service_name] in [ServiceStatus.RUNNING, ServiceStatus.STARTING]:
            logger.warning("服务已在运行", service_name=service_name)
            return True
        
        try:
            self.service_status[service_name] = ServiceStatus.STARTING
            logger.info("启动服务", service_name=service_name)
            
            # 确保日志目录存在
            log_path = Path(service.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 确保PID目录存在
            pid_path = Path(service.pid_file)
            pid_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 设置环境变量
            env = os.environ.copy()
            env.update(service.env_vars)
            
            # 启动进程
            with open(service.log_file, 'a') as log_file:
                process = subprocess.Popen(
                    service.command.split(),
                    cwd=service.working_dir,
                    env=env,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    preexec_fn=os.setsid  # 创建新的进程组
                )
            
            # 保存进程信息
            self.processes[service_name] = process
            
            # 写入PID文件
            with open(service.pid_file, 'w') as f:
                f.write(str(process.pid))
            
            # 等待进程启动
            await asyncio.sleep(2)
            
            # 检查进程是否成功启动
            if process.poll() is None:
                self.service_status[service_name] = ServiceStatus.RUNNING
                
                # 启动健康监控
                await self._start_health_monitor(service_name, process.pid)
                
                logger.info("服务启动成功", 
                           service_name=service_name, 
                           pid=process.pid)
                return True
            else:
                self.service_status[service_name] = ServiceStatus.FAILED
                logger.error("服务启动失败", 
                           service_name=service_name,
                           return_code=process.returncode)
                return False
        
        except Exception as e:
            self.service_status[service_name] = ServiceStatus.FAILED
            logger.error("启动服务异常", 
                        service_name=service_name, 
                        error=str(e))
            return False
    
    async def stop_service(self, service_name: str, force: bool = False) -> bool:
        """停止服务"""
        if service_name not in self.services:
            logger.error("服务不存在", service_name=service_name)
            return False
        
        if self.service_status[service_name] == ServiceStatus.STOPPED:
            logger.info("服务已停止", service_name=service_name)
            return True
        
        try:
            self.service_status[service_name] = ServiceStatus.STOPPING
            logger.info("停止服务", service_name=service_name, force=force)
            
            # 停止健康监控
            if service_name in self.monitors:
                await self.monitors[service_name].stop_monitoring()
                del self.monitors[service_name]
            
            # 获取进程
            process = self.processes.get(service_name)
            if process:
                try:
                    if force:
                        # 强制终止
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    else:
                        # 优雅终止
                        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                        
                        # 等待进程结束
                        for _ in range(10):  # 等待最多10秒
                            if process.poll() is not None:
                                break
                            await asyncio.sleep(1)
                        
                        # 如果还没结束，强制终止
                        if process.poll() is None:
                            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    
                    # 等待进程完全结束
                    process.wait()
                    
                except ProcessLookupError:
                    # 进程已经不存在
                    pass
                except Exception as e:
                    logger.warning("终止进程时出现异常", error=str(e))
                
                del self.processes[service_name]
            
            # 清理PID文件
            pid_file = Path(self.services[service_name].pid_file)
            if pid_file.exists():
                pid_file.unlink()
            
            self.service_status[service_name] = ServiceStatus.STOPPED
            logger.info("服务停止成功", service_name=service_name)
            return True
        
        except Exception as e:
            logger.error("停止服务异常", 
                        service_name=service_name, 
                        error=str(e))
            return False
    
    async def restart_service(self, service_name: str) -> bool:
        """重启服务"""
        if service_name not in self.services:
            logger.error("服务不存在", service_name=service_name)
            return False
        
        service = self.services[service_name]
        
        # 检查重启限制
        if self.restart_counts[service_name] >= service.max_restart_attempts:
            logger.error("已达到最大重启次数",
                        service_name=service_name,
                        restart_count=self.restart_counts[service_name])
            return False
        
        # 检查重启间隔
        if time.time() - self.last_restart_times[service_name] < service.restart_delay:
            logger.info("重启间隔未到，跳过重启",
                       service_name=service_name)
            return False
        
        try:
            self.service_status[service_name] = ServiceStatus.RESTARTING
            self.restart_counts[service_name] += 1
            self.last_restart_times[service_name] = time.time()
            self.stats["total_restarts"] += 1
            
            logger.info("重启服务",
                       service_name=service_name,
                       restart_count=self.restart_counts[service_name])
            
            # 停止服务
            await self.stop_service(service_name)
            
            # 等待一段时间
            await asyncio.sleep(service.restart_delay)
            
            # 启动服务
            success = await self.start_service(service_name)
            
            if success:
                self.stats["successful_restarts"] += 1
                # 重置重启计数（成功重启后）
                self.restart_counts[service_name] = 0
                logger.info("服务重启成功", service_name=service_name)
            else:
                self.stats["failed_restarts"] += 1
                logger.error("服务重启失败", service_name=service_name)
            
            return success
        
        except Exception as e:
            self.stats["failed_restarts"] += 1
            logger.error("重启服务异常",
                        service_name=service_name,
                        error=str(e))
            return False
    
    async def _start_health_monitor(self, service_name: str, pid: int):
        """启动健康监控"""
        service = self.services[service_name]
        
        monitor = ProcessHealthMonitor(
            process_name=service_name,
            pid=pid,
            check_interval=service.health_check_interval,
            cpu_threshold=service.cpu_threshold,
            memory_threshold_mb=service.memory_threshold_mb,
            max_uptime_hours=service.max_uptime_hours
        )
        
        # 设置回调函数
        monitor.on_restart_needed = lambda metrics, reasons: asyncio.create_task(
            self._handle_restart_needed(service_name, metrics, reasons)
        )
        
        self.monitors[service_name] = monitor
        await monitor.start_monitoring()
    
    async def _handle_restart_needed(self, service_name: str, metrics, reasons: List[str]):
        """处理需要重启的情况"""
        logger.warning("检测到服务需要重启",
                      service_name=service_name,
                      reasons=reasons,
                      cpu_percent=metrics.cpu_percent,
                      memory_mb=metrics.memory_mb)
        
        # 自动重启
        if self.services[service_name].auto_restart:
            await self.restart_service(service_name)
    
    async def start_all_services(self):
        """启动所有服务"""
        logger.info("启动所有服务")
        
        for service_name in self.services:
            success = await self.start_service(service_name)
            if not success:
                logger.error("启动服务失败", service_name=service_name)
            
            # 服务间启动间隔
            await asyncio.sleep(5)
    
    async def stop_all_services(self):
        """停止所有服务"""
        logger.info("停止所有服务")
        
        # 按相反顺序停止服务
        service_names = list(reversed(list(self.services.keys())))
        
        for service_name in service_names:
            await self.stop_service(service_name)
            await asyncio.sleep(2)
    
    def get_service_status(self, service_name: str) -> Dict[str, Any]:
        """获取服务状态"""
        if service_name not in self.services:
            return {"error": "服务不存在"}
        
        status_info = {
            "name": service_name,
            "status": self.service_status[service_name].value,
            "restart_count": self.restart_counts[service_name],
            "last_restart_time": self.last_restart_times[service_name],
            "config": {
                "auto_restart": self.services[service_name].auto_restart,
                "max_restart_attempts": self.services[service_name].max_restart_attempts,
                "cpu_threshold": self.services[service_name].cpu_threshold,
                "memory_threshold_mb": self.services[service_name].memory_threshold_mb
            }
        }
        
        # 添加进程信息
        if service_name in self.processes:
            process = self.processes[service_name]
            status_info["process"] = {
                "pid": process.pid,
                "running": process.poll() is None
            }
        
        # 添加健康监控信息
        if service_name in self.monitors:
            monitor = self.monitors[service_name]
            current_metrics = monitor.get_current_metrics()
            if current_metrics:
                status_info["health"] = {
                    "status": current_metrics.status.value,
                    "cpu_percent": current_metrics.cpu_percent,
                    "memory_mb": current_metrics.memory_mb,
                    "uptime_hours": current_metrics.uptime_seconds / 3600,
                    "issues": current_metrics.issues
                }
        
        return status_info
    
    def get_all_status(self) -> Dict[str, Any]:
        """获取所有服务状态"""
        return {
            "services": {name: self.get_service_status(name) for name in self.services},
            "manager_stats": self.stats,
            "manager_status": {
                "running": self.is_running,
                "services_count": len(self.services),
                "running_services": sum(1 for status in self.service_status.values() 
                                      if status == ServiceStatus.RUNNING)
            }
        }


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="MarketPrism 服务管理器")
    parser.add_argument("--config", default="config/services.yaml", help="配置文件路径")
    parser.add_argument("--action", choices=["start", "stop", "restart", "status"], 
                       default="start", help="操作类型")
    parser.add_argument("--service", help="指定服务名称")
    
    args = parser.parse_args()
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    manager = ServiceManager(args.config)
    manager.load_config()
    
    try:
        if args.action == "start":
            if args.service:
                success = await manager.start_service(args.service)
                print(f"启动服务 {args.service}: {'成功' if success else '失败'}")
            else:
                await manager.start_all_services()
                print("所有服务启动完成")
                
                # 保持运行，监控服务
                print("服务管理器运行中，按 Ctrl+C 停止...")
                try:
                    while True:
                        await asyncio.sleep(60)
                        # 定期输出状态
                        status = manager.get_all_status()
                        running_count = status["manager_status"]["running_services"]
                        total_count = status["manager_status"]["services_count"]
                        print(f"服务状态: {running_count}/{total_count} 运行中")
                except KeyboardInterrupt:
                    print("\n收到停止信号，正在停止所有服务...")
                    await manager.stop_all_services()
        
        elif args.action == "stop":
            if args.service:
                success = await manager.stop_service(args.service)
                print(f"停止服务 {args.service}: {'成功' if success else '失败'}")
            else:
                await manager.stop_all_services()
                print("所有服务已停止")
        
        elif args.action == "restart":
            if args.service:
                success = await manager.restart_service(args.service)
                print(f"重启服务 {args.service}: {'成功' if success else '失败'}")
            else:
                await manager.stop_all_services()
                await asyncio.sleep(5)
                await manager.start_all_services()
                print("所有服务已重启")
        
        elif args.action == "status":
            status = manager.get_all_status()
            print(json.dumps(status, indent=2, ensure_ascii=False, default=str))
    
    except Exception as e:
        logger.error("服务管理器异常", error=str(e))
        return 1
    
    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
