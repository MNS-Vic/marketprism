# 📚 MarketPrism 统一API使用示例

## 🎯 **概述**

本文档提供了MarketPrism统一交易数据标准化器的完整API使用示例，包括数据标准化、查询、监控等各种场景的实际代码示例。

## 🔧 **基础使用**

### **1. 导入和初始化**

```python
import sys
sys.path.append('services/data-collector')

from collector.normalizer import DataNormalizer
from collector.data_types import (
    NormalizedTrade, 
    NormalizedMarketLongShortRatio,
    NormalizedTopTraderLongShortRatio
)
from decimal import Decimal
from datetime import datetime, timezone

# 初始化标准化器
normalizer = DataNormalizer()
```

### **2. Binance现货数据标准化**

```python
# Binance现货逐笔交易数据
binance_spot_data = {
    "e": "trade",
    "E": 1672515782136,
    "s": "BTCUSDT",
    "t": 12345,
    "p": "45000.50",
    "q": "0.1",
    "T": 1672515782136,
    "m": False  # 主动买入
}

# 标准化处理
result = normalizer.normalize_binance_spot_trade(binance_spot_data)

if result:
    print(f"交易所: {result.exchange_name}")      # binance
    print(f"交易对: {result.symbol_name}")        # BTC-USDT
    print(f"币种: {result.currency}")             # BTC
    print(f"价格: {result.price}")                # 45000.50
    print(f"数量: {result.quantity}")             # 0.1
    print(f"方向: {result.side}")                 # buy
    print(f"类型: {result.trade_type}")           # spot
    print(f"成交金额: {result.quote_quantity}")   # 4500.05
    
    # 转换为字典格式
    trade_dict = result.to_dict()
    print(f"字典格式: {trade_dict}")
```

### **3. Binance期货数据标准化**

```python
# Binance期货归集交易数据
binance_futures_data = {
    "e": "aggTrade",
    "E": 123456789,
    "s": "BTCUSDT",
    "a": 5933014,      # 归集交易ID
    "p": "45000.50",
    "q": "0.1",
    "f": 100,          # 首个交易ID
    "l": 105,          # 末次交易ID
    "T": 123456785,
    "m": True          # 主动卖出
}

# 标准化处理
result = normalizer.normalize_binance_futures_trade(binance_futures_data)

if result:
    print(f"交易所: {result.exchange_name}")      # binance
    print(f"交易类型: {result.trade_type}")       # futures
    print(f"方向: {result.side}")                 # sell
    print(f"归集ID: {result.agg_trade_id}")       # 5933014
    print(f"首个ID: {result.first_trade_id}")     # 100
    print(f"末次ID: {result.last_trade_id}")      # 105
```

### **4. OKX数据标准化**

```python
# OKX交易数据（WebSocket格式）
okx_data = {
    "arg": {
        "channel": "trades",
        "instId": "BTC-USDT"
    },
    "data": [{
        "instId": "BTC-USDT",
        "tradeId": "130639474",
        "px": "45000.50",
        "sz": "0.1",
        "side": "buy",
        "ts": "1629386781174"
    }]
}

# 自动识别交易类型
result = normalizer.normalize_okx_trade(okx_data, trade_type="auto")

if result:
    print(f"交易所: {result.exchange_name}")      # okx
    print(f"交易类型: {result.trade_type}")       # 自动识别
    print(f"方向: {result.side}")                 # buy (直接使用)
    
# 指定交易类型
result_spot = normalizer.normalize_okx_trade(okx_data, trade_type="spot")
result_swap = normalizer.normalize_okx_trade(okx_data, trade_type="swap")
```

## 📊 **市场情绪数据处理**

### **1. 市场多空人数比数据**

```python
# Binance市场多空人数比数据
binance_market_ratio = {
    "symbol": "BTCUSDT",
    "longShortRatio": "1.2500",
    "longAccount": "0.5556",
    "shortAccount": "0.4444",
    "timestamp": "1672515782000"
}

result = normalizer.normalize_binance_market_long_short_ratio(
    binance_market_ratio, 
    period="1h"
)

if result:
    print(f"多空人数比: {result.long_short_ratio}")      # 1.2500
    print(f"多仓人数比例: {result.long_account_ratio}")  # 0.5556
    print(f"空仓人数比例: {result.short_account_ratio}") # 0.4444
    print(f"数据质量: {result.data_quality_score}")     # 质量评分
```

### **2. 大户持仓比数据**

```python
# Binance大户持仓比数据
binance_top_trader = {
    "symbol": "BTCUSDT",
    "longShortRatio": "2.1000",
    "longAccount": "0.6774",
    "shortAccount": "0.3226",
    "timestamp": "1672515782000"
}

result = normalizer.normalize_binance_top_trader_long_short_ratio(
    binance_top_trader,
    period="1h"
)

if result:
    print(f"大户多空比: {result.long_short_ratio}")
    print(f"数据类型: {result.data_type}")  # position
```

## 🔄 **批量数据处理**

### **1. 批量标准化**

```python
# 批量处理不同交易所的数据
trade_data_batch = [
    {
        "source": "binance_spot",
        "data": {"e": "trade", "s": "BTCUSDT", "p": "45000", "q": "0.1", "m": False}
    },
    {
        "source": "okx",
        "data": {"data": [{"instId": "ETH-USDT", "px": "3000", "sz": "1.0", "side": "sell"}]}
    }
]

normalized_results = []

for item in trade_data_batch:
    if item["source"] == "binance_spot":
        result = normalizer.normalize_binance_spot_trade(item["data"])
    elif item["source"] == "okx":
        result = normalizer.normalize_okx_trade(item["data"])
    
    if result:
        normalized_results.append(result)

print(f"成功标准化 {len(normalized_results)} 条数据")
```

### **2. 数据质量检查**

```python
def check_data_quality(normalized_trade):
    """检查标准化后数据的质量"""
    issues = []
    
    # 基本字段检查
    if not normalized_trade.exchange_name:
        issues.append("缺少交易所名称")
    
    if normalized_trade.price <= 0:
        issues.append("价格异常")
    
    if normalized_trade.quantity <= 0:
        issues.append("数量异常")
    
    if normalized_trade.side not in ["buy", "sell"]:
        issues.append("交易方向异常")
    
    # 时间戳检查
    if normalized_trade.timestamp:
        time_diff = datetime.now(timezone.utc) - normalized_trade.timestamp
        if time_diff.total_seconds() > 3600:  # 超过1小时
            issues.append("数据时间过旧")
    
    return issues

# 使用示例
for trade in normalized_results:
    issues = check_data_quality(trade)
    if issues:
        print(f"数据质量问题: {issues}")
    else:
        print("数据质量正常")
```

## 📈 **实时数据流处理**

### **1. WebSocket数据处理**

```python
import asyncio
import websockets
import json

async def process_realtime_data():
    """处理实时交易数据流"""
    
    async def handle_binance_stream():
        uri = "wss://stream.binance.com:9443/ws/btcusdt@trade"
        async with websockets.connect(uri) as websocket:
            async for message in websocket:
                data = json.loads(message)
                
                # 标准化数据
                normalized = normalizer.normalize_binance_spot_trade(data)
                if normalized:
                    print(f"Binance: {normalized.price} @ {normalized.quantity}")
    
    async def handle_okx_stream():
        # OKX WebSocket处理逻辑
        pass
    
    # 并发处理多个数据流
    await asyncio.gather(
        handle_binance_stream(),
        handle_okx_stream()
    )

# 运行实时数据处理
# asyncio.run(process_realtime_data())
```

### **2. 数据聚合和分析**

```python
from collections import defaultdict
from statistics import mean

class TradeAnalyzer:
    """交易数据分析器"""
    
    def __init__(self):
        self.trades_by_exchange = defaultdict(list)
        self.trades_by_currency = defaultdict(list)
    
    def add_trade(self, normalized_trade):
        """添加标准化交易数据"""
        self.trades_by_exchange[normalized_trade.exchange_name].append(normalized_trade)
        self.trades_by_currency[normalized_trade.currency].append(normalized_trade)
    
    def get_price_stats(self, currency):
        """获取价格统计"""
        trades = self.trades_by_currency[currency]
        if not trades:
            return None
        
        prices = [float(trade.price) for trade in trades]
        return {
            "currency": currency,
            "count": len(prices),
            "avg_price": mean(prices),
            "min_price": min(prices),
            "max_price": max(prices),
            "latest_price": prices[-1]
        }
    
    def get_volume_stats(self, exchange):
        """获取交易量统计"""
        trades = self.trades_by_exchange[exchange]
        if not trades:
            return None
        
        total_volume = sum(float(trade.quantity) for trade in trades)
        buy_volume = sum(float(trade.quantity) for trade in trades if trade.side == "buy")
        sell_volume = total_volume - buy_volume
        
        return {
            "exchange": exchange,
            "total_volume": total_volume,
            "buy_volume": buy_volume,
            "sell_volume": sell_volume,
            "buy_ratio": buy_volume / total_volume if total_volume > 0 else 0
        }

# 使用示例
analyzer = TradeAnalyzer()

# 添加标准化数据
for trade in normalized_results:
    analyzer.add_trade(trade)

# 获取统计信息
btc_stats = analyzer.get_price_stats("BTC")
binance_volume = analyzer.get_volume_stats("binance")

print(f"BTC价格统计: {btc_stats}")
print(f"Binance交易量统计: {binance_volume}")
```

## 🔍 **错误处理和调试**

### **1. 错误处理最佳实践**

```python
def safe_normalize_trade(normalizer, data, source_type):
    """安全的数据标准化处理"""
    try:
        if source_type == "binance_spot":
            result = normalizer.normalize_binance_spot_trade(data)
        elif source_type == "binance_futures":
            result = normalizer.normalize_binance_futures_trade(data)
        elif source_type == "okx":
            result = normalizer.normalize_okx_trade(data)
        else:
            raise ValueError(f"不支持的数据源类型: {source_type}")
        
        if result is None:
            print(f"标准化失败: {data}")
            return None
        
        return result
        
    except Exception as e:
        print(f"标准化异常 [{source_type}]: {e}")
        print(f"原始数据: {data}")
        return None

# 使用示例
test_data = {"e": "trade", "s": "INVALID"}
result = safe_normalize_trade(normalizer, test_data, "binance_spot")
```

### **2. 数据验证工具**

```python
def validate_normalized_trade(trade):
    """验证标准化后的交易数据"""
    validation_results = {
        "valid": True,
        "errors": [],
        "warnings": []
    }
    
    # 必需字段检查
    required_fields = ["exchange_name", "symbol_name", "currency", "trade_id", "price", "quantity", "side"]
    for field in required_fields:
        if not hasattr(trade, field) or getattr(trade, field) is None:
            validation_results["errors"].append(f"缺少必需字段: {field}")
            validation_results["valid"] = False
    
    # 数据范围检查
    if hasattr(trade, "price") and trade.price <= 0:
        validation_results["errors"].append("价格必须大于0")
        validation_results["valid"] = False
    
    if hasattr(trade, "quantity") and trade.quantity <= 0:
        validation_results["errors"].append("数量必须大于0")
        validation_results["valid"] = False
    
    # 枚举值检查
    if hasattr(trade, "side") and trade.side not in ["buy", "sell"]:
        validation_results["errors"].append("交易方向必须是buy或sell")
        validation_results["valid"] = False
    
    return validation_results

# 使用示例
for trade in normalized_results:
    validation = validate_normalized_trade(trade)
    if not validation["valid"]:
        print(f"数据验证失败: {validation['errors']}")
```

## 🚀 **性能优化**

### **1. 批量处理优化**

```python
def batch_normalize_trades(normalizer, trade_batch, batch_size=1000):
    """批量标准化交易数据"""
    results = []
    
    for i in range(0, len(trade_batch), batch_size):
        batch = trade_batch[i:i + batch_size]
        batch_results = []
        
        for item in batch:
            try:
                if item["type"] == "binance_spot":
                    result = normalizer.normalize_binance_spot_trade(item["data"])
                elif item["type"] == "okx":
                    result = normalizer.normalize_okx_trade(item["data"])
                
                if result:
                    batch_results.append(result)
                    
            except Exception as e:
                print(f"批量处理错误: {e}")
                continue
        
        results.extend(batch_results)
        print(f"已处理 {len(results)} / {len(trade_batch)} 条数据")
    
    return results
```

### **2. 内存优化**

```python
def memory_efficient_processing(data_stream):
    """内存高效的数据处理"""
    normalizer = DataNormalizer()
    
    for data_chunk in data_stream:
        # 处理数据块
        normalized = normalizer.normalize_binance_spot_trade(data_chunk)
        
        if normalized:
            # 立即处理，不存储在内存中
            yield normalized
        
        # 清理引用
        del data_chunk
```

---

**文档版本**: v1.0  
**最后更新**: 2024-12-19  
**维护者**: MarketPrism开发团队
