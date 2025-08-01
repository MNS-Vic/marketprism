#!/bin/bash
set -e

# MarketPrism Data Collector Docker 启动脚本

echo "🚀 启动MarketPrism数据收集器容器"
echo "时间: $(date)"
echo "容器ID: $(hostname)"

# 设置默认环境变量
export PYTHONPATH=/app
export PYTHONUNBUFFERED=1
export LOG_LEVEL=${LOG_LEVEL:-INFO}
export COLLECTOR_MODE=${COLLECTOR_MODE:-launcher}
export COLLECTOR_CONFIG_PATH=${COLLECTOR_CONFIG_PATH:-/app/config/collector/unified_data_collection.yaml}

# NATS连接配置
export NATS_URL=${NATS_URL:-nats://message-broker:4222}
export NATS_STREAM=${NATS_STREAM:-MARKET_DATA}

# 交易所配置
export EXCHANGE=${EXCHANGE:-binance_spot}
export SYMBOLS=${SYMBOLS:-BTCUSDT,ETHUSDT}
export DATA_TYPES=${DATA_TYPES:-orderbook,trade}

echo "📋 容器配置:"
echo "  - Python路径: $PYTHONPATH"
echo "  - 日志级别: $LOG_LEVEL"
echo "  - 收集器模式: $COLLECTOR_MODE"
echo "  - 配置文件: $COLLECTOR_CONFIG_PATH"
echo "  - NATS地址: $NATS_URL"
echo "  - 交易所: $EXCHANGE"
echo "  - 交易对: $SYMBOLS"
echo "  - 数据类型: $DATA_TYPES"

# 等待依赖服务启动
wait_for_service() {
    local service_name=$1
    local service_url=$2
    local max_attempts=30
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

# 等待NATS服务
if [ "${WAIT_FOR_NATS:-true}" = "true" ]; then
    NATS_HOST=$(echo $NATS_URL | sed 's|nats://||' | cut -d':' -f1)
    NATS_HTTP_PORT=${NATS_HTTP_PORT:-8222}
    wait_for_service "NATS" "http://$NATS_HOST:$NATS_HTTP_PORT"
fi

# 创建日志目录
mkdir -p /var/log/marketprism

# 健康检查端点
start_health_server() {
    cat > /tmp/health_server.py << 'EOF'
import http.server
import socketserver
import json
import threading
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
                "service": "data-collector",
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

# 切换到工作目录
cd /app/services/data-collector

echo "🎯 启动数据收集器..."
echo "命令: python unified_collector_main.py --mode $COLLECTOR_MODE --config $COLLECTOR_CONFIG_PATH --log-level $LOG_LEVEL"

# 启动主程序
exec python unified_collector_main.py \
    --mode "$COLLECTOR_MODE" \
    --config "$COLLECTOR_CONFIG_PATH" \
    --log-level "$LOG_LEVEL" \
    "$@"

# 等待依赖服务启动
wait_for_service() {
    local service_name=$1
    local service_url=$2
    local max_attempts=30
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

# 等待NATS服务
if [ "$WAIT_FOR_NATS" = "true" ]; then
    NATS_HOST=$(echo $NATS_URL | sed 's|nats://||' | cut -d':' -f1)
    NATS_HTTP_PORT=${NATS_HTTP_PORT:-8222}
    wait_for_service "NATS" "http://$NATS_HOST:$NATS_HTTP_PORT"
fi

# 创建日志目录
mkdir -p /var/log/marketprism

# 健康检查端点
start_health_server() {
    cat > /tmp/health_server.py << 'EOF'
import http.server
import socketserver
import json
import threading
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
                "service": "data-collector",
                "exchange": "$EXCHANGE",
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

# 切换到工作目录
cd /app/services/data-collector

echo "🎯 启动数据收集器..."
echo "命令: python unified_collector_main.py --mode $COLLECTOR_MODE --config $COLLECTOR_CONFIG_PATH --log-level $LOG_LEVEL"

# 启动主程序
exec python unified_collector_main.py \
    --mode "$COLLECTOR_MODE" \
    --config "$COLLECTOR_CONFIG_PATH" \
    --log-level "$LOG_LEVEL" \
    "$@"
