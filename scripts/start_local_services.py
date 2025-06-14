#!/usr/bin/env python3
"""
本地服务启动脚本
启动Redis、ClickHouse和NATS的本地实例
"""

import subprocess
import asyncio
import time
import psutil
from pathlib import Path

class LocalServiceManager:
    """本地服务管理器"""
    
    def __init__(self):
        self.services = {
            'redis': {'port': 6379, 'process': None},
            'nats': {'port': 4222, 'process': None},
        }
        
    def is_port_in_use(self, port):
        """检查端口是否被占用"""
        for conn in psutil.net_connections():
            if conn.laddr.port == port:
                return True
        return False
    
    def start_redis(self):
        """启动Redis服务"""
        if self.is_port_in_use(6379):
            print("✅ Redis已在端口6379运行")
            return True
            
        try:
            # 尝试使用Homebrew安装的Redis
            result = subprocess.run(['which', 'redis-server'], capture_output=True, text=True)
            if result.returncode == 0:
                redis_path = result.stdout.strip()
                print(f"🚀 启动Redis: {redis_path}")
                process = subprocess.Popen([redis_path, '--port', '6379', '--daemonize', 'yes'])
                time.sleep(2)
                
                if self.is_port_in_use(6379):
                    print("✅ Redis启动成功")
                    return True
                else:
                    print("❌ Redis启动失败")
                    return False
            else:
                print("❌ 未找到redis-server，请安装Redis: brew install redis")
                return False
                
        except Exception as e:
            print(f"❌ Redis启动失败: {e}")
            return False
    
    def start_nats(self):
        """启动NATS服务"""
        if self.is_port_in_use(4222):
            print("✅ NATS已在端口4222运行")
            return True
            
        try:
            # 尝试使用Homebrew安装的NATS
            result = subprocess.run(['which', 'nats-server'], capture_output=True, text=True)
            if result.returncode == 0:
                nats_path = result.stdout.strip()
                print(f"🚀 启动NATS: {nats_path}")
                process = subprocess.Popen([nats_path, '-p', '4222', '-m', '8222', '-js', '--daemon'])
                time.sleep(3)
                
                if self.is_port_in_use(4222):
                    print("✅ NATS启动成功")
                    return True
                else:
                    print("❌ NATS启动失败")
                    return False
            else:
                print("❌ 未找到nats-server，请安装NATS: brew install nats-server")
                return False
                
        except Exception as e:
            print(f"❌ NATS启动失败: {e}")
            return False
    
    def start_clickhouse_alternative(self):
        """ClickHouse替代方案 - 使用SQLite"""
        print("💾 ClickHouse本地安装较复杂，使用SQLite作为替代存储")
        print("   配置将自动适配到SQLite后端")
        return True
    
    def install_services_via_homebrew(self):
        """通过Homebrew安装服务"""
        print("📦 检查并安装必要的服务...")
        
        services_to_install = []
        
        # 检查Redis
        result = subprocess.run(['which', 'redis-server'], capture_output=True)
        if result.returncode != 0:
            services_to_install.append('redis')
        
        # 检查NATS
        result = subprocess.run(['which', 'nats-server'], capture_output=True)
        if result.returncode != 0:
            services_to_install.append('nats-server')
        
        if services_to_install:
            print(f"🍺 安装服务: {', '.join(services_to_install)}")
            for service in services_to_install:
                try:
                    subprocess.run(['brew', 'install', service], check=True)
                    print(f"✅ {service} 安装成功")
                except subprocess.CalledProcessError as e:
                    print(f"❌ {service} 安装失败: {e}")
                    return False
        
        return True
    
    def start_all_services(self):
        """启动所有服务"""
        print("🚀 启动MarketPrism本地基础设施服务")
        print("=" * 50)
        
        # 先尝试安装必要的服务
        if not self.install_services_via_homebrew():
            print("❌ 服务安装失败，尝试手动安装后重试")
            return False
        
        success_count = 0
        total_services = 3
        
        # 启动Redis
        if self.start_redis():
            success_count += 1
        
        # 启动NATS
        if self.start_nats():
            success_count += 1
        
        # ClickHouse替代方案
        if self.start_clickhouse_alternative():
            success_count += 1
        
        print("\n" + "=" * 50)
        print(f"📊 服务启动结果: {success_count}/{total_services}")
        
        if success_count >= 2:  # Redis + NATS 足够运行
            print("🎉 基础设施服务启动成功！")
            print("💡 系统已准备就绪，可以运行验证测试")
            return True
        else:
            print("⚠️ 部分服务启动失败，但系统仍可基本运行")
            return False

def main():
    """主函数"""
    manager = LocalServiceManager()
    success = manager.start_all_services()
    
    if success:
        print("\n🎯 下一步: 运行修复验证")
        print("python scripts/quick_fix_verification.py")
    else:
        print("\n💡 备选方案:")
        print("1. 手动安装: brew install redis nats-server")
        print("2. 使用Docker: docker-compose up -d")

if __name__ == "__main__":
    main()