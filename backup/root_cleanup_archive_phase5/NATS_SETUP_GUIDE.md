
🚀 MarketPrism NATS 设置指南

## 1. 安装NATS服务器

### 方法1: 使用Homebrew (推荐)
```bash
brew install nats-server
```

### 方法2: 使用Go
```bash
go install github.com/nats-io/nats-server/v2@latest
```

### 方法3: 下载二进制文件
访问: https://github.com/nats-io/nats-server/releases

## 2. 启动NATS服务器

### 基础启动 (开发环境)
```bash
nats-server
```

### 启用JetStream (推荐)
```bash
nats-server -js
```

### 使用配置文件启动
```bash
nats-server -c nats-server.conf
```

## 3. 验证NATS服务

### 检查服务状态
```bash
# 检查端口
lsof -i :4222

# 使用NATS CLI工具
nats server info
```

### Python客户端测试
```python
import asyncio
import nats

async def test():
    nc = await nats.connect("nats://localhost:4222")
    print("NATS连接成功!")
    await nc.close()

asyncio.run(test())
```

## 4. 配置JetStream流

项目配置了以下流:
- BINANCE_TRADES (binance.trade.*)
- BINANCE_ORDERBOOK (binance.orderbook.*)  
- OKX_TRADES (okx.trade.*)
- DERIBIT_TRADES (deribit.trade.*)

## 5. Docker方式运行NATS

```bash
# 启动NATS服务器
docker run -p 4222:4222 -p 8222:8222 nats:latest -js

# 使用docker-compose
# 在docker-compose.yml中添加:
# services:
#   nats:
#     image: nats:latest
#     ports:
#       - "4222:4222"
#       - "8222:8222"
#     command: ["-js"]
```

## 6. 常见问题

❓ 连接被拒绝 (Connection refused)
解决: 确保NATS服务器正在运行

❓ JetStream不可用
解决: 启动时使用 -js 参数

❓ 流不存在
解决: 确保启用JetStream并创建流

## 7. 生产环境建议

- 使用持久化存储
- 配置集群模式
- 设置监控和日志
- 使用认证和TLS
