# Data Collector TDD 测试套件

MarketPrism Data Collector 的完整 TDD 测试套件，提供全面的测试覆盖和 TDD 开发支持。

## 🏗️ 测试架构

```
tests/data_collector/
├── unit/                   # 单元测试
│   ├── test_config.py     # 配置管理测试
│   ├── test_data_types.py # 数据类型测试
│   └── test_collector.py  # 主类功能测试
├── integration/           # 集成测试
│   └── test_collector_integration.py
├── e2e/                  # 端到端测试
│   └── test_full_data_collection_flow.py
├── run_tdd_tests.py      # TDD 测试运行器
├── pytest.ini           # pytest 配置
└── README.md            # 本文档
```

## 🚀 快速开始

### 安装依赖

```bash
# 安装测试依赖
pip install pytest pytest-asyncio pytest-cov aiohttp psutil

# 或者从项目根目录安装
pip install -r requirements.txt
```

### 运行测试

```bash
# 进入测试目录
cd tests/data_collector

# 运行所有测试
python run_tdd_tests.py all

# 运行单元测试
python run_tdd_tests.py unit

# 运行集成测试
python run_tdd_tests.py integration

# 运行E2E测试
python run_tdd_tests.py e2e

# 运行测试并生成覆盖率报告
python run_tdd_tests.py coverage

# TDD 红-绿-重构循环
python run_tdd_tests.py tdd
```

### 查看可用命令

```bash
python run_tdd_tests.py --help
```

## 🧪 测试类型

### 单元测试 (Unit Tests)

专注于独立组件的功能测试，使用 Mock 隔离外部依赖。

**覆盖范围：**
- 配置管理 (`test_config.py`)
- 数据类型和验证 (`test_data_types.py`)
- MarketDataCollector 主类 (`test_collector.py`)

**特点：**
- 快速执行
- 完全隔离
- 高覆盖率
- 边缘情况测试

### 集成测试 (Integration Tests)

测试组件间的集成，包括部分真实依赖。

**覆盖范围：**
- 配置系统集成
- HTTP API 集成
- 数据流集成
- 性能集成
- 错误处理集成

**特点：**
- 真实组件交互
- 部分 Mock 外部服务
- 中等执行时间
- 真实场景测试

### 端到端测试 (E2E Tests)

测试完整的数据收集流程，包括真实的外部服务交互。

**覆盖范围：**
- 完整生命周期测试
- 真实 NATS 集成（可选）
- 真实交易所 API 集成（可选）
- 性能压力测试
- 资源使用测试

**特点：**
- 最接近生产环境
- 可能需要外部服务
- 较长执行时间
- 完整流程验证

## 🔄 TDD 开发流程

### 红-绿-重构循环

1. **🔴 RED 阶段**：编写失败的测试
   ```bash
   python run_tdd_tests.py tdd --file test_new_feature.py
   ```

2. **🟢 GREEN 阶段**：编写最少代码使测试通过
   - 修复代码实现
   - 再次运行测试

3. **🔵 REFACTOR 阶段**：重构代码提高质量
   - 保持测试通过
   - 改进代码结构

### TDD 最佳实践

- **测试先行**：先写测试，后写代码
- **小步迭代**：每次只解决一个具体问题
- **快速反馈**：频繁运行测试获得反馈
- **持续重构**：在测试保护下安全重构

## 📊 测试覆盖率

### 查看覆盖率

```bash
# 生成覆盖率报告
python run_tdd_tests.py coverage --test-type all -v

# 查看HTML报告
open htmlcov/index.html
```

### 覆盖率目标

- **单元测试**：> 90%
- **集成测试**：> 70%
- **整体覆盖率**：> 80%

## 🏷️ 测试标记

使用 pytest 标记来分类和过滤测试：

```bash
# 只运行单元测试
pytest -m unit

# 只运行不需要外部服务的测试
pytest -m "not nats and not exchange"

# 运行性能测试
pytest -m performance

# 跳过慢速测试
pytest -m "not slow"
```

### 可用标记

- `unit`: 单元测试
- `integration`: 集成测试
- `e2e`: 端到端测试
- `slow`: 慢速测试
- `nats`: 需要 NATS 服务器
- `exchange`: 需要真实交易所 API
- `performance`: 性能测试

## 🛠️ 开发工具

### 测试运行器功能

```bash
# 列出所有可用测试
python run_tdd_tests.py list

# 检查依赖
python run_tdd_tests.py deps

# 运行特定测试
python run_tdd_tests.py specific --pattern "test_config"

# 详细输出
python run_tdd_tests.py unit -v
```

### IDE 集成

#### VS Code
1. 安装 Python 扩展
2. 配置测试发现：`"python.testing.pytestEnabled": true`
3. 设置测试路径：`"python.testing.pytestArgs": ["tests/data_collector"]`

#### PyCharm
1. 设置测试运行器为 pytest
2. 配置工作目录为项目根目录
3. 添加测试目录到源代码路径

## 🐛 故障排除

### 常见问题

1. **导入错误**
   ```bash
   # 确保在项目根目录运行测试
   cd /path/to/marketprism
   python -m pytest tests/data_collector/
   ```

2. **依赖缺失**
   ```bash
   # 检查并安装依赖
   python tests/data_collector/run_tdd_tests.py deps
   pip install pytest pytest-asyncio pytest-cov
   ```

3. **异步测试问题**
   ```bash
   # 确保安装了 pytest-asyncio
   pip install pytest-asyncio
   ```

4. **NATS 连接失败**
   ```bash
   # 启动本地 NATS 服务器
   docker run -p 4222:4222 nats:latest
   
   # 或跳过需要 NATS 的测试
   pytest -m "not nats"
   ```

### 调试技巧

1. **添加调试输出**
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

2. **使用 pdb 调试**
   ```python
   import pdb; pdb.set_trace()
   ```

3. **查看详细错误**
   ```bash
   pytest -v --tb=long
   ```

## 📈 性能测试

### 运行性能测试

```bash
# 运行所有性能测试
pytest -m performance -v

# 运行特定性能测试
pytest tests/data_collector/integration/test_collector_integration.py::TestPerformanceIntegration -v
```

### 性能指标

- **吞吐量**：> 200 消息/秒
- **延迟**：< 50ms 处理时间
- **内存使用**：< 100MB 增长
- **CPU 使用**：< 50% 平均

## 🤝 贡献指南

### 添加新测试

1. **确定测试类型**：单元、集成或 E2E
2. **创建测试文件**：遵循命名约定 `test_*.py`
3. **编写测试**：使用 TDD 方法
4. **添加适当标记**：使用 pytest 标记
5. **更新文档**：更新相关文档

### 测试约定

1. **命名约定**
   - 文件：`test_feature_name.py`
   - 类：`TestFeatureName`
   - 方法：`test_specific_behavior`

2. **结构约定**
   ```python
   class TestFeatureName:
       def test_should_behave_correctly_when_condition(self):
           # Arrange
           # Act
           # Assert
   ```

3. **文档约定**
   - 每个测试文件顶部添加模块文档
   - 每个测试类添加类文档
   - 复杂测试添加方法文档

## 📚 参考资源

- [pytest 文档](https://docs.pytest.org/)
- [pytest-asyncio 文档](https://pytest-asyncio.readthedocs.io/)
- [TDD 最佳实践](https://testdriven.io/test-driven-development/)
- [Python 测试指南](https://realpython.com/python-testing/)

---

## 🎯 测试目标

通过这个完整的 TDD 测试套件，我们确保 Data Collector 服务：

✅ **功能正确性**：所有功能按预期工作  
✅ **稳定性**：在各种条件下稳定运行  
✅ **性能**：满足性能要求  
✅ **可维护性**：代码易于理解和修改  
✅ **可扩展性**：支持未来功能扩展  

**让我们一起通过 TDD 构建高质量的 Data Collector！** 🚀