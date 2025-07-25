# MarketPrism 数据标准化规范

## 概述

MarketPrism系统通过统一的数据标准化机制，将来自不同交易所的原始市场数据转换为标准格式，确保数据的一致性和可用性。本文档详细说明了数据标准化的架构、规则和实现方式。

## 标准化架构

### 1. 核心设计原则

- **统一数据模型**：所有交易所数据转换为相同的数据结构
- **适配器模式**：每个交易所有专门的适配器处理特定格式
- **类型安全**：使用强类型和精确的数据类型（如Decimal）
- **错误容错**：完善的异常处理和数据验证
- **性能优化**：支持批量处理和异步操作

### 2. 系统架构图

```
原始数据 → 交易所适配器 → 数据标准化器 → 统一数据模型 → NATS消息队列
   ↓           ↓              ↓              ↓              ↓
Binance → BinanceAdapter → DataNormalizer → NormalizedTrade → market.binance.btc/usdt.trade
  OKX   →   OKXAdapter   → DataNormalizer → NormalizedTrade → market.okx.btc-usdt.trade
Deribit → DeribitAdapter → DataNormalizer → NormalizedTrade → market.deribit.btc-perpetual.trade
```

## 统一数据模型

### 1. 核心数据类型

#### NormalizedTrade（标准化交易数据）
```python
class NormalizedTrade(BaseModel):
    exchange_name: str          # 交易所名称（binance/okx/deribit）
    symbol_name: str           # 交易对名称（BTC/USDT, BTC-PERPETUAL）
    trade_id: str              # 交易唯一标识
    price: Decimal             # 成交价格（高精度）
    quantity: Decimal          # 成交数量
    quote_quantity: Decimal    # 成交金额（价格×数量）
    timestamp: datetime        # 成交时间（UTC）
    is_buyer_maker: bool       # 是否买方为做市方
    collected_at: datetime     # 数据采集时间
```

#### NormalizedOrderBook（标准化订单簿数据）
```python
class NormalizedOrderBook(BaseModel):
    exchange_name: str
    symbol_name: str
    last_update_id: Optional[int]  # 最后更新ID
    bids: List[PriceLevel]         # 买单列表（价格从高到低）
    asks: List[PriceLevel]         # 卖单列表（价格从低到高）
    timestamp: datetime
    collected_at: datetime

class PriceLevel(BaseModel):
    price: Decimal             # 价格档位
    quantity: Decimal          # 该价格的数量
```

#### NormalizedTicker（标准化行情数据）
```python
class NormalizedTicker(BaseModel):
    exchange_name: str
    symbol_name: str
    last_price: Decimal        # 最新成交价
    open_price: Decimal        # 24h开盘价
    high_price: Decimal        # 24h最高价
    low_price: Decimal         # 24h最低价
    volume: Decimal            # 24h成交量
    quote_volume: Decimal      # 24h成交额
    price_change: Decimal      # 24h价格变动
    price_change_percent: Decimal  # 24h价格变动百分比
    weighted_avg_price: Decimal    # 加权平均价
    best_bid_price: Decimal    # 最佳买价
    best_bid_quantity: Decimal # 最佳买量
    best_ask_price: Decimal    # 最佳卖价
    best_ask_quantity: Decimal # 最佳卖量
    trade_count: int           # 24h交易笔数
    timestamp: datetime
```

### 2. 衍生品专用数据类型

#### NormalizedFundingRate（资金费率）
```python
class NormalizedFundingRate(BaseModel):
    exchange_name: str
    symbol_name: str           # 如：BTC-USDT
    funding_rate: Decimal      # 当前资金费率（如0.0001表示0.01%）
    estimated_rate: Optional[Decimal]  # 预测费率
    next_funding_time: datetime        # 下次结算时间
    mark_price: Decimal        # 标记价格
    index_price: Decimal       # 指数价格
    premium_index: Decimal     # 溢价指数
    funding_interval: str      # 结算间隔（如"8h"）
    timestamp: datetime
```

#### NormalizedOpenInterest（持仓量）
```python
class NormalizedOpenInterest(BaseModel):
    exchange_name: str
    symbol_name: str
    open_interest: Decimal     # 持仓量（合约数量）
    open_interest_value: Decimal   # 持仓价值（USDT）
    change_24h: Optional[Decimal]  # 24h变化量
    change_24h_percent: Optional[Decimal]  # 24h变化百分比
    instrument_type: str       # 合约类型（futures/swap/perpetual）
    timestamp: datetime
```

## 交易所适配器实现

### 1. 基础适配器接口

```python
class ExchangeAdapter(ABC):
    """交易所适配器基类"""
    
    @abstractmethod
    async def normalize_trade(self, raw_data: Dict[str, Any]) -> Optional[NormalizedTrade]:
        """标准化交易数据"""
        pass
    
    @abstractmethod
    async def normalize_orderbook(self, raw_data: Dict[str, Any]) -> Optional[NormalizedOrderBook]:
        """标准化订单簿数据"""
        pass
    
    @abstractmethod
    async def normalize_ticker(self, raw_data: Dict[str, Any]) -> Optional[NormalizedTicker]:
        """标准化行情数据"""
        pass
    
    # 通用工具方法
    def _safe_decimal(self, value: Any) -> Decimal:
        """安全转换为Decimal类型"""
        try:
            if value is None or value == '':
                return Decimal('0')
            return Decimal(str(value))
        except:
            return Decimal('0')
    
    def _safe_timestamp(self, timestamp: Any) -> datetime:
        """安全转换时间戳"""
        try:
            if isinstance(timestamp, (int, float)):
                # 处理毫秒时间戳
                if timestamp > 1e10:
                    timestamp = timestamp / 1000
                return datetime.utcfromtimestamp(timestamp)
        except:
            return datetime.utcnow()
```

### 2. Binance适配器

#### 数据格式特点
- 时间戳：毫秒级（需要除以1000）
- 交易对格式：`BTCUSDT`（无分隔符）
- 交易方向：`m`字段表示是否买方为maker

#### 字段映射规则
| 标准字段 | Binance字段 | 说明 |
|---------|-------------|------|
| symbol_name | `s` | 交易对符号 |
| trade_id | `t` | 交易ID |
| price | `p` | 成交价格 |
| quantity | `q` | 成交数量 |
| timestamp | `T` | 成交时间（毫秒） |
| is_buyer_maker | `m` | 买方是否为maker |

#### 实现示例
```python
class BinanceAdapter(ExchangeAdapter):
    async def normalize_trade(self, raw_data: Dict[str, Any]) -> Optional[NormalizedTrade]:
        try:
            price = self._safe_decimal(raw_data["p"])
            quantity = self._safe_decimal(raw_data["q"])
            
            return NormalizedTrade(
                exchange_name="binance",
                symbol_name=raw_data["s"],
                trade_id=str(raw_data["t"]),
                price=price,
                quantity=quantity,
                quote_quantity=price * quantity,
                timestamp=self._safe_timestamp(raw_data["T"]),
                is_buyer_maker=raw_data["m"]
            )
        except Exception as e:
            self.logger.error("标准化Binance交易数据失败", error=str(e))
            return None
```

### 3. OKX适配器

#### 数据格式特点
- 时间戳：毫秒级
- 交易对格式：`BTC-USDT`（带分隔符）
- 字段名称：使用缩写（`px`=价格，`sz`=数量）

#### 字段映射规则
| 标准字段 | OKX字段 | 说明 |
|---------|---------|------|
| symbol_name | `instId` | 交易对标识 |
| trade_id | `tradeId` | 交易ID |
| price | `px` | 成交价格 |
| quantity | `sz` | 成交数量 |
| timestamp | `ts` | 成交时间（毫秒） |
| is_buyer_maker | `side` | 需要转换（sell=maker买入） |

#### 实现示例
```python
class OKXAdapter(ExchangeAdapter):
    async def normalize_trade(self, raw_data: Dict[str, Any]) -> Optional[NormalizedTrade]:
        try:
            price = self._safe_decimal(raw_data["px"])
            quantity = self._safe_decimal(raw_data["sz"])
            
            return NormalizedTrade(
                exchange_name="okx",
                symbol_name=raw_data["instId"],
                trade_id=str(raw_data["tradeId"]),
                price=price,
                quantity=quantity,
                quote_quantity=price * quantity,
                timestamp=self._safe_timestamp(int(raw_data["ts"])),
                is_buyer_maker=raw_data["side"] == "sell"  # OKX特殊转换
            )
        except Exception as e:
            self.logger.error("标准化OKX交易数据失败", error=str(e))
            return None
```

### 4. Deribit适配器

#### 数据格式特点
- 专注衍生品：期货、期权、永续合约
- 时间戳：毫秒级
- 交易对格式：`BTC-PERPETUAL`、`BTC-25DEC21-50000-C`
- 数量字段：使用`amount`而非`quantity`

#### 字段映射规则
| 标准字段 | Deribit字段 | 说明 |
|---------|-------------|------|
| symbol_name | 从channel提取 | 从WebSocket频道解析 |
| trade_id | `trade_id` | 交易ID |
| price | `price` | 成交价格 |
| quantity | `amount` | 成交数量 |
| timestamp | `timestamp` | 成交时间（毫秒） |
| is_buyer_maker | `direction` | 需要转换（sell=maker买入） |

#### 实现示例
```python
class DeribitAdapter(ExchangeAdapter):
    async def normalize_trade(self, raw_data: Dict[str, Any], channel: str) -> Optional[NormalizedTrade]:
        try:
            # 从WebSocket频道提取交易对
            symbol = channel.split(".")[1]
            
            price = self._safe_decimal(raw_data["price"])
            quantity = self._safe_decimal(raw_data["amount"])  # Deribit使用amount
            
            return NormalizedTrade(
                exchange_name="deribit",
                symbol_name=symbol,
                trade_id=str(raw_data["trade_id"]),
                price=price,
                quantity=quantity,
                quote_quantity=price * quantity,
                timestamp=self._safe_timestamp(raw_data["timestamp"]),
                is_buyer_maker=raw_data["direction"] == "sell"  # Deribit转换规则
            )
        except Exception as e:
            self.logger.error("标准化Deribit交易数据失败", error=str(e))
            return None
```

## 数据验证和质量控制

### 1. 必填字段验证

```python
def validate_required_fields(self, data: Dict[str, Any], required_fields: List[str]) -> bool:
    """验证必填字段"""
    for field in required_fields:
        if field not in data or data[field] is None:
            self.logger.error(f"缺少必要字段: {field}")
            return False
    return True
```

### 2. 数据合理性检查

```python
def validate_orderbook(self, orderbook: NormalizedOrderBook) -> bool:
    """验证订单簿数据合理性"""
    if not orderbook.bids or not orderbook.asks:
        return False
    
    # 验证价格合理性：最佳卖价应该高于最佳买价
    best_bid = orderbook.bids[0].price
    best_ask = orderbook.asks[0].price
    
    if best_ask <= best_bid:
        self.logger.warning(f"订单簿价格异常: bid={best_bid}, ask={best_ask}")
        return False
    
    return True
```

### 3. 价格精度控制

```python
def normalize_price_precision(self, price: Decimal, symbol: str) -> Decimal:
    """标准化价格精度"""
    # 根据交易对设置合适的精度
    precision_map = {
        "BTC": 2,    # BTC相关保留2位小数
        "ETH": 3,    # ETH相关保留3位小数
        "USDT": 4    # 小币种保留4位小数
    }
    
    for token, precision in precision_map.items():
        if token in symbol.upper():
            return price.quantize(Decimal(f'0.{"0" * precision}'))
    
    return price.quantize(Decimal('0.00000001'))  # 默认8位精度
```

## 性能优化策略

### 1. 批量处理

```python
async def normalize_batch_trades(self, raw_trades: List[Dict]) -> List[NormalizedTrade]:
    """批量标准化交易数据"""
    tasks = []
    for trade in raw_trades:
        task = self.normalize_trade(trade)
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 过滤掉异常结果
    normalized_trades = []
    for result in results:
        if isinstance(result, NormalizedTrade):
            normalized_trades.append(result)
        elif isinstance(result, Exception):
            self.logger.error(f"批量处理异常: {result}")
    
    return normalized_trades
```

### 2. 内存优化

```python
class DataNormalizer:
    def __init__(self):
        # 使用对象池减少内存分配
        self._decimal_cache = {}
        self._datetime_cache = {}
    
    def _cached_decimal(self, value: str) -> Decimal:
        """缓存Decimal对象"""
        if value not in self._decimal_cache:
            self._decimal_cache[value] = Decimal(value)
        return self._decimal_cache[value]
```

### 3. 异步处理

```python
async def process_market_data_stream(self, exchange: str, data_stream):
    """异步处理市场数据流"""
    async for raw_data in data_stream:
        try:
            # 异步标准化
            normalized = await self.normalize_data(exchange, raw_data)
            
            if normalized:
                # 异步发布到NATS
                await self.publish_normalized_data(normalized)
                
        except Exception as e:
            self.logger.error(f"处理数据流异常: {e}")
```

## 错误处理和监控

### 1. 异常分类处理

```python
class DataNormalizationError(Exception):
    """数据标准化异常基类"""
    pass

class MissingFieldError(DataNormalizationError):
    """缺少必填字段异常"""
    pass

class InvalidDataFormatError(DataNormalizationError):
    """数据格式无效异常"""
    pass

class PrecisionError(DataNormalizationError):
    """精度转换异常"""
    pass
```

### 2. 监控指标

```python
class NormalizationMetrics:
    """标准化监控指标"""
    def __init__(self):
        self.total_processed = 0
        self.successful_normalized = 0
        self.failed_normalized = 0
        self.processing_time_ms = []
        self.error_counts_by_type = defaultdict(int)
    
    def record_success(self, processing_time_ms: float):
        """记录成功处理"""
        self.total_processed += 1
        self.successful_normalized += 1
        self.processing_time_ms.append(processing_time_ms)
    
    def record_failure(self, error_type: str):
        """记录处理失败"""
        self.total_processed += 1
        self.failed_normalized += 1
        self.error_counts_by_type[error_type] += 1
    
    def get_success_rate(self) -> float:
        """获取成功率"""
        if self.total_processed == 0:
            return 0.0
        return self.successful_normalized / self.total_processed
```

## 配置管理

### 1. 交易所配置

```yaml
# config/exchanges/binance_spot.yaml
exchange: "binance"
market_type: "spot"
enabled: true
base_url: "https://api.binance.com"
ws_url: "wss://stream.binance.com:9443"
data_types:
  - "trade"
  - "orderbook"
  - "ticker"
symbols:
  - "BTC/USDT"
  - "ETH/USDT"
normalization:
  price_precision: 8
  quantity_precision: 8
  validate_orderbook: true
  max_price_deviation: 0.1  # 10%价格偏差阈值
```

### 2. 标准化配置

```yaml
# config/normalization.yaml
global:
  default_precision: 8
  max_processing_time_ms: 100
  enable_validation: true
  enable_caching: true

exchanges:
  binance:
    timestamp_unit: "milliseconds"
    symbol_format: "BTCUSDT"
    maker_field: "m"
  
  okx:
    timestamp_unit: "milliseconds"
    symbol_format: "BTC-USDT"
    price_field: "px"
    quantity_field: "sz"
  
  deribit:
    timestamp_unit: "milliseconds"
    symbol_format: "BTC-PERPETUAL"
    quantity_field: "amount"
    direction_field: "direction"
```

## 测试和验证

### 1. 单元测试

```python
class TestDataNormalization:
    def test_binance_trade_normalization(self):
        """测试Binance交易数据标准化"""
        raw_data = {
            "s": "BTCUSDT",
            "t": 12345,
            "p": "50000.00",
            "q": "0.001",
            "T": 1640995200000,
            "m": False
        }
        
        adapter = BinanceAdapter()
        normalized = adapter.normalize_trade(raw_data)
        
        assert normalized.exchange_name == "binance"
        assert normalized.symbol_name == "BTCUSDT"
        assert normalized.price == Decimal("50000.00")
        assert normalized.quantity == Decimal("0.001")
        assert normalized.is_buyer_maker == False
```

### 2. 集成测试

```python
async def test_real_data_normalization():
    """使用真实数据测试标准化"""
    # 获取真实Binance数据
    real_data = await get_real_binance_trade_data()
    
    # 标准化处理
    normalizer = DataNormalizer()
    normalized = await normalizer.normalize_trade("binance", real_data)
    
    # 验证结果
    assert normalized is not None
    assert normalized.price > 0
    assert normalized.quantity > 0
    assert isinstance(normalized.timestamp, datetime)
```

### 3. 性能测试

```python
async def test_normalization_performance():
    """测试标准化性能"""
    # 生成1000条测试数据
    test_data = generate_test_trades(1000)
    
    start_time = time.time()
    
    # 批量标准化
    normalizer = DataNormalizer()
    results = await normalizer.normalize_batch_trades(test_data)
    
    processing_time = time.time() - start_time
    
    # 验证性能要求
    assert processing_time < 1.0  # 1000条数据应在1秒内完成
    assert len(results) == 1000   # 所有数据都应成功处理
```

## 最佳实践

### 1. 代码规范

- 使用类型注解确保代码可读性
- 异常处理要具体和有意义
- 日志记录要包含足够的上下文信息
- 使用配置文件而非硬编码

### 2. 数据质量

- 始终验证输入数据的完整性
- 对异常数据进行标记而非丢弃
- 保留原始数据用于调试和审计
- 定期检查数据质量指标

### 3. 性能优化

- 使用批量处理减少网络开销
- 合理使用缓存避免重复计算
- 异步处理提高并发性能
- 监控内存使用避免泄漏

### 4. 可维护性

- 模块化设计便于扩展新交易所
- 统一的接口规范
- 完善的文档和注释
- 自动化测试覆盖

## 扩展新交易所

### 1. 实现步骤

1. **创建适配器类**：继承`ExchangeAdapter`基类
2. **实现标准化方法**：根据交易所API格式实现数据转换
3. **添加配置文件**：定义交易所特定配置
4. **编写测试用例**：确保标准化正确性
5. **更新文档**：记录新交易所的特殊处理

### 2. 示例：添加Bybit支持

```python
class BybitAdapter(ExchangeAdapter):
    """Bybit交易所适配器"""
    
    async def normalize_trade(self, raw_data: Dict[str, Any]) -> Optional[NormalizedTrade]:
        try:
            # Bybit特定字段映射
            return NormalizedTrade(
                exchange_name="bybit",
                symbol_name=raw_data["symbol"],
                trade_id=str(raw_data["trade_id"]),
                price=self._safe_decimal(raw_data["price"]),
                quantity=self._safe_decimal(raw_data["size"]),  # Bybit使用size
                quote_quantity=self._safe_decimal(raw_data["price"]) * self._safe_decimal(raw_data["size"]),
                timestamp=self._safe_timestamp(raw_data["timestamp"]),
                is_buyer_maker=raw_data["side"] == "Sell"  # Bybit特殊逻辑
            )
        except Exception as e:
            self.logger.error("标准化Bybit交易数据失败", error=str(e))
            return None
```

## 总结

MarketPrism的数据标准化系统通过统一的数据模型、灵活的适配器架构和完善的质量控制机制，实现了多交易所数据的高效、准确标准化处理。该系统具有以下特点：

1. **高度可扩展**：易于添加新交易所支持
2. **类型安全**：使用强类型确保数据精度
3. **性能优化**：支持批量和异步处理
4. **质量保证**：完善的验证和监控机制
5. **易于维护**：模块化设计和清晰的接口

这套标准化系统为MarketPrism的数据处理、存储和分析提供了坚实的基础，确保了来自不同交易所的数据能够以统一、可靠的方式进行处理和使用。 