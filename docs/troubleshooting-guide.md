# MarketPrism 智能监控告警系统故障排除指南

## 🚨 常见问题诊断和解决方案

### 1. 服务启动问题

#### 1.1 服务无法启动
**症状**: 容器启动失败或立即退出

**诊断步骤**:
```bash
# 查看容器状态
docker-compose ps

# 查看启动日志
docker-compose logs monitoring-alerting

# 检查配置文件
docker-compose config
```

**常见原因和解决方案**:

1. **端口冲突**
```bash
# 检查端口占用
netstat -tulpn | grep :8082

# 解决方案：修改端口配置
# 编辑 .env 文件
MONITORING_PORT=8083
```

2. **环境变量缺失**
```bash
# 检查环境变量
docker-compose exec monitoring-alerting env | grep -E "(REDIS|CLICKHOUSE|JWT)"

# 解决方案：补充缺失的环境变量
echo "JWT_SECRET=your_secret_key_here" >> .env
```

3. **依赖服务未就绪**
```bash
# 检查依赖服务状态
docker-compose ps redis clickhouse

# 解决方案：等待依赖服务启动
docker-compose up -d redis clickhouse
sleep 30
docker-compose up -d monitoring-alerting
```

#### 1.2 健康检查失败
**症状**: 服务启动但健康检查失败

**诊断步骤**:
```bash
# 直接测试健康检查端点
curl -f http://localhost:8082/health

# 查看详细错误信息
docker-compose logs monitoring-alerting | grep -i error
```

**解决方案**:
```bash
# 检查数据库连接
docker-compose exec monitoring-alerting python -c "
import redis
import clickhouse_connect
try:
    r = redis.Redis(host='redis', port=6379)
    r.ping()
    print('Redis连接正常')
except Exception as e:
    print(f'Redis连接失败: {e}')

try:
    client = clickhouse_connect.get_client(host='clickhouse', port=8123)
    client.ping()
    print('ClickHouse连接正常')
except Exception as e:
    print(f'ClickHouse连接失败: {e}')
"
```

### 2. 数据库连接问题

#### 2.1 Redis 连接问题
**症状**: Redis连接超时或拒绝连接

**诊断步骤**:
```bash
# 检查Redis服务状态
docker-compose exec redis redis-cli ping

# 检查Redis配置
docker-compose exec redis redis-cli config get "*"

# 检查网络连接
docker-compose exec monitoring-alerting ping redis
```

**解决方案**:
```bash
# 重启Redis服务
docker-compose restart redis

# 检查Redis内存使用
docker-compose exec redis redis-cli info memory

# 如果内存不足，清理过期数据
docker-compose exec redis redis-cli flushdb
```

#### 2.2 ClickHouse 连接问题
**症状**: ClickHouse查询失败或连接超时

**诊断步骤**:
```bash
# 检查ClickHouse服务状态
docker-compose exec clickhouse clickhouse-client --query "SELECT 1"

# 检查数据库和表
docker-compose exec clickhouse clickhouse-client --query "SHOW DATABASES"
docker-compose exec clickhouse clickhouse-client --query "SHOW TABLES FROM marketprism"

# 检查磁盘空间
docker-compose exec clickhouse df -h
```

**解决方案**:
```bash
# 重启ClickHouse服务
docker-compose restart clickhouse

# 清理旧数据（谨慎操作）
docker-compose exec clickhouse clickhouse-client --query "
OPTIMIZE TABLE marketprism.alerts FINAL;
ALTER TABLE marketprism.alerts DELETE WHERE created_at < now() - INTERVAL 30 DAY;
"

# 检查和修复表
docker-compose exec clickhouse clickhouse-client --query "CHECK TABLE marketprism.alerts"
```

### 3. 性能问题

#### 3.1 API响应慢
**症状**: API请求响应时间超过1秒

**诊断步骤**:
```bash
# 测试API响应时间
time curl -s http://localhost:8082/api/v1/alerts

# 查看系统资源使用
docker stats

# 检查数据库查询性能
docker-compose exec clickhouse clickhouse-client --query "
SELECT query, query_duration_ms, memory_usage
FROM system.query_log
WHERE event_time > now() - INTERVAL 1 HOUR
ORDER BY query_duration_ms DESC
LIMIT 10;
"
```

**解决方案**:
```bash
# 增加工作进程数
# 编辑 .env 文件
MAX_WORKERS=20

# 优化数据库查询
docker-compose exec clickhouse clickhouse-client --query "
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON marketprism.alerts (created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON marketprism.alerts (severity);
"

# 增加缓存大小
# 编辑 .env 文件
CACHE_SIZE=2000
```

#### 3.2 内存使用过高
**症状**: 容器内存使用率超过80%

**诊断步骤**:
```bash
# 查看内存使用详情
docker stats --no-stream

# 检查Python进程内存
docker-compose exec monitoring-alerting ps aux

# 分析内存泄漏
docker-compose exec monitoring-alerting python -c "
import psutil
import os
process = psutil.Process(os.getpid())
print(f'内存使用: {process.memory_info().rss / 1024 / 1024:.2f} MB')
"
```

**解决方案**:
```bash
# 重启服务释放内存
docker-compose restart monitoring-alerting

# 调整内存限制
# 编辑 docker-compose.yml
deploy:
  resources:
    limits:
      memory: 4G

# 优化缓存配置
# 编辑 .env 文件
CACHE_SIZE=500
CACHE_TTL=180
```

### 4. 告警系统问题

#### 4.1 告警不触发
**症状**: 满足条件但告警未触发

**诊断步骤**:
```bash
# 检查告警规则
curl -s http://localhost:8082/api/v1/rules | jq '.'

# 查看告警处理日志
docker-compose logs monitoring-alerting | grep -i alert

# 测试告警规则
curl -X POST http://localhost:8082/api/v1/anomaly/detect \
  -H "Content-Type: application/json" \
  -d '{"metric_name": "test_metric", "value": 999.0}'
```

**解决方案**:
```bash
# 检查告警规则配置
docker-compose exec monitoring-alerting python -c "
from core.observability.alerting.alert_rules import AlertRuleEngine
engine = AlertRuleEngine()
rules = engine.get_all_rules()
for rule in rules:
    print(f'规则: {rule.name}, 启用: {rule.enabled}')
"

# 重新加载告警规则
curl -X POST http://localhost:8082/api/v1/admin/reload-rules
```

#### 4.2 通知发送失败
**症状**: 告警触发但通知未发送

**诊断步骤**:
```bash
# 检查通知配置
docker-compose exec monitoring-alerting python -c "
import os
print('SMTP配置:')
print(f'  服务器: {os.getenv(\"SMTP_SERVER\")}')
print(f'  用户名: {os.getenv(\"SMTP_USERNAME\")}')
print(f'  密码: {\"已配置\" if os.getenv(\"SMTP_PASSWORD\") else \"未配置\"}')
"

# 测试邮件发送
curl -X POST http://localhost:8082/api/v1/admin/test-notification \
  -H "Content-Type: application/json" \
  -d '{"channel": "email", "message": "测试消息"}'
```

**解决方案**:
```bash
# 检查网络连接
docker-compose exec monitoring-alerting nslookup smtp.gmail.com

# 验证SMTP配置
docker-compose exec monitoring-alerting python -c "
import smtplib
import os
try:
    server = smtplib.SMTP(os.getenv('SMTP_SERVER'), 587)
    server.starttls()
    server.login(os.getenv('SMTP_USERNAME'), os.getenv('SMTP_PASSWORD'))
    print('SMTP连接成功')
    server.quit()
except Exception as e:
    print(f'SMTP连接失败: {e}')
"
```

### 5. 前端界面问题

#### 5.1 前端无法访问
**症状**: 浏览器无法打开前端页面

**诊断步骤**:
```bash
# 检查前端服务状态
docker-compose ps monitoring-dashboard

# 查看前端日志
docker-compose logs monitoring-dashboard

# 测试前端端口
curl -I http://localhost:3000
```

**解决方案**:
```bash
# 重启前端服务
docker-compose restart monitoring-dashboard

# 检查端口映射
docker-compose port monitoring-dashboard 3000

# 重新构建前端镜像
docker-compose build monitoring-dashboard
```

#### 5.2 API数据加载失败
**症状**: 前端界面显示但数据无法加载

**诊断步骤**:
```bash
# 检查API连接
curl -s http://localhost:8082/api/v1/health

# 查看浏览器控制台错误
# 在浏览器开发者工具中查看Network和Console标签

# 检查CORS配置
curl -H "Origin: http://localhost:3000" \
     -H "Access-Control-Request-Method: GET" \
     -H "Access-Control-Request-Headers: X-Requested-With" \
     -X OPTIONS \
     http://localhost:8082/api/v1/alerts
```

**解决方案**:
```bash
# 配置CORS
# 编辑后端配置文件，添加CORS支持
echo "CORS_ORIGINS=http://localhost:3000,https://yourdomain.com" >> .env

# 检查网络连接
docker-compose exec monitoring-dashboard ping monitoring-alerting
```

### 6. 日志分析工具

#### 6.1 日志聚合查询
```bash
# 查看所有服务日志
docker-compose logs --tail=100 -f

# 查看特定时间段的错误日志
docker-compose logs --since="2024-06-22T10:00:00" monitoring-alerting | grep -i error

# 统计错误类型
docker-compose logs monitoring-alerting | grep -i error | awk '{print $NF}' | sort | uniq -c
```

#### 6.2 性能监控查询
```bash
# 查看API请求统计
curl -s http://localhost:8082/metrics | grep -E "(http_requests|response_time)"

# 查看数据库性能
docker-compose exec clickhouse clickhouse-client --query "
SELECT
    query_kind,
    count() as query_count,
    avg(query_duration_ms) as avg_duration,
    max(query_duration_ms) as max_duration
FROM system.query_log
WHERE event_time > now() - INTERVAL 1 HOUR
GROUP BY query_kind
ORDER BY avg_duration DESC;
"
```

### 7. 紧急恢复程序

#### 7.1 服务完全故障恢复
```bash
#!/bin/bash
# emergency-recovery.sh

echo "开始紧急恢复程序..."

# 1. 停止所有服务
docker-compose down

# 2. 清理损坏的容器和网络
docker system prune -f

# 3. 从备份恢复数据
LATEST_BACKUP=$(ls -t /backup/marketprism/ | head -1)
if [ -n "$LATEST_BACKUP" ]; then
    echo "从备份恢复数据: $LATEST_BACKUP"
    ./scripts/restore.sh "$LATEST_BACKUP"
fi

# 4. 重新启动服务
docker-compose up -d

# 5. 等待服务就绪
echo "等待服务启动..."
sleep 60

# 6. 验证服务状态
if curl -f http://localhost:8082/health > /dev/null 2>&1; then
    echo "✅ 服务恢复成功"
else
    echo "❌ 服务恢复失败，请手动检查"
    exit 1
fi
```

#### 7.2 数据一致性检查
```bash
#!/bin/bash
# data-consistency-check.sh

echo "开始数据一致性检查..."

# 检查Redis数据
REDIS_KEYS=$(docker-compose exec redis redis-cli dbsize | tr -d '\r')
echo "Redis键数量: $REDIS_KEYS"

# 检查ClickHouse数据
CH_ALERTS=$(docker-compose exec clickhouse clickhouse-client --query "SELECT count() FROM marketprism.alerts" | tr -d '\r')
echo "ClickHouse告警记录数: $CH_ALERTS"

# 检查数据完整性
if [ "$REDIS_KEYS" -gt 0 ] && [ "$CH_ALERTS" -gt 0 ]; then
    echo "✅ 数据一致性检查通过"
else
    echo "❌ 数据一致性检查失败"
    exit 1
fi
```

### 8. 联系支持

如果以上解决方案无法解决问题，请收集以下信息并联系技术支持：

1. **系统信息**:
```bash
# 收集系统信息
uname -a
docker --version
docker-compose --version
```

2. **服务状态**:
```bash
docker-compose ps
docker-compose logs --tail=200 > logs.txt
```

3. **配置信息**:
```bash
docker-compose config > config.yml
```

4. **错误详情**: 具体的错误消息和复现步骤

**技术支持联系方式**:
- 邮箱: support@marketprism.com
- 文档: https://docs.marketprism.com
- GitHub Issues: https://github.com/marketprism/issues
