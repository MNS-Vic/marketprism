#!/bin/bash
set -e

# MarketPrism Data Storage Service Docker 启动脚本

echo "🚀 启动MarketPrism数据存储服务容器"
echo "时间: $(date)"
echo "容器ID: $(hostname)"

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

# 初始化ClickHouse数据库和表
init_clickhouse() {
    echo "🔧 初始化ClickHouse数据库和表..."
    
    # 创建数据库
    curl -s "http://$CLICKHOUSE_HOST:$CLICKHOUSE_HTTP_PORT/" \
        --data "CREATE DATABASE IF NOT EXISTS $CLICKHOUSE_DATABASE"
    
    if [ $? -eq 0 ]; then
        echo "✅ 数据库创建成功: $CLICKHOUSE_DATABASE"
    else
        echo "❌ 数据库创建失败"
        return 1
    fi
    
    # 创建表结构（使用我们验证过的表结构）
    python -c "
import sys
sys.path.append('/app')
from scripts.init_clickhouse_tables import init_all_tables
init_all_tables('$CLICKHOUSE_HOST', $CLICKHOUSE_HTTP_PORT, '$CLICKHOUSE_DATABASE')
"
    
    if [ $? -eq 0 ]; then
        echo "✅ ClickHouse表结构初始化完成"
    else
        echo "❌ ClickHouse表结构初始化失败"
        return 1
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
PORT = 8080

with socketserver.TCPServer(("", PORT), HealthHandler) as httpd:
    httpd.serve_forever()
EOF
    
    python /tmp/health_server.py &
    echo "✅ 健康检查服务已启动 (端口: 8080)"
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

# 启动主程序（使用我们已验证的增强版本）
exec python simple_hot_storage.py "$@"
