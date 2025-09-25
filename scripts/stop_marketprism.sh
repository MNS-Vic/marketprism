#!/bin/bash
# MarketPrism服务停止脚本
# 安全地停止所有MarketPrism服务

set -euo pipefail

WORKSPACE_ROOT="/home/ubuntu/marketprism"
PID_DIR="$WORKSPACE_ROOT/temp"

echo "=== MarketPrism服务停止 ==="

cd "$WORKSPACE_ROOT"

# 1. 停止应用服务
echo "1. 停止应用服务:"

# 停止数据采集器
if [ -f "$PID_DIR/collector.pid" ]; then
    COLLECTOR_PID=$(cat "$PID_DIR/collector.pid")
    if kill -0 "$COLLECTOR_PID" 2>/dev/null; then
        echo "  停止数据采集器 (PID: $COLLECTOR_PID)"
        kill -TERM "$COLLECTOR_PID"
        sleep 3
        if kill -0 "$COLLECTOR_PID" 2>/dev/null; then
            echo "  强制停止数据采集器"
            kill -KILL "$COLLECTOR_PID"
        fi
    else
        echo "  数据采集器已停止"
    fi
    rm -f "$PID_DIR/collector.pid"
else
    echo "  数据采集器PID文件不存在"
fi

# 停止热端存储服务
if [ -f "$PID_DIR/hot_storage.pid" ]; then
    HOT_PID=$(cat "$PID_DIR/hot_storage.pid")
    if kill -0 "$HOT_PID" 2>/dev/null; then
        echo "  停止热端存储服务 (PID: $HOT_PID)"
        kill -TERM "$HOT_PID"
        sleep 3
        if kill -0 "$HOT_PID" 2>/dev/null; then
            echo "  强制停止热端存储服务"
            kill -KILL "$HOT_PID"
        fi
    else
        echo "  热端存储服务已停止"
    fi
    rm -f "$PID_DIR/hot_storage.pid"
else
    echo "  热端存储服务PID文件不存在"
fi

# 停止冷端存储服务（如果运行）
if [ -f "$PID_DIR/cold_storage.pid" ]; then
    COLD_PID=$(cat "$PID_DIR/cold_storage.pid")
    if kill -0 "$COLD_PID" 2>/dev/null; then
        echo "  停止冷端存储服务 (PID: $COLD_PID)"
        kill -TERM "$COLD_PID"
        sleep 3
        if kill -0 "$COLD_PID" 2>/dev/null; then
            echo "  强制停止冷端存储服务"
            kill -KILL "$COLD_PID"
        fi
    else
        echo "  冷端存储服务已停止"
    fi
    rm -f "$PID_DIR/cold_storage.pid"
else
    echo "  冷端存储服务未运行"
fi

# 2. 清理进程
echo -e "\n2. 清理相关进程:"
pkill -f "unified_collector_main.py" || echo "  无数据采集器进程"
pkill -f "data-storage-service.*main.py" || echo "  无存储服务进程"

# 3. 检查端口占用
echo -e "\n3. 检查端口占用:"
echo "MarketPrism服务端口:"
ss -ltnp | grep -E ":808[5-7]" || echo "  无MarketPrism服务端口占用"

# 4. 清理临时文件
echo -e "\n4. 清理临时文件:"
rm -f "$PID_DIR"/*.pid
echo "  PID文件已清理"

echo -e "\n=== ✅ MarketPrism服务停止完成！ ==="
echo "基础设施服务(NATS、ClickHouse)仍在运行"
echo "如需停止基础设施，请手动执行相应的docker-compose down命令"
