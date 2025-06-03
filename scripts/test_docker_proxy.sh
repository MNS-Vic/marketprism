#!/bin/bash

# Docker代理测试脚本
echo "🧪 测试Docker代理连接..."

# 检测主机IP
if [[ "$OSTYPE" == "darwin"* ]]; then
    HOST_IP="host.docker.internal"
else
    HOST_IP="172.17.0.1"
fi

# 测试代理端口
for port in 1087 7890 8080; do
    echo -n "测试代理 $HOST_IP:$port... "
    if docker run --rm alpine:latest sh -c "
        apk add --no-cache curl >/dev/null 2>&1 && 
        curl -s -I --connect-timeout 3 --max-time 5 --proxy 'http://$HOST_IP:$port' https://www.google.com >/dev/null 2>&1
    "; then
        echo "✅ 成功"
        echo "可用代理: http://$HOST_IP:$port"
        exit 0
    else
        echo "❌ 失败"
    fi
done

echo "⚠️  所有代理测试失败，将使用直连构建"
