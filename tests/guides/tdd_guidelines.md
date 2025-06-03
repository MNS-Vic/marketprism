# MarketPrism 测试驱动开发指南

## 测试驱动开发 (TDD) 简介

测试驱动开发是一种软件开发方法，它遵循以下循环：

1. **红色**：先编写一个失败的测试
2. **绿色**：实现最小代码使测试通过
3. **重构**：优化代码，保持测试通过

## MarketPrism项目中的TDD实践指南

### 1. 测试分类与组织

根据功能模块和测试类型组织测试：

- **单元测试** (`tests/unit/`)：测试独立组件
- **集成测试** (`tests/integration/`)：测试组件间交互
- **性能测试** (`tests/performance/`)：测试性能指标
- **负载测试** (`tests/load_testing/`)：测试高负载情况下的系统行为

### 2. 命名约定

- 测试文件：`test_<被测模块>.py`
- 测试类：`Test<被测组件名>`
- 测试方法：`test_<功能描述>_<预期结果>`

### 3. TDD工作流程

#### 开发新功能时：

1. **创建测试文件**：在适当的目录下创建测试文件
2. **编写失败测试**：描述期望的行为
3. **实现功能**：编写最小代码使测试通过
4. **运行测试**：确认测试通过
5. **重构代码**：提高代码质量
6. **重复过程**：增量开发其他功能

#### 修复Bug时：

1. **复现Bug**：编写一个能复现Bug的测试
2. **确认失败**：运行测试，确保它失败（红色）
3. **修复Bug**：修改代码修复问题
4. **验证修复**：运行测试，确保通过（绿色）

### 4. 测试用例设计指南

- **边界值测试**：测试极限条件
- **错误情况测试**：测试错误输入或异常情况
- **正向测试**：测试正常功能流程
- **性能临界点**：关注系统性能临界点

### 5. 测试编写规范

每个测试应遵循 **AAA模式**：

- **Arrange**（准备）：设置测试环境和数据
- **Act**（执行）：调用被测代码
- **Assert**（断言）：验证执行结果

示例：
```python
def test_normalize_trade_valid(self):
    # Arrange
    trade_data = {
        "price": "1000.5",
        "amount": "2.5",
        "exchange": "binance"
    }
    normalizer = DataNormalizer()
    
    # Act
    result = normalizer.normalize_trade(trade_data)
    
    # Assert
    assert result["price"] == 1000.5  # 字符串转浮点数
    assert result["amount"] == 2.5
    assert result["exchange"] == "binance"  # 保留原始字段
```

### 6. 测试夹具(Fixtures)使用指南

- 使用`pytest`的`fixtures`管理测试状态和依赖
- 将通用的测试夹具放在`tests/fixtures/`目录
- 在`conftest.py`中定义广泛使用的夹具

### 7. 模拟对象(Mocks)使用指南

- 使用`unittest.mock`或`pytest-mock`进行依赖隔离
- 确保模拟对象行为接近真实对象
- 避免过度模拟

### 8. 持续集成中的测试

- 每次提交都应运行基本测试套件
- 较大的测试套件可以在夜间构建中运行
- 使用测试标记分类不同类型的测试

### 9. 测试覆盖率目标

MarketPrism项目的测试覆盖率目标：

- 核心服务模块：至少90%覆盖率 
- 工具和辅助功能：至少80%覆盖率
- 定期运行覆盖率报告并检查未测试的代码

### 10. 测试优先级指南

按照以下优先级开发测试：

1. 核心业务逻辑（数据处理和标准化）
2. 关键用户路径和API
3. 已知有问题的区域
4. 边缘案例和健壮性测试

## TDD实践示例

### 示例1：开发数据标准化功能

1. **编写测试**:
```python
def test_normalize_trade_timestamp_conversion(self):
    # 测试时间戳格式转换
    trade = {"timestamp": "2023-05-01T12:34:56.789Z", "price": "100.5"}
    result = self.normalizer.normalize_trade(trade)
    assert isinstance(result["timestamp"], float)
    assert abs(result["timestamp"] - 1682944496.789) < 0.001
```

2. **运行测试，确认失败**

3. **实现功能**:
```python
def normalize_trade(self, trade_data):
    result = trade_data.copy()
    
    # 转换时间戳
    if "timestamp" in result:
        try:
            dt = datetime.fromisoformat(result["timestamp"].replace("Z", "+00:00"))
            result["timestamp"] = dt.timestamp()
        except Exception:
            # 保持原始值
            pass
            
    return result
```

4. **运行测试，确认通过**

5. **重构优化**

### 示例2：针对Bug修复的TDD

1. **编写测试复现Bug**:
```python
def test_normalize_trade_empty_price(self):
    # 测试空价格处理
    trade = {"price": "", "amount": "2.5"}
    result = self.normalizer.normalize_trade(trade)
    assert result["price"] is None  # 期望空字符串转为None
```

2. **确认测试失败**

3. **修复Bug**:
```python
def normalize_trade(self, trade_data):
    result = trade_data.copy()
    
    # 处理空字符串
    for field in ["price", "amount"]:
        if field in result and result[field] == "":
            result[field] = None
            
    return result
```

4. **确认测试通过** 