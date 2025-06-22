# MarketPrism 代码修复执行规则

## 📋 概述

本文档定义了MarketPrism项目代码修复过程中的质量标准、TDD要求和验收条件，确保修复工作的一致性和高质量。

---

## 🎯 代码质量标准

### 代码规范
- **Python版本**: 支持Python 3.10-3.12
- **代码风格**: 遵循PEP 8标准
- **类型注解**: 所有公共方法必须有类型注解
- **文档字符串**: 所有类和公共方法必须有docstring
- **命名规范**: 使用描述性命名，避免缩写

### 代码复杂度要求
- **函数长度**: 单个函数不超过50行
- **类长度**: 单个类不超过500行
- **圈复杂度**: 单个函数圈复杂度不超过10
- **嵌套深度**: 代码嵌套不超过4层
- **重复代码**: 重复代码率不超过10%

### 性能要求
- **响应时间**: API调用响应时间 < 2秒
- **内存使用**: 单个适配器内存占用 < 100MB
- **CPU使用**: 正常运行CPU使用率 < 20%
- **并发处理**: 支持至少100个并发连接

---

## 🧪 TDD测试要求

### 测试驱动开发流程
1. **Red**: 先写失败的测试
2. **Green**: 编写最小可行代码使测试通过
3. **Refactor**: 重构代码保持测试通过

### 测试覆盖率目标
- **整体覆盖率**: ≥ 90%
- **核心模块覆盖率**: ≥ 95%
- **新增代码覆盖率**: 100%
- **关键路径覆盖率**: 100%

### 测试类型要求
- **单元测试**: 测试单个函数/方法
- **集成测试**: 测试模块间交互
- **端到端测试**: 测试完整业务流程
- **性能测试**: 验证性能指标
- **错误处理测试**: 验证异常情况

### 测试命名规范
```python
def test_[功能]_[场景]_[预期结果]():
    """测试：[功能描述] - [场景描述]"""
    # 示例
def test_binance_adapter_get_server_time_success():
    """测试：Binance适配器获取服务器时间成功"""
```

---

## ✅ 验收条件定义

### Priority 1任务验收标准

#### Exchange适配器API完善
**功能验收**:
- [ ] 所有REST API方法正常工作
- [ ] API响应时间 < 2秒
- [ ] 错误处理覆盖率 100%
- [ ] 支持所有必需的认证方式

**测试验收**:
- [ ] 单元测试覆盖率 ≥ 95%
- [ ] 集成测试通过率 100%
- [ ] 性能测试达标
- [ ] 错误场景测试完整

**代码质量验收**:
- [ ] 代码审查通过
- [ ] 静态分析无高危问题
- [ ] 文档更新完整
- [ ] 符合编码规范

#### 依赖管理优化
**功能验收**:
- [ ] 无依赖环境正常运行
- [ ] 依赖冲突率 < 1%
- [ ] 安装成功率 > 98%
- [ ] 版本兼容性明确

**测试验收**:
- [ ] 多环境测试通过
- [ ] 依赖缺失场景测试
- [ ] 版本兼容性测试
- [ ] 安装流程测试

### Priority 2任务验收标准

#### 监控功能完善
**功能验收**:
- [ ] 基础监控无外部依赖
- [ ] 监控数据准确率 > 99%
- [ ] 告警响应时间 < 30秒
- [ ] 监控覆盖率 > 90%

**测试验收**:
- [ ] 监控功能单元测试
- [ ] 告警机制集成测试
- [ ] 性能影响测试
- [ ] 故障恢复测试

#### 配置管理优化
**功能验收**:
- [ ] 配置错误检出率 > 95%
- [ ] 配置验证时间 < 1秒
- [ ] 环境覆盖成功率 > 99%
- [ ] 配置热重载支持

**测试验收**:
- [ ] 配置验证测试
- [ ] 环境覆盖测试
- [ ] 配置变更测试
- [ ] 错误恢复测试

### Priority 3任务验收标准

#### 代码重构优化
**质量验收**:
- [ ] 代码重复率 < 10%
- [ ] 圈复杂度达标
- [ ] 代码可读性提升
- [ ] 维护成本降低

**测试验收**:
- [ ] 重构后功能测试
- [ ] 性能回归测试
- [ ] 兼容性测试
- [ ] 扩展性验证

---

## 🛠️ 修复执行指导

### 任务执行流程

#### 1. 任务准备阶段
```bash
# 创建功能分支
git checkout -b fix/[task-name]

# 更新依赖
pip install -r requirements-dev.txt

# 运行基线测试
pytest tests/ --cov=core --cov=services
```

#### 2. TDD开发阶段
```python
# 步骤1: 编写失败测试
def test_new_feature_success():
    """测试：新功能正常工作"""
    # 测试代码
    assert False  # 初始失败

# 步骤2: 实现最小代码
def new_feature():
    """新功能实现"""
    pass  # 最小实现

# 步骤3: 重构优化
def new_feature():
    """新功能实现 - 重构版本"""
    # 优化后的实现
    pass
```

#### 3. 质量检查阶段
```bash
# 代码格式检查
black --check .
flake8 .

# 类型检查
mypy src/

# 安全扫描
bandit -r src/

# 测试覆盖率
pytest --cov=src --cov-report=html
```

#### 4. 提交审查阶段
```bash
# 提交代码
git add .
git commit -m "fix: [task description]"

# 推送分支
git push origin fix/[task-name]

# 创建Pull Request
# 等待代码审查
```

### 代码模板

#### Exchange适配器方法模板
```python
async def get_api_method(self, param: str) -> Dict[str, Any]:
    """
    API方法描述
    
    Args:
        param: 参数描述
        
    Returns:
        API响应数据
        
    Raises:
        Exception: 错误情况描述
    """
    try:
        # 1. 参数验证
        if not param:
            raise ValueError("参数不能为空")
            
        # 2. 会话检查
        await self._ensure_session()
        
        # 3. API调用
        url = f"{self.base_url}/api/endpoint"
        params = {"param": param}
        
        async with self.session.get(url, params=params) as response:
            # 4. 响应处理
            if response.status == 200:
                return await response.json()
            else:
                await self._handle_api_error(response)
                
    except Exception as e:
        # 5. 错误处理
        self.logger.error("API调用失败", exc_info=True)
        raise
```

#### 测试用例模板
```python
@pytest.mark.asyncio
async def test_api_method_success(self):
    """测试：API方法调用成功"""
    # Arrange
    expected_response = {"result": "success"}
    
    with patch.object(self.adapter, '_ensure_session'):
        with patch.object(self.adapter.session, 'get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = expected_response
            mock_get.return_value.__aenter__.return_value = mock_response
            
            # Act
            result = await self.adapter.get_api_method("test_param")
            
            # Assert
            assert result == expected_response
            mock_get.assert_called_once()
```

### 错误处理模板
```python
class ExchangeAPIError(Exception):
    """交易所API错误"""
    def __init__(self, message: str, status_code: int = None, response_data: Dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data

async def _handle_api_error(self, response: aiohttp.ClientResponse):
    """处理API错误响应"""
    try:
        error_data = await response.json()
    except:
        error_data = {"error": await response.text()}
    
    error_message = f"API错误: {response.status}"
    if "msg" in error_data:
        error_message += f" - {error_data['msg']}"
        
    raise ExchangeAPIError(
        message=error_message,
        status_code=response.status,
        response_data=error_data
    )
```

---

## 📊 质量检查清单

### 代码提交前检查
- [ ] 所有测试通过
- [ ] 代码覆盖率达标
- [ ] 代码格式符合规范
- [ ] 类型注解完整
- [ ] 文档字符串完整
- [ ] 无安全漏洞
- [ ] 性能测试通过

### Pull Request检查
- [ ] 功能需求满足
- [ ] 测试用例完整
- [ ] 代码审查通过
- [ ] CI/CD流水线通过
- [ ] 文档更新完整
- [ ] 变更日志更新

### 发布前检查
- [ ] 集成测试通过
- [ ] 性能基准测试
- [ ] 安全扫描通过
- [ ] 兼容性测试
- [ ] 部署脚本验证
- [ ] 回滚方案准备

---

## 🚨 风险缓解措施

### 开发风险
- **代码冲突**: 频繁同步主分支，小步提交
- **功能回归**: 完整的回归测试套件
- **性能下降**: 性能基准测试和监控
- **安全漏洞**: 自动化安全扫描

### 部署风险
- **部署失败**: 蓝绿部署策略
- **数据丢失**: 数据备份和恢复方案
- **服务中断**: 滚动更新和健康检查
- **配置错误**: 配置验证和回滚机制

### 质量风险
- **测试不足**: 强制覆盖率要求
- **文档缺失**: 文档审查流程
- **标准不一**: 自动化代码检查
- **技术债务**: 定期代码审查和重构

---

## 📚 实用工具和模板

### 常用命令集合

#### 开发环境设置
```bash
# 激活虚拟环境
source venv/bin/activate

# 安装开发依赖
pip install -r requirements-dev.txt

# 设置pre-commit钩子
pre-commit install
```

#### 测试命令
```bash
# 运行所有测试
pytest tests/ -v

# 运行特定模块测试
pytest tests/unit/services/data_collector/ -v

# 运行覆盖率测试
pytest --cov=src --cov-report=html --cov-report=term

# 运行性能测试
pytest tests/performance/ -v --benchmark-only
```

#### 代码质量检查
```bash
# 格式化代码
black .

# 检查代码风格
flake8 .

# 类型检查
mypy src/

# 安全扫描
bandit -r src/

# 复杂度检查
radon cc src/ -a
```

### 调试工具配置

#### VS Code调试配置 (.vscode/launch.json)
```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: 当前文件",
            "type": "python",
            "request": "launch",
            "program": "${file}",
            "console": "integratedTerminal",
            "cwd": "${workspaceFolder}",
            "env": {
                "PYTHONPATH": "${workspaceFolder}/src"
            }
        },
        {
            "name": "Python: 测试调试",
            "type": "python",
            "request": "launch",
            "module": "pytest",
            "args": ["${file}", "-v", "-s"],
            "console": "integratedTerminal",
            "cwd": "${workspaceFolder}"
        }
    ]
}
```

#### 日志配置模板
```python
import logging
import sys
from datetime import datetime

def setup_logging(level=logging.INFO, log_file=None):
    """设置日志配置"""
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # 文件处理器
    handlers = [console_handler]
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    # 配置根日志器
    logging.basicConfig(
        level=level,
        handlers=handlers,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    return logging.getLogger(__name__)
```

### 性能监控模板

#### 性能装饰器
```python
import time
import functools
from typing import Callable, Any

def performance_monitor(func: Callable) -> Callable:
    """性能监控装饰器"""
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs) -> Any:
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time

            # 记录性能指标
            logger = logging.getLogger(func.__module__)
            logger.info(
                "函数执行完成",
                function=func.__name__,
                execution_time=execution_time,
                args_count=len(args),
                kwargs_count=len(kwargs)
            )

            # 性能警告
            if execution_time > 5.0:  # 超过5秒
                logger.warning(
                    "函数执行时间过长",
                    function=func.__name__,
                    execution_time=execution_time
                )

            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger = logging.getLogger(func.__module__)
            logger.error(
                "函数执行失败",
                function=func.__name__,
                execution_time=execution_time,
                error=str(e)
            )
            raise

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs) -> Any:
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time

            logger = logging.getLogger(func.__module__)
            logger.info(
                "函数执行完成",
                function=func.__name__,
                execution_time=execution_time
            )

            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger = logging.getLogger(func.__module__)
            logger.error(
                "函数执行失败",
                function=func.__name__,
                execution_time=execution_time,
                error=str(e)
            )
            raise

    # 根据函数类型选择包装器
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper
```

### 错误处理最佳实践

#### 自定义异常类
```python
class MarketPrismError(Exception):
    """MarketPrism基础异常类"""
    def __init__(self, message: str, error_code: str = None, context: dict = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.context = context or {}
        self.timestamp = datetime.now(timezone.utc)

class ExchangeAPIError(MarketPrismError):
    """交易所API错误"""
    def __init__(self, message: str, exchange: str, status_code: int = None, **kwargs):
        super().__init__(message, **kwargs)
        self.exchange = exchange
        self.status_code = status_code

class RateLimitError(ExchangeAPIError):
    """限流错误"""
    def __init__(self, message: str, retry_after: int = 60, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after

class AuthenticationError(ExchangeAPIError):
    """认证错误"""
    pass

class ConfigurationError(MarketPrismError):
    """配置错误"""
    def __init__(self, message: str, config_key: str = None, **kwargs):
        super().__init__(message, **kwargs)
        self.config_key = config_key
```

#### 重试机制模板
```python
import asyncio
import random
from typing import Callable, Any, Type, Tuple

async def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retry_exceptions: Tuple[Type[Exception], ...] = (Exception,)
) -> Any:
    """带退避的重试机制"""

    for attempt in range(max_retries + 1):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func()
            else:
                return func()
        except retry_exceptions as e:
            if attempt == max_retries:
                raise

            # 计算延迟时间
            delay = min(base_delay * (backoff_factor ** attempt), max_delay)

            # 添加抖动
            if jitter:
                delay *= (0.5 + random.random() * 0.5)

            logger = logging.getLogger(__name__)
            logger.warning(
                "函数执行失败，准备重试",
                function=func.__name__,
                attempt=attempt + 1,
                max_retries=max_retries,
                delay=delay,
                error=str(e)
            )

            await asyncio.sleep(delay)

    raise RuntimeError("重试次数已用完")
```

### 配置管理模板

#### 配置验证器
```python
from typing import Dict, Any, List
import jsonschema

class ConfigValidator:
    """配置验证器"""

    def __init__(self):
        self.schema = {
            "type": "object",
            "properties": {
                "exchanges": {
                    "type": "object",
                    "properties": {
                        "binance": {"$ref": "#/definitions/exchange_config"},
                        "okx": {"$ref": "#/definitions/exchange_config"},
                        "deribit": {"$ref": "#/definitions/exchange_config"}
                    }
                },
                "data_collector": {
                    "type": "object",
                    "properties": {
                        "buffer_size": {"type": "integer", "minimum": 1000},
                        "flush_interval": {"type": "number", "minimum": 1.0},
                        "max_connections": {"type": "integer", "minimum": 1}
                    },
                    "required": ["buffer_size", "flush_interval"]
                }
            },
            "definitions": {
                "exchange_config": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean"},
                        "api_key": {"type": "string"},
                        "api_secret": {"type": "string"},
                        "base_url": {"type": "string", "format": "uri"},
                        "ws_url": {"type": "string", "format": "uri"}
                    },
                    "required": ["enabled", "base_url", "ws_url"]
                }
            },
            "required": ["exchanges", "data_collector"]
        }

    def validate(self, config: Dict[str, Any]) -> List[str]:
        """验证配置并返回错误列表"""
        errors = []

        try:
            jsonschema.validate(config, self.schema)
        except jsonschema.ValidationError as e:
            errors.append(f"配置验证失败: {e.message}")
        except jsonschema.SchemaError as e:
            errors.append(f"配置模式错误: {e.message}")

        # 自定义验证规则
        errors.extend(self._validate_business_rules(config))

        return errors

    def _validate_business_rules(self, config: Dict[str, Any]) -> List[str]:
        """验证业务规则"""
        errors = []

        # 检查至少启用一个交易所
        exchanges = config.get("exchanges", {})
        enabled_exchanges = [
            name for name, cfg in exchanges.items()
            if cfg.get("enabled", False)
        ]

        if not enabled_exchanges:
            errors.append("至少需要启用一个交易所")

        # 检查API密钥配置
        for name, cfg in exchanges.items():
            if cfg.get("enabled", False):
                if not cfg.get("api_key") and not cfg.get("api_secret"):
                    errors.append(f"{name}交易所已启用但缺少API密钥配置")

        return errors
```

---

## 📋 检查清单模板

### 代码提交检查清单
```markdown
## 代码提交前检查清单

### 功能实现
- [ ] 功能需求完全实现
- [ ] 边界条件处理完整
- [ ] 错误处理机制完善
- [ ] 性能要求满足

### 代码质量
- [ ] 代码格式符合PEP 8
- [ ] 类型注解完整
- [ ] 文档字符串完整
- [ ] 变量命名清晰
- [ ] 函数长度合理 (< 50行)
- [ ] 圈复杂度合理 (< 10)

### 测试覆盖
- [ ] 单元测试覆盖率 ≥ 90%
- [ ] 集成测试完整
- [ ] 错误场景测试
- [ ] 性能测试通过
- [ ] 所有测试通过

### 安全检查
- [ ] 无硬编码密钥
- [ ] 输入验证完整
- [ ] SQL注入防护
- [ ] XSS防护
- [ ] 安全扫描通过

### 文档更新
- [ ] API文档更新
- [ ] 配置文档更新
- [ ] 变更日志更新
- [ ] README更新
```

### Pull Request检查清单
```markdown
## Pull Request检查清单

### 基本信息
- [ ] PR标题清晰描述变更
- [ ] PR描述包含变更原因
- [ ] 关联相关Issue
- [ ] 标记正确的标签

### 代码审查
- [ ] 代码逻辑正确
- [ ] 架构设计合理
- [ ] 性能影响评估
- [ ] 安全风险评估
- [ ] 向后兼容性检查

### 测试验证
- [ ] CI/CD流水线通过
- [ ] 所有测试通过
- [ ] 覆盖率达标
- [ ] 性能测试通过
- [ ] 手动测试验证

### 部署准备
- [ ] 数据库迁移脚本
- [ ] 配置变更说明
- [ ] 部署步骤文档
- [ ] 回滚方案准备
```

---

*本规则文档将根据项目进展持续更新，确保修复工作的高质量执行。*
