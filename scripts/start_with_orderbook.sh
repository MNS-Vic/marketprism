#!/bin/bash

# MarketPrism 启动脚本 - 启用OrderBook Manager
# 用于演示Phase 3 REST API集成功能

set -e

echo "🚀 启动MarketPrism - 启用OrderBook Manager"
echo "================================================"

# 检查环境
echo "📋 检查环境..."

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装"
    exit 1
fi

# 检查Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装"
    exit 1
fi

# 检查Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose 未安装"
    exit 1
fi

echo "✅ 环境检查通过"

# 设置代理（本地开发必需）
echo "🌐 设置网络代理..."
export http_proxy=http://127.0.0.1:1087
export https_proxy=http://127.0.0.1:1087
export ALL_PROXY=socks5://127.0.0.1:1080
export no_proxy=localhost,127.0.0.1

echo "✅ 代理配置完成"

# 启动基础设施
echo "🏗️ 启动基础设施..."
docker-compose -f docker-compose.infrastructure.yml up -d

# 等待服务启动
echo "⏳ 等待NATS和ClickHouse启动..."
sleep 10

# 检查NATS连接
echo "🔍 检查NATS连接..."
if ! curl -s http://localhost:8222/healthz > /dev/null; then
    echo "❌ NATS 连接失败"
    exit 1
fi
echo "✅ NATS 连接正常"

# 检查ClickHouse连接
echo "🔍 检查ClickHouse连接..."
if ! curl -s http://localhost:8123/ping > /dev/null; then
    echo "❌ ClickHouse 连接失败"
    exit 1
fi
echo "✅ ClickHouse 连接正常"

# 启动Python Collector（启用OrderBook Manager）
echo "🐍 启动Python Collector（启用OrderBook Manager）..."

# 检查虚拟环境
if [ ! -d "venv_tdd" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv_tdd
fi

# 激活虚拟环境
source venv_tdd/bin/activate

# 安装依赖
echo "📦 安装依赖..."
pip install -q -r requirements.txt

# 使用启用OrderBook Manager的配置启动collector
echo "🚀 启动Collector（OrderBook Manager已启用）..."
cd services/python-collector

# 设置环境变量启用OrderBook Manager
export ENABLE_ORDERBOOK_MANAGER=true
export LOG_LEVEL=INFO

# 启动collector
python -m src.marketprism_collector.collector &
COLLECTOR_PID=$!

cd ../..

echo "✅ Collector已启动 (PID: $COLLECTOR_PID)"

# 等待collector启动
echo "⏳ 等待Collector启动..."
sleep 5

# 验证服务状态
echo "🔍 验证服务状态..."

# 检查健康状态
echo "📊 检查系统健康状态..."
if curl -s http://localhost:8080/health | grep -q "healthy"; then
    echo "✅ 系统健康状态正常"
else
    echo "⚠️ 系统健康状态异常"
fi

# 检查OrderBook Manager状态
echo "📊 检查OrderBook Manager状态..."
if curl -s http://localhost:8080/status | grep -q "orderbook_manager"; then
    echo "✅ OrderBook Manager已启用"
else
    echo "⚠️ OrderBook Manager状态异常"
fi

# 测试OrderBook API
echo "🧪 测试OrderBook REST API..."
if curl -s http://localhost:8080/api/v1/orderbook/health > /dev/null; then
    echo "✅ OrderBook REST API可访问"
else
    echo "⚠️ OrderBook REST API不可访问"
fi

echo ""
echo "🎉 MarketPrism启动完成！"
echo "================================================"
echo "📡 服务端点："
echo "  - 健康检查: http://localhost:8080/health"
echo "  - 系统状态: http://localhost:8080/status"
echo "  - Prometheus指标: http://localhost:8080/metrics"
echo "  - OrderBook健康: http://localhost:8080/api/v1/orderbook/health"
echo "  - OrderBook统计: http://localhost:8080/api/v1/orderbook/stats"
echo ""
echo "📋 可用的OrderBook API端点："
echo "  - GET /api/v1/orderbook/exchanges - 列出交易所"
echo "  - GET /api/v1/orderbook/{exchange}/{symbol} - 获取订单簿"
echo "  - GET /api/v1/orderbook/stats - 获取统计信息"
echo ""
echo "🛑 停止服务："
echo "  - Ctrl+C 停止collector"
echo "  - docker-compose -f docker-compose.infrastructure.yml down"
echo ""
echo "📄 日志查看："
echo "  - Collector日志: 控制台输出"
echo "  - NATS日志: docker-compose logs nats"
echo "  - ClickHouse日志: docker-compose logs clickhouse"

# 等待用户中断
echo "⏳ 服务运行中... 按Ctrl+C停止"
trap "echo '🛑 停止服务...'; kill $COLLECTOR_PID; docker-compose -f docker-compose.infrastructure.yml down; echo '✅ 服务已停止'; exit 0" INT

# 保持脚本运行
wait $COLLECTOR_PID