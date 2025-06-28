# MarketPrism 统一配置工厂架构设计

## 1. 配置架构分析总结

### 1.1 当前配置结构问题
- **配置分散**: 配置文件分布在多个目录，缺乏统一管理
- **依赖复杂**: 服务间配置依赖关系不清晰
- **环境混乱**: 缺乏清晰的环境分离机制
- **格式不统一**: 混合使用YAML、Python、JSON等格式
- **重复配置**: 多个服务存在重复的配置项

### 1.2 核心模块配置依赖
```
监控告警服务 ← Redis + ClickHouse + 告警规则
前端仪表板 ← API连接 + 环境变量
数据收集器 ← 交易所配置 + NATS + 存储
基础设施 ← Docker + K8s + 监控组件
安全认证 ← JWT + API密钥 + SSL证书
```

## 2. 新配置架构设计

### 2.1 目录结构设计
```
config/
├── core/                           # 核心配置
│   ├── base.yaml                   # 基础配置
│   ├── security.yaml               # 安全配置
│   └── logging.yaml                # 日志配置
├── environments/                   # 环境配置
│   ├── development.yaml            # 开发环境
│   ├── staging.yaml                # 测试环境
│   ├── production.yaml             # 生产环境
│   └── local.yaml                  # 本地环境
├── services/                       # 服务配置
│   ├── monitoring-alerting/        # 监控告警服务
│   │   ├── service.yaml            # 服务基础配置
│   │   ├── alerting.yaml           # 告警配置
│   │   ├── anomaly-detection.yaml  # 异常检测配置
│   │   └── failure-prediction.yaml # 故障预测配置
│   ├── frontend-dashboard/         # 前端仪表板
│   │   ├── service.yaml            # 服务配置
│   │   ├── api-client.yaml         # API客户端配置
│   │   └── ui-settings.yaml        # UI设置
│   ├── data-collector/             # 数据收集器
│   │   ├── service.yaml            # 服务配置
│   │   ├── exchanges.yaml          # 交易所配置
│   │   └── streams.yaml            # 数据流配置
│   └── api-gateway/                # API网关
│       ├── service.yaml            # 服务配置
│       ├── routing.yaml            # 路由配置
│       └── rate-limiting.yaml      # 限流配置
├── infrastructure/                 # 基础设施配置
│   ├── databases/                  # 数据库配置
│   │   ├── redis.yaml              # Redis配置
│   │   ├── clickhouse.yaml         # ClickHouse配置
│   │   └── postgresql.yaml         # PostgreSQL配置
│   ├── messaging/                  # 消息系统配置
│   │   ├── nats.yaml               # NATS配置
│   │   └── kafka.yaml              # Kafka配置
│   ├── monitoring/                 # 监控配置
│   │   ├── prometheus.yaml         # Prometheus配置
│   │   ├── grafana.yaml            # Grafana配置
│   │   └── jaeger.yaml             # Jaeger配置
│   └── deployment/                 # 部署配置
│       ├── docker-compose.yaml     # Docker Compose配置
│       ├── kubernetes.yaml         # Kubernetes配置
│       └── nginx.yaml              # Nginx配置
├── schemas/                        # 配置模式定义
│   ├── service-schema.yaml         # 服务配置模式
│   ├── database-schema.yaml        # 数据库配置模式
│   └── monitoring-schema.yaml      # 监控配置模式
├── templates/                      # 配置模板
│   ├── new-service.yaml.template   # 新服务配置模板
│   ├── database.yaml.template      # 数据库配置模板
│   └── monitoring.yaml.template    # 监控配置模板
└── factory/                        # 配置工厂
    ├── __init__.py                 # 工厂初始化
    ├── config_factory.py           # 配置工厂主类
    ├── loaders/                    # 配置加载器
    │   ├── yaml_loader.py          # YAML加载器
    │   ├── env_loader.py           # 环境变量加载器
    │   └── secret_loader.py        # 密钥加载器
    ├── validators/                 # 配置验证器
    │   ├── schema_validator.py     # 模式验证器
    │   ├── dependency_validator.py # 依赖验证器
    │   └── security_validator.py   # 安全验证器
    └── managers/                   # 配置管理器
        ├── hot_reload_manager.py   # 热重载管理器
        ├── version_manager.py      # 版本管理器
        └── cache_manager.py        # 缓存管理器
```

### 2.2 配置层次结构
```
1. 基础配置 (core/base.yaml)
   ↓
2. 环境配置 (environments/{env}.yaml)
   ↓
3. 服务配置 (services/{service}/*.yaml)
   ↓
4. 基础设施配置 (infrastructure/*/*.yaml)
   ↓
5. 环境变量覆盖
   ↓
6. 运行时配置
```

## 3. 配置工厂核心功能

### 3.1 配置加载策略
- **分层加载**: 按优先级加载配置文件
- **环境隔离**: 根据环境自动选择配置
- **依赖解析**: 自动解析服务间配置依赖
- **变量替换**: 支持环境变量和配置变量替换
- **配置合并**: 智能合并多个配置源

### 3.2 配置验证机制
- **模式验证**: 基于JSON Schema验证配置格式
- **依赖检查**: 验证服务间配置依赖完整性
- **安全检查**: 验证敏感配置的安全性
- **一致性检查**: 确保配置间的一致性

### 3.3 配置管理功能
- **热重载**: 支持配置文件变更时自动重载
- **版本控制**: 配置变更历史和回滚
- **缓存机制**: 提高配置访问性能
- **监控告警**: 配置变更和错误告警

## 4. 实现计划

### 4.1 第一阶段：基础架构搭建
1. 创建新的配置目录结构
2. 实现配置工厂核心类
3. 实现基础的配置加载器
4. 创建配置模式定义

### 4.2 第二阶段：服务配置迁移
1. 迁移监控告警服务配置
2. 迁移前端仪表板配置
3. 迁移数据收集器配置
4. 迁移基础设施配置

### 4.3 第三阶段：高级功能实现
1. 实现配置验证机制
2. 实现热重载功能
3. 实现版本管理
4. 实现监控告警

### 4.4 第四阶段：测试和优化
1. 全面测试配置加载
2. 性能优化
3. 文档完善
4. 部署验证

## 5. 配置示例

### 5.1 基础配置示例 (core/base.yaml)
```yaml
# MarketPrism 基础配置
app:
  name: "MarketPrism"
  version: "1.0.0"
  description: "智能监控告警系统"

# 默认网络配置
network:
  host: "0.0.0.0"
  timeout: 30
  max_connections: 1000

# 默认日志配置
logging:
  level: "INFO"
  format: "json"
  structured: true
```

### 5.2 环境配置示例 (environments/production.yaml)
```yaml
# 生产环境配置
environment: "production"

# 覆盖基础配置
logging:
  level: "WARN"
  file:
    enabled: true
    path: "/var/log/marketprism"

# 生产环境特定配置
security:
  strict_mode: true
  audit_logging: true

performance:
  cache_enabled: true
  batch_processing: true
```

### 5.3 服务配置示例 (services/monitoring-alerting/service.yaml)
```yaml
# 监控告警服务配置
service:
  name: "monitoring-alerting"
  port: 8082
  
# 依赖服务
dependencies:
  - redis
  - clickhouse
  - prometheus

# 健康检查
health_check:
  enabled: true
  endpoint: "/health"
  interval: 30
```

## 6. 迁移策略

### 6.1 渐进式迁移
- 保持现有配置文件兼容
- 逐步迁移到新配置结构
- 提供配置迁移工具
- 确保服务不中断

### 6.2 验证机制
- 配置加载前验证
- 服务启动时验证
- 运行时配置检查
- 自动化测试验证

### 6.3 回滚计划
- 保留配置变更历史
- 支持快速回滚
- 提供配置对比工具
- 监控配置变更影响

这个设计方案将为MarketPrism提供一个统一、可扩展、易维护的配置管理系统。
