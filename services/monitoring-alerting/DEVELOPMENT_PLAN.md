# MarketPrism 监控告警服务 - 开发计划文档

> **文档版本**: v1.0
> **创建日期**: 2025-10-20
> **最后更新**: 2025-10-20
> **状态**: 基于实际代码验证的开发计划

---

## 📋 第一章节：模块开发 PRD（产品需求文档）

### 1.1 模块定位与核心职责

**核心定位**：
- MarketPrism 系统的**统一监控与告警中心**
- 为 Grafana 提供高性能数据源支持
- 集成 Prometheus + Alertmanager + Grafana 的完整监控栈
- 提供 RESTful API 用于告警管理和服务状态查询

**核心职责**：
1. **指标收集与暴露**：通过 `/metrics` 端点暴露 Prometheus 格式指标
2. **告警管理**：提供告警规则配置、告警查询、告警状态管理 API
3. **服务健康监控**：监控 collector、hot-storage、cold-storage、message-broker 等服务健康状态
4. **监控栈编排**：通过 docker-compose 一键部署 Prometheus/Alertmanager/Grafana/Blackbox/DingTalk
5. **告警通知**：集成 DingTalk Webhook 实现告警推送

**非职责**（明确边界）：
- ❌ 不负责业务数据的采集（由 data-collector 负责）
- ❌ 不负责数据存储（由 hot/cold-storage 负责）
- ❌ 不负责消息队列管理（由 message-broker 负责）
- ❌ 不实现复杂的异常检测算法（当前版本已移除，专注核心功能）

### 1.2 功能需求清单

#### ✅ 已实现功能（基于代码审查）

**基础服务功能**：
- [x] 基于 BaseService 框架的服务生命周期管理
- [x] 健康检查端点 `/health`（由 BaseService 提供）
- [x] Prometheus 指标端点 `/metrics`（由 BaseService 提供）
- [x] 结构化日志（基于 structlog）
- [x] CORS 支持（通过 aiohttp-cors）

**告警管理 API**：
- [x] GET `/api/v1/alerts` - 查询告警列表（支持 status/severity/category 过滤）
- [x] POST `/api/v1/alerts` - 创建新告警
- [x] GET `/api/v1/alerts/rules` - 查询告警规则列表
- [x] POST `/api/v1/alerts/rules` - 创建新告警规则

**服务状态 API**：
- [x] GET `/api/v1/status` - 获取服务状态（运行时间、统计信息、组件健康）
- [x] GET `/api/v1/metrics` - 获取业务指标（JSON 格式，支持 Prometheus 格式转换）
- [x] GET `/api/v1/health/components` - 获取各组件健康状态

**监控栈集成**：
- [x] Prometheus 配置（抓取 collector:9092、hot:9094、cold:9095、broker:9096）
- [x] Alertmanager 配置（告警路由、DingTalk 通知、抑制规则）
- [x] Grafana 自动配置（数据源、仪表盘 provisioning）
- [x] Blackbox Exporter 配置（HTTP 健康检查探测）
- [x] 告警规则定义（BrokerDown、HotInsertErrorsHigh、ColdReplicationLagHigh 等）

**安全功能（已实现但未集成）**：
- [x] 认证中间件（auth.py）：Token/API Key/Basic Auth、速率限制
- [x] 验证中间件（validation.py）：Pydantic 校验、SQL 注入/XSS 防护
- [x] SSL/TLS 支持（ssl_config.py）：自签名证书生成、证书管理

#### 🔧 待修复的 Bug（P0 - 阻塞运行）

**关键 Bug**：
1. **main.py 调用不存在的方法**：
   - 问题：第 700 行调用 `await service.start()`，第 712 行调用 `await service.stop()`
   - 现象：`AttributeError: 'MonitoringAlertingService' object has no attribute 'start'`
   - 影响：**服务无法启动**
   - 根因：BaseService 只提供 `run()` 方法，不提供 `start()/stop()`

2. **health_check.py 作用域错误**：
   - 问题：ClientSession 在第 16 行创建，但在第 42/54/67 行（已关闭后）继续使用
   - 影响：健康检查脚本无法正常工作
   - 根因：异步上下文管理器作用域错误

3. **start_service.py 导入不存在的模块**：
   - 问题：第 68 行 `from config.unified_config_loader import UnifiedConfigLoader`
   - 影响：使用 start_service.py 启动会失败（但有 try-except 捕获）
   - 根因：配置加载器路径错误

#### 🚀 待开发功能（P1/P2 - 增强）

**P1 - 重要增强**：
- [ ] 中间件集成：将 auth.py 和 validation.py 接入服务（可选，通过环境变量控制）
- [ ] 配置外部化：DingTalk token/secret 从 docker-compose.yml 移至环境变量
- [ ] 告警持久化：当前告警数据存储在内存，重启丢失
- [ ] 指标聚合：从其他服务收集指标并聚合展示

**P2 - 可选增强**：
- [ ] 告警规则动态加载：支持从配置文件或数据库加载规则
- [ ] 告警历史查询：提供告警历史记录查询 API
- [ ] 多通知渠道：支持邮件、Slack、企业微信等
- [ ] Grafana 仪表盘完善：补充更多业务指标可视化

### 1.3 非功能需求

**性能指标**（基于 README 声明）：
- QPS: > 2000（实测 2960）
- 响应时间: < 5ms（实测 3.8ms 平均）
- P95 响应时间: < 10ms
- P99 响应时间: < 17ms
- 成功率: 100%
- CPU 使用率: < 10%（实测 7.3%）
- 内存使用率: < 50%（实测 30.6%）

**可用性指标**：
- 服务可用性: 99.9%
- 健康检查响应时间: < 100ms
- 监控栈启动时间: < 30s

**安全要求**：
- 支持 HTTPS（可选，通过环境变量启用）
- 支持认证（可选，通过环境变量启用）
- 敏感信息不得硬编码在代码或配置文件中
- 支持速率限制防止 DDoS

**可维护性要求**：
- 代码覆盖率: > 70%（单元测试 + 集成测试）
- 日志结构化，支持 JSON 格式输出
- 配置集中管理，支持环境变量覆盖
- 文档完整，包含 API 文档、部署文档、故障排查文档

### 1.4 与其他服务的集成关系

**监控目标服务**（被监控）：
1. **data-collector** (端口 8087)
   - 健康检查: `http://host.docker.internal:8087/health`
   - 指标端点: `http://host.docker.internal:9092/metrics`
   - 监控指标: 采集速率、WebSocket 连接数、错误率

2. **hot-storage-service** (端口 8085)
   - 健康检查: `http://host.docker.internal:8085/health`
   - 指标端点: `http://host.docker.internal:9094/metrics`
   - 监控指标: ClickHouse 写入速率、错误率、队列积压

3. **cold-storage-service** (端口 8086)
   - 健康检查: `http://host.docker.internal:8086/health`
   - 指标端点: `http://host.docker.internal:9095/metrics`
   - 监控指标: 复制延迟、存储容量、错误率

4. **message-broker** (端口 8088)
   - 健康检查: `http://host.docker.internal:8088/health`
   - 指标端点: `http://host.docker.internal:9096/metrics`
   - 监控指标: NATS 连接状态、消息吞吐量、队列深度

**依赖的外部服务**：
- **ClickHouse (Hot)**: `http://host.docker.internal:8123/ping`
- **ClickHouse (Cold)**: `http://host.docker.internal:8124/ping`

**集成方式**：
- Prometheus 通过 HTTP 拉取各服务的 `/metrics` 端点（15s 间隔）
- Blackbox Exporter 探测各服务的 `/health` 端点（30s 间隔）
- Alertmanager 接收 Prometheus 告警并路由到 DingTalk Webhook
- Grafana 从 Prometheus 查询数据并可视化

**数据流向**：
```
各服务 /metrics → Prometheus → Grafana（可视化）
                              ↓
                         告警规则评估
                              ↓
                        Alertmanager
                              ↓
                      DingTalk Webhook
```

### 1.5 用户场景与使用流程

**场景 1：开发者本地调试监控栈**
1. 启动监控栈：`cd services/monitoring-alerting && docker compose up -d`
2. 访问 Grafana：`http://localhost:3000`（admin/admin）
3. 查看 Prometheus targets：`http://localhost:9090/targets`
4. 查看告警规则：`http://localhost:9090/alerts`
5. 触发测试告警：停止某个服务，观察告警触发

**场景 2：运维人员查看系统健康状态**
1. 访问 Grafana 仪表盘查看整体指标
2. 通过 `/api/v1/status` API 查询服务状态
3. 通过 `/api/v1/health/components` 查询各组件健康
4. 接收 DingTalk 告警通知并响应

**场景 3：开发者集成新服务到监控系统**
1. 在新服务中实现 `/health` 和 `/metrics` 端点
2. 在 `prometheus.yml` 添加新的 scrape_configs
3. 在 `alerts.yml` 添加新的告警规则
4. 在 Grafana 仪表盘添加新的面板
5. 重启监控栈使配置生效

### 1.6 验收标准

**P0 - 基础功能验收**：
- [ ] 服务可以成功启动：`python services/monitoring-alerting/main.py`
- [ ] 健康检查返回 200：`curl http://localhost:8082/health`
- [ ] 指标端点返回 Prometheus 格式：`curl http://localhost:8082/metrics`
- [ ] 告警 API 可访问：`curl http://localhost:8082/api/v1/alerts`
- [ ] 监控栈可以启动：`docker compose up -d` 所有容器 healthy

**P1 - 集成功能验收**：
- [ ] Prometheus 可以抓取所有 targets（collector/hot/cold/broker）
- [ ] Grafana 可以查询到 Prometheus 数据
- [ ] 告警规则可以正常评估和触发
- [ ] DingTalk 可以接收告警通知
- [ ] Blackbox 可以探测各服务健康状态

**P2 - 高级功能验收**：
- [ ] 认证中间件可以正常工作（启用后）
- [ ] 速率限制可以防止滥用
- [ ] HTTPS 可以正常工作（启用后）
- [ ] 健康检查脚本可以正常运行
- [ ] 单元测试和集成测试通过

---

## 🗓️ 第二章节：模块开发计划

### 2.1 分阶段开发路线图

#### 阶段 0：验证与诊断（已完成 ✅）
**目标**：确认当前代码状态，识别阻塞问题
**时间**：0.5 天
**状态**：已完成

**完成的工作**：
- ✅ 运行 main.py 并记录报错
- ✅ 检查 docker-compose 状态
- ✅ 分析依赖关系
- ✅ 识别关键 bug

**发现的问题**：
1. main.py 调用不存在的 start/stop 方法 → 服务无法启动
2. health_check.py 作用域错误 → 健康检查脚本无法工作
3. start_service.py 导入错误 → 启动脚本有问题（但有 fallback）

#### 阶段 1：P0 Bug 修复（必须完成）
**目标**：修复阻塞服务运行的关键 bug
**优先级**：P0（最高）
**预估工作量**：0.5 天
**依赖**：无
**风险**：低

**任务清单**：
1. **修复 main.py 启动逻辑**
   - 将 `await service.start()` 改为 `await service.run()`
   - 移除 `await service.stop()` 调用（run() 已包含清理）
   - 验证：服务可以正常启动并响应请求

2. **修复 health_check.py 作用域**
   - 将所有 HTTP 请求放入同一个 `async with ClientSession()` 块
   - 修正字段名：`alerts_data.get('total')` → `alerts_data.get('total_count')`
   - 验证：健康检查脚本可以正常运行

3. **修复 start_service.py 导入**
   - 移除不存在的 `unified_config_loader` 导入
   - 简化为直接使用默认配置
   - 验证：start_service.py 可以正常启动服务

**交付物**：
- 修复后的 main.py、health_check.py、start_service.py
- 验证报告（服务启动成功、健康检查通过）

**验收标准**：
- 服务可以启动并监听 8082 端口
- `/health` 返回 200
- `/metrics` 返回 Prometheus 格式数据
- health_check.py 可以正常运行

#### 阶段 2：P1 安全与配置增强（重要）
**目标**：解决安全隐患，完善配置管理
**优先级**：P1（高）
**预估工作量**：1 天
**依赖**：阶段 1 完成
**风险**：中（涉及配置变更）

**任务清单**：
1. **DingTalk 密钥外部化**
   - 创建 `.env.example` 模板文件
   - 修改 `docker-compose.yml`，使用环境变量引用
   - 更新 README 说明如何配置密钥
   - 验证：docker-compose 可以从 .env 读取密钥

2. **README 路由命名统一**
   - 将 README 中的 `/api/v1/rules` 统一为 `/api/v1/alerts/rules`
   - 确保文档与实际实现一致
   - 验证：文档描述与代码匹配

3. **认证中间件集成（可选）**
   - 在 main.py 中添加中间件挂载逻辑
   - 通过环境变量 `MARKETPRISM_ENABLE_AUTH` 控制是否启用
   - 默认关闭（开发环境），生产环境可启用
   - 验证：启用后 API 需要认证，禁用后无需认证

4. **验证中间件集成（可选）**
   - 在 main.py 中添加验证中间件
   - 通过环境变量 `MARKETPRISM_ENABLE_VALIDATION` 控制
   - 验证：启用后请求参数会被校验

**交付物**：
- .env.example 文件
- 更新后的 docker-compose.yml
- 更新后的 README.md
- 可选：集成中间件的 main.py

**验收标准**：
- docker-compose.yml 不包含明文密钥
- .env.example 提供清晰的配置模板
- README 文档准确无误
- 认证中间件可以正常工作（如果启用）

#### 阶段 3：P2 功能完善与测试（可选）
**目标**：补充测试，完善文档，提升用户体验
**优先级**：P2（中）
**预估工作量**：1-2 天
**依赖**：阶段 1 完成（阶段 2 可选）
**风险**：低

**任务清单**：
1. **补充单元测试**
   - 为 MonitoringAlertingService 补充测试
   - 为中间件（auth/validation）补充测试
   - 目标覆盖率：> 70%

2. **补充集成测试**
   - 测试完整的 API 调用流程
   - 测试监控栈集成（Prometheus/Grafana）
   - 测试告警触发与通知

3. **完善 API 功能**
   - 告警 API 支持分页、排序
   - 指标 API 支持时间范围查询
   - 支持告警规则的 CRUD 操作

4. **完善文档**
   - 补充 API 文档（OpenAPI/Swagger）
   - 补充故障排查文档
   - 补充性能调优文档

**交付物**：
- 单元测试和集成测试
- 增强的 API 功能
- 完善的文档

**验收标准**：
- 测试覆盖率 > 70%
- 所有测试通过
- 文档完整且准确

### 2.2 时间线与里程碑

| 阶段 | 时间 | 里程碑 | 交付物 |
|------|------|--------|--------|
| 阶段 0 | Day 0 | ✅ 验证完成 | 问题诊断报告 |
| 阶段 1 | Day 1 | 🎯 服务可运行 | 修复后的代码 + 验证报告 |
| 阶段 2 | Day 2 | 🔒 安全加固 | 配置外部化 + 文档更新 |
| 阶段 3 | Day 3-4 | 📈 功能完善 | 测试 + 文档 + 增强功能 |

**关键里程碑**：
- **M1 (Day 1 EOD)**: 服务可以正常启动并响应请求
- **M2 (Day 2 EOD)**: 监控栈可以完整部署并工作
- **M3 (Day 4 EOD)**: 测试覆盖率达标，文档完善

### 2.3 依赖关系与风险识别

**依赖关系**：
```
阶段 0 (验证) → 阶段 1 (P0 修复) → 阶段 2 (P1 增强)
                                  ↘
                                   阶段 3 (P2 完善)
```

**风险识别与缓解**：

| 风险 | 等级 | 影响 | 缓解措施 |
|------|------|------|----------|
| BaseService 接口变更 | 低 | 修复方案失效 | 先查看 BaseService 源码确认接口 |
| 其他服务未实现 /metrics | 中 | Prometheus 抓取失败 | 分离"自身运行"和"完整监控栈"验收 |
| Docker 环境问题 | 低 | 监控栈无法启动 | 提供详细的环境要求文档 |
| 中间件集成冲突 | 中 | 服务启动失败 | 通过环境变量控制，默认禁用 |
| 配置变更破坏现有部署 | 低 | 生产环境受影响 | 提供迁移指南，保持向后兼容 |

---

## 📐 第三章节：模块开发细节规范

### 3.1 代码结构与目录组织规范

**当前目录结构**：
```
services/monitoring-alerting/
├── main.py                    # ✅ 唯一入口（符合项目约定）
├── start_service.py           # 🔧 启动脚本（需修复）
├── health_check.py            # 🔧 健康检查工具（需修复）
├── requirements.txt           # ✅ 依赖声明
├── Dockerfile                 # ✅ 容器镜像定义
├── docker-compose.yml         # ✅ 监控栈编排
├── README.md                  # ✅ 模块文档
├── DEVELOPMENT_PLAN.md        # ✅ 本文档
│
├── config/                    # ⚠️ 当前为空，未来可放服务配置
│
├── auth.py                    # ✅ 认证中间件（未集成）
├── validation.py              # ✅ 验证中间件（未集成）
├── ssl_config.py              # ✅ SSL 配置（未集成）
│
├── prometheus.yml             # ✅ Prometheus 配置
├── alertmanager.yml           # ✅ Alertmanager 配置
├── alerts.yml                 # ✅ 告警规则定义
├── blackbox.yml               # ✅ Blackbox Exporter 配置
│
├── dashboards/                # ✅ Grafana 仪表盘
│   └── marketprism.json
├── provisioning/              # ✅ Grafana 自动配置
│   ├── dashboards/
│   └── datasources/
│
├── deprecated/                # ✅ 历史版本（已废弃）
│   ├── main_old.py
│   ├── main_before_security.py
│   └── main_secure_v2.py
│
└── temp/                      # ✅ 临时脚本（当前为空）
```

**目录组织原则**：
1. **唯一入口**：`main.py` 是模块的唯一入口，符合项目约定
2. **配置集中**：监控栈配置（prometheus.yml 等）放在模块根目录，与 docker-compose.yml 同级
3. **服务配置**：未来如需服务自身配置，放在 `config/` 目录
4. **临时文件**：临时测试脚本放在 `temp/`，完成后删除
5. **历史版本**：废弃代码放在 `deprecated/`，不删除但不使用

**不允许的操作**：
- ❌ 不创建新的入口文件（如 main_v2.py）
- ❌ 不在模块外部放置配置文件
- ❌ 不在代码中硬编码配置（使用环境变量）

### 3.2 API 路由命名与响应格式规范

**路由命名规范**：
```
基础路径: /api/v1

资源路由:
  GET    /api/v1/alerts              # 查询告警列表
  POST   /api/v1/alerts              # 创建新告警
  GET    /api/v1/alerts/{id}         # 查询单个告警
  PUT    /api/v1/alerts/{id}         # 更新告警
  DELETE /api/v1/alerts/{id}         # 删除告警

  GET    /api/v1/alerts/rules        # 查询告警规则列表
  POST   /api/v1/alerts/rules        # 创建新规则
  GET    /api/v1/alerts/rules/{id}   # 查询单个规则
  PUT    /api/v1/alerts/rules/{id}   # 更新规则
  DELETE /api/v1/alerts/rules/{id}   # 删除规则

状态路由:
  GET    /api/v1/status              # 服务状态
  GET    /api/v1/metrics             # 业务指标（JSON）
  GET    /api/v1/health/components   # 组件健康

健康检查（BaseService 提供）:
  GET    /health                     # 健康检查
  GET    /metrics                    # Prometheus 指标
```

**响应格式规范**：

**成功响应**：
```json
{
  "success": true,
  "data": {
    // 业务数据
  },
  "timestamp": "2025-10-20T22:50:45Z"
}
```

**错误响应**：
```json
{
  "success": false,
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "告警不存在",
    "details": {}
  },
  "timestamp": "2025-10-20T22:50:45Z"
}
```

**分页响应**：
```json
{
  "success": true,
  "data": {
    "items": [...],
    "total_count": 100,
    "page": 1,
    "page_size": 20,
    "total_pages": 5
  },
  "timestamp": "2025-10-20T22:50:45Z"
}
```

**HTTP 状态码规范**：
- 200: 成功
- 201: 创建成功
- 400: 请求参数错误
- 401: 未认证
- 403: 无权限
- 404: 资源不存在
- 429: 请求过于频繁
- 500: 服务器内部错误
- 503: 服务不可用

### 3.3 配置管理规范

**配置层次**（优先级从高到低）：
1. **环境变量**：运行时动态配置（最高优先级）
2. **配置文件**：`config/*.yaml`（如果存在）
3. **代码默认值**：main.py 中的默认配置（最低优先级）

**环境变量命名规范**：
```bash
# 服务基础配置
MARKETPRISM_MONITORING_PORT=8082
MARKETPRISM_MONITORING_HOST=0.0.0.0
MARKETPRISM_MONITORING_LOG_LEVEL=INFO

# 安全配置（与代码一致）
MARKETPRISM_ENABLE_AUTH=false        # 是否启用认证（auth 中间件）
MARKETPRISM_ENABLE_VALIDATION=false  # 是否启用验证（validation 中间件）
# 如需 HTTPS，可使用自定义变量（示例）：MARKETPRISM_ENABLE_HTTPS=false
MONITORING_API_KEY=mp-monitoring-key-2024  # 默认 API Key，可覆盖
MONITORING_USERNAME=admin
MONITORING_PASSWORD=marketprism2024!

# 监控栈配置
DINGTALK_WEBHOOK_URL=https://...     # DingTalk Webhook URL
DINGTALK_SECRET=your-secret-here     # DingTalk 签名密钥
```

**敏感信息处理**：
1. **不得硬编码**：密钥、密码、token 不得出现在代码或配置文件中
2. **使用环境变量**：通过 `.env` 文件或系统环境变量注入
3. **提供示例文件**：`.env.example` 提供配置模板（不包含真实值）
4. **Git 忽略**：`.env` 文件必须在 `.gitignore` 中

**配置文件示例**（未来如需创建 config/service.yaml）：
```yaml
server:
  port: 8082
  host: 0.0.0.0

security:
  auth_enabled: false
  validation_enabled: true
  https_enabled: false

monitoring:
  prometheus_enabled: true
  metrics_path: /metrics

logging:
  level: INFO
  format: json
```

### 3.4 中间件接入规范

**中间件顺序**（从外到内）：
1. **CORS 中间件**：处理跨域请求
2. **日志中间件**：记录请求日志
3. **认证中间件**：验证用户身份（可选）
4. **验证中间件**：校验请求参数（可选）
5. **速率限制中间件**：防止滥用（可选）
6. **业务处理器**：实际的路由处理函数

**中间件集成示例**：
```python
async def create_app(config: Dict[str, Any]) -> web.Application:
    """创建应用实例"""
    service = MonitoringAlertingService(config)

    # 可选中间件
    middlewares = []

    # 认证中间件（通过环境变量控制）
    if os.getenv('ENABLE_AUTH', 'false').lower() == 'true':
        from auth import create_auth_middleware
        middlewares.append(create_auth_middleware())

    # 验证中间件（通过环境变量控制）
    if os.getenv('ENABLE_VALIDATION', 'true').lower() == 'true':
        from validation import create_validation_middleware
        middlewares.append(create_validation_middleware())

    # 将中间件添加到应用
    for middleware in middlewares:
        service.app.middlewares.append(middleware)

    return service.app
```

**路由白名单**（无需认证）：
- `/health`
- `/metrics`
- `/api/v1/status`（只读）
- `/login`（获取 Bearer Token）

**路由需要认证**：
- POST/PUT/DELETE 操作
- 敏感数据查询

### 3.5 错误处理与日志规范

**错误处理原则**：
1. **捕获所有异常**：不允许未捕获的异常导致服务崩溃
2. **分类处理**：区分业务错误、系统错误、外部依赖错误
3. **友好提示**：返回清晰的错误信息，不暴露内部实现细节
4. **记录日志**：所有错误必须记录日志，包含上下文信息

**错误处理示例**：
```python
async def handle_alert_query(request: web.Request) -> web.Response:
    """查询告警列表"""
    try:
        # 业务逻辑
        alerts = await self.get_alerts()
        return self.success_response(alerts)

    except ValueError as e:
        # 业务错误（400）
        logger.warning(f"参数错误: {e}", extra={"request_id": request.get('request_id')})
        return self.error_response(
            code="INVALID_PARAMETER",
            message=str(e),
            status=400
        )

    except Exception as e:
        # 系统错误（500）
        logger.error(f"查询告警失败: {e}", exc_info=True, extra={"request_id": request.get('request_id')})
        return self.error_response(
            code="INTERNAL_ERROR",
            message="服务器内部错误",
            status=500
        )
```

**日志规范**：

**日志级别**：
- **DEBUG**: 详细的调试信息（开发环境）
- **INFO**: 关键业务流程（如服务启动、请求处理）
- **WARNING**: 警告信息（如参数错误、降级运行）
- **ERROR**: 错误信息（如异常、失败）
- **CRITICAL**: 严重错误（如服务无法启动）

**日志格式**（结构化日志）：
```json
{
  "timestamp": "2025-10-20T22:50:45.123Z",
  "level": "INFO",
  "logger": "monitoring-alerting",
  "message": "处理告警查询请求",
  "request_id": "abc123",
  "user_id": "user123",
  "duration_ms": 15,
  "status_code": 200
}
```

**日志记录示例**：
```python
import structlog

logger = structlog.get_logger()

# 记录请求
logger.info(
    "处理告警查询请求",
    request_id=request_id,
    method=request.method,
    path=request.path,
    query_params=dict(request.query)
)

# 记录错误
logger.error(
    "查询告警失败",
    request_id=request_id,
    error=str(e),
    exc_info=True
)
```

### 3.6 测试规范

**测试分类**：
1. **单元测试**：测试单个函数或类（tests/unit/）
2. **集成测试**：测试服务间集成（tests/integration/）
3. **端到端测试**：测试完整流程（tests/e2e/）

**测试覆盖率要求**：
- 核心业务逻辑：> 80%
- 工具函数：> 70%
- 整体覆盖率：> 70%

**单元测试示例**：
```python
import pytest
from services.monitoring_alerting.main import MonitoringAlertingService

@pytest.fixture
async def service():
    """创建测试服务实例"""
    config = {'port': 8082, 'host': '0.0.0.0'}
    service = MonitoringAlertingService(config)
    await service.on_startup()
    yield service
    await service.on_shutdown()

@pytest.mark.asyncio
async def test_get_alerts(service):
    """测试查询告警列表"""
    alerts = await service.get_alerts()
    assert isinstance(alerts, list)
    assert len(alerts) >= 0

@pytest.mark.asyncio
async def test_create_alert(service):
    """测试创建告警"""
    alert_data = {
        'name': 'Test Alert',
        'severity': 'high',
        'message': 'Test message'
    }
    alert = await service.create_alert(alert_data)
    assert alert['name'] == 'Test Alert'
    assert alert['severity'] == 'high'
```

**集成测试示例**：
```python
import pytest
from aiohttp.test_utils import AioHTTPTestCase
from services.monitoring_alerting.main import create_app

class TestMonitoringAPI(AioHTTPTestCase):
    """监控告警 API 集成测试"""

    async def get_application(self):
        """获取测试应用"""
        config = {'port': 8082, 'host': '0.0.0.0'}
        return await create_app(config)

    async def test_health_endpoint(self):
        """测试健康检查端点"""
        resp = await self.client.get('/health')
        assert resp.status == 200
        data = await resp.json()
        assert data['status'] == 'healthy'

    async def test_alerts_api(self):
        """测试告警 API"""
        resp = await self.client.get('/api/v1/alerts')
        assert resp.status == 200
        data = await resp.json()
        assert 'data' in data
        assert isinstance(data['data'], list)
```

**测试运行命令**：
```bash
# 使用 pytest（如项目采用 pytest）
# 运行所有测试
pytest tests/
# 运行单元测试
pytest tests/unit/
# 运行集成测试
pytest tests/integration/
# 生成覆盖率报告
pytest --cov=services/monitoring-alerting --cov-report=html tests/
```

**unittest 运行命令（本模块推荐）**：
```bash
# 由于目录名包含连字符，建议按路径直接运行集成测试
python3 -m unittest -v services/monitoring-alerting/tests/integration/test_service.py
# 或显式指定发现目录与模式
python3 -m unittest discover -v -s services/monitoring-alerting/tests/integration -p 'test_*.py'
```

### 3.7 部署规范

**Docker 部署**：

**Dockerfile 规范**：
- 使用官方 Python 镜像（python:3.12-slim）
- 最小化镜像大小（清理 apt 缓存）
- 使用非 root 用户运行
- 设置健康检查
- 正确设置 PYTHONPATH

**docker-compose.yml 规范**：
- 使用环境变量引用敏感信息
- 设置资源限制（CPU/内存）
- 配置健康检查
- 使用命名卷持久化数据
- 配置网络隔离

**健康检查规范**：
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8082/health"]
  interval: 30s
  timeout: 10s
  start_period: 5s
  retries: 3
```

**部署流程**：
1. 构建镜像：`docker build -t marketprism-monitoring:2.0.0 .`
2. 启动服务：`docker compose up -d`
3. 验证健康：`docker compose ps` 确认所有容器 healthy
4. 查看日志：`docker compose logs -f`
5. 停止服务：`docker compose down`

### 3.8 监控与告警规范

**Prometheus 指标规范**：

**指标命名**：
```
<namespace>_<subsystem>_<metric_name>_<unit>

示例:
marketprism_monitoring_http_requests_total
marketprism_monitoring_alert_processing_duration_seconds
marketprism_monitoring_active_alerts_count
```

**指标类型**：
- **Counter**: 累计值（如请求总数、错误总数）
- **Gauge**: 瞬时值（如活跃告警数、内存使用）
- **Histogram**: 分布统计（如响应时间分布）
- **Summary**: 分位数统计（如 P95/P99 响应时间）

**必须暴露的指标**：
```
# 服务基础指标
marketprism_monitoring_up{service="monitoring-alerting"}
marketprism_monitoring_http_requests_total{method="GET",path="/api/v1/alerts",status="200"}
marketprism_monitoring_http_request_duration_seconds{method="GET",path="/api/v1/alerts"}

# 业务指标
marketprism_monitoring_active_alerts_total{severity="high"}
marketprism_monitoring_alert_rules_total{enabled="true"}
marketprism_monitoring_components_healthy{component="collector"}
```

**告警规则规范**：

**告警命名**：
```
<Severity><Component><Condition>

示例:
CriticalCollectorDown
HighHotStorageInsertErrors
WarningColdStorageReplicationLag
```

**告警标签**：
```yaml
labels:
  severity: critical|high|medium|low
  component: collector|hot-storage|cold-storage|broker
  category: availability|performance|capacity
```

**告警注解**：
```yaml
annotations:
  summary: "简短描述"
  description: "详细描述，包含当前值和阈值"
  runbook_url: "故障排查文档链接"
```

**告警规则示例**：
```yaml
groups:
  - name: marketprism_services
    interval: 30s
    rules:
      - alert: CriticalCollectorDown
        expr: up{job="collector"} == 0
        for: 1m
        labels:
          severity: critical
          component: collector
          category: availability
        annotations:
          summary: "数据采集服务不可用"
          description: "collector 服务已停止响应超过 1 分钟"
          runbook_url: "https://wiki.example.com/runbook/collector-down"
```

### 3.9 安全规范

**认证机制**：
1. **API Key 认证**：通过 `X-API-Key` 请求头传递
2. **Basic Auth**：通过 `Authorization: Basic <base64>` 传递
3. **Token 认证**：通过 `Authorization: Bearer <token>` 传递

**密钥管理**：
1. **生成强密钥**：至少 32 字符，包含大小写字母、数字、特殊字符
2. **定期轮换**：每 90 天轮换一次
3. **安全存储**：使用环境变量或密钥管理服务（如 Vault）
4. **最小权限**：每个密钥只授予必要的权限

**HTTPS 配置**：
```python
# 生产环境必须启用 HTTPS
ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
ssl_context.load_cert_chain('cert.pem', 'key.pem')

# 启动服务
await web._run_app(app, host='0.0.0.0', port=8443, ssl_context=ssl_context)
```

**速率限制**：
```python
# 默认限制：每个 IP 每分钟 100 请求
rate_limit = {
    'requests_per_minute': 100,
    'burst': 20
}
```

**安全检查清单**：
- [ ] 所有敏感信息使用环境变量
- [ ] 生产环境启用 HTTPS
- [ ] 生产环境启用认证
- [ ] 启用速率限制
- [ ] 输入参数校验
- [ ] SQL 注入防护
- [ ] XSS 防护
- [ ] CORS 配置正确
- [ ] 日志不包含敏感信息
- [ ] 错误信息不暴露内部实现

---

## 📝 附录

### A. 快速开始指南

**场景 1：本地开发（仅启动服务）**
```bash
# 1. 进入模块目录
cd /home/ubuntu/marketprism/services/monitoring-alerting

# 2. 启动服务
python main.py

# 3. 验证
curl http://localhost:8082/health
curl http://localhost:8082/metrics
curl http://localhost:8082/api/v1/alerts
```

**场景 2：完整监控栈部署**
```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env，填入真实的 DingTalk token 和 secret

# 2. 启动监控栈
docker compose up -d

# 3. 验证
docker compose ps  # 确认所有容器 healthy
curl http://localhost:9090/targets  # Prometheus targets
curl http://localhost:3000  # Grafana (admin/admin)

# 4. 查看日志
docker compose logs -f prometheus
docker compose logs -f grafana

# 5. 停止
docker compose down
```

### B. 故障排查指南

**问题 1：服务无法启动**
```
错误: AttributeError: 'MonitoringAlertingService' object has no attribute 'start'
解决: 确保已应用阶段 1 的修复（使用 run() 而非 start()）
```

**问题 2：Prometheus 无法抓取指标**
```
错误: context deadline exceeded
原因: 目标服务未启动或端口不正确
解决:
  1. 确认目标服务已启动
  2. 检查端口配置（collector:9092, hot:9094, cold:9095, broker:9096）
  3. 检查防火墙规则
```

**问题 3：Grafana 无数据**
```
原因: Prometheus 数据源未配置或查询错误
解决:
  1. 访问 Grafana → Configuration → Data Sources
  2. 确认 Prometheus 数据源存在且可访问
  3. 测试查询: up{job="collector"}
```

**问题 4：DingTalk 未收到告警**
```
原因: Webhook URL 或 Secret 配置错误
解决:
  1. 检查 .env 文件中的 DINGTALK_WEBHOOK_URL 和 DINGTALK_SECRET
  2. 测试 Webhook: curl -X POST <webhook_url> -d '{"msgtype":"text","text":{"content":"test"}}'
  3. 检查 Alertmanager 日志: docker compose logs alertmanager
```

### C. 性能调优建议

**服务性能优化**：
1. 启用 uvloop（已在 requirements.txt 中）
2. 调整 aiohttp 连接池大小
3. 使用 orjson 替代标准 json（已在 requirements.txt 中）
4. 启用 gzip 压缩

**Prometheus 性能优化**：
1. 调整 scrape_interval（默认 15s，可根据需求调整）
2. 设置合理的 retention 时间（默认 15 天）
3. 启用远程存储（如 Thanos、Cortex）用于长期存储

**Grafana 性能优化**：
1. 使用查询缓存
2. 限制时间范围
3. 使用变量和模板
4. 避免过于复杂的查询

### D. 参考资源

**官方文档**：
- [Prometheus 官方文档](https://prometheus.io/docs/)
- [Grafana 官方文档](https://grafana.com/docs/)
- [Alertmanager 官方文档](https://prometheus.io/docs/alerting/latest/alertmanager/)
- [aiohttp 官方文档](https://docs.aiohttp.org/)

**项目内部文档**：
- `/home/ubuntu/marketprism/services/monitoring-alerting/README.md`
- `/home/ubuntu/marketprism/core/service_framework.py`
- `/home/ubuntu/marketprism/core/config/`

**相关服务**：
- data-collector: `/home/ubuntu/marketprism/services/data-collector`
- hot-storage-service: `/home/ubuntu/marketprism/services/hot-storage-service`
- cold-storage-service: `/home/ubuntu/marketprism/services/cold-storage-service`
- message-broker: `/home/ubuntu/marketprism/services/message-broker`

---

## 🎯 总结

本开发计划基于对 monitoring-alerting 模块的深度分析和实际验证，明确了：

1. **当前状态**：服务代码基本完整，但存在 3 个阻塞运行的 P0 bug
2. **核心问题**：main.py 调用不存在的 start/stop 方法，导致服务无法启动
3. **修复策略**：分阶段修复（P0 → P1 → P2），优先保证基础功能可用
4. **开发原则**：基于实际状态、避免过度设计、保持简单性、符合项目约定

**下一步行动**：
1. ✅ 完成阶段 0 验证（已完成）
2. 🎯 执行阶段 1 P0 修复（预计 0.5 天）
3. 🔒 执行阶段 2 P1 增强（可选，预计 1 天）
4. 📈 执行阶段 3 P2 完善（可选，预计 1-2 天）

**成功标准**：
- 服务可以正常启动并响应请求
- 监控栈可以完整部署并工作
- 文档准确且完整
- 测试覆盖率达标

---

**文档维护**：
- 本文档应随着开发进度更新
- 每个阶段完成后，更新对应的状态标记
- 发现新问题时，及时补充到相应章节
- 定期审查并优化规范内容


