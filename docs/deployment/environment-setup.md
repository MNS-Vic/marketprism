# MarketPrism 环境配置和密钥设置指南

## 📋 概述

本指南详细说明如何配置MarketPrism智能监控告警系统的部署环境，包括GitHub Secrets、Kubernetes集群、数据库等关键组件的设置。

## 🔐 GitHub Secrets 配置

### 1. 访问GitHub Secrets设置

1. 进入GitHub仓库
2. 点击 `Settings` 标签
3. 在左侧菜单选择 `Secrets and variables` > `Actions`
4. 点击 `New repository secret`

### 2. 必需的Secrets列表

#### 容器注册表认证
```bash
# GitHub Container Registry (自动提供)
GITHUB_TOKEN                 # 自动生成，无需手动设置
```

#### Kubernetes集群配置
```bash
KUBE_CONFIG_STAGING         # Staging环境Kubernetes配置
KUBE_CONFIG_PRODUCTION      # Production环境Kubernetes配置
```

#### 数据库认证
```bash
POSTGRES_PASSWORD           # PostgreSQL数据库密码
REDIS_PASSWORD             # Redis缓存密码
```

#### 外部服务集成
```bash
SLACK_WEBHOOK_URL          # Slack通知Webhook (可选)
DISCORD_WEBHOOK_URL        # Discord通知Webhook (可选)
EMAIL_SMTP_PASSWORD        # SMTP邮件服务密码 (可选)
```

#### API密钥
```bash
BINANCE_API_KEY            # Binance API密钥 (可选)
BINANCE_SECRET_KEY         # Binance API密钥 (可选)
MONITORING_API_KEY         # 监控服务API密钥 (可选)
```

### 3. Secrets配置步骤

#### 配置Kubernetes访问

**Staging环境**:
```bash
# 1. 获取staging集群的kubeconfig
kubectl config view --raw --minify --context=staging-context > staging-kubeconfig.yaml

# 2. Base64编码
cat staging-kubeconfig.yaml | base64 -w 0

# 3. 在GitHub Secrets中创建
# Name: KUBE_CONFIG_STAGING
# Value: <base64-encoded-content>
```

**Production环境**:
```bash
# 1. 获取production集群的kubeconfig
kubectl config view --raw --minify --context=production-context > production-kubeconfig.yaml

# 2. Base64编码
cat production-kubeconfig.yaml | base64 -w 0

# 3. 在GitHub Secrets中创建
# Name: KUBE_CONFIG_PRODUCTION
# Value: <base64-encoded-content>
```

#### 配置数据库密码

**生成安全密码**:
```bash
# PostgreSQL密码
openssl rand -base64 32

# Redis密码
openssl rand -base64 24

# 或使用pwgen
pwgen -s 32 1
```

**设置Secrets**:
```bash
# Name: POSTGRES_PASSWORD
# Value: <generated-postgres-password>

# Name: REDIS_PASSWORD
# Value: <generated-redis-password>
```

#### 配置Slack通知

**获取Slack Webhook URL**:
1. 访问 https://api.slack.com/apps
2. 创建新应用或选择现有应用
3. 启用 "Incoming Webhooks"
4. 创建新的Webhook URL
5. 复制Webhook URL

**设置Secret**:
```bash
# Name: SLACK_WEBHOOK_URL
# Value: https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX
```

## 🏗️ Kubernetes集群设置

### 1. 集群要求

**最低配置**:
- Kubernetes 1.24+
- 2个节点（staging）/ 3个节点（production）
- 每节点最少2GB RAM, 2 CPU核心
- 支持LoadBalancer服务类型
- 支持PersistentVolume

**推荐配置**:
- Kubernetes 1.28+
- 3个节点（staging）/ 5个节点（production）
- 每节点4GB RAM, 4 CPU核心
- 网络策略支持
- 监控和日志收集

### 2. 集群初始化

#### 使用kubeadm创建集群

```bash
# 1. 初始化主节点
sudo kubeadm init --pod-network-cidr=10.244.0.0/16

# 2. 配置kubectl
mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config

# 3. 安装网络插件 (Flannel)
kubectl apply -f https://raw.githubusercontent.com/coreos/flannel/master/Documentation/kube-flannel.yml

# 4. 加入工作节点
kubeadm join <master-ip>:6443 --token <token> --discovery-token-ca-cert-hash <hash>
```

#### 使用云服务提供商

**AWS EKS**:
```bash
# 使用eksctl创建集群
eksctl create cluster --name marketprism-staging --region us-west-2 --nodes 3

# 获取kubeconfig
aws eks update-kubeconfig --region us-west-2 --name marketprism-staging
```

**Google GKE**:
```bash
# 创建集群
gcloud container clusters create marketprism-staging --num-nodes=3 --zone=us-central1-a

# 获取kubeconfig
gcloud container clusters get-credentials marketprism-staging --zone=us-central1-a
```

**Azure AKS**:
```bash
# 创建集群
az aks create --resource-group myResourceGroup --name marketprism-staging --node-count 3

# 获取kubeconfig
az aks get-credentials --resource-group myResourceGroup --name marketprism-staging
```

### 3. 集群配置验证

```bash
# 检查节点状态
kubectl get nodes

# 检查系统Pod
kubectl get pods -n kube-system

# 验证网络连接
kubectl run test-pod --image=busybox --rm -it --restart=Never -- nslookup kubernetes.default

# 测试存储
kubectl apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: test-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
EOF

kubectl get pvc test-pvc
kubectl delete pvc test-pvc
```

## 🗄️ 数据库设置

### 1. PostgreSQL配置

#### 使用Kubernetes部署

```yaml
# postgres-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: postgres-config
data:
  POSTGRES_DB: marketprism
  POSTGRES_USER: marketprism_user
  # POSTGRES_PASSWORD 通过Secret设置
```

#### 使用外部数据库

**AWS RDS**:
```bash
# 创建RDS实例
aws rds create-db-instance \
  --db-instance-identifier marketprism-postgres \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --master-username marketprism_user \
  --master-user-password <secure-password> \
  --allocated-storage 20
```

**Google Cloud SQL**:
```bash
# 创建Cloud SQL实例
gcloud sql instances create marketprism-postgres \
  --database-version=POSTGRES_13 \
  --tier=db-f1-micro \
  --region=us-central1
```

### 2. Redis配置

#### 使用Kubernetes部署

```yaml
# redis-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: redis-config
data:
  redis.conf: |
    maxmemory 256mb
    maxmemory-policy allkeys-lru
    save 900 1
    save 300 10
    save 60 10000
```

#### 使用外部Redis

**AWS ElastiCache**:
```bash
# 创建Redis集群
aws elasticache create-cache-cluster \
  --cache-cluster-id marketprism-redis \
  --cache-node-type cache.t3.micro \
  --engine redis \
  --num-cache-nodes 1
```

## 🌐 网络和安全配置

### 1. 网络策略

```yaml
# network-policy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: marketprism-network-policy
  namespace: marketprism-production
spec:
  podSelector:
    matchLabels:
      app: monitoring-alerting
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
    ports:
    - protocol: TCP
      port: 8082
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: postgres
    ports:
    - protocol: TCP
      port: 5432
  - to:
    - podSelector:
        matchLabels:
          app: redis
    ports:
    - protocol: TCP
      port: 6379
```

### 2. TLS/SSL配置

#### 使用cert-manager自动证书

```bash
# 安装cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# 创建ClusterIssuer
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@example.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF
```

## 📊 监控和日志配置

### 1. Prometheus监控

```yaml
# prometheus-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-config
data:
  prometheus.yml: |
    global:
      scrape_interval: 15s
    scrape_configs:
    - job_name: 'marketprism'
      static_configs:
      - targets: ['monitoring-alerting-service:8082']
      metrics_path: '/metrics'
```

### 2. 日志收集

```yaml
# fluentd-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: fluentd-config
data:
  fluent.conf: |
    <source>
      @type tail
      path /var/log/containers/*marketprism*.log
      pos_file /var/log/fluentd-containers.log.pos
      tag kubernetes.*
      format json
    </source>
    
    <match kubernetes.**>
      @type elasticsearch
      host elasticsearch.logging.svc.cluster.local
      port 9200
      index_name marketprism
    </match>
```

## 🔧 环境变量配置

### 1. 应用环境变量

```bash
# 基础配置
ENVIRONMENT=production
CONFIG_FACTORY_ENABLED=true
LOG_LEVEL=INFO

# 数据库配置
DATABASE_URL=postgresql://user:pass@host:5432/db
REDIS_URL=redis://:pass@host:6379/0

# 监控配置
PROMETHEUS_ENABLED=true
METRICS_PORT=8082

# 安全配置
JWT_SECRET_KEY=<secure-jwt-secret>
API_KEY=<secure-api-key>
```

### 2. Kubernetes环境变量

```yaml
env:
- name: ENVIRONMENT
  value: "production"
- name: CONFIG_FACTORY_ENABLED
  value: "true"
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: database-secret
      key: url
- name: REDIS_URL
  valueFrom:
    secretKeyRef:
      name: redis-secret
      key: url
```

## ✅ 配置验证

### 1. 验证脚本

```bash
#!/bin/bash
# validate-environment.sh

echo "🔍 验证环境配置..."

# 检查Kubernetes连接
if kubectl cluster-info > /dev/null 2>&1; then
    echo "✅ Kubernetes集群连接正常"
else
    echo "❌ Kubernetes集群连接失败"
    exit 1
fi

# 检查命名空间
if kubectl get namespace marketprism-staging > /dev/null 2>&1; then
    echo "✅ Staging命名空间存在"
else
    echo "⚠️  Staging命名空间不存在，将自动创建"
fi

# 检查Secrets
if kubectl get secret marketprism-secrets -n marketprism-staging > /dev/null 2>&1; then
    echo "✅ Secrets配置正常"
else
    echo "❌ Secrets配置缺失"
    exit 1
fi

echo "🎉 环境配置验证完成"
```

### 2. 配置检查清单

- [ ] GitHub Secrets已配置
- [ ] Kubernetes集群可访问
- [ ] 数据库连接正常
- [ ] Redis连接正常
- [ ] 网络策略已配置
- [ ] TLS证书已配置
- [ ] 监控系统已部署
- [ ] 日志收集已配置
- [ ] 环境变量已设置
- [ ] 安全策略已应用

这个指南提供了完整的环境配置步骤，确保MarketPrism系统能够在各种环境中正确部署和运行。
