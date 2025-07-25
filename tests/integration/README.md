# MarketPrism 集成测试

本目录包含 MarketPrism 项目的集成测试，验证不同组件之间的协同工作。

## 集成测试概述

集成测试验证系统组件间的交互，与单元测试相比，集成测试关注的是组件之间的接口和数据流。

## 目录结构

```
integration/
├── services/                   # 服务集成测试
│   └── test_normalizer_integration.py  # 数据标准化器集成测试
├── api/                        # API集成测试
├── conftest.py                 # 集成测试共享fixtures
└── README.md                   # 本文档
```

## 集成测试原则

1. **测试组件交互**：重点关注组件之间的接口和数据流
2. **接近真实环境**：尽量在接近真实的环境中进行测试
3. **关注结果**：验证最终结果而非实现细节
4. **测试主要流程**：确保核心功能和业务流程正常工作

## 测试环境设置

集成测试需要一个隔离的测试环境，配置方式如下：

1. **测试数据库**：使用独立的`marketprism_test`数据库
2. **测试消息流**：使用独立的`TEST_MARKET_DATA`等测试流
3. **配置隔离**：通过环境变量传入测试专用配置

## 测试类型

### 服务间集成测试

验证多个服务协同工作：

```python
@pytest.mark.integration
def test_data_collection_and_storage():
    """测试数据采集和存储的完整流程"""
    # 设置测试环境
    collector = DataCollector(config=test_config)
    normalizer = DataNormalizer(config=test_config)
    storage = StorageService(config=test_config)
    
    # 执行测试流程
    raw_data = collector.collect_from_exchange("binance", "BTC-USDT")
    normalized_data = normalizer.process(raw_data)
    result = storage.store(normalized_data)
    
    # 验证结果
    assert result.success is True
    assert result.records_count > 0
```

### API集成测试

验证API接口的完整功能：

```python
@pytest.mark.integration
def test_market_data_api():
    """测试市场数据API"""
    # 设置API客户端
    client = APIClient(base_url="http://localhost:8000")
    
    # 执行测试
    response = client.get("/api/v1/market/trades", 
                         params={"symbol": "BTC-USDT", "limit": 10})
    
    # 验证结果
    assert response.status_code == 200
    assert len(response.json()["data"]) <= 10
    assert "BTC-USDT" in response.json()["data"][0]["symbol"]
```

## 数据管理

集成测试需要特别注意数据管理：

1. **测试数据准备**：使用 fixture 创建测试所需的初始数据
2. **数据清理**：测试后清理测试数据，避免影响后续测试
3. **数据隔离**：每个测试应使用独立的数据集

```python
@pytest.fixture
def prepared_database():
    """准备测试数据库环境"""
    # 创建表结构
    db = get_test_db_connection()
    db.execute("CREATE TABLE IF NOT EXISTS test_trades (...)")
    
    # 插入测试数据
    test_data = generate_test_trades(10)
    db.insert("test_trades", test_data)
    
    yield db
    
    # 清理数据
    db.execute("DROP TABLE test_trades")
```

## 运行集成测试

### 前置条件

集成测试需要有可用的 NATS 和 ClickHouse 服务。测试框架会通过 Docker Compose 自动启动这些服务。

### 要求

1. 必须安装 Docker 和 Docker Compose
2. Python 依赖项: pytest, pytest-asyncio, docker-py

### 运行方式

```bash
# 运行所有集成测试
pytest --run-integration tests/integration/

# 运行特定集成测试
pytest --run-integration tests/integration/services/test_normalizer_integration.py
```

## DataNormalizer集成测试说明

`test_normalizer_integration.py` 文件包含以下集成测试：

1. **NATS到DataNormalizer测试**：验证从NATS接收消息并通过DataNormalizer处理
2. **DataNormalizer到ClickHouse测试**：验证DataNormalizer处理的数据可正确写入ClickHouse
3. **端到端流程测试**：验证完整的数据流：NATS → DataNormalizer → ClickHouse

### 测试流程

1. 测试启动前自动准备环境（ClickHouse表和NATS流）
2. 执行测试场景，模拟实际数据流
3. 验证数据在各环节的处理结果
4. 测试结束后自动清理测试数据

### 注意事项

- 集成测试使用独立的测试数据库和消息流，不会影响生产环境
- 测试可能需要较长时间执行，因为涉及实际网络通信和数据存储
- 如果本地没有Docker环境，可以设置环境变量指向远程服务：
  ```bash
  export TEST_NATS_URL=nats://your-nats-server:4222
  export TEST_CH_HOST=your-clickhouse-server
  ```