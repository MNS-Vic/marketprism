#!/bin/bash
# MarketPrism服务状态检查脚本
# 检查所有服务的运行状态和健康状况

set -euo pipefail

WORKSPACE_ROOT="/home/ubuntu/marketprism"
PID_DIR="$WORKSPACE_ROOT/temp"

echo "=== MarketPrism服务状态检查 ==="

cd "$WORKSPACE_ROOT"

# 1. 基础设施状态
echo "1. 基础设施状态:"
echo -n "  NATS JetStream: "
if curl -s http://127.0.0.1:8222/healthz >/dev/null; then
    echo "✅ 运行中 (http://127.0.0.1:8222)"
else
    echo "❌ 未运行"
fi

echo -n "  ClickHouse: "
if curl -s "http://127.0.0.1:8123/?query=SELECT%201" >/dev/null; then
    echo "✅ 运行中 (http://127.0.0.1:8123)"
else
    echo "❌ 未运行"
fi

# 2. 应用服务状态
echo -e "\n2. 应用服务状态:"

# 数据采集器
echo -n "  数据采集器: "
if [ -f "$PID_DIR/collector.pid" ]; then
    COLLECTOR_PID=$(cat "$PID_DIR/collector.pid")
    if kill -0 "$COLLECTOR_PID" 2>/dev/null; then
        echo -n "✅ 运行中 (PID: $COLLECTOR_PID) "
        if curl -s http://127.0.0.1:8087/health >/dev/null; then
            echo "健康检查: ✅"
        else
            echo "健康检查: ❌"
        fi
    else
        echo "❌ 进程不存在 (PID: $COLLECTOR_PID)"
    fi
else
    echo "❌ 未运行"
fi

# 热端存储服务
echo -n "  热端存储服务: "
if [ -f "$PID_DIR/hot_storage.pid" ]; then
    HOT_PID=$(cat "$PID_DIR/hot_storage.pid")
    if kill -0 "$HOT_PID" 2>/dev/null; then
        echo -n "✅ 运行中 (PID: $HOT_PID) "
        if curl -s http://127.0.0.1:8085/health >/dev/null; then
            echo "健康检查: ✅"
        else
            echo "健康检查: ❌"
        fi
    else
        echo "❌ 进程不存在 (PID: $HOT_PID)"
    fi
else
    echo "❌ 未运行"
fi

# 冷端存储服务
echo -n "  冷端存储服务: "
if [ -f "$PID_DIR/cold_storage.pid" ]; then
    COLD_PID=$(cat "$PID_DIR/cold_storage.pid")
    if kill -0 "$COLD_PID" 2>/dev/null; then
        echo -n "✅ 运行中 (PID: $COLD_PID) "
        if curl -s http://127.0.0.1:8086/health >/dev/null; then
            echo "健康检查: ✅"
        else
            echo "健康检查: ❌"
        fi
    else
        echo "❌ 进程不存在 (PID: $COLD_PID)"
    fi
else
    echo "⚪ 未运行 (按需启动)"
fi

# 3. 端口占用情况
echo -e "\n3. 端口占用情况:"
echo "  MarketPrism服务端口:"
ss -ltnp | grep -E ":808[5-7]|:4222|:8123" | while read -r line; do
    echo "    $line"
done || echo "    无端口占用"

# 4. 数据流状态
echo -e "\n4. 数据流状态 (最近5分钟):"
if curl -s "http://127.0.0.1:8123/?query=SELECT%201" >/dev/null; then
    source venv/bin/activate
    
    # 检查热端数据
    hot_orderbooks=$(curl -s "http://127.0.0.1:8123/?query=SELECT%20count()%20FROM%20marketprism_hot.orderbooks%20WHERE%20timestamp%20%3E%20now()%20-%20INTERVAL%205%20MINUTE" 2>/dev/null || echo "0")
    hot_trades=$(curl -s "http://127.0.0.1:8123/?query=SELECT%20count()%20FROM%20marketprism_hot.trades%20WHERE%20timestamp%20%3E%20now()%20-%20INTERVAL%205%20MINUTE" 2>/dev/null || echo "0")
    
    echo "  热端数据 (最近5分钟):"
    echo "    订单簿: $hot_orderbooks 条"
    echo "    交易: $hot_trades 条"
    
    if [ "$hot_orderbooks" -gt 0 ] || [ "$hot_trades" -gt 0 ]; then
        echo "  数据流: ✅ 正常"
    else
        echo "  数据流: ⚠️ 无最新数据"
    fi
else
    echo "  ClickHouse不可用，无法检查数据流"
fi

# 5. 日志文件状态
echo -e "\n5. 日志文件状态:"
if [ -f "logs/collector.log" ]; then
    collector_size=$(stat -c%s logs/collector.log)
    echo "  数据采集器日志: logs/collector.log ($collector_size bytes)"
else
    echo "  数据采集器日志: 不存在"
fi

if [ -f "logs/hot_storage.log" ]; then
    hot_size=$(stat -c%s logs/hot_storage.log)
    echo "  热端存储日志: logs/hot_storage.log ($hot_size bytes)"
else
    echo "  热端存储日志: 不存在"
fi

echo -e "\n=== 状态检查完成 ==="
