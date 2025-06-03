#!/bin/bash

# 快速重建单个服务
SERVICE=${1:-"go-collector"}

echo "🔄 快速重建服务: $SERVICE"

# 只重建指定服务
docker-compose build --no-cache $SERVICE

# 重启服务
docker-compose up -d $SERVICE

echo "✅ 服务 $SERVICE 重建完成"
