#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}===== MarketPrism 本地部署启动脚本 =====${NC}"
echo -e "${YELLOW}该脚本将启动基础设施和核心服务${NC}"

# 检查是否已激活Python虚拟环境
if [[ -z "${VIRTUAL_ENV}" ]]; then
    echo -e "${RED}请先激活Python虚拟环境后再运行此脚本${NC}"
    echo "示例: source venv/bin/activate"
    exit 1
fi

echo -e "${BLUE}==== 检查 Docker 服务是否运行 ====${NC}"
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Docker 未运行，请先启动 Docker${NC}"
    exit 1
fi
echo -e "${GREEN}Docker 服务正在运行${NC}"

echo -e "${BLUE}==== 启动 ClickHouse 和 NATS 基础设施 ====${NC}"
docker-compose up -d clickhouse nats
echo -e "${GREEN}ClickHouse 和 NATS 已启动${NC}"

echo -e "${BLUE}==== 等待基础设施准备就绪 ====${NC}"
sleep 5

echo -e "${BLUE}==== 初始化 ClickHouse 数据库 ====${NC}"
python init_clickhouse.py
echo -e "${GREEN}ClickHouse 数据库初始化完成${NC}"

echo -e "${BLUE}==== 创建 NATS 消息流 ====${NC}"
python fix_nats_streams.py
echo -e "${GREEN}NATS 消息流创建完成${NC}"

echo -e "${BLUE}==== 启动数据归档服务 ====${NC}"
python services/data_archiver/main.py &
DATA_ARCHIVER_PID=$!
echo -e "${GREEN}数据归档服务已启动，PID: ${DATA_ARCHIVER_PID}${NC}"

echo -e "${BLUE}==== 启动数据接收服务 ====${NC}"
cd services/ingestion
python start_ingestion.py &
INGESTION_PID=$!
cd ../../
echo -e "${GREEN}数据接收服务已启动，PID: ${INGESTION_PID}${NC}"

echo -e "${BLUE}==== 启动真实数据收集器 ====${NC}"
services/go-collector/dist/collector -config config/collector/real_collector_config.json &
COLLECTOR_PID=$!
echo -e "${GREEN}真实数据收集器已启动，PID: ${COLLECTOR_PID}${NC}"

echo -e "${BLUE}==== 所有服务已启动 ====${NC}"
echo "数据归档服务 PID: ${DATA_ARCHIVER_PID}"
echo "数据接收服务 PID: ${INGESTION_PID}"
echo "真实数据收集器 PID: ${COLLECTOR_PID}"

echo -e "${GREEN}访问服务：${NC}"
echo "- 真实数据收集器: http://localhost:8081"
echo "- ClickHouse: http://localhost:8123"
echo "- NATS监控: http://localhost:8222"

echo -e "${YELLOW}按 CTRL+C 停止所有服务${NC}"

# 捕获中断信号
trap "echo -e '${RED}正在停止所有服务...${NC}'; kill $DATA_ARCHIVER_PID $INGESTION_PID $COLLECTOR_PID; echo -e '${GREEN}所有服务已停止${NC}'; exit 0" INT

# 保持脚本运行
wait 