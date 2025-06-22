# 🚀 MarketPrism部署解决方案指南

## 📋 方案概览

基于当前的部署问题，我们提供了三种完整的解决方案：

| 方案 | 适用场景 | 复杂度 | 推荐指数 |
|------|----------|--------|----------|
| **方案一：Docker代理配置** | 本地开发，有稳定代理 | ⭐⭐ | ⭐⭐⭐⭐ |
| **方案二：腾讯云镜像源** | 中国大陆用户，网络限制 | ⭐⭐⭐ | ⭐⭐⭐ |
| **方案三：GitHub Actions云端** | 完全云端部署，避免本地问题 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

## 🌐 方案一：Docker网络代理配置

### **适用场景**
- 有稳定的代理服务器（如Clash、V2Ray等）
- 希望在本地开发和测试
- 网络环境需要代理访问外部资源

### **执行步骤**

#### 1. 启动代理服务
```bash
# 确保代理服务运行在 127.0.0.1:7890
# 测试代理连接
curl --proxy http://127.0.0.1:7890 https://www.google.com
```

#### 2. 配置Docker代理
```bash
# 运行Docker代理配置脚本
chmod +x scripts/setup_docker_proxy.sh
sudo ./scripts/setup_docker_proxy.sh
```

#### 3. 执行代理部署
```bash
# 使用代理部署脚本
chmod +x scripts/deploy_with_proxy.sh
./scripts/deploy_with_proxy.sh
```

#### 4. 验证部署
```bash
# 验证代理配置
chmod +x scripts/verify_proxy_setup.sh
./scripts/verify_proxy_setup.sh

# 检查服务状态
docker-compose -f docker-compose.proxy.yml ps
curl http://localhost:8080/health
```

### **可能遇到的问题**
- **代理连接失败**: 检查代理服务是否运行，端口是否正确
- **Docker daemon代理配置**: 可能需要重启Docker服务
- **容器内网络访问**: 确保使用 `host.docker.internal` 访问宿主机代理

---

## 🏢 方案二：腾讯云镜像源配置

### **适用场景**
- 中国大陆用户，访问Docker Hub较慢
- 企业环境，有网络限制
- 希望使用国内镜像加速

### **执行步骤**

#### 1. 配置腾讯云镜像加速器
```bash
# 运行腾讯云镜像配置脚本
chmod +x scripts/setup_tencent_registry.sh
sudo ./scripts/setup_tencent_registry.sh
```

#### 2. 验证镜像可用性
```bash
# 测试腾讯云镜像拉取
docker pull ccr.ccs.tencentyun.com/library/redis:7-alpine
docker pull ccr.ccs.tencentyun.com/library/postgres:15-alpine
```

#### 3. 执行腾讯云部署
```bash
# 使用腾讯云部署脚本
chmod +x scripts/deploy_with_tencent.sh
./scripts/deploy_with_tencent.sh
```

#### 4. 验证部署
```bash
# 检查服务状态
docker-compose -f docker-compose.tencent.yml ps
curl http://localhost:8080/health

# 查看部署报告
cat tencent_deployment_report.txt
```

### **可能遇到的问题**
- **镜像不存在**: 某些镜像可能在腾讯云镜像仓库中不可用
- **认证问题**: 可能需要登录腾讯云容器镜像服务
- **网络问题**: 仍可能遇到网络连接问题

---

## ☁️ 方案三：GitHub Actions云端部署（推荐）

### **适用场景**
- 完全避免本地网络问题
- 希望使用CI/CD最佳实践
- 需要自动化部署流程
- 团队协作开发

### **执行步骤**

#### 1. 配置GitHub Secrets
```bash
# 安装GitHub CLI（如果未安装）
# macOS: brew install gh
# Ubuntu: sudo apt install gh

# 配置GitHub Secrets
chmod +x scripts/setup_github_secrets.sh
./scripts/setup_github_secrets.sh
```

#### 2. 提交代码并推送
```bash
# 提交所有更改
git add .
git commit -m "Setup cloud deployment with GitHub Actions

- Add cloud deployment workflow
- Configure Docker Swarm deployment
- Setup monitoring and validation
- Add deployment scripts and documentation"

# 推送到GitHub
git push origin main
```

#### 3. 触发云端部署
```bash
# 使用脚本触发部署
chmod +x scripts/trigger_cloud_deployment.sh
./scripts/trigger_cloud_deployment.sh

# 或者手动触发
gh workflow run cloud-deployment.yml --field environment=staging
```

#### 4. 监控部署进度
```bash
# 使用监控脚本
python scripts/monitor_cloud_deployment.py

# 或者使用GitHub CLI
gh run list --workflow=cloud-deployment.yml
gh run watch [RUN_ID]
```

#### 5. 验证云端部署
```bash
# 下载部署报告
gh run download [RUN_ID]

# 检查部署状态
cat deployment-report.md
```

### **优势**
- ✅ 完全避免本地网络问题
- ✅ 使用GitHub的网络环境
- ✅ 自动化CI/CD流程
- ✅ 详细的部署日志和报告
- ✅ 支持多环境部署（staging/production）
- ✅ 内置监控和验证

### **可能遇到的问题**
- **GitHub Actions配额**: 免费账户有使用限制
- **Secrets配置**: 需要正确配置敏感信息
- **Docker Swarm**: 需要了解Docker Swarm基础概念

---

## 🎯 推荐执行顺序

### **首选方案：GitHub Actions云端部署**
```bash
# 1. 配置GitHub环境
./scripts/setup_github_secrets.sh

# 2. 提交并推送代码
git add . && git commit -m "Setup cloud deployment" && git push

# 3. 触发云端部署
./scripts/trigger_cloud_deployment.sh

# 4. 监控部署进度
python scripts/monitor_cloud_deployment.py
```

### **备选方案：Docker代理配置**
```bash
# 1. 确保代理服务运行
curl --proxy http://127.0.0.1:7890 https://www.google.com

# 2. 配置Docker代理
sudo ./scripts/setup_docker_proxy.sh

# 3. 执行代理部署
./scripts/deploy_with_proxy.sh

# 4. 验证部署
./scripts/verify_proxy_setup.sh
```

### **最后选择：腾讯云镜像源**
```bash
# 1. 配置腾讯云镜像
sudo ./scripts/setup_tencent_registry.sh

# 2. 执行腾讯云部署
./scripts/deploy_with_tencent.sh

# 3. 检查部署状态
docker-compose -f docker-compose.tencent.yml ps
```

## 🔧 故障排除

### **通用问题**
1. **权限问题**: 确保脚本有执行权限 `chmod +x script.sh`
2. **Docker未运行**: 启动Docker Desktop或Docker daemon
3. **端口冲突**: 检查8080、9090等端口是否被占用
4. **网络连接**: 测试基础网络连接

### **获取帮助**
- 查看详细日志: `docker-compose logs [service-name]`
- 检查服务状态: `docker-compose ps`
- 运行健康检查: `curl http://localhost:8080/health`
- 查看GitHub Actions日志: `gh run view [RUN_ID]`

## 📞 支持

如果遇到问题：
1. 查看相关脚本的输出日志
2. 检查Docker和网络状态
3. 参考故障排除部分
4. 查看GitHub Actions工作流日志

---

**选择最适合您环境的方案，按照步骤执行即可完成MarketPrism的部署！** 🚀
