# MarketPrism TDD 真实环境测试

本目录包含MarketPrism微服务架构的TDD（测试驱动开发）测试套件，专注于真实环境验证。

## 🎯 TDD核心理念

### 测试先行原则
1. **红灯（Red）**：先写测试，描述期望的行为，运行测试应该失败
2. **绿灯（Green）**：实现最小代码，使测试通过
3. **重构（Refactor）**：在测试保护下优化代码结构

### 真实环境测试
- ❌ **不使用Mock**：所有测试连接真实的外部服务
- ✅ **真实API连接**：直接连接Binance、OKX等真实交易所API
- ✅ **真实数据库**：使用真实的Redis、ClickHouse实例
- ✅ **真实网络**：通过代理连接互联网服务

## 📁 测试文件结构

```
tests/tdd/
├── README.md                              # 本文档
├── test_real_data_storage.py              # 数据存储服务真实性测试
├── test_real_market_data_collector.py     # 市场数据采集真实性测试
├── test_real_api_gateway.py               # API网关真实性测试
├── test_real_monitoring.py                # 监控服务真实性测试
├── test_real_scheduler.py                 # 调度服务真实性测试
├── test_real_message_broker.py            # 消息代理真实性测试
├── test_real_integration.py               # 端到端集成测试
└── conftest.py                            # pytest配置和fixtures
```

## 🚀 快速开始

### 1. 环境准备

```bash
# 1. 安装测试依赖
pip install -r requirements-test.txt

# 2. 配置代理（如需要）
export HTTP_PROXY=http://127.0.0.1:7890
export HTTPS_PROXY=http://127.0.0.1:7890

# 3. 启动基础设施（Redis、ClickHouse）
# 确保Redis在localhost:6379运行
redis-server

# 确保ClickHouse可访问（如果使用）
```

### 2. 设置TDD测试环境

```bash
# 一键设置环境
python scripts/tdd_setup.py --setup

# 查看环境状态
python scripts/tdd_setup.py --status
```

### 3. 运行TDD测试

```bash
# 运行单个测试文件
python -m pytest tests/tdd/test_real_data_storage.py -v

# 运行所有TDD测试
python scripts/tdd_setup.py --test

# 运行特定模式的测试
python -m pytest tests/tdd/ -k "storage" -v

# 生成HTML测试报告
python -m pytest tests/tdd/ --html=reports/tdd_report.html
```

### 4. 清理环境

```bash
# 清理测试环境
python scripts/tdd_setup.py --cleanup
```

## 📋 测试分类

### 基础服务测试
- **数据存储服务**：Redis连接、数据存储、查询、热冷数据管理
- **市场数据采集**：交易所连接、数据规范化、多交易所支持
- **API网关**：路由转发、负载均衡、服务发现
- **监控服务**：指标收集、告警、健康检查
- **调度服务**：任务调度、定时执行、故障恢复
- **消息代理**：NATS连接、消息发布、流管理

### 集成测试
- **端到端数据流**：从数据采集到存储的完整流程
- **服务间通信**：微服务协作和消息传递
- **错误恢复**：网络中断、服务故障恢复
- **性能压力**：高并发、大数据量处理

### 生产场景测试
- **高可用性**：服务故障转移、自动恢复
- **数据一致性**：跨服务事务、数据同步
- **安全性**：认证授权、速率限制
- **监控告警**：实时监控、异常告警

## 🛠️ 测试配置

### 代理配置
```yaml
# config/test_config.yaml
proxy:
  enabled: true
  http_proxy: "http://127.0.0.1:7890"
  https_proxy: "http://127.0.0.1:7890"
  no_proxy: "localhost,127.0.0.1,::1"
```

### 交易所配置
```yaml
exchanges:
  binance:
    testnet: true
    base_url: "https://testnet.binance.vision"
    ws_url: "wss://testnet.binance.vision/ws"
    api_key: ""  # 测试网API密钥
    api_secret: ""
```

### 数据库配置
```yaml
databases:
  redis:
    host: "localhost"
    port: 6379
    db: 1  # 测试专用数据库
    
  clickhouse:
    host: "localhost"
    port: 8123
    database: "marketprism_test"
```

## 📊 测试示例

### 数据存储真实性测试
```python
@pytest.mark.asyncio
async def test_should_connect_to_real_redis_when_service_starts():
    """
    TDD测试：数据存储服务启动时应该连接到真实Redis
    
    Given: Redis服务在localhost:6379运行
    When: 启动数据存储服务
    Then: 应该成功连接到Redis并能执行基本操作
    """
    async with real_test_environment() as env:
        # 验证环境准备就绪
        assert env.databases_ready.get('redis', False)
        assert env.services_running.get('data_storage', False)
        
        # 测试真实Redis连接
        redis_client = redis.Redis(host='localhost', port=6379, db=1)
        ping_result = redis_client.ping()
        assert ping_result is True
```

### 市场数据采集真实性测试
```python
@pytest.mark.asyncio
async def test_should_connect_to_real_binance_testnet_with_proxy():
    """
    TDD测试：应该能通过代理连接到真实的Binance Testnet
    
    Given: 代理已配置，Binance Testnet可访问
    When: 启动市场数据采集服务
    Then: 应该成功连接Binance WebSocket并接收数据
    """
    async with real_test_environment() as env:
        assert env.proxy_configured
        assert env.services_running.get('market_data_collector', False)
        
        # 测试真实Binance连接
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://localhost:8081/api/v1/exchange/binance/status"
            ) as response:
                assert response.status == 200
                status_data = await response.json()
                assert status_data.get('connected', False)
```

## 🎯 测试最佳实践

### 命名规范
```python
def test_should_[expected_behavior]_when_[condition]():
    """
    测试：[业务描述]
    
    Given: [前置条件]
    When: [触发动作]
    Then: [期望结果]
    """
```

### 断言策略
```python
# 具体的错误信息
assert response.status == 200, f"请求失败: {response.status}"

# 业务逻辑验证
assert data.get('success', False), f"业务处理失败: {data}"

# 数据完整性检查
assert 'price' in market_data, "市场数据缺少price字段"
```

### 清理策略
```python
async def test_with_cleanup():
    test_data = await setup_test_data()
    try:
        # 执行测试逻辑
        result = await perform_test(test_data)
        assert result.success
    finally:
        # 确保清理测试数据
        await cleanup_test_data(test_data)
```

## ⚡ 性能要求

### 测试执行时间
- 单个测试：< 30秒
- 完整测试套件：< 10分钟
- 集成测试：< 5分钟

### 资源使用
- 内存：< 2GB
- CPU：< 80%
- 网络：合理使用，遵守API限制

### 并发支持
- 支持多个测试并行执行
- 数据隔离避免测试冲突
- 资源竞争检测和处理

## 🐛 故障排查

### 常见问题

1. **Redis连接失败**
   ```bash
   # 检查Redis状态
   redis-cli ping
   
   # 启动Redis
   redis-server
   ```

2. **代理连接问题**
   ```bash
   # 检查代理设置
   echo $HTTP_PROXY
   
   # 测试代理连接
   curl --proxy $HTTP_PROXY https://httpbin.org/ip
   ```

3. **服务启动失败**
   ```bash
   # 检查端口占用
   lsof -i :8080
   
   # 查看服务日志
   python services/api-gateway-service/main.py
   ```

4. **测试数据污染**
   ```bash
   # 清理Redis测试数据
   redis-cli -n 1 FLUSHDB
   
   # 重置测试环境
   python scripts/tdd_setup.py --cleanup
   python scripts/tdd_setup.py --setup
   ```

### 调试技巧

```python
# 启用详细日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 测试暂停点
import pdb; pdb.set_trace()

# 异步调试
import asyncio
await asyncio.sleep(0)  # 暂停点
```

## 📈 测试指标

### 覆盖率目标
- 单元测试：> 90%
- 集成测试：> 80%
- 端到端测试：> 70%

### 质量标准
- ✅ 所有测试使用真实环境
- ✅ 零Mock依赖
- ✅ 测试独立性
- ✅ 错误处理覆盖

### 成功标准
- ✅ 连续运行24小时无故障
- ✅ 响应时间P95 < 100ms
- ✅ 吞吐量 > 1000 req/s
- ✅ 内存使用稳定无泄漏

---

**🎯 目标**：通过TDD真实环境测试，确保MarketPrism微服务架构在生产环境中稳定可靠运行