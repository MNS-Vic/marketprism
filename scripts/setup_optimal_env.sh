#!/bin/bash

# 最优环境变量设置 - 自动生成于 Sat May 24 12:59:44 CST 2025
echo "🔧 设置最优构建环境..."

# 设置代理
export http_proxy="http://127.0.0.1:1087"
export https_proxy="http://127.0.0.1:1087"
export HTTP_PROXY="http://127.0.0.1:1087"
export HTTPS_PROXY="http://127.0.0.1:1087"
echo "✅ 代理: http://127.0.0.1:1087"

# 设置包源
export PIP_INDEX_URL="https://repo.huaweicloud.com/repository/pypi/simple/"
export PIP_TRUSTED_HOST=$(echo "https://repo.huaweicloud.com/repository/pypi/simple/" | sed 's|https\?://||' | cut -d/ -f1)
export GOPROXY="https://goproxy.io,direct"
export GOSUMDB=off

# Docker主机IP
if [[ "$OSTYPE" == "darwin"* ]]; then
    export DOCKER_HOST_IP="host.docker.internal"
else
    export DOCKER_HOST_IP="172.17.0.1"
fi

echo "✅ Python包源: https://repo.huaweicloud.com/repository/pypi/simple/"
echo "✅ Go代理: https://goproxy.io"
echo "✅ Docker镜像源: https://mirror.ccs.tencentyun.com"
echo "🎉 最优环境设置完成！"
