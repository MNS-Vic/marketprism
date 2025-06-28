#!/bin/bash
# 腾讯云容器镜像服务配置脚本

echo "🏢 配置腾讯云容器镜像服务..."

# 1. 配置Docker daemon使用腾讯云镜像加速器
echo "⚙️ 配置Docker镜像加速器..."

# 创建Docker daemon配置目录
sudo mkdir -p /etc/docker

# 配置腾讯云镜像加速器
cat << 'EOF' | sudo tee /etc/docker/daemon.json
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://ccr.ccs.tencentyun.com"
  ],
  "insecure-registries": [
    "ccr.ccs.tencentyun.com"
  ],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m",
    "max-file": "3"
  }
}
EOF

# 2. 重启Docker服务
echo "🔄 重启Docker服务..."
if command -v systemctl > /dev/null; then
    sudo systemctl daemon-reload
    sudo systemctl restart docker
    echo "✅ Docker服务已重启"
else
    echo "⚠️ 请手动重启Docker Desktop"
fi

# 3. 验证配置
echo "🔍 验证镜像加速器配置..."
docker info | grep -A 10 "Registry Mirrors" || echo "配置验证失败"

# 4. 测试镜像拉取
echo "📦 测试镜像拉取..."
docker pull ccr.ccs.tencentyun.com/library/redis:7-alpine
if [ $? -eq 0 ]; then
    echo "✅ 腾讯云镜像拉取成功"
else
    echo "❌ 腾讯云镜像拉取失败"
fi

echo "🎉 腾讯云镜像服务配置完成！"
