# 🚀 MarketPrism生产环境部署指南

## 📋 部署前准备

### 系统要求
- **操作系统**: Ubuntu 20.04+ / CentOS 8+ / Docker支持的Linux发行版
- **内存**: 最低4GB，推荐8GB+
- **CPU**: 最低2核，推荐4核+
- **存储**: 最低20GB，推荐50GB+ SSD
- **网络**: 稳定的互联网连接，支持HTTPS

### 必需软件
```bash
# Docker和Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Git
sudo apt update && sudo apt install -y git curl

# 验证安装
docker --version
docker-compose --version
git --version
```

## 🔧 快速部署

### 1. 获取项目代码
```bash
# 克隆项目
git clone https://github.com/MNS-Vic/marketprism.git
cd marketprism

# 检查最新稳定版本
git checkout main
git pull origin main
```

### 2. 环境配置
```bash
# 复制环境配置模板
cp config/env.example .env

# 编辑环境配置
nano .env
```

**关键配置项**:
```bash
# 基础配置
ENV=production
LOG_LEVEL=INFO
DEBUG=false

# 数据库配置
POSTGRES_DB=marketprism
POSTGRES_USER=marketprism_user
POSTGRES_PASSWORD=your_secure_password_here

# Redis配置
REDIS_PASSWORD=your_redis_password_here

# API配置
RATE_LIMIT_ENABLED=true
API_TIMEOUT=30

# 监控配置
PROMETHEUS_ENABLED=true
METRICS_PORT=9090

# 告警系统配置
ALERTING_ENABLED=true
NOTIFICATION_CHANNELS=email,slack,log

# 邮件通知配置
ALERT_EMAIL_SMTP_HOST=smtp.your-domain.com
ALERT_EMAIL_SMTP_PORT=587
ALERT_EMAIL_USERNAME=alerts@your-domain.com
ALERT_EMAIL_PASSWORD=your_secure_email_password
ALERT_EMAIL_FROM=alerts@your-domain.com
ALERT_EMAIL_TO=admin@your-domain.com,ops@your-domain.com

# Slack通知配置
ALERT_SLACK_WEBHOOK=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK
ALERT_SLACK_CHANNEL=#alerts

# 钉钉通知配置
ALERT_DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN
ALERT_DINGTALK_SECRET=your_dingtalk_secret

# 企业微信通知配置
ALERT_WECHAT_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY
```

### 3. 网络配置 (如需要)
```bash
# 如果需要代理访问交易所API
nano config/proxy.yaml

# 配置示例
environments:
  production:
    data-collector:
      enabled: true  # 根据网络环境设置
      rest_api:
        http_proxy: "http://your-proxy:port"
        https_proxy: "http://your-proxy:port"
        timeout: 30
```

### 4. 启动服务
```bash
# 启动基础设施服务
docker-compose up -d redis postgres nats prometheus

# 等待服务启动 (约30秒)
sleep 30

# 检查服务状态
docker-compose ps

# 启动数据收集器
docker-compose up -d data-collector

# 查看启动日志
docker-compose logs -f data-collector
```

### 5. 验证部署
```bash
# 检查服务健康状态
curl http://localhost:8080/health

# 检查API连接
curl http://localhost:8080/api/v1/exchanges/binance/ping

# 检查监控指标
curl http://localhost:9090/metrics

# 检查数据收集状态
curl http://localhost:8080/api/v1/status

# 验证告警系统
python scripts/test_alerting_system.py

# 检查告警规则配置
curl http://localhost:8080/api/v1/alerts/rules

# 测试告警通知（可选）
curl -X POST http://localhost:8080/api/v1/alerts/test \
  -H "Content-Type: application/json" \
  -d '{"rule_name": "test_alert", "message": "部署验证测试告警"}'
```

## 📊 监控和维护

### 服务监控
```bash
# 查看所有服务状态
docker-compose ps

# 查看资源使用情况
docker stats

# 查看服务日志
docker-compose logs -f data-collector
docker-compose logs -f redis
docker-compose logs -f postgres
```

### 健康检查脚本
```bash
#!/bin/bash
# health_check.sh

echo "=== MarketPrism健康检查 ==="

# 检查容器状态
echo "1. 检查容器状态..."
docker-compose ps

# 检查API健康度
echo "2. 检查API健康度..."
curl -s http://localhost:8080/health | jq .

# 检查数据收集状态
echo "3. 检查数据收集状态..."
curl -s http://localhost:8080/api/v1/status | jq .

# 检查监控指标
echo "4. 检查监控指标..."
curl -s http://localhost:9090/api/v1/query?query=up | jq .

echo "=== 健康检查完成 ==="
```

### 日志管理
```bash
# 查看实时日志
docker-compose logs -f --tail=100 data-collector

# 日志轮转配置
# 在docker-compose.yml中添加:
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

## 🔒 安全配置

### 防火墙设置
```bash
# 开放必要端口
sudo ufw allow 8080/tcp  # API端口
sudo ufw allow 9090/tcp  # 监控端口
sudo ufw allow 22/tcp    # SSH端口

# 限制数据库端口访问 (仅本地)
sudo ufw deny 5432/tcp
sudo ufw deny 6379/tcp

# 启用防火墙
sudo ufw enable
```

### SSL/TLS配置 (推荐)
```bash
# 使用Let's Encrypt获取SSL证书
sudo apt install certbot
sudo certbot certonly --standalone -d your-domain.com

# 配置Nginx反向代理
sudo apt install nginx
```

**Nginx配置示例** (`/etc/nginx/sites-available/marketprism`):
```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /metrics {
        proxy_pass http://localhost:9090;
        # 限制访问
        allow 127.0.0.1;
        deny all;
    }
}
```

## 🔄 备份和恢复

### 数据备份
```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/backup/marketprism/$(date +%Y%m%d_%H%M%S)"
mkdir -p $BACKUP_DIR

# 备份PostgreSQL数据
docker-compose exec postgres pg_dump -U marketprism_user marketprism > $BACKUP_DIR/postgres_backup.sql

# 备份Redis数据
docker-compose exec redis redis-cli --rdb $BACKUP_DIR/redis_backup.rdb

# 备份配置文件
cp -r config/ $BACKUP_DIR/
cp .env $BACKUP_DIR/

echo "备份完成: $BACKUP_DIR"
```

### 数据恢复
```bash
#!/bin/bash
# restore.sh

BACKUP_DIR=$1

if [ -z "$BACKUP_DIR" ]; then
    echo "用法: ./restore.sh /path/to/backup"
    exit 1
fi

# 恢复PostgreSQL数据
docker-compose exec -T postgres psql -U marketprism_user marketprism < $BACKUP_DIR/postgres_backup.sql

# 恢复Redis数据
docker-compose stop redis
docker cp $BACKUP_DIR/redis_backup.rdb $(docker-compose ps -q redis):/data/dump.rdb
docker-compose start redis

echo "恢复完成"
```

## 📈 性能优化

### 资源限制配置
```yaml
# docker-compose.override.yml
version: '3.8'

services:
  data-collector:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '0.5'
        reservations:
          memory: 512M
          cpus: '0.25'

  redis:
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.2'

  postgres:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '0.3'
```

### 数据库优化
```sql
-- PostgreSQL性能优化
-- 在postgres容器中执行

-- 调整连接数
ALTER SYSTEM SET max_connections = 200;

-- 调整内存设置
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';

-- 重启PostgreSQL使配置生效
SELECT pg_reload_conf();
```

## 🚨 故障排除

### 常见问题

**1. 容器启动失败**
```bash
# 检查日志
docker-compose logs container_name

# 检查资源使用
docker system df
docker system prune  # 清理未使用的资源
```

**2. API连接超时**
```bash
# 检查网络连接
curl -v https://api.binance.com/api/v3/ping

# 检查代理配置
cat config/proxy.yaml

# 测试代理连接
curl --proxy http://proxy:port https://api.binance.com/api/v3/ping
```

**3. 数据库连接失败**
```bash
# 检查数据库状态
docker-compose exec postgres pg_isready -U marketprism_user

# 检查连接配置
echo $POSTGRES_URL

# 重置数据库连接
docker-compose restart postgres
```

**4. 内存不足**
```bash
# 检查内存使用
free -h
docker stats

# 清理Docker缓存
docker system prune -a

# 调整服务资源限制
nano docker-compose.override.yml
```

### 紧急恢复
```bash
#!/bin/bash
# emergency_recovery.sh

echo "开始紧急恢复..."

# 停止所有服务
docker-compose down

# 清理异常容器
docker container prune -f

# 重新启动基础服务
docker-compose up -d redis postgres nats

# 等待服务就绪
sleep 30

# 启动数据收集器
docker-compose up -d data-collector

# 验证恢复状态
curl http://localhost:8080/health

echo "紧急恢复完成"
```

## 📞 支持和联系

### 技术支持
- **GitHub Issues**: https://github.com/MNS-Vic/marketprism/issues
- **文档**: https://github.com/MNS-Vic/marketprism/docs
- **监控仪表板**: http://your-domain.com:9090

### 维护计划
- **日常检查**: 每日健康检查和日志审查
- **周度维护**: 系统更新和性能优化
- **月度备份**: 完整数据备份和恢复测试
- **季度升级**: 依赖更新和安全补丁

---

**部署指南版本**: v1.0  
**最后更新**: 2025-06-21  
**适用版本**: MarketPrism v1.0+
