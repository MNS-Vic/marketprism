#!/usr/bin/env python3
"""
监控告警服务健康检查脚本
"""

import sys
import asyncio
import aiohttp
import json
from pathlib import Path

async def check_service_health(host='localhost', port=8082):
    """检查服务健康状态"""
    base_url = f"http://{host}:{port}"
    
    async with aiohttp.ClientSession() as session:
        try:
            # 健康检查
            async with session.get(f"{base_url}/health") as resp:
                if resp.status == 200:
                    health_data = await resp.json()
                    print("✅ 服务健康检查通过")
                    print(f"   状态: {health_data.get('status')}")
                    print(f"   运行时间: {health_data.get('uptime_seconds', 0):.2f}秒")
                    
                    components = health_data.get('components', {})
                    for component, status in components.items():
                        status_icon = "✅" if status else "❌"
                        print(f"   {status_icon} {component}: {'健康' if status else '异常'}")
                else:
                    print(f"❌ 健康检查失败: HTTP {resp.status}")
                    
        except aiohttp.ClientConnectorError:
            print(f"❌ 无法连接到服务 {base_url}")
            return False
        except Exception as e:
            print(f"❌ 健康检查异常: {e}")
            return False
    
    try:
        # 就绪检查
        async with session.get(f"{base_url}/ready") as resp:
            if resp.status == 200:
                ready_data = await resp.json()
                print(f"✅ 服务就绪状态: {'就绪' if ready_data.get('ready') else '未就绪'}")
            else:
                print(f"❌ 就绪检查失败: HTTP {resp.status}")
                
    except Exception as e:
        print(f"⚠️ 就绪检查异常: {e}")
    
    try:
        # 检查告警API
        async with session.get(f"{base_url}/api/v1/alerts") as resp:
            if resp.status == 200:
                alerts_data = await resp.json()
                alert_count = alerts_data.get('total', 0)
                print(f"✅ 告警API正常，当前活跃告警: {alert_count}个")
            else:
                print(f"❌ 告警API异常: HTTP {resp.status}")
                
    except Exception as e:
        print(f"⚠️ 告警API检查异常: {e}")
    
    try:
        # 检查指标端点
        async with session.get(f"{base_url}/metrics") as resp:
            if resp.status == 200:
                print("✅ Prometheus指标端点正常")
            else:
                print(f"❌ 指标端点异常: HTTP {resp.status}")
                
    except Exception as e:
        print(f"⚠️ 指标端点检查异常: {e}")
    
    return True

async def main():
    """主函数"""
    print("MarketPrism 监控告警服务健康检查")
    print("=" * 50)
    
    # 检查默认端口
    await check_service_health()
    
    print("\n健康检查完成!")

if __name__ == '__main__':
    asyncio.run(main())
