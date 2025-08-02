# MarketPrism Data Collector 简化Docker部署指南

## 🎯 **简化改造说明**

本版本对MarketPrism Data Collector进行了Docker部署简化改造：

### ✅ **改造内容**
1. **简化运行模式**：只保留`launcher`模式（完整数据收集系统）
2. **统一Docker配置**：简化docker-compose配置，移除多余服务定义
3. **统一入口脚本**：移除多模式切换逻辑，专注launcher模式
4. **功能验证**：确保所有8种数据类型和5个交易所正常工作

### 🚀 **快速部署**

#### 1. 启动统一NATS容器
```bash
cd services/message-broker/unified-nats
sudo docker-compose -f docker-compose.unified.yml up -d
```

#### 2. 启动Data Collector
```bash
cd services/data-collector
sudo docker-compose -f docker-compose.unified.yml up -d
```

#### 3. 验证部署
```bash
# 检查容器状态
sudo docker ps | grep marketprism

# 检查NATS数据流
curl -s http://localhost:8222/jsz

# 查看Data Collector日志
sudo docker logs marketprism-data-collector --tail 50
```

## 📋 **配置说明**

### 环境变量配置
```bash
# 基础配置
LOG_LEVEL=INFO
COLLECTOR_MODE=launcher

# NATS配置
MARKETPRISM_NATS_SERVERS=nats://localhost:4222

# 端口配置（host网络模式）
# - 8086: 健康检查端口（暂未启用）
# - 9093: Prometheus指标端口（暂未启用）
```

### 支持的功能
- ✅ **8种数据类型**：orderbook, trade, funding_rate, open_interest, lsr_top_position, lsr_all_account, volatility_index, liquidation
- ✅ **5个交易所**：Binance现货/衍生品, OKX现货/衍生品, Deribit衍生品
- ✅ **统一NATS集成**：自动连接到统一NATS容器
- ✅ **实时数据收集**：持续收集和推送市场数据

## 🔧 **技术架构**

### 简化架构图
```
┌─────────────────────────────────────┐
│     MarketPrism Data Collector      │
│         (launcher模式)              │
│                                     │
│  ┌─────────────────────────────────┐ │
│  │        数据收集引擎              │ │
│  │  • 5个交易所                    │ │
│  │  • 8种数据类型                  │ │
│  │  • 实时WebSocket连接            │ │
│  └─────────────────────────────────┘ │
│                 │                   │
└─────────────────┼───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│        统一NATS容器                 │
│                                     │
│  • JetStream持久化                  │
│  • 消息队列管理                     │
│  • 数据流分发                       │
└─────────────────────────────────────┘
```

### 网络配置
- **网络模式**：host网络模式，直接使用主机网络
- **NATS连接**：通过localhost:4222连接到统一NATS容器
- **端口暴露**：8086（健康检查）、9093（监控）

## 📊 **验证结果**

### 功能验证通过
- ✅ **容器构建**：成功构建简化Docker镜像
- ✅ **容器启动**：成功启动launcher模式
- ✅ **NATS连接**：成功连接到统一NATS容器
- ✅ **数据收集**：所有数据类型正常收集
- ✅ **数据推送**：29,897条消息，207MB数据成功推送到NATS

### 实时数据验证
```bash
# 示例日志输出
2025-08-02 12:32:24,662 - funding_rate_manager.okx_derivatives - INFO - 资金费率数据处理完成
2025-08-02 12:32:27,789 - funding_rate_manager.binance_derivatives - INFO - 资金费率数据处理完成  
2025-08-02 12:32:33,080 - vol_index_manager.deribit_derivatives - INFO - 波动率指数数据处理完成
2025-08-02 12:32:35,661 - lsr_lsr_all_account_okx_derivatives_derivatives - INFO - lsr_all_account数据处理完成
```

## 🛠️ **故障排除**

### 常见问题
1. **端口冲突**：确保4222和8222端口未被占用
2. **NATS连接失败**：检查统一NATS容器是否正常运行
3. **数据收集异常**：查看容器日志排查具体问题

### 日志查看
```bash
# 查看Data Collector日志
sudo docker logs marketprism-data-collector --tail 100

# 查看NATS状态
curl -s http://localhost:8222/jsz

# 检查容器状态
sudo docker ps | grep marketprism
```

## 🎉 **部署成功标志**

当看到以下情况时，说明部署成功：
1. 容器状态显示为"Up"且健康检查通过
2. NATS中有持续增长的消息数量
3. 日志中显示各种数据类型的"数据处理完成"信息
4. 没有连接错误或异常日志

---

**🎊 MarketPrism Data Collector Docker部署简化改造完成！**
