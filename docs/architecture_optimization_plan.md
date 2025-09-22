# MarketPrism 架构优化计划

## 当前状态分析

### ✅ 已完成修复
- deliver_policy=LAST 配置生效
- 批量处理恢复正常
- 消费者积压从 75,400 降至 226

### 📊 性能基线
- 批量插入：30 次
- 平均批量大小：10.43
- 消息处理：334 条
- 错误率：0%

## 优化建议

### 🚀 Phase 3A: 性能调优（已实施）
**目标**：提升批量处理效率
- ✅ 提升 max_batch_size: 50 → 100
- ✅ 增加 trade_batch_size: 150（专用）
- ✅ 调整 flush_interval: 0.8s → 1.0s
- ✅ 提升 low_freq_batch_size: 10 → 20

**预期收益**：
- 批量大小提升 2-3倍
- ClickHouse 写入 QPS 提升 50%
- 减少网络开销

### 🏗️ Phase 3B: 多消费者分片（推荐）
**目标**：水平扩展处理能力

#### 方案1：按交易所分片
```yaml
consumers:
  - name: storage-binance-consumer
    subjects: ["trade.binance.>", "orderbook.binance.>"]
  - name: storage-okx-consumer  
    subjects: ["trade.okx.>", "orderbook.okx.>"]
  - name: storage-deribit-consumer
    subjects: ["trade.deribit.>", "orderbook.deribit.>"]
```

#### 方案2：按数据类型分片
```yaml
consumers:
  - name: storage-trade-consumer
    subjects: ["trade.>"]
    batch_size: 200
  - name: storage-orderbook-consumer
    subjects: ["orderbook.>"] 
    batch_size: 150
  - name: storage-lowfreq-consumer
    subjects: ["liquidation.>", "funding_rate.>"]
    batch_size: 50
```

**实施优先级**：中等（当单消费者达到瓶颈时）

### 📊 Phase 3C: 监控和告警系统
**目标**：预防性运维

#### 关键指标监控
```yaml
alerts:
  - name: batch_processing_stopped
    condition: batch_inserts_total == 0 for 2min
    action: restart_service
    
  - name: high_pending_messages  
    condition: num_pending > 10000
    action: scale_consumers
    
  - name: high_error_rate
    condition: error_rate > 5%
    action: investigate_logs
    
  - name: clickhouse_write_latency
    condition: avg_batch_insert_time > 5s
    action: check_clickhouse_health
```

#### 自动扩容机制
```python
async def auto_scale_consumers():
    if num_pending > 50000:
        # 启动额外消费者实例
        await start_additional_consumer()
    elif num_pending < 1000:
        # 缩减消费者实例
        await stop_excess_consumer()
```

### 🔧 Phase 3D: ClickHouse 优化
**目标**：提升写入性能

#### 表结构优化
```sql
-- 使用 ReplacingMergeTree 避免重复数据
CREATE TABLE trades_optimized (
    exchange String,
    symbol String, 
    timestamp DateTime64(3),
    price Float64,
    size Float64,
    -- 添加分区键提升查询性能
    date Date MATERIALIZED toDate(timestamp)
) ENGINE = ReplacingMergeTree()
PARTITION BY (exchange, date)
ORDER BY (symbol, timestamp)
SETTINGS index_granularity = 8192;
```

#### 写入优化
- 启用异步插入：`async_insert=1`
- 调整批量大小：`max_insert_block_size=1000000`
- 使用 TCP 驱动替代 HTTP

## 配置一致性检查

### ✅ LSR 配置对齐
检查 `.env.docker` 中的 LSR 配置：
- `LSR_DELIVER_POLICY=last` ✅ 与修复一致
- `LSR_ACK_POLICY=explicit` ✅ 与修复一致  
- `LSR_ACK_WAIT=30` ⚠️ 建议调整为 60 与其他消费者一致

### 🔄 其他服务配置同步
需要检查的服务：
- data-collector: 发布速率配置
- message-broker: JetStream 限制配置
- 监控服务: 指标收集配置

## 生产环境部署检查清单

### 🔍 性能验证
- [ ] 负载测试：模拟 10x 当前消息量
- [ ] 故障恢复测试：服务重启后恢复时间
- [ ] 内存使用监控：批量缓冲区内存占用
- [ ] 网络带宽监控：ClickHouse 写入带宽

### 🛡️ 可靠性验证  
- [ ] 消息不丢失验证：端到端消息追踪
- [ ] 重复消息处理：幂等性验证
- [ ] 异常场景处理：ClickHouse 不可用时的行为

### 📋 运维准备
- [ ] 监控面板：Grafana 仪表板
- [ ] 告警规则：PagerDuty/钉钉集成
- [ ] 运维手册：故障排查流程
- [ ] 备份策略：配置和数据备份

## 预期收益评估

### 短期收益（Phase 3A）
- 批量处理效率提升 2-3倍
- 消息积压减少 80%
- 系统稳定性提升

### 中期收益（Phase 3B-C）
- 处理能力提升 5-10倍
- 故障自愈能力
- 运维效率提升 50%

### 长期收益（Phase 3D）
- 支持更多交易所接入
- 查询性能提升 10倍
- 存储成本优化 30%
