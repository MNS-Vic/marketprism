# MarketPrism 一键部署指南

## 📋 目录

- [系统要求](#系统要求)
- [快速开始](#快速开始)
- [详细步骤](#详细步骤)
- [配置说明](#配置说明)
- [故障排查](#故障排查)
- [常见问题](#常见问题)

---

## 🖥️ 系统要求

### 硬件要求
- **CPU**: 2核心以上
- **内存**: 4GB 以上（推荐 8GB）
- **磁盘**: 20GB 以上可用空间

### 操作系统
- Ubuntu 20.04+ / Debian 11+
- CentOS 8+ / RHEL 8+
- macOS 12+ (Monterey)

### 软件要求
- **必需**:
  - curl 或 wget
  - git
  - sudo 权限

- **自动安装**（脚本会自动安装）:
  - NATS Server v2.10.7
  - ClickHouse v25.10.1
  - Python 3.9+
  - 所有 Python 依赖

---

## 🚀 快速开始

### 方式一：全新部署（推荐用于新主机）

```bash
# 1. 克隆项目
git clone https://github.com/MNS-Vic/marketprism.git
cd marketprism

# 2. 一键部署
./scripts/one_click_deploy.sh --fresh

# 3. 等待部署完成（约 5-10 分钟）
# 脚本会自动完成所有安装和配置
```

### 方式二：更新部署（保留数据）

```bash
cd marketprism
git pull
./scripts/one_click_deploy.sh --update
```

### 方式三：使用 Docker 模式

```bash
./scripts/one_click_deploy.sh --fresh --docker-mode
```

---

## 📝 详细步骤

### 第1步：环境检测

脚本会自动检测：
- ✅ 操作系统类型和版本
- ✅ 系统内存和磁盘空间
- ✅ sudo 权限
- ✅ 必要工具（curl、wget、git）

### 第2步：依赖安装

脚本会自动安装：
- ✅ NATS Server（消息代理）
- ✅ ClickHouse（数据库）
- ✅ Python 虚拟环境
- ✅ 所有 Python 依赖包

**跳过依赖安装**（如果已安装）：
```bash
./scripts/one_click_deploy.sh --fresh --skip-deps
```

### 第3步：启动基础服务

脚本会自动启动：
- ✅ NATS Server（端口 4222, 8222）
- ✅ ClickHouse Server（端口 8123, 9000）

### 第4步：初始化数据库和流

脚本会自动：
- ✅ 创建 ClickHouse 数据库和表
- ✅ 初始化 NATS JetStream 流
- ✅ 配置数据路由规则

### 第5步：启动应用服务

脚本会自动启动：
- ✅ 数据存储服务（热端，端口 8085）
- ✅ 数据采集器（从交易所采集数据）

### 第6步：健康检查

脚本会自动验证：
- ✅ 所有服务是否正常运行
- ✅ 端口是否正常监听
- ✅ 数据流是否正常

### 第7步：部署报告

脚本会显示：
- ✅ 服务访问地址
- ✅ 管理命令
- ✅ 日志文件位置
- ✅ 数据查询示例

---

## ⚙️ 配置说明

### 环境变量配置

1. 复制配置模板：
```bash
cp .env.example .env
```

2. 编辑配置文件：
```bash
vim .env
```

3. 主要配置项：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `ENVIRONMENT` | 环境类型 | `production` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `NATS_URL` | NATS 服务器地址 | `nats://localhost:4222` |
| `CLICKHOUSE_HTTP_PORT` | ClickHouse HTTP 端口 | `8123` |
| `HEALTH_CHECK_PORT` | 健康检查端口 | `8087` |
| `HOT_STORAGE_PORT` | 热端存储端口 | `8085` |

### 交易所 API 配置（可选）

如果需要访问私有 API（如账户数据），需要配置 API 密钥：

```bash
# Binance
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret

# OKX
OKX_API_KEY=your_api_key
OKX_API_SECRET=your_api_secret
OKX_PASSPHRASE=your_passphrase

# Deribit
DERIBIT_API_KEY=your_api_key
DERIBIT_API_SECRET=your_api_secret
```

**注意**: 公开市场数据不需要 API 密钥。

---

## 🔍 验证部署

### 1. 检查服务状态

```bash
./scripts/manage_all.sh status
```

### 2. 健康检查

```bash
./scripts/manage_all.sh health
```

### 3. 查看数据

```bash
# 查看交易记录数量
clickhouse-client --query "SELECT count(*) FROM marketprism_hot.trades"

# 查看最新数据
clickhouse-client --query "SELECT * FROM marketprism_hot.trades ORDER BY timestamp DESC LIMIT 10"

# 查看数据分布
clickhouse-client --query "SELECT exchange, symbol, count(*) FROM marketprism_hot.trades GROUP BY exchange, symbol"
```

### 4. 查看日志

```bash
# NATS 日志
tail -f /tmp/nats-server.log

# 存储服务日志
tail -f /tmp/storage-hot.log

# 数据采集器日志
tail -f /tmp/collector.log

# 部署日志
tail -f deployment.log
```

---

## 🛠️ 管理命令

### 启动服务

```bash
./scripts/manage_all.sh start
```

### 停止服务

```bash
./scripts/manage_all.sh stop
```

### 重启服务

```bash
./scripts/manage_all.sh restart
```

### 查看状态

```bash
./scripts/manage_all.sh status
```

### 健康检查

```bash
./scripts/manage_all.sh health
```

### 清理资源

```bash
./scripts/one_click_deploy.sh --clean
```

---

## 🐛 故障排查

### 问题1：NATS Server 启动失败

**症状**: 端口 4222 或 8222 无法访问

**解决方案**:
```bash
# 检查端口占用
ss -ltnp | grep -E "(4222|8222)"

# 杀死占用进程
pkill -x nats-server

# 重新启动
nats-server -js -m 8222 -p 4222 --store_dir /tmp/nats-jetstream &
```

### 问题2：ClickHouse 启动失败

**症状**: 端口 8123 或 9000 无法访问

**解决方案**:
```bash
# 检查 ClickHouse 状态
sudo clickhouse status

# 重启 ClickHouse
sudo clickhouse restart

# 查看日志
sudo tail -f /var/log/clickhouse-server/clickhouse-server.log
```

### 问题3：数据采集器无数据

**症状**: ClickHouse 中没有数据

**解决方案**:
```bash
# 检查采集器进程
pgrep -f services/data-collector/main.py

# 查看采集器日志
tail -f /tmp/collector.log

# 检查 NATS 消息
curl -s http://localhost:8222/jsz | jq '.streams'

# 重启采集器
pkill -f services/data-collector/main.py
cd services/data-collector
source ../../venv/bin/activate
HEALTH_CHECK_PORT=8087 python main.py --mode launcher &
```

### 问题4：Binance API 451 错误

**症状**: 日志中出现 HTTP 451 错误

**原因**: Binance 地理限制

**解决方案**:
- 使用 VPN 或代理
- 或者只使用 OKX 和 Deribit 数据

### 问题5：内存不足

**症状**: 服务频繁崩溃或重启

**解决方案**:
```bash
# 增加系统交换空间
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 或者减少并发连接数
# 编辑 .env 文件
MAX_CONCURRENT_CONNECTIONS=50
```

---

## ❓ 常见问题

### Q1: 部署需要多长时间？

**A**: 通常 5-10 分钟，取决于网络速度和系统性能。

### Q2: 可以在虚拟机上部署吗？

**A**: 可以，但建议至少分配 4GB 内存。

### Q3: 支持 ARM 架构吗？

**A**: 支持，脚本会自动检测架构并下载对应版本。

### Q4: 如何升级到新版本？

**A**: 
```bash
git pull
./scripts/one_click_deploy.sh --update
```

### Q5: 如何完全卸载？

**A**:
```bash
./scripts/one_click_deploy.sh --clean
sudo apt-get remove clickhouse-server clickhouse-client  # Ubuntu
sudo rm /usr/local/bin/nats-server
rm -rf venv
```

### Q6: 数据会保存多久？

**A**: 
- 热端数据：默认 7 天
- 冷端数据：默认 365 天
- 可在 `.env` 文件中配置

### Q7: 如何备份数据？

**A**:
```bash
# 备份 ClickHouse 数据
clickhouse-client --query "BACKUP DATABASE marketprism_hot TO Disk('backups', 'backup.zip')"

# 备份 NATS 数据
tar -czf nats-backup.tar.gz /tmp/nats-jetstream
```

---

## 📞 获取帮助

- **GitHub Issues**: https://github.com/MNS-Vic/marketprism/issues
- **文档**: https://github.com/MNS-Vic/marketprism/tree/main/docs
- **日志文件**: `deployment.log`

---

## 🎯 下一步

部署成功后，你可以：

1. **查看实时数据**: 访问 http://localhost:8222 查看 NATS 监控
2. **查询数据**: 使用 ClickHouse 客户端查询数据
3. **配置监控**: 设置 Prometheus 和 Grafana
4. **自定义采集**: 修改配置文件添加更多交易对
5. **开发应用**: 使用 MarketPrism 数据开发交易策略

祝你使用愉快！🚀

