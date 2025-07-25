# MarketPrism 智能监控告警系统运维最佳实践

## 🎯 运维管理最佳实践

### 1. 日常运维检查清单

#### 1.1 每日检查 (Daily Checklist)
```bash
#!/bin/bash
# daily-check.sh - 每日运维检查脚本

echo "=== MarketPrism 每日运维检查 ==="
echo "检查时间: $(date)"

# 1. 服务状态检查
echo "1. 检查服务状态..."
docker-compose ps

# 2. 健康检查
echo "2. 执行健康检查..."
./scripts/ops-automation.sh health --verbose

# 3. 资源使用检查
echo "3. 检查资源使用..."
docker stats --no-stream

# 4. 磁盘空间检查
echo "4. 检查磁盘空间..."
df -h

# 5. 告警统计
echo "5. 检查告警统计..."
curl -s http://localhost:8082/api/v1/stats/alerts | jq '.'

# 6. 错误日志检查
echo "6. 检查错误日志..."
docker-compose logs --since="24h" | grep -i error | wc -l

echo "=== 每日检查完成 ==="
```

#### 1.2 每周检查 (Weekly Checklist)
```bash
#!/bin/bash
# weekly-check.sh - 每周运维检查脚本

echo "=== MarketPrism 每周运维检查 ==="

# 1. 性能趋势分析
echo "1. 性能趋势分析..."
./scripts/load-test.sh http://localhost:8082 300 50

# 2. 数据库优化
echo "2. 数据库优化..."
docker-compose exec clickhouse clickhouse-client --query "OPTIMIZE TABLE marketprism.alerts FINAL"

# 3. 日志清理
echo "3. 清理旧日志..."
./scripts/ops-automation.sh cleanup --days=7 --force

# 4. 备份验证
echo "4. 验证备份完整性..."
LATEST_BACKUP=$(ls -t /backup/marketprism/ | head -1)
if [ -n "$LATEST_BACKUP" ]; then
    echo "最新备份: $LATEST_BACKUP"
    # 验证备份文件完整性
    tar -tzf "/backup/marketprism/$LATEST_BACKUP/config.tar.gz" > /dev/null
    echo "备份文件完整性: OK"
fi

# 5. 安全检查
echo "5. 执行安全检查..."
./scripts/security-test.sh http://localhost:8082 docker-compose

echo "=== 每周检查完成 ==="
```

#### 1.3 每月检查 (Monthly Checklist)
```bash
#!/bin/bash
# monthly-check.sh - 每月运维检查脚本

echo "=== MarketPrism 每月运维检查 ==="

# 1. 容量规划分析
echo "1. 容量规划分析..."
echo "数据增长统计:"
docker-compose exec clickhouse clickhouse-client --query "
SELECT 
    toYYYYMM(created_at) as month,
    count() as alert_count,
    sum(length(description)) as data_size
FROM marketprism.alerts 
WHERE created_at >= now() - INTERVAL 3 MONTH
GROUP BY month
ORDER BY month;
"

# 2. 系统更新检查
echo "2. 检查系统更新..."
docker images | grep marketprism

# 3. 证书有效期检查
echo "3. 检查SSL证书..."
if [ -f "/etc/ssl/certs/monitoring.crt" ]; then
    openssl x509 -in /etc/ssl/certs/monitoring.crt -noout -dates
fi

# 4. 依赖组件版本检查
echo "4. 检查依赖组件版本..."
docker-compose exec redis redis-server --version
docker-compose exec clickhouse clickhouse-client --version

echo "=== 每月检查完成 ==="
```

### 2. 监控和告警策略

#### 2.1 关键指标监控
```yaml
# 关键性能指标 (KPI) 监控
monitoring_kpis:
  # 系统可用性
  availability:
    target: 99.9%
    measurement: "uptime / total_time"
    alert_threshold: 99.5%
  
  # API响应时间
  response_time:
    target: 500ms
    measurement: "95th percentile"
    alert_threshold: 1000ms
  
  # 错误率
  error_rate:
    target: 1%
    measurement: "errors / total_requests"
    alert_threshold: 5%
  
  # 数据处理延迟
  processing_delay:
    target: 100ms
    measurement: "avg processing time"
    alert_threshold: 500ms
```

#### 2.2 告警级别定义
```yaml
# 告警级别和响应时间
alert_levels:
  critical:
    description: "系统完全不可用或数据丢失"
    response_time: "5分钟内"
    escalation: "立即通知所有相关人员"
    examples:
      - "服务完全宕机"
      - "数据库连接失败"
      - "安全漏洞"
  
  high:
    description: "系统功能受限或性能严重下降"
    response_time: "15分钟内"
    escalation: "通知主要负责人"
    examples:
      - "API响应时间超过2秒"
      - "错误率超过10%"
      - "磁盘使用率超过90%"
  
  medium:
    description: "系统性能下降但功能正常"
    response_time: "1小时内"
    escalation: "通知运维团队"
    examples:
      - "内存使用率超过80%"
      - "API响应时间超过1秒"
      - "告警数量异常增加"
  
  low:
    description: "潜在问题或预警"
    response_time: "4小时内"
    escalation: "记录日志，定期检查"
    examples:
      - "磁盘使用率超过70%"
      - "连接数接近上限"
      - "配置文件变更"
```

### 3. 变更管理流程

#### 3.1 变更分类
```yaml
change_categories:
  emergency:
    description: "紧急安全修复或严重故障恢复"
    approval: "技术负责人口头批准"
    testing: "最小化测试"
    rollback_plan: "必须"
  
  standard:
    description: "常规功能更新和配置变更"
    approval: "变更委员会书面批准"
    testing: "完整测试流程"
    rollback_plan: "必须"
  
  normal:
    description: "日常维护和小幅优化"
    approval: "运维负责人批准"
    testing: "基础测试"
    rollback_plan: "推荐"
```

#### 3.2 变更执行流程
```bash
#!/bin/bash
# change-management.sh - 变更管理脚本

CHANGE_TYPE="$1"
CHANGE_DESC="$2"
CHANGE_ID="CHG-$(date +%Y%m%d-%H%M%S)"

echo "=== 变更管理流程 ==="
echo "变更ID: $CHANGE_ID"
echo "变更类型: $CHANGE_TYPE"
echo "变更描述: $CHANGE_DESC"

# 1. 变更前检查
echo "1. 执行变更前检查..."
./scripts/ops-automation.sh status
./scripts/ops-automation.sh health

# 2. 创建备份
echo "2. 创建变更前备份..."
./scripts/ops-automation.sh backup --force

# 3. 记录变更开始
echo "3. 记录变更开始时间..."
echo "$(date): 开始执行变更 $CHANGE_ID - $CHANGE_DESC" >> /var/log/marketprism/changes.log

# 4. 执行变更 (这里需要根据具体变更内容实现)
echo "4. 执行变更..."
# 变更执行逻辑

# 5. 变更后验证
echo "5. 执行变更后验证..."
./scripts/test-deployment.sh
if [ $? -eq 0 ]; then
    echo "✅ 变更验证成功"
    echo "$(date): 变更 $CHANGE_ID 执行成功" >> /var/log/marketprism/changes.log
else
    echo "❌ 变更验证失败，开始回滚..."
    # 执行回滚逻辑
    echo "$(date): 变更 $CHANGE_ID 执行失败，已回滚" >> /var/log/marketprism/changes.log
fi
```

### 4. 备份和恢复策略

#### 4.1 备份策略
```yaml
backup_strategy:
  # 全量备份
  full_backup:
    frequency: "每周日凌晨2点"
    retention: "4周"
    components:
      - "所有数据库"
      - "配置文件"
      - "日志文件"
      - "应用程序"
  
  # 增量备份
  incremental_backup:
    frequency: "每日凌晨3点"
    retention: "7天"
    components:
      - "数据库变更"
      - "配置文件变更"
  
  # 实时备份
  realtime_backup:
    frequency: "每小时"
    retention: "24小时"
    components:
      - "关键配置"
      - "告警数据"
```

#### 4.2 恢复测试
```bash
#!/bin/bash
# backup-recovery-test.sh - 备份恢复测试

echo "=== 备份恢复测试 ==="

# 1. 创建测试环境
echo "1. 创建测试环境..."
docker-compose -f docker-compose.test.yml up -d

# 2. 恢复最新备份到测试环境
echo "2. 恢复备份到测试环境..."
LATEST_BACKUP=$(ls -t /backup/marketprism/ | head -1)
./scripts/restore.sh "$LATEST_BACKUP" --target=test

# 3. 验证恢复结果
echo "3. 验证恢复结果..."
./scripts/test-deployment.sh http://localhost:8083 docker-compose

# 4. 清理测试环境
echo "4. 清理测试环境..."
docker-compose -f docker-compose.test.yml down

echo "=== 备份恢复测试完成 ==="
```

### 5. 安全运维实践

#### 5.1 安全检查清单
```bash
#!/bin/bash
# security-checklist.sh - 安全检查清单

echo "=== 安全检查清单 ==="

# 1. 检查默认密码
echo "1. 检查默认密码..."
if grep -q "admin\|password\|123456" .env; then
    echo "❌ 发现默认密码，请立即更改"
else
    echo "✅ 未发现默认密码"
fi

# 2. 检查SSL证书
echo "2. 检查SSL证书..."
if [ -f "/etc/ssl/certs/monitoring.crt" ]; then
    EXPIRY=$(openssl x509 -in /etc/ssl/certs/monitoring.crt -noout -enddate | cut -d= -f2)
    EXPIRY_EPOCH=$(date -d "$EXPIRY" +%s)
    NOW_EPOCH=$(date +%s)
    DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))
    
    if [ $DAYS_LEFT -lt 30 ]; then
        echo "❌ SSL证书将在 $DAYS_LEFT 天后过期"
    else
        echo "✅ SSL证书有效期正常 ($DAYS_LEFT 天)"
    fi
fi

# 3. 检查容器安全
echo "3. 检查容器安全..."
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
    aquasec/trivy image marketprism/monitoring-alerting:latest

# 4. 检查网络安全
echo "4. 检查网络安全..."
nmap -sS -O localhost

echo "=== 安全检查完成 ==="
```

#### 5.2 访问控制管理
```yaml
# 访问控制策略
access_control:
  # 管理员权限
  admin:
    permissions:
      - "系统配置"
      - "用户管理"
      - "备份恢复"
      - "安全设置"
    access_method: "双因素认证"
    session_timeout: "30分钟"
  
  # 运维人员权限
  operator:
    permissions:
      - "服务重启"
      - "日志查看"
      - "性能监控"
      - "告警管理"
    access_method: "单因素认证"
    session_timeout: "2小时"
  
  # 只读用户权限
  viewer:
    permissions:
      - "仪表板查看"
      - "告警查看"
      - "报告查看"
    access_method: "单因素认证"
    session_timeout: "8小时"
```

### 6. 性能优化实践

#### 6.1 性能监控脚本
```bash
#!/bin/bash
# performance-monitor.sh - 性能监控脚本

echo "=== 性能监控报告 ==="
echo "监控时间: $(date)"

# 1. CPU使用率
echo "1. CPU使用率:"
top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1

# 2. 内存使用率
echo "2. 内存使用率:"
free | grep Mem | awk '{printf "%.2f%%\n", $3/$2 * 100.0}'

# 3. 磁盘I/O
echo "3. 磁盘I/O:"
iostat -x 1 1 | tail -n +4

# 4. 网络流量
echo "4. 网络流量:"
sar -n DEV 1 1 | grep -E "(eth0|ens)"

# 5. 应用性能指标
echo "5. 应用性能指标:"
curl -s http://localhost:8082/metrics | grep -E "(response_time|request_count|error_rate)"

echo "=== 性能监控完成 ==="
```

#### 6.2 性能调优建议
```yaml
performance_tuning:
  # 数据库调优
  database:
    redis:
      - "启用持久化: appendonly yes"
      - "设置内存策略: maxmemory-policy allkeys-lru"
      - "调整连接池: maxclients 10000"
    
    clickhouse:
      - "优化查询缓存: uncompressed_cache_size 8GB"
      - "启用数据压缩: compression lz4"
      - "调整并发查询: max_concurrent_queries 100"
  
  # 应用调优
  application:
    - "增加工作进程: MAX_WORKERS=20"
    - "优化批处理: BATCH_SIZE=200"
    - "调整缓存: CACHE_SIZE=2000"
    - "启用连接池: DB_POOL_SIZE=50"
  
  # 系统调优
  system:
    - "调整文件描述符: ulimit -n 65536"
    - "优化网络参数: net.core.somaxconn=65535"
    - "调整内存管理: vm.swappiness=10"
```

### 7. 文档和知识管理

#### 7.1 运维文档结构
```
docs/
├── operations/
│   ├── daily-procedures.md      # 日常操作程序
│   ├── emergency-procedures.md  # 应急处理程序
│   ├── maintenance-windows.md   # 维护窗口计划
│   └── escalation-matrix.md     # 升级矩阵
├── troubleshooting/
│   ├── common-issues.md         # 常见问题
│   ├── error-codes.md           # 错误代码说明
│   └── diagnostic-tools.md      # 诊断工具使用
├── procedures/
│   ├── backup-restore.md        # 备份恢复程序
│   ├── security-procedures.md   # 安全操作程序
│   └── change-management.md     # 变更管理程序
└── references/
    ├── configuration-guide.md   # 配置参考
    ├── api-reference.md         # API参考
    └── architecture-overview.md # 架构概览
```

#### 7.2 知识库维护
```bash
#!/bin/bash
# knowledge-base-update.sh - 知识库更新脚本

echo "=== 知识库更新 ==="

# 1. 更新系统信息
echo "1. 更新系统信息..."
cat > docs/system-info.md << EOF
# 系统信息

## 更新时间
$(date)

## 服务版本
$(docker images | grep marketprism)

## 系统配置
$(docker-compose config)

## 性能基准
$(./scripts/load-test.sh http://localhost:8082 60 10 | tail -10)
EOF

# 2. 更新故障案例
echo "2. 更新故障案例..."
if [ -f "/var/log/marketprism/incidents.log" ]; then
    tail -50 /var/log/marketprism/incidents.log >> docs/incident-history.md
fi

# 3. 生成配置文档
echo "3. 生成配置文档..."
docker-compose config > docs/current-configuration.yml

echo "=== 知识库更新完成 ==="
```

这些最佳实践将帮助运维团队高效、安全地管理MarketPrism智能监控告警系统，确保系统的稳定性和可靠性。
