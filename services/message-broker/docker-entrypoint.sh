#!/bin/bash
set -e

# MarketPrism Message Broker (NATS JetStream) Docker 启动脚本

echo "🚀 启动MarketPrism消息代理容器 (NATS JetStream)"
echo "时间: $(date)"
echo "容器ID: $(hostname)"

# 设置默认环境变量
export NATS_CONFIG_FILE=${NATS_CONFIG_FILE:-/app/nats.conf}
export JETSTREAM_STORE_DIR=${JETSTREAM_STORE_DIR:-/data/jetstream}
export NATS_LOG_FILE=${NATS_LOG_FILE:-/var/log/nats/nats.log}

echo "📋 容器配置:"
echo "  - NATS配置文件: $NATS_CONFIG_FILE"
echo "  - JetStream存储目录: $JETSTREAM_STORE_DIR"
echo "  - 日志文件: $NATS_LOG_FILE"

# 创建必要的目录
mkdir -p $(dirname $NATS_LOG_FILE)
mkdir -p $JETSTREAM_STORE_DIR

# 生成NATS配置文件
generate_nats_config() {
    cat > $NATS_CONFIG_FILE << EOF
# MarketPrism NATS JetStream 配置
server_name: "marketprism-nats"

# 监听配置
host: "0.0.0.0"
port: 4222

# HTTP监控端口
http_port: 8222

# JetStream配置
jetstream {
    store_dir: "$JETSTREAM_STORE_DIR"
    max_memory_store: 1073741824    # 1GB
    max_file_store: 10737418240     # 10GB
}

# 日志配置
log_file: "$NATS_LOG_FILE"
logtime: true
debug: false
trace: false

# 监控配置
monitor_port: 8222

# 客户端连接配置
max_connections: 1000
max_control_line: 4096
max_payload: 1048576
max_pending: 67108864

# 认证配置（可选）
# authorization {
#     users = [
#         {user: "marketprism", password: "marketprism123"}
#     ]
# }

# 集群配置（单节点模式暂时禁用）
# cluster {
#     name: "marketprism-cluster"
#     listen: "0.0.0.0:6222"
# }
EOF

    echo "✅ NATS配置文件已生成: $NATS_CONFIG_FILE"
}

# 初始化JetStream
init_jetstream() {
    echo "⏳ 等待NATS服务器启动..."
    
    # 等待NATS服务器就绪
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s http://localhost:8222/healthz > /dev/null 2>&1; then
            echo "✅ NATS服务器已就绪"
            break
        fi
        
        echo "   尝试 $attempt/$max_attempts: NATS服务器未就绪"
        sleep 2
        attempt=$((attempt + 1))
    done
    
    if [ $attempt -gt $max_attempts ]; then
        echo "❌ NATS服务器启动超时"
        return 1
    fi
    
    # 初始化JetStream配置
    echo "🔧 初始化JetStream配置..."
    python3 init_jetstream.py --wait --config nats_config.yaml
    
    if [ $? -eq 0 ]; then
        echo "✅ JetStream初始化完成"
    else
        echo "❌ JetStream初始化失败"
        return 1
    fi
}

# 信号处理
cleanup() {
    echo "🛑 收到停止信号，正在清理..."
    
    # 停止后台进程
    kill $(jobs -p) 2>/dev/null || true
    
    # 等待进程结束
    wait
    
    echo "✅ 清理完成"
    exit 0
}

trap cleanup SIGTERM SIGINT

# 生成配置文件
generate_nats_config

# 启动NATS服务器
echo "🎯 启动NATS服务器..."
nats-server -c $NATS_CONFIG_FILE &
NATS_PID=$!

# 等待NATS启动并初始化JetStream
sleep 5
init_jetstream

# 保持容器运行
echo "✅ MarketPrism消息代理已启动"
echo "📊 监控地址: http://localhost:8222"
echo "🔌 客户端连接: nats://localhost:4222"

# 等待NATS进程
wait $NATS_PID
