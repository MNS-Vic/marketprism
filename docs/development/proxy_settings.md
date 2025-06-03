# 代理设置指南

本文档介绍如何在MarketPrism项目中配置和使用代理，特别是在访问外部API时（如币安WebSocket）。

## 使用场景

在以下情况下需要配置代理：

1. 开发环境中无法直接访问外部API
2. 位于防火墙/网络限制区域内
3. 需要稳定连接到国际服务器

## 配置方法

### 1. 本地开发环境变量设置（推荐）

在本地开发时，需要设置以下环境变量来连接代理：

```bash
# 设置HTTP/HTTPS代理
export http_proxy=http://127.0.0.1:1087
export https_proxy=http://127.0.0.1:1087

# 设置SOCKS5代理（用于WebSocket等连接）
export ALL_PROXY=socks5://127.0.0.1:1080

# 设置不使用代理的地址
export no_proxy=localhost,127.0.0.1
```

**一键设置命令**：
```bash
export http_proxy=http://127.0.0.1:1087;export https_proxy=http://127.0.0.1:1087;export ALL_PROXY=socks5://127.0.0.1:1080
```

> 💡 **重要提示**：这些环境变量设置对于本地开发访问外部交易所API（如Binance、OKX、Deribit）是必需的。

### 2. 配置文件中设置代理

在`config/nats_base.yaml`（或您的自定义配置文件）中添加以下配置：

```yaml
# 代理配置
proxy:
  enabled: true  # 是否启用代理
  http_proxy: "http://127.0.0.1:1087"  # HTTP代理
  https_proxy: "http://127.0.0.1:1087"  # HTTPS代理
  no_proxy: "localhost,127.0.0.1,nats,clickhouse"  # 不使用代理的地址
  connect_timeout: 30  # 连接超时(秒)
  read_timeout: 30    # 读取超时(秒)
```

### 3. Docker环境变量中设置代理

在`docker-compose.yml`中添加环境变量：

```yaml
environment:
  - HTTP_PROXY=http://127.0.0.1:1087
  - HTTPS_PROXY=http://127.0.0.1:1087
  - ALL_PROXY=socks5://127.0.0.1:1080
  - NO_PROXY=localhost,127.0.0.1,nats,clickhouse
```

### 4. Docker网络设置

对于开发环境，为了让Docker容器能够访问宿主机的代理服务，请在`docker-compose.yml`中为相关服务添加：

```yaml
network_mode: "host"
```

> ⚠️ 注意：`network_mode: "host"`设置与`ports`映射、`networks`和某些`extra_hosts`设置不兼容。如果使用host网络模式，需要注释掉这些设置。

## 开发环境与生产环境切换

我们提供了两个示例配置文件：

1. **开发环境**: `docker-compose.yml` + `config/nats_base.yaml`
   - 启用代理
   - 使用host网络模式
   - 设置DEV_MODE环境变量

2. **生产环境**: `docker-compose.prod.yml` + `config/nats_prod.yaml`
   - 禁用代理
   - 使用普通容器网络
   - 禁用DEV_MODE

### 切换到生产环境

```bash
# 使用生产环境配置启动服务
docker-compose -f docker-compose.prod.yml up -d
```

## 测试代理连接

您可以使用项目根目录中的测试脚本来验证代理是否正常工作：

```bash
python test_proxy.py
```

如果代理正常工作，您将看到成功连接的消息。

## 常见问题排查

### 容器无法访问宿主机的代理

1. 确认宿主机的代理服务允许来自Docker网络的连接
2. 检查代理软件是否仅监听`127.0.0.1`而不是`0.0.0.0`
3. 尝试使用`network_mode: "host"`让容器直接使用宿主机网络

### 代理连接超时

1. 验证代理服务器是否正常运行
2. 测试代理能否访问目标服务器
3. 检查防火墙设置

### WebSocket连接失败但HTTP连接正常

有些代理服务器可能不支持WebSocket协议，或需要特定配置。检查代理服务器的WebSocket支持情况。

## 安全考虑

在生产环境中，建议：

1. 禁用代理设置，直接连接外部API
2. 如必须使用代理，确保使用安全的代理服务器
3. 限制代理的作用范围，只为必要的服务配置代理 