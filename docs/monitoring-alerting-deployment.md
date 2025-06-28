# MarketPrism 智能监控告警系统部署指南

## 概述

MarketPrism智能监控告警系统是一个企业级的监控解决方案，提供多级告警、异常检测、故障预测和用户体验监控功能。

## 系统要求

### 硬件要求
- **CPU**: 最低2核，推荐4核以上
- **内存**: 最低4GB，推荐8GB以上
- **磁盘**: 最低20GB可用空间，推荐SSD
- **网络**: 稳定的网络连接，支持HTTP/HTTPS

### 软件要求
- **操作系统**: Linux (Ubuntu 20.04+, CentOS 8+) 或 Docker
- **Python**: 3.12+
- **Docker**: 20.10+ (可选)
- **Kubernetes**: 1.20+ (可选)

## 部署方式

### 方式一：Docker部署（推荐）

#### 1. 构建Docker镜像

```bash
# 进入服务目录
cd services/monitoring-alerting-service

# 构建镜像
docker build -t marketprism/monitoring-alerting:latest .
```

#### 2. 创建配置文件

创建 `docker-compose.yml`:

```yaml
version: '3.8'

services:
  monitoring-alerting:
    image: marketprism/monitoring-alerting:latest
    ports:
      - "8082:8082"
    environment:
      - SMTP_USERNAME=${SMTP_USERNAME}
      - SMTP_PASSWORD=${SMTP_PASSWORD}
      - SLACK_WEBHOOK_URL=${SLACK_WEBHOOK_URL}
      - JWT_SECRET=${JWT_SECRET}
    volumes:
      - ./config:/app/config
      - ./logs:/app/logs
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8082/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana-storage:/var/lib/grafana

volumes:
  grafana-storage:
```

#### 3. 启动服务

```bash
# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f monitoring-alerting
```

### 方式二：Kubernetes部署

#### 1. 创建命名空间

```yaml
# namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: marketprism-monitoring
```

#### 2. 创建ConfigMap

```yaml
# configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: monitoring-alerting-config
  namespace: marketprism-monitoring
data:
  config.yaml: |
    alert_manager:
      enabled: true
      evaluation_interval: 30
    notification_manager:
      enabled: true
      channels:
        email:
          enabled: true
          smtp_server: "smtp.gmail.com"
          smtp_port: 587
    # ... 其他配置
```

#### 3. 创建Deployment

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: monitoring-alerting
  namespace: marketprism-monitoring
spec:
  replicas: 2
  selector:
    matchLabels:
      app: monitoring-alerting
  template:
    metadata:
      labels:
        app: monitoring-alerting
    spec:
      containers:
      - name: monitoring-alerting
        image: marketprism/monitoring-alerting:latest
        ports:
        - containerPort: 8082
        env:
        - name: SMTP_USERNAME
          valueFrom:
            secretKeyRef:
              name: smtp-secret
              key: username
        - name: SMTP_PASSWORD
          valueFrom:
            secretKeyRef:
              name: smtp-secret
              key: password
        volumeMounts:
        - name: config
          mountPath: /app/config
        livenessProbe:
          httpGet:
            path: /health
            port: 8082
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /ready
            port: 8082
          initialDelaySeconds: 5
          periodSeconds: 10
      volumes:
      - name: config
        configMap:
          name: monitoring-alerting-config
```

#### 4. 创建Service

```yaml
# service.yaml
apiVersion: v1
kind: Service
metadata:
  name: monitoring-alerting-service
  namespace: marketprism-monitoring
spec:
  selector:
    app: monitoring-alerting
  ports:
  - port: 8082
    targetPort: 8082
  type: ClusterIP
```

#### 5. 部署到Kubernetes

```bash
# 应用所有配置
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml

# 检查部署状态
kubectl get pods -n marketprism-monitoring
kubectl get services -n marketprism-monitoring
```

### 方式三：直接部署

#### 1. 安装依赖

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

#### 2. 配置环境变量

```bash
# 创建 .env 文件
cat > .env << EOF
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
JWT_SECRET=your_jwt_secret_key
EOF
```

#### 3. 启动服务

```bash
# 启动监控告警服务
python services/monitoring-alerting-service/main.py
```

## 配置说明

### 核心配置项

#### 告警管理器配置
```yaml
alert_manager:
  enabled: true
  evaluation_interval: 30  # 评估间隔（秒）
  cleanup_interval: 3600   # 清理间隔（秒）
  max_active_alerts: 1000  # 最大活跃告警数
```

#### 通知配置
```yaml
notification_manager:
  channels:
    email:
      enabled: true
      smtp_server: "smtp.gmail.com"
      smtp_port: 587
      username: "${SMTP_USERNAME}"
      password: "${SMTP_PASSWORD}"
    
    slack:
      enabled: true
      webhook_url: "${SLACK_WEBHOOK_URL}"
      channel: "#alerts"
```

#### 异常检测配置
```yaml
anomaly_detection:
  enabled: true
  statistical:
    threshold: 2.0  # Z-score阈值
  ml:
    contamination: 0.1  # 异常比例
```

### 环境变量

| 变量名 | 描述 | 必需 | 默认值 |
|--------|------|------|--------|
| `SMTP_USERNAME` | SMTP用户名 | 是 | - |
| `SMTP_PASSWORD` | SMTP密码 | 是 | - |
| `SLACK_WEBHOOK_URL` | Slack Webhook URL | 否 | - |
| `JWT_SECRET` | JWT密钥 | 是 | - |
| `LOG_LEVEL` | 日志级别 | 否 | INFO |

## 监控和健康检查

### 健康检查端点

- **健康检查**: `GET /health`
- **就绪检查**: `GET /ready`
- **Prometheus指标**: `GET /metrics`

### 监控指标

系统提供以下关键指标：

- `marketprism_alert_total` - 告警总数
- `marketprism_alert_active` - 活跃告警数
- `marketprism_anomaly_detection_duration` - 异常检测耗时
- `marketprism_notification_sent_total` - 通知发送总数

### 日志配置

```yaml
logging:
  level: "INFO"
  format: "json"
  structured_fields:
    - "timestamp"
    - "level"
    - "logger"
    - "message"
    - "trace_id"
```

## 故障排除

### 常见问题

#### 1. 服务启动失败
```bash
# 检查日志
docker-compose logs monitoring-alerting

# 检查配置文件
docker-compose config
```

#### 2. 告警不发送
- 检查SMTP配置
- 验证Slack Webhook URL
- 查看通知管理器日志

#### 3. 异常检测不工作
- 确认有足够的历史数据
- 检查指标数据格式
- 验证检测器配置

#### 4. 性能问题
- 调整评估间隔
- 优化数据窗口大小
- 启用批处理模式

### 日志分析

```bash
# 查看错误日志
docker-compose logs monitoring-alerting | grep ERROR

# 查看告警创建日志
docker-compose logs monitoring-alerting | grep "创建告警"

# 查看性能指标
curl http://localhost:8082/api/v1/stats/performance
```

## 性能优化

### 配置优化

```yaml
performance:
  batch_processing:
    enabled: true
    batch_size: 100
    flush_interval_seconds: 5
  
  caching:
    enabled: true
    cache_size: 1000
    ttl_seconds: 300
  
  concurrency:
    max_workers: 10
    queue_size: 1000
```

### 资源限制

```yaml
# Kubernetes资源限制
resources:
  requests:
    memory: "512Mi"
    cpu: "250m"
  limits:
    memory: "2Gi"
    cpu: "1000m"
```

## 安全配置

### API认证

```yaml
security:
  api_auth:
    enabled: true
    jwt_secret: "${JWT_SECRET}"
    token_expiry_hours: 24
  
  access_control:
    enabled: true
    allowed_ips:
      - "10.0.0.0/8"
      - "172.16.0.0/12"
      - "192.168.0.0/16"
```

### HTTPS配置

```yaml
# 使用反向代理配置HTTPS
server:
  ssl:
    enabled: true
    cert_file: "/etc/ssl/certs/server.crt"
    key_file: "/etc/ssl/private/server.key"
```

## 备份和恢复

### 数据备份

```bash
# 备份配置文件
tar -czf config-backup-$(date +%Y%m%d).tar.gz config/

# 备份告警历史（如果使用持久化存储）
docker exec monitoring-alerting tar -czf /tmp/alerts-backup.tar.gz /app/data/
```

### 恢复流程

```bash
# 恢复配置
tar -xzf config-backup-20240101.tar.gz

# 重启服务
docker-compose restart monitoring-alerting
```

## 升级指南

### 版本升级

```bash
# 1. 备份当前配置
cp -r config config-backup

# 2. 拉取新镜像
docker pull marketprism/monitoring-alerting:latest

# 3. 更新服务
docker-compose up -d

# 4. 验证升级
curl http://localhost:8082/health
```

### 配置迁移

升级时可能需要更新配置文件格式，请参考版本发布说明。
