#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}===== MarketPrism 集成收集器修复和启动脚本 =====${NC}"

# 清理函数
cleanup() {
    echo -e "${RED}正在停止所有服务...${NC}"
    if [ ! -z "$COLLECTOR_PID" ]; then
        kill $COLLECTOR_PID 2>/dev/null
    fi
    pkill -f "collector" 2>/dev/null || true
    echo -e "${GREEN}清理完成${NC}"
}

# 捕获中断信号
trap cleanup EXIT INT TERM

# 停止可能运行的collector进程
pkill -f "collector" 2>/dev/null || true
sleep 2

# 检查Docker服务
echo -e "${BLUE}检查Docker服务...${NC}"
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Docker未运行，请先启动Docker${NC}"
    exit 1
fi
echo -e "${GREEN}Docker服务正在运行${NC}"

# 启动基础设施服务
echo -e "${BLUE}启动基础设施服务...${NC}"
docker-compose up -d nats clickhouse
echo -e "${GREEN}ClickHouse和NATS服务已启动${NC}"

# 等待服务准备就绪
echo -e "${BLUE}等待服务准备就绪...${NC}"
sleep 5

# 初始化ClickHouse数据库
echo -e "${BLUE}初始化ClickHouse数据库...${NC}"
python init_clickhouse.py
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}ClickHouse初始化警告，但继续执行${NC}"
fi
echo -e "${GREEN}ClickHouse数据库已初始化${NC}"

# 修复NATS流
echo -e "${BLUE}创建和修复NATS流...${NC}"
python create_basic_streams.py
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}NATS流创建警告，但继续执行${NC}"
fi
echo -e "${GREEN}NATS流已创建/修复${NC}"

# 修复Go编译环境
echo -e "${BLUE}修复Go编译环境...${NC}"

# 创建必要的目录
mkdir -p services/go-collector/dist
mkdir -p services/go-collector/internal/normalizer/processors

# 更新go.mod文件
echo -e "${BLUE}更新go.mod文件...${NC}"
cat > go.mod << 'EOT'
module github.com/marketprism

go 1.20

require (
	github.com/gorilla/websocket v1.5.0
	github.com/nats-io/nats.go v1.31.0
	go.uber.org/zap v1.26.0
	gopkg.in/yaml.v2 v2.4.0
)

require (
	github.com/klauspost/compress v1.17.0 // indirect
	github.com/nats-io/nkeys v0.4.6 // indirect
	github.com/nats-io/nuid v1.0.1 // indirect
	github.com/prometheus/client_golang v1.18.0 // indirect
	go.uber.org/multierr v1.11.0 // indirect
	golang.org/x/crypto v0.14.0 // indirect
	golang.org/x/sys v0.13.0 // indirect
	golang.org/x/text v0.13.0 // indirect
)

replace github.com/marketprism/services/go-collector => ./services/go-collector
replace github.com/marketprism/services/go-collector/internal/nats => ./services/go-collector/internal/nats
replace github.com/marketprism/services/go-collector/internal/normalizer => ./services/go-collector/internal/normalizer
EOT

# 下载依赖
go mod download
go mod tidy

# 尝试编译真实收集器
echo -e "${BLUE}编译真实收集器...${NC}"
go build -o services/go-collector/dist/collector services/go-collector/main.go services/go-collector/collector_real.go services/go-collector/config_types.go

if [ $? -ne 0 ]; then
    echo -e "${RED}真实收集器编译失败${NC}"
    cleanup
    exit 1
fi

echo -e "${GREEN}真实收集器编译成功${NC}"

# 启动真实收集器
echo -e "${BLUE}启动真实数据收集器...${NC}"
cd services/go-collector/dist
./collector -config ../../../config/collector/real_collector_config.json > ../../../logs/collector_real.log 2>&1 &
COLLECTOR_PID=$!
cd ../../../
echo -e "${GREEN}真实数据收集器已启动，PID: ${COLLECTOR_PID}${NC}"

# 等待收集器启动
echo -e "${BLUE}等待收集器初始化...${NC}"
sleep 5

# 检查收集器是否正在运行
if ! ps -p $COLLECTOR_PID > /dev/null; then
    echo -e "${RED}收集器启动失败，请查看日志文件${NC}"
    cat logs/collector_real.log
    cleanup
    exit 1
fi

# 测试数据流
echo -e "${BLUE}检查数据流...${NC}"
python check_nats_messages.py
echo -e "${GREEN}数据流检查完成${NC}"

# 测试健康检查端点
echo -e "${BLUE}测试健康检查端点...${NC}"
curl -s http://localhost:8081/health
echo ""

# 测试指标端点
echo -e "${BLUE}测试指标端点...${NC}"
curl -s http://localhost:8081/metrics | head -n 5
echo ""

# 显示服务状态
echo -e "${BLUE}所有服务已启动${NC}"
echo "真实数据收集器 PID: ${COLLECTOR_PID}"
echo -e "${YELLOW}日志保存在 logs/collector_real.log${NC}"

echo -e "${GREEN}访问服务：${NC}"
echo "- 收集器健康检查: http://localhost:8081/health"
echo "- 收集器指标: http://localhost:8081/metrics"
echo "- ClickHouse Web界面: http://localhost:8123"
echo "- NATS监控: http://localhost:8222"

echo -e "${YELLOW}按 CTRL+C 停止所有服务${NC}"

# 保持脚本运行
wait $COLLECTOR_PID 