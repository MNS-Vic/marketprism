#!/bin/bash
# MarketPrism混合部署脚本 - 代理+腾讯云镜像

echo "🚀 MarketPrism混合部署开始（代理+腾讯云镜像）..."

# 设置代理环境变量
export HTTP_PROXY="http://127.0.0.1:7890"
export HTTPS_PROXY="http://127.0.0.1:7890"
export NO_PROXY="localhost,127.0.0.1,redis,postgres,nats,prometheus"

echo "🌐 代理配置："
echo "  HTTP_PROXY: $HTTP_PROXY"
echo "  HTTPS_PROXY: $HTTPS_PROXY"
echo "  NO_PROXY: $NO_PROXY"

# 更新.env文件中的代理配置
echo "⚙️ 更新环境配置..."
cat >> .env << EOF

# 代理配置
HTTP_PROXY=${HTTP_PROXY}
HTTPS_PROXY=${HTTPS_PROXY}
NO_PROXY=${NO_PROXY}
PROXY_ENABLED=true

# 腾讯云镜像配置
TENCENT_MIRROR_ENABLED=true
EOF

echo "✅ 环境变量已设置"

# 1. 配置Docker镜像加速器
echo "🏢 配置Docker腾讯云镜像加速器..."

# 检查是否为macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "📱 检测到macOS系统，请手动配置Docker Desktop镜像加速器："
    echo "   1. 打开Docker Desktop"
    echo "   2. 进入Settings > Docker Engine"
    echo "   3. 添加以下配置到JSON中："
    echo '   "registry-mirrors": ["https://mirror.ccs.tencentyun.com"]'
    echo "   4. 点击Apply & Restart"
    echo ""
    read -p "配置完成后按回车继续..."
else
    # Linux系统自动配置
    sudo cp docker-daemon.json /etc/docker/daemon.json
    sudo systemctl daemon-reload
    sudo systemctl restart docker
    echo "✅ Docker镜像加速器配置完成"
fi

# 2. 测试代理连接
echo "🔍 测试代理连接..."
if curl -s --proxy $HTTP_PROXY --max-time 10 https://www.google.com > /dev/null; then
    echo "✅ 代理连接正常"
else
    echo "⚠️ 代理连接失败，将仅使用腾讯云镜像"
    export HTTP_PROXY=""
    export HTTPS_PROXY=""
fi

# 3. 测试腾讯云镜像
echo "🔍 测试腾讯云镜像连接..."
if docker pull ccr.ccs.tencentyun.com/library/alpine:latest > /dev/null 2>&1; then
    echo "✅ 腾讯云镜像连接正常"
    docker rmi ccr.ccs.tencentyun.com/library/alpine:latest > /dev/null 2>&1
else
    echo "❌ 腾讯云镜像连接失败"
fi

# 4. 停止现有服务
echo "🛑 停止现有服务..."
docker-compose -f docker-compose.hybrid.yml down

# 5. 清理Docker资源
echo "🧹 清理Docker资源..."
docker system prune -f

# 6. 拉取所有镜像
echo "📦 拉取Docker镜像..."
echo "正在拉取Redis镜像..."
docker pull ccr.ccs.tencentyun.com/library/redis:7-alpine

echo "正在拉取PostgreSQL镜像..."
docker pull ccr.ccs.tencentyun.com/library/postgres:15-alpine

echo "正在拉取NATS镜像..."
docker pull ccr.ccs.tencentyun.com/library/nats:2-alpine

echo "正在拉取Prometheus镜像..."
docker pull ccr.ccs.tencentyun.com/library/prometheus:latest

echo "✅ 所有镜像拉取完成"

# 7. 构建应用镜像
echo "🔨 构建应用镜像..."
docker-compose -f docker-compose.hybrid.yml build --build-arg HTTP_PROXY=$HTTP_PROXY --build-arg HTTPS_PROXY=$HTTPS_PROXY

# 8. 启动基础设施服务
echo "🏗️ 启动基础设施服务..."
docker-compose -f docker-compose.hybrid.yml up -d redis postgres nats prometheus

# 等待服务启动
echo "⏳ 等待基础设施服务启动..."
sleep 30

# 9. 检查基础设施服务健康状态
echo "🔍 检查基础设施服务健康状态..."
for service in redis postgres nats prometheus; do
    echo "检查 $service 服务..."
    for i in {1..6}; do
        if docker-compose -f docker-compose.hybrid.yml ps $service | grep -q "healthy\|Up"; then
            echo "✅ $service 服务正常"
            break
        else
            echo "⏳ 等待 $service 服务启动... ($i/6)"
            sleep 10
        fi
    done
done

# 10. 启动数据收集器
echo "🚀 启动数据收集器..."
docker-compose -f docker-compose.hybrid.yml up -d data-collector

# 等待应用启动
echo "⏳ 等待应用启动..."
sleep 30

# 11. 验证部署
echo "✅ 验证部署状态..."

# 检查所有服务状态
echo "📊 服务状态："
docker-compose -f docker-compose.hybrid.yml ps

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

# 12. 运行API测试
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

# 13. 检查日志
echo "📝 检查应用日志..."
docker-compose -f docker-compose.hybrid.yml logs --tail=20 data-collector

# 14. 显示部署信息
echo "📊 部署完成！服务信息："
echo "- 应用API: http://localhost:8080"
echo "- 健康检查: http://localhost:8080/health"
echo "- Prometheus: http://localhost:9090"
echo "- Redis: localhost:6379"
echo "- PostgreSQL: localhost:5432"
echo "- NATS: localhost:4222"

# 15. 保存部署报告
echo "📄 生成部署报告..."
cat > hybrid_deployment_report.txt << EOF
MarketPrism混合部署报告（代理+腾讯云镜像）
部署时间: $(date)
代理配置: $HTTP_PROXY
镜像源: 腾讯云容器镜像服务 (CCR)

服务状态:
$(docker-compose -f docker-compose.hybrid.yml ps)

镜像信息:
$(docker images | grep -E "(ccr.ccs.tencentyun.com|marketprism)")

网络信息:
$(docker network ls | grep marketprism)

存储卷信息:
$(docker volume ls | grep marketprism)

健康检查:
API状态: $(curl -s http://localhost:8080/health 2>/dev/null || echo "不可访问")
Prometheus状态: $(curl -s http://localhost:9090/-/healthy 2>/dev/null && echo "正常" || echo "异常")
EOF

echo "✅ 部署报告已保存: hybrid_deployment_report.txt"

echo "🎉 MarketPrism混合部署完成！"

# 最终状态检查
if curl -s http://localhost:8080/health > /dev/null; then
    echo "🎊 部署成功！MarketPrism正在运行！"
    echo "🔗 访问地址: http://localhost:8080"
    exit 0
else
    echo "⚠️ 部署完成但API不可访问，请检查日志"
    echo "📝 查看日志: docker-compose -f docker-compose.hybrid.yml logs data-collector"
    exit 1
fi
