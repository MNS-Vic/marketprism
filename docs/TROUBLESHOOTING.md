# MarketPrism 故障排查指南

## 📋 目录

- [部署问题](#部署问题)
- [服务问题](#服务问题)
- [数据问题](#数据问题)
- [性能问题](#性能问题)
- [网络问题](#网络问题)

---

## 🔧 部署问题

### 问题：脚本执行权限不足

**错误信息**:
```
Permission denied: ./scripts/one_click_deploy.sh
```

**解决方案**:
```bash
chmod +x scripts/one_click_deploy.sh
./scripts/one_click_deploy.sh --fresh
```

---

### 问题：缺少 sudo 权限

**错误信息**:
```
sudo: command not found
或
user is not in the sudoers file
```

**解决方案**:
```bash
# 方式1：使用 root 用户
su -
cd /path/to/marketprism
./scripts/one_click_deploy.sh --fresh

# 方式2：添加用户到 sudoers
su -
usermod -aG sudo your_username
```

---

### 问题：Python 版本过低

**错误信息**:
```
Python 3.9+ required
```

**解决方案**:
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install python3.9 python3.9-venv

# CentOS/RHEL
sudo yum install python39

# macOS
brew install python@3.9
```

---

## 🚦 服务问题

### 问题：NATS Server 无法启动

**症状**: 端口 4222 或 8222 无法访问

**诊断步骤**:
```bash
# 1. 检查进程
pgrep -x nats-server

# 2. 检查端口
ss -ltnp | grep -E "(4222|8222)"

# 3. 查看日志
tail -f /tmp/nats-server.log
```

**解决方案**:
```bash
# 杀死旧进程
pkill -x nats-server

# 清理数据目录
rm -rf /tmp/nats-jetstream

# 重新启动
nats-server -js -m 8222 -p 4222 --store_dir /tmp/nats-jetstream > /tmp/nats-server.log 2>&1 &

# 验证启动
curl http://localhost:8222/healthz
```

---

### 问题：ClickHouse 无法启动

**症状**: 端口 8123 或 9000 无法访问

**诊断步骤**:
```bash
# 1. 检查状态
sudo clickhouse status

# 2. 查看日志
sudo tail -f /var/log/clickhouse-server/clickhouse-server.log

# 3. 检查配置
sudo clickhouse-server --config-file=/etc/clickhouse-server/config.xml --test
```

**解决方案**:
```bash
# 重启服务
sudo clickhouse restart

# 如果失败，尝试完全重装
sudo apt-get remove --purge clickhouse-server clickhouse-client
curl https://clickhouse.com/ | sh
sudo ./clickhouse install
sudo clickhouse start
```

---

### 问题：存储服务启动失败

**症状**: 端口 8085 未监听

**诊断步骤**:
```bash
# 1. 检查进程
pgrep -f "data-storage-service.*main.py"

# 2. 查看日志
tail -f /tmp/storage-hot.log

# 3. 检查依赖
source venv/bin/activate
python -c "import aiohttp, clickhouse_driver, structlog"
```

**解决方案**:
```bash
# 重新安装依赖
source venv/bin/activate
pip install --upgrade aiohttp clickhouse-driver structlog

# 重启服务
pkill -f "data-storage-service.*main.py"
cd services/data-storage-service
python main.py --mode hot > /tmp/storage-hot.log 2>&1 &
```

---

### 问题：数据采集器启动失败

**症状**: 采集器进程不存在

**诊断步骤**:
```bash
# 1. 检查进程
pgrep -f "unified_collector_main.py"

# 2. 查看日志
tail -f /tmp/collector.log

# 3. 测试 NATS 连接
source venv/bin/activate
python -c "import nats; print('NATS module OK')"
```

**解决方案**:
```bash
# 重新安装依赖
source venv/bin/activate
pip install --upgrade nats-py websockets ccxt

# 重启采集器
pkill -f "unified_collector_main.py"
cd services/data-collector
HEALTH_CHECK_PORT=8087 METRICS_PORT=9093 python unified_collector_main.py --mode launcher > /tmp/collector.log 2>&1 &
```

---

## 📊 数据问题

### 问题：ClickHouse 中没有数据

**症状**: 查询返回 0 条记录

**诊断步骤**:
```bash
# 1. 检查表是否存在
clickhouse-client --query "SHOW TABLES FROM marketprism_hot"

# 2. 检查 NATS 消息
curl -s http://localhost:8222/jsz | jq '.streams'

# 3. 检查采集器日志
tail -f /tmp/collector.log | grep "发布成功"

# 4. 检查存储服务日志
tail -f /tmp/storage-hot.log | grep "写入成功"
```

**解决方案**:
```bash
# 1. 验证 NATS 有消息
curl -s http://localhost:8222/jsz | jq '.streams[] | {name: .name, messages: .state.messages}'

# 2. 如果 NATS 有消息但 ClickHouse 没有，重启存储服务
pkill -f "data-storage-service.*main.py"
cd services/data-storage-service
source ../../venv/bin/activate
python main.py --mode hot > /tmp/storage-hot.log 2>&1 &

# 3. 等待几分钟后再次查询
sleep 60
clickhouse-client --query "SELECT count(*) FROM marketprism_hot.trades"
```

---

### 问题：数据更新不及时

**症状**: 数据时间戳较旧

**诊断步骤**:
```bash
# 检查最新数据时间
clickhouse-client --query "SELECT max(timestamp) FROM marketprism_hot.trades"

# 检查采集器是否运行
pgrep -f "unified_collector_main.py"

# 检查 WebSocket 连接
tail -f /tmp/collector.log | grep "WebSocket"
```

**解决方案**:
```bash
# 重启采集器
pkill -f "unified_collector_main.py"
cd services/data-collector
source ../../venv/bin/activate
HEALTH_CHECK_PORT=8087 python unified_collector_main.py --mode launcher > /tmp/collector.log 2>&1 &
```

---

### 问题：订单簿数据为空

**症状**: `orderbooks` 表没有数据

**原因**: 订单簿数据存储消费者未启动

**解决方案**:
```bash
# 检查 ORDERBOOK_SNAP 流
curl -s http://localhost:8222/jsz | jq '.streams[] | select(.name=="ORDERBOOK_SNAP")'

# 启动订单簿存储消费者（需要实现）
# 这是一个已知问题，订单簿数据需要单独的消费者
```

---

## ⚡ 性能问题

### 问题：内存使用过高

**症状**: 系统内存不足，服务被 OOM Killer 杀死

**诊断步骤**:
```bash
# 检查内存使用
free -h

# 检查进程内存
ps aux --sort=-%mem | head -10

# 检查 ClickHouse 内存
clickhouse-client --query "SELECT * FROM system.metrics WHERE metric LIKE '%Memory%'"
```

**解决方案**:
```bash
# 1. 增加交换空间
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 2. 限制 ClickHouse 内存
sudo vim /etc/clickhouse-server/config.xml
# 添加: <max_server_memory_usage>4000000000</max_server_memory_usage>

# 3. 减少并发连接
vim .env
# 设置: MAX_CONCURRENT_CONNECTIONS=50
```

---

### 问题：CPU 使用率过高

**症状**: CPU 持续 100%

**诊断步骤**:
```bash
# 检查 CPU 使用
top -o %CPU

# 检查具体进程
ps aux --sort=-%cpu | head -10
```

**解决方案**:
```bash
# 1. 减少采集频率
# 编辑配置文件，降低采集频率

# 2. 优化 ClickHouse 查询
# 添加索引，优化查询语句

# 3. 限制并发
vim .env
MAX_CONCURRENT_CONNECTIONS=30
```

---

## 🌐 网络问题

### 问题：Binance API 返回 451 错误

**错误信息**:
```
HTTP 451: Unavailable For Legal Reasons
```

**原因**: Binance 地理限制

**解决方案**:
```bash
# 方式1：使用代理
export HTTP_PROXY=http://your-proxy:port
export HTTPS_PROXY=http://your-proxy:port

# 方式2：只使用 OKX 和 Deribit
# 编辑配置文件，禁用 Binance

# 方式3：使用 VPN
# 连接到支持的地区
```

---

### 问题：WebSocket 连接频繁断开

**症状**: 日志中频繁出现重连信息

**诊断步骤**:
```bash
# 检查网络稳定性
ping -c 10 www.okx.com

# 检查 DNS
nslookup www.okx.com

# 检查防火墙
sudo iptables -L
```

**解决方案**:
```bash
# 1. 增加重连延迟
vim .env
WEBSOCKET_RECONNECT_DELAY=10

# 2. 检查网络质量
# 使用更稳定的网络连接

# 3. 使用代理
# 配置稳定的代理服务器
```

---

## 🔍 调试技巧

### 启用详细日志

```bash
# 编辑 .env
LOG_LEVEL=DEBUG

# 重启服务
./scripts/manage_all.sh restart
```

### 实时监控日志

```bash
# 多窗口监控
tmux new-session \; \
  split-window -h \; \
  split-window -v \; \
  select-pane -t 0 \; \
  send-keys 'tail -f /tmp/nats-server.log' C-m \; \
  select-pane -t 1 \; \
  send-keys 'tail -f /tmp/storage-hot.log' C-m \; \
  select-pane -t 2 \; \
  send-keys 'tail -f /tmp/collector.log' C-m
```

### 手动测试组件

```bash
# 测试 NATS 连接
source venv/bin/activate
python -c "
import asyncio
from nats.aio.client import Client

async def test():
    nc = Client()
    await nc.connect('nats://localhost:4222')
    print('NATS 连接成功')
    await nc.close()

asyncio.run(test())
"

# 测试 ClickHouse 连接
clickhouse-client --query "SELECT 1"

# 测试交易所 API
source venv/bin/activate
python -c "
import ccxt
okx = ccxt.okx()
ticker = okx.fetch_ticker('BTC/USDT')
print(f'BTC 价格: {ticker[\"last\"]}')"
```

---

## 📞 获取帮助

如果以上方法都无法解决问题：

1. **查看完整日志**: `cat deployment.log`
2. **收集系统信息**: `uname -a && free -h && df -h`
3. **提交 Issue**: https://github.com/MNS-Vic/marketprism/issues
4. **包含以下信息**:
   - 操作系统版本
   - 错误信息
   - 相关日志
   - 已尝试的解决方案

---

## ✅ 预防措施

### 定期维护

```bash
# 每周执行
./scripts/manage_all.sh health

# 每月执行
clickhouse-client --query "OPTIMIZE TABLE marketprism_hot.trades"

# 定期备份
tar -czf backup-$(date +%Y%m%d).tar.gz /tmp/nats-jetstream
```

### 监控告警

```bash
# 设置 cron 任务监控
crontab -e

# 添加：每小时检查一次
0 * * * * /path/to/marketprism/scripts/manage_all.sh health || echo "MarketPrism 健康检查失败" | mail -s "Alert" your@email.com
```

---

祝你顺利解决问题！🚀

