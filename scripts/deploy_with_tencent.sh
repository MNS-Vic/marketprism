#!/bin/bash
# MarketPrism腾讯云部署脚本

echo "🏢 MarketPrism腾讯云部署开始..."

# 1. 配置腾讯云镜像加速器
echo "⚙️ 配置腾讯云镜像加速器..."
./scripts/setup_tencent_registry.sh

# 2. 验证镜像可用性
echo "🔍 验证腾讯云镜像可用性..."
test_images=(
    "ccr.ccs.tencentyun.com/library/redis:7-alpine"
    "ccr.ccs.tencentyun.com/library/postgres:15-alpine"
    "ccr.ccs.tencentyun.com/library/nats:2-alpine"
    "ccr.ccs.tencentyun.com/library/prometheus:latest"
)

for image in "${test_images[@]}"; do
    echo "测试镜像: $image"
    if docker pull "$image" > /dev/null 2>&1; then
        echo "✅ $image 拉取成功"
    else
        echo "❌ $image 拉取失败"
        # 尝试使用官方镜像作为备选
        official_image=$(echo "$image" | sed 's|ccr.ccs.tencentyun.com/library/||')
        echo "尝试官方镜像: $official_image"
        docker pull "$official_image"
    fi
done

# 3. 停止现有服务
echo "🛑 停止现有服务..."
docker-compose -f docker-compose.tencent.yml down

# 4. 清理Docker资源
echo "🧹 清理Docker资源..."
docker system prune -f

# 5. 拉取所有镜像
echo "📦 拉取所有镜像..."
docker-compose -f docker-compose.tencent.yml pull

# 6. 构建应用镜像
echo "🔨 构建应用镜像..."
docker-compose -f docker-compose.tencent.yml build

# 7. 启动基础设施服务
echo "🏗️ 启动基础设施服务..."
docker-compose -f docker-compose.tencent.yml up -d redis postgres nats prometheus

# 等待服务启动
echo "⏳ 等待基础设施服务启动..."
sleep 30

# 8. 检查基础设施服务健康状态
echo "🔍 检查基础设施服务健康状态..."
for service in redis postgres nats prometheus; do
    echo "检查 $service 服务..."
    for i in {1..6}; do
        if docker-compose -f docker-compose.tencent.yml ps $service | grep -q "healthy\|Up"; then
            echo "✅ $service 服务正常"
            break
        else
            echo "⏳ 等待 $service 服务启动... ($i/6)"
            sleep 10
        fi
    done
done

# 9. 启动数据收集器
echo "🚀 启动数据收集器..."
docker-compose -f docker-compose.tencent.yml up -d data-collector

# 等待应用启动
echo "⏳ 等待应用启动..."
sleep 30

# 10. 验证部署
echo "✅ 验证部署状态..."

# 检查所有服务状态
echo "📊 服务状态："
docker-compose -f docker-compose.tencent.yml ps

# 检查应用健康状态
echo "🔍 检查应用健康状态..."
for i in {1..12}; do
    if curl -s http://localhost:8080/health > /dev/null; then
        echo "✅ 应用健康检查通过"
        break
    else
        echo "⏳ 等待应用启动... ($i/12)"
        sleep 10
    fi
done

# 11. 运行API测试
echo "🧪 运行API测试..."

# 健康检查
echo "测试健康检查API..."
health_response=$(curl -s http://localhost:8080/health)
if [ $? -eq 0 ]; then
    echo "✅ 健康检查API正常: $health_response"
else
    echo "❌ 健康检查API失败"
fi

# Prometheus指标
echo "测试Prometheus指标..."
if curl -s http://localhost:9090/metrics | head -5 > /dev/null; then
    echo "✅ Prometheus指标正常"
else
    echo "❌ Prometheus指标获取失败"
fi

# 12. 检查日志
echo "📝 检查应用日志..."
docker-compose -f docker-compose.tencent.yml logs --tail=20 data-collector

# 13. 显示部署信息
echo "📊 部署完成！服务信息："
echo "- 应用API: http://localhost:8080"
echo "- 健康检查: http://localhost:8080/health"
echo "- Prometheus: http://localhost:9090"
echo "- Redis: localhost:6379"
echo "- PostgreSQL: localhost:5432"
echo "- NATS: localhost:4222"

# 14. 保存部署报告
echo "📄 生成部署报告..."
cat > tencent_deployment_report.txt << EOF
MarketPrism腾讯云部署报告
部署时间: $(date)
使用镜像源: 腾讯云容器镜像服务 (CCR)

服务状态:
$(docker-compose -f docker-compose.tencent.yml ps)

镜像信息:
$(docker images | grep -E "(ccr.ccs.tencentyun.com|marketprism)")

网络信息:
$(docker network ls | grep marketprism)

存储卷信息:
$(docker volume ls | grep marketprism)
EOF

echo "✅ 部署报告已保存: tencent_deployment_report.txt"

echo "🎉 MarketPrism腾讯云部署完成！"
