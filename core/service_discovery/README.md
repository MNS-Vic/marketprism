# MarketPrism 服务发现模块

## 📖 概述

MarketPrism服务发现模块为分布式微服务架构提供了完整的服务注册、发现和管理功能。支持多种后端存储，提供健康检查、负载均衡、事件通知等企业级特性。

## 🏗️ 架构设计

### 为什么放在Core模块？

服务发现是**基础设施组件**，具有以下特点：
- **跨服务共享**：所有微服务都需要服务发现功能
- **基础设施性质**：类似于日志、监控、配置管理
- **避免循环依赖**：放在core避免services之间的复杂依赖

### 核心组件

```
core/service_discovery/
├── __init__.py              # 模块初始化
├── registry.py              # 服务注册表核心实现
├── discovery_client.py      # 服务发现客户端
├── backends.py              # 多种后端实现
├── examples.py              # 使用示例
└── README.md               # 本文档
```

## 🚀 快速开始

### 1. 基础使用

```python
from core.service_discovery import ServiceDiscoveryClient, ServiceStatus

# 创建客户端
config = {
    'backend': 'memory',  # 或 consul, etcd, nats, redis
    'health_check_interval': 30,
    'instance_ttl': 300
}

client = ServiceDiscoveryClient(config)
await client.initialize()

# 注册当前服务
instance = await client.register_myself(
    service_name="my-service",
    host="localhost",
    port=8080,
    metadata={"version": "1.0.0"},
    tags=["api", "web"]
)

# 发现其他服务
instances = await client.discover("api-gateway-service")
for inst in instances:
    print(f"发现服务: {inst.base_url}")

# 获取服务URL（负载均衡）
url = await client.get_service_url("data-collector")
if url:
    print(f"数据采集服务: {url}")

# 更新服务状态
await client.update_my_status(ServiceStatus.HEALTHY)

# 清理
await client.shutdown()
```

### 2. 便捷函数

```python
from core.service_discovery import register_service, discover_service, get_service_url

# 注册服务
instance = await register_service(
    service_name="my-service",
    host="localhost", 
    port=8080,
    config={'backend': 'memory'}
)

# 发现服务
instances = await discover_service("api-gateway-service")

# 获取服务URL
url = await get_service_url("data-collector")
```

## 🔧 配置选项

### 后端配置

#### 1. 内存后端（默认）
```python
config = {
    'backend': 'memory'
}
```
- **适用场景**：单机部署、开发测试
- **特点**：简单快速，无外部依赖

#### 2. Consul后端
```python
config = {
    'backend': 'consul',
    'backend_config': {
        'url': 'http://localhost:8500',
        'datacenter': 'dc1',
        'token': 'your-token'
    }
}
```
- **适用场景**：生产环境推荐
- **特点**：成熟稳定，自带健康检查

#### 3. etcd后端
```python
config = {
    'backend': 'etcd',
    'backend_config': {
        'url': 'http://localhost:2379',
        'username': 'user',
        'password': 'pass'
    }
}
```
- **适用场景**：Kubernetes环境
- **特点**：强一致性，高可用

#### 4. NATS后端
```python
config = {
    'backend': 'nats',
    'backend_config': {
        'url': 'nats://localhost:4222'
    }
}
```
- **适用场景**：消息驱动架构
- **特点**：轻量级，实时性好

#### 5. Redis后端
```python
config = {
    'backend': 'redis',
    'backend_config': {
        'url': 'redis://localhost:6379',
        'password': 'your-password'
    }
}
```
- **适用场景**：已有Redis基础设施
- **特点**：高性能，TTL支持

### 完整配置示例

```python
config = {
    # 后端配置
    'backend': 'consul',
    'backend_config': {
        'url': 'http://consul:8500'
    },
    
    # 健康检查配置
    'health_check_interval': 30,  # 健康检查间隔（秒）
    'instance_ttl': 300,          # 实例过期时间（秒）
    'cleanup_interval': 60,       # 清理间隔（秒）
    
    # 自动注册配置
    'auto_register': True,
    'auto_deregister': True
}
```

## 🎯 微服务集成

### API网关集成

```python
# services/api-gateway-service/main.py
from core.service_discovery import ServiceDiscoveryClient

class APIGateway:
    def __init__(self):
        self.discovery = ServiceDiscoveryClient({
            'backend': 'consul',
            'backend_config': {'url': 'http://consul:8500'}
        })
    
    async def start(self):
        await self.discovery.initialize()
        
        # 注册网关服务
        await self.discovery.register_myself(
            service_name="api-gateway-service",
            host="0.0.0.0",
            port=8080,
            metadata={"role": "gateway", "public": True},
            tags=["gateway", "api"]
        )
    
    async def route_request(self, service_name: str):
        # 发现后端服务
        instance = await self.discovery.get_service(service_name)
        if instance:
            return f"{instance.base_url}/api/v1"
        return None
```

### 数据采集服务集成

```python
# services/data-collector/main.py
from core.service_discovery import ServiceDiscoveryClient

class DataCollector:
    def __init__(self):
        self.discovery = ServiceDiscoveryClient({
            'backend': 'consul'
        })
    
    async def start(self):
        await self.discovery.initialize()
        
        # 注册数据采集服务
        await self.discovery.register_myself(
            service_name="data-collector",
            host="0.0.0.0",
            port=8081,
            metadata={
                "exchanges": ["binance", "okx", "deribit"],
                "role": "collector"
            },
            tags=["collector", "data"]
        )
        
        # 发现存储服务
        storage_url = await self.discovery.get_service_url("data-storage-service")
        if storage_url:
            print(f"连接到存储服务: {storage_url}")
```

## 📊 事件处理

```python
# 添加事件处理器
async def on_service_registered(instance):
    print(f"新服务注册: {instance.service_name}")

async def on_service_status_changed(data):
    print(f"服务状态变更: {data['service_name']} -> {data['new_status']}")

client.add_event_handler('service_registered', on_service_registered)
client.add_event_handler('service_status_changed', on_service_status_changed)
```

## 🔍 健康检查

服务发现模块提供自动健康检查功能：

```python
# 自定义健康检查端点
instance = await client.register_myself(
    service_name="my-service",
    host="localhost",
    port=8080,
    metadata={"health_endpoint": "/custom-health"}
)

# 手动检查服务健康状态
is_healthy = await client.health_check_service("my-service", instance.instance_id)
```

## ⚖️ 负载均衡

支持多种负载均衡策略：

```python
# 加权轮询（默认）
instance = await client.get_service("data-storage-service")

# 注册时设置权重
await client.registry.register_service(
    service_name="worker-service",
    host="localhost",
    port=8080,
    metadata={"weight": 150}  # 更高权重
)
```

## 🌍 环境配置

### 开发环境
```yaml
# config/service_discovery.yaml
service_discovery:
  backend: "memory"
  health_check_interval: 10
  instance_ttl: 60
```

### 生产环境
```yaml
service_discovery:
  backend: "consul"
  backend_config:
    consul:
      url: "${CONSUL_URL:-http://consul:8500}"
      datacenter: "${CONSUL_DATACENTER:-dc1}"
  health_check_interval: 30
  instance_ttl: 300
```

## 🧪 测试

运行测试套件：

```bash
# 基础功能测试
python test_service_discovery.py

# 运行示例
python -m core.service_discovery.examples
```

## 📈 监控指标

服务发现模块提供以下监控指标：

- `service_discovery_registrations_total`: 服务注册总数
- `service_discovery_discoveries_total`: 服务发现总数  
- `service_discovery_health_checks_total`: 健康检查总数
- `service_discovery_instances_active`: 活跃实例数量

## 🔒 安全考虑

### 1. 网络安全
```python
config = {
    'backend': 'consul',
    'backend_config': {
        'url': 'https://consul:8500',  # 使用HTTPS
        'token': 'secure-token'        # 认证令牌
    }
}
```

### 2. 服务隔离
```python
# 使用标签进行服务隔离
await client.register_myself(
    service_name="sensitive-service",
    host="localhost",
    port=8080,
    tags=["internal", "secure"],      # 内部安全服务
    metadata={"security_level": "high"}
)
```

## 🚀 最佳实践

### 1. 服务命名规范
```python
# 推荐命名格式：{功能}-{类型}-service
service_names = [
    "api-gateway-service",
    "data-collector-service", 
    "user-auth-service",
    "order-processing-service"
]
```

### 2. 元数据使用
```python
metadata = {
    "version": "1.2.3",
    "environment": "production",
    "region": "us-west-1",
    "capabilities": ["read", "write"],
    "max_connections": 1000
}
```

### 3. 优雅关闭
```python
import signal
import asyncio

async def graceful_shutdown():
    # 更新状态为维护模式
    await client.update_my_status(ServiceStatus.MAINTENANCE)
    await asyncio.sleep(5)  # 等待请求完成
    
    # 注销服务
    await client.deregister_myself()
    await client.shutdown()

# 注册信号处理器
signal.signal(signal.SIGTERM, lambda s, f: asyncio.create_task(graceful_shutdown()))
```

## 🔧 故障排除

### 常见问题

1. **服务注册失败**
   ```python
   # 检查后端连接
   try:
       await client.initialize()
   except Exception as e:
       print(f"后端连接失败: {e}")
   ```

2. **服务发现为空**
   ```python
   # 检查服务名称和状态
   all_services = await client.list_all_services()
   print(f"所有服务: {list(all_services.keys())}")
   ```

3. **健康检查失败**
   ```python
   # 确保健康检查端点可访问
   instance.health_check_url = "http://localhost:8080/health"
   ```

## 📚 相关文档

- [MarketPrism架构文档](../../README.md)
- [微服务部署指南](../../docs/deployment.md)
- [配置管理文档](../config/README.md)
- [监控系统文档](../observability/README.md)

## 🤝 贡献指南

1. Fork项目
2. 创建功能分支
3. 提交更改
4. 创建Pull Request

## 📄 许可证

本项目采用MIT许可证 - 查看[LICENSE](../../LICENSE)文件了解详情。 