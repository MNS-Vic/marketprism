#!/usr/bin/env python3
"""
MarketPrism 基础设施服务启动脚本

解决基础设施服务未启动的问题：
- Redis
- ClickHouse  
- NATS

支持Docker和本地部署两种方式
"""

import asyncio
import subprocess
import sys
import time
import yaml
import json
import psutil
from pathlib import Path
from typing import Dict, List, Optional, Any
import docker
import aioredis
import aiohttp
import nats

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

class InfrastructureManager:
    """基础设施管理器"""
    
    def __init__(self):
        self.docker_client = None
        self.services_status = {}
        
        # 服务配置
        self.services = {
            'redis': {
                'name': 'redis',
                'port': 6379,
                'docker_image': 'redis:7-alpine',
                'docker_ports': {'6379/tcp': 6379},
                'health_check': self._check_redis_health,
                'start_local': self._start_redis_local,
                'stop_local': self._stop_redis_local
            },
            'clickhouse': {
                'name': 'clickhouse',
                'port': 8123,
                'docker_image': 'clickhouse/clickhouse-server:latest',
                'docker_ports': {'8123/tcp': 8123, '9000/tcp': 9000},
                'docker_volumes': {
                    str(PROJECT_ROOT / 'config' / 'clickhouse-cold'): {'bind': '/etc/clickhouse-server', 'mode': 'rw'}
                },
                'health_check': self._check_clickhouse_health,
                'start_local': self._start_clickhouse_local,
                'stop_local': self._stop_clickhouse_local
            },
            'nats': {
                'name': 'nats',
                'port': 4222,
                'docker_image': 'nats:2-alpine',
                'docker_ports': {'4222/tcp': 4222, '8222/tcp': 8222},
                'docker_command': ['-js', '-m', '8222'],
                'health_check': self._check_nats_health,
                'start_local': self._start_nats_local,
                'stop_local': self._stop_nats_local
            }
        }
    
    async def check_docker_availability(self) -> bool:
        """检查Docker是否可用"""
        try:
            import docker
            self.docker_client = docker.from_env()
            self.docker_client.ping()
            print("✅ Docker可用")
            return True
        except Exception as e:
            print(f"❌ Docker不可用: {e}")
            return False
    
    async def check_services_status(self) -> Dict[str, Dict[str, Any]]:
        """检查所有服务状态"""
        print("🔍 检查基础设施服务状态...")
        
        status = {}
        for service_name, service_config in self.services.items():
            try:
                is_healthy = await service_config['health_check']()
                status[service_name] = {
                    'running': is_healthy,
                    'port': service_config['port'],
                    'docker_available': self.docker_client is not None,
                    'health_status': 'healthy' if is_healthy else 'unhealthy'
                }
                
                if is_healthy:
                    print(f"   ✅ {service_name}: 运行正常 (端口 {service_config['port']})")
                else:
                    print(f"   ❌ {service_name}: 未运行或不健康 (端口 {service_config['port']})")
                    
            except Exception as e:
                status[service_name] = {
                    'running': False,
                    'port': service_config['port'],
                    'error': str(e),
                    'health_status': 'error'
                }
                print(f"   ❌ {service_name}: 检查失败 - {e}")
        
        return status
    
    async def _check_redis_health(self) -> bool:
        """检查Redis健康状态"""
        try:
            redis_client = await aioredis.create_redis_pool('redis://localhost:6379')
            await redis_client.ping()
            redis_client.close()
            await redis_client.wait_closed()
            return True
        except Exception:
            return False
    
    async def _check_clickhouse_health(self) -> bool:
        """检查ClickHouse健康状态"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('http://localhost:8123/ping', timeout=aiohttp.ClientTimeout(total=5)) as response:
                    return response.status == 200
        except Exception:
            return False
    
    async def _check_nats_health(self) -> bool:
        """检查NATS健康状态"""
        try:
            nc = await nats.connect("nats://localhost:4222", connect_timeout=3)
            await nc.close()
            return True
        except Exception:
            return False
    
    async def start_service_docker(self, service_name: str) -> bool:
        """使用Docker启动服务"""
        if not self.docker_client:
            return False
        
        service_config = self.services[service_name]
        
        try:
            # 检查容器是否已存在
            try:
                container = self.docker_client.containers.get(f"marketprism-{service_name}")
                if container.status == 'running':
                    print(f"   ✅ {service_name} Docker容器已在运行")
                    return True
                else:
                    print(f"   🔄 启动现有的{service_name} Docker容器")
                    container.start()
                    
            except docker.errors.NotFound:
                print(f"   🚀 创建并启动{service_name} Docker容器")
                
                # 准备容器参数
                container_args = {
                    'image': service_config['docker_image'],
                    'name': f"marketprism-{service_name}",
                    'ports': service_config['docker_ports'],
                    'detach': True,
                    'restart_policy': {"Name": "unless-stopped"}
                }
                
                # 添加卷挂载（如果有）
                if 'docker_volumes' in service_config:
                    container_args['volumes'] = service_config['docker_volumes']
                
                # 添加启动命令（如果有）
                if 'docker_command' in service_config:
                    container_args['command'] = service_config['docker_command']
                
                # 特殊配置处理
                if service_name == 'clickhouse':
                    # ClickHouse特殊配置
                    container_args['environment'] = {
                        'CLICKHOUSE_DB': 'marketprism',
                        'CLICKHOUSE_USER': 'default',
                        'CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT': '1'
                    }
                
                container = self.docker_client.containers.run(**container_args)
            
            # 等待服务健康
            print(f"   ⏳ 等待{service_name}服务启动...")
            for i in range(30):  # 等待最多30秒
                await asyncio.sleep(1)
                if await service_config['health_check']():
                    print(f"   ✅ {service_name} Docker服务启动成功")
                    return True
                    
            print(f"   ❌ {service_name} Docker服务启动超时")
            return False
            
        except Exception as e:
            print(f"   ❌ {service_name} Docker启动失败: {e}")
            return False
    
    async def start_service_local(self, service_name: str) -> bool:
        """本地启动服务"""
        service_config = self.services[service_name]
        
        try:
            print(f"   🚀 本地启动{service_name}服务...")
            success = await service_config['start_local']()
            
            if success:
                # 等待服务健康
                print(f"   ⏳ 等待{service_name}服务启动...")
                for i in range(20):  # 等待最多20秒
                    await asyncio.sleep(1)
                    if await service_config['health_check']():
                        print(f"   ✅ {service_name} 本地服务启动成功")
                        return True
                        
                print(f"   ❌ {service_name} 本地服务启动超时")
                return False
            else:
                print(f"   ❌ {service_name} 本地启动失败")
                return False
                
        except Exception as e:
            print(f"   ❌ {service_name} 本地启动失败: {e}")
            return False
    
    async def _start_redis_local(self) -> bool:
        """本地启动Redis"""
        try:
            # 检查Redis是否已安装
            result = subprocess.run(['which', 'redis-server'], capture_output=True)
            if result.returncode != 0:
                print("   ❌ Redis未安装，请安装Redis: brew install redis (macOS) 或 apt install redis-server (Ubuntu)")
                return False
            
            # 启动Redis
            subprocess.Popen(['redis-server', '--daemonize', 'yes'])
            return True
            
        except Exception as e:
            print(f"   ❌ Redis本地启动失败: {e}")
            return False
    
    async def _start_clickhouse_local(self) -> bool:
        """本地启动ClickHouse"""
        try:
            # 检查ClickHouse是否已安装
            result = subprocess.run(['which', 'clickhouse-server'], capture_output=True)
            if result.returncode != 0:
                print("   ❌ ClickHouse未安装，建议使用Docker方式")
                return False
            
            # 启动ClickHouse
            subprocess.Popen(['clickhouse-server', '--daemon'])
            return True
            
        except Exception as e:
            print(f"   ❌ ClickHouse本地启动失败: {e}")
            return False
    
    async def _start_nats_local(self) -> bool:
        """本地启动NATS"""
        try:
            # 检查NATS是否已安装
            result = subprocess.run(['which', 'nats-server'], capture_output=True)
            if result.returncode != 0:
                print("   ❌ NATS未安装，建议使用Docker方式")
                return False
            
            # 启动NATS
            subprocess.Popen(['nats-server', '-js', '-D'])
            return True
            
        except Exception as e:
            print(f"   ❌ NATS本地启动失败: {e}")
            return False
    
    async def _stop_redis_local(self) -> bool:
        """停止本地Redis"""
        try:
            subprocess.run(['redis-cli', 'shutdown'], check=False)
            return True
        except Exception:
            return False
    
    async def _stop_clickhouse_local(self) -> bool:
        """停止本地ClickHouse"""
        try:
            subprocess.run(['pkill', '-f', 'clickhouse-server'], check=False)
            return True
        except Exception:
            return False
    
    async def _stop_nats_local(self) -> bool:
        """停止本地NATS"""
        try:
            subprocess.run(['pkill', '-f', 'nats-server'], check=False)
            return True
        except Exception:
            return False
    
    async def start_all_services(self, use_docker: bool = True) -> Dict[str, bool]:
        """启动所有基础设施服务"""
        print(f"🚀 启动所有基础设施服务 ({'Docker模式' if use_docker else '本地模式'})")
        
        results = {}
        
        for service_name in self.services.keys():
            print(f"\n📦 启动{service_name}服务...")
            
            # 先检查服务是否已运行
            if await self.services[service_name]['health_check']():
                print(f"   ✅ {service_name}已在运行，跳过启动")
                results[service_name] = True
                continue
            
            # 启动服务
            if use_docker:
                success = await self.start_service_docker(service_name)
            else:
                success = await self.start_service_local(service_name)
            
            results[service_name] = success
        
        return results
    
    async def stop_all_services(self, use_docker: bool = True) -> Dict[str, bool]:
        """停止所有基础设施服务"""
        print(f"🛑 停止所有基础设施服务 ({'Docker模式' if use_docker else '本地模式'})")
        
        results = {}
        
        for service_name in self.services.keys():
            print(f"\n🔻 停止{service_name}服务...")
            
            try:
                if use_docker and self.docker_client:
                    # Docker方式停止
                    try:
                        container = self.docker_client.containers.get(f"marketprism-{service_name}")
                        container.stop()
                        print(f"   ✅ {service_name} Docker容器已停止")
                        results[service_name] = True
                    except docker.errors.NotFound:
                        print(f"   ⚠️ {service_name} Docker容器不存在")
                        results[service_name] = True
                else:
                    # 本地方式停止
                    success = await self.services[service_name]['stop_local']()
                    results[service_name] = success
                    if success:
                        print(f"   ✅ {service_name} 本地服务已停止")
                    else:
                        print(f"   ❌ {service_name} 本地服务停止失败")
                        
            except Exception as e:
                print(f"   ❌ 停止{service_name}失败: {e}")
                results[service_name] = False
        
        return results
    
    async def get_services_info(self) -> Dict[str, Any]:
        """获取服务信息"""
        status = await self.check_services_status()
        
        info = {
            'docker_available': self.docker_client is not None,
            'services': status,
            'summary': {
                'total': len(self.services),
                'running': sum(1 for s in status.values() if s.get('running', False)),
                'healthy': sum(1 for s in status.values() if s.get('health_status') == 'healthy')
            }
        }
        
        return info

async def main():
    """主函数"""
    print("🔧 MarketPrism 基础设施服务管理器")
    print("="*60)
    
    manager = InfrastructureManager()
    
    # 检查Docker可用性
    docker_available = await manager.check_docker_availability()
    
    # 检查当前服务状态
    status = await manager.check_services_status()
    
    # 统计运行状况
    total_services = len(status)
    running_services = sum(1 for s in status.values() if s.get('running', False))
    
    print(f"\n📊 服务状态统计: {running_services}/{total_services} 运行中")
    
    if running_services == total_services:
        print("✅ 所有基础设施服务都在运行，无需启动")
        return
    
    # 询问启动方式
    print(f"\n🤔 检测到 {total_services - running_services} 个服务未运行")
    
    if docker_available:
        response = input("选择启动方式:\n1. Docker (推荐)\n2. 本地安装\n3. 仅检查状态\n请输入选择 (1/2/3): ").strip()
        
        if response == "1":
            use_docker = True
        elif response == "2":
            use_docker = False
        elif response == "3":
            print("\n📋 服务详细状态:")
            for service_name, service_status in status.items():
                status_icon = "✅" if service_status.get('running') else "❌"
                print(f"   {status_icon} {service_name}: {service_status.get('health_status', 'unknown')}")
            return
        else:
            print("❌ 无效选择，退出")
            return
    else:
        print("⚠️ Docker不可用，将使用本地启动方式")
        use_docker = False
    
    # 启动服务
    print(f"\n🚀 开始启动基础设施服务...")
    start_results = await manager.start_all_services(use_docker)
    
    # 报告启动结果
    print("\n📊 启动结果:")
    print("="*60)
    
    success_count = 0
    for service_name, success in start_results.items():
        status_icon = "✅" if success else "❌"
        print(f"   {status_icon} {service_name}: {'启动成功' if success else '启动失败'}")
        if success:
            success_count += 1
    
    print(f"\n🎯 总结: {success_count}/{len(start_results)} 服务启动成功")
    
    if success_count == len(start_results):
        print("🎉 所有基础设施服务启动成功!")
        print("\n🔗 服务连接信息:")
        print("   Redis:      redis://localhost:6379")
        print("   ClickHouse: http://localhost:8123")
        print("   NATS:       nats://localhost:4222")
        print("\n✨ 现在可以运行TDD测试:")
        print("   python scripts/fixed_tdd_tests.py")
    else:
        print("⚠️ 部分服务启动失败，请检查错误信息并手动处理")
    
    # 最终状态检查
    print("\n🔍 最终服务状态检查...")
    final_status = await manager.check_services_status()
    
    all_healthy = all(s.get('running', False) for s in final_status.values())
    
    if all_healthy:
        print("✅ 所有服务健康检查通过!")
    else:
        print("❌ 部分服务健康检查失败")
        for service_name, service_status in final_status.items():
            if not service_status.get('running', False):
                print(f"   ❌ {service_name}: {service_status.get('health_status', 'unknown')}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️ 用户中断操作")
    except Exception as e:
        print(f"\n❌ 执行失败: {e}")
        import traceback
        traceback.print_exc()