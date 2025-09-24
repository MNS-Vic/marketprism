# MarketPrism 分层存储（热→冷）Docker 部署指南

> 统一入口：modules 根目录 main.py；统一配置：config/tiered_storage_config.yaml；容器一键启动；如遇端口冲突（8123/9000/8085/8086），请先 kill 占用再启动，不改端口。

## 架构
```
Data Collector  →  NATS JetStream  →  Hot Storage → ClickHouse Hot
                                         │
                                         └──── 定时归档（Cold Storage Service） → ClickHouse Cold
```

- 热端：实时写入 marketprism_hot（TTL 3 天）
- 冷端：归档写入 marketprism_cold（TTL 365 天）
- 定时：由 ColdStorageService 周期运行，窗口/间隔/清理策略均来自 tiered_storage_config.yaml

## 一键启动
```bash
cd /home/ubuntu/marketprism
# 启动 ClickHouse 热库 + 冷归档服务（连接同一网络）
docker compose -f services/data-storage-service/docker-compose.tiered-storage.yml up -d clickhouse-hot cold-storage-service

# 查看服务日志（冷端）
docker logs -f --tail=120 marketprism-cold-storage
```

## 配置说明（config/tiered_storage_config.yaml）
- sync.interval_hours: 首次启动后每隔多少小时触发一次归档（默认 6）
- sync.batch_hours: 每次归档覆盖的时间窗口（默认 24）
- sync.cleanup_enabled: 归档成功后是否清理热端旧数据（默认 true）

## 验证冷库数据
```bash
# 统计冷库核心表数据量
docker exec marketprism-clickhouse-hot clickhouse-client --query "SELECT 'trades', count() FROM marketprism_cold.trades UNION ALL SELECT 'orderbooks', count() FROM marketprism_cold.orderbooks"

# 查看样例一条
docker exec marketprism-clickhouse-hot clickhouse-client --query "SELECT * FROM marketprism_cold.trades ORDER BY timestamp DESC LIMIT 1"
```

## 手动快速迁移（可选，用于联调）
```bash
# 迁移最近 1 小时的 BTC-USDT 成交到冷库（Binance 现货）
docker exec marketprism-clickhouse-hot clickhouse-client --query "INSERT INTO marketprism_cold.trades (timestamp, exchange, market_type, symbol, trade_id, price, quantity, side, is_maker, trade_time, data_source, created_at) SELECT timestamp, exchange, market_type, symbol, trade_id, price, quantity, side, is_maker, trade_time, 'marketprism' AS data_source, now() AS created_at FROM marketprism_hot.trades WHERE exchange='binance_spot' AND symbol='BTC-USDT' AND timestamp >= now()-interval 1 hour"

# 迁移最近 30 分钟的 BTC-USDT 订单簿到冷库（字段类型转换）
docker exec marketprism-clickhouse-hot clickhouse-client --query "INSERT INTO marketprism_cold.orderbooks (timestamp, exchange, market_type, symbol, last_update_id, bids_count, asks_count, best_bid_price, best_ask_price, best_bid_quantity, best_ask_quantity, bids, asks, data_source, created_at) SELECT toDateTime(timestamp), exchange, market_type, symbol, last_update_id, bids_count, asks_count, toFloat64(best_bid_price), toFloat64(best_ask_price), toFloat64(best_bid_quantity), toFloat64(best_ask_quantity), bids, asks, 'marketprism', now() FROM marketprism_hot.orderbooks WHERE exchange='binance_spot' AND symbol='BTC-USDT' AND timestamp >= now()-interval 30 minute"
```

## 运行健康
- 热端健康检查端口：8085（由 SimpleHotStorageService 暴露）
- 冷端健康检查端口：8086（由 ColdStorageService 暴露），Compose 已配置容器内健康检查
- 如遇端口冲突，先 kill 占用后重启，不更改端口号

## 常见问题
1) 冷库无数据
- 检查冷端日志是否有 SQL 报错
- 手动执行上面的 INSERT…SELECT 看是否成功
- 确认 config/tiered_storage_config.yaml 的时间窗口覆盖了已有热库数据

2) 日志出现“存储订单簿数据失败: 0”
- 该为逐行兜底写入的噪声，不影响批量归档；冷端默认使用批量迁移
- 建议观察冷库计数是否持续增长来判断归档状态

3) 端口冲突
- 需 kill 占用进程/容器后再启动，不要改端口

---

如需将定时器与冷端同机部署，请保持统一入口（main.py）与统一配置（config/ 目录），避免分叉配置与入口的重复创建。
