# MarketPrism 策略管理服务

## 🎯 服务概述

策略管理服务是MarketPrism量化交易系统的核心组件，负责管理各种交易策略的创建、配置、监控和控制。支持网格策略、信号交易、定投策略等多种量化交易策略。

## 🚀 功能特性

### 📊 支持的策略类型

1. **网格策略 (Grid Trading)**
   - 支持现货和合约网格
   - 自定义价格区间和网格数量
   - 智能网格密度优化
   - 自动重启功能

2. **信号交易 (Signal Trading)**
   - 多种技术指标信号
   - 自定义止盈止损
   - 仓位管理
   - 信号源集成

3. **定投策略 (Dollar Cost Averaging)**
   - 多币种定投
   - 灵活投资周期
   - 动态分配比例
   - 智能触发条件

### 🔧 管理功能

- **策略创建**：通过API或Grafana界面创建策略
- **实时监控**：策略状态、PnL、持仓实时监控
- **风险控制**：止损、风险预警、仓位限制
- **表现分析**：收益率、夏普比率、最大回撤等指标

## 🏗️ 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    策略管理服务架构                            │
├─────────────────┬─────────────────┬─────────────────────────┤
│   📱 API接口     │   🧠 策略引擎     │   📊 数据分析            │
│   • REST API    │   • 网格策略      │   • 性能指标            │
│   • WebSocket   │   • 信号交易      │   • 风险监控            │
│   • Grafana集成 │   • 定投策略      │   • 回测分析            │
├─────────────────┼─────────────────┼─────────────────────────┤
│   🔄 任务调度     │   💾 数据存储     │   🔔 告警通知            │
│   • 定时执行     │   • 策略配置      │   • 风险预警            │
│   • 事件触发     │   • 交易记录      │   • 状态通知            │
│   • 条件监控     │   • 性能数据      │   • 异常告警            │
└─────────────────┴─────────────────┴─────────────────────────┘
```

## 📡 API接口

### 策略管理

#### 创建网格策略
```bash
POST /api/v1/strategies/grid
Content-Type: application/json

{
  "name": "BTC网格策略1",
  "symbol": "BTCUSDT",
  "exchange": "binance",
  "lower_price": 60000,
  "upper_price": 70000,
  "grid_count": 20,
  "investment_amount": 1000,
  "auto_restart": true
}
```

#### 创建信号交易策略
```bash
POST /api/v1/strategies/signal
Content-Type: application/json

{
  "name": "ETH技术指标策略",
  "symbol": "ETHUSDT",
  "exchange": "binance",
  "signal_source": "rsi_macd",
  "position_size": 0.1,
  "stop_loss": 5.0,
  "take_profit": 10.0
}
```

#### 创建定投策略
```bash
POST /api/v1/strategies/dca
Content-Type: application/json

{
  "name": "多币种定投计划",
  "symbols": ["BTCUSDT", "ETHUSDT", "ADAUSDT"],
  "exchange": "binance",
  "interval": "daily",
  "amount_per_order": 100,
  "allocation": {
    "BTCUSDT": 0.5,
    "ETHUSDT": 0.3,
    "ADAUSDT": 0.2
  }
}
```

### 策略控制

#### 获取策略列表
```bash
GET /api/v1/strategies
```

#### 获取策略详情
```bash
GET /api/v1/strategies/{strategy_id}
```

#### 暂停策略
```bash
POST /api/v1/strategies/{strategy_id}/pause
```

#### 恢复策略
```bash
POST /api/v1/strategies/{strategy_id}/resume
```

#### 停止策略
```bash
POST /api/v1/strategies/{strategy_id}/stop
```

#### 获取策略表现
```bash
GET /api/v1/strategies/{strategy_id}/performance
```

## 🔌 Grafana 集成

### 数据源配置

1. **安装MarketPrism数据源插件**
```bash
grafana-cli plugins install marketprism-datasource
```

2. **配置数据源**
```json
{
  "name": "MarketPrism策略",
  "type": "marketprism-datasource",
  "url": "http://localhost:8087",
  "access": "proxy",
  "jsonData": {
    "apiKey": "your-api-key",
    "timeout": 30
  }
}
```

### 仪表板模板

#### 策略概览仪表板
- 活跃策略列表
- 总体PnL趋势
- 风险指标监控
- 告警状态显示

#### 策略详情仪表板
- 策略配置信息
- 实时表现图表
- 交易历史记录
- 风险分析指标

## 🚀 启动服务

### 直接启动
```bash
cd services/strategy-management
python main.py
```

### 使用启动脚本
```bash
./start-strategy-management.sh
```

### Docker启动
```bash
docker-compose up strategy-management
```

## ⚙️ 配置说明

### 服务配置 (config/services.yaml)
```yaml
strategy-management:
  host: "0.0.0.0"
  port: 8087
  log_level: "info"
  max_strategies: 100
  default_exchange: "binance"
  risk_limits:
    max_position_size: 0.1
    max_daily_loss: 5.0
    max_drawdown: 20.0
```

### 策略配置 (config/strategies.yaml)
```yaml
grid_strategies:
  default_settings:
    min_grid_count: 5
    max_grid_count: 100
    min_investment: 10
    default_auto_restart: true

signal_strategies:
  default_settings:
    default_stop_loss: 5.0
    default_take_profit: 10.0
    max_position_size: 0.2

dca_strategies:
  default_settings:
    supported_intervals: ["daily", "weekly", "monthly"]
    min_amount_per_order: 1
    max_symbols: 10
```

## 📊 监控指标

### 策略级别指标
- **收益指标**：总收益率、日收益率、月收益率
- **风险指标**：最大回撤、波动率、夏普比率
- **交易指标**：胜率、平均持仓时间、交易频率

### 系统级别指标
- **服务状态**：活跃策略数、总管理资金、系统负载
- **性能指标**：API响应时间、处理吞吐量、错误率

## 🔔 告警配置

### 风险告警
- 策略回撤超过阈值
- 单日损失超过限制
- 仓位集中度过高

### 系统告警
- 策略执行异常
- 交易所连接中断
- 服务资源不足

## 🧪 测试

### 单元测试
```bash
cd tests/unit
python -m pytest test_strategy_management.py -v
```

### 集成测试
```bash
cd tests/integration
python -m pytest test_strategy_api.py -v
```

### 性能测试
```bash
cd tests/performance
python test_strategy_load.py
```

## 📝 开发指南

### 添加新策略类型

1. **定义配置模型**
```python
class CustomStrategyConfig(BaseModel):
    name: str
    custom_param: float
    # 其他参数...
```

2. **实现策略逻辑**
```python
async def create_custom_strategy(self, config: CustomStrategyConfig):
    # 策略创建逻辑
    pass
```

3. **添加API端点**
```python
@self.app.post("/api/v1/strategies/custom")
async def create_custom_strategy(config: CustomStrategyConfig):
    # API处理逻辑
    pass
```

### 扩展数据源
- 支持更多交易所API
- 集成外部信号源
- 添加自定义指标计算

## 🤝 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/新功能`)
3. 提交更改 (`git commit -am '添加新功能'`)
4. 推送到分支 (`git push origin feature/新功能`)
5. 创建 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🆘 支持

如果您遇到问题或有建议，请：
1. 查看 [FAQ](docs/FAQ.md)
2. 提交 [Issue](https://github.com/marketprism/issues)
3. 联系开发团队

---

**MarketPrism策略管理服务** - 让量化交易更简单、更智能！