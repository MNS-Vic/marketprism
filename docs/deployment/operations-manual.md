# MarketPrism 运维操作手册

## 📋 概述

本手册提供MarketPrism智能监控告警系统的日常运维操作指南，包括部署、监控、故障排除和维护等关键操作。

## 🚀 快速部署操作

### 1. 生产环境部署

```bash
# 方法1: 使用GitHub Actions (推荐)
# 1. 推送代码到main分支
git push origin main

# 2. 在GitHub Actions页面批准生产部署
# 访问: https://github.com/MNS-Vic/marketprism/actions
# 选择"Monitoring Alerting CI/CD"工作流
# 点击"Review deployments" -> "production" -> "Approve and deploy"

# 方法2: 使用本地部署脚本
./scripts/deploy-with-config-factory.sh -e production -m kubernetes
```

### 2. 测试环境部署

```bash
# 自动部署到staging (推送到develop分支)
git push origin develop

# 或手动部署
./scripts/deploy-with-config-factory.sh -e staging
```

### 3. 本地开发环境

```bash
# Docker Compose部署
./scripts/deploy-with-config-factory.sh -e staging -m docker-compose

# 或直接使用docker-compose
docker-compose up -d
```

## 📊 监控和健康检查

### 1. 服务状态检查

```bash
# Kubernetes环境
kubectl get pods -n marketprism-production
kubectl get svc -n marketprism-production
kubectl get ingress -n marketprism-production

# 检查服务健康状态
kubectl exec -it deployment/monitoring-alerting -n marketprism-production -- curl localhost:8082/health

# Docker Compose环境
docker-compose ps
docker-compose logs monitoring-alerting
```

### 2. 关键指标监控

```bash
# 检查API响应时间
curl -w "@curl-format.txt" -o /dev/null -s http://marketprism.example.com/health

# 检查Prometheus指标
curl http://marketprism.example.com/metrics | grep marketprism

# 检查数据库连接
kubectl exec -it deployment/postgres -n marketprism-production -- psql -U marketprism_user -d marketprism -c "SELECT 1;"
```

### 3. 日志查看

```bash
# Kubernetes日志
kubectl logs -f deployment/monitoring-alerting -n marketprism-production

# 查看最近的错误日志
kubectl logs deployment/monitoring-alerting -n marketprism-production --since=1h | grep ERROR

# Docker Compose日志
docker-compose logs -f monitoring-alerting
docker-compose logs --tail=100 monitoring-alerting
```

## 🔧 配置管理操作

### 1. 配置更新

```bash
# 验证配置更改
python scripts/validate-config-factory.py

# 应用配置更改 (Kubernetes)
kubectl create configmap marketprism-config \
  --from-file=config/new-structure/ \
  --namespace=marketprism-production \
  --dry-run=client -o yaml | kubectl apply -f -

# 重启服务以应用新配置
kubectl rollout restart deployment/monitoring-alerting -n marketprism-production
```

### 2. 密钥管理

```bash
# 更新数据库密码
kubectl create secret generic marketprism-secrets \
  --from-literal=postgres-password=NEW_PASSWORD \
  --namespace=marketprism-production \
  --dry-run=client -o yaml | kubectl apply -f -

# 重启相关服务
kubectl rollout restart deployment/monitoring-alerting -n marketprism-production
kubectl rollout restart deployment/postgres -n marketprism-production
```

### 3. 环境变量更新

```bash
# 更新部署中的环境变量
kubectl patch deployment monitoring-alerting -n marketprism-production -p \
  '{"spec":{"template":{"spec":{"containers":[{"name":"monitoring-alerting","env":[{"name":"LOG_LEVEL","value":"DEBUG"}]}]}}}}'
```

## 🔄 扩缩容操作

### 1. 手动扩缩容

```bash
# 扩展副本数
kubectl scale deployment monitoring-alerting --replicas=5 -n marketprism-production

# 检查扩容状态
kubectl get pods -l app=monitoring-alerting -n marketprism-production

# 查看HPA状态
kubectl get hpa -n marketprism-production
```

### 2. 资源限制调整

```bash
# 更新资源限制
kubectl patch deployment monitoring-alerting -n marketprism-production -p \
  '{"spec":{"template":{"spec":{"containers":[{"name":"monitoring-alerting","resources":{"limits":{"memory":"2Gi","cpu":"1000m"},"requests":{"memory":"1Gi","cpu":"500m"}}}]}}}}'
```

## 🔄 备份和恢复

### 1. 数据库备份

```bash
# PostgreSQL备份
kubectl exec deployment/postgres -n marketprism-production -- \
  pg_dump -U marketprism_user marketprism > backup-$(date +%Y%m%d-%H%M%S).sql

# Redis备份
kubectl exec deployment/redis -n marketprism-production -- \
  redis-cli BGSAVE

# 下载备份文件
kubectl cp marketprism-production/postgres-pod:/backup.sql ./backup.sql
```

### 2. 配置备份

```bash
# 备份ConfigMap
kubectl get configmap marketprism-config -n marketprism-production -o yaml > config-backup.yaml

# 备份Secrets
kubectl get secret marketprism-secrets -n marketprism-production -o yaml > secrets-backup.yaml
```

### 3. 数据恢复

```bash
# PostgreSQL恢复
kubectl exec -i deployment/postgres -n marketprism-production -- \
  psql -U marketprism_user marketprism < backup.sql

# 配置恢复
kubectl apply -f config-backup.yaml
kubectl apply -f secrets-backup.yaml
```

## 🚨 故障处理

### 1. 服务无响应

```bash
# 检查Pod状态
kubectl describe pod -l app=monitoring-alerting -n marketprism-production

# 检查资源使用
kubectl top pods -n marketprism-production

# 重启服务
kubectl rollout restart deployment/monitoring-alerting -n marketprism-production

# 强制删除Pod
kubectl delete pod -l app=monitoring-alerting -n marketprism-production
```

### 2. 数据库连接问题

```bash
# 检查数据库Pod状态
kubectl get pods -l app=postgres -n marketprism-production

# 测试数据库连接
kubectl exec -it deployment/monitoring-alerting -n marketprism-production -- \
  python -c "import psycopg2; conn = psycopg2.connect('postgresql://user:pass@postgres:5432/marketprism'); print('Connected')"

# 检查数据库日志
kubectl logs deployment/postgres -n marketprism-production
```

### 3. 内存/CPU问题

```bash
# 检查资源使用情况
kubectl top pods -n marketprism-production
kubectl describe nodes

# 临时增加资源限制
kubectl patch deployment monitoring-alerting -n marketprism-production -p \
  '{"spec":{"template":{"spec":{"containers":[{"name":"monitoring-alerting","resources":{"limits":{"memory":"4Gi","cpu":"2000m"}}}]}}}}'
```

## 🔄 版本更新

### 1. 滚动更新

```bash
# 更新镜像版本
kubectl set image deployment/monitoring-alerting \
  monitoring-alerting=ghcr.io/mns-vic/marketprism/monitoring-alerting:v1.2.0 \
  -n marketprism-production

# 检查更新状态
kubectl rollout status deployment/monitoring-alerting -n marketprism-production

# 查看更新历史
kubectl rollout history deployment/monitoring-alerting -n marketprism-production
```

### 2. 回滚操作

```bash
# 回滚到上一个版本
kubectl rollout undo deployment/monitoring-alerting -n marketprism-production

# 回滚到指定版本
kubectl rollout undo deployment/monitoring-alerting --to-revision=2 -n marketprism-production

# 验证回滚
kubectl get pods -l app=monitoring-alerting -n marketprism-production
```

## 📈 性能优化

### 1. 缓存优化

```bash
# 检查Redis缓存使用情况
kubectl exec deployment/redis -n marketprism-production -- redis-cli info memory

# 清理缓存
kubectl exec deployment/redis -n marketprism-production -- redis-cli FLUSHDB

# 调整缓存配置
kubectl exec deployment/redis -n marketprism-production -- \
  redis-cli CONFIG SET maxmemory 512mb
```

### 2. 数据库优化

```bash
# 检查数据库性能
kubectl exec deployment/postgres -n marketprism-production -- \
  psql -U marketprism_user -d marketprism -c "SELECT * FROM pg_stat_activity;"

# 分析慢查询
kubectl exec deployment/postgres -n marketprism-production -- \
  psql -U marketprism_user -d marketprism -c "SELECT query, mean_time FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"
```

## 🔒 安全操作

### 1. 密钥轮换

```bash
# 生成新密钥
NEW_PASSWORD=$(openssl rand -base64 32)

# 更新密钥
kubectl patch secret marketprism-secrets -n marketprism-production -p \
  "{\"data\":{\"postgres-password\":\"$(echo -n $NEW_PASSWORD | base64)\"}}"

# 重启服务
kubectl rollout restart deployment/monitoring-alerting -n marketprism-production
```

### 2. 网络策略更新

```bash
# 应用网络策略
kubectl apply -f k8s/production/network-policy.yaml

# 验证网络策略
kubectl get networkpolicy -n marketprism-production
```

## 📋 日常维护检查清单

### 每日检查
- [ ] 检查所有Pod运行状态
- [ ] 查看错误日志
- [ ] 验证健康检查端点
- [ ] 检查资源使用情况

### 每周检查
- [ ] 检查备份完整性
- [ ] 更新安全补丁
- [ ] 性能指标分析
- [ ] 容量规划评估

### 每月检查
- [ ] 安全审计
- [ ] 配置审查
- [ ] 灾难恢复演练
- [ ] 成本优化分析

## 📞 紧急联系

### 故障升级流程
1. **Level 1**: 自动告警和自愈
2. **Level 2**: 运维团队介入
3. **Level 3**: 开发团队支持
4. **Level 4**: 架构师和管理层

### 联系方式
- **运维值班**: 查看内部通讯录
- **开发团队**: GitHub Issues
- **紧急热线**: 查看项目README

---

*本手册定期更新，最后更新时间: 2025年6月22日*
