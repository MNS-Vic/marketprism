# Python收集器企业级升级开发计划

## 🎯 目标：让Python-Collector达到Go-Collector的企业级水平

### 📊 当前差距评估
- **go-collector**: 企业级功能完备 (95%)
- **python-collector**: 基础功能优秀 (60%)
- **目标**: 提升到企业级功能完备 (95%)

---

## 📅 分阶段开发计划

### 🔥 **第一阶段：监控与可观测性 (优先级：关键)**
**时间估计**: 3-5天
**影响度**: 生产部署必需

#### 1.1 Prometheus监控系统
```python
# 新增模块：src/marketprism_collector/monitoring/
├── metrics.py          # Prometheus指标定义
├── health.py           # 健康检查端点
└── middleware.py       # 监控中间件
```

**核心指标实现**：
```python
from prometheus_client import Counter, Histogram, Gauge, Info

class CollectorMetrics:
    def __init__(self):
        # 消息计数器
        self.messages_total = Counter(
            'marketprism_messages_total',
            'Total messages processed',
            ['exchange', 'data_type', 'status']
        )
        
        # 错误计数器
        self.errors_total = Counter(
            'marketprism_errors_total',
            'Total errors',
            ['exchange', 'error_type']
        )
        
        # 处理延迟
        self.processing_latency = Histogram(
            'marketprism_processing_seconds',
            'Message processing latency',
            ['exchange', 'data_type']
        )
        
        # 连接状态
        self.connection_status = Gauge(
            'marketprism_connection_status',
            'Connection status',
            ['exchange']
        )
```

#### 1.2 HTTP服务器扩展
```python
# 扩展现有的HTTP服务器
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

async def metrics_handler(request):
    return web.Response(
        text=generate_latest(),
        content_type=CONTENT_TYPE_LATEST
    )

async def health_handler(request):
    # 检查所有交易所连接状态
    health_status = await check_all_connections()
    return web.json_response(health_status)
```

### 🚨 **第二阶段：高级数据类型支持 (优先级：高)**
**时间估计**: 5-7天
**影响度**: 功能完整性关键

#### 2.1 扩展数据类型定义
```python
# 扩展 src/marketprism_collector/types.py

class NormalizedFundingRate(BaseModel):
    """资金费率数据"""
    exchange_name: str
    symbol_name: str
    funding_rate: Decimal
    estimated_rate: Optional[Decimal] = None
    next_funding_time: datetime
    mark_price: Decimal
    index_price: Decimal
    premium_index: Decimal
    timestamp: datetime

class NormalizedOpenInterest(BaseModel):
    """持仓量数据"""
    exchange_name: str
    symbol_name: str
    open_interest: Decimal
    open_interest_value: Decimal  # 持仓量价值
    timestamp: datetime

class NormalizedLiquidation(BaseModel):
    """强平数据"""
    exchange_name: str
    symbol_name: str
    liquidation_id: Optional[str] = None
    side: str  # 'buy' or 'sell'
    price: Decimal
    quantity: Decimal
    leverage: Optional[Decimal] = None
    instrument_type: str  # 'futures', 'swap', 'spot'
    timestamp: datetime
```

#### 2.2 交易所适配器扩展
**为每个交易所添加新数据类型支持**：

```python
# 扩展 exchanges/binance.py
class BinanceAdapter(ExchangeAdapter):
    
    async def subscribe_funding_rate_stream(self):
        """订阅资金费率流"""
        # 期货API WebSocket连接
        futures_streams = []
        for symbol in self.config.symbols:
            if hasattr(self.config, 'futures_symbols') and symbol in self.config.futures_symbols:
                futures_streams.append(f"{symbol.lower()}@markPrice")
        
        # 建立期货WebSocket连接
        if futures_streams:
            await self._connect_futures_ws(futures_streams)
    
    async def collect_funding_rate_data(self):
        """定时收集资金费率"""
        for symbol in self.config.futures_symbols:
            url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    data = await response.json()
                    funding_rate = await self.normalize_funding_rate(data)
                    if funding_rate:
                        await self._emit_data(DataType.FUNDING_RATE, funding_rate)
    
    async def normalize_funding_rate(self, raw_data: Dict[str, Any]) -> Optional[NormalizedFundingRate]:
        """标准化资金费率数据"""
        try:
            return NormalizedFundingRate(
                exchange_name="binance",
                symbol_name=self.symbol_map.get(raw_data["symbol"], raw_data["symbol"]),
                funding_rate=self._safe_decimal(raw_data["lastFundingRate"]),
                mark_price=self._safe_decimal(raw_data["markPrice"]),
                index_price=self._safe_decimal(raw_data["indexPrice"]),
                premium_index=self._safe_decimal(raw_data["markPrice"]) - self._safe_decimal(raw_data["indexPrice"]),
                next_funding_time=self._safe_timestamp(int(raw_data["nextFundingTime"])),
                timestamp=datetime.utcnow()
            )
        except Exception as e:
            self.logger.error("资金费率标准化失败", error=str(e))
            return None
```

### 🔄 **第三阶段：任务调度系统 (优先级：高)**
**时间估计**: 3-4天
**影响度**: 定时数据收集必需

#### 3.1 集成APScheduler
```python
# 新增模块：src/marketprism_collector/scheduler/
├── scheduler.py        # 任务调度器
├── jobs.py            # 定时任务定义
└── tasks.py           # 任务执行逻辑

# scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

class CollectorScheduler:
    def __init__(self, collector):
        self.collector = collector
        self.scheduler = AsyncIOScheduler()
        
    async def start(self):
        """启动调度器"""
        # 每小时收集资金费率
        self.scheduler.add_job(
            self.collect_funding_rates,
            IntervalTrigger(hours=1),
            id='funding_rates'
        )
        
        # 每15分钟收集持仓量数据
        self.scheduler.add_job(
            self.collect_open_interest,
            IntervalTrigger(minutes=15),
            id='open_interest'
        )
        
        self.scheduler.start()
    
    async def collect_funding_rates(self):
        """定时收集资金费率"""
        for adapter in self.collector.exchange_adapters.values():
            if hasattr(adapter, 'collect_funding_rate_data'):
                await adapter.collect_funding_rate_data()
```

#### 3.2 配置扩展
```yaml
# config/collector.yaml 扩展
collector:
  use_real_exchanges: true
  enable_scheduler: true    # 启用任务调度
  
# 定时任务配置
scheduler:
  jobs:
    funding_rate:
      enabled: true
      interval: 1h         # 每小时
    open_interest:
      enabled: true
      interval: 15m        # 每15分钟
    liquidation_monitor:
      enabled: true
      interval: 1m         # 每分钟检查
```

### 💼 **第四阶段：企业级可靠性 (优先级：中)**
**时间估计**: 4-5天
**影响度**: 生产稳定性

#### 4.1 高级错误处理
```python
# 新增模块：src/marketprism_collector/reliability/
├── error_handler.py    # 错误分类和处理
├── circuit_breaker.py  # 熔断器
├── rate_limiter.py     # 限流器
└── retry.py           # 智能重试

class ErrorClassifier:
    """错误分类器"""
    
    NETWORK_ERRORS = (aiohttp.ClientError, websockets.ConnectionClosed)
    API_ERRORS = (aiohttp.ClientResponseError,)
    DATA_ERRORS = (json.JSONDecodeError, ValidationError)
    
    @classmethod
    def classify_error(cls, error: Exception) -> str:
        if isinstance(error, cls.NETWORK_ERRORS):
            return "network"
        elif isinstance(error, cls.API_ERRORS):
            return "api"
        elif isinstance(error, cls.DATA_ERRORS):
            return "data"
        else:
            return "unknown"

class RateLimiter:
    """API限流器"""
    
    def __init__(self, max_requests: int, time_window: int):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []
    
    async def acquire(self):
        """获取请求许可"""
        now = time.time()
        # 清理过期请求
        self.requests = [req_time for req_time in self.requests 
                        if now - req_time < self.time_window]
        
        if len(self.requests) >= self.max_requests:
            # 计算需要等待的时间
            oldest_request = min(self.requests)
            wait_time = self.time_window - (now - oldest_request)
            await asyncio.sleep(wait_time)
        
        self.requests.append(now)
```

#### 4.2 连接池管理
```python
class ConnectionPool:
    """WebSocket连接池"""
    
    def __init__(self, max_connections: int = 10):
        self.max_connections = max_connections
        self.active_connections = {}
        self.connection_stats = defaultdict(dict)
    
    async def get_connection(self, exchange: str, url: str):
        """获取连接"""
        key = f"{exchange}:{url}"
        
        if key in self.active_connections:
            conn = self.active_connections[key]
            if conn.is_healthy():
                return conn
            else:
                await self.remove_connection(key)
        
        # 创建新连接
        conn = await self.create_connection(url)
        self.active_connections[key] = conn
        return conn
```

### 🎛️ **第五阶段：高级配置管理 (优先级：中)**
**时间估计**: 2-3天
**影响度**: 配置灵活性

#### 5.1 多层配置系统
```python
# 扩展配置系统支持多API端点
class ExchangeConfig(BaseModel):
    exchange: Exchange
    market_type: MarketType
    enabled: bool = True
    
    # 基础配置
    base_url: str
    ws_url: str
    
    # 多端点支持
    futures_url: Optional[str] = None      # 期货API
    futures_ws_url: Optional[str] = None   # 期货WebSocket
    
    # 功能开关
    enable_funding_rate: bool = False
    enable_open_interest: bool = False
    enable_liquidation: bool = False
    
    # 交易对配置
    symbols: List[str]
    futures_symbols: Optional[List[str]] = None
    
    # 限流配置
    max_requests_per_minute: int = 1200
    api_rate_limit: int = 100
    
    # 数据类型配置
    data_types: List[DataType]
```

### 🏭 **第六阶段：生产环境优化 (优先级：低)**
**时间估计**: 3-4天
**影响度**: 性能和稳定性

#### 6.1 批量数据处理
```python
class BatchProcessor:
    """批量数据处理器"""
    
    def __init__(self, batch_size: int = 100, flush_interval: float = 1.0):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.buffer = []
        self.last_flush = time.time()
    
    async def add_message(self, message):
        """添加消息到缓冲区"""
        self.buffer.append(message)
        
        # 检查是否需要刷新
        if (len(self.buffer) >= self.batch_size or 
            time.time() - self.last_flush >= self.flush_interval):
            await self.flush()
    
    async def flush(self):
        """刷新缓冲区"""
        if self.buffer:
            await self.process_batch(self.buffer)
            self.buffer.clear()
            self.last_flush = time.time()
```

#### 6.2 智能重连机制
```python
class SmartReconnect:
    """智能重连机制"""
    
    def __init__(self):
        self.backoff_base = 1  # 基础退避时间
        self.backoff_max = 60  # 最大退避时间
        self.failure_count = 0
        
    async def reconnect_with_backoff(self, connect_func):
        """使用指数退避重连"""
        while True:
            try:
                await connect_func()
                self.failure_count = 0  # 重置失败计数
                break
            except Exception as e:
                self.failure_count += 1
                wait_time = min(
                    self.backoff_base * (2 ** self.failure_count),
                    self.backoff_max
                )
                await asyncio.sleep(wait_time)
```

---

## 📊 实施优先级矩阵

| 阶段 | 功能 | 优先级 | 实现难度 | 影响度 | 预估时间 |
|------|------|--------|----------|--------|----------|
| 1 | 监控系统 | 🔥 关键 | 中等 | 高 | 3-5天 |
| 2 | 高级数据类型 | 🔥 高 | 高 | 高 | 5-7天 |
| 3 | 任务调度 | 🟡 高 | 中等 | 中 | 3-4天 |
| 4 | 企业可靠性 | 🟡 中等 | 高 | 中 | 4-5天 |
| 5 | 配置管理 | 🟢 中等 | 低 | 低 | 2-3天 |
| 6 | 性能优化 | 🟢 低 | 中等 | 中 | 3-4天 |

**总预估时间**: 20-28天

---

## 🎯 实施建议

### 立即开始 (第1-2阶段)
1. **监控系统**: 生产部署的基础要求
2. **资金费率数据**: 最重要的缺失功能

### 后续实施 (第3-4阶段)
3. **任务调度**: 提升数据收集完整性
4. **企业级可靠性**: 提升生产稳定性

### 长期优化 (第5-6阶段)
5. **配置管理**: 提升系统灵活性
6. **性能优化**: 达到企业级性能标准

---

## 📈 预期成果

完成所有阶段后，python-collector将实现：

- **功能完整性**: 95% (与go-collector相当)
- **企业级监控**: Prometheus + 健康检查
- **高级数据类型**: 资金费率、持仓量、强平数据
- **生产级可靠性**: 熔断、限流、智能重试
- **灵活配置**: 多端点、功能开关
- **高性能**: 批量处理、连接池管理

这将使python-collector从"基础功能优秀"升级到"企业级功能完备"！ 