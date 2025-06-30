# Task Worker Service 技术文档

## 📋 服务概述

Task Worker Service 是 MarketPrism 微服务架构的分布式任务处理引擎，基于 BaseService 框架构建，提供高性能的异步任务处理能力。

### 核心功能
- **分布式任务队列**: 基于 NATS 的高性能任务分发
- **多工作者负载均衡**: 动态工作者管理和负载分配
- **自动扩容/缩容**: 根据负载动态调整工作者数量
- **任务状态监控**: 实时监控任务执行状态和性能指标
- **故障转移和重试**: 自动故障检测和任务重试机制
- **统一 API 响应**: 标准化的 REST API 接口

## 🏗️ 架构设计

### 服务架构
```
┌─────────────────────────────────────────────────────────────┐
│                Task Worker Service                          │
├─────────────────────────────────────────────────────────────┤
│  BaseService Framework                                      │
│  ├── 统一 API 响应格式                                        │
│  ├── 标准化错误处理                                          │
│  ├── 服务生命周期管理                                        │
│  └── 健康检查和监控                                          │
├─────────────────────────────────────────────────────────────┤
│  Task Management Layer                                      │
│  ├── TaskWorkerService (主服务)                              │
│  ├── Worker Pool Management (工作者池管理)                    │
│  ├── Task Distribution (任务分发)                            │
│  └── Load Balancing (负载均衡)                               │
├─────────────────────────────────────────────────────────────┤
│  NATS Integration Layer                                     │
│  ├── NATSTaskWorker (任务工作者)                              │
│  ├── Message Queue (消息队列)                                │
│  ├── Task Persistence (任务持久化)                           │
│  └── Connection Management (连接管理)                        │
├─────────────────────────────────────────────────────────────┤
│  Worker Instances                                          │
│  ├── Worker-1 (max_concurrent: 5)                          │
│  ├── Worker-2 (max_concurrent: 5)                          │
│  └── Worker-N (动态扩展)                                     │
└─────────────────────────────────────────────────────────────┘
```

### 技术栈
- **框架**: BaseService (MarketPrism 统一服务框架)
- **任务队列**: NATS + JetStream
- **Web 框架**: aiohttp
- **异步处理**: asyncio
- **日志系统**: structlog
- **容器化**: Docker

## 🔧 配置管理

### 环境变量
```bash
# 服务配置
ENVIRONMENT=production          # 运行环境
API_PORT=8090                  # API 服务端口
LOG_LEVEL=INFO                 # 日志级别

# 工作者配置
WORKER_COUNT=3                 # 工作者数量
WORKER_TYPE=general            # 工作者类型
MAX_CONCURRENT_TASKS=5         # 每个工作者最大并发任务数

# NATS 配置
NATS_URL=nats://nats:4222      # NATS 服务器地址
```

### 配置文件结构
```yaml
services:
  task-worker:
    port: 8090
    host: "0.0.0.0"
    worker_count: 3
    worker_type: "general"
    max_concurrent_tasks: 5
    nats_url: "nats://localhost:4222"
    scaling:
      min_workers: 1
      max_workers: 10
      scale_threshold: 0.8
```

## 🌐 API 接口文档

### 标准化响应格式

#### 成功响应
```json
{
  "status": "success",
  "message": "操作成功描述",
  "data": { ... },
  "timestamp": "2025-06-29T05:32:44.123Z"
}
```

#### 错误响应
```json
{
  "status": "error",
  "error_code": "WORKER_START_ERROR",
  "message": "错误描述信息",
  "data": null,
  "timestamp": "2025-06-29T05:32:44.123Z"
}
```

### 核心 API 端点

#### 1. 服务状态查询
```http
GET /api/v1/status
```

**响应示例**:
```json
{
  "status": "success",
  "message": "Service status retrieved successfully",
  "data": {
    "service": "task-worker",
    "status": "running",
    "uptime_seconds": 3600.45,
    "version": "1.0.0",
    "environment": "production",
    "port": 8090,
    "features": {
      "distributed_tasks": true,
      "nats_integration": true,
      "auto_scaling": true,
      "load_balancing": true,
      "fault_tolerance": true
    },
    "worker_summary": {
      "total_workers": 3,
      "running_workers": 3,
      "worker_type": "general",
      "max_concurrent_per_worker": 5,
      "total_max_concurrent": 15
    },
    "nats_info": {
      "url": "nats://nats:4222",
      "connected": true,
      "connection_count": 3
    },
    "statistics": {
      "tasks_processed": 1542,
      "tasks_failed": 12,
      "current_active_tasks": 8,
      "average_task_duration": 2.5
    }
  },
  "timestamp": "2025-06-29T05:32:44.123Z"
}
```

#### 2. 工作者管理

##### 获取工作者列表
```http
GET /api/v1/workers
```

##### 获取工作者状态
```http
GET /api/v1/workers/status
```

##### 获取工作者统计
```http
GET /api/v1/workers/stats
```

##### 动态扩容/缩容
```http
POST /api/v1/workers/scale
Content-Type: application/json

{
  "worker_count": 5
}
```

#### 3. 任务管理

##### 获取任务统计
```http
GET /api/v1/tasks/stats
```

##### 提交任务
```http
POST /api/v1/tasks/submit
Content-Type: application/json

{
  "task_type": "data_processing",
  "task_data": {
    "input": "market_data.csv",
    "operation": "analyze",
    "parameters": {
      "window": 60,
      "threshold": 0.05
    }
  },
  "priority": "high",
  "timeout": 300
}
```

## 🔒 错误代码规范

### 标准错误代码
```python
ERROR_CODES = {
    'WORKER_START_ERROR': '工作者启动失败',
    'WORKER_STOP_ERROR': '工作者停止失败',
    'WORKER_NOT_FOUND': '工作者不存在',
    'TASK_SUBMISSION_ERROR': '任务提交失败',
    'TASK_EXECUTION_ERROR': '任务执行失败',
    'NATS_CONNECTION_ERROR': 'NATS连接失败',
    'SCALING_ERROR': '扩缩容操作失败',
    'INVALID_WORKER_CONFIG': '无效的工作者配置',
    'INVALID_TASK_DATA': '无效的任务数据',
    'INVALID_PARAMETERS': '无效参数',
    'SERVICE_UNAVAILABLE': '服务不可用',
    'INTERNAL_ERROR': '内部错误'
}
```

### HTTP 状态码映射
- `200`: 成功操作
- `400`: 客户端错误 (参数验证失败)
- `404`: 资源不存在 (工作者不存在)
- `500`: 服务器内部错误
- `503`: 服务不可用 (无可用工作者)

## 🚀 部署指南

### Docker 部署
```bash
# 构建镜像
docker build -t marketprism_task-worker:latest \
  -f services/task-worker/Dockerfile .

# 运行容器
docker run -d \
  --name marketprism-task-worker \
  --network marketprism_marketprism-network \
  -p 8090:8090 \
  -e ENVIRONMENT=production \
  -e API_PORT=8090 \
  -e WORKER_COUNT=3 \
  -e WORKER_TYPE=general \
  -e MAX_CONCURRENT_TASKS=5 \
  -e NATS_URL=nats://marketprism-nats:4222 \
  marketprism_task-worker:latest
```

### 健康检查
```bash
# 基础健康检查
curl http://localhost:8090/health

# 详细状态检查
curl http://localhost:8090/api/v1/status

# 工作者状态检查
curl http://localhost:8090/api/v1/workers/status
```

## 🔍 监控和日志

### 关键指标
- **任务吞吐量**: 每分钟处理的任务数
- **工作者利用率**: 当前活跃任务 / 总容量
- **任务成功率**: 成功任务 / 总任务数
- **平均任务时长**: 任务执行的平均时间
- **NATS 连接状态**: 工作者与 NATS 的连接状态

### 日志格式
```json
{
  "timestamp": "2025-06-29T05:32:44.123Z",
  "level": "INFO",
  "logger": "task-worker",
  "message": "任务处理完成",
  "service": "task-worker",
  "worker_id": "general-worker-1",
  "task_id": "task-20250629053244-1",
  "task_type": "data_processing",
  "duration_ms": 2500,
  "status": "success"
}
```

## 🧪 测试指南

### API 测试示例
```bash
# 1. 测试服务状态
curl -X GET http://localhost:8090/api/v1/status

# 2. 获取工作者列表
curl -X GET http://localhost:8090/api/v1/workers

# 3. 提交测试任务
curl -X POST http://localhost:8090/api/v1/tasks/submit \
  -H "Content-Type: application/json" \
  -d '{"task_type":"test","task_data":{"message":"hello"}}'

# 4. 扩容工作者
curl -X POST http://localhost:8090/api/v1/workers/scale \
  -H "Content-Type: application/json" \
  -d '{"worker_count":5}'

# 5. 获取任务统计
curl -X GET http://localhost:8090/api/v1/tasks/stats
```

### 性能测试
- **并发任务**: 支持 15+ 并发任务 (3 workers × 5 concurrent)
- **任务吞吐**: 100+ 任务/分钟
- **API 响应**: < 50ms (P95)
- **内存使用**: < 150MB (正常负载)

## 🔧 故障排除

### 常见问题

#### 1. 工作者启动失败
```bash
# 检查 NATS 连接
curl http://localhost:8090/api/v1/workers/status

# 检查工作者日志
docker logs marketprism-task-worker | grep worker
```

#### 2. 任务提交失败
- 检查任务数据格式是否正确
- 验证是否有可用的工作者
- 确认 NATS 连接状态

#### 3. 扩容失败
- 检查目标工作者数量是否合理
- 验证系统资源是否充足
- 确认 NATS 连接池容量

---

**文档版本**: 1.0.0  
**最后更新**: 2025-06-29  
**维护团队**: MarketPrism Development Team
