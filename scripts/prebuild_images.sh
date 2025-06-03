#!/bin/bash

# 预构建基础镜像脚本 - 代理支持版本
set -e

echo "🚀 开始预构建优化镜像..."

# 设置代理（如果可用）
if curl -I --connect-timeout 3 http://127.0.0.1:1087 >/dev/null 2>&1; then
    echo "🌐 检测到代理，启用代理构建..."
    export PROXY_ARGS="--build-arg http_proxy=http://127.0.0.1:1087 --build-arg https_proxy=http://127.0.0.1:1087"
else
    echo "🔗 直连构建..."
    export PROXY_ARGS=""
fi

# 使用官方镜像，支持代理
echo "📦 构建Python基础镜像..."
docker build $PROXY_ARGS -t marketprism/python-base:latest -f - . << 'DOCKERFILE'
FROM python:3.9-slim
ARG http_proxy
ARG https_proxy
ENV http_proxy=${http_proxy}
ENV https_proxy=${https_proxy}
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --upgrade pip \
    && useradd -m appuser
ENV PIP_INDEX_URL=https://pypi.org/simple/
ENV PIP_TRUSTED_HOST=pypi.org
# 清理代理环境变量
ENV http_proxy=
ENV https_proxy=
DOCKERFILE

echo "✅ Python基础镜像构建完成"

# 构建依赖层镜像
echo "📦 构建Python依赖镜像..."
docker build $PROXY_ARGS -t marketprism/python-deps:latest -f - . << 'DOCKERFILE'
FROM marketprism/python-base:latest
ARG http_proxy
ARG https_proxy
ENV http_proxy=${http_proxy}
ENV https_proxy=${https_proxy}
COPY requirements.txt /tmp/
RUN pip install --user --no-warn-script-location -r /tmp/requirements.txt
# 清理代理环境变量
ENV http_proxy=
ENV https_proxy=
DOCKERFILE

echo "✅ Python依赖镜像构建完成"

# 构建Go基础镜像
echo "📦 构建Go基础镜像..."
docker build $PROXY_ARGS -t marketprism/go-base:latest -f - . << 'DOCKERFILE'
FROM golang:1.20-alpine
ARG http_proxy
ARG https_proxy
ENV http_proxy=${http_proxy}
ENV https_proxy=${https_proxy}
RUN apk add --no-cache git ca-certificates tzdata curl
ENV CGO_ENABLED=0
ENV GOOS=linux
ENV GOARCH=amd64
ENV GOPROXY=https://proxy.golang.org,direct
# 清理代理环境变量
ENV http_proxy=
ENV https_proxy=
DOCKERFILE

echo "✅ Go基础镜像构建完成"

echo "🎉 预构建完成，后续构建将更快！"

# 显示构建的镜像
echo ""
echo "📋 构建的基础镜像："
docker images | grep "marketprism/"
