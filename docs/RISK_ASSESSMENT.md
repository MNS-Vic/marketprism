# MarketPrism 监控与告警体系 —— 风险评估与链路梳理（Phase 1）

本文档梳理 MarketPrism 全链路数据流、依赖与健康/重试机制，并识别各层潜在风险点，提出监控指标与告警建议（P0/P1优先）。

## 1. 全链路与端口/健康
- Collector → NATS JetStream → Hot Storage → ClickHouse(Hot) → Cold Storage → ClickHouse(Cold)
- 端口与健康/指标（统一约定）
  - Collector: 8087 /health，9093 /metrics（已实现 prometheus_client）
  - Message Broker: 8086 API（/api/v1/...），新增 9096 /metrics（Prometheus 文本）
  - Hot Storage: 8085 /health,/stats；新增 9094 /metrics（Prometheus 文本，保持向后兼容）
  - Cold Storage: 8086 /health,/stats；新增 9095 /metrics（Prometheus 文本）
  - NATS: 4222（客户端），8222（监控）
  - ClickHouse Hot: 8123（HTTP），9000（TCP）
  - ClickHouse Cold: 8124（HTTP）

## 2. 关键依赖、超时与重试（按层）
### 2.1 Collector（services/data-collector）
- 依赖：交易所 WS/REST、NATS JetStream
- 超时/重试：WS 自动重连与退避；NATS 发布失败捕获与重试；标准化失败计数
- 健康：/health 汇总；/metrics 完整（CPU/Mem、WS、NATS、订单簿、错误等）

### 2.2 Message Broker（services/message-broker）
- 依赖：外部 NATS 集群（JetStream）
- 超时/重试：连接失败降级运行；流严格对齐（subjects）
- 健康：/api/v1/broker/health；新增 /metrics 暴露连接状态、流统计、Collector 心跳聚合

### 2.3 Hot Storage（services/hot-storage-service）
- 依赖：NATS、ClickHouse(Hot) TCP 优先，HTTP 回退
- 超时/重试：单条/批量插入 with 重试（max_retries, backoff）；批量缓冲+定时 flush；失败回退单条
- 健康：/health 检查 NATS 与 ClickHouse/ping；/stats JSON；新增 /metrics（兼容旧前缀 + marketprism_storage_）

### 2.4 Cold Storage（services/cold-storage-service）
- 依赖：ClickHouse Hot/Cold（驱动优先，CLI 回退），复制窗口推进与可选清理
- 超时/重试：周期任务，窗口级失败记录与 recent_errors；落后窗口追赶
- 健康：/health 检查 Hot/Cold；/stats JSON（增强 last_success_utc, recent_errors）；新增 /metrics（滞后/窗口/错误等）

## 3. 风险点与易发 Bug（含建议指标与告警）

P0 = 影响核心数据链路可用性；P1 = 影响时效/完整性；P2 = 性能/成本优化。

### 3.1 采集层（Collector）
- WS 断连/重连风暴（P0）
  - 指标：marketprism_collector_ws_reconnects_total、connection_status（0/1）
  - 告警：5m 内重连次数 > 阈值；连接断开持续 > 1m
- 交易所限流/封禁（P0）
  - 指标：REST 错误码计数；2xx 比例下降；延迟飙升
  - 告警：HTTP 4xx/5xx 突增；message receive 速率骤降
- 标准化失败（P1）
  - 指标：marketprism_collector_normalize_errors_total by exchange,data_type
  - 告警：任一 data_type 5m 错误率 > 5%
- 内存增长（P2）
  - 指标：process_resident_memory_bytes、gc 次数
  - 告警：内存 1h 增长 > 30% 且未回落

### 3.2 消息队列层（Message Broker / NATS）
- JetStream 流满/丢弃（P0）
  - 指标：NATS 8222 / JS state（messages/bytes/max_age）；本服务 /metrics 聚合流消息、字节
  - 告警：messages/bytes 接近上限 90%；discard 计数 > 0
- 消费堆积/重投递（P0）
  - 指标：consumer lag（需在订阅侧观测）；broker 聚合心跳活跃实例
  - 告警：订阅端滞后持续上升；活跃 collector 数骤降

### 3.3 热端存储（Hot Storage）
- ClickHouse 写入失败/降级（P0）
  - 指标：marketprism_storage_clickhouse_insert_errors_total、http_fallback_total、tcp_hits_total
  - 告警：insert_errors_total 连续增加；HTTP 回退占比 > 50%
- 批量缓冲积压/延迟（P1）
  - 指标：marketprism_storage_batch_queue_size{data_type}、batch_inserts_total、batch_size_avg
  - 告警：queue_size 长时间高位；batch_inserts 速率骤降
- 数据处理失败（P1）
  - 指标：messages_failed_total、error_rate_percent；按 data_type 分维度
  - 告警：错误率 > 5%；低频类型连续失败

### 3.4 冷端复制（Cold Storage）
- 复制滞后（P0）
  - 指标：marketprism_cold_replication_lag_minutes{table}
  - 告警：单表 lag_minutes > 15m 且上升
- 窗口失败/错误尖刺（P1）
  - 指标：failed_windows_total、errors_count_1h_total、recent_errors
  - 告警：1h 错误数 > 阈值；连续窗口失败
- 清理与写放大（P2）
  - 指标：每窗口写入行数、清理耗时（后续补充）

## 4. 现有健康检查与指标暴露方式
- Collector：aiohttp /health 与 /metrics（prometheus_client）
- Broker：aiohttp /api/v1/...；新增 /metrics 文本
- Hot Storage：aiohttp /health,/stats；新增 /metrics 文本（兼容旧名称 + 统一前缀）
- Cold Storage：aiohttp /health,/stats；新增 /metrics 文本

## 5. P0/P1 指标清单（最小集，可被 Prometheus 抓取）
- Broker：
  - marketprism_broker_connected
  - marketprism_broker_stream_messages_total{stream}
  - marketprism_broker_collectors_active
- Hot Storage：
  - marketprism_storage_messages_processed_total{data_type}
  - marketprism_storage_messages_failed_total{data_type}
  - marketprism_storage_clickhouse_insert_errors_total
  - marketprism_storage_batch_queue_size{data_type}
- Cold Storage：
  - marketprism_cold_replication_lag_minutes{table}
  - marketprism_cold_success_windows_total / failed_windows_total
  - marketprism_cold_errors_count_1h_total

## 6. 告警建议（草案）
- P0
  - Broker 断连：marketprism_broker_connected == 0 持续 30s
  - Hot Insert 错误：insert_errors_total 5m 内单调递增且速率阈值 > X
  - Cold 滞后：任一表 lag_minutes > 15 持续 10m
- P1
  - Hot 错误率：marketprism_storage_error_rate_percent > 5 持续 5m
  - 批量缓冲积压：queue_size{data_type} 高于 Y 持续 10m
  - Cold 窗口失败：failed_windows_total 5m 增量 > Z

## 7. 变更影响与兼容
- 保持唯一入口与唯一配置，不新增并行入口
- /metrics 为新增端点，不破坏现有 health/integrity 流程
- Hot Storage 仍输出旧前缀指标，避免现有仪表盘/脚本失效；同时提供统一前缀 marketprism_ 便于规范化

## 8. 后续阶段（Phase 2/3 提示）
- Phase 2：统一 prometheus_client 接入（Hot/Cold/Broker），端口规范：9093/9094/9095/9096
- Phase 3：prometheus+alertmanager+grafana 一体化部署（services/monitoring-alerting），仪表盘 + 告警规则落地

以上内容覆盖 Phase 1 成功标准：
- [x] 风险评估文档覆盖所有模块
- [x] 健康与指标暴露方式已梳理
- [x] 提出 P0/P1 指标与告警建议（最小集）

