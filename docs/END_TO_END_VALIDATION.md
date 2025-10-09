# MarketPrism 端到端数据流验证功能说明

## 概述

MarketPrism 系统的端到端数据流验证功能提供了完整的数据链路健康检查，覆盖从数据采集到存储的全流程，包括 NATS JetStream、热端数据库（marketprism_hot）和冷端数据库（marketprism_cold）。

## 完整数据流路径

```
数据采集器 → NATS JetStream → 热端存储（marketprism_hot）→ 冷端存储（marketprism_cold）
    ↓              ↓                    ↓                           ↓
  8种数据类型    2个流              TTL: 3天                    永久存储
```

## 验证覆盖范围

### 1. NATS JetStream 验证

**检查项**：
- 流数量（期望：2 个）
  - MARKET_DATA：7 个 subjects（trades, funding_rates, open_interests, liquidations, lsr_top_positions, lsr_all_accounts, volatility_indices）
  - ORDERBOOK_SNAP：1 个 subject（orderbook snapshots）
- 消费者数量（期望：8 个）
- 消息数量（实时统计）

**输出示例**：
```
✅ JetStream: 正常
✅   - 流数量: 2
✅   - 消费者数量: 8
✅   - 消息数量: 12548
✅   - MARKET_DATA subjects(期望): 7
✅   - ORDERBOOK_SNAP subjects(期望): 1
```

### 2. 热端数据库验证（marketprism_hot）

**检查 8 种数据类型**：

**高频数据**（必须有数据）：
- `trades`（交易数据）
- `orderbooks`（订单簿快照）

**低频数据**（应该有数据，但可容忍短时间为空）：
- `funding_rates`（资金费率）
- `open_interests`（未平仓量）
- `lsr_top_positions`（多空持仓比-大户）
- `lsr_all_accounts`（多空持仓比-全账户）

**事件驱动数据**（可能为空，取决于市场活动）：
- `liquidations`（强平数据）
- `volatility_indices`（波动率指数，仅 Deribit）

**输出示例**：
```
✅ ClickHouse 热端数据统计 (marketprism_hot):
✅   - trades(高频): 2848 条
✅   - orderbooks(高频): 9597 条
✅   - funding_rates(低频): 13 条
✅   - open_interests(低频): 21 条
✅   - liquidations(事件): 0 条 (事件驱动，取决于市场活动)
✅   - lsr_top_positions(低频): 25 条
✅   - lsr_all_accounts(低频): 25 条
✅   - volatility_indices(低频): 7 条
```

### 3. 冷端数据库验证（marketprism_cold）

**检查项**：
- 8 种数据类型的记录数
- 与热端数据的一致性（冷端数据量应 ≤ 热端数据量）
- 数据迁移状态

**输出示例**：
```
✅ ClickHouse 冷端数据统计 (marketprism_cold):
✅   - trades(高频): 1000 条
✅   - orderbooks(高频): 3000 条
✅   - funding_rates(低频): 5 条
✅   - open_interests(低频): 0 条
✅   - liquidations(事件): 0 条
✅   - lsr_top_positions(低频): 0 条
✅   - lsr_all_accounts(低频): 0 条
✅   - volatility_indices(低频): 0 条
```

### 4. 数据迁移状态分析

**检查项**：
- 冷端/热端数据比例
- 数据一致性（冷端 ≤ 热端）
- 冷端存储服务运行状态

**场景 1：系统刚启动（< 10 分钟）**
```
✅ 数据迁移状态: 系统刚启动（运行 1 分钟），冷端为空是正常的
✅   提示: 热端数据 TTL 默认 3 天，到期后会自动迁移到冷端
```

**场景 2：正常迁移中**
```
✅ 数据迁移状态: 正常（冷端数据量为热端的 22%）
```

**场景 3：热端有数据但冷端为空（长期运行）**
```
⚠️  数据迁移状态: 热端有 18091 条数据，但冷端为空
⚠️    可能原因: 1) TTL 未到期（默认 3 天） 2) 冷端存储服务未运行
⚠️    检测到冷端存储服务未运行，请启动冷端服务
```

**场景 4：数据不一致（冷端 > 热端）**
```
✅ 数据迁移状态: 正常（冷端数据量为热端的 15%）
⚠️  数据一致性警告: 以下表的冷端数据量大于热端（异常）:
⚠️    - liquidations: 热端=0, 冷端=1
```

## 智能系统状态判断

### 运行时间检测

验证功能会自动检测系统运行时间（通过 NATS 进程启动时间），并根据运行时间调整验证标准：

- **刚启动**（< 10 分钟）：
  - 高频数据为 0：提示"系统刚启动，等待中"
  - 冷端为空：提示"TTL 未到期是正常的"
  - 低频数据为 0：不报警

- **长期运行**（≥ 10 分钟）：
  - 高频数据为 0：警告"应该有数据"
  - 冷端为空但热端有数据：检查冷端服务状态
  - 所有低频数据为 0：提示"可能需要等待更长时间"

## 验证成功标准

### 完全成功 ✅
```
✅ 端到端数据流: 完整验证通过 ✅
✅   - JetStream: 2 个流，12548 条消息
✅   - 热端数据: 12536 条（高频: 2/2 类型有数据）
✅   - 冷端数据: 4005 条（高频: 2/2 类型有数据）
```

**条件**：
- JetStream 有 ≥1 个流
- 热端有数据（总数 > 0）
- 高频数据（trades, orderbooks）至少有一种有数据
- 无数据一致性警告

### 部分成功 ⚠️
```
⚠️  端到端数据流: 部分验证通过（有数据但存在警告）⚠️
```

**条件**：
- 热端有数据
- 但存在以下问题之一：
  - 数据一致性警告（冷端 > 热端）
  - 冷端服务未运行
  - 高频数据缺失（长期运行场景）

### 失败 ❌
```
⚠️  端到端数据流: 暂无数据，系统可能仍在初始化
```

**条件**：
- JetStream 无法获取流信息
- 热端完全无数据

## 使用方法

### 1. 启动时自动验证

系统启动后会自动执行健康检查，包含端到端验证：

```bash
./scripts/manage_all.sh start
```

### 2. 手动执行验证

```bash
./scripts/manage_all.sh health
```

### 3. 仅执行端到端验证

在脚本中调用验证函数：

```bash
source scripts/manage_all.sh
validate_end_to_end_data_flow
```

## 常见问题

### Q1: 为什么冷端一直为空？

**A**: 可能的原因：
1. **系统刚启动**：热端数据 TTL 默认 3 天，需要等待数据到期后才会迁移到冷端
2. **冷端服务未运行**：检查 `http://localhost:8086/health` 是否返回 healthy
3. **TTL 未到期**：即使系统运行很久，如果热端数据还在 TTL 期内，也不会迁移

### Q2: 为什么低频数据一直为 0？

**A**: 低频数据（funding_rates, open_interests 等）通常每分钟或每小时更新一次，需要等待更长时间。如果系统运行超过 10 分钟仍为 0，可能需要检查：
- 数据采集器日志：`services/data-collector/logs/collector.log`
- 交易所 API 是否正常响应
- 网络连接是否正常

### Q3: 为什么 liquidations 和 volatility_indices 一直为 0？

**A**: 这两种数据是事件驱动的：
- **liquidations**：只有在市场发生强平事件时才会产生数据
- **volatility_indices**：仅 Deribit 交易所提供，且更新频率较低

这是正常现象，不影响系统健康。

### Q4: 数据一致性警告是什么意思？

**A**: 如果冷端某个表的数据量大于热端，说明数据状态异常。正常情况下：
- 冷端数据是热端数据的历史归档
- 冷端数据量应该 ≤ 热端数据量

出现不一致可能是因为：
- 手动操作导致数据不一致
- 热端数据被意外清空
- 数据迁移逻辑异常

建议检查热端和冷端的数据完整性。

## 技术实现

### 核心函数

`validate_end_to_end_data_flow()` 位于 `scripts/manage_all.sh`

### 关键技术点

1. **系统运行时间检测**：
   ```bash
   local nats_pid=$(pgrep -f "nats-server" | head -n1)
   local start_time=$(ps -p "$nats_pid" -o lstart=)
   local start_epoch=$(date -d "$start_time" +%s)
   local system_uptime_minutes=$(( (now_epoch - start_epoch) / 60 ))
   ```

2. **JetStream 状态查询**：
   ```bash
   curl -s http://localhost:8222/jsz
   ```

3. **ClickHouse 数据统计**：
   ```bash
   clickhouse-client --query "SELECT COUNT(*) FROM marketprism_hot.trades"
   ```

4. **数据一致性检查**：
   ```bash
   if [ "${cold_counts[$t]}" -gt "${hot_counts[$t]}" ]; then
       # 报警：冷端 > 热端
   fi
   ```

## 相关文档

- [系统架构文档](./architecture/README.md)
- [数据存储服务集成](./architecture/storage_service_integration.md)
- [NATS JetStream 配置](./NATS_AUTO_PUSH_CONFIGURATION.md)
- [自动化修复总结](./AUTOMATED_FIXES_SUMMARY.md)

