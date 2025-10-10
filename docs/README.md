# MarketPrism 文档中心

> 最后更新：2025-01-27

欢迎来到 MarketPrism 文档中心！这里包含了项目的完整技术文档，帮助您快速了解、部署和开发 MarketPrism 系统。

## 📚 文档导航

### 🚀 快速开始
- **[快速开始指南](getting-started/quick-start.md)** - 5分钟快速启动系统
- **[安装指南](getting-started/installation.md)** - 详细的安装步骤
- **[基础配置](getting-started/configuration.md)** - 基本配置说明

### 🏗️ 系统架构
- **[架构概述](architecture/overview.md)** - 系统整体架构和设计理念
- **[数据流设计](architecture/data-flow.md)** - 数据处理流程
- **[服务说明](architecture/services.md)** - 各服务组件详细说明
- **[数据库设计](architecture/database-schema.md)** - 数据库结构设计

### 🚢 部署指南
- **[本地开发环境](deployment/local-development.md)** - 本地开发环境搭建
- **[Docker 部署](deployment/docker-deployment.md)** - 容器化部署方案
- **[生产环境部署](deployment/production.md)** - 生产环境部署指南
- **[监控配置](deployment/monitoring.md)** - 监控系统配置

### 💻 开发文档
- **[编码规范](development/coding-standards.md)** - 代码规范和最佳实践
- **[数据标准化规范](development/data-normalization.md)** - 数据标准化技术规范
- **[TDD方法论指南](development/tdd_methodology_guide.md)** - 测试驱动开发完全指南
- **[测试指南](development/testing.md)** - 测试策略和方法
- **[贡献指南](development/contributing.md)** - 如何贡献代码

### 🔧 运维指南
- **[故障排除](operations/troubleshooting.md)** - 常见问题和解决方案
- **[性能调优](operations/performance-tuning.md)** - 系统性能优化
- **[备份恢复](operations/backup-recovery.md)** - 数据备份和恢复
- **[安全配置](operations/security.md)** - 安全配置指南

### 📡 API 文档
- **[REST API](api/rest-api.md)** - REST API 接口文档
- **[WebSocket API](api/websocket-api.md)** - WebSocket 接口文档
- **[数据格式](api/data-formats.md)** - 数据格式说明

### 📖 参考资料
- **[术语表](references/glossary.md)** - 技术术语解释
- **[常见问题](references/faq.md)** - 常见问题解答
- **[外部链接](references/external-links.md)** - 相关外部资源

### 📜 历史文档
- **[迁移报告](history/migration-reports/)** - 系统迁移和重构记录
- **[优化报告](history/optimization-reports/)** - 性能优化历程
- **[TDD 报告](history/tdd-reports/)** - 测试驱动开发实施记录

## 🎯 文档使用指南

### 新用户推荐路径
1. **了解系统** → [架构概述](architecture/overview.md)
2. **快速体验** → [快速开始指南](getting-started/quick-start.md)
3. **深入学习** → [部署指南](deployment/) 和 [开发文档](development/)

### 开发者推荐路径
1. **环境搭建** → [本地开发环境](deployment/local-development.md)
2. **了解规范** → [编码规范](development/coding-standards.md)
3. **数据处理** → [数据标准化规范](development/data-normalization.md)
4. **贡献代码** → [贡献指南](development/contributing.md)

### 运维人员推荐路径
1. **部署系统** → [生产环境部署](deployment/production.md)
2. **配置监控** → [监控配置](deployment/monitoring.md)
3. **日常维护** → [运维指南](operations/)

## 📊 项目状态

### 当前版本
- **系统版本**: MarketPrism v2.0
- **架构状态**: 生产就绪
- **性能等级**: 高性能 (152.6+ msg/s)
- **可靠性**: 99%+ SLA

### 核心特性
- ✅ **多交易所支持**: Binance、OKX、Deribit
- ✅ **7种数据类型**: 交易、订单簿、行情、资金费率等
- ✅ **企业级监控**: 111+ Prometheus 指标
- ✅ **任务调度**: APScheduler 自动化任务
- ✅ **高性能**: 异步处理，批量操作
- ✅ **可扩展**: 模块化设计，易于扩展

### 技术栈
- **后端**: Python 3.12+, asyncio, Pydantic
- **消息队列**: NATS JetStream
- **数据库**: ClickHouse
- **监控**: Prometheus + Grafana
- **部署**: Docker + Docker Compose


## 🧪 Schema 一致性检查（忽略 TTL）
- 权威 Schema 路径：`services/data-storage-service/config/clickhouse_schema.sql`
- 本地运行检查：
  ```bash
  python3 services/data-storage-service/scripts/validate_schema_consistency.py
  ```
- CI 集成：GitHub Actions 已添加 `Schema Consistency Check` 任务，会启动临时 ClickHouse 实例，应用权威 schema，并执行上述脚本
- manage 脚本集成：`services/data-storage-service/scripts/manage.sh integrity` 会自动执行该检查

## 🔄 文档维护

### 更新频率
- **核心文档**: 随代码变更同步更新
- **API 文档**: 每次接口变更后更新
- **部署文档**: 每月审查和更新
- **历史文档**: 仅归档，不再更新

### 贡献文档
欢迎贡献文档改进！请参考：
1. [贡献指南](development/contributing.md)
2. 提交 Pull Request
3. 文档审查和合并

### 反馈渠道
- **GitHub Issues**: 报告文档问题
- **Pull Requests**: 直接改进文档
- **讨论区**: 技术讨论和建议

## 🆘 获取帮助

### 快速帮助
- **常见问题**: [FAQ](references/faq.md)
- **故障排除**: [故障排除指南](operations/troubleshooting.md)
- **API 问题**: [API 文档](api/)

### 技术支持
- **GitHub Issues**: 技术问题和 Bug 报告
- **讨论区**: 技术讨论和经验分享
- **邮件支持**: technical-support@marketprism.com

### 社区资源
- **官方网站**: https://marketprism.com
- **GitHub 仓库**: https://github.com/your-org/marketprism
- **技术博客**: https://blog.marketprism.com

---

## 📋 文档结构

```
docs/
├── README.md                    # 本文档 - 文档导航中心
├── getting-started/             # 快速开始指南
├── architecture/                # 系统架构文档
├── deployment/                  # 部署指南
├── development/                 # 开发文档
├── operations/                  # 运维指南
├── api/                        # API 文档
├── references/                 # 参考资料
└── history/                    # 历史文档归档
```

**文档中心状态**: ✅ 已整理完成
**文档数量**: 20+ 个核心文档
**覆盖范围**: 从入门到精通的完整技术文档
**维护状态**: 持续更新，与代码同步