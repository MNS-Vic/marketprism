# MarketPrism 服务命名规范

## 概述

本文档定义了MarketPrism项目中所有微服务的统一命名规范，确保服务名称、容器名、镜像名的一致性，避免命名混乱导致的部署和集成问题。

## 命名规范

### 1. 服务名称格式

**标准格式**: `{功能}-{类型}`
- 使用小写字母
- 使用连字符（-）分隔单词
- 避免下划线（_）
- 保持简洁明了

### 2. 各组件命名规则

#### Docker Compose服务名
```yaml
services:
  data-collector:        # ✅ 正确
  message-broker:        # ✅ 正确
  task-worker:          # ✅ 正确
```

#### 容器名
```yaml
container_name: marketprism-{service-name}
```
示例：
- `marketprism-data-collector`
- `marketprism-message-broker`
- `marketprism-task-worker`

#### 镜像名
```yaml
image: marketprism_{service-name}:latest
```
示例：
- `marketprism_data-collector:latest`
- `marketprism_message-broker:latest`
- `marketprism_task-worker:latest`

#### 服务标识符（代码中）
```python
super().__init__("service-name", config)
```
示例：
- `"data-collector"`
- `"message-broker"`
- `"task-worker"`

## 当前标准服务列表

| 服务功能 | 标准名称 | 端口 | 容器名 | 镜像名 |
|---------|---------|------|--------|--------|
| 数据收集器 | `data-collector` | 8084 | `marketprism-data-collector` | `marketprism_data-collector` |
| 消息代理 | `message-broker` | 8086 | `marketprism-message-broker` | `marketprism_message-broker` |
| 任务工作器 | `task-worker` | 8090 | `marketprism-task-worker` | `marketprism_task-worker` |
| 数据存储 | `data-storage` | 8083 | `marketprism-data-storage` | `marketprism_data-storage` |
| 监控告警 | `monitoring-alerting` | 8082 | `marketprism-monitoring-alerting` | `marketprism_monitoring-alerting` |

## 端口分配标准

- 8080: API Gateway
- 8081: 预留
- 8082: Monitoring Alerting
- 8083: Data Storage
- 8084: Data Collector
- 8085: 预留
- 8086: Message Broker
- 8087: Data Storage Hot
- 8088-8089: 预留
- 8090: Task Worker

## 配置文件一致性

### docker-compose.yml
```yaml
services:
  data-collector:
    container_name: marketprism-data-collector
    ports:
      - "8084:8084"
```

### services.yaml
```yaml
services:
  data-collector:
    port: 8084
```

### 服务代码
```python
class DataCollectorService(BaseService):
    def __init__(self, config):
        super().__init__("data-collector", config)
```

## 检查清单

在添加新服务或修改现有服务时，请确认：

- [ ] Docker Compose服务名使用连字符格式
- [ ] 容器名以`marketprism-`为前缀
- [ ] 镜像名以`marketprism_`为前缀
- [ ] 服务标识符与Docker Compose服务名一致
- [ ] 端口配置在所有文件中保持一致
- [ ] 更新本文档中的服务列表

## 常见错误

### ❌ 错误示例
```yaml
# 不一致的命名
services:
  market-data-collector:     # Docker Compose中
    container_name: marketprism-data-collector  # 容器名不匹配

# 代码中
super().__init__("data-collector", config)  # 服务标识符不匹配
```

### ✅ 正确示例
```yaml
# 一致的命名
services:
  data-collector:            # Docker Compose中
    container_name: marketprism-data-collector  # 容器名匹配

# 代码中
super().__init__("data-collector", config)  # 服务标识符匹配
```

## 版本历史

- v1.0.0 (2025-06-29): 初始版本，统一data-collector命名规范
