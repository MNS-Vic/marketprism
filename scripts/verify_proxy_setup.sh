#!/bin/bash
# 代理配置验证脚本

echo "🔍 验证Docker代理配置..."

# 1. 检查宿主机代理
echo "1. 检查宿主机代理状态："
if curl -s --proxy http://127.0.0.1:7890 --max-time 10 https://www.google.com > /dev/null; then
    echo "✅ 宿主机代理可用"
else
    echo "❌ 宿主机代理不可用"
fi

# 2. 检查Docker daemon代理配置
echo "2. 检查Docker daemon代理配置："
if command -v systemctl > /dev/null; then
    systemctl show --property=Environment docker | grep -i proxy || echo "未配置daemon代理"
else
    echo "⚠️ 非systemd系统，跳过daemon代理检查"
fi

# 3. 测试Docker镜像拉取
echo "3. 测试Docker镜像拉取："
if docker pull alpine:latest > /dev/null 2>&1; then
    echo "✅ Docker镜像拉取成功"
else
    echo "❌ Docker镜像拉取失败"
fi

# 4. 测试容器内网络访问
echo "4. 测试容器内网络访问："
docker run --rm \
    -e HTTP_PROXY=http://host.docker.internal:7890 \
    -e HTTPS_PROXY=http://host.docker.internal:7890 \
    alpine/curl:latest \
    curl -s --max-time 10 https://api.github.com > /dev/null

if [ $? -eq 0 ]; then
    echo "✅ 容器内代理访问成功"
else
    echo "❌ 容器内代理访问失败"
fi

# 5. 检查MarketPrism服务状态
echo "5. 检查MarketPrism服务状态："
if docker-compose -f docker-compose.proxy.yml ps | grep -q "Up"; then
    echo "✅ MarketPrism服务运行中"
    
    # 检查API可访问性
    if curl -s http://localhost:8080/health > /dev/null; then
        echo "✅ MarketPrism API可访问"
    else
        echo "⚠️ MarketPrism API不可访问"
    fi
else
    echo "⚠️ MarketPrism服务未运行"
fi

# 6. 网络连通性测试
echo "6. 网络连通性测试："
test_urls=(
    "https://api.binance.com/api/v3/ping"
    "https://www.okx.com/api/v5/public/time"
    "https://api.exchange.coinbase.com/time"
)

for url in "${test_urls[@]}"; do
    exchange=$(echo $url | cut -d'/' -f3 | cut -d'.' -f1,2)
    if curl -s --max-time 10 "$url" > /dev/null; then
        echo "✅ $exchange API可访问"
    else
        echo "❌ $exchange API不可访问"
    fi
done

echo "🎯 代理配置验证完成！"
