#!/bin/bash

# MarketPrism 系统停止脚本

set -euo pipefail

echo "🛑 MarketPrism 系统停止脚本"
echo "=================================="

# 从PID文件读取进程ID并停止
echo "1. 停止MarketPrism服务"
echo "----------------------"

if [ -f .collector.pid ]; then
    COLLECTOR_PID=$(cat .collector.pid)
    echo "停止数据采集器 (PID: $COLLECTOR_PID)..."
    kill $COLLECTOR_PID 2>/dev/null || echo "  采集器进程已停止"
    rm -f .collector.pid
fi

if [ -f .hot_storage.pid ]; then
    HOT_PID=$(cat .hot_storage.pid)
    echo "停止热端存储 (PID: $HOT_PID)..."
    kill $HOT_PID 2>/dev/null || echo "  热端存储进程已停止"
    rm -f .hot_storage.pid
fi

if [ -f .cold_storage.pid ]; then
    COLD_PID=$(cat .cold_storage.pid)
    echo "停止冷端存储 (PID: $COLD_PID)..."
    kill $COLD_PID 2>/dev/null || echo "  冷端存储进程已停止"
    rm -f .cold_storage.pid
fi

# 强制清理所有相关进程
echo -e "\n2. 强制清理相关进程"
echo "-------------------"
pkill -f "unified_collector_main.py" || echo "  采集器进程已清理"
pkill -f "main.py --mode hot" || echo "  热端存储进程已清理"
pkill -f "main.py --mode cold" || echo "  冷端存储进程已清理"

# 等待进程完全停止
sleep 3

# 验证进程已停止
echo -e "\n3. 验证进程状态"
echo "---------------"
if pgrep -f "unified_collector_main.py" >/dev/null; then
    echo "  ⚠️ 采集器进程仍在运行"
else
    echo "  ✅ 采集器进程已停止"
fi

if pgrep -f "main.py --mode hot" >/dev/null; then
    echo "  ⚠️ 热端存储进程仍在运行"
else
    echo "  ✅ 热端存储进程已停止"
fi

if pgrep -f "main.py --mode cold" >/dev/null; then
    echo "  ⚠️ 冷端存储进程仍在运行"
else
    echo "  ✅ 冷端存储进程已停止"
fi

echo -e "\n🎉 MarketPrism系统停止完成！"
echo "=================================="
