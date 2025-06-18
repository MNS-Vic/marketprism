# MarketPrism 测试执行指南

## 📋 概述

本指南提供了MarketPrism项目测试套件的完整执行说明，包括环境设置、测试运行、结果分析和故障排除。

## 🚀 快速开始

### 环境准备
```bash
# 1. 确保Python版本
python --version  # 需要 3.10+

# 2. 安装测试依赖
pip install pytest pytest-cov pytest-asyncio pytest-mock pytest-xdist

# 3. 设置环境变量
export PYTHONPATH=/path/to/marketprism:$PYTHONPATH
```

### 基本测试运行
```bash
# 运行所有测试
pytest

# 运行核心模块测试
pytest tests/unit/core/

# 运行集成测试
pytest tests/integration/
```

## 📊 测试套件概览

### 当前测试统计
- **总测试用例**: 415个
- **通过测试**: 402个 (96.9%)
- **失败测试**: 5个 (1.2%)
- **跳过测试**: 8个 (1.9%)
- **测试覆盖率**: 32.61%

### 测试分布
```
单元测试 (70%): 290个测试
├── 配置管理: 24个测试
├── 可靠性组件: 89个测试
├── 网络组件: 67个测试
├── 存储组件: 45个测试
└── 监控组件: 65个测试

集成测试 (20%): 83个测试
├── 端到端数据管道: 25个测试
├── 微服务集成: 28个测试
├── 网络存储集成: 30个测试

性能测试 (10%): 42个测试
├── 负载测试: 20个测试
├── 压力测试: 22个测试
```

## 🔧 详细测试命令

### 1. 基础测试执行

#### 运行所有测试
```bash
# 标准运行
pytest

# 详细输出
pytest -v

# 简洁输出
pytest -q

# 显示测试进度
pytest --tb=short
```

#### 运行特定模块
```bash
# 核心模块
pytest tests/unit/core/

# 配置模块
pytest tests/unit/core/config/

# 可靠性模块
pytest tests/unit/core/reliability/

# 网络模块
pytest tests/unit/core/networking/

# 存储模块
pytest tests/unit/core/storage/
```

#### 运行特定测试文件
```bash
# 配置管理器测试
pytest tests/unit/core/config/test_unified_config_manager_fixed.py

# 限流器测试
pytest tests/unit/core/reliability/test_rate_limiter.py

# 重试处理器测试
pytest tests/unit/core/reliability/test_retry_handler.py
```

#### 运行特定测试方法
```bash
# 运行单个测试方法
pytest tests/unit/core/reliability/test_rate_limiter.py::TestAdaptiveRateLimiter::test_rate_limiter_basic_functionality

# 运行测试类
pytest tests/unit/core/config/test_unified_config_manager_fixed.py::TestUnifiedConfigManagerCore
```

### 2. 覆盖率测试

#### 生成覆盖率报告
```bash
# HTML报告
pytest tests/unit/core/ --cov=core --cov-report=html:tests/reports/coverage

# 终端报告
pytest tests/unit/core/ --cov=core --cov-report=term-missing

# 同时生成HTML和终端报告
pytest tests/unit/core/ --cov=core --cov-report=html:tests/reports/coverage --cov-report=term-missing
```

#### 覆盖率阈值设置
```bash
# 设置最低覆盖率要求
pytest tests/unit/core/ --cov=core --cov-fail-under=30

# 检查特定模块覆盖率
pytest tests/unit/core/reliability/ --cov=core.reliability --cov-fail-under=80
```

#### 覆盖率分析
```bash
# 显示未覆盖的行
pytest tests/unit/core/ --cov=core --cov-report=term-missing

# 生成详细的覆盖率报告
pytest tests/unit/core/ --cov=core --cov-report=html:coverage_detailed --cov-report=term
```

### 3. 并行测试执行

#### 多进程运行
```bash
# 使用4个进程
pytest tests/unit/core/ -n 4

# 自动检测CPU核心数
pytest tests/unit/core/ -n auto

# 指定进程数和输出格式
pytest tests/unit/core/ -n 4 -v
```

#### 分布式测试
```bash
# 按模块分发
pytest tests/unit/core/ -n auto --dist=loadscope

# 按文件分发
pytest tests/unit/core/ -n auto --dist=loadfile
```

### 4. 测试过滤和标记

#### 按标记运行
```bash
# 运行集成测试
pytest -m integration

# 运行性能测试
pytest -m performance

# 运行单元测试
pytest -m "not integration and not performance"

# 跳过慢速测试
pytest -m "not slow"
```

#### 按关键词过滤
```bash
# 运行包含"config"的测试
pytest -k config

# 运行包含"rate_limiter"的测试
pytest -k rate_limiter

# 排除特定测试
pytest -k "not test_slow_operation"
```

### 5. 调试和故障排除

#### 调试选项
```bash
# 显示print输出
pytest -s

# 在第一个失败处停止
pytest -x

# 最多失败3次后停止
pytest --maxfail=3

# 显示最慢的10个测试
pytest --durations=10
```

#### 详细错误信息
```bash
# 显示完整的错误堆栈
pytest --tb=long

# 显示简短的错误信息
pytest --tb=short

# 只显示一行错误信息
pytest --tb=line

# 不显示错误堆栈
pytest --tb=no
```

## 📈 测试结果分析

### 成功测试示例
```
tests/unit/core/config/test_unified_config_manager_fixed.py::TestUnifiedConfigManagerCore::test_config_manager_initialization_default PASSED [  4%]
```

### 失败测试示例
```
tests/unit/core/networking/test_proxy_manager.py::TestProxyConfigManager::test_proxy_manager_get_proxy_config_no_config FAILED
```

### 跳过测试示例
```
tests/unit/core/reliability/test_retry_handler.py::TestExponentialBackoffRetryIntegration::test_retry_handler_fallback_mechanism SKIPPED [s]
```

### 覆盖率报告解读
```
Name                                    Stmts   Miss  Cover   Missing
---------------------------------------------------------------------
core/reliability/rate_limiter.py         204     35    83%   162-166, 229-231
core/reliability/retry_handler.py        197     37    81%   161, 177, 196
core/config/unified_config_manager.py    253    139    45%   42-47, 55-59
---------------------------------------------------------------------
TOTAL                                   23877  16091    33%
```

## 🎯 测试执行策略

### 开发阶段
```bash
# 快速反馈循环
pytest tests/unit/core/module_being_developed/ -x -v

# 监控文件变化自动运行测试
pytest-watch tests/unit/core/module_being_developed/
```

### 提交前检查
```bash
# 完整测试套件
pytest tests/unit/core/ --cov=core --cov-fail-under=30

# 检查代码质量
pytest tests/unit/core/ --cov=core --cov-report=term-missing
```

### CI/CD集成
```bash
# 生产环境测试
pytest tests/ --cov=core --cov=services --cov-report=xml --junitxml=test-results.xml

# 性能基准测试
pytest tests/performance/ --benchmark-only
```

## 🔍 常见问题解决

### 1. 导入错误
```bash
# 问题: ModuleNotFoundError: No module named 'core'
# 解决方案:
export PYTHONPATH=/path/to/marketprism:$PYTHONPATH
# 或者
python -m pytest tests/unit/core/
```

### 2. 异步测试问题
```bash
# 问题: RuntimeWarning: coroutine 'test_function' was never awaited
# 解决方案: 确保安装pytest-asyncio
pip install pytest-asyncio

# 在测试中使用
@pytest.mark.asyncio
async def test_async_function():
    result = await async_function()
    assert result is not None
```

### 3. 覆盖率不准确
```bash
# 问题: 覆盖率报告缺少文件
# 解决方案: 指定正确的源码路径
pytest --cov=core --cov=services tests/

# 或者使用配置文件
# 在pytest.ini中设置:
[tool:pytest]
addopts = --cov=core --cov=services
```

### 4. 测试运行缓慢
```bash
# 解决方案: 使用并行执行
pytest tests/unit/core/ -n auto

# 或者跳过慢速测试
pytest tests/unit/core/ -m "not slow"
```

### 5. 内存使用过高
```bash
# 解决方案: 限制并行进程数
pytest tests/unit/core/ -n 2

# 或者分批运行测试
pytest tests/unit/core/config/
pytest tests/unit/core/reliability/
pytest tests/unit/core/networking/
```

## 📊 性能监控

### 测试执行时间
```bash
# 显示最慢的测试
pytest --durations=0

# 只显示超过1秒的测试
pytest --durations-min=1.0
```

### 内存使用监控
```bash
# 安装内存监控插件
pip install pytest-monitor

# 运行带内存监控的测试
pytest --monitor tests/unit/core/
```

### 并发性能测试
```bash
# 测试不同并发级别的性能
for n in 1 2 4 8; do
    echo "Testing with $n processes:"
    time pytest tests/unit/core/ -n $n -q
done
```

## 📋 测试维护

### 定期维护任务
1. **每周**: 运行完整测试套件，检查覆盖率
2. **每月**: 更新测试依赖，清理过时测试
3. **每季度**: 评估测试策略，优化测试性能

### 测试质量检查
```bash
# 检查测试覆盖率趋势
pytest tests/unit/core/ --cov=core --cov-report=html:coverage_$(date +%Y%m%d)

# 分析测试执行时间
pytest tests/unit/core/ --durations=20 > test_performance_$(date +%Y%m%d).log
```

### 测试数据管理
```bash
# 清理测试缓存
pytest --cache-clear

# 清理覆盖率数据
rm -rf .coverage htmlcov/

# 重置测试环境
find . -name "__pycache__" -type d -exec rm -rf {} +
```

## 📞 获取帮助

### 命令行帮助
```bash
# pytest帮助
pytest --help

# 覆盖率帮助
pytest --help | grep cov

# 插件帮助
pytest --help | grep -A5 -B5 plugin
```

### 在线资源
- [pytest官方文档](https://docs.pytest.org/)
- [pytest-cov文档](https://pytest-cov.readthedocs.io/)
- [pytest-asyncio文档](https://pytest-asyncio.readthedocs.io/)

---

**指南版本**: v1.0  
**最后更新**: 2025-06-18  
**适用版本**: MarketPrism TDD Phase 4
