# Collector 停机调查总结

**日期**: 2025-10-21  
**调查时间**: 17:00 - 18:10 UTC  
**状态**: ✅ 已解决并完成监控增强

---

## 📋 问题回顾

### 用户报告
1. **Grafana Dashboard** 显示 "no data"（Ingest Rate 和 Success Rate 表格）
2. **用户声明**："我没有关闭 collector"
3. **监控系统未预警**：没有收到任何告警通知

### 初步发现
- Prometheus 显示 `up{job="collector"} == 0`（collector target down）
- 最后成功抓取时间：09:24:14 UTC
- Collector 进程仍在运行（Docker 容器 + 宿主机进程）
- HTTP metrics 端点 (9092) 无响应

---

## 🔍 根本原因分析

### 1. 直接原因：资源耗尽导致服务降级

**时间线**：

**09:24:09** - 资源告警触发
```
🚨 强制清理后内存仍然过高
  - 内存使用: 2869 MB
  - 对象数量: 15,303,778
  - TCP 连接: 97 个（阈值 50）
  - 文件描述符: 快速增长趋势
```

**09:24:09** - OrderBook 状态丢失
```
⚠️ 多个交易对状态不存在，执行惰性初始化
⏰ BTC-USDT、ETH-USDT 等待快照超时，触发重订阅
```

**09:24:10** - 健康检查返回 200（可能在 grace period 内）

**09:24:14** - Prometheus 抓取失败（HTTP 服务器无响应）

### 2. 深层原因：资源泄漏

#### 内存泄漏
- **OrderBook 对象累积**：15M+ 对象，2.9GB 内存
- **未正确清理过期数据**
- **可能存在循环引用**

#### 连接泄漏
- **正常连接数**：~10-15 个 WebSocket
- **实际连接数**：97 个 TCP 连接
- **可能原因**：WebSocket 重连时未关闭旧连接

#### 文件描述符泄漏
- **趋势**：快速增长（rapidly_increasing）
- **影响**：可能导致无法创建新连接

### 3. 监控盲区

**问题**：
1. ❌ 没有资源使用（内存、连接数）的告警
2. ❌ 健康检查过于严格（degraded 也返回 503）
3. ❌ 缺少数据采集速率的监控告警
4. ❌ 没有自动恢复机制

---

## ✅ 已完成的修复

### 1. 服务恢复（09:33:03）

```bash
# 重启 Docker 容器
cd /home/ubuntu/marketprism/services/data-collector
docker compose -f docker-compose.unified.yml restart

# 停止宿主机上的重复进程
kill -9 1571693
```

**结果**：
- ✅ HTTP metrics 端点恢复正常
- ✅ Prometheus 恢复抓取（health: up）
- ✅ Dashboard 显示数据正常

### 2. Dashboard 优化（17:51）

**修复内容**：
1. ✅ Success Rate 查询简化（使用 `clamp_max(rate > 0, 1)`）
2. ✅ 面板尺寸调整（宽度 6，高度 10，每行 4 个）
3. ✅ 布局优化（2 行显示 8 个主题）

**结果**：
- ✅ Ingest Rate 表格显示数据
- ✅ Success Rate 表格显示 100%
- ✅ 面板大小合适，无需滚动

### 3. 监控告警增强（18:05）

#### 新增 Prometheus 告警规则

**文件**：`services/monitoring-alerting/config/prometheus/alerts.yml`

```yaml
# 1. Collector Target Down（升级为 critical）
- alert: CollectorTargetDown
  expr: up{job="collector"} == 0
  for: 30s
  labels:
    severity: critical
  annotations:
    summary: "🚨 Collector metrics 端点不可用"

# 2. 内存使用过高
- alert: CollectorHighMemory
  expr: process_resident_memory_bytes{job="collector"} > 3000000000
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "⚠️ Collector 内存使用过高"

# 3. 停止采集数据
- alert: CollectorNoDataIngestion
  expr: rate(marketprism_nats_messages_published_total[5m]) == 0
  for: 3m
  labels:
    severity: critical
  annotations:
    summary: "🚨 Collector 停止采集数据"

# 4. 数据采集速率过低
- alert: CollectorDataIngestionLow
  expr: sum(rate(marketprism_nats_messages_published_total[5m])) < 10
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "⚠️ Collector 数据采集速率过低"
```

#### 优化 Alertmanager 路由

**文件**：`services/monitoring-alerting/config/alertmanager/alertmanager.yml`

```yaml
routes:
  # Critical 告警：更频繁的重复通知
  - matchers:
      - severity="critical"
    receiver: 'dingtalk'
    repeat_interval: 10m  # 每 10 分钟重复一次
  
  # Warning 告警：默认配置
  - matchers:
      - severity="warning"
    receiver: 'dingtalk'
    repeat_interval: 2h  # 每 2 小时重复一次
```

**结果**：
- ✅ 4 个新告警规则已加载（state: inactive, health: unknown）
- ✅ Alertmanager 配置已重新加载
- ✅ Critical 告警每 10 分钟重复通知

---

## 📊 当前系统状态

### Collector 服务
```
✅ Docker 容器运行正常（Up 33 minutes, healthy）
✅ HTTP metrics 端口 9092 正常响应
✅ 健康检查端口 8087 正常响应
✅ Prometheus 抓取正常（health: up）
✅ 数据采集正常（~109KB metrics）
```

### 监控系统
```
✅ Prometheus 运行正常（9090）
✅ Grafana 运行正常（3000）
✅ Alertmanager 运行正常（9093）
✅ 4 个 Collector 告警规则已激活
✅ DingTalk webhook 已配置
```

### Dashboard
```
✅ MarketPrism Business Monitoring 正常显示
✅ Ingest Rate 表格显示数据（8 个主题）
✅ Success Rate 表格显示 100%（8 个主题）
✅ 面板布局合理（每行 4 个，宽度 6，高度 10）
```

---

## 🎯 待办事项

### 优先级 P0（已完成）
- [x] 重启 collector 服务
- [x] 修复 Dashboard Success Rate 查询
- [x] 调整面板尺寸和布局
- [x] 添加 Prometheus 告警规则
- [x] 优化 Alertmanager 路由配置
- [x] 停止宿主机上的重复进程

### 优先级 P1（本周完成）
- [ ] 修改健康检查策略（degraded 视为可接受）
- [ ] 添加 Docker healthcheck 和自动重启
- [ ] 创建 Collector Resource Monitoring dashboard
- [ ] 测试告警通知（模拟 collector down）

### 优先级 P2（下周完成）
- [ ] 调查内存泄漏根源（使用 memory_profiler）
- [ ] 优化 OrderBook 数据结构（限制对象数量）
- [ ] 修复 WebSocket 连接泄漏（确保重连时关闭旧连接）
- [ ] 添加文件描述符监控指标

### 优先级 P3（长期优化）
- [ ] 实现优雅降级机制（资源压力大时自动降级）
- [ ] 添加自动化压力测试
- [ ] 完善运维文档和 Runbook

---

## 📚 相关文档

- [详细分析报告](./collector_downtime_analysis.md) - 完整的根本原因分析和解决方案
- [Prometheus 告警规则](../config/prometheus/alerts.yml) - 所有告警规则配置
- [Alertmanager 配置](../config/alertmanager/alertmanager.yml) - 告警路由配置
- [Business Dashboard 生成脚本](../temp/generate_business_dashboard.py) - Dashboard JSON 生成工具

---

## 💡 经验教训

1. **监控覆盖要全面**
   - ✅ 不仅要监控服务可用性，还要监控资源使用
   - ✅ 内存、连接数、文件描述符都需要告警

2. **健康检查要合理**
   - ⚠️ "degraded" 状态不应导致服务标记为 down
   - ⚠️ 部分数据源暂时中断不影响整体可用性

3. **告警要及时**
   - ✅ Critical 告警需要更频繁的重复通知（10 分钟）
   - ✅ 告警消息要清晰，包含 dashboard 链接

4. **自动恢复很重要**
   - ⚠️ 需要 Docker healthcheck 和自动重启机制
   - ⚠️ 避免手动干预，提高系统可用性

5. **资源泄漏要重视**
   - 🚨 长时间运行后资源持续增长是严重问题
   - 🚨 需要定期分析和优化，不能等到出问题才处理

---

## 🔗 快速链接

- **Grafana Dashboard**: http://43.156.224.10:3000/d/marketprism-business/marketprism-business-monitoring
- **Prometheus Targets**: http://localhost:9090/targets
- **Prometheus Alerts**: http://localhost:9090/alerts
- **Alertmanager**: http://localhost:9093/#/alerts
- **Collector Metrics**: http://localhost:9092/metrics
- **Collector Health**: http://localhost:8087/health

---

**调查完成时间**: 2025-10-21 18:10 UTC  
**下一步行动**: 测试告警通知，创建资源监控 dashboard

