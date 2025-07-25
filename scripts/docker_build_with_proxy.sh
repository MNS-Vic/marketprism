#!/bin/bash

# Docker代理构建脚本
set -e

# macOS Docker使用host.docker.internal访问宿主机
DOCKER_HOST_IP="host.docker.internal"

# 检测代理
if [ -n "$HTTP_PROXY" ]; then
    # 将127.0.0.1替换为Docker主机IP
    DOCKER_PROXY_URL=$(echo "$HTTP_PROXY" | sed "s/127\.0\.0\.1/$DOCKER_HOST_IP/g")
    PROXY_ARGS="--build-arg http_proxy=$DOCKER_PROXY_URL --build-arg https_proxy=$DOCKER_PROXY_URL"
    echo "🌐 使用代理构建: $DOCKER_PROXY_URL"
else
    PROXY_ARGS=""
    echo "🔗 直连构建（无代理）"
fi

# 构建函数
build_with_proxy() {
    local dockerfile=$1
    local tag=$2
    local context=${3:-.}
    
    echo "🚀 构建镜像: $tag"
    docker build $PROXY_ARGS -f "$dockerfile" -t "$tag" "$context"
}

# 导出函数
export -f build_with_proxy
export PROXY_ARGS

echo "✅ Docker代理构建环境已设置"
