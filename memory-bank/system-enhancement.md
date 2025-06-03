# MarketPrism系统性能优化记录

## 2025年6月优化

### 概要
完成了系统核心组件的可靠性增强和监控系统的全面升级，为长期稳定数据采集提供更加坚实的基础。

### 主要优化点

#### 1. Binance订单簿同步机制优化
- 实现了符合官方文档的增量更新处理逻辑
- 添加了LastUpdateID验证机制确保数据一致性
- 优化了断线重连后的完整重同步流程
- 减少了不必要的快照请求，降低API请求频率

#### 2. ClickHouse数据存储优化
- 实现了表分区支持，按月创建数据分区
- 添加TTL支持，自动管理数据生命周期
- 优化了索引和排序键设计
- 增强了冷热数据分离机制

#### 3. NATS消息队列可靠性提升
- 添加了死信队列(DLQ)支持，处理失败消息
- 定义了明确的消息确认(ACK)策略
- 优化了消息重试机制，确保消息可靠投递
- 添加了消息链路跟踪

#### 4. 数据归档服务增强
- 集成了NATS消息处理功能
- 添加了死信队列处理能力
- 实现心跳机制，确保服务健康监控
- 添加了异步处理架构，提高吞吐量

#### 5. 监控系统全面升级
- 部署了完整的Prometheus + Grafana + AlertManager监控链
- 添加了针对关键系统指标的告警规则
- 集成了Loki和Promtail实现日志聚合和检索
- 添加了Node Exporter监控主机资源使用情况

### 技术细节

#### 订单簿同步机制
```go
// 订单簿同步遵循币安官方文档规范
// 1. 首先通过REST API获取订单簿快照
// 2. 缓存任何U字段 >= lastUpdateId+1且U字段 <= lastUpdateId+1的事件
// 3. 丢弃任何u字段 <= lastUpdateId的事件
// 4. 对于任何其他事件，处理事件中的bids和asks字段按普通增量更新处理
```

#### 数据库表分区示例
```sql
CREATE TABLE marketprism.trades (
    id UInt64,
    exchange LowCardinality(String),
    symbol LowCardinality(String),
    trade_id String,
    price Float64,
    quantity Float64,
    side LowCardinality(String),
    trade_time DateTime,
    receive_time DateTime,
    is_best_match Bool DEFAULT true
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(trade_time)
ORDER BY (exchange, symbol, trade_time)
TTL trade_time + INTERVAL 90 DAY
SETTINGS index_granularity=8192;
```

#### 死信队列处理流程
```python
async def _process_dlq(self):
    """
    处理死信队列中的消息
    """
    while self.running:
        try:
            # 获取死信队列信息
            dlq_info = await self.nats_js.stream_info("DLQ")
            msg_count = dlq_info.state.messages
            
            if msg_count > 0:
                logger.info(f"死信队列中有 {msg_count} 条消息需要处理")
                
                # 创建临时消费者
                consumer_config = {
                    "durable_name": "DLQ_PROCESSOR",
                    "ack_policy": "explicit",
                    "filter_subject": "deadletter.>",
                    "max_deliver": 1,  # 只投递一次
                }
                
                # 拉取死信消息
                sub = await self.nats_js.pull_subscribe("deadletter.>", "DLQ_PROCESSOR", stream="DLQ")
                
                # 分批处理死信消息
                batch_size = 20
                processed = 0
                
                while processed < msg_count and self.running:
                    # 批量拉取死信消息
                    dlq_msgs = await sub.fetch(min(batch_size, msg_count - processed), timeout=5)
                    
                    for msg in dlq_msgs:
                        try:
                            # 处理死信消息
                            await self._handle_dlq_message(msg)
                            processed += 1
                        except Exception as e:
                            # 即使处理失败也确认消息，避免无限循环
                            await msg.ack()
```

#### Prometheus告警规则示例
```yaml
groups:
  - name: marketprism_alerts
    rules:
      - alert: ExchangeConnectionDown
        expr: marketprism_collector_connection_status{exchange=~".*"} == 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "交易所连接中断 [{{ $labels.exchange }}]"
          description: "{{ $labels.exchange }} 连接已经中断超过5分钟"
```

### 性能影响

优化后系统在以下方面有显著提升：
1. **数据完整性**: 通过优化订单簿同步机制，减少了数据丢失和不一致情况
2. **系统稳定性**: 通过死信队列和消息确认机制，提高了系统在面对异常时的恢复能力
3. **存储效率**: 通过分区和TTL机制，提高了数据查询效率并优化了存储空间使用
4. **监控可见性**: 通过完整的监控系统，提供了系统运行状态的全面可见性
5. **错误处理**: 通过结构化的错误处理和日志记录，提升了问题诊断和解决效率

### 后续计划

1. 继续优化交易所连接的自动重连机制
2. 添加更多的性能指标采集点
3. 开发自动化的数据质量检查工具
4. 增强监控仪表盘，添加更多业务指标
5. 实现更细粒度的数据分区策略