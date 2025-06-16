# MarketPrism 代理配置使用指南

## 概述

MarketPrism 采用分离式代理配置系统，支持不同服务在不同环境下的精细化代理控制。这样可以确保只有需要访问外部资源的服务使用代理，而内部服务保持直连以获得最佳性能。

## 配置文件结构

### 主配置文件：`config/proxy.yaml`

```yaml
# 全局代理设置
global:
  enabled: false  # 全局代理开关
  default_timeout: 30
  retry_attempts: 3

# 服务特定代理配置
services:
  data-collector:    # 数据收集服务
    enabled: true
    description: "数据收集服务需要代理连接外部交易所"
    rest_api:
      http_proxy: "http://127.0.0.1:1087"
      https_proxy: "http://127.0.0.1:1087"
    websocket:
      socks_proxy: "socks5://127.0.0.1:1080"
    no_proxy: "localhost,127.0.0.1,*.local"
  
  # 其他服务默认不使用代理
  api-gateway:       # API网关服务
    enabled: false
  data-storage:      # 数据存储服务
    enabled: false
  scheduler:         # 调度服务
    enabled: false
  monitoring:        # 监控服务
    enabled: false
  message-broker:    # 消息代理服务
    enabled: false

# 环境特定配置
environments:
  development:       # 开发环境
  testing:          # 测试环境
  production:       # 生产环境
```

## 环境配置策略

### 1. 开发环境 (development)

**目标**：本地开发，需要通过代理访问外部交易所API

```yaml
development:
  data-collector:
    enabled: true     # ✅ 启用代理
    rest_api:
      http_proxy: "http://127.0.0.1:1087"
      https_proxy: "http://127.0.0.1:1087"
    websocket:
      socks_proxy: "socks5://127.0.0.1:1080"
  
  # 其他服务不使用代理
  api-gateway: { enabled: false }
  data-storage: { enabled: false }
  scheduler: { enabled: false }
  monitoring: { enabled: false }
  message-broker: { enabled: false }
```

**适用场景**：
- 本地开发调试
- 需要连接真实交易所数据
- 开发者本地环境

### 2. 测试环境 (testing)

**目标**：测试环境，需要验证与真实交易所的连接

```yaml
testing:
  data-collector:
    enabled: true     # ✅ 启用代理
    rest_api:
      http_proxy: "http://127.0.0.1:1087"
      https_proxy: "http://127.0.0.1:1087"
    websocket:
      socks_proxy: "socks5://127.0.0.1:1080"
  
  # 其他服务不使用代理
  api-gateway: { enabled: false }
  data-storage: { enabled: false }
  scheduler: { enabled: false }
  monitoring: { enabled: false }
  message-broker: { enabled: false }
```

**适用场景**：
- 集成测试
- API功能验证
- 性能测试
- 预发布验证

### 3. 生产环境 (production)

**目标**：生产部署，通常部署在有直接网络访问的环境

```yaml
production:
  # 所有服务都不使用代理
  data-collector: { enabled: false }
  api-gateway: { enabled: false }
  data-storage: { enabled: false }
  scheduler: { enabled: false }
  monitoring: { enabled: false }
  message-broker: { enabled: false }
```

**适用场景**：
- 云服务器部署
- 企业内网部署
- 容器化部署
- 有直接外网访问的环境

## 服务代理需求分析

### 需要代理的服务

#### 1. Data Collector Service (data-collector)
- **为什么需要代理**：需要连接外部交易所API (Binance, OKX, Deribit等)
- **代理类型**：
  - REST API: HTTP/HTTPS代理
  - WebSocket: SOCKS5代理
- **环境**：development, testing

### 不需要代理的服务

#### 1. API Gateway Service (api-gateway)
- **为什么不需要**：处理内部服务间的API路由
- **连接对象**：内部微服务

#### 2. Data Storage Service (data-storage)
- **为什么不需要**：连接本地数据库 (ClickHouse, Redis)
- **连接对象**：本地存储系统

#### 3. Scheduler Service (scheduler)
- **为什么不需要**：执行内部定时任务
- **连接对象**：内部服务API

#### 4. Monitoring Service (monitoring)
- **为什么不需要**：收集内部服务指标
- **连接对象**：内部服务监控端点

#### 5. Message Broker Service (message-broker)
- **为什么不需要**：管理内部消息队列 (NATS)
- **连接对象**：本地NATS服务器

## 代理类型说明

### HTTP/HTTPS 代理
- **用途**：REST API请求
- **协议**：HTTP, HTTPS
- **默认端口**：1087
- **适用场景**：
  - 获取市场数据
  - 账户信息查询
  - 订单管理API

### SOCKS5 代理
- **用途**：WebSocket连接
- **协议**：TCP, WebSocket
- **默认端口**：1080
- **适用场景**：
  - 实时数据流
  - 订单簿更新
  - 交易事件推送

## 使用方法

### 1. 代码中使用代理管理器

```python
from core.config.proxy_manager import get_proxy_manager, configure_service_proxy

# 获取代理管理器
proxy_manager = get_proxy_manager("development")

# 检查服务是否需要代理
if proxy_manager.is_proxy_enabled("data-collector"):
    # 获取代理配置
    proxy_dict = proxy_manager.get_proxy_dict("data-collector")
    
    # 配置requests
    import requests
    response = requests.get("https://api.binance.com/api/v3/time", proxies=proxy_dict)
    
    # 配置aiohttp
    import aiohttp
    connector_kwargs = proxy_manager.get_aiohttp_connector_kwargs("data-collector")
    async with aiohttp.ClientSession(**connector_kwargs) as session:
        async with session.get("https://api.binance.com/api/v3/time") as response:
            data = await response.json()
```

### 2. 环境变量配置

```python
from core.config.proxy_manager import configure_service_proxy

# 为data-collector服务配置代理环境变量
configure_service_proxy("data-collector", "development")

# 现在环境变量已设置：
# http_proxy=http://127.0.0.1:1087
# https_proxy=http://127.0.0.1:1087
# HTTP_PROXY=http://127.0.0.1:1087
# HTTPS_PROXY=http://127.0.0.1:1087
```

### 3. 服务启动时自动配置

```python
# 在服务启动脚本中
import os
from core.config.proxy_manager import configure_service_proxy

# 获取当前环境
environment = os.getenv("MARKETPRISM_ENV", "development")
service_name = "data-collector"

# 自动配置代理
configure_service_proxy(service_name, environment)

# 启动服务
# ...
```

## 配置验证

### 测试代理配置

```bash
# 运行代理配置测试
python scripts/test_proxy_config.py
```

### 验证特定服务

```python
from core.config.proxy_manager import get_proxy_manager

proxy_manager = get_proxy_manager("development")

# 验证data-collector配置
valid = proxy_manager.validate_proxy_config("data-collector")
print(f"Data collector proxy config valid: {valid}")

# 获取完整配置
config = proxy_manager.get_service_proxy_config("data-collector")
print(f"Data collector config: {config}")
```

## 常见问题

### 1. 如何修改代理地址？

编辑 `config/proxy.yaml` 文件：

```yaml
environments:
  development:
    data-collector:
      rest_api:
        http_proxy: "http://your-proxy-host:port"
        https_proxy: "http://your-proxy-host:port"
      websocket:
        socks_proxy: "socks5://your-proxy-host:port"
```

### 2. 如何为新环境添加配置？

在 `config/proxy.yaml` 的 `environments` 部分添加：

```yaml
environments:
  staging:  # 新环境
    data-collector:
      enabled: true
      rest_api:
        http_proxy: "http://staging-proxy:8080"
        https_proxy: "http://staging-proxy:8080"
```

### 3. 如何临时禁用代理？

设置环境变量：

```bash
export MARKETPRISM_ENV=production  # 使用不启用代理的环境
```

或者直接修改配置文件中的 `enabled: false`

### 4. 如何添加代理认证？

在 `config/proxy.yaml` 中添加认证信息：

```yaml
security:
  authentication:
    enabled: true
    username: "your-username"
    password: "your-password"  # 建议使用环境变量
```

### 5. 如何调试代理连接？

启用详细日志：

```python
import logging
logging.getLogger("core.config.proxy_manager").setLevel(logging.DEBUG)
```

检查代理连接：

```bash
# 测试HTTP代理
curl --proxy http://127.0.0.1:1087 https://httpbin.org/ip

# 测试SOCKS代理
curl --proxy socks5://127.0.0.1:1080 https://httpbin.org/ip
```

## 最佳实践

### 1. 环境隔离
- 开发环境：启用代理，便于本地调试
- 测试环境：启用代理，验证真实连接
- 生产环境：禁用代理，直连获得最佳性能

### 2. 服务分离
- 只为需要外部访问的服务启用代理
- 内部服务保持直连，减少延迟

### 3. 配置管理
- 使用环境变量覆盖敏感配置
- 定期验证代理配置有效性
- 监控代理连接性能

### 4. 安全考虑
- 代理认证信息使用环境变量
- 定期更新代理配置
- 监控代理使用情况

## 故障排除

### 代理连接失败
1. 检查代理服务器是否运行
2. 验证代理地址和端口
3. 检查防火墙设置
4. 验证代理认证信息

### 性能问题
1. 监控代理延迟
2. 考虑使用更近的代理服务器
3. 优化代理配置参数
4. 评估是否需要代理

### 配置错误
1. 运行配置验证脚本
2. 检查YAML语法
3. 验证环境变量设置
4. 查看服务日志

## 更新历史

- **2025-06-15**: 创建分离式代理配置系统
- **2025-06-15**: 添加测试环境代理支持
- **2025-06-15**: 完善使用指南和最佳实践 