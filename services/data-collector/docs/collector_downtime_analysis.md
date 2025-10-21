# Data Collector 停机问题分析报告

**日期**: 2025-10-21  
**分析人员**: AI Assistant  
**问题发现时间**: 09:24:14 UTC  
**问题解决时间**: 09:33:03 UTC (重启后恢复)

---

## 1. 问题现象

### 1.1 监控发现
- **Prometheus**: collector target 显示 `health: down`，最后成功抓取时间 09:24:14
- **Grafana Dashboard**: Business Monitoring 面板显示 "no data"
- **实际情况**: collector 进程仍在运行，数据采集正常，但 HTTP metrics 端点无响应

### 1.2 初步诊断
```bash
# Prometheus target 状态
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="collector")'
# 结果: health: "down", lastScrape: "2025-10-21T09:24:14.025421497Z"

# Collector 进程状态
ps aux | grep data-collector
# 结果: PID 1234352 运行中，CPU 85%，内存 2.9GB

# Metrics 端点测试
curl http://localhost:9092/metrics
# 结果: 挂起，无响应
```

---

## 2. 根本原因分析

### 2.1 直接原因：HTTP Metrics 服务未启动

**发现**：collector 的 HTTP metrics 服务器默认是**关闭**的。

**代码位置**：`services/data-collector/main.py:2039`
```python
enable_http = os.getenv('COLLECTOR_ENABLE_HTTP', '0').lower() in ('1', 'true', 'yes')
```

**配置状态**：
- ✅ `docker-compose.unified.yml` 中已设置 `COLLECTOR_ENABLE_HTTP=1`
- ✅ 容器环境变量正确
- ❌ 但在 09:24:14 之前，HTTP 服务器因资源问题停止响应

### 2.2 深层原因：资源泄漏导致服务降级

**时间线**：

**09:24:09** - 资源告警触发
```log
[error] 🚨 强制清理后内存仍然过高
  current_mb=2869.72
  objects_count=15,303,778

[warning] ⚠️ 网络连接数达到警告阈值
  current_connections=97
  tcp_connections=97
  threshold=50

[warning] 🔍 资源使用趋势警告
  warnings=['文件描述符使用呈 rapidly_increasing 趋势', 
           '网络连接数呈 rapidly_increasing 趋势']
```

**09:24:09** - OrderBook 状态丢失
```log
[warning] ⚠️ ETH-USDT-SWAP状态不存在，执行惰性初始化
[warning] ⏰ BTC-USDT等待快照超时，触发重订阅
[warning] ⚠️ ETH-USDT状态不存在，执行惰性初始化
[warning] ⏰ ETH-USDT等待快照超时，触发重订阅
```

**09:24:10** - 健康检查返回 200（可能在 grace period 内）

**09:24:14** - Prometheus 抓取失败（可能是 HTTP 服务器已无响应）

### 2.3 健康检查机制分析

**健康检查逻辑**：`services/data-collector/collector/health_check.py:330`
```python
"status": "healthy" if overall_healthy else "unhealthy"
```

**HTTP 响应码**：`services/data-collector/collector/http_server.py:158`
```python
status_code = 200 if status == "healthy" else 503
```

**Grace Period**：启动后 120 秒内，即使状态不健康也返回 200

**问题**：
1. OrderBook 数据陈旧（>60秒）→ status = "degraded" 或 "unhealthy"
2. 整体健康检查返回 503
3. Prometheus 认为 target 不健康，但实际上只是部分数据源暂时中断

---

## 3. 资源泄漏根源

### 3.1 内存泄漏

**可能原因**：
1. **OrderBook 数据累积**：15,303,778 个对象，内存 2.9GB
2. **WebSocket 连接未正确清理**：97 个 TCP 连接（正常应 < 50）
3. **文件描述符泄漏**：快速增长趋势

**影响**：
- 内存压力导致 GC 频繁，CPU 使用率高（85%）
- 可能触发 OOM killer 或服务降级

### 3.2 连接泄漏

**正常连接数**：
- Binance Spot: 2 个 WebSocket（orderbook, trade）
- Binance Derivatives: 2 个
- OKX Spot: 2 个
- OKX Derivatives: 2 个
- Deribit: 2 个
- **预期总数**: ~10-15 个

**实际连接数**: 97 个（异常）

**可能原因**：
- WebSocket 重连时未关闭旧连接
- HTTP 连接池未正确释放
- NATS 连接泄漏

---

## 4. 解决方案

### 4.1 立即修复（已完成）

✅ **重启 collector 容器**
```bash
cd /home/ubuntu/marketprism/services/data-collector
docker compose -f docker-compose.unified.yml restart
```

**结果**：
- 容器重启后，HTTP metrics 服务正常启动
- Prometheus 恢复抓取（health: up）
- Dashboard 显示数据正常

### 4.2 短期优化（建议）

#### 4.2.1 调整健康检查策略

**问题**：OrderBook 数据暂时陈旧不应导致整体服务标记为 unhealthy

**建议**：修改 `health_check.py`，将 "degraded" 状态也视为可接受：
```python
# 修改前
status_code = 200 if status == "healthy" else 503

# 修改后
status_code = 200 if status in ["healthy", "degraded"] else 503
```

**理由**：
- "degraded" 表示部分数据源暂时中断，但服务整体可用
- 避免因短暂的数据延迟导致 Prometheus 误判

#### 4.2.2 增加资源监控告警

**建议**：在 Prometheus 中添加告警规则：

```yaml
# services/monitoring-alerting/config/prometheus/alerts/collector_alerts.yml
groups:
  - name: collector_resource_alerts
    interval: 30s
    rules:
      - alert: CollectorHighMemory
        expr: process_resident_memory_bytes{job="collector"} > 3000000000  # 3GB
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Collector 内存使用过高"
          description: "Collector 内存使用 {{ $value | humanize }}B，超过 3GB 阈值"

      - alert: CollectorHighConnections
        expr: collector_tcp_connections > 50
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Collector TCP 连接数过多"
          description: "Collector TCP 连接数 {{ $value }}，超过 50 阈值"

      - alert: CollectorDown
        expr: up{job="collector"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Collector 服务不可用"
          description: "Collector 已停止响应 Prometheus 抓取请求"
```

#### 4.2.3 自动重启机制

**建议**：在 `docker-compose.unified.yml` 中添加健康检查和自动重启：

```yaml
services:
  data-collector:
    # ... 其他配置 ...
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8087/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 2G
```

### 4.3 长期优化（需要开发）

#### 4.3.1 修复内存泄漏

**调查方向**：
1. **OrderBook 数据结构优化**
   - 检查 `OrderBookManager` 是否正确清理过期数据
   - 限制每个交易对的最大深度和历史记录

2. **WebSocket 连接管理**
   - 确保重连时关闭旧连接
   - 添加连接池监控和自动清理

3. **对象生命周期管理**
   - 使用 `weakref` 避免循环引用
   - 定期触发 GC 并监控效果

**建议工具**：
```bash
# 内存分析
pip install memory_profiler
python -m memory_profiler main.py

# 对象追踪
pip install objgraph
# 在代码中添加
import objgraph
objgraph.show_most_common_types(limit=20)
```

#### 4.3.2 连接池优化

**建议**：
1. 为 HTTP 客户端设置连接池限制
2. 为 WebSocket 添加连接状态监控
3. 定期检查并关闭僵尸连接

#### 4.3.3 优雅降级机制

**建议**：当资源压力过大时，自动降级：
1. 减少采集频率
2. 暂停低优先级数据源
3. 触发告警但不停止服务

---

## 5. 监控改进建议

### 5.1 添加业务指标监控

**建议指标**：
```python
# 在 collector/metrics.py 中添加
collector_tcp_connections = Gauge(
    'collector_tcp_connections',
    'Number of TCP connections'
)

collector_file_descriptors = Gauge(
    'collector_file_descriptors',
    'Number of open file descriptors'
)

collector_orderbook_objects = Gauge(
    'collector_orderbook_objects',
    'Number of orderbook objects in memory'
)
```

### 5.2 Dashboard 增强

**建议**：在 Grafana 中添加 "Collector Resource Monitoring" 面板：
- 内存使用趋势图
- TCP 连接数趋势图
- 文件描述符趋势图
- OrderBook 对象数量
- GC 频率和耗时

### 5.3 告警路由配置

**建议**：在 Alertmanager 中配置 DingTalk 告警：
```yaml
route:
  group_by: ['alertname', 'severity']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h
  receiver: 'dingtalk'
  routes:
    - match:
        severity: critical
      receiver: 'dingtalk'
      repeat_interval: 5m  # 严重告警每 5 分钟重复一次
```

---

## 6. 行动计划

### 优先级 P0（立即执行）
- [x] 重启 collector 服务（已完成）
- [ ] 添加 Prometheus 告警规则（CollectorDown, CollectorHighMemory）
- [ ] 配置 Alertmanager → DingTalk 路由

### 优先级 P1（本周完成）
- [ ] 修改健康检查策略（degraded 视为可接受）
- [ ] 添加 Docker healthcheck 和自动重启
- [ ] 创建 Collector Resource Monitoring dashboard

### 优先级 P2（下周完成）
- [ ] 调查内存泄漏根源（使用 memory_profiler）
- [ ] 优化 OrderBook 数据结构
- [ ] 修复 WebSocket 连接泄漏

### 优先级 P3（长期优化）
- [ ] 实现优雅降级机制
- [ ] 添加自动化压力测试
- [ ] 完善文档和运维手册

---

## 7. 经验教训

1. **监控覆盖不足**：缺少资源使用（内存、连接数）的告警，导致问题发现滞后
2. **健康检查过于严格**：部分数据源暂时中断不应导致整体服务标记为 down
3. **缺少自动恢复机制**：服务异常时需要手动重启，影响可用性
4. **资源泄漏未及时发现**：长时间运行后资源持续增长，最终导致服务降级

---

## 8. 参考资料

- [Prometheus Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)
- [Docker Healthcheck](https://docs.docker.com/engine/reference/builder/#healthcheck)
- [Python Memory Profiling](https://pypi.org/project/memory-profiler/)
- [Grafana Dashboard Best Practices](https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/best-practices/)

