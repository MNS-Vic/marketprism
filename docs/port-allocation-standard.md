# MarketPrism 端口分配标准

## 🎯 端口分配原则

### 1. 分段管理
- **8080-8089**: 核心业务服务
- **8090-8099**: 支持服务和工具
- **9000-9099**: 监控和管理服务
- **4000-4999**: 消息队列和数据库
- **3000-3999**: 前端和UI服务

### 2. 命名规范
- 每个服务只能占用一个主端口
- 端口号与服务功能相关联
- 避免随意分配，遵循统一标准

## 📋 标准端口分配表

### 核心业务服务 (8080-8089)
| 端口 | 服务名称 | 服务ID | 功能描述 |
|------|----------|--------|----------|
| 8080 | API Gateway | api-gateway-service | API网关和路由 |
| 8081 | 预留 | - | 核心业务扩展 |
| 8082 | Monitoring Alerting | monitoring-alerting-service | 监控告警服务 |
| 8083 | Data Storage | data-storage-service | 数据存储服务 |
| 8084 | Data Collector | data-collector | 数据收集服务 |
| 8085 | 预留 | - | 核心业务扩展 |
| 8086 | Message Broker | message-broker-service | 消息代理服务 |
| 8087 | Data Storage Hot | data-storage-hot-service | 热数据存储服务 |
| 8088-8089 | 预留 | - | 核心业务扩展 |

### 支持服务 (8090-8099)
| 端口 | 服务名称 | 服务ID | 功能描述 |
|------|----------|--------|----------|
| 8090 | Task Worker | task-worker-service | 任务工作者 |
| 8091-8099 | 预留 | - | 支持服务扩展 |
| 8093 | 预留 | - | 支持服务扩展 |
| 8094 | 预留 | - | 支持服务扩展 |
| 8095 | 预留 | - | 支持服务扩展 |
| 8096 | 预留 | - | 支持服务扩展 |
| 8097 | 预留 | - | 支持服务扩展 |
| 8098 | 预留 | - | 支持服务扩展 |
| 8099 | 预留 | - | 支持服务扩展 |

### 监控管理服务 (9000-9099)
| 端口 | 服务名称 | 服务ID | 功能描述 |
|------|----------|--------|----------|
| 9000-9089 | 预留 | - | 监控服务扩展 |
| 9090 | Prometheus | prometheus | 指标收集 |
| 9091 | Grafana | grafana | 可视化面板 |
| 9092 | 预留 | - | 监控服务扩展 |

### 基础设施服务 (4000-4999)
| 端口 | 服务名称 | 服务ID | 功能描述 |
|------|----------|--------|----------|
| 4222 | NATS | nats | 消息队列 |
| 4223 | NATS Monitoring | nats-monitoring | NATS监控 |
| 5432 | PostgreSQL | postgres | 关系数据库 |
| 6379 | Redis | redis | 缓存数据库 |
| 8123 | ClickHouse HTTP | clickhouse | 时序数据库HTTP |
| 9000 | ClickHouse TCP | clickhouse | 时序数据库TCP |

### 前端UI服务 (3000-3999)
| 端口 | 服务名称 | 服务ID | 功能描述 |
|------|----------|--------|----------|
| 3000 | Market Prism Dashboard | market-prism-dashboard | 主要UI界面 |
| 3001 | Admin Dashboard | admin-dashboard | 管理界面 |
| 3002 | 预留 | - | UI服务扩展 |

## 🔧 端口冲突解决方案

### 当前冲突修复
1. **monitoring-service**: 8082 → 9000
2. **monitoring-dashboard**: 8086 → 9001  
3. **strategy-management**: 8087 → 8086
4. **data-migration-service**: 保持8087 → 8087

### 实施步骤
1. 更新 `config/services.yaml` 配置
2. 更新 `docker-compose.yml` 端口映射
3. 更新各服务的Dockerfile EXPOSE指令
4. 更新健康检查和服务发现配置
5. 更新文档和部署脚本

## 📝 端口分配规则

### 分配新端口时
1. 查阅此文档确认端口可用性
2. 按照服务类型选择对应端口段
3. 更新此文档记录新分配
4. 更新相关配置文件

### 端口冲突检测
```bash
# 检查端口占用
netstat -tlnp | grep :8080

# 检查Docker容器端口
docker ps --format "table {{.Names}}\t{{.Ports}}"

# 检查配置文件冲突
grep -r "port.*8080" config/
```

## 🚀 自动化工具

### 端口冲突检测脚本
```bash
#!/bin/bash
# scripts/check-port-conflicts.sh
echo "检查MarketPrism端口冲突..."
grep -r "port:" config/services.yaml | sort | uniq -d
```

### 端口分配验证
```bash
#!/bin/bash
# scripts/validate-port-allocation.sh
echo "验证端口分配标准合规性..."
# 实现端口分配验证逻辑
```

---

**遵循此标准可以确保MarketPrism系统的端口分配清晰、有序、无冲突。**
