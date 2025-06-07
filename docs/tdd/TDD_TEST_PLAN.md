# MarketPrism TDD 测试优化计划
*真实环境 - 问题导向 - 测试先行*

## 🎯 TDD 核心目标

### 测试原则
1. **🔬 真实环境测试**：不使用Mock，连接真实交易所API、数据库
2. **🧪 测试先行**：先写测试描述需求，再实现功能
3. **⚡ 快速反馈**：小步迭代，立即发现问题和设计缺陷
4. **🎯 问题导向**：每个测试对应具体的功能需求或设计问题

### 质量目标
- ✅ **功能完整性**：所有微服务真实可用
- ✅ **性能达标**：响应时间、吞吐量满足要求
- ✅ **稳定性保证**：长时间运行无故障
- ✅ **集成正确性**：服务间通信正常

## 📋 TDD 测试阶段规划

### Phase 1: 基础服务真实性验证 (Week 1)
**目标**：确保每个微服务都能真实工作，不依赖模拟

#### 1.1 数据存储服务真实性测试
```python
# TDD: 先写测试，描述期望的行为
def test_real_clickhouse_connection():
    """测试：数据存储服务应该能连接真实的ClickHouse"""
    # Given: ClickHouse服务运行中
    # When: 调用存储服务API
    # Then: 应该成功连接并返回状态
    pass  # 实现将驱动代码编写

def test_real_redis_caching():
    """测试：缓存功能应该使用真实Redis"""
    # Given: Redis服务运行中
    # When: 存储和读取缓存数据
    # Then: 数据应该正确缓存和检索
    pass

def test_hot_cold_data_lifecycle():
    """测试：热冷数据生命周期管理应该真实工作"""
    # Given: 有热数据存储
    # When: 触发数据归档
    # Then: 数据应该正确迁移到冷存储
    pass
```

#### 1.2 市场数据采集真实性测试
```python
def test_real_binance_connection():
    """测试：应该能连接真实的Binance Testnet"""
    # Given: 代理配置正确，有Testnet API密钥
    # When: 连接Binance WebSocket
    # Then: 应该成功连接并接收数据
    pass

def test_real_data_normalization():
    """测试：应该正确规范化真实市场数据"""
    # Given: 接收到Binance原始数据
    # When: 进行数据规范化
    # Then: 输出应该符合内部数据格式
    pass

def test_multi_exchange_real_data():
    """测试：应该同时处理多个交易所的真实数据"""
    # Given: 连接Binance和OKX
    # When: 同时订阅相同交易对
    # Then: 应该正确处理并区分数据源
    pass
```

#### 1.3 API网关真实路由测试
```python
def test_real_service_discovery():
    """测试：API网关应该发现真实运行的服务"""
    # Given: 微服务都在运行
    # When: 查询服务注册表
    # Then: 应该返回所有健康的服务
    pass

def test_real_load_balancing():
    """测试：负载均衡应该分发到真实服务实例"""
    # Given: 有多个服务实例
    # When: 发送多个请求
    # Then: 请求应该均匀分发
    pass
```

### Phase 2: 端到端集成真实性验证 (Week 2)
**目标**：验证完整的数据流和服务协作

#### 2.1 真实数据流测试
```python
def test_end_to_end_data_flow():
    """测试：从数据采集到存储的完整流程"""
    # Given: 所有服务正常运行
    # When: 启动市场数据采集
    # Then: 数据应该正确流转并存储
    
    # 详细步骤：
    # 1. 采集器连接交易所
    # 2. 接收真实市场数据
    # 3. 数据规范化处理
    # 4. 发布到消息队列
    # 5. 存储服务接收并保存
    # 6. 可以通过API查询到数据
    pass

def test_real_time_data_processing():
    """测试：实时数据处理的性能和准确性"""
    # Given: 高频数据流
    # When: 系统处理实时数据
    # Then: 延迟应该小于指定阈值
    pass

def test_error_recovery_in_real_scenario():
    """测试：真实场景下的错误恢复"""
    # Given: 系统正常运行
    # When: 模拟网络中断或服务故障
    # Then: 系统应该自动恢复并重新连接
    pass
```

#### 2.2 性能压力真实性测试
```python
def test_real_load_performance():
    """测试：真实负载下的系统性能"""
    # Given: 系统接收真实市场数据
    # When: 同时处理多个交易所的高频数据
    # Then: 系统应该保持稳定性能
    pass

def test_memory_usage_under_real_load():
    """测试：真实负载下的内存使用"""
    # Given: 长时间运行
    # When: 处理大量真实数据
    # Then: 内存使用应该稳定，无内存泄漏
    pass
```

### Phase 3: 生产场景模拟测试 (Week 3)
**目标**：模拟生产环境的复杂场景

#### 3.1 高可用性测试
```python
def test_service_failure_recovery():
    """测试：单个服务故障时的系统恢复"""
    # Given: 系统正常运行
    # When: 单个服务崩溃
    # Then: 其他服务应该继续工作，故障服务应该自动重启
    pass

def test_database_failover():
    """测试：数据库故障时的故障转移"""
    # Given: 主数据库故障
    # When: 切换到备份数据库
    # Then: 数据访问应该无缝切换
    pass
```

#### 3.2 数据一致性测试
```python
def test_data_consistency_across_services():
    """测试：跨服务数据一致性"""
    # Given: 多个服务处理相同数据
    # When: 并发更新数据
    # Then: 所有服务看到的数据应该一致
    pass

def test_transaction_integrity():
    """测试：事务完整性"""
    # Given: 跨服务事务
    # When: 部分服务失败
    # Then: 事务应该正确回滚
    pass
```

### Phase 4: 安全性和监控真实性测试 (Week 4)
**目标**：验证安全防护和监控告警

#### 4.1 安全性测试
```python
def test_real_api_rate_limiting():
    """测试：真实API速率限制"""
    # Given: 配置了速率限制
    # When: 超过限制频率发送请求
    # Then: 应该正确拒绝过量请求
    pass

def test_authentication_with_real_tokens():
    """测试：使用真实token的认证"""
    # Given: 真实的JWT token
    # When: 访问受保护的API
    # Then: 应该正确验证并授权
    pass
```

#### 4.2 监控告警测试
```python
def test_real_prometheus_metrics():
    """测试：Prometheus指标收集"""
    # Given: 系统正常运行
    # When: 查询Prometheus指标
    # Then: 应该有完整的服务指标数据
    pass

def test_alert_triggering():
    """测试：告警触发机制"""
    # Given: 配置了告警规则
    # When: 系统指标超过阈值
    # Then: 应该正确触发告警
    pass
```

## 🛠️ TDD 工具和基础设施

### 测试环境配置
```yaml
# config/test_config.yaml 示例
proxy:
  enabled: true
  http_proxy: "http://127.0.0.1:7890"
  https_proxy: "http://127.0.0.1:7890"

exchanges:
  binance:
    testnet: true
    base_url: "https://testnet.binance.vision"
    ws_url: "wss://testnet.binance.vision/ws"
    
databases:
  clickhouse:
    host: "localhost"
    port: 8123
    database: "marketprism_test"
    
  redis:
    host: "localhost"
    port: 6379
    db: 1  # 测试专用数据库
```

### 测试框架使用
```python
# 使用真实测试基础类
from tests.tdd_framework.real_test_base import RealTestBase, real_test_environment

class TestMarketDataCollector(RealTestBase):
    
    @pytest.mark.asyncio
    async def test_binance_real_connection(self):
        """TDD: 测试真实Binance连接"""
        async with real_test_environment() as env:
            # 这里写具体的测试逻辑
            pass
```

### 测试数据管理
```python
# 测试数据生命周期
def setup_test_data():
    """准备测试数据"""
    pass

def cleanup_test_data():
    """清理测试数据"""
    pass

def verify_test_data_integrity():
    """验证测试数据完整性"""
    pass
```

## 📊 TDD 执行计划

### Week 1: 基础服务验证
- [ ] 设置TDD测试环境和代理配置
- [ ] 实现数据存储服务真实性测试
- [ ] 实现市场数据采集真实性测试
- [ ] 实现API网关真实路由测试
- [ ] 验证所有基础服务可以真实工作

### Week 2: 集成流程验证
- [ ] 实现端到端数据流测试
- [ ] 实现性能压力测试
- [ ] 验证服务间真实通信
- [ ] 测试错误恢复机制

### Week 3: 生产场景测试
- [ ] 实现高可用性测试
- [ ] 实现数据一致性测试
- [ ] 模拟复杂故障场景
- [ ] 验证系统稳定性

### Week 4: 安全监控测试
- [ ] 实现安全性测试
- [ ] 实现监控告警测试
- [ ] 性能基准建立
- [ ] 最终集成验证

## 🎯 TDD 成功标准

### 功能指标
- ✅ 所有微服务可以连接真实外部服务
- ✅ 端到端数据流正常工作
- ✅ 错误处理和恢复机制有效
- ✅ 性能满足预期要求

### 质量指标
- ✅ 测试覆盖率 > 90%
- ✅ 所有测试使用真实环境
- ✅ 测试执行时间 < 30分钟
- ✅ 零Mock依赖

### 生产就绪指标
- ✅ 系统可以连续运行24小时无故障
- ✅ 响应时间 < 100ms (P95)
- ✅ 吞吐量 > 1000 req/s
- ✅ 内存使用稳定无泄漏

## 🚀 快速开始

### 1. 环境准备
```bash
# 配置代理
export HTTP_PROXY=http://127.0.0.1:7890
export HTTPS_PROXY=http://127.0.0.1:7890

# 安装测试依赖
pip install -r requirements-test.txt

# 启动基础设施
docker-compose -f docker-compose-test.yml up -d
```

### 2. 运行TDD测试
```bash
# 测试环境验证
python tests/tdd_framework/real_test_base.py

# 运行第一个TDD测试
pytest tests/tdd/test_data_storage_real.py -v

# 运行完整TDD测试套件
pytest tests/tdd/ -v --tb=short
```

### 3. 查看测试报告
```bash
# 生成覆盖率报告
pytest --cov=services tests/tdd/

# 生成HTML报告
pytest --html=reports/tdd_report.html
```

## 📝 TDD 最佳实践

### 编写测试的原则
1. **描述清晰**：每个测试都有明确的业务含义
2. **独立性**：测试之间不相互依赖
3. **可重复**：同样的测试多次运行结果一致
4. **快速反馈**：测试运行时间尽可能短

### 测试命名规范
```python
def test_should_connect_to_real_binance_when_proxy_configured():
    """
    测试：配置代理后应该能连接到真实Binance
    Given: 代理已配置
    When: 尝试连接Binance Testnet
    Then: 连接应该成功
    """
    pass
```

### 错误处理策略
```python
def test_should_retry_when_network_temporarily_fails():
    """
    测试：网络临时故障时应该重试
    """
    # 模拟网络故障
    # 验证重试机制
    # 确认最终成功
    pass
```

---

**🎯 TDD目标**：通过真实环境测试，确保MarketPrism微服务架构在生产环境中稳定可靠运行