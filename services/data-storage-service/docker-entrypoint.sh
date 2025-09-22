#!/bin/bash
set -e

# MarketPrism Data Storage Service Docker 启动脚本
# 🔄 Docker部署简化改造版本 (2025-08-02)
#
# 简化改造内容:
# - ✅ 支持8种数据类型的ClickHouse表自动创建
# - ✅ 优化NATS连接等待逻辑
# - ✅ 简化健康检查和监控配置
# - ✅ 自动数据库初始化和验证

echo "🚀 启动MarketPrism数据存储服务容器 (热存储版)"
echo "时间: $(date)"
echo "容器ID: $(hostname)"
echo "版本: MarketPrism Data Storage Service v1.0.0-simplified"

# 设置默认环境变量
export PYTHONPATH=/app
export PYTHONUNBUFFERED=1
export LOG_LEVEL=${LOG_LEVEL:-INFO}

# ClickHouse连接配置
export CLICKHOUSE_HOST=${CLICKHOUSE_HOST:-clickhouse}
export CLICKHOUSE_HTTP_PORT=${CLICKHOUSE_HTTP_PORT:-8123}
export CLICKHOUSE_TCP_PORT=${CLICKHOUSE_TCP_PORT:-9000}
export CLICKHOUSE_DATABASE=${CLICKHOUSE_DATABASE:-marketprism_hot}
export CLICKHOUSE_USER=${CLICKHOUSE_USER:-default}
export CLICKHOUSE_PASSWORD=${CLICKHOUSE_PASSWORD:-}

# NATS连接配置
export NATS_URL=${NATS_URL:-nats://message-broker:4222}
export NATS_STREAM=${NATS_STREAM:-MARKET_DATA}
# 变量统一：若设置 MARKETPRISM_NATS_URL，则覆盖 NATS_URL（保留下游兼容）
if [ -n "$MARKETPRISM_NATS_URL" ]; then
    export NATS_URL="$MARKETPRISM_NATS_URL"
fi


echo "📋 容器配置:"
echo "  - Python路径: $PYTHONPATH"
echo "  - 日志级别: $LOG_LEVEL"
echo "  - ClickHouse主机: $CLICKHOUSE_HOST:$CLICKHOUSE_HTTP_PORT"
echo "  - ClickHouse数据库: $CLICKHOUSE_DATABASE"
echo "  - NATS地址: $NATS_URL"
echo "  - NATS Stream: $NATS_STREAM"

# 等待依赖服务启动
wait_for_service() {
    local service_name=$1
    local service_url=$2
    local max_attempts=60
    local attempt=1

    echo "⏳ 等待服务启动: $service_name ($service_url)"

    while [ $attempt -le $max_attempts ]; do
        if curl -s --connect-timeout 2 "$service_url" > /dev/null 2>&1; then
            echo "✅ $service_name 已就绪"
            return 0
        fi

        echo "   尝试 $attempt/$max_attempts: $service_name 未就绪"
        sleep 2
        attempt=$((attempt + 1))
    done

    echo "❌ $service_name 启动超时"
    return 1
}

# 等待ClickHouse服务
if [ "${WAIT_FOR_CLICKHOUSE:-true}" = "true" ]; then
    wait_for_service "ClickHouse" "http://$CLICKHOUSE_HOST:$CLICKHOUSE_HTTP_PORT/ping"
fi

# 等待NATS服务
if [ "${WAIT_FOR_NATS:-true}" = "true" ]; then
    NATS_HOST=$(echo $NATS_URL | sed 's|nats://||' | cut -d':' -f1)
    NATS_HTTP_PORT=${NATS_HTTP_PORT:-8222}
    wait_for_service "NATS" "http://$NATS_HOST:$NATS_HTTP_PORT"
fi

# 初始化ClickHouse数据库和表（带 preflight 校验）
init_clickhouse() {
    echo "🔧 初始化ClickHouse数据库和表（preflight）..."

    # 1) 创建数据库（幂等）
    if clickhouse-client --host "$CLICKHOUSE_HOST" --port "$CLICKHOUSE_TCP_PORT" \
        --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" \
        --query "CREATE DATABASE IF NOT EXISTS $CLICKHOUSE_DATABASE"; then
        echo "✅ 数据库存在/创建成功: $CLICKHOUSE_DATABASE"
    else
        echo "❌ 数据库创建失败: $CLICKHOUSE_DATABASE"
        return 1
    fi

    # 2) preflight：检查必需表是否存在
    required_tables=( \
        orderbooks trades funding_rates open_interests \
        liquidations lsr_top_positions lsr_all_accounts volatility_indices \
    )

    missing_count=0
    for t in "${required_tables[@]}"; do
        if ! clickhouse-client --host "$CLICKHOUSE_HOST" --port "$CLICKHOUSE_TCP_PORT" \
            --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" \
            --query "EXISTS ${CLICKHOUSE_DATABASE}.${t}" | grep -q '^1$'; then
            echo "⚠️ 缺少表: ${CLICKHOUSE_DATABASE}.${t}"
            missing_count=$((missing_count+1))
        fi
    done

    # 3) 若有缺失，则执行 schema.sql（多语句）
    if [ "$missing_count" -gt 0 ]; then
        echo "🧱 发现 ${missing_count} 个缺失表，执行 schema 初始化..."
        if [ -f "/app/config/clickhouse_schema.sql" ]; then
            if clickhouse-client --host "$CLICKHOUSE_HOST" --port "$CLICKHOUSE_TCP_PORT" \
                --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" \
                --multiline --multiquery < /app/config/clickhouse_schema.sql; then
                echo "✅ 表结构创建成功 (8种数据类型)"
                echo "  - orderbooks (订单簿)"
                echo "  - trades (交易)"
                echo "  - funding_rates (资金费率)"
                echo "  - open_interests (未平仓量)"
                echo "  - liquidations (强平)"
                echo "  - lsr_top_positions (LSR顶级持仓)"
                echo "  - lsr_all_accounts (LSR全账户)"
                echo "  - volatility_indices (波动率指数)"
            else
                echo "❌ 表结构创建失败"
                return 1
            fi
        else
            echo "❌ 找不到建表脚本: /app/config/clickhouse_schema.sql"
            return 1
        fi
    else
        echo "✅ 所有必需表已存在，跳过 schema 初始化"
    fi
}

# 初始化ClickHouse
if [ "${INIT_CLICKHOUSE:-true}" = "true" ]; then
    init_clickhouse
fi

# 创建日志目录
mkdir -p /var/log/marketprism

# 健康检查端点
start_health_server() {
    cat > /tmp/health_server.py << 'EOF'
import http.server
import socketserver
import json
import time
from datetime import datetime

class HealthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            health_data = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "service": "data-storage",
                "uptime": time.time() - start_time
            }

            self.wfile.write(json.dumps(health_data).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # 禁用访问日志

start_time = time.time()
PORT = 18080

with socketserver.TCPServer(("", PORT), HealthHandler) as httpd:
    httpd.serve_forever()
EOF

    python /tmp/health_server.py &
    echo "✅ 健康检查服务已启动 (端口: 18080)"
}

# 启动健康检查服务
start_health_server

# 信号处理
cleanup() {
    echo "🛑 收到停止信号，正在清理..."
    kill $(jobs -p) 2>/dev/null || true
    exit 0
}

trap cleanup SIGTERM SIGINT

echo "🎯 启动数据存储服务..."
echo "命令: python simple_hot_storage.py"

# 启动主程序（简化热端存储服务）
exec python simple_hot_storage.py "$@"
