#!/bin/bash

# 快速构建环境设置
set -e

echo "🔧 设置优化的构建环境..."

# 设置代理
export http_proxy=http://127.0.0.1:1087
export https_proxy=http://127.0.0.1:1087
export HTTP_PROXY=http://127.0.0.1:1087
export HTTPS_PROXY=http://127.0.0.1:1087
echo "✅ 代理已设置: http://127.0.0.1:1087"

# 设置包源
export PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple/
export PIP_TRUSTED_HOST=$(echo https://pypi.tuna.tsinghua.edu.cn/simple/ | sed 's|https\?://||' | cut -d/ -f1)
export GOPROXY=https://proxy.golang.org,direct
export GOSUMDB=off

echo "✅ Python包源: https://pypi.tuna.tsinghua.edu.cn/simple/"
echo "✅ Go代理: https://proxy.golang.org"
echo "✅ Docker镜像源: https://registry-1.docker.io"
echo "🎉 构建环境设置完成！"
