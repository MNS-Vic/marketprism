# MarketPrism 智能监控告警系统生产环境优化指南

## 🎯 生产环境配置优化

### 1. 系统资源配置

#### 1.1 推荐硬件配置
```yaml
# 最小配置
minimum:
  cpu: 4核心
  memory: 8GB
  storage: 100GB SSD
  network: 1Gbps

# 推荐配置
recommended:
  cpu: 8核心
  memory: 16GB
  storage: 500GB NVMe SSD
  network: 10Gbps

# 高负载配置
high_load:
  cpu: 16核心
  memory: 32GB
  storage: 1TB NVMe SSD
  network: 10Gbps
```

#### 1.2 容器资源限制
```yaml
# Docker Compose 资源限制
services:
  monitoring-alerting:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G

  monitoring-dashboard:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 1G
```

### 2. 数据库优化

#### 2.1 Redis 优化配置
```redis
# redis.conf 生产环境配置
maxmemory 4gb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
tcp-keepalive 300
timeout 0
tcp-backlog 511
databases 16
```

#### 2.2 ClickHouse 优化配置
```xml
<!-- config.xml 生产环境配置 -->
<yandex>
    <max_connections>4096</max_connections>
    <keep_alive_timeout>3</keep_alive_timeout>
    <max_concurrent_queries>100</max_concurrent_queries>
    <uncompressed_cache_size>8589934592</uncompressed_cache_size>
    <mark_cache_size>5368709120</mark_cache_size>
    
    <!-- 数据压缩 -->
    <compression>
        <case>
            <method>lz4</method>
        </case>
    </compression>
    
    <!-- 日志配置 -->
    <logger>
        <level>information</level>
        <log>/var/log/clickhouse-server/clickhouse-server.log</log>
        <errorlog>/var/log/clickhouse-server/clickhouse-server.err.log</errorlog>
        <size>1000M</size>
        <count>10</count>
    </logger>
</yandex>
```

### 3. 应用程序优化

#### 3.1 Python 应用优化
```python
# 生产环境配置
PRODUCTION_CONFIG = {
    # 工作进程配置
    'MAX_WORKERS': 10,
    'WORKER_TIMEOUT': 30,
    'BATCH_SIZE': 100,
    
    # 缓存配置
    'CACHE_SIZE': 1000,
    'CACHE_TTL': 300,
    
    # 数据库连接池
    'DB_POOL_SIZE': 20,
    'DB_POOL_TIMEOUT': 30,
    
    # 日志配置
    'LOG_LEVEL': 'INFO',
    'LOG_FORMAT': 'json',
    'LOG_ROTATION': '100MB',
    
    # 性能优化
    'ENABLE_PROFILING': False,
    'ENABLE_METRICS': True,
    'METRICS_INTERVAL': 60,
}
```

#### 3.2 Next.js 前端优化
```javascript
// next.config.js 生产环境配置
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  compress: true,
  poweredByHeader: false,
  
  // 性能优化
  experimental: {
    optimizeCss: true,
    optimizePackageImports: ['lucide-react', '@radix-ui/react-icons'],
  },
  
  // 图片优化
  images: {
    formats: ['image/webp', 'image/avif'],
    minimumCacheTTL: 60,
  },
  
  // 安全头
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'Referrer-Policy',
            value: 'origin-when-cross-origin',
          },
        ],
      },
    ]
  },
}

module.exports = nextConfig
```

### 4. 网络和安全优化

#### 4.1 Nginx 反向代理配置
```nginx
# nginx.conf 生产环境配置
upstream monitoring_backend {
    server monitoring-alerting:8082;
    keepalive 32;
}

upstream dashboard_frontend {
    server monitoring-dashboard:3000;
    keepalive 32;
}

server {
    listen 80;
    listen 443 ssl http2;
    server_name monitoring.yourdomain.com;
    
    # SSL 配置
    ssl_certificate /etc/ssl/certs/monitoring.crt;
    ssl_certificate_key /etc/ssl/private/monitoring.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
    
    # 安全头
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains";
    
    # 前端路由
    location / {
        proxy_pass http://dashboard_frontend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
    
    # API 路由
    location /api/ {
        proxy_pass http://monitoring_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 超时配置
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }
    
    # 静态资源缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

#### 4.2 防火墙配置
```bash
# UFW 防火墙规则
ufw default deny incoming
ufw default allow outgoing

# 允许SSH
ufw allow 22/tcp

# 允许HTTP/HTTPS
ufw allow 80/tcp
ufw allow 443/tcp

# 允许内部服务通信
ufw allow from 172.20.0.0/16 to any port 8082
ufw allow from 172.20.0.0/16 to any port 3000
ufw allow from 172.20.0.0/16 to any port 6379
ufw allow from 172.20.0.0/16 to any port 8123

# 启用防火墙
ufw enable
```

### 5. 监控和日志优化

#### 5.1 日志轮转配置
```bash
# /etc/logrotate.d/marketprism
/var/log/marketprism/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 marketprism marketprism
    postrotate
        systemctl reload marketprism-monitoring
    endscript
}
```

#### 5.2 Prometheus 监控配置
```yaml
# prometheus.yml 生产环境配置
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: 'marketprism-production'
    environment: 'production'

rule_files:
  - "rules/*.yml"

scrape_configs:
  - job_name: 'monitoring-alerting'
    static_configs:
      - targets: ['monitoring-alerting:8082']
    scrape_interval: 30s
    metrics_path: '/metrics'
    
  - job_name: 'node-exporter'
    static_configs:
      - targets: ['node-exporter:9100']
    scrape_interval: 30s
    
  - job_name: 'redis-exporter'
    static_configs:
      - targets: ['redis-exporter:9121']
    scrape_interval: 30s

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093
```

### 6. 备份和恢复策略

#### 6.1 自动备份脚本
```bash
#!/bin/bash
# backup.sh - 自动备份脚本

BACKUP_DIR="/backup/marketprism"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=7

# 创建备份目录
mkdir -p "$BACKUP_DIR/$DATE"

# 备份Redis
docker exec marketprism-redis redis-cli BGSAVE
docker cp marketprism-redis:/data/dump.rdb "$BACKUP_DIR/$DATE/redis_dump.rdb"

# 备份ClickHouse
docker exec marketprism-clickhouse clickhouse-client --query "BACKUP DATABASE marketprism TO '/backup/clickhouse_$DATE.backup'"

# 备份配置文件
tar -czf "$BACKUP_DIR/$DATE/config.tar.gz" /opt/marketprism/config

# 清理旧备份
find "$BACKUP_DIR" -type d -mtime +$RETENTION_DAYS -exec rm -rf {} +

# 上传到云存储（可选）
# aws s3 sync "$BACKUP_DIR/$DATE" s3://marketprism-backups/
```

#### 6.2 恢复脚本
```bash
#!/bin/bash
# restore.sh - 数据恢复脚本

BACKUP_DATE="$1"
BACKUP_DIR="/backup/marketprism/$BACKUP_DATE"

if [ ! -d "$BACKUP_DIR" ]; then
    echo "备份目录不存在: $BACKUP_DIR"
    exit 1
fi

# 停止服务
docker-compose down

# 恢复Redis
docker cp "$BACKUP_DIR/redis_dump.rdb" marketprism-redis:/data/dump.rdb

# 恢复ClickHouse
docker exec marketprism-clickhouse clickhouse-client --query "RESTORE DATABASE marketprism FROM '/backup/clickhouse_$BACKUP_DATE.backup'"

# 恢复配置文件
tar -xzf "$BACKUP_DIR/config.tar.gz" -C /

# 重启服务
docker-compose up -d

echo "数据恢复完成"
```

### 7. 性能调优建议

#### 7.1 系统级优化
```bash
# /etc/sysctl.conf 系统参数优化
# 网络优化
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216
net.ipv4.tcp_congestion_control = bbr

# 文件描述符限制
fs.file-max = 1000000

# 内存管理
vm.swappiness = 10
vm.dirty_ratio = 15
vm.dirty_background_ratio = 5
```

#### 7.2 Docker 优化
```yaml
# docker-compose.override.yml 生产环境覆盖
version: '3.8'

services:
  monitoring-alerting:
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "3"
    restart: unless-stopped
    ulimits:
      nofile:
        soft: 65536
        hard: 65536
    
  redis:
    command: redis-server --appendonly yes --maxmemory 4gb --maxmemory-policy allkeys-lru
    
  clickhouse:
    ulimits:
      nofile:
        soft: 262144
        hard: 262144
```

### 8. 容量规划

#### 8.1 存储容量规划
```yaml
# 存储需求估算
daily_data_volume:
  alerts: 1GB
  metrics: 5GB
  logs: 2GB
  traces: 3GB
  total: 11GB

monthly_storage:
  raw_data: 330GB
  compressed: 100GB  # 压缩比 3:1
  backups: 50GB
  total: 480GB

yearly_storage:
  estimated: 6TB
  recommended: 10TB  # 包含增长空间
```

#### 8.2 网络带宽规划
```yaml
# 网络带宽需求
peak_traffic:
  api_requests: 1000 req/s
  data_ingestion: 100 MB/s
  dashboard_users: 50 concurrent
  total_bandwidth: 1 Gbps

average_traffic:
  api_requests: 200 req/s
  data_ingestion: 20 MB/s
  dashboard_users: 10 concurrent
  total_bandwidth: 200 Mbps
```

这些优化配置将确保MarketPrism智能监控告警系统在生产环境中的高性能、高可用性和安全性。
