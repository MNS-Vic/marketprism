# MarketPrism Mock清理计划

## 清理目标
完全移除项目中的所有Mock对象，替换为真实的服务和数据，符合"不要Mock，要真实"的要求。

## 需要清理的Mock使用

### 1. 核心代码中的Mock (高优先级)

#### 1.1 MockExchangeAdapter
**文件**: `services/python-collector/src/marketprism_collector/exchanges/base.py`
**问题**: 包含完整的MockExchangeAdapter类
**解决方案**: 
- 移除MockExchangeAdapter类
- 如需测试数据，使用真实的交易所API或测试环境
- 更新__init__.py移除Mock导入

#### 1.2 交换所工厂
**文件**: `services/python-collector/src/marketprism_collector/exchanges/__init__.py`
**问题**: 导出MockExchangeAdapter
**解决方案**: 移除Mock相关导入和导出

### 2. 测试框架Mock (中优先级)

#### 2.1 conftest.py Mock对象
**文件**: `tests/conftest.py`
**问题**: 包含多个Mock类
**解决方案**: 
- 移除所有Mock类定义
- 替换为真实服务的测试fixture
- 使用Docker容器提供真实服务

#### 2.2 Mock工厂
**文件**: `tests/mocks/mock_factory.py`
**问题**: 完整的Mock对象工厂
**解决方案**: 
- 删除整个文件
- 创建真实服务连接工具
- 更新所有引用此文件的测试

### 3. 测试文件Mock使用 (中优先级)

#### 3.1 测试工具
**文件**: `tests/utils/test_helpers.py`
**问题**: 导入unittest.mock
**解决方案**: 移除Mock导入，使用真实数据生成器

#### 3.2 可靠性测试
**文件**: `services/reliability/tests/test_reliability_system.py`
**问题**: 使用AsyncMock, MagicMock
**解决方案**: 重写为真实服务测试

### 4. 遗留测试文件 (低优先级)

#### 4.1 简单测试文件
**文件**: `services/python-collector/test_collector_simple.py`
**问题**: 使用MockExchangeAdapter
**解决方案**: 重写为真实交换所测试或删除

#### 4.2 其他测试文件
**问题**: 多个测试文件使用Mock对象
**解决方案**: 逐个重写为真实测试

## 实施步骤

### 第一阶段：清理核心代码Mock
1. 移除MockExchangeAdapter类
2. 更新交换所工厂
3. 验证核心功能正常

### 第二阶段：重构测试框架
1. 删除mock_factory.py
2. 清理conftest.py中的Mock
3. 创建真实服务测试工具

### 第三阶段：更新测试文件
1. 重写使用Mock的测试文件
2. 确保所有测试使用真实服务
3. 更新测试文档

### 第四阶段：验证和清理
1. 运行所有真实测试
2. 确认无Mock残留
3. 更新项目文档

## 替换方案

### Mock -> 真实服务映射

| Mock对象 | 真实替代方案 |
|---------|-------------|
| MockNATSClient | 真实NATS Docker容器 |
| MockClickHouseClient | 真实ClickHouse Docker容器 |
| MockExchangeAdapter | 真实交易所API (Binance/OKX) |
| MockHTTPClient | 真实HTTP请求 (requests/httpx) |
| MockRedisClient | 真实Redis Docker容器 |

### 测试数据生成

| Mock数据 | 真实数据来源 |
|---------|-------------|
| 模拟交易数据 | 真实交易所API |
| 模拟订单簿 | 真实市场深度数据 |
| 模拟行情 | 真实价格数据 |
| 模拟网络响应 | 真实API响应 |

## 预期效果

### 清理前问题
- 测试可能通过但生产环境失败
- 无法发现真实集成问题
- Mock行为与真实服务不一致
- 测试结果不反映真实性能

### 清理后优势
- 测试通过意味着真实环境可用
- 能发现真实的网络和集成问题
- 测试结果反映真实性能
- 提高生产环境部署信心

## 风险评估

### 潜在风险
- 测试执行时间可能增加
- 需要外部服务依赖
- 网络问题可能影响测试

### 风险缓解
- 使用Docker确保服务可用性
- 实现服务健康检查
- 提供离线测试数据备份
- 优化测试执行顺序

## 完成标准

### 代码清理标准
- [x] 所有Mock类已移除
- [x] 所有unittest.mock导入已移除（核心文件）
- [ ] 所有测试使用真实服务
- [x] 核心代码无Mock残留

### 测试质量标准
- [ ] 所有测试通过
- [ ] 测试覆盖率保持或提升
- [ ] 性能基准建立
- [ ] 文档更新完成

### 验证标准
- [ ] 搜索代码无Mock关键词
- [ ] 真实测试套件运行成功
- [ ] CI/CD流程正常
- [ ] 团队培训完成 