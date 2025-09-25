#!/bin/bash
# MarketPrism完整数据链路启动脚本
# 按正确顺序启动所有服务，确保数据流的完整性

set -euo pipefail

# 配置参数
WORKSPACE_ROOT="/home/ubuntu/marketprism"
VENV_PATH="$WORKSPACE_ROOT/venv"
LOG_DIR="$WORKSPACE_ROOT/logs"
PID_DIR="$WORKSPACE_ROOT/temp"

# 创建必要目录
mkdir -p "$LOG_DIR" "$PID_DIR"

echo "=== MarketPrism完整数据链路启动 ==="
echo "工作目录: $WORKSPACE_ROOT"
echo "虚拟环境: $VENV_PATH"
echo "日志目录: $LOG_DIR"

# 激活虚拟环境
cd "$WORKSPACE_ROOT"
source "$VENV_PATH/bin/activate"

# 1. 检查基础设施
echo -e "\n1. 检查基础设施状态:"
echo -n "  NATS JetStream: "
if curl -s http://127.0.0.1:8222/healthz >/dev/null; then
    echo "✅ 运行中"
else
    echo "❌ 未运行"
    echo "请先启动NATS JetStream: docker-compose -f services/message-broker/docker-compose.yml up -d"
    exit 1
fi

echo -n "  ClickHouse: "
if curl -s "http://127.0.0.1:8123/?query=SELECT%201" >/dev/null; then
    echo "✅ 运行中"
else
    echo "❌ 未运行"
    echo "请先启动ClickHouse: docker-compose -f services/data-storage-service/docker-compose.tiered-storage.yml up -d"
    exit 1
fi

# 2. 启动数据采集器
echo -e "\n2. 启动数据采集器:"
COLLECTOR_CMD="python services/data-collector/unified_collector_main.py --config services/data-collector/config/collector/unified_data_collection.yaml"
echo "  命令: $COLLECTOR_CMD"
$COLLECTOR_CMD > "$LOG_DIR/collector.log" 2>&1 &
COLLECTOR_PID=$!
echo $COLLECTOR_PID > "$PID_DIR/collector.pid"
echo "  PID: $COLLECTOR_PID"

# 等待数据采集器启动
echo "  等待数据采集器启动..."
sleep 15

# 检查数据采集器健康状态
echo -n "  健康检查(8087): "
if curl -s http://127.0.0.1:8087/health >/dev/null; then
    echo "✅ 正常"
else
    echo "❌ 异常"
    echo "数据采集器启动失败，请检查日志: $LOG_DIR/collector.log"
    exit 1
fi

# 3. 启动热端存储服务
echo -e "\n3. 启动热端存储服务:"
HOT_CMD="python services/data-storage-service/main.py --mode hot --config services/data-storage-service/config/tiered_storage_config.yaml"
echo "  命令: $HOT_CMD"
$HOT_CMD > "$LOG_DIR/hot_storage.log" 2>&1 &
HOT_PID=$!
echo $HOT_PID > "$PID_DIR/hot_storage.pid"
echo "  PID: $HOT_PID"

# 等待热端存储服务启动
echo "  等待热端存储服务启动..."
sleep 10

# 检查热端存储服务健康状态
echo -n "  健康检查(8085): "
if curl -s http://127.0.0.1:8085/health >/dev/null; then
    echo "✅ 正常"
else
    echo "❌ 异常"
    echo "热端存储服务启动失败，请检查日志: $LOG_DIR/hot_storage.log"
    exit 1
fi

# 4. 显示服务状态
echo -e "\n4. 服务状态总览:"
echo "  基础设施:"
echo "    NATS JetStream: http://127.0.0.1:8222 (监控)"
echo "    ClickHouse: http://127.0.0.1:8123 (HTTP API)"
echo "  应用服务:"
echo "    数据采集器: PID $COLLECTOR_PID, 健康检查 http://127.0.0.1:8087/health"
echo "    热端存储: PID $HOT_PID, 健康检查 http://127.0.0.1:8085/health"
echo "  日志文件:"
echo "    数据采集器: $LOG_DIR/collector.log"
echo "    热端存储: $LOG_DIR/hot_storage.log"

# 5. 提供冷端存储启动命令
echo -e "\n5. 冷端存储服务（按需启动）:"
echo "  启动命令: python services/data-storage-service/main.py --mode cold --config services/data-storage-service/config/tiered_storage_config.yaml"
echo "  健康检查: http://127.0.0.1:8086/health"

echo -e "\n=== ✅ MarketPrism数据链路启动完成！ ==="
echo "数据流: 交易所 → 数据采集器(8087) → NATS JetStream → 热端存储(8085) → ClickHouse"
echo "停止服务: bash scripts/stop_marketprism.sh"
echo "查看状态: bash scripts/status_marketprism.sh"
