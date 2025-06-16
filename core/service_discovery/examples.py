"""
MarketPrism 服务发现使用示例
展示如何在不同场景下使用服务发现功能
"""

import asyncio
import aiohttp
from typing import Dict, Any
import logging

from .discovery_client import (
    ServiceDiscoveryClient, 
    register_service, 
    discover_service,
    get_service_url,
    wait_for_service
)
from .registry import ServiceStatus

logger = logging.getLogger(__name__)


async def example_basic_usage():
    """基础使用示例"""
    print("=== 基础服务发现使用示例 ===")
    
    # 1. 创建服务发现客户端
    config = {
        'backend': 'memory',  # 使用内存后端进行演示
        'health_check_interval': 10,
        'instance_ttl': 60
    }
    
    client = ServiceDiscoveryClient(config)
    await client.initialize()
    
    try:
        # 2. 注册当前服务
        my_instance = await client.register_myself(
            service_name="example-service",
            host="localhost",
            port=8080,
            metadata={"version": "1.0.0", "environment": "development"},
            tags=["api", "web"]
        )
        print(f"✅ 服务注册成功: {my_instance.service_name}#{my_instance.instance_id}")
        
        # 3. 发现其他服务
        instances = await client.discover("api-gateway-service")
        print(f"🔍 发现 api-gateway-service 实例: {len(instances)}个")
        
        # 4. 获取服务URL
        gateway_url = await client.get_service_url("api-gateway-service")
        if gateway_url:
            print(f"🌐 API网关URL: {gateway_url}")
        else:
            print("❌ API网关服务未找到")
        
        # 5. 更新服务状态
        await client.update_my_status(ServiceStatus.HEALTHY)
        print("✅ 服务状态更新为健康")
        
        # 6. 列出所有服务
        all_services = await client.list_all_services()
        print(f"📋 所有服务: {list(all_services.keys())}")
        
    finally:
        # 7. 清理
        await client.deregister_myself()
        await client.shutdown()
        print("🧹 服务发现客户端关闭")


async def example_microservice_integration():
    """微服务集成示例"""
    print("\n=== 微服务集成示例 ===")
    
    # 模拟API网关服务
    async def api_gateway_service():
        config = {'backend': 'memory'}
        client = ServiceDiscoveryClient(config)
        await client.initialize()
        
        try:
            # 注册API网关
            await client.register_myself(
                service_name="api-gateway-service",
                host="localhost",
                port=8080,
                metadata={"role": "gateway", "public": True}
            )
            
            # 等待数据采集服务可用
            data_collector = await client.wait_for_service("data-collector", timeout=30)
            if data_collector:
                print(f"✅ API网关发现数据采集服务: {data_collector.base_url}")
                
                # 模拟代理请求
                async with aiohttp.ClientSession() as session:
                    try:
                        async with session.get(f"{data_collector.base_url}/health") as response:
                            if response.status == 200:
                                print("✅ 数据采集服务健康检查通过")
                            else:
                                print(f"❌ 数据采集服务健康检查失败: {response.status}")
                    except Exception as e:
                        print(f"❌ 连接数据采集服务失败: {e}")
            else:
                print("❌ 等待数据采集服务超时")
                
        finally:
            await client.shutdown()
    
    # 模拟数据采集服务
    async def data_collector_service():
        await asyncio.sleep(2)  # 模拟启动延迟
        
        config = {'backend': 'memory'}
        client = ServiceDiscoveryClient(config)
        await client.initialize()
        
        try:
            # 注册数据采集服务
            await client.register_myself(
                service_name="data-collector",
                host="localhost",
                port=8081,
                metadata={"exchanges": ["binance", "okx"], "role": "collector"}
            )
            
            # 模拟服务运行
            await asyncio.sleep(5)
            
        finally:
            await client.shutdown()
    
    # 并发运行两个服务
    await asyncio.gather(
        api_gateway_service(),
        data_collector_service()
    )


async def example_load_balancing():
    """负载均衡示例"""
    print("\n=== 负载均衡示例 ===")
    
    config = {'backend': 'memory'}
    client = ServiceDiscoveryClient(config)
    await client.initialize()
    
    try:
        # 注册多个数据存储服务实例
        instances = []
        for i in range(3):
            instance = await client.registry.register_service(
                service_name="data-storage-service",
                host="localhost",
                port=8082 + i,
                metadata={"instance": f"storage-{i}", "weight": 100 - i * 10}
            )
            instances.append(instance)
            print(f"✅ 注册存储实例 {i}: {instance.base_url}")
        
        # 模拟负载均衡请求
        print("\n🔄 负载均衡测试:")
        for i in range(10):
            instance = await client.get_service("data-storage-service")
            if instance:
                print(f"请求 {i+1}: 路由到 {instance.base_url}")
            else:
                print(f"请求 {i+1}: 无可用实例")
        
        # 模拟实例故障
        print(f"\n💥 模拟实例故障: {instances[0].base_url}")
        await client.registry.update_service_status(
            "data-storage-service",
            instances[0].instance_id,
            ServiceStatus.UNHEALTHY
        )
        
        # 再次测试负载均衡
        print("\n🔄 故障后负载均衡测试:")
        for i in range(5):
            instance = await client.get_service("data-storage-service")
            if instance:
                print(f"请求 {i+1}: 路由到 {instance.base_url}")
            else:
                print(f"请求 {i+1}: 无可用实例")
                
    finally:
        await client.shutdown()


async def example_event_handling():
    """事件处理示例"""
    print("\n=== 事件处理示例 ===")
    
    # 事件处理器
    async def on_service_registered(instance):
        print(f"🎉 服务注册事件: {instance.service_name}#{instance.instance_id}")
    
    async def on_service_deregistered(instance):
        print(f"👋 服务注销事件: {instance.service_name}#{instance.instance_id}")
    
    async def on_service_status_changed(data):
        print(f"🔄 服务状态变更: {data['service_name']} {data['old_status']} -> {data['new_status']}")
    
    config = {'backend': 'memory'}
    client = ServiceDiscoveryClient(config)
    await client.initialize()
    
    try:
        # 添加事件处理器
        client.add_event_handler('service_registered', on_service_registered)
        client.add_event_handler('service_deregistered', on_service_deregistered)
        client.add_event_handler('service_status_changed', on_service_status_changed)
        
        # 注册服务（触发注册事件）
        instance = await client.register_myself(
            service_name="event-test-service",
            host="localhost",
            port=9000
        )
        
        # 更新状态（触发状态变更事件）
        await client.update_my_status(ServiceStatus.HEALTHY)
        await asyncio.sleep(1)
        await client.update_my_status(ServiceStatus.MAINTENANCE)
        
        # 注销服务（触发注销事件）
        await client.deregister_myself()
        
    finally:
        await client.shutdown()


async def example_convenient_functions():
    """便捷函数使用示例"""
    print("\n=== 便捷函数使用示例 ===")
    
    config = {'backend': 'memory'}
    
    try:
        # 使用便捷函数注册服务
        instance = await register_service(
            service_name="convenient-service",
            host="localhost",
            port=7000,
            metadata={"type": "example"},
            config=config
        )
        print(f"✅ 便捷注册: {instance.service_name}")
        
        # 发现服务
        instances = await discover_service("convenient-service", config)
        print(f"🔍 便捷发现: 找到 {len(instances)} 个实例")
        
        # 获取服务URL
        url = await get_service_url("convenient-service", config)
        print(f"🌐 便捷URL获取: {url}")
        
        # 等待服务
        waited_instance = await wait_for_service("convenient-service", timeout=10, config=config)
        if waited_instance:
            print(f"⏰ 便捷等待: 服务已可用 {waited_instance.base_url}")
        
    finally:
        # 清理全局客户端
        from .discovery_client import shutdown_discovery_client
        await shutdown_discovery_client()


async def example_multi_backend():
    """多后端示例"""
    print("\n=== 多后端示例 ===")
    
    backends = [
        {'name': 'Memory', 'config': {'backend': 'memory'}},
        # 注意：以下后端需要相应的服务运行
        # {'name': 'Consul', 'config': {'backend': 'consul', 'backend_config': {'url': 'http://localhost:8500'}}},
        # {'name': 'Redis', 'config': {'backend': 'redis', 'backend_config': {'url': 'redis://localhost:6379'}}},
    ]
    
    for backend_info in backends:
        print(f"\n--- 测试 {backend_info['name']} 后端 ---")
        
        client = ServiceDiscoveryClient(backend_info['config'])
        
        try:
            await client.initialize()
            
            # 注册测试服务
            instance = await client.register_myself(
                service_name=f"test-service-{backend_info['name'].lower()}",
                host="localhost",
                port=6000,
                metadata={"backend": backend_info['name']}
            )
            print(f"✅ {backend_info['name']} 后端注册成功")
            
            # 发现服务
            instances = await client.discover(instance.service_name)
            print(f"🔍 {backend_info['name']} 后端发现 {len(instances)} 个实例")
            
        except Exception as e:
            print(f"❌ {backend_info['name']} 后端测试失败: {e}")
        finally:
            try:
                await client.shutdown()
            except Exception:
                pass


async def main():
    """运行所有示例"""
    print("🚀 MarketPrism 服务发现示例")
    print("=" * 50)
    
    # 运行各种示例
    await example_basic_usage()
    await example_microservice_integration()
    await example_load_balancing()
    await example_event_handling()
    await example_convenient_functions()
    await example_multi_backend()
    
    print("\n✅ 所有示例运行完成!")


if __name__ == "__main__":
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 运行示例
    asyncio.run(main()) 