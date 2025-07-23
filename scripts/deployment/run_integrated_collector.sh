#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 清理函数
cleanup() {
    echo -e "${RED}正在停止所有服务...${NC}"
    # 停止收集器进程
    if [ ! -z "$COLLECTOR_PID" ]; then
        kill $COLLECTOR_PID 2>/dev/null || true
    fi
    # 确保没有其他收集器进程在运行
    pkill -f "collector(_mock|_integrated)?" 2>/dev/null || true
    echo -e "${GREEN}所有服务已停止${NC}"
    exit 0
}

# 捕获中断信号
trap cleanup INT TERM

echo -e "${BLUE}===== 编译并运行MarketPrism集成版收集器 =====${NC}"

# 确保logs目录存在
mkdir -p logs

# 停止已有的收集器进程
echo -e "${BLUE}停止已有的收集器进程...${NC}"
pkill -f "collector(_mock|_integrated)?" 2>/dev/null || true
echo -e "${GREEN}已尝试停止所有收集器进程${NC}"
sleep 2

# 检查是否有进程在使用8081端口
port_check=$(lsof -i:8081 2>/dev/null)
if [ ! -z "$port_check" ]; then
    echo -e "${YELLOW}端口8081已被占用，尝试释放...${NC}"
    lsof -i:8081 -t | xargs kill -9 2>/dev/null || true
    sleep 2
fi

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

# 启动Go真实收集器
echo -e "${BLUE}启动真实数据收集器...${NC}"
cd services/go-collector/dist
# 🔧 配置文件清理：使用统一配置文件
./collector -config ../../../config/collector/unified_data_collection.yaml > ../../../logs/collector_real.log 2>&1 &
COLLECTOR_PID=$!
cd ../../../
echo -e "${GREEN}真实数据收集器已启动，PID: ${COLLECTOR_PID}${NC}"

# 等待收集器启动
echo -e "${BLUE}等待收集器初始化...${NC}"
sleep 3

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