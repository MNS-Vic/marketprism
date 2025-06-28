# MarketPrism GitHub Actions 部署指南

## 📋 概述

MarketPrism智能监控告警系统提供完整的GitHub Actions CI/CD流水线，支持自动化构建、测试和部署到多个环境。

## 🚀 快速开始

### 1. 前置条件

- GitHub仓库已配置
- Docker Hub或GitHub Container Registry访问权限
- Kubernetes集群（可选）
- 必要的GitHub Secrets已配置

### 2. 基本部署流程

```bash
# 1. 推送代码到main分支触发生产部署
git push origin main

# 2. 推送代码到develop分支触发测试部署
git push origin develop

# 3. 手动触发部署
# 在GitHub Actions页面选择"MarketPrism Cloud Deployment"工作流
# 点击"Run workflow"并选择环境
```

## 🔧 GitHub Secrets 配置

### 必需的Secrets

在GitHub仓库的Settings > Secrets and variables > Actions中配置：

#### 容器注册表
```bash
GITHUB_TOKEN                 # 自动提供，用于GHCR访问
```

#### Kubernetes配置
```bash
KUBE_CONFIG_STAGING         # Staging环境kubeconfig (base64编码)
KUBE_CONFIG_PRODUCTION      # Production环境kubeconfig (base64编码)
```

#### 数据库密码
```bash
POSTGRES_PASSWORD           # PostgreSQL数据库密码
REDIS_PASSWORD             # Redis密码
```

#### 通知配置
```bash
SLACK_WEBHOOK_URL          # Slack通知Webhook URL (可选)
```

### Secrets配置示例

#### 1. 配置Kubernetes访问

```bash
# 获取kubeconfig并编码
cat ~/.kube/config | base64 -w 0

# 在GitHub Secrets中设置
# Name: KUBE_CONFIG_STAGING
# Value: <base64-encoded-kubeconfig>
```

#### 2. 配置数据库密码

```bash
# 生成安全密码
openssl rand -base64 32

# 在GitHub Secrets中设置
# Name: POSTGRES_PASSWORD
# Value: <generated-password>
```

## 📊 工作流说明

### 1. 监控告警服务CI/CD (`monitoring-alerting-ci.yml`)

**触发条件**:
- Push到main/develop分支
- 修改监控告警相关文件
- Pull Request到main分支

**流程阶段**:
1. **代码质量检查** - Black, Flake8, MyPy, Bandit
2. **单元测试** - 多Python版本测试
3. **集成测试** - Redis, ClickHouse集成
4. **Docker构建** - 多架构镜像
5. **安全扫描** - Trivy漏洞扫描
6. **部署测试环境** - 自动部署到staging
7. **部署生产环境** - 手动批准后部署

### 2. 统一配置工厂CI (`config-factory-ci.yml`)

**触发条件**:
- 修改配置工厂相关文件
- 修改配置文件

**验证内容**:
- 配置工厂功能测试
- 向后兼容性验证
- 环境变量覆盖测试
- 配置合并验证

### 3. 云端部署 (`cloud-deployment.yml`)

**支持的部署模式**:
- Docker Compose
- Docker Swarm
- Kubernetes

**手动触发参数**:
- `environment`: staging/production
- 支持工作流手动触发

## 🌐 部署环境

### Staging环境

**配置特点**:
- 自动部署（develop分支）
- 较少的资源配置
- 用于功能测试和验证

**访问地址**:
- API: `http://staging.marketprism.local:8082`
- 健康检查: `http://staging.marketprism.local:8082/health`

### Production环境

**配置特点**:
- 手动批准部署（main分支）
- 高可用配置（多副本）
- 自动扩缩容
- SSL/TLS加密

**访问地址**:
- API: `https://marketprism.example.com`
- 健康检查: `https://marketprism.example.com/health`

## 🛠️ 本地部署脚本

### 使用部署脚本

```bash
# 基本部署到staging
./scripts/deploy-with-config-factory.sh

# 部署到production环境
./scripts/deploy-with-config-factory.sh -e production

# 使用Kubernetes部署
./scripts/deploy-with-config-factory.sh -e production -m kubernetes

# 跳过验证和测试的快速部署
./scripts/deploy-with-config-factory.sh -e staging -s -t
```

### 脚本参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-e, --environment` | 部署环境 (staging/production) | staging |
| `-m, --mode` | 部署模式 (docker-compose/kubernetes) | docker-compose |
| `-s, --skip-validation` | 跳过配置验证 | false |
| `-t, --skip-tests` | 跳过测试 | false |
| `-h, --help` | 显示帮助信息 | - |

## 🔍 监控和日志

### 部署监控

**GitHub Actions监控**:
- 工作流执行状态
- 构建时间和成功率
- 部署频率统计

**应用监控**:
- Prometheus指标收集
- 健康检查端点
- 性能指标监控

### 日志查看

**GitHub Actions日志**:
```bash
# 在GitHub仓库中查看
Actions > 选择工作流 > 查看详细日志
```

**Kubernetes日志**:
```bash
# 查看Pod日志
kubectl logs -f deployment/monitoring-alerting -n marketprism-staging

# 查看事件
kubectl get events -n marketprism-staging --sort-by='.lastTimestamp'
```

**Docker Compose日志**:
```bash
# 查看服务日志
docker-compose logs -f monitoring-alerting

# 查看所有服务日志
docker-compose logs -f
```

## 🚨 故障排除

### 常见问题

#### 1. Docker权限问题

**问题**: `Permission denied` 错误

**解决方案**:
```bash
# 添加用户到docker组
sudo usermod -aG docker $USER

# 或使用sudo运行
sudo ./scripts/deploy-with-config-factory.sh
```

#### 2. Kubernetes连接问题

**问题**: `kubectl` 无法连接集群

**解决方案**:
```bash
# 检查kubeconfig
kubectl config current-context

# 验证集群连接
kubectl cluster-info

# 检查GitHub Secret配置
echo $KUBE_CONFIG_STAGING | base64 -d > kubeconfig
export KUBECONFIG=kubeconfig
kubectl get nodes
```

#### 3. 配置工厂验证失败

**问题**: 配置验证失败

**解决方案**:
```bash
# 手动运行验证
python scripts/validate-config-factory.py

# 检查配置文件
ls -la config/new-structure/

# 验证Python依赖
pip install -r services/monitoring-alerting-service/requirements.txt
```

#### 4. 镜像构建失败

**问题**: Docker镜像构建失败

**解决方案**:
```bash
# 检查Dockerfile
docker build -t test-image -f services/monitoring-alerting-service/Dockerfile .

# 检查依赖文件
cat services/monitoring-alerting-service/requirements.txt

# 验证基础镜像
docker pull python:3.12-slim
```

### 调试技巧

#### 1. 启用详细日志

在GitHub Actions中添加调试变量：
```yaml
env:
  ACTIONS_STEP_DEBUG: true
  ACTIONS_RUNNER_DEBUG: true
```

#### 2. 本地测试工作流

```bash
# 使用act工具本地运行GitHub Actions
act -j build-and-test

# 测试特定事件
act push -e .github/workflows/test-event.json
```

#### 3. 配置验证

```bash
# 验证所有配置
python scripts/validate-config-factory.py

# 测试配置加载
python -c "
from config.unified_config_loader import UnifiedConfigLoader
loader = UnifiedConfigLoader()
config = loader.load_service_config('monitoring-alerting-service')
print('配置加载成功')
"
```

## 📈 性能优化

### 构建优化

1. **Docker层缓存**: 使用GitHub Actions缓存
2. **并行构建**: 多架构并行构建
3. **依赖缓存**: pip缓存优化

### 部署优化

1. **滚动更新**: Kubernetes滚动更新策略
2. **健康检查**: 快速健康检查配置
3. **资源限制**: 合理的资源请求和限制

## 🔒 安全最佳实践

### 1. Secrets管理

- 使用GitHub Secrets存储敏感信息
- 定期轮换密码和密钥
- 最小权限原则

### 2. 镜像安全

- 定期更新基础镜像
- 使用Trivy进行漏洞扫描
- 签名和验证镜像

### 3. 网络安全

- 使用TLS加密
- 网络策略限制
- 定期安全审计

## 📋 检查清单

### 部署前检查

- [ ] GitHub Secrets已配置
- [ ] Kubernetes集群可访问
- [ ] 配置文件已验证
- [ ] 测试已通过
- [ ] 安全扫描已完成

### 部署后验证

- [ ] 服务健康检查通过
- [ ] API端点可访问
- [ ] 监控指标正常
- [ ] 日志输出正常
- [ ] 性能指标符合预期

这个指南提供了完整的GitHub Actions部署流程说明，包括配置、故障排除和最佳实践。
