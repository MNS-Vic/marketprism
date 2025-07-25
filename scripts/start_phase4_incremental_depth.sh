#!/bin/bash

# Phase 4: 增量深度数据流启动脚本
# 启动MarketPrism Collector with 增量深度数据流配置

echo "🚀 启动Phase 4: 增量深度数据流"
echo "=================================="

# 检查当前目录
if [ ! -f "config/collector_with_incremental_depth.yaml" ]; then
    echo "❌ 错误: 请在项目根目录运行此脚本"
    echo "   当前目录: $(pwd)"
    echo "   期望目录: marketprism项目根目录"
    exit 1
fi

# 检查Python环境
if ! command -v python &> /dev/null; then
    echo "❌ 错误: Python未安装或不在PATH中"
    exit 1
fi

# 检查NATS服务器
echo "🔍 检查NATS服务器..."
if ! nc -z localhost 4222 2>/dev/null; then
    echo "⚠️  警告: NATS服务器未运行在localhost:4222"
    echo "   请先启动NATS服务器: nats-server"
    echo "   或者使用Docker: docker run -p 4222:4222 nats:latest"
fi

# 设置代理（如果需要）
export HTTP_PROXY=http://127.0.0.1:1087
export HTTPS_PROXY=http://127.0.0.1:1087

echo "🔧 配置信息:"
echo "   配置文件: config/collector_with_incremental_depth.yaml"
echo "   HTTP端口: 8080"
echo "   代理设置: $HTTP_PROXY"
echo "   OrderBook Manager: 启用"
echo "   交易所: Binance (仅)"

echo ""
echo "🚀 启动Collector..."
echo "   使用Ctrl+C停止"
echo ""

# 启动collector
python -m services.python-collector.src.marketprism_collector.collector \
    --config config/collector_with_incremental_depth.yaml

echo ""
echo "✅ Collector已停止"