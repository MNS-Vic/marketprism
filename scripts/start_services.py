#!/usr/bin/env python3
"""
MarketPrism 微服务启动脚本
用于启动和管理所有微服务
"""

import asyncio
import subprocess
import sys
import time
import signal
import os
from pathlib import Path
from typing import List, Dict, Any
import yaml
import aiohttp

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class ServiceManager:
    """服务管理器"""
    
    def __init__(self):
        self.services = {}
        self.running = False
        
    def load_config(self) -> Dict[str, Any]:
        """加载服务配置"""
        config_path = project_root / "config" / "services.yaml"
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
            
    async def start_service(self, service_name: str, service_config: Dict[str, Any]):
        """启动单个服务"""
        try:
            service_path = project_root / "services" / service_name / "main.py"
            
            if not service_path.exists():
                print(f"❌ Service script not found: {service_path}")
                return None
                
            # 启动服务进程
            process = subprocess.Popen([
                sys.executable, str(service_path)
            ], cwd=str(project_root))
            
            self.services[service_name] = {
                "process": process,
                "config": service_config,
                "start_time": time.time()
            }
            
            print(f"🚀 Started {service_name} (PID: {process.pid})")
            
            # 等待服务启动
            await asyncio.sleep(2)
            
            # 检查服务健康状态
            if await self.check_service_health(service_name, service_config):
                print(f"✅ {service_name} is healthy")
            else:
                print(f"⚠️  {service_name} health check failed")
                
            return process
            
        except Exception as e:
            print(f"❌ Failed to start {service_name}: {e}")
            return None
            
    async def check_service_health(self, service_name: str, service_config: Dict[str, Any]) -> bool:
        """检查服务健康状态"""
        try:
            port = service_config.get('port', 8080)
            health_url = f"http://localhost:{port}/health"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        health_data = await response.json()
                        return health_data.get('status') == 'healthy'
                    return False
                    
        except Exception:
            return False
            
    async def stop_service(self, service_name: str):
        """停止单个服务"""
        if service_name in self.services:
            service_info = self.services[service_name]
            process = service_info["process"]
            
            try:
                # 发送SIGTERM信号
                process.terminate()
                
                # 等待进程结束
                try:
                    process.wait(timeout=10)
                    print(f"🛑 Stopped {service_name}")
                except subprocess.TimeoutExpired:
                    # 强制杀死进程
                    process.kill()
                    print(f"💀 Force killed {service_name}")
                    
            except Exception as e:
                print(f"❌ Failed to stop {service_name}: {e}")
                
            del self.services[service_name]
            
    async def start_all_services(self):
        """启动所有服务"""
        config = self.load_config()
        
        # 定义服务启动顺序（基础设施服务优先）
        service_order = [
            "message-broker-service",
            "monitoring-service", 
            "data-storage-service",
            "scheduler-service",
            "market-data-collector",
            "api-gateway-service"
        ]
        
        print("🚀 Starting MarketPrism microservices...")
        print("=" * 50)
        
        for service_name in service_order:
            if service_name in config:
                service_config = config[service_name]
                await self.start_service(service_name, service_config)
                
                # 服务间启动间隔
                await asyncio.sleep(3)
            else:
                print(f"⚠️  No configuration found for {service_name}")
                
        print("=" * 50)
        print(f"✅ Started {len(self.services)} services")
        
        # 显示服务状态
        await self.show_service_status()
        
    async def stop_all_services(self):
        """停止所有服务"""
        print("🛑 Stopping all services...")
        
        # 反向顺序停止服务
        service_names = list(self.services.keys())
        service_names.reverse()
        
        for service_name in service_names:
            await self.stop_service(service_name)
            
        print("✅ All services stopped")
        
    async def show_service_status(self):
        """显示服务状态"""
        print("\n📊 Service Status:")
        print("-" * 60)
        print(f"{'Service':<25} {'Port':<8} {'Status':<10} {'PID':<8}")
        print("-" * 60)
        
        config = self.load_config()
        
        for service_name, service_info in self.services.items():
            process = service_info["process"]
            service_config = service_info["config"]
            port = service_config.get('port', 'N/A')
            
            if process.poll() is None:
                status = "Running"
                pid = process.pid
            else:
                status = "Stopped"
                pid = "N/A"
                
            print(f"{service_name:<25} {port:<8} {status:<10} {pid:<8}")
            
        print("-" * 60)
        
    async def monitor_services(self):
        """监控服务状态"""
        self.running = True
        
        while self.running:
            try:
                # 检查所有服务状态
                for service_name, service_info in list(self.services.items()):
                    process = service_info["process"]
                    
                    if process.poll() is not None:
                        print(f"⚠️  Service {service_name} has stopped unexpectedly")
                        
                        # 可以在这里实现自动重启逻辑
                        # await self.restart_service(service_name)
                        
                await asyncio.sleep(30)  # 每30秒检查一次
                
            except Exception as e:
                print(f"❌ Monitor error: {e}")
                await asyncio.sleep(60)
                
    async def restart_service(self, service_name: str):
        """重启服务"""
        print(f"🔄 Restarting {service_name}...")
        
        if service_name in self.services:
            service_config = self.services[service_name]["config"]
            await self.stop_service(service_name)
            await asyncio.sleep(2)
            await self.start_service(service_name, service_config)
            
    def signal_handler(self, signum, frame):
        """信号处理器"""
        print(f"\n🛑 Received signal {signum}, shutting down...")
        self.running = False
        asyncio.create_task(self.stop_all_services())


async def main():
    """主函数"""
    manager = ServiceManager()
    
    # 设置信号处理
    signal.signal(signal.SIGINT, manager.signal_handler)
    signal.signal(signal.SIGTERM, manager.signal_handler)
    
    try:
        # 启动所有服务
        await manager.start_all_services()
        
        # 开始监控
        print("\n🔍 Starting service monitoring...")
        print("Press Ctrl+C to stop all services")
        
        await manager.monitor_services()
        
    except KeyboardInterrupt:
        print("\n🛑 Keyboard interrupt received")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await manager.stop_all_services()


if __name__ == "__main__":
    asyncio.run(main())