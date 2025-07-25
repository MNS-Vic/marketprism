# 📊 MarketPrism 大户多空持仓比数据标准化器

## 🎯 **概述**

本文档详细介绍了MarketPrism系统中大户/精英交易员多空持仓比数据的标准化处理方案，支持Binance和OKX两大交易所的数据采集、标准化、存储和分析。

## 📡 **支持的API**

### **Binance API**
- **端点**: `/futures/data/topLongShortPositionRatio`
- **描述**: 大户多空持仓量比（保证金余额排名前20%用户）
- **数据类型**: 持仓量比例
- **更新频率**: 支持5m-1d多种周期

### **OKX API**
- **端点**: `/api/v5/rubik/stat/contracts/long-short-account-ratio-contract-top-trader`
- **描述**: 精英交易员合约多空持仓仓位比
- **数据类型**: 持仓量比例
- **更新频率**: 支持5m-1d多种周期

## 🔧 **数据结构分析**

### **Binance数据格式**
```json
{
  "symbol": "BTCUSDT",
  "longShortRatio": "1.4342",
  "longAccount": "0.5344", 
  "shortAccount": "0.4238",
  "timestamp": "1583139600000"
}
```

### **OKX数据格式**
```json
{
  "code": "0",
  "msg": "",
  "data": [{
    "ccy": "BTC",
    "longShortRatio": "1.2345",
    "longRatio": "0.5523",
    "shortRatio": "0.4477", 
    "ts": "1583139600000"
  }]
}
```

## 📋 **标准化数据类型**

### **NormalizedTopTraderLongShortRatio**
```python
@dataclass
class NormalizedTopTraderLongShortRatio:
    # 基础信息
    exchange_name: str              # 交易所名称 (binance/okx)
    symbol_name: str                # 标准交易对格式 (BTC-USDT)
    currency: str                   # 币种名称 (BTC)
    
    # 核心持仓比数据
    long_short_ratio: Decimal       # 多空持仓量比值
    long_position_ratio: Decimal    # 多仓持仓量比例 (0-1)
    short_position_ratio: Decimal   # 空仓持仓量比例 (0-1)
    
    # 元数据
    data_type: str                  # 数据类型 (position/account)
    period: Optional[str]           # 时间周期 (5m,15m,1h等)
    instrument_type: str            # 合约类型 (futures/swap)
    
    # 数据质量指标
    data_quality_score: Optional[Decimal]  # 数据质量评分 (0-1)
    ratio_sum_check: Optional[bool]        # 比例和检查
    
    # 时间信息
    timestamp: datetime             # 数据时间戳
    collected_at: datetime          # 采集时间
    raw_data: Optional[Dict]        # 原始数据
```

## 🔄 **标准化处理器**

### **Binance标准化器**
```python
def normalize_binance_top_trader_long_short_ratio(
    self, 
    data: Dict[str, Any], 
    period: Optional[str] = None
) -> Optional[NormalizedTopTraderLongShortRatio]:
    """
    标准化Binance大户多空持仓比数据
    
    特点:
    - 处理symbol格式转换 (BTCUSDT -> BTC-USDT)
    - 提取币种信息
    - 数据质量检查和评分
    - 时间戳标准化
    """
```

### **OKX标准化器**
```python
def normalize_okx_top_trader_long_short_ratio(
    self, 
    data: Dict[str, Any], 
    period: Optional[str] = None
) -> Optional[NormalizedTopTraderLongShortRatio]:
    """
    标准化OKX精英交易员多空持仓比数据
    
    特点:
    - 处理API响应包装格式
    - 币种到交易对映射 (BTC -> BTC-USDT)
    - 数据质量检查和评分
    - 时间戳标准化
    """
```

## 📊 **数据质量控制**

### **质量检查项目**
1. **比例和检查**: `long_position_ratio + short_position_ratio ≈ 1.0`
2. **比值合理性**: `long_short_ratio > 0`
3. **时间戳有效性**: 时间戳不为空且合理
4. **必要字段完整性**: 核心字段不为空

### **质量评分算法**
```python
data_quality_score = 1.0
if not ratio_sum_check:
    data_quality_score -= 0.3  # 比例和不正确扣分
if long_short_ratio <= 0:
    data_quality_score -= 0.5  # 比值异常扣分
```

## 📡 **NATS消息流配置**

### **流定义**
- **流名称**: `top-trader-long-short-ratio-data`
- **主题模式**: `top-trader-ratio.>`
- **存储**: 文件存储，30天保留期
- **容量**: 100万消息，10GB存储

### **主题路由规则**
```yaml
# 原始数据
top-trader-ratio.okx.{currency}           # OKX原始数据
top-trader-ratio.binance.{symbol}         # Binance原始数据

# 标准化数据
top-trader-ratio.normalized.{exchange}.{currency}  # 标准化数据

# 告警数据
top-trader-ratio.alerts.{alert_type}.{exchange}.{currency}  # 异常告警
```

### **消费者配置**
1. **clickhouse-writer**: 写入ClickHouse数据库
2. **realtime-monitor**: 实时监控持仓变化
3. **trend-analyzer**: 分析持仓趋势
4. **alert-processor**: 处理异常告警

## 🗄️ **ClickHouse存储方案**

### **主表结构**
```sql
CREATE TABLE top_trader_long_short_ratio (
    exchange_name LowCardinality(String),
    symbol_name String,
    currency LowCardinality(String),
    long_short_ratio Decimal64(8),
    long_position_ratio Decimal64(8),
    short_position_ratio Decimal64(8),
    data_quality_score Nullable(Decimal64(4)),
    ratio_sum_check Nullable(UInt8),
    period LowCardinality(String),
    timestamp DateTime64(3, 'UTC'),
    collected_at DateTime64(3, 'UTC'),
    raw_data String
) ENGINE = MergeTree()
PARTITION BY (exchange_name, toYYYYMM(timestamp))
ORDER BY (exchange_name, currency, symbol_name, period, timestamp)
TTL timestamp + INTERVAL 180 DAY;
```

### **物化视图**
1. **按小时聚合**: `top_trader_ratio_hourly_stats`
2. **按日聚合**: `top_trader_ratio_daily_stats`

### **监控视图**
1. **最新数据**: `latest_top_trader_ratio`
2. **排行榜**: `top_trader_ratio_rankings`
3. **异常监控**: `top_trader_ratio_anomalies`

## 🚨 **异常监控与告警**

### **异常类型定义**
```python
sentiment_levels = {
    "EXTREMELY_BULLISH": long_short_ratio > 3.0,
    "VERY_BULLISH": long_short_ratio > 2.0,
    "BULLISH": long_short_ratio > 1.5,
    "NEUTRAL": 0.67 <= long_short_ratio <= 1.5,
    "BEARISH": long_short_ratio < 0.67,
    "VERY_BEARISH": long_short_ratio < 0.5,
    "EXTREMELY_BEARISH": long_short_ratio < 0.33
}
```

### **数据质量告警**
- 数据质量评分 < 0.7
- 比例和检查失败
- 连续数据缺失

## 🔍 **使用示例**

### **数据标准化**
```python
from collector.normalizer import DataNormalizer

normalizer = DataNormalizer()

# Binance数据标准化
binance_data = {
    "symbol": "BTCUSDT",
    "longShortRatio": "1.4342",
    "longAccount": "0.5344",
    "shortAccount": "0.4238",
    "timestamp": "1583139600000"
}

result = normalizer.normalize_binance_top_trader_long_short_ratio(
    binance_data, 
    period="1h"
)

# OKX数据标准化
okx_data = {
    "code": "0",
    "data": [{
        "ccy": "BTC",
        "longShortRatio": "1.2345",
        "longRatio": "0.5523",
        "shortRatio": "0.4477",
        "ts": "1583139600000"
    }]
}

result = normalizer.normalize_okx_top_trader_long_short_ratio(
    okx_data, 
    period="1h"
)
```

### **数据查询**
```sql
-- 查询最新的大户持仓比数据
SELECT * FROM latest_top_trader_ratio 
WHERE currency = 'BTC' 
ORDER BY timestamp DESC LIMIT 10;

-- 查询异常持仓比情况
SELECT * FROM top_trader_ratio_anomalies 
WHERE sentiment_level IN ('EXTREMELY_BULLISH', 'EXTREMELY_BEARISH');

-- 查询持仓比趋势
SELECT 
    currency,
    period,
    avg_long_short_ratio,
    ratio_change_percent
FROM top_trader_ratio_daily_stats 
WHERE date >= today() - 7 
ORDER BY currency, period, date;
```

## ✅ **验证与测试**

系统提供了完整的测试套件，包括：
- 数据标准化功能测试
- 错误处理测试
- 数据质量检查测试
- 性能基准测试

运行测试：
```bash
python3 standalone_normalizer_test.py
```

## 📈 **性能指标**

- **数据处理延迟**: < 100ms
- **数据质量准确率**: > 99%
- **存储压缩比**: ~70%
- **查询响应时间**: < 500ms

---

**文档版本**: v1.0  
**最后更新**: 2024-12-19  
**维护者**: MarketPrism开发团队
