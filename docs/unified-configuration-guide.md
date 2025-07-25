# 📋 MarketPrism 统一配置指南

## 🎯 **概述**

本文档提供了MarketPrism系统的统一配置管理指南，包括NATS流配置、ClickHouse表结构、数据管道配置等所有核心组件的配置说明。

## 📁 **配置文件结构**

```
config/
├── nats_unified_streams.yaml          # 统一NATS流配置
├── trade_data_pipeline_config.yaml    # 数据管道配置
├── clickhouse/
│   ├── init_all_tables.sql            # 统一表初始化脚本
│   ├── unified_trade_data_table_schema.sql    # 交易数据表结构
│   └── market_long_short_ratio_table_schema.sql   # 市场情绪表结构
└── services.yaml                      # 服务配置
```

## 📡 **NATS流配置**

### **主配置文件**: `config/nats_unified_streams.yaml`

#### **支持的数据流**
1. **unified-trade-data**: 统一交易数据流
2. **liquidation-orders**: 强平订单数据流
3. **open-interest-data**: 持仓量数据流
4. **funding-rate-data**: 资金费率数据流
5. **top-trader-ratio-data**: 大户持仓比数据流
6. **market-ratio-data**: 市场多空人数比数据流

#### **路由规则**
```yaml
# 统一交易数据路由
trades.binance.spot.{symbol}           # Binance现货原始数据
trades.binance.futures.{symbol}        # Binance期货原始数据
trades.okx.{trade_type}.{symbol}       # OKX原始数据
trades.normalized.{exchange}.{trade_type}.{currency}  # 标准化数据

# 强平订单路由
liquidation.{exchange}.{product_type}.{symbol}        # 原始数据
liquidation.normalized.{exchange}.{product_type}.{symbol}  # 标准化数据

# 其他数据类型路由
{data_type}.{exchange}.{symbol}         # 原始数据
{data_type}.normalized.{exchange}.{currency}  # 标准化数据
```

## 🗄️ **ClickHouse表结构**

### **主初始化脚本**: `config/clickhouse/init_all_tables.sql`

#### **核心数据表**
1. **unified_trade_data**: 统一交易数据
2. **liquidations**: 强平订单数据
3. **open_interest**: 持仓量数据
4. **funding_rates**: 资金费率数据
5. **top_trader_long_short_ratio**: 大户持仓比数据
6. **market_long_short_ratio**: 市场多空人数比数据

#### **物化视图**
- **trade_minute_stats**: 交易数据分钟级聚合
- **liquidation_hourly_stats**: 强平订单小时级聚合

#### **监控视图**
- **latest_trades**: 最新交易数据
- **latest_liquidations**: 最新强平订单
- **arbitrage_opportunities**: 套利机会检测

## ⚙️ **数据管道配置**

### **主配置文件**: `config/trade_data_pipeline_config.yaml`

#### **核心配置节**
```yaml
nats:                    # NATS连接和流配置
clickhouse:             # ClickHouse连接配置
data_processing:        # 数据处理配置
monitoring:             # 监控配置
retention:              # 数据保留策略
performance:            # 性能优化配置
```

#### **标准化器配置**
- **binance_spot**: Binance现货数据标准化
- **binance_futures**: Binance期货数据标准化
- **okx_unified**: OKX统一数据标准化

## 🔧 **数据类型支持**

### **统一交易数据** (`NormalizedTrade`)
```python
{
    "exchange_name": "binance|okx",
    "symbol_name": "BTC-USDT",
    "currency": "BTC",
    "trade_id": "12345",
    "price": 45000.50,
    "quantity": 0.1,
    "side": "buy|sell",
    "trade_type": "spot|futures|swap",
    "timestamp": "2024-12-19T10:00:00Z"
}
```

### **市场多空人数比** (`NormalizedMarketLongShortRatio`)
```python
{
    "exchange_name": "binance|okx",
    "symbol_name": "BTC-USDT",
    "currency": "BTC",
    "long_short_ratio": 1.25,
    "long_account_ratio": 0.55,
    "short_account_ratio": 0.45,
    "data_type": "account",
    "timestamp": "2024-12-19T10:00:00Z"
}
```

### **大户持仓比** (`NormalizedTopTraderLongShortRatio`)
```python
{
    "exchange_name": "binance|okx",
    "symbol_name": "BTC-USDT",
    "currency": "BTC",
    "long_short_ratio": 2.1,
    "long_position_ratio": 0.68,
    "short_position_ratio": 0.32,
    "data_type": "position",
    "timestamp": "2024-12-19T10:00:00Z"
}
```

## 🚀 **部署和初始化**

### **1. 初始化ClickHouse表**
```bash
# 连接到ClickHouse并执行初始化脚本
clickhouse-client --query "$(cat config/clickhouse/init_all_tables.sql)"
```

### **2. 配置NATS流**
```bash
# 使用NATS CLI创建流
nats stream add --config config/nats_unified_streams.yaml
```

### **3. 启动数据管道**
```bash
# 启动数据收集服务
python services/data-collector/main.py --config config/trade_data_pipeline_config.yaml
```

## 📊 **监控和维护**

### **性能监控**
- 流消息数量和大小
- 消费者待处理消息数
- 数据处理延迟
- 错误率统计

### **数据质量监控**
- 数据完整性检查
- 重复数据检测
- 异常值监控
- 数据新鲜度检查

### **告警配置**
```yaml
monitoring:
  alert_thresholds:
    stream_msgs_warning: 4000000
    stream_msgs_critical: 4500000
    consumer_pending_warning: 1000
    consumer_pending_critical: 5000
    data_loss_rate: 0.01
    error_rate: 0.05
```

## 🔄 **数据流处理流程**

### **1. 数据采集**
```
外部API → 原始数据 → NATS流 (原始主题)
```

### **2. 数据标准化**
```
原始数据 → 标准化器 → 统一格式 → NATS流 (标准化主题)
```

### **3. 数据存储**
```
标准化数据 → ClickHouse写入器 → 数据库表
```

### **4. 数据分析**
```
数据库表 → 物化视图 → 聚合统计 → 监控视图
```

## 📈 **扩展和定制**

### **添加新的数据类型**
1. 在`data_types.py`中定义新的数据类型
2. 在`normalizer.py`中添加标准化方法
3. 在NATS配置中添加新的流和路由
4. 在ClickHouse中创建对应的表结构

### **添加新的交易所**
1. 实现对应的API客户端
2. 添加标准化方法
3. 更新路由配置
4. 测试数据流

### **性能优化**
- 调整NATS流的批处理大小
- 优化ClickHouse表的分区策略
- 配置合适的TTL策略
- 启用数据压缩

## ✅ **配置验证**

### **验证NATS配置**
```bash
# 检查YAML语法
python -c "import yaml; yaml.safe_load(open('config/nats_unified_streams.yaml'))"

# 验证流配置
nats stream ls
```

### **验证ClickHouse配置**
```bash
# 检查表结构
clickhouse-client --query "SHOW TABLES FROM marketprism"

# 验证数据写入
clickhouse-client --query "SELECT count() FROM marketprism.unified_trade_data"
```

### **验证数据管道**
```bash
# 运行配置测试
python test_configuration.py

# 检查服务状态
python -c "from services.health_check import check_all_services; check_all_services()"
```

## 📝 **最佳实践**

1. **配置管理**
   - 使用版本控制管理配置文件
   - 定期备份配置
   - 使用环境变量管理敏感信息

2. **性能优化**
   - 根据数据量调整批处理大小
   - 合理设置TTL策略
   - 监控资源使用情况

3. **数据质量**
   - 实施数据验证规则
   - 设置数据质量告警
   - 定期进行数据审计

4. **安全性**
   - 使用TLS加密连接
   - 实施访问控制
   - 定期更新密码和密钥

---

**文档版本**: v2.0  
**最后更新**: 2024-12-19  
**维护者**: MarketPrism开发团队
