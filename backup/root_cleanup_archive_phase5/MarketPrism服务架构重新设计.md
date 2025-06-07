# MarketPrism 服务架构重新设计方案

## 设计原则

### 1. 分层架构原则
```
应用层 (Services)     - 业务逻辑组合者，依赖core层
基础设施层 (Core)      - 可复用的技术能力
```

### 2. 微服务职责划分
- **单一责任**：每个服务只负责一个业务域
- **高内聚低耦合**：服务内部功能相关性强，服务间依赖最小
- **技术栈独立**：每个服务可选择最适合的技术

## 建议的服务架构

### 📊 核心业务服务层 (Business Services)

#### 1. 🔄 **market-data-collector** 
**职责**：市场数据收集和预处理
```yaml
功能:
  - 连接各大交易所API/WebSocket
  - 数据标准化和清洗
  - 实时数据流处理
  - 数据质量验证

依赖的core组件:
  - core/networking/unified_session_manager
  - core/storage/unified_clickhouse_writer  
  - core/monitoring (指标上报)
  - core/reliability (重试和容错)

输出:
  - 标准化市场数据 → message-broker
  - 数据质量指标 → monitoring-service
```

#### 2. 🗄️ **data-storage-service**
**职责**：数据存储生命周期管理
```yaml
功能:
  - 热数据存储 (实时查询)
  - 冷数据归档 (历史数据)
  - 数据生命周期策略执行
  - 存储性能优化

依赖的core组件:
  - core/storage/unified_storage_manager
  - core/operations (自动化运维)
  - core/monitoring (存储监控)

特点:
  - 纯数据管理，不含业务逻辑
  - 提供标准化数据访问API
  - 自动化数据归档和清理
```

#### 3. 🌐 **api-gateway-service**
**职责**：外部API统一入口
```yaml
功能:
  - 请求路由和负载均衡
  - 认证和授权
  - 限流和熔断
  - API版本管理

依赖的core组件:
  - core/networking (连接管理)
  - core/security (认证授权)
  - core/monitoring (请求监控)
  - core/middleware (中间件)

特点:
  - 无状态服务
  - 高可用性设计
  - 统一错误处理
```

### 🔧 基础设施服务层 (Infrastructure Services)

#### 4. 📊 **monitoring-service**
**职责**：系统监控和告警
```yaml
功能:
  - 指标收集和聚合
  - 健康检查和故障检测
  - 智能告警和通知
  - 监控仪表板

技术栈:
  - Prometheus + Grafana + AlertManager
  - 集成core/monitoring组件
  - 支持自定义指标

部署模式:
  - 独立部署，服务无关性
  - 可选：嵌入式agent到各服务
```

#### 5. 📨 **message-broker-service**  
**职责**：异步消息通信
```yaml
功能:
  - 消息路由和分发
  - 消息持久化
  - 消费者组管理
  - 消息重试和死信处理

技术选型:
  - NATS (轻量级，高性能)
  - 或 Apache Kafka (高吞吐量)

特点:
  - 服务解耦的关键组件
  - 支持多种消息模式
```

#### 6. ⏰ **scheduler-service**
**职责**：分布式任务调度
```yaml
功能:
  - Cron表达式调度
  - 分布式任务协调
  - 任务失败重试
  - 调度历史和监控

依赖的core组件:
  - core/operations (操作自动化)
  - core/reliability (故障恢复)

任务类型:
  - 数据归档任务
  - 系统维护任务  
  - 数据质量检查
  - 性能报告生成
```

## 服务间通信设计

### 1. 同步通信 (REST/gRPC)
```yaml
适用场景:
  - API Gateway → 各业务服务
  - 实时查询请求
  - 配置管理操作

通信模式:
  - HTTP/REST: 外部API和管理接口
  - gRPC: 内部服务高性能通信
```

### 2. 异步通信 (Message Broker)
```yaml
适用场景:
  - market-data-collector → data-storage-service
  - 事件通知和状态同步
  - 批量数据处理

消息类型:
  - 市场数据流: collector → storage
  - 系统事件: 各服务 → monitoring
  - 调度任务: scheduler → 各业务服务
```

### 3. 配置管理
```yaml
方案: 集中式配置中心
  - 基于 core/config 扩展
  - 支持动态配置更新
  - 环境隔离和版本管理

配置分层:
  - 全局配置 (数据库连接等)
  - 服务专属配置
  - 环境特定配置
```

## 部署架构选择

### 方案A: 渐进式部署 (推荐)
```yaml
阶段1: 单体重构
  - 保持现有结构，重构为模块化单体
  - 完善core层基础设施
  - 明确服务边界

阶段2: 选择性拆分  
  - 先拆分无状态服务 (api-gateway, monitoring)
  - 再拆分核心业务服务 (collector, storage)
  - 最后拆分基础设施服务

阶段3: 全微服务化
  - 独立部署和扩展
  - 服务网格引入 (可选)
  - 自动化运维完善
```

### 方案B: 混合架构
```yaml
核心计算: 单体 (collector + storage)
  - 高性能数据处理
  - 减少网络开销
  - 简化事务管理

独立服务: 微服务
  - monitoring-service
  - scheduler-service  
  - api-gateway-service

优势:
  - 平衡性能和架构灵活性
  - 降低运维复杂度
  - 适合中等规模团队
```

## 与现有Core架构的关系

### Core层职责 (基础设施能力)
```python
core/
├── networking/     # 网络连接管理 (供所有服务使用)
├── storage/        # 存储抽象层 (供data-storage-service使用)
├── monitoring/     # 监控SDK (供所有服务集成)
├── security/       # 安全组件 (供api-gateway等使用)
├── operations/     # 运维自动化 (供scheduler-service使用)
├── reliability/    # 可靠性保障 (供所有服务使用)
└── middleware/     # 通用中间件 (供所有服务使用)
```

### Service层职责 (业务能力组合)
```python
services/
├── market-data-collector/    # 业务逻辑 + core组件组合
├── data-storage-service/     # 业务逻辑 + core/storage
├── api-gateway-service/      # 业务逻辑 + core/networking
├── monitoring-service/       # 业务逻辑 + core/monitoring
├── scheduler-service/        # 业务逻辑 + core/operations
└── message-broker-service/   # 独立中间件服务
```

## 总结优势

### 1. 清晰的职责边界
- Core层：技术能力沉淀
- Service层：业务逻辑组合
- 避免重复开发

### 2. 渐进式演进
- 可以从单体开始
- 根据需要逐步拆分
- 降低迁移风险

### 3. 技术栈灵活性
- 每个服务可选择最适合的技术
- Core层提供标准化能力
- 新技术集成容易

### 4. 运维友好
- 标准化的监控和日志
- 统一的配置管理
- 自动化的部署和扩展

这个架构设计既保持了微服务的灵活性，又避免了过度拆分的复杂性，同时充分利用了现有的core基础设施投入。