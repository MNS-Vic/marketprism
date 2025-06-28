#!/bin/bash
# MarketPrism代理部署脚本

echo "🌐 MarketPrism代理部署开始..."

# 设置代理环境变量
export HTTP_PROXY="http://127.0.0.1:7890"
export HTTPS_PROXY="http://127.0.0.1:7890"
export NO_PROXY="localhost,127.0.0.1,redis,postgres,nats,prometheus"

# 更新.env文件中的代理配置
echo "⚙️ 更新环境配置..."
cat >> .env << EOF

# 代理配置
HTTP_PROXY=${HTTP_PROXY}
HTTPS_PROXY=${HTTPS_PROXY}
NO_PROXY=${NO_PROXY}
PROXY_ENABLED=true
EOF

echo "✅ 代理环境变量已设置"

# 1. 停止现有服务
echo "🛑 停止现有服务..."
docker-compose -f docker-compose.proxy.yml down

# 2. 清理Docker缓存
echo "🧹 清理Docker缓存..."
docker system prune -f

# 3. 拉取镜像（使用代理）
echo "📦 拉取Docker镜像..."
docker-compose -f docker-compose.proxy.yml pull

# 4. 构建自定义镜像（如果需要）
echo "🔨 构建应用镜像..."
docker-compose -f docker-compose.proxy.yml build --build-arg HTTP_PROXY=$HTTP_PROXY --build-arg HTTPS_PROXY=$HTTPS_PROXY

# 5. 启动基础设施服务
echo "🏗️ 启动基础设施服务..."
docker-compose -f docker-compose.proxy.yml up -d redis postgres nats prometheus

# 等待服务启动
echo "⏳ 等待基础设施服务启动..."
sleep 30

# 6. 检查基础设施服务状态
echo "🔍 检查服务状态..."
docker-compose -f docker-compose.proxy.yml ps

# 7. 启动数据收集器
echo "🚀 启动数据收集器..."
docker-compose -f docker-compose.proxy.yml up -d data-collector

# 等待应用启动
echo "⏳ 等待应用启动..."
sleep 20

# 8. 验证部署
echo "✅ 验证部署状态..."

# 检查所有服务状态
docker-compose -f docker-compose.proxy.yml ps

# 检查健康状态
echo "🔍 检查服务健康状态..."
for i in {1..12}; do
    if curl -s http://localhost:8080/health > /dev/null; then
        echo "✅ 应用健康检查通过"
        break
    else
        echo "⏳ 等待应用启动... ($i/12)"
        sleep 10
    fi
done

# 9. 运行验证测试
echo "🧪 运行验证测试..."

# API连接测试
echo "测试API连接..."
curl -s http://localhost:8080/health | jq '.' || echo "API健康检查失败"

# Prometheus指标测试
echo "测试Prometheus指标..."
curl -s http://localhost:9090/metrics | head -5 || echo "Prometheus指标获取失败"

# 10. 显示服务信息
echo "📊 部署完成！服务信息："
echo "- 应用API: http://localhost:8080"
echo "- 健康检查: http://localhost:8080/health"
echo "- Prometheus: http://localhost:9090"
echo "- Redis: localhost:6379"
echo "- PostgreSQL: localhost:5432"

# 11. 显示日志
echo "📝 最近的应用日志："
docker-compose -f docker-compose.proxy.yml logs --tail=10 data-collector

echo "🎉 MarketPrism代理部署完成！"
