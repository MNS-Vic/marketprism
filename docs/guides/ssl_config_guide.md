# MarketPrism SSL配置指南

本文档详细说明如何为MarketPrism项目的各组件配置SSL安全通信。

## 生成证书

首先，运行证书生成脚本：

```bash
# 添加执行权限
chmod +x scripts/generate_ssl_certs.sh

# 运行生成脚本
./scripts/generate_ssl_certs.sh
```

## 各组件SSL配置

### 1. ClickHouse配置

修改 `docker-compose.yml` 中ClickHouse服务部分：

```yaml
clickhouse:
  # ... 现有配置 ...
  volumes:
    # ... 现有挂载 ...
    - ./ssl-certs/clickhouse:/etc/clickhouse-server/ssl
  command:
    - "--config-file=/etc/clickhouse-server/config.xml"
    - "--ssl_cert_file=/etc/clickhouse-server/ssl/cert.pem"
    - "--ssl_key_file=/etc/clickhouse-server/ssl/key.pem"
    - "--ssl_ca_file=/etc/clickhouse-server/ssl/ca-cert.pem"
  ports:
    - "8123:8123"  # HTTP接口
    - "9000:9000"  # 原TCP接口
    - "9440:9440"  # 安全TCP接口
```

分布式部署时，修改 `docker-compose.hot.yml` 和 `docker-compose.cold.yml` 文件。

修改 `config/storage_policy.yaml`：

```yaml
storage:
  hot_storage:
    # ... 现有配置 ...
    port: 9440  # 改为安全端口
    secure: true
    ssl_ca_file: "/app/ssl-certs/clickhouse/ca-cert.pem"  # 容器内路径
  
  cold_storage:
    # ... 现有配置 ...
    port: 9440  # 改为安全端口
    secure: true
    ssl_ca_file: "/app/ssl-certs/clickhouse/ca-cert.pem"  # 容器内路径
```

### 2. NATS配置

修改 `docker-compose.yml` 中NATS服务部分：

```yaml
nats:
  # ... 现有配置 ...
  command:
    - "--jetstream"
    - "--http_port=8222"
    - "--tls"
    - "--tlscert=/etc/nats/ssl/cert.pem"
    - "--tlskey=/etc/nats/ssl/key.pem"
    - "--tlscacert=/etc/nats/ssl/ca-cert.pem"
    - "--tlsverify"
  volumes:
    # ... 现有卷 ...
    - ./ssl-certs/nats:/etc/nats/ssl
```

在所有NATS客户端配置中添加SSL相关设置，修改 `config/nats_base.yaml`：

```yaml
nats:
  url: "tls://nats:4222"  # 使用tls://前缀
  ssl:
    enabled: true
    ca_file: "/app/ssl-certs/nats/ca-cert.pem"
    cert_file: "/app/ssl-certs/nats/cert.pem"
    key_file: "/app/ssl-certs/nats/key.pem"
    verify: true
```

### 3. Go数据收集器配置

修改 `services/go-collector` 的 `Dockerfile`，增加证书复制：

```dockerfile
# ... 现有内容 ...

# 创建证书目录
RUN mkdir -p /app/ssl-certs/nats /app/ssl-certs/clickhouse

# 复制应用代码
COPY . .

# 取消注释下面两行以在构建时包含证书（小心！通常建议在运行时挂载）
# COPY ./ssl-certs/nats/*.pem /app/ssl-certs/nats/
# COPY ./ssl-certs/clickhouse/*.pem /app/ssl-certs/clickhouse/

# ... 现有内容 ...
```

修改 `docker-compose.yml` 中go-collector服务部分：

```yaml
go-collector:
  # ... 现有配置 ...
  volumes:
    # ... 现有卷 ...
    - ./ssl-certs/nats:/app/ssl-certs/nats
    - ./ssl-certs/clickhouse:/app/ssl-certs/clickhouse
```

### 4. 数据接收服务配置

修改 `docker-compose.yml` 中data-ingestion服务部分：

```yaml
data-ingestion:
  # ... 现有配置 ...
  volumes:
    # ... 现有卷 ...
    - ./ssl-certs/nats:/app/ssl-certs/nats
    - ./ssl-certs/clickhouse:/app/ssl-certs/clickhouse
```

### 5. 数据归档服务配置

修改 `docker-compose.yml` 中data-archiver服务部分（如有）：

```yaml
data-archiver:
  # ... 现有配置 ...
  volumes:
    # ... 现有卷 ...
    - ./ssl-certs/clickhouse:/app/ssl-certs/clickhouse
```

## 如何验证SSL配置是否正确

1. 验证NATS SSL连接：

```bash
./ssl-certs/test_ssl_connection.sh nats localhost 4222
```

2. 验证ClickHouse SSL连接：

```bash
./ssl-certs/test_ssl_connection.sh clickhouse localhost 9440
```

## 常见问题排查

### 1. 连接被拒绝

- 检查端口是否正确（NATS: 4222, ClickHouse: 9440）
- 确认相应服务已启用SSL
- 检查防火墙设置

### 2. 证书验证失败

- 确保使用了正确的CA证书
- 确认服务器名称匹配证书中的CN或SAN
- 检查证书是否过期

### 3. 文件路径错误

- 确认容器内的证书路径是否正确
- 检查卷挂载是否正确配置

## 安全最佳实践

1. **定期更新证书**：证书有效期为1年，建议提前1个月更新
2. **保护私钥**：严格限制私钥文件访问权限
3. **监控SSL连接**：定期检查服务日志中的SSL握手错误
4. **计划证书轮换**：提前规划好证书更新流程，避免证书过期导致服务中断 