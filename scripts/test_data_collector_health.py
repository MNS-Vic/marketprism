#!/usr/bin/env python3
import requests
import time
import subprocess
import signal
import os

def test_data_collector_health():
    print("🏥 测试 Data Collector 健康检查...")
    
    try:
        # 等待服务启动
        time.sleep(3)
        
        # 健康检查
        response = requests.get("http://localhost:8081/health", timeout=5)
        print(f"📊 健康检查状态码: {response.status_code}")
        
        if response.status_code == 200:
            health_data = response.json()
            print(f"✅ 健康检查成功")
            print(f"📈 服务状态: {health_data.get('status', 'unknown')}")
            print(f"⏰ 运行时间: {health_data.get('uptime_seconds', 0)} 秒")
            
            # 检查端口监听
            port_check = subprocess.run(
                ["lsof", "-i", ":8081"],
                capture_output=True,
                text=True
            )
            
            if port_check.returncode == 0:
                print("✅ 端口 8081 正在监听")
                print("✅ Data Collector 启动测试通过")
                return True
            else:
                print("❌ 端口 8081 未监听")
                return False
        else:
            print(f"❌ 健康检查失败，状态码: {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ 健康检查请求失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

if __name__ == "__main__":
    success = test_data_collector_health()
    exit(0 if success else 1)