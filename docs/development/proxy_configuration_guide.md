# MarketPrism 代理配置指南

## 概述

MarketPrism支持在需要代理的网络环境中运行，特别是在访问国外交易所API时。本指南详细说明了如何配置不同类型的代理以及如何针对不同场景进行优化。

## 支持的代理类型

### 1. HTTP/HTTPS代理

适用于REST API调用，大多数代理软件都支持。

```bash
export HTTP_PROXY=http://127.0.0.1:1087
export HTTPS_PROXY=http://127.0.0.1:1087
export NO_PROXY=localhost,127.0.0.1
```

### 2. SOCKS代理

适用于WebSocket连接，通常提供更好的性能和更广泛的协议支持。

```bash
export ALL_PROXY=socks5://127.0.0.1:1080
export NO_PROXY=localhost,127.0.0.1
```

### 3. 混合代理配置

对于复杂的网络环境，可以为不同的协议配置不同的代理：

```bash
# REST API使用HTTP代理
export HTTP_PROXY=http://127.0.0.1:1087
export HTTPS_PROXY=http://127.0.0.1:1087

# WebSocket使用SOCKS代理
export ALL_PROXY=socks5://127.0.0.1:1080

# 本地地址不使用代理
export NO_PROXY=localhost,127.0.0.1,*.local
```

## 测试结果分析

基于我们的实际测试，以下是各种代理配置的性能表现：

### Binance交易所

| 代理类型 | REST API | WebSocket | 推荐度 |
|---------|----------|-----------|--------|
| HTTP代理 | ✅ 0.745s | ✅ 0.798s (3条消息) | ⭐⭐⭐⭐ |
| SOCKS代理 | ✅ 0.774s | ✅ 1.160s (3条消息) | ⭐⭐⭐⭐⭐ |
| 直连 | ❌ 超时 | ❌ 超时 | ❌ |

### OKX交易所

| 代理类型 | REST API | WebSocket | 推荐度 |
|---------|----------|-----------|--------|
| HTTP代理 | ✅ 0.729s | ✅ 0.799s | ⭐⭐⭐⭐ |
| SOCKS代理 | ✅ 0.450s | ✅ 0.534s | ⭐⭐⭐⭐⭐ |
| 直连 | ❌ 超时 | ✅ 1.139s | ⭐ |

### 性能分析

1. **SOCKS代理表现最佳**：特别是对OKX交易所，SOCKS代理的响应时间显著优于HTTP代理
2. **WebSocket连接稳定性好**：所有代理配置下WebSocket连接都很稳定
3. **直连不可行**：在当前网络环境下，直连无法访问交易所API

## 推荐配置

### 1. 最佳性能配置（推荐）

```bash
# 优先使用SOCKS代理，获得最佳性能
export ALL_PROXY=socks5://127.0.0.1:1080
export HTTP_PROXY=http://127.0.0.1:1087
export HTTPS_PROXY=http://127.0.0.1:1087
export NO_PROXY=localhost,127.0.0.1
```

### 2. 高可靠性配置

```bash
# 主要使用HTTP代理，备用SOCKS代理
export HTTP_PROXY=http://127.0.0.1:1087
export HTTPS_PROXY=http://127.0.0.1:1087
export ALL_PROXY=socks5://127.0.0.1:1080
export NO_PROXY=localhost,127.0.0.1
```

### 3. 混合优化配置

针对不同交易所使用不同代理（需要程序级别配置）：

- **Binance**: HTTP代理（稳定性好）
- **OKX**: SOCKS代理（性能最佳）

## 代理软件推荐

### 1. V2Ray/V2RayN

```bash
# 典型配置
export HTTP_PROXY=http://127.0.0.1:10809
export HTTPS_PROXY=http://127.0.0.1:10809
export ALL_PROXY=socks5://127.0.0.1:10808
```

### 2. Clash

```bash
# 典型配置
export HTTP_PROXY=http://127.0.0.1:7890
export HTTPS_PROXY=http://127.0.0.1:7890
export ALL_PROXY=socks5://127.0.0.1:7891
```

### 3. Shadowsocks

```bash
# 典型配置
export ALL_PROXY=socks5://127.0.0.1:1080
```

## 程序级配置

### Python Collector配置

在`config/development.yaml`中配置：

```yaml
proxy:
  enabled: true
  http_proxy: "http://127.0.0.1:1087"
  https_proxy: "http://127.0.0.1:1087"
  no_proxy: "localhost,127.0.0.1"

# 环境变量会自动覆盖配置文件
```

### REST客户端配置

```python
from marketprism_collector.rest_client import RestClientConfig

# 创建带代理的REST客户端配置
config = RestClientConfig(
    base_url="https://api.binance.com",
    proxy="http://127.0.0.1:1087",  # 为特定客户端设置代理
    timeout=30
)
```

### WebSocket适配器配置

WebSocket连接会自动检测环境变量中的代理设置：

1. 优先使用`ALL_PROXY`（SOCKS代理）
2. 其次使用`HTTPS_PROXY`或`HTTP_PROXY`
3. 最后尝试直连

## 测试和验证

### 1. 快速代理测试

```bash
# 运行代理配置测试
python test_proxy_simple.py
```

### 2. 特定交易所测试

```bash
# 测试OKX交易所
python test_proxy_okx.py
```

### 3. 集成测试

```bash
# 运行完整的真实API集成测试
python -m pytest tests/integration/test_real_api_integration.py -v
```

## 故障排除

### 常见问题

1. **连接超时**
   - 检查代理软件是否正常运行
   - 验证代理端口是否正确
   - 确认代理协议类型（HTTP vs SOCKS）

2. **部分API可访问，部分不可访问**
   - 检查`NO_PROXY`设置，确保本地服务不走代理
   - 验证不同协议的代理配置

3. **WebSocket连接失败**
   - 优先尝试SOCKS代理
   - 检查代理软件是否支持WebSocket协议

### 调试方法

1. **查看当前代理设置**
```bash
env | grep -i proxy
```

2. **测试代理连通性**
```bash
curl -x http://127.0.0.1:1087 https://api.binance.com/api/v3/ping
```

3. **查看应用日志**
```bash
tail -f logs/collector.log | grep -i proxy
```

## 性能优化建议

### 1. 选择最快的代理

基于测试结果，针对不同交易所选择性能最佳的代理：

- **OKX**: 优先使用SOCKS代理（响应时间快50%+）
- **Binance**: HTTP和SOCKS代理性能相近，选择稳定性更好的

### 2. 连接池优化

```python
# REST客户端连接池配置
config = RestClientConfig(
    max_connections=100,
    max_connections_per_host=30,
    keepalive_timeout=30
)
```

### 3. 超时设置

```python
# 针对代理环境调整超时设置
config = RestClientConfig(
    timeout=30,  # 代理环境下适当增加超时时间
    max_retries=3,
    retry_delay=1.0
)
```

## 安全考虑

1. **代理认证**：如果代理需要认证，在URL中包含用户名密码
2. **本地代理**：建议使用本地代理软件，避免网络传输敏感信息
3. **流量加密**：使用支持加密的代理协议
4. **访问控制**：合理配置`NO_PROXY`，避免内网流量走代理

## 总结

基于实际测试，我们推荐以下代理配置策略：

1. **生产环境**：使用SOCKS代理+HTTP代理的混合配置，获得最佳性能和兼容性
2. **开发环境**：根据本地代理软件类型进行配置
3. **测试环境**：支持快速切换不同代理配置进行测试

通过正确配置代理，MarketPrism可以在任何网络环境中稳定运行，实现与各大交易所的可靠连接。 