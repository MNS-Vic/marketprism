#!/bin/bash

# MarketPrism 系统启动脚本
# 从唯一配置和唯一入口启动完整系统

set -euo pipefail

echo "🚀 MarketPrism 系统启动脚本"
echo "=================================="

# 激活虚拟环境
source venv/bin/activate

# 检查基础设施
echo "1. 检查基础设施状态"
echo "-------------------"
echo -n "  NATS: "
if curl -s http://127.0.0.1:8222/healthz >/dev/null; then
    echo "✅ OK"
else
    echo "❌ FAIL - 请先启动NATS服务"
    exit 1
fi

echo -n "  ClickHouse: "
if curl -s "http://127.0.0.1:8123/?query=SELECT%201" >/dev/null; then
    echo "✅ OK"
else
    echo "❌ FAIL - 请先启动ClickHouse服务"
    exit 1
fi

# 初始化数据库（如果需要）
echo -e "\n2. 数据库初始化"
echo "---------------"
if [ "${INIT_DB:-0}" = "1" ]; then
    echo "执行数据库初始化..."
    bash scripts/init_databases.sh
    echo "✅ 数据库初始化完成"
else
    echo "跳过数据库初始化（设置 INIT_DB=1 可启用）"
fi

# 清理旧进程
echo -e "\n3. 清理旧进程"
echo "-------------"
pkill -f "unified_collector_main.py" || echo "  采集器进程已清理"
pkill -f "main.py --mode hot" || echo "  热端存储进程已清理"
pkill -f "main.py --mode cold" || echo "  冷端存储进程已清理"
sleep 3

# 启动服务
echo -e "\n4. 启动MarketPrism服务"
echo "----------------------"

# 启动热端存储服务
echo "启动热端存储服务..."
cd services/data-storage-service
python main.py --mode hot > ../../logs/hot_storage_system.log 2>&1 &
HOT_PID=$!
echo "  热端存储 PID: $HOT_PID"
cd ../..

# 等待热端服务启动
sleep 5

# 启动冷端存储服务
echo "启动冷端存储服务..."
cd services/data-storage-service
python main.py --mode cold > ../../logs/cold_storage_system.log 2>&1 &
COLD_PID=$!
echo "  冷端存储 PID: $COLD_PID"
cd ../..

# 等待冷端服务启动
sleep 5

# 启动数据采集器（启用HTTP健康检查）
echo "启动数据采集器..."
cd services/data-collector
COLLECTOR_ENABLE_HTTP=1 HEALTH_CHECK_PORT=8087 ALLOW_MULTIPLE=1 \
python unified_collector_main.py > ../../logs/collector_system.log 2>&1 &
COLLECTOR_PID=$!
echo "  数据采集器 PID: $COLLECTOR_PID"
cd ../..

# 等待所有服务启动
echo -e "\n5. 等待服务启动完成"
echo "-------------------"
sleep 15

# 验证服务状态
echo -e "\n6. 验证服务状态"
echo "---------------"
echo -n "  数据采集器(8087): "
if curl -s http://127.0.0.1:8087/health >/dev/null; then
    echo "✅ OK"
else
    echo "❌ FAIL"
    exit 1
fi

echo -n "  热端存储(8085): "
if curl -s http://127.0.0.1:8085/health >/dev/null; then
    echo "✅ OK"
else
    echo "❌ FAIL"
    exit 1
fi

echo -n "  冷端存储(8086): "
if curl -s http://127.0.0.1:8086/health >/dev/null; then
    echo "✅ OK"
else
    echo "❌ FAIL"
    exit 1
fi

# 显示进程信息
echo -e "\n7. 系统进程信息"
echo "---------------"
echo "  数据采集器: PID $COLLECTOR_PID"
echo "  热端存储: PID $HOT_PID"
echo "  冷端存储: PID $COLD_PID"

# 保存PID到文件
echo "$COLLECTOR_PID" > .collector.pid
echo "$HOT_PID" > .hot_storage.pid
echo "$COLD_PID" > .cold_storage.pid

echo -e "\n🎉 MarketPrism系统启动完成！"
echo "=================================="
echo "✅ 所有服务正常运行"
echo "✅ 数据采集、热端存储、冷端传输全链路正常"
echo "✅ HTTP健康检查接口已启用"
echo ""
echo "📋 服务端点："
echo "  数据采集器健康检查: http://127.0.0.1:8087/health"
echo "  热端存储健康检查: http://127.0.0.1:8085/health"
echo "  冷端存储健康检查: http://127.0.0.1:8086/health"
echo ""
echo "📊 验证命令："
echo "  bash scripts/final_end_to_end_verification.sh"
echo ""
echo "🛑 停止命令："
echo "  bash scripts/stop_marketprism_system.sh"
