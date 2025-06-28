# MarketPrism 智能监控告警系统运维手册

## 概述

本手册提供MarketPrism智能监控告警系统的日常运维指导，包括监控、故障处理、性能优化和维护流程。

## 系统架构概览

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Data Sources  │    │  Alert Manager  │    │  Notification   │
│                 │───▶│                 │───▶│   Channels      │
│ • Prometheus    │    │ • Rule Engine   │    │ • Email         │
│ • Business      │    │ • Anomaly Det.  │    │ • Slack         │
│   Metrics       │    │ • Failure Pred. │    │ • DingTalk      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 日常监控

### 1. 系统健康检查

#### 自动化健康检查
```bash
#!/bin/bash
# health_check.sh - 系统健康检查脚本

SERVICE_URL="http://localhost:8082"

# 检查服务状态
echo "检查服务健康状态..."
health_response=$(curl -s -o /dev/null -w "%{http_code}" $SERVICE_URL/health)

if [ $health_response -eq 200 ]; then
    echo "✅ 服务健康状态正常"
else
    echo "❌ 服务健康检查失败 (HTTP $health_response)"
    exit 1
fi

# 检查就绪状态
ready_response=$(curl -s -o /dev/null -w "%{http_code}" $SERVICE_URL/ready)

if [ $ready_response -eq 200 ]; then
    echo "✅ 服务就绪状态正常"
else
    echo "❌ 服务就绪检查失败 (HTTP $ready_response)"
    exit 1
fi

# 检查关键指标
echo "检查关键指标..."
metrics=$(curl -s $SERVICE_URL/api/v1/stats/alerts)
active_alerts=$(echo $metrics | jq -r '.active_alerts // 0')

echo "当前活跃告警数: $active_alerts"

if [ $active_alerts -gt 100 ]; then
    echo "⚠️  活跃告警数量过多，需要关注"
fi
```

#### 手动检查清单

**每日检查项目**：
- [ ] 服务健康状态 (`/health`)
- [ ] 活跃告警数量
- [ ] 错误率和响应时间
- [ ] 磁盘空间使用率
- [ ] 内存使用情况

**每周检查项目**：
- [ ] 告警规则有效性
- [ ] 通知渠道测试
- [ ] 性能趋势分析
- [ ] 日志轮转状态

### 2. 关键指标监控

#### Prometheus查询示例

```promql
# 服务可用性
up{job="monitoring-alerting"}

# 活跃告警数量
marketprism_alert_active

# API响应时间
histogram_quantile(0.95, rate(marketprism_api_request_duration_seconds_bucket[5m]))

# 错误率
rate(marketprism_api_requests_total{status=~"5.."}[5m]) / rate(marketprism_api_requests_total[5m])

# 内存使用率
process_resident_memory_bytes / (1024 * 1024 * 1024)
```

#### Grafana仪表板配置

创建监控仪表板，包含以下面板：

1. **系统概览**
   - 服务状态
   - 活跃告警数
   - 处理延迟
   - 错误率

2. **告警分析**
   - 按严重程度分布
   - 按类别分布
   - 告警趋势
   - 解决时间

3. **性能指标**
   - API响应时间
   - 吞吐量
   - 资源使用率
   - 异常检测性能

## 故障处理流程

### 1. 告警分级处理

#### P1 - 严重告警（立即响应）
- **响应时间**: 5分钟内
- **处理场景**: 服务完全不可用、数据丢失
- **处理流程**:
  1. 立即确认告警
  2. 评估影响范围
  3. 启动应急预案
  4. 通知相关团队
  5. 记录处理过程

#### P2 - 高级告警（30分钟内响应）
- **响应时间**: 30分钟内
- **处理场景**: 功能受影响、性能下降
- **处理流程**:
  1. 分析告警详情
  2. 确定根本原因
  3. 实施修复措施
  4. 验证修复效果

#### P3 - 中级告警（2小时内响应）
- **响应时间**: 2小时内
- **处理场景**: 潜在问题、预警
- **处理流程**:
  1. 调查问题原因
  2. 制定修复计划
  3. 安排修复时间
  4. 跟踪问题状态

#### P4 - 低级告警（工作时间内处理）
- **响应时间**: 下个工作日
- **处理场景**: 信息性告警、优化建议
- **处理流程**:
  1. 记录问题
  2. 评估优先级
  3. 纳入维护计划

### 2. 常见故障处理

#### 服务无响应
```bash
# 1. 检查服务状态
docker-compose ps
kubectl get pods -n marketprism-monitoring

# 2. 查看日志
docker-compose logs --tail=100 monitoring-alerting
kubectl logs -f deployment/monitoring-alerting -n marketprism-monitoring

# 3. 检查资源使用
docker stats
kubectl top pods -n marketprism-monitoring

# 4. 重启服务
docker-compose restart monitoring-alerting
kubectl rollout restart deployment/monitoring-alerting -n marketprism-monitoring
```

#### 告警不发送
```bash
# 1. 检查通知配置
curl http://localhost:8082/api/v1/stats/alerts

# 2. 测试SMTP连接
telnet smtp.gmail.com 587

# 3. 验证Slack Webhook
curl -X POST -H 'Content-type: application/json' \
  --data '{"text":"测试消息"}' \
  $SLACK_WEBHOOK_URL

# 4. 检查通知日志
grep "通知" /app/logs/monitoring-alerting.log
```

#### 内存泄漏
```bash
# 1. 监控内存使用
watch -n 5 'docker stats --no-stream | grep monitoring-alerting'

# 2. 生成内存转储
docker exec monitoring-alerting python -c "
import gc
import psutil
import os
print(f'Memory usage: {psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024:.2f} MB')
print(f'Objects: {len(gc.get_objects())}')
"

# 3. 重启服务释放内存
docker-compose restart monitoring-alerting
```

#### 数据库连接问题
```bash
# 1. 检查数据库连接
docker exec monitoring-alerting python -c "
import asyncio
from core.storage.unified_storage_manager import UnifiedStorageManager
# 测试连接代码
"

# 2. 检查网络连接
docker exec monitoring-alerting ping clickhouse-server
docker exec monitoring-alerting telnet redis-server 6379

# 3. 重置连接池
curl -X POST http://localhost:8082/api/v1/admin/reset-connections
```

### 3. 应急预案

#### 服务完全不可用
1. **立即行动**:
   - 切换到备用实例
   - 启用降级模式
   - 通知所有相关人员

2. **恢复步骤**:
   ```bash
   # 启用备用服务
   docker-compose -f docker-compose.backup.yml up -d
   
   # 更新负载均衡器配置
   # 重定向流量到备用实例
   ```

3. **后续处理**:
   - 分析故障原因
   - 修复主服务
   - 数据同步
   - 切回主服务

## 性能优化

### 1. 性能监控

#### 关键性能指标
- **响应时间**: API平均响应时间 < 500ms
- **吞吐量**: 处理能力 > 1000 请求/分钟
- **资源使用**: CPU < 70%, 内存 < 80%
- **错误率**: < 1%

#### 性能分析工具
```bash
# 1. API性能测试
ab -n 1000 -c 10 http://localhost:8082/api/v1/alerts

# 2. 内存分析
docker exec monitoring-alerting python -m memory_profiler main.py

# 3. CPU分析
docker exec monitoring-alerting python -m cProfile -o profile.stats main.py
```

### 2. 优化策略

#### 配置优化
```yaml
# 高性能配置
performance:
  batch_processing:
    enabled: true
    batch_size: 500
    flush_interval_seconds: 2
  
  caching:
    enabled: true
    cache_size: 5000
    ttl_seconds: 600
  
  concurrency:
    max_workers: 20
    queue_size: 5000
```

#### 数据库优化
```sql
-- ClickHouse优化
OPTIMIZE TABLE alerts_history;
ALTER TABLE alerts_history DELETE WHERE created_at < now() - INTERVAL 30 DAY;

-- 索引优化
CREATE INDEX idx_alerts_timestamp ON alerts_history (created_at);
CREATE INDEX idx_alerts_severity ON alerts_history (severity);
```

## 维护流程

### 1. 定期维护

#### 每日维护
```bash
#!/bin/bash
# daily_maintenance.sh

echo "开始每日维护..."

# 清理旧日志
find /app/logs -name "*.log" -mtime +7 -delete

# 检查磁盘空间
df -h | awk '$5 > 80 {print "磁盘使用率过高: " $0}'

# 备份配置
cp -r /app/config /backup/config-$(date +%Y%m%d)

echo "每日维护完成"
```

#### 每周维护
```bash
#!/bin/bash
# weekly_maintenance.sh

echo "开始每周维护..."

# 清理旧的告警历史
curl -X DELETE "http://localhost:8082/api/v1/admin/cleanup?days=30"

# 优化数据库
curl -X POST "http://localhost:8082/api/v1/admin/optimize-storage"

# 生成性能报告
curl -s "http://localhost:8082/api/v1/stats/performance" > /reports/performance-$(date +%Y%m%d).json

echo "每周维护完成"
```

### 2. 配置管理

#### 配置版本控制
```bash
# 配置变更流程
git add config/
git commit -m "更新告警规则配置"
git push origin main

# 配置验证
python scripts/validate_config.py config/services/monitoring-alerting-config.yaml

# 应用配置
docker-compose restart monitoring-alerting
```

#### 配置回滚
```bash
# 回滚到上一个版本
git checkout HEAD~1 -- config/
docker-compose restart monitoring-alerting

# 验证回滚效果
curl http://localhost:8082/health
```

### 3. 数据管理

#### 数据清理策略
- **告警历史**: 保留30天
- **指标数据**: 保留7天
- **日志文件**: 保留14天
- **追踪数据**: 保留24小时

#### 数据备份
```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/backup/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

# 备份配置
tar -czf $BACKUP_DIR/config.tar.gz config/

# 备份数据库
docker exec clickhouse-server clickhouse-client --query "BACKUP DATABASE marketprism TO '$BACKUP_DIR/clickhouse.backup'"

# 备份Redis
docker exec redis-server redis-cli BGSAVE
cp /var/lib/redis/dump.rdb $BACKUP_DIR/

echo "备份完成: $BACKUP_DIR"
```

## 安全管理

### 1. 访问控制

#### API认证
```bash
# 生成JWT Token
curl -X POST http://localhost:8082/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password"}'

# 使用Token访问API
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8082/api/v1/alerts
```

#### 权限管理
- **管理员**: 完全访问权限
- **运维人员**: 告警查看和处理权限
- **开发人员**: 只读权限
- **监控系统**: 指标上报权限

### 2. 安全审计

#### 访问日志分析
```bash
# 分析访问模式
grep "api/v1" /app/logs/access.log | \
  awk '{print $1}' | sort | uniq -c | sort -nr

# 检查异常访问
grep "401\|403\|404" /app/logs/access.log | tail -20

# 监控API调用频率
grep "api/v1/alerts" /app/logs/access.log | \
  awk '{print $4}' | cut -d: -f1-2 | uniq -c
```

## 容量规划

### 1. 资源需求评估

#### 当前使用情况
```bash
# CPU使用率
docker stats --no-stream | grep monitoring-alerting

# 内存使用情况
docker exec monitoring-alerting cat /proc/meminfo

# 磁盘使用情况
docker exec monitoring-alerting df -h

# 网络流量
docker exec monitoring-alerting cat /proc/net/dev
```

#### 增长预测
基于历史数据预测资源需求：
- **告警数量增长**: 每月10%
- **API调用增长**: 每月15%
- **存储需求增长**: 每月20%

### 2. 扩容策略

#### 水平扩容
```yaml
# Kubernetes HPA配置
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: monitoring-alerting-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: monitoring-alerting
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

#### 垂直扩容
```yaml
# 资源限制调整
resources:
  requests:
    memory: "1Gi"
    cpu: "500m"
  limits:
    memory: "4Gi"
    cpu: "2000m"
```

## 联系信息

### 紧急联系人
- **主要负责人**: 运维团队 (ops-team@company.com)
- **技术负责人**: 开发团队 (dev-team@company.com)
- **24/7支持**: +86-xxx-xxxx-xxxx

### 相关文档
- [部署指南](monitoring-alerting-deployment.md)
- [API文档](monitoring-alerting-api.md)
- [故障排除指南](monitoring-alerting-troubleshooting.md)
