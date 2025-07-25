# MarketPrism 智能监控告警系统完整部署指南

## 📋 文档概览

本指南提供了MarketPrism智能监控告警系统的完整部署流程，包括前端UI、后端服务、数据库和监控组件的集成部署。

## 🎯 系统架构

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   前端仪表板     │    │   后端API服务    │    │   数据存储层     │
│  (Next.js)     │────│  (Python)      │────│  Redis+ClickHouse│
│  Port: 3000    │    │  Port: 8082    │    │  Port: 6379,8123│
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │   监控组件       │
                    │ Prometheus+     │
                    │ Grafana+Jaeger  │
                    └─────────────────┘
```

## 🚀 快速部署

### 方式一：Docker Compose 部署（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/your-org/marketprism.git
cd marketprism

# 2. 配置环境变量
cp deployments/docker-compose/.env.example deployments/docker-compose/.env
# 编辑 .env 文件，配置必要的参数

# 3. 启动所有服务
cd deployments/docker-compose
docker-compose up -d

# 4. 验证部署
./scripts/test-deployment.sh
```

### 方式二：Kubernetes 部署

```bash
# 1. 应用Kubernetes配置
kubectl apply -f deployments/kubernetes/

# 2. 等待Pod就绪
kubectl wait --for=condition=ready pod -l app=monitoring-alerting -n marketprism-monitoring

# 3. 验证部署
kubectl get pods -n marketprism-monitoring
```

## 📦 组件详细说明

### 1. 前端仪表板 (monitoring-dashboard)
- **技术栈**: Next.js 15 + React 19 + Radix UI + Tailwind CSS
- **端口**: 3000
- **功能**: 
  - 实时监控仪表板
  - 智能告警管理
  - 异常检测界面
  - 故障预测展示

### 2. 后端API服务 (monitoring-alerting)
- **技术栈**: Python 3.12 + FastAPI + SQLAlchemy
- **端口**: 8082
- **功能**:
  - 告警管理引擎
  - 异常检测算法
  - 故障预测模型
  - 通知管理系统

### 3. 数据存储层
- **Redis**: 缓存和会话存储
- **ClickHouse**: 时序数据和告警历史
- **配置**: 优化的生产环境配置

### 4. 监控组件
- **Prometheus**: 指标收集
- **Grafana**: 数据可视化
- **Jaeger**: 分布式追踪

## 🔧 详细部署步骤

### 步骤1: 环境准备

#### 1.1 系统要求
```yaml
minimum_requirements:
  cpu: 4核心
  memory: 8GB
  storage: 100GB SSD
  os: Ubuntu 20.04+ / CentOS 8+

recommended_requirements:
  cpu: 8核心
  memory: 16GB
  storage: 500GB NVMe SSD
  network: 1Gbps+
```

#### 1.2 软件依赖
```bash
# Docker 和 Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 验证安装
docker --version
docker-compose --version
```

### 步骤2: 项目配置

#### 2.1 获取项目代码
```bash
git clone https://github.com/your-org/marketprism.git
cd marketprism
```

#### 2.2 环境变量配置
```bash
# 复制环境配置模板
cp deployments/docker-compose/.env.example deployments/docker-compose/.env

# 编辑配置文件
nano deployments/docker-compose/.env
```

**关键配置项**:
```env
# 基础配置
ENVIRONMENT=production
DOMAIN=your-domain.com

# 服务端口
MONITORING_PORT=8082
DASHBOARD_PORT=3000

# 数据库配置
REDIS_PASSWORD=your_secure_redis_password
CLICKHOUSE_USER=marketprism_user
CLICKHOUSE_PASSWORD=your_secure_clickhouse_password

# 通知配置
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK

# 安全配置
JWT_SECRET=your_very_secure_jwt_secret_key_here_at_least_32_characters
API_KEY=your_api_key_here
```

### 步骤3: 服务部署

#### 3.1 使用部署脚本
```bash
# 使用自动化部署脚本
./scripts/deploy.sh docker-compose production latest

# 或者手动部署
cd deployments/docker-compose
docker-compose up -d
```

#### 3.2 验证部署状态
```bash
# 检查服务状态
docker-compose ps

# 查看服务日志
docker-compose logs -f monitoring-alerting
docker-compose logs -f monitoring-dashboard

# 执行健康检查
curl http://localhost:8082/health
curl http://localhost:3000
```

### 步骤4: 部署验证

#### 4.1 功能测试
```bash
# 执行完整的部署测试
./scripts/test-deployment.sh

# 执行性能测试
./scripts/load-test.sh http://localhost:8082 300 50

# 执行安全测试
./scripts/security-test.sh http://localhost:8082 docker-compose
```

#### 4.2 UI功能验证
1. 访问前端仪表板: `http://localhost:3000`
2. 检查以下功能:
   - ✅ 仪表板数据加载
   - ✅ 告警列表显示
   - ✅ 异常检测功能
   - ✅ 故障预测功能
   - ✅ 实时数据更新

#### 4.3 API功能验证
```bash
# 测试关键API端点
curl http://localhost:8082/api/v1/alerts
curl http://localhost:8082/api/v1/rules
curl http://localhost:8082/api/v1/metrics/business
curl -X POST http://localhost:8082/api/v1/anomaly/detect \
  -H "Content-Type: application/json" \
  -d '{"metric_name": "test_metric", "value": 100.0}'
```

## 🔒 安全配置

### SSL/TLS 配置
```bash
# 生成SSL证书（生产环境使用Let's Encrypt）
sudo certbot --nginx -d monitoring.yourdomain.com

# 或使用自签名证书（仅测试环境）
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/monitoring.key \
  -out /etc/ssl/certs/monitoring.crt
```

### 防火墙配置
```bash
# 配置UFW防火墙
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

## 📊 监控配置

### Prometheus 配置
```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'monitoring-alerting'
    static_configs:
      - targets: ['monitoring-alerting:8082']
```

### Grafana 仪表板
1. 访问 Grafana: `http://localhost:3000`
2. 导入预配置的仪表板
3. 配置数据源连接

## 🔄 运维管理

### 日常运维命令
```bash
# 查看系统状态
./scripts/ops-automation.sh status

# 执行健康检查
./scripts/ops-automation.sh health --verbose

# 查看服务日志
./scripts/ops-automation.sh logs --tail=100 --follow

# 重启服务
./scripts/ops-automation.sh restart --force

# 创建备份
./scripts/ops-automation.sh backup

# 清理旧数据
./scripts/ops-automation.sh cleanup --days=7
```

### 扩容操作
```bash
# 水平扩容（增加实例）
./scripts/ops-automation.sh scale --replicas=3

# 垂直扩容（增加资源）
# 编辑 docker-compose.yml 中的资源限制
docker-compose up -d --force-recreate
```

## 🆙 升级流程

### 版本升级
```bash
# 1. 备份当前版本
./scripts/ops-automation.sh backup --force

# 2. 拉取新版本
git pull origin main

# 3. 更新服务
./scripts/ops-automation.sh update v1.1.0 --force

# 4. 验证升级
./scripts/test-deployment.sh
```

### 回滚操作
```bash
# 如果升级失败，执行回滚
./scripts/ops-automation.sh rollback --force

# 或使用GitHub Actions回滚工作流
# 在GitHub Actions中触发回滚流水线
```

## 🔧 故障排除

### 常见问题
1. **服务启动失败**: 检查端口冲突和环境变量
2. **数据库连接失败**: 验证数据库服务状态和连接配置
3. **前端无法访问**: 检查网络配置和防火墙设置
4. **API数据加载失败**: 验证后端服务状态和CORS配置

### 诊断工具
```bash
# 系统诊断
./scripts/ops-automation.sh monitor

# 性能分析
./scripts/ops-automation.sh performance

# 安全检查
./scripts/ops-automation.sh security
```

## 📚 相关文档

- [生产环境优化指南](production-optimization.md)
- [故障排除指南](troubleshooting-guide.md)
- [运维最佳实践](operations-best-practices.md)
- [部署检查清单](deployment-checklist.md)
- [API文档](api-documentation.md)

## 🆘 技术支持

如需技术支持，请联系：
- 📧 邮箱: support@marketprism.com
- 📖 文档: https://docs.marketprism.com
- 🐛 问题反馈: https://github.com/marketprism/issues

---

**MarketPrism Team** - 构建下一代智能监控系统
