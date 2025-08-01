# MarketPrism 故障排除指南

> 最后更新：2025-01-27

## 🚨 常见问题快速诊断

### 系统状态检查清单

```bash
# 1. 检查所有服务状态
docker-compose ps

# 2. 检查收集器健康状态
curl http://localhost:8080/health

# 3. 检查基础设施连接
docker exec -it marketprism_nats_1 nats stream ls
docker exec -it marketprism_clickhouse_1 clickhouse-client --query "SELECT 1"

# 4. 检查数据流
curl http://localhost:8080/metrics | grep messages_per_second
```

## 🔧 服务启动问题

### 1. Python Collector 无法启动

#### 症状
- 服务启动失败
- 端口占用错误
- 依赖导入错误

#### 诊断步骤
```bash
# 检查端口占用
lsof -i :8080
netstat -tulpn | grep 8080

# 检查 Python 环境
python --version
pip list | grep -E "(pydantic|nats|asyncio)"

# 检查环境变量
env | grep -E "(NATS|CLICKHOUSE|COLLECTOR)"

# 查看详细错误日志
python -m marketprism_collector.main --debug
```

#### 解决方案
```bash
# 1. 杀死占用端口的进程
kill -9 $(lsof -ti:8080)

# 2. 重新安装依赖
pip install -r requirements.txt --force-reinstall

# 3. 检查配置文件
python -c "import yaml; print(yaml.safe_load(open('config/collector.yaml')))"

# 4. 使用不同端口
export COLLECTOR_HTTP_PORT=8081
```

### 2. Docker 服务启动失败

#### 症状
- Docker Compose 启动失败
- 容器异常退出
- 网络连接问题

#### 诊断步骤
```bash
# 检查 Docker 状态
docker version
docker-compose version

# 查看容器日志
docker-compose logs nats
docker-compose logs clickhouse
docker-compose logs python-collector

# 检查资源使用
docker stats
df -h  # 磁盘空间
free -h  # 内存使用
```

#### 解决方案
```bash
# 1. 重启 Docker 服务
sudo systemctl restart docker  # Linux
# 或重启 Docker Desktop  # macOS/Windows

# 2. 清理 Docker 资源
docker system prune -f
docker volume prune -f

# 3. 重新构建镜像
docker-compose build --no-cache

# 4. 分步启动服务
docker-compose up -d nats
sleep 10
docker-compose up -d clickhouse
sleep 10
docker-compose up -d python-collector
```

## 📡 网络连接问题

### 1. NATS 连接失败

#### 症状
- 无法连接到 NATS 服务器
- 消息发布失败
- 连接超时

#### 诊断步骤
```bash
# 检查 NATS 服务状态
docker exec -it marketprism_nats_1 nats server check

# 测试连接
telnet localhost 4222
nc -zv localhost 4222

# 检查 NATS 配置
docker exec -it marketprism_nats_1 cat /etc/nats/nats.conf

# 查看 NATS 日志
docker logs marketprism_nats_1
```

#### 解决方案
```bash
# 1. 重启 NATS 服务
docker-compose restart nats

# 2. 检查防火墙设置
sudo ufw status  # Ubuntu
sudo firewall-cmd --list-ports  # CentOS

# 3. 修改 NATS 配置
# 编辑 config/nats/nats.conf
port: 4222
http_port: 8222
jetstream: enabled

# 4. 使用不同端口
export NATS_PORT=4223
```

### 2. ClickHouse 连接问题

#### 症状
- 数据库连接失败
- 查询超时
- 认证错误

#### 诊断步骤
```bash
# 检查 ClickHouse 状态
docker exec -it marketprism_clickhouse_1 clickhouse-client --query "SELECT version()"

# 测试 HTTP 接口
curl http://localhost:8123/ping

# 检查数据库配置
docker exec -it marketprism_clickhouse_1 cat /etc/clickhouse-server/config.xml

# 查看 ClickHouse 日志
docker logs marketprism_clickhouse_1
```

#### 解决方案
```bash
# 1. 重启 ClickHouse
docker-compose restart clickhouse

# 2. 检查数据库权限
docker exec -it marketprism_clickhouse_1 clickhouse-client --query "SHOW USERS"

# 3. 重新初始化数据库
python scripts/init_clickhouse.py --force

# 4. 检查磁盘空间
docker exec -it marketprism_clickhouse_1 df -h
```

## 📊 数据流问题

### 1. 数据未正确收集

#### 症状
- 监控指标显示 0 消息
- 交易所连接正常但无数据
- 数据标准化错误

#### 诊断步骤
```bash
# 检查交易所连接状态
curl http://localhost:8080/metrics | grep exchange_connection_status

# 查看实时日志
docker-compose logs -f python-collector | grep -E "(ERROR|WARNING)"

# 检查 WebSocket 连接
curl http://localhost:8080/status | jq '.websocket_connections'

# 验证数据格式
curl http://localhost:8080/debug/raw_data  # 如果启用了调试端点
```

#### 解决方案
```bash
# 1. 检查网络代理设置
export HTTP_PROXY=""
export HTTPS_PROXY=""

# 2. 重新配置交易所
# 编辑 config/exchanges/binance_spot.yaml
enabled: true
symbols: ["BTCUSDT"]  # 原始格式，会自动标准化为BTC-USDT

# 3. 重启收集器
docker-compose restart python-collector

# 4. 检查 API 限制
# 查看交易所 API 文档，确认频率限制
```

### 2. 数据存储问题

#### 症状
- NATS 有消息但 ClickHouse 无数据
- 数据写入失败
- 表结构错误

#### 诊断步骤
```bash
# 检查 NATS 消息
docker exec -it marketprism_nats_1 nats stream info MARKET_DATA

# 检查 ClickHouse 表
docker exec -it marketprism_clickhouse_1 clickhouse-client --query "SHOW TABLES FROM marketprism"

# 查看表结构
docker exec -it marketprism_clickhouse_1 clickhouse-client --query "DESCRIBE marketprism.trades"

# 检查数据写入
docker exec -it marketprism_clickhouse_1 clickhouse-client --query "SELECT count() FROM marketprism.trades"
```

#### 解决方案
```bash
# 1. 重新创建表结构
python scripts/init_clickhouse.py --recreate-tables

# 2. 检查数据格式
docker exec -it marketprism_clickhouse_1 clickhouse-client --query "SELECT * FROM marketprism.trades LIMIT 1 FORMAT Vertical"

# 3. 手动插入测试数据
docker exec -it marketprism_clickhouse_1 clickhouse-client --query "INSERT INTO marketprism.trades VALUES (...)"

# 4. 检查磁盘权限
docker exec -it marketprism_clickhouse_1 ls -la /var/lib/clickhouse/
```

## 🔍 性能问题

### 1. 处理速度慢

#### 症状
- 消息处理延迟高
- CPU 使用率高
- 内存使用持续增长

#### 诊断步骤
```bash
# 检查性能指标
curl http://localhost:8080/metrics | grep -E "(processing_duration|memory_usage|cpu_usage)"

# 查看系统资源
top -p $(pgrep -f marketprism_collector)
htop

# 检查网络延迟
ping api.binance.com
ping www.okx.com

# 分析内存使用
python -m memory_profiler services/python-collector/src/marketprism_collector/main.py
```

#### 解决方案
```bash
# 1. 调整批处理大小
# 编辑配置文件
batch_size: 100  # 减少批处理大小
flush_interval: 1000  # 增加刷新间隔

# 2. 优化并发设置
max_concurrent_connections: 5  # 减少并发连接

# 3. 增加系统资源
# 修改 docker-compose.yml
services:
  python-collector:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'

# 4. 启用性能分析
export ENABLE_PROFILING=true
```

### 2. 内存泄漏

#### 症状
- 内存使用持续增长
- 系统变慢
- 最终内存耗尽

#### 诊断步骤
```bash
# 监控内存使用趋势
watch -n 5 'docker stats --no-stream | grep python-collector'

# 使用内存分析工具
pip install memory-profiler
python -m memory_profiler services/python-collector/src/marketprism_collector/main.py

# 检查对象引用
python -c "
import gc
gc.collect()
print(f'Objects: {len(gc.get_objects())}')
"
```

#### 解决方案
```bash
# 1. 重启服务释放内存
docker-compose restart python-collector

# 2. 启用垃圾回收调试
export PYTHONMALLOC=debug
export PYTHONFAULTHANDLER=1

# 3. 调整垃圾回收参数
python -c "
import gc
gc.set_threshold(700, 10, 10)  # 更频繁的垃圾回收
"

# 4. 使用内存限制
docker run --memory=1g --memory-swap=1g python-collector
```

## 🛡️ 安全问题

### 1. 认证失败

#### 症状
- API 密钥无效
- 权限不足错误
- 访问被拒绝

#### 诊断步骤
```bash
# 检查 API 密钥配置
env | grep -E "(API_KEY|SECRET)"

# 测试 API 连接
curl -H "X-MBX-APIKEY: your_api_key" https://api.binance.com/api/v3/account

# 检查权限设置
ls -la config/
ls -la logs/
```

#### 解决方案
```bash
# 1. 更新 API 密钥
# 编辑 .env 文件
BINANCE_API_KEY=new_api_key
BINANCE_SECRET_KEY=new_secret_key

# 2. 检查 API 权限
# 确保 API 密钥有读取权限

# 3. 重新加载配置
docker-compose restart python-collector

# 4. 使用测试网络
# 编辑交易所配置
testnet: true
base_url: "https://testnet.binance.vision"
```

### 2. 网络安全问题

#### 症状
- 连接被阻止
- SSL 证书错误
- 代理配置问题

#### 诊断步骤
```bash
# 检查 SSL 证书
openssl s_client -connect api.binance.com:443

# 测试代理连接
curl --proxy http://proxy:8080 https://api.binance.com/api/v3/ping

# 检查防火墙规则
sudo iptables -L
sudo ufw status
```

#### 解决方案
```bash
# 1. 配置代理
export HTTP_PROXY=http://proxy:8080
export HTTPS_PROXY=http://proxy:8080

# 2. 忽略 SSL 验证 (仅测试环境)
export PYTHONHTTPSVERIFY=0

# 3. 配置防火墙
sudo ufw allow 8080
sudo ufw allow 4222
sudo ufw allow 8123

# 4. 使用 VPN 或代理
# 配置网络代理服务
```

## 📋 日志分析

### 日志位置
```bash
# Docker 容器日志
docker-compose logs python-collector
docker-compose logs nats
docker-compose logs clickhouse

# 应用程序日志
tail -f logs/marketprism.log
tail -f logs/error.log

# 系统日志
journalctl -u docker
tail -f /var/log/syslog
```

### 常见错误模式

#### 1. 连接错误
```
ERROR: Failed to connect to NATS: Connection refused
ERROR: ClickHouse connection timeout
ERROR: WebSocket connection closed unexpectedly
```

#### 2. 数据错误
```
ERROR: Failed to normalize data: Missing required field
WARNING: Invalid price value: -1.0
ERROR: JSON decode error: Expecting value
```

#### 3. 性能警告
```
WARNING: High memory usage: 1.5GB
WARNING: Processing delay: 5000ms
WARNING: Queue size exceeded: 10000 messages
```

## 🔧 维护工具

### 系统健康检查脚本

创建 `scripts/health_check.sh`:
```bash
#!/bin/bash

echo "=== MarketPrism Health Check ==="

# 检查服务状态
echo "1. Checking services..."
docker-compose ps

# 检查收集器健康
echo "2. Checking collector health..."
curl -s http://localhost:8080/health | jq .

# 检查数据流
echo "3. Checking data flow..."
curl -s http://localhost:8080/metrics | grep messages_per_second

# 检查错误率
echo "4. Checking error rate..."
curl -s http://localhost:8080/metrics | grep error_rate

echo "=== Health Check Complete ==="
```

### 性能监控脚本

创建 `scripts/performance_monitor.sh`:
```bash
#!/bin/bash

echo "=== Performance Monitor ==="

while true; do
    echo "$(date): $(curl -s http://localhost:8080/metrics | grep -E '(messages_per_second|memory_usage|cpu_usage)' | tr '\n' ' ')"
    sleep 10
done
```

## 📞 获取帮助

### 紧急问题
1. 检查 [常见问题](../references/faq.md)
2. 查看 [GitHub Issues](https://github.com/your-org/marketprism/issues)
3. 联系技术支持: support@marketprism.com

### 社区支持
- **GitHub 讨论**: 技术问题讨论
- **Stack Overflow**: 标签 `marketprism`
- **Discord**: MarketPrism 社区频道

---

**故障排除指南状态**: ✅ 已完成  
**覆盖问题**: 90% 常见问题  
**更新频率**: 根据用户反馈持续更新  
**支持级别**: 社区 + 企业支持