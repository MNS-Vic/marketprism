# MarketPrism 告警 Runbook

**版本**: 1.0  
**最后更新**: 2025-10-21  
**维护者**: DevOps Team

---

## 目录

1. [Collector 告警](#collector-告警)
2. [NATS 告警](#nats-告警)
3. [ClickHouse 告警](#clickhouse-告警)
4. [Storage 服务告警](#storage-服务告警)
5. [通用诊断步骤](#通用诊断步骤)
6. [快速参考](#快速参考)

---

## Collector 告警

### 🚨 CollectorTargetDown

**严重程度**: Critical  
**触发条件**: Prometheus 无法抓取 collector metrics 端点超过 30 秒

#### 症状
- Prometheus targets 页面显示 collector 为 DOWN
- Grafana dashboards 显示 "No Data"
- 钉钉收到告警通知

#### 可能原因
1. Collector 服务崩溃或停止
2. Collector HTTP 服务器未启动
3. 网络连接问题
4. 容器重启中

#### 诊断步骤

**1. 检查容器状态**
```bash
docker ps --filter "name=collector"
```

**预期输出**: `Up X seconds (healthy)`

**2. 检查容器日志**
```bash
docker logs marketprism-data-collector --tail 50
```

**查找**: 错误信息、异常堆栈、OOM 错误

**3. 检查 metrics 端点**
```bash
curl -sS http://localhost:9092/metrics | head -n 10
```

**预期输出**: Prometheus 格式的指标数据

**4. 检查健康检查端点**
```bash
curl -sS http://localhost:8087/health | jq
```

**预期输出**: `{"status": "healthy", ...}`

#### 解决步骤

**场景 1: 容器已停止**
```bash
cd /home/ubuntu/marketprism/services/data-collector
docker compose -f docker-compose.unified.yml start
```

**场景 2: 容器崩溃循环**
```bash
# 查看详细日志
docker logs marketprism-data-collector --tail 100

# 如果是资源问题，重启容器
docker compose -f docker-compose.unified.yml restart

# 如果是配置问题，检查配置文件
cat config/collector_config.yaml
```

**场景 3: HTTP 服务器未启动**
```bash
# 检查环境变量
docker exec marketprism-data-collector env | grep COLLECTOR_ENABLE_HTTP

# 如果未设置，重新构建并启动
docker compose -f docker-compose.unified.yml up -d --build
```

#### 验证恢复
```bash
# 1. 检查容器状态
docker ps --filter "name=collector"

# 2. 检查 Prometheus targets
curl -sS http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="collector") | {health: .health, lastError: .lastError}'

# 3. 检查告警状态
curl -sS http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | select(.labels.alertname=="CollectorTargetDown") | {state: .state}'
```

#### 预防措施
- ✅ Docker healthcheck 已配置（每 30 秒检查）
- ✅ 自动重启策略已启用（`restart: unless-stopped`）
- ✅ 资源监控告警已配置

---

### ⚠️ CollectorHighMemory

**严重程度**: Warning  
**触发条件**: Collector 内存使用超过 3GB 持续 5 分钟

#### 症状
- 内存使用持续增长
- 可能出现 GC 频繁
- 性能下降

#### 可能原因
1. 内存泄漏（OrderBook 对象累积）
2. WebSocket 连接泄漏
3. 数据积压未及时处理
4. 配置的交易对过多

#### 诊断步骤

**1. 检查当前内存使用**
```bash
curl -sS http://localhost:9092/metrics | grep "process_resident_memory_bytes"
```

**2. 检查对象数量**
```bash
curl -sS http://localhost:9092/metrics | grep "marketprism_process_objects_count"
```

**3. 检查 GC 统计**
```bash
curl -sS http://localhost:9092/metrics | grep "python_gc"
```

**4. 检查 OrderBook 状态**
```bash
curl -sS http://localhost:8087/health | jq '.checks.orderbook'
```

**5. 检查网络连接数**
```bash
docker exec marketprism-data-collector ss -s
```

#### 解决步骤

**场景 1: 内存持续增长但未达到临界值**
```bash
# 监控内存趋势
watch -n 5 'curl -sS http://localhost:9092/metrics | grep process_resident_memory_bytes'

# 如果增长速度过快，准备重启
```

**场景 2: 内存接近临界值（> 3.5GB）**
```bash
# 立即重启容器
cd /home/ubuntu/marketprism/services/data-collector
docker compose -f docker-compose.unified.yml restart
```

**场景 3: 频繁触发告警**
```bash
# 需要调查内存泄漏根源
# 参考任务 3: 调查内存泄漏根源
```

#### 验证恢复
```bash
# 检查内存使用
curl -sS http://localhost:9092/metrics | grep "process_resident_memory_bytes" | awk '{print $2/1024/1024/1024 " GB"}'

# 检查对象数量
curl -sS http://localhost:9092/metrics | grep "marketprism_process_objects_count"
```

#### 预防措施
- 🔄 定期重启（建议每周重启一次）
- 📊 监控内存趋势
- 🔍 调查内存泄漏根源（任务 3）

---

### 🚨 CollectorNoDataIngestion

**严重程度**: Critical  
**触发条件**: Collector 在过去 5 分钟内没有发布任何消息到 NATS，持续 3 分钟

#### 症状
- 数据采集完全停止
- NATS 没有收到新消息
- Dashboard 数据不更新

#### 可能原因
1. 所有 WebSocket 连接断开
2. NATS 连接断开
3. 交易所 API 限流
4. 网络问题

#### 诊断步骤

**1. 检查 NATS 连接状态**
```bash
curl -sS http://localhost:8087/health | jq '.checks.nats'
```

**2. 检查 WebSocket 连接状态**
```bash
curl -sS http://localhost:9092/metrics | grep "marketprism_websocket_connected"
```

**3. 检查最近的错误**
```bash
docker logs marketprism-data-collector --tail 100 | grep -E "ERROR|Exception"
```

**4. 检查 NATS 服务状态**
```bash
curl -sS http://localhost:8222/healthz
```

#### 解决步骤

**场景 1: NATS 连接断开**
```bash
# 检查 NATS 服务
docker ps --filter "name=nats"

# 如果 NATS 停止，启动它
cd /home/ubuntu/marketprism/services/message-broker
docker compose up -d

# 重启 collector
cd /home/ubuntu/marketprism/services/data-collector
docker compose -f docker-compose.unified.yml restart
```

**场景 2: WebSocket 连接全部断开**
```bash
# 检查网络连接
docker exec marketprism-data-collector ping -c 3 api.binance.com

# 重启 collector 重新建立连接
docker compose -f docker-compose.unified.yml restart
```

**场景 3: 交易所 API 限流**
```bash
# 检查日志中的限流错误
docker logs marketprism-data-collector | grep -i "rate limit\|429\|418"

# 如果是限流，等待限流解除（通常 1-5 分钟）
# 或者减少订阅的交易对数量
```

#### 验证恢复
```bash
# 检查数据采集速率
curl -sS http://localhost:9090/api/v1/query?query=rate(marketprism_nats_messages_published_total[1m]) | jq '.data.result[0].value[1]'

# 应该 > 10 ops/s
```

---

### ⚠️ CollectorDataIngestionLow

**严重程度**: Warning  
**触发条件**: Collector 总采集速率 < 10 ops/s，持续 5 分钟

#### 症状
- 数据采集速率异常低
- 部分数据源可能断开

#### 可能原因
1. 部分 WebSocket 连接断开
2. 部分交易对数据停止更新
3. 交易所维护
4. 网络延迟高

#### 诊断步骤

**1. 检查各交易所的采集速率**
```bash
curl -sS 'http://localhost:9090/api/v1/query?query=sum by (subject) (rate(marketprism_nats_messages_published_total[1m]))' | jq '.data.result[] | {subject: .metric.subject, rate: .value[1]}'
```

**2. 检查 WebSocket 连接状态**
```bash
curl -sS http://localhost:9092/metrics | grep "marketprism_websocket_connected{exchange="
```

**3. 检查重连次数**
```bash
curl -sS http://localhost:9092/metrics | grep "marketprism_websocket_reconnections_total"
```

#### 解决步骤

**场景 1: 部分连接断开**
```bash
# 重启 collector 重新建立所有连接
cd /home/ubuntu/marketprism/services/data-collector
docker compose -f docker-compose.unified.yml restart
```

**场景 2: 交易所维护**
```bash
# 检查交易所公告
# Binance: https://www.binance.com/en/support/announcement
# OKX: https://www.okx.com/support/hc/en-us/sections/115000267214-Latest-Announcements
# Deribit: https://www.deribit.com/main#/status

# 如果是维护，等待维护完成
```

#### 验证恢复
```bash
# 检查总采集速率
curl -sS 'http://localhost:9090/api/v1/query?query=sum(rate(marketprism_nats_messages_published_total[1m]))' | jq '.data.result[0].value[1]'

# 应该 > 10 ops/s
```

---

## NATS 告警

### 🚨 BrokerDown

**严重程度**: Critical  
**触发条件**: NATS 服务不可用超过 30 秒

#### 症状
- NATS 健康检查失败
- Collector 无法发布消息
- Storage 服务无法接收消息

#### 诊断步骤

**1. 检查 NATS 容器状态**
```bash
docker ps --filter "name=nats"
```

**2. 检查 NATS 日志**
```bash
docker logs marketprism-nats --tail 50
```

**3. 检查 NATS 健康端点**
```bash
curl -sS http://localhost:8222/healthz
```

#### 解决步骤

**场景 1: 容器停止**
```bash
cd /home/ubuntu/marketprism/services/message-broker
docker compose up -d
```

**场景 2: 容器崩溃**
```bash
# 查看崩溃原因
docker logs marketprism-nats --tail 100

# 重启容器
docker compose restart
```

#### 验证恢复
```bash
# 检查 NATS 状态
curl -sS http://localhost:8222/varz | jq '{connections: .connections, in_msgs: .in_msgs, out_msgs: .out_msgs}'
```

---

## ClickHouse 告警

### 🚨 ClickHouseHotDown / ClickHouseColdDown

**严重程度**: Critical  
**触发条件**: ClickHouse 服务不可用超过 30 秒

#### 诊断步骤

**1. 检查容器状态**
```bash
# Hot ClickHouse
docker ps --filter "name=clickhouse-hot"

# Cold ClickHouse
docker ps --filter "name=clickhouse-cold"
```

**2. 检查日志**
```bash
# Hot
docker logs marketprism-clickhouse-hot --tail 50

# Cold
docker logs marketprism-clickhouse-cold --tail 50
```

**3. 检查连接**
```bash
# Hot (端口 8123)
curl -sS http://localhost:8123/ping

# Cold (端口 8124)
curl -sS http://localhost:8124/ping
```

#### 解决步骤

```bash
cd /home/ubuntu/marketprism/services/message-broker

# 重启 Hot ClickHouse
docker compose restart clickhouse-hot

# 重启 Cold ClickHouse
docker compose restart clickhouse-cold
```

---

## Storage 服务告警

### 🚨 HotStorageDown / ColdStorageDown

**严重程度**: Critical  
**触发条件**: Storage 服务不可用超过 1 分钟

#### 诊断步骤

**1. 检查容器状态**
```bash
docker ps --filter "name=storage"
```

**2. 检查健康端点**
```bash
# Hot Storage (端口 8085)
curl -sS http://localhost:8085/health | jq

# Cold Storage (端口 8086)
curl -sS http://localhost:8086/health | jq
```

**3. 检查日志**
```bash
docker logs marketprism-hot-storage --tail 50
docker logs marketprism-cold-storage --tail 50
```

#### 解决步骤

```bash
cd /home/ubuntu/marketprism/services/data-storage-service

# 重启 Hot Storage
docker compose restart hot-storage

# 重启 Cold Storage
docker compose restart cold-storage
```

---

## 通用诊断步骤

### 检查所有服务状态
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

### 检查资源使用
```bash
docker stats --no-stream
```

### 检查网络连接
```bash
docker network inspect marketprism | jq '.[0].Containers'
```

### 检查磁盘空间
```bash
df -h
```

### 查看 Prometheus 告警
```bash
curl -sS http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | select(.state=="firing") | {alertname: .labels.alertname, severity: .labels.severity, startsAt: .activeAt}'
```

---

## 快速参考

### 重要端口

| 服务 | 端口 | 用途 |
|------|------|------|
| Collector Health | 8087 | 健康检查 |
| Collector Metrics | 9092 | Prometheus 指标 |
| NATS Client | 4222 | NATS 客户端连接 |
| NATS Monitoring | 8222 | NATS 监控 |
| Hot ClickHouse | 8123 | HTTP 接口 |
| Cold ClickHouse | 8124 | HTTP 接口 |
| Hot Storage | 8085 | 健康检查 |
| Cold Storage | 8086 | 健康检查 |
| Prometheus | 9090 | Web UI |
| Grafana | 3000 | Web UI |
| Alertmanager | 9093 | Web UI |

### 重要文件路径

```
/home/ubuntu/marketprism/
├── services/
│   ├── data-collector/
│   │   ├── docker-compose.unified.yml
│   │   ├── config/collector_config.yaml
│   │   └── main.py
│   ├── message-broker/
│   │   ├── docker-compose.yml
│   │   └── config/
│   ├── data-storage-service/
│   │   ├── docker-compose.yml
│   │   └── config/
│   └── monitoring-alerting/
│       ├── docker-compose.yml
│       ├── config/prometheus/alerts.yml
│       └── config/alertmanager/alertmanager.yml
```

### Dashboard 链接

- **Grafana**: http://43.156.224.10:3000
- **Prometheus**: http://localhost:9090
- **Alertmanager**: http://localhost:9093
- **NATS Monitoring**: http://localhost:8222

### 联系方式

- **DevOps Team**: devops@marketprism.com
- **On-Call**: +86-xxx-xxxx-xxxx
- **钉钉群**: MarketPrism 运维群

---

**文档版本**: 1.0  
**最后更新**: 2025-10-21  
**下次审查**: 2025-11-21

