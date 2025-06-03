# MarketPrism 测试框架

## 简介

MarketPrism测试框架提供了全面的测试工具和方法，用于验证系统的正确性、可靠性和性能。本框架支持单元测试、集成测试、性能测试和负载测试，确保系统各组件高质量运行。

## 快速开始

### 安装测试依赖

```bash
pip install -r tests/requirements_test.txt
```

### 运行测试

```bash
# 运行所有测试
python tests/run_tests_可复用.py --all

# 运行单元测试
python tests/run_tests_可复用.py --unit

# 运行集成测试
python tests/run_tests_可复用.py --integration

# 运行性能测试
python tests/run_tests_可复用.py --performance

# 运行负载测试
python tests/run_tests_可复用.py --load
```

## 测试目录结构

```
tests/
  ├── unit/                  # 单元测试
  │   ├── models/            # 数据模型测试
  │   ├── services/          # 服务组件测试
  │   │   └── go-collector/  # Go采集器测试
  │   ├── config/            # 配置测试
  │   ├── storage/           # 存储测试
  │   └── api/               # API测试
  │
  ├── integration/           # 集成测试
  │   ├── api/               # API集成测试
  │   └── services/          # 服务集成测试
  │
  ├── performance/           # 性能测试
  ├── load_testing/          # 负载测试
  ├── fixtures/              # 测试固定数据
  ├── utils/                 # 测试工具
  ├── reports/               # 测试报告目录
  |
  ├── conftest.py            # 测试全局配置
  ├── pytest.ini             # pytest配置文件
  └── requirements_test.txt  # 测试依赖列表
```

## 已实现的测试

### 单元测试

- **数据模型**: `test_market_data_models_可复用.py` - 测试市场数据模型（交易、订单簿等）
- **存储**: `test_clickhouse_storage_可复用.py` - 测试ClickHouse存储接口
- **数据归档**: `test_data_archiver_可复用.py` - 测试数据归档服务
- **NATS服务**: `test_nats_service_可复用.py` - 测试NATS消息服务
- **配置模块**: 
  - `test_exchange_config_可复用.py` - 测试交易所配置
  - `test_monitoring_config_可复用.py` - 测试监控配置
  - `test_clickhouse_init_可复用.py` - 测试ClickHouse初始化
- **采集器**: `test_go_collector_可复用.py` - 测试Go采集器
- **API**: `test_api_routes_可复用.py` - 测试API路由和处理函数

### 集成测试

- **标准化服务**: `test_normalizer_integration_可复用.py` - 测试数据标准化服务集成
- **市场API**: `test_market_data_api_可复用.py` - 测试市场数据API集成

### 性能测试

- **NATS性能**: `test_nats_performance_可复用.py` - 测试NATS消息服务性能

## 运行特定测试

### 运行单元测试

```bash
# 运行所有单元测试
python tests/run_tests_可复用.py --unit

# 运行特定模块测试
python tests/run_tests_可复用.py --unit --module models
python tests/run_tests_可复用.py --unit --module services
python tests/run_tests_可复用.py --unit --module storage
python tests/run_tests_可复用.py --unit --module config
python tests/run_tests_可复用.py --unit --module api

# 运行特定文件
python -m pytest tests/unit/models/test_market_data_models_可复用.py
```

### 运行集成测试

```bash
# 运行所有集成测试
python tests/run_tests_可复用.py --integration

# 运行特定的集成测试
python tests/run_tests_可复用.py --integration --module services
python tests/run_tests_可复用.py --integration --module api

# 运行特定文件
python -m pytest tests/integration/services/test_normalizer_integration_可复用.py
```

### 运行性能测试

```bash
# 运行所有性能测试
python tests/run_tests_可复用.py --performance

# 运行特定的性能测试
python -m pytest tests/performance/test_nats_performance_可复用.py
```

## 测试工具

### 数据工厂

`tests/utils/data_factory_可复用.py`提供生成测试数据的工具：

```python
from tests.utils.data_factory_可复用 import DataFactory

# 创建交易数据
trade = DataFactory.generate_trade_data(
    exchange="binance", 
    symbol="BTC/USDT"
)

# 创建订单簿数据
orderbook = DataFactory.generate_orderbook_data(
    exchange="binance",
    symbol="BTC/USDT",
    depth=10
)

# 创建行情数据
ticker = DataFactory.generate_ticker_data(
    exchange="binance",
    symbol="BTC/USDT"
)

# 创建交易所配置
exchange_config = DataFactory.generate_exchange_config(
    exchange_id="binance"
)

# 创建NATS消息
nats_msg = DataFactory.generate_nats_message(
    subject="market.trade.binance.BTCUSDT",
    data=trade
)
```

### 模拟工厂

`tests/utils/mock_factory_可复用.py`提供创建模拟对象的工具：

```python
from tests.utils.mock_factory_可复用 import MockFactory

# 创建NATS客户端模拟对象
nats_mock = MockFactory.create_mock_nats_client()

# 创建ClickHouse客户端模拟对象
clickhouse_mock = MockFactory.create_mock_clickhouse_client()

# 创建HTTP客户端模拟对象
http_mock = MockFactory.create_mock_http_client()

# 创建配置模拟对象
config_mock = MockFactory.create_mock_config(config_dict={})
```

### 测试助手

`tests/utils/test_helpers_可复用.py`提供常用的测试辅助功能：

```python
from tests.utils.test_helpers_可复用 import TestHelpers

# 获取项目根目录
root_dir = TestHelpers.get_project_root()

# 获取测试文件路径
file_path = TestHelpers.get_test_file_path("data.json")

# 加载测试数据
test_data = TestHelpers.load_test_data("sample_data.json")

# 保存测试数据
path = TestHelpers.save_test_data(data, "output.json")

# 创建临时文件
with TestHelpers.create_temp_file() as tmp_file:
    # 使用临时文件
    pass

# 创建临时目录
with TestHelpers.create_temp_dir() as tmp_dir:
    # 使用临时目录
    pass

# 等待条件满足
success = TestHelpers.wait_for(
    condition_func=lambda: check_something(), 
    timeout=10.0, 
    interval=0.5
)

# 异步等待
success = await TestHelpers.async_wait_for(
    condition_func=async_check_func, 
    timeout=10.0, 
    interval=0.5
)

# 查找空闲端口
port = TestHelpers.find_free_port()

# 设置测试环境变量
orig_vars = TestHelpers.setup_test_env({"TEST_VAR": "value"})

# 恢复环境变量
TestHelpers.restore_env(orig_vars)

# 比较对象
equal, differences = TestHelpers.compare_objects(
    obj1, obj2, 
    exclude_keys=["timestamp"], 
    float_tolerance=0.001
)
```

## 测试报告

使用`--html`和`--cov`参数生成测试报告：

```bash
# 生成HTML报告和覆盖率报告
python tests/run_tests_可复用.py --unit --html --cov
```

测试运行后会生成以下报告：

- HTML报告：`tests/reports/report.html`
- 覆盖率报告：`tests/reports/coverage/index.html`
- 最近运行结果：`tests/reports/last_run.json`

## 测试配置

测试配置位于`tests/pytest.ini`文件中，主要配置项包括：

- 测试标记定义（unit、integration、performance、load）
- 测试路径和文件模式
- 异步测试配置
- 报告配置
- 并行执行选项

## 编写新测试

### 创建单元测试

示例：

```python
import pytest
from tests.utils.data_factory_可复用 import DataFactory

class TestNewFeature:
    """新功能测试类"""
    
    @pytest.fixture
    def setup_test(self):
        """设置测试环境"""
        # 创建测试资源
        yield resource
        # 清理资源
    
    def test_specific_functionality(self, setup_test):
        """测试特定功能"""
        # 准备测试数据
        test_data = DataFactory.generate_trade_data()
        
        # 执行被测功能
        result = some_function(test_data)
        
        # 验证结果
        assert result is not None
        assert result.status == "success"
        assert result.data["price"] == test_data["price"]
        
    def test_error_handling(self, setup_test):
        """测试错误处理"""
        # 准备异常测试数据
        invalid_data = {"invalid": "data"}
        
        # 验证异常处理
        with pytest.raises(ValueError) as exc_info:
            some_function(invalid_data)
            
        assert "Invalid data format" in str(exc_info.value)
```

## 其他资源

- **测试计划**：`tests/test_plan.md`
- **测试开发计划**：`tests/test_development_plan.md`
- **测试框架详细说明**：`tests/README_测试框架说明.md`
- **测试依赖**：`tests/requirements_test.txt`

## 测试执行环境

- **本地环境**：适用于开发阶段，运行单元测试和基本集成测试
- **CI环境**：GitHub Actions中的自动化测试
- **专用测试环境**：用于性能测试和负载测试的专用服务器

## 最佳实践

1. **使用数据工厂**：始终使用测试数据工厂生成一致的测试数据
2. **隔离外部依赖**：使用模拟对象替代外部服务和依赖
3. **独立测试**：每个测试应独立运行，不依赖其他测试的状态
4. **测试边界条件**：添加错误情况和边界条件的测试用例
5. **定期运行测试**：集成到工作流程中，定期运行完整测试套件