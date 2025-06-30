# MarketPrism 项目清理分析报告

## 📊 **第一步：项目依赖分析结果**

### **核心生产组件（必须保留）**
1. **Data Collector Service** (`services/data-collector/`)
   - 端口: 8081
   - 功能: 多交易所数据收集、实时WebSocket、数据标准化
   - 状态: ✅ 核心服务，包含最新的Deribit波动率指数集成

2. **NATS Message Broker** 
   - 端口: 4222
   - 功能: 高性能消息队列、流处理
   - 状态: ✅ 核心基础设施

3. **ClickHouse Database**
   - 端口: 9000
   - 功能: 时序数据存储、高性能查询
   - 状态: ✅ 核心存储

4. **Redis Cache**
   - 端口: 6379
   - 功能: 缓存、会话存储
   - 状态: ✅ 核心缓存

### **数据处理层（必须保留）**
- **统一数据标准化器** - 支持Binance、OKX、Deribit
- **波动率指数处理** - 最新集成的Deribit功能
- **交易数据处理** - 核心业务逻辑
- **多空比数据处理** - 市场情绪分析

### **支持服务（部分保留）**
1. **API Gateway** (端口: 8080) - ✅ 保留
2. **Message Broker Service** (端口: 8086) - ✅ 保留
3. **Monitoring Alerting** (端口: 8084) - ✅ 保留
4. **Task Worker** (端口: 8087) - ✅ 保留

### **配置管理（必须保留）**
- `config/nats_unified_streams.yaml` - 统一NATS流配置
- `config/clickhouse/*.sql` - 数据库表结构
- `config/exchanges.yaml` - 交易所配置
- `config/services.yaml` - 服务配置

## 📁 **第二步：文件分类分析**

### **1. 文档分类 (`docs/`目录)**

#### **🟢 高价值文档（必须保留）**
- `unified-configuration-guide.md` - 统一配置指南
- `unified-trade-data-normalizer.md` - 交易数据标准化器文档
- `api-usage-examples-unified.md` - API使用示例
- `best-practices-unified.md` - 最佳实践指南
- `data-collector-technical-documentation.md` - 数据收集器技术文档
- `architecture/overview.md` - 架构概述
- `deployment/PRODUCTION_DEPLOYMENT_GUIDE.md` - 生产部署指南
- `references/faq.md` - 常见问题

#### **🟡 中等价值文档（选择性保留）**
- `market-long-short-ratio-normalizer.md` - 市场多空比标准化器
- `top-trader-long-short-ratio-normalizer.md` - 大户持仓比标准化器
- `liquidation-order-processing-guide.md` - 强平订单处理指南
- `port-allocation-standard.md` - 端口分配标准
- `service-naming-standards.md` - 服务命名标准

#### **🔴 低价值文档（建议删除）**
- `stage9-*.md` - 阶段性报告文档
- `stage10-*.md` - 阶段性报告文档
- `test-coverage-stage*.md` - 测试覆盖率报告
- `project-delivery-report.md` - 项目交付报告
- `PROJECT_DELIVERY_FINAL_REPORT.md` - 最终交付报告
- `marketprism-project-refactoring-completion-report.md` - 重构完成报告
- `services-consistency-verification-report.md` - 服务一致性验证报告
- `config-factory-*.md` - 配置工厂相关文档
- `monitoring-alerting-*.md` - 监控告警相关报告
- `development/tdd_*.md` - TDD相关文档
- `testing/TDD_*.md` - TDD测试文档
- `frontend-handover/` - 前端交接文档（已过时）
- `NAS_DEPLOYMENT.md` - NAS部署文档（特定环境）
- `api-proxy-*.md` - API代理文档（功能已整合）

#### **🔴 重复文档（建议删除）**
- `api-usage-examples.md` (保留unified版本)
- `deployment-configuration.md` vs `deployment-checklist.md`
- `architecture/project-description-legacy.md` (legacy版本)
- `deployment/local-deployment-legacy.md` (legacy版本)

### **2. 测试文件分析 (`tests/`目录)**

#### **🟢 有效测试（必须保留）**
- `tests/unit/services/data_collector/` - 数据收集器单元测试
- `tests/integration/test_live_exchange_apis.py` - 交易所API集成测试
- `tests/conftest.py` - 测试配置
- `tests/fixtures/` - 测试夹具

#### **🔴 过时测试（建议删除）**
- `TDD_*.md` - TDD相关文档
- `TEST_EXECUTION_GUIDE.md` - 测试执行指南（过时）
- `reports/` - 测试报告（临时文件）

### **3. 配置文件分析 (`config/`目录)**

#### **🟢 核心配置（必须保留）**
- `nats_unified_streams.yaml` - 统一NATS流配置
- `exchanges.yaml` - 交易所配置
- `services.yaml` - 服务配置
- `clickhouse/*.sql` - 数据库表结构
- `trade_data_pipeline_config.yaml` - 数据管道配置

#### **🟡 环境配置（选择性保留）**
- `environments/` - 环境配置
- `prometheus/` - Prometheus配置
- `grafana/` - Grafana配置

#### **🔴 过时配置（建议删除）**
- `collector_config.yaml` - 已删除
- `collector_with_*.yaml` - 已删除
- `nats_base.yaml` - 已删除
- `test_*.yaml` - 测试配置（临时）

### **4. 脚本和工具分析 (`scripts/`目录)**

#### **🟢 核心脚本（必须保留）**
- `deployment/` - 部署脚本
- `clickhouse/` - ClickHouse初始化脚本
- `setup_*.sh` - 环境设置脚本

#### **🔴 临时脚本（建议删除）**
- `fix_*.sh` - 修复脚本（临时）
- `emergency_*.sh` - 紧急修复脚本（临时）
- `auto-fix-*.sh` - 自动修复脚本（临时）
- `quick_*.sh` - 快速脚本（调试用）

## 🎯 **清理建议**

### **立即删除**
1. 所有阶段性报告文档 (`stage*.md`)
2. TDD相关文档和报告
3. 前端交接文档
4. 临时修复脚本
5. 重复的配置文件
6. 过时的测试报告

### **保留并整理**
1. 核心技术文档
2. API使用指南
3. 生产部署文档
4. 有效的单元测试和集成测试
5. 核心配置文件

### **需要更新**
1. README.md - 反映最新架构
2. 架构文档 - 包含Deribit波动率指数集成
3. 部署指南 - 更新端口分配和服务配置
