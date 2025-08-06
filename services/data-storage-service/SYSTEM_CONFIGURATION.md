# MarketPrism系统配置文档

## 系统概览

MarketPrism是一个企业级的加密货币市场数据处理平台，实现了100%的8种数据类型覆盖率，支持实时数据收集、处理和存储。

### 系统架构

```
Data Collector (Docker) → NATS → Storage Service → ClickHouse (Docker)
```

## 数据类型配置

### 支持的数据类型 (8种)

| 数据类型 | 频率 | 批处理配置 | 数据源 |
|---------|------|-----------|--------|
| orderbooks | 高频 | 100条/10秒 | Binance, OKX |
| trades | 超高频 | 100条/10秒 | Binance, OKX |
| funding_rates | 中频 | 10条/2秒 | Binance, OKX |
| open_interests | 低频 | 50条/10秒 | Binance, OKX |
| liquidations | 事件驱动 | 5条/10秒 | OKX |
| lsr_top_positions | 低频 | 1条/1秒 | Binance, OKX |
| lsr_all_accounts | 低频 | 1条/1秒 | Binance, OKX |
| volatility_indices | 低频 | 1条/1秒 | Deribit |

## 批处理配置详情

### 高频数据配置
```python
'orderbooks': {'batch_size': 100, 'timeout': 10.0, 'max_queue': 1000}
'trades': {'batch_size': 100, 'timeout': 10.0, 'max_queue': 1000}
```

### 中频数据配置
```python
'funding_rates': {'batch_size': 10, 'timeout': 2.0, 'max_queue': 500}
'open_interests': {'batch_size': 50, 'timeout': 10.0, 'max_queue': 500}
```

### 低频数据配置
```python
'liquidations': {'batch_size': 5, 'timeout': 10.0, 'max_queue': 200}
'lsr_top_position': {'batch_size': 1, 'timeout': 1.0, 'max_queue': 50}
'lsr_all_account': {'batch_size': 1, 'timeout': 1.0, 'max_queue': 50}
'volatility_index': {'batch_size': 1, 'timeout': 1.0, 'max_queue': 50}
```

## NATS主题配置

### 主题格式标准
```
高频数据: {data_type}-data.{exchange}.{market_type}.{symbol}
LSR数据: lsr-data.{exchange}.{market_type}.{subtype}.{symbol}
波动率: volatility-index-data.{exchange}.{market_type}.{symbol}
```

### 订阅主题列表
- `orderbook-data.>`
- `trade-data.>`
- `funding-rate-data.>`
- `open-interest-data.>`
- `liquidation-data.>`
- `lsr-data.>`
- `volatility-index-data.>`

## 时间戳格式标准

### ClickHouse DateTime格式
- **标准格式**: `YYYY-MM-DD HH:MM:SS`
- **示例**: `2025-08-06 02:17:13`
- **时区**: UTC

### 时间戳转换逻辑
```python
# ISO格式转换为ClickHouse格式
if 'T' in value:
    if value.endswith('Z'):
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    elif '+' in value or '-' in value[-6:]:
        dt = datetime.fromisoformat(value)
    else:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    
    cleaned_data[field] = dt.strftime('%Y-%m-%d %H:%M:%S')
```

## 性能指标

### 数据处理能力
- **总吞吐量**: 138.8条/秒
- **高频数据**: 137.8条/秒 (99.3%)
- **低频数据**: 1.0条/秒 (0.7%)
- **批处理效率**: 99.6%
- **错误率**: 0%

### 系统资源使用
- **系统负载**: 1.07 (26.75%使用率)
- **内存使用**: 3.1GiB/7.5GiB (41.3%)
- **Data Collector**: 37.16% CPU, 70.21MiB内存
- **ClickHouse**: 50.91% CPU, 1.331GiB内存
- **NATS**: 2.49% CPU, 83.71MiB内存

## 数据质量标准

### 质量指标
- **时间戳格式正确率**: 100%
- **数据新鲜度**: 7/8数据类型 ≤ 5分钟延迟
- **交易所覆盖**: Binance, OKX, Deribit
- **数据完整性**: 无数据丢失

### 重复数据处理
- **高频数据**: 允许重复（业务需求）
- **低频数据**: 重复率 < 5%
- **去重策略**: 基于(exchange, symbol, timestamp)

## Docker容器配置

### 容器列表
1. **marketprism-data-collector**: 数据收集服务
2. **marketprism-clickhouse-hot**: ClickHouse数据库
3. **marketprism-nats-unified**: NATS消息队列

### 健康检查
- **检查间隔**: 30秒
- **超时时间**: 10秒
- **重试次数**: 3次
- **状态要求**: healthy

## 监控和告警

### 监控指标
- 数据写入速率
- 批处理成功率
- 系统资源使用
- 容器健康状态
- 时间戳格式正确性

### 告警阈值
- **高频数据**: < 100条/分钟
- **中频数据**: < 1条/分钟
- **系统负载**: > 3.0
- **内存使用**: > 80%
- **容器状态**: unhealthy

## 运维建议

### 日常维护
1. 每日检查容器健康状态
2. 监控数据写入速率
3. 检查磁盘空间使用
4. 验证时间戳格式正确性

### 故障排查
1. 检查Docker容器日志
2. 验证NATS连接状态
3. 检查ClickHouse查询性能
4. 监控系统资源使用

### 性能优化
1. 根据数据流量调整批处理参数
2. 监控内存使用，防止内存泄漏
3. 定期清理旧日志文件
4. 优化ClickHouse查询索引

## 故障排查指南

### 常见问题及解决方案

#### 1. 数据写入停止
**症状**: 某种数据类型停止写入
**排查步骤**:
```bash
# 检查容器状态
sudo docker ps --format 'table {{.Names}}\t{{.Status}}'

# 检查存储服务日志
tail -50 production_lsr_final.log | grep ERROR

# 检查数据收集器日志
sudo docker logs marketprism-data-collector --since 10m
```

#### 2. 时间戳格式错误
**症状**: ClickHouse报告时间戳解析错误
**解决方案**:
```bash
# 检查最新数据的时间戳格式
curl -s "http://localhost:8123/" --data "SELECT timestamp FROM marketprism_hot.trades ORDER BY timestamp DESC LIMIT 1"

# 重启数据收集器
cd services/data-collector && sudo docker-compose -f docker-compose.unified.yml restart
```

#### 3. 系统资源不足
**症状**: 系统负载过高或内存不足
**解决方案**:
```bash
# 检查资源使用
free -h && uptime
sudo docker stats --no-stream

# 清理日志文件
find services/data-storage-service -name "*.log" -mtime +7 -delete
```

#### 4. NATS连接问题
**症状**: 数据收集器无法发布消息
**解决方案**:
```bash
# 检查NATS状态
sudo docker logs marketprism-nats-unified --since 5m

# 重启NATS
sudo docker restart marketprism-nats-unified
```

### 快速诊断命令

```bash
# 系统健康检查
cd services/data-storage-service && python3 quick_monitor.py

# 数据质量检查
cd services/data-storage-service && python3 data_quality_check.py

# 资源使用检查
cd services/data-storage-service && python3 resource_monitor.py
```

## 版本信息

- **系统版本**: MarketPrism v1.0
- **最后更新**: 2025-08-06
- **配置状态**: 生产就绪
- **数据类型覆盖率**: 100% (8/8)
- **修复完成**: LSR数据时间戳格式统一
