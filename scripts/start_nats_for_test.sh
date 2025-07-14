#!/bin/bash

# MarketPrism NATS服务器启动脚本
# 用于综合集成测试

echo "🚀 启动NATS服务器用于MarketPrism集成测试"

# 检查Docker是否安装
if ! command -v docker &> /dev/null; then
    echo "❌ Docker未安装，请先安装Docker"
    exit 1
fi

# 检查是否已有NATS容器在运行
if docker ps | grep -q "nats.*4222"; then
    echo "✅ NATS服务器已在运行"
    docker ps | grep nats
else
    echo "🔄 启动NATS服务器..."
    
    # 停止可能存在的旧容器
    docker stop marketprism-nats 2>/dev/null || true
    docker rm marketprism-nats 2>/dev/null || true
    
    # 启动新的NATS容器
    docker run -d \
        --name marketprism-nats \
        -p 4222:4222 \
        -p 8222:8222 \
        -p 6222:6222 \
        nats:latest \
        --jetstream \
        --store_dir /data \
        --max_memory_store 1GB \
        --max_file_store 10GB
    
    if [ $? -eq 0 ]; then
        echo "✅ NATS服务器启动成功"
        echo "   - 客户端端口: 4222"
        echo "   - 监控端口: 8222"
        echo "   - 集群端口: 6222"
        echo "   - JetStream: 启用"
    else
        echo "❌ NATS服务器启动失败"
        exit 1
    fi
fi

# 等待NATS服务器就绪
echo "⏳ 等待NATS服务器就绪..."
sleep 3

# 测试连接
echo "🔍 测试NATS连接..."
if command -v nats &> /dev/null; then
    nats server check connection
else
    # 使用Docker测试连接
    docker run --rm --network host nats:latest nats server check connection
fi

if [ $? -eq 0 ]; then
    echo "✅ NATS服务器连接测试成功"
    echo ""
    echo "🎯 NATS服务器已就绪，可以运行集成测试："
    echo "   python scripts/comprehensive_integration_test.py"
    echo ""
    echo "📊 NATS监控界面："
    echo "   http://localhost:8222"
    echo ""
    echo "🛑 停止NATS服务器："
    echo "   docker stop marketprism-nats"
else
    echo "❌ NATS服务器连接测试失败"
    exit 1
fi
