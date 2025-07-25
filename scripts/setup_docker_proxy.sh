#!/bin/bash
# Docker代理配置脚本

echo "🌐 配置Docker代理设置..."

# 1. 创建Docker daemon配置目录
sudo mkdir -p /etc/systemd/system/docker.service.d

# 2. 创建代理配置文件
cat << 'EOF' | sudo tee /etc/systemd/system/docker.service.d/http-proxy.conf
[Service]
Environment="HTTP_PROXY=http://127.0.0.1:7890"
Environment="HTTPS_PROXY=http://127.0.0.1:7890"
Environment="NO_PROXY=localhost,127.0.0.1,docker-registry.example.com,.corp"
EOF

# 3. 重新加载systemd配置
sudo systemctl daemon-reload

# 4. 重启Docker服务
sudo systemctl restart docker

# 5. 验证代理配置
echo "✅ Docker代理配置完成"
echo "验证配置："
sudo systemctl show --property=Environment docker

# 6. 配置Docker客户端代理（用于docker pull）
mkdir -p ~/.docker
cat << 'EOF' > ~/.docker/config.json
{
  "proxies": {
    "default": {
      "httpProxy": "http://127.0.0.1:7890",
      "httpsProxy": "http://127.0.0.1:7890",
      "noProxy": "localhost,127.0.0.1"
    }
  }
}
EOF

echo "✅ Docker客户端代理配置完成"

# 7. 测试代理连接
echo "🔍 测试代理连接..."
docker run --rm alpine/curl:latest curl -I https://www.google.com

echo "🎉 Docker代理配置完成！"
