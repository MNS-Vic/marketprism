# MarketPrism服务重构计划与命名规范修复

## 📋 项目概述

基于data-collector服务的优化标准，对MarketPrism项目的其他核心服务进行统一重构，确保所有服务都遵循相同的架构规范和命名标准。

## 🎯 重构目标

1. **统一架构规范**：所有服务都使用BaseService框架
2. **标准化API响应**：统一的成功和错误响应格式
3. **规范化错误处理**：标准化错误代码和HTTP状态码
4. **一致性命名规范**：统一的服务、容器、镜像命名标准
5. **完整技术文档**：每个服务都有完整的技术文档

## 🔍 当前状态分析

### 服务优化状态

| 服务 | BaseService | API格式 | 错误代码 | 文档 | 命名规范 | 优化度 |
|------|-------------|---------|----------|------|----------|--------|
| data-collector | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| task-worker | ✅ | ❌ | ❌ | ❌ | ❌ | 70% |
| message-broker | ✅ | ❌ | ❌ | ❌ | ❌ | 60% |
| monitoring-alerting | ❌ | ❌ | ❌ | ❌ | ❌ | 30% |

### 命名不一致问题

#### 🔴 严重问题
1. **task-worker服务**：
   - 服务名：`task-worker-service` ❌ (应该是 `task-worker`)
   - 容器名：`marketprism-task-worker-fixed` ❌ (应该是 `marketprism-task-worker`)
   - 目录名：`task-worker-service` ❌ (应该是 `task-worker`)

2. **message-broker服务**：
   - 服务名：`message-broker-service` ❌ (应该是 `message-broker`)
   - 容器名：`marketprism-message-broker-fixed` ❌ (应该是 `marketprism-message-broker`)
   - 目录名：`message-broker-service` ❌ (应该是 `message-broker`)

3. **monitoring-alerting服务**：
   - 服务名：`MarketPrism Monitoring & Alerting Service` ❌ (应该是 `monitoring-alerting`)
   - 目录名：`monitoring-alerting-service` ❌ (应该是 `monitoring-alerting`)

#### ✅ 正确命名
- **data-collector服务**：完全符合命名规范

## 📅 重构计划时间表

### 阶段1：命名规范修复 (1天)
**优先级：🔴 最高 | 预计时间：8小时**

#### 任务1.1：修复容器命名 (2小时)
- [ ] 重新启动task-worker容器，使用标准命名
- [ ] 重新启动message-broker容器，使用标准命名
- [ ] 验证所有容器命名符合规范

#### 任务1.2：修复服务内部命名 (3小时)
- [ ] 修改task-worker服务名为`task-worker`
- [ ] 修改message-broker服务名为`message-broker`
- [ ] 修改monitoring-alerting服务名为`monitoring-alerting`

#### 任务1.3：重命名服务目录 (2小时)
- [ ] 重命名`task-worker-service`为`task-worker`
- [ ] 重命名`message-broker-service`为`message-broker`
- [ ] 重命名`monitoring-alerting-service`为`monitoring-alerting`
- [ ] 更新所有相关路径引用

#### 任务1.4：验证命名一致性 (1小时)
- [ ] 验证所有服务命名符合规范
- [ ] 测试所有API端点正常工作
- [ ] 更新文档中的命名引用

### 阶段2：monitoring-alerting服务重构 (2-3天)
**优先级：🔴 高 | 预计时间：20小时**

#### 任务2.1：BaseService框架迁移 (8小时)
- [ ] 重构MonitoringAlertingService继承BaseService
- [ ] 迁移现有功能到BaseService架构
- [ ] 更新服务启动和关闭流程
- [ ] 集成BaseService的健康检查和指标

#### 任务2.2：API响应格式统一 (4小时)
- [ ] 实现`_create_success_response()`方法
- [ ] 实现`_create_error_response()`方法
- [ ] 重构所有API端点使用统一格式
- [ ] 添加JSON序列化兼容性处理

#### 任务2.3：错误处理标准化 (4小时)
- [ ] 定义标准化错误代码常量
- [ ] 实现分层错误处理机制
- [ ] 添加参数验证和错误响应
- [ ] 完善异常捕获和日志记录

#### 任务2.4：技术文档创建 (4小时)
- [ ] 创建完整的API文档
- [ ] 编写架构设计文档
- [ ] 提供部署和运维指南
- [ ] 添加开发和扩展指南

### 阶段3：message-broker服务优化 (1-2天)
**优先级：🟡 中 | 预计时间：12小时**

#### 任务3.1：API响应格式修复 (3小时)
- [ ] 修复API返回`{status: null, message: null}`问题
- [ ] 实现统一响应格式方法
- [ ] 重构现有API端点
- [ ] 测试API响应格式正确性

#### 任务3.2：错误处理增强 (3小时)
- [ ] 添加标准化错误代码定义
- [ ] 实现完整的错误处理机制
- [ ] 添加参数验证和错误响应
- [ ] 完善日志记录和调试信息

#### 任务3.3：代码规范优化 (3小时)
- [ ] 完善文档字符串和类型注解
- [ ] 优化代码结构和PEP 8规范
- [ ] 添加性能监控和内存管理
- [ ] 实现优雅的服务关闭机制

#### 任务3.4：技术文档创建 (3小时)
- [ ] 创建API文档和使用指南
- [ ] 编写架构和部署文档
- [ ] 提供故障排除指南
- [ ] 添加开发维护文档

### 阶段4：task-worker服务优化 (1天)
**优先级：🟡 中 | 预计时间：8小时**

#### 任务4.1：API响应格式统一 (3小时)
- [ ] 实现统一的成功和错误响应方法
- [ ] 重构现有API端点使用标准格式
- [ ] 修复JSON序列化问题
- [ ] 测试API响应格式一致性

#### 任务4.2：错误处理完善 (2小时)
- [ ] 添加标准化错误代码定义
- [ ] 实现完整的异常处理机制
- [ ] 添加参数验证和错误日志
- [ ] 优化错误响应和HTTP状态码

#### 任务4.3：文档和规范完善 (3小时)
- [ ] 完善方法文档字符串
- [ ] 添加类型注解和代码注释
- [ ] 创建基础技术文档
- [ ] 优化代码结构和规范

### 阶段5：文档和验证 (1天)
**优先级：🟢 低 | 预计时间：8小时**

#### 任务5.1：统一开发规范文档 (4小时)
- [ ] 创建服务开发标准规范
- [ ] 编写API设计指南
- [ ] 提供代码审查清单
- [ ] 建立持续集成标准

#### 任务5.2：端到端验证 (4小时)
- [ ] 验证所有服务API格式一致性
- [ ] 测试服务间通信和集成
- [ ] 进行性能和稳定性测试
- [ ] 完成最终文档审查

## 🎯 命名规范标准

### 统一命名规范

```
服务名称: {service-name}
目录名称: services/{service-name}/
镜像名称: marketprism_{service-name}:latest
容器名称: marketprism-{service-name}
网络别名: {service-name}
API路径: /api/v1/{endpoint}
```

### 具体命名标准

| 组件 | 格式 | 示例 |
|------|------|------|
| 服务名 | kebab-case | `data-collector` |
| 目录名 | kebab-case | `services/data-collector/` |
| 镜像名 | snake_case | `marketprism_data-collector` |
| 容器名 | kebab-case | `marketprism-data-collector` |
| 类名 | PascalCase | `DataCollectorService` |
| 方法名 | snake_case | `_get_service_status` |
| 常量名 | UPPER_CASE | `ERROR_CODES` |

## 📊 成功标准

### 技术指标
- [ ] 所有服务使用BaseService框架
- [ ] 统一的API响应格式 (100%一致性)
- [ ] 标准化错误代码和处理
- [ ] 完整的技术文档覆盖
- [ ] 符合PEP 8代码规范

### 质量指标
- [ ] API响应时间 < 500ms
- [ ] 服务启动时间 < 30s
- [ ] 内存使用优化 (< 100MB per service)
- [ ] 错误率 < 1%
- [ ] 文档覆盖率 100%

### 运维指标
- [ ] 容器健康检查通过率 100%
- [ ] 服务发现和命名一致性
- [ ] 日志格式标准化
- [ ] 监控指标完整性

## 🛠️ 具体执行步骤

### 步骤1：命名规范修复

#### 1.1 修复容器命名
```bash
# 停止并删除旧容器
docker stop marketprism-task-worker-fixed marketprism-message-broker-fixed
docker rm marketprism-task-worker-fixed marketprism-message-broker-fixed

# 启动标准命名的容器
docker run -d --name marketprism-task-worker \
  --network marketprism_marketprism-network \
  -p 8090:8090 \
  -e ENVIRONMENT=staging \
  -e NATS_URL=nats://marketprism-nats:4222 \
  -e API_PORT=8090 \
  marketprism_task-worker:latest

docker run -d --name marketprism-message-broker \
  --network marketprism_marketprism-network \
  -p 8086:8086 \
  -e ENVIRONMENT=staging \
  -e NATS_URL=nats://marketprism-nats:4222 \
  -e API_PORT=8086 \
  marketprism_message-broker:latest
```

#### 1.2 修复服务内部命名
```python
# services/task-worker-service/main.py
# 修改第35行
super().__init__("task-worker", config)  # 原来是 "task-worker-service"

# services/message-broker-service/main.py
# 修改第30行
super().__init__("message-broker", config)  # 原来是 "message-broker-service"

# services/monitoring-alerting-service/main.py
# 需要重构为BaseService架构
class MonitoringAlertingService(BaseService):
    def __init__(self, config: Dict[str, Any]):
        super().__init__("monitoring-alerting", config)
```

#### 1.3 重命名服务目录
```bash
# 重命名服务目录
mv services/task-worker-service services/task-worker
mv services/message-broker-service services/message-broker
mv services/monitoring-alerting-service services/monitoring-alerting

# 更新Dockerfile路径引用
# 更新docker-compose.yml中的路径
# 更新所有相关配置文件
```

### 步骤2：monitoring-alerting服务重构

#### 2.1 BaseService框架迁移
```python
# 新的services/monitoring-alerting/main.py
from core.service_framework import BaseService
from aiohttp import web
from datetime import datetime, timezone
from typing import Dict, Any

class MonitoringAlertingService(BaseService):
    def __init__(self, config: Dict[str, Any]):
        super().__init__("monitoring-alerting", config)
        self.alert_rules = []
        self.metrics_store = {}

    def _create_success_response(self, data: Any, message: str = "Success") -> web.Response:
        return web.json_response({
            "status": "success",
            "message": message,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    def _create_error_response(self, message: str, error_code: str = "INTERNAL_ERROR",
                              status_code: int = 500) -> web.Response:
        return web.json_response({
            "status": "error",
            "error_code": error_code,
            "message": message,
            "data": None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, status=status_code)
```

#### 2.2 API端点重构
```python
def setup_routes(self):
    """设置API路由"""
    self.app.router.add_get("/api/v1/status", self._get_service_status)
    self.app.router.add_get("/api/v1/alerts/rules", self._get_alert_rules)
    self.app.router.add_post("/api/v1/alerts/rules", self._create_alert_rule)
    self.app.router.add_get("/api/v1/metrics", self._get_metrics)

async def _get_service_status(self, request: web.Request) -> web.Response:
    """获取服务状态"""
    try:
        status_data = {
            "service": "monitoring-alerting",
            "status": "running",
            "uptime_seconds": (datetime.now(timezone.utc) - self.start_time).total_seconds(),
            "alert_rules_count": len(self.alert_rules),
            "metrics_count": len(self.metrics_store)
        }
        return self._create_success_response(status_data, "Service status retrieved successfully")
    except Exception as e:
        return self._create_error_response(f"Failed to retrieve service status: {str(e)}")
```

### 步骤3：message-broker服务优化

#### 3.1 修复API响应格式
```python
# services/message-broker/main.py
def _create_success_response(self, data: Any, message: str = "Success") -> web.Response:
    """创建成功响应"""
    return web.json_response({
        "status": "success",
        "message": message,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

def _create_error_response(self, message: str, error_code: str = "INTERNAL_ERROR",
                          status_code: int = 500) -> web.Response:
    """创建错误响应"""
    return web.json_response({
        "status": "error",
        "error_code": error_code,
        "message": message,
        "data": None,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }, status=status_code)

# 重构所有API端点使用统一格式
async def _get_service_status(self, request: web.Request) -> web.Response:
    try:
        status_data = {
            "service": "message-broker",
            "status": "running",
            "nats_connected": self.nats_connected,
            "message_count": self.message_count
        }
        return self._create_success_response(status_data, "Service status retrieved successfully")
    except Exception as e:
        return self._create_error_response(f"Failed to retrieve service status: {str(e)}")
```

### 步骤4：task-worker服务优化

#### 4.1 API响应格式统一
```python
# services/task-worker/main.py
def _create_success_response(self, data: Any, message: str = "Success") -> web.Response:
    """创建成功响应"""
    return web.json_response({
        "status": "success",
        "message": message,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

def _create_error_response(self, message: str, error_code: str = "INTERNAL_ERROR",
                          status_code: int = 500) -> web.Response:
    """创建错误响应"""
    return web.json_response({
        "status": "error",
        "error_code": error_code,
        "message": message,
        "data": None,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }, status=status_code)

# 重构现有API端点
async def _get_service_status(self, request: web.Request) -> web.Response:
    try:
        status_data = {
            "service": "task-worker",
            "status": "running",
            "worker_summary": {
                "total_workers": len(self.workers),
                "running_workers": sum(1 for w in self.workers if getattr(w, 'is_running', False)),
                "total_max_concurrent": sum(w.max_concurrent_tasks for w in self.workers)
            }
        }
        return self._create_success_response(status_data, "Service status retrieved successfully")
    except Exception as e:
        return self._create_error_response(f"Failed to retrieve service status: {str(e)}")
```

## 📋 验证清单

### 命名规范验证
- [ ] 所有容器名称格式：`marketprism-{service-name}`
- [ ] 所有镜像名称格式：`marketprism_{service-name}:latest`
- [ ] 所有服务名称格式：`{service-name}`
- [ ] 所有目录名称格式：`services/{service-name}/`

### API格式验证
- [ ] 所有成功响应包含：`{status: "success", message: "...", data: {...}, timestamp: "..."}`
- [ ] 所有错误响应包含：`{status: "error", error_code: "...", message: "...", data: null, timestamp: "..."}`
- [ ] 所有API端点返回正确的HTTP状态码
- [ ] JSON序列化兼容性（datetime对象等）

### 功能验证
- [ ] 所有服务继承BaseService框架
- [ ] 健康检查端点正常工作
- [ ] 监控指标端点正常工作
- [ ] 服务间通信正常
- [ ] 容器启动和关闭正常

## 🎯 预期结果

完成重构后，所有服务将具备：

1. **统一的架构规范**：所有服务都基于BaseService框架
2. **一致的API格式**：统一的成功和错误响应格式
3. **标准化的命名**：服务、容器、镜像命名完全一致
4. **完整的文档**：每个服务都有详细的技术文档
5. **高质量代码**：符合PEP 8规范，完整的错误处理

---

**文档版本**: 1.0.0
**创建时间**: 2025-06-29
**预计完成时间**: 2025-07-04
**负责团队**: MarketPrism Development Team
