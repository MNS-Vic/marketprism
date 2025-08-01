#!/bin/bash
# MarketPrism 分层数据存储端到端验证启动脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$(dirname "$SERVICE_DIR")")"

echo -e "${BLUE}🚀 MarketPrism 分层数据存储端到端验证${NC}"
echo "=================================================="

# 检查Python环境
echo -e "${YELLOW}📋 检查Python环境...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 未安装${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✅ Python版本: $PYTHON_VERSION${NC}"

# 检查虚拟环境
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo -e "${GREEN}✅ 虚拟环境已激活: $VIRTUAL_ENV${NC}"
else
    echo -e "${YELLOW}⚠️ 未检测到虚拟环境，建议激活虚拟环境${NC}"
fi

# 检查依赖
echo -e "${YELLOW}📦 检查Python依赖...${NC}"
cd "$PROJECT_ROOT"

# 检查核心依赖
REQUIRED_PACKAGES=("asyncio-nats-client" "clickhouse-driver" "structlog" "PyYAML")
MISSING_PACKAGES=()

for package in "${REQUIRED_PACKAGES[@]}"; do
    if ! python3 -c "import ${package//-/_}" &> /dev/null; then
        MISSING_PACKAGES+=("$package")
    fi
done

if [ ${#MISSING_PACKAGES[@]} -ne 0 ]; then
    echo -e "${RED}❌ 缺少依赖包: ${MISSING_PACKAGES[*]}${NC}"
    echo -e "${YELLOW}💡 请运行以下命令安装依赖:${NC}"
    echo "pip install ${MISSING_PACKAGES[*]}"
    exit 1
fi

echo -e "${GREEN}✅ Python依赖检查完成${NC}"

# 检查配置文件
echo -e "${YELLOW}⚙️ 检查配置文件...${NC}"
CONFIG_FILE="$SERVICE_DIR/config/tiered_storage_config.yaml"

if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}❌ 配置文件不存在: $CONFIG_FILE${NC}"
    exit 1
fi

echo -e "${GREEN}✅ 配置文件存在: $CONFIG_FILE${NC}"

# 检查ClickHouse连接
echo -e "${YELLOW}🗄️ 检查ClickHouse连接...${NC}"

# 从配置文件读取ClickHouse配置
CLICKHOUSE_HOST=$(python3 -c "
import yaml
with open('$CONFIG_FILE', 'r') as f:
    config = yaml.safe_load(f)
print(config.get('hot_storage', {}).get('clickhouse_host', 'localhost'))
")

CLICKHOUSE_PORT=$(python3 -c "
import yaml
with open('$CONFIG_FILE', 'r') as f:
    config = yaml.safe_load(f)
print(config.get('hot_storage', {}).get('clickhouse_http_port', 8123))
")

echo "检查ClickHouse连接: $CLICKHOUSE_HOST:$CLICKHOUSE_PORT"

if command -v curl &> /dev/null; then
    if curl -s "http://$CLICKHOUSE_HOST:$CLICKHOUSE_PORT/ping" &> /dev/null; then
        echo -e "${GREEN}✅ ClickHouse连接正常${NC}"
    else
        echo -e "${RED}❌ ClickHouse连接失败${NC}"
        echo -e "${YELLOW}💡 请确保ClickHouse服务正在运行${NC}"
        echo "   Docker: docker-compose up clickhouse"
        echo "   或检查配置文件中的连接信息"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠️ curl未安装，跳过ClickHouse连接检查${NC}"
fi

# 检查NATS连接
echo -e "${YELLOW}📡 检查NATS连接...${NC}"

NATS_URL=$(python3 -c "
import yaml
with open('$CONFIG_FILE', 'r') as f:
    config = yaml.safe_load(f)
print(config.get('nats', {}).get('url', 'nats://localhost:4222'))
")

NATS_HOST=$(echo "$NATS_URL" | sed 's|nats://||' | cut -d':' -f1)
NATS_PORT=$(echo "$NATS_URL" | sed 's|nats://||' | cut -d':' -f2)

echo "检查NATS连接: $NATS_HOST:$NATS_PORT"

if command -v nc &> /dev/null; then
    if nc -z "$NATS_HOST" "$NATS_PORT" 2>/dev/null; then
        echo -e "${GREEN}✅ NATS连接正常${NC}"
    else
        echo -e "${RED}❌ NATS连接失败${NC}"
        echo -e "${YELLOW}💡 请确保NATS服务正在运行${NC}"
        echo "   Docker: docker-compose up nats"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠️ netcat未安装，跳过NATS连接检查${NC}"
fi

# 创建日志目录
echo -e "${YELLOW}📁 创建日志目录...${NC}"
LOG_DIR="$SERVICE_DIR/logs"
mkdir -p "$LOG_DIR"
echo -e "${GREEN}✅ 日志目录: $LOG_DIR${NC}"

# 选择验证模式
echo ""
echo -e "${BLUE}🎯 选择验证模式:${NC}"
echo "1) 初始化ClickHouse数据库"
echo "2) 运行端到端验证"
echo "3) 完整验证（初始化 + 验证）"
echo "4) 退出"

read -p "请选择 (1-4): " choice

case $choice in
    1)
        echo -e "${YELLOW}🏗️ 初始化ClickHouse数据库...${NC}"
        cd "$SERVICE_DIR"
        python3 scripts/init_clickhouse.py
        ;;
    2)
        echo -e "${YELLOW}🔍 运行端到端验证...${NC}"
        cd "$SERVICE_DIR"
        python3 scripts/end_to_end_validation.py
        ;;
    3)
        echo -e "${YELLOW}🚀 运行完整验证...${NC}"
        cd "$SERVICE_DIR"
        
        echo -e "${BLUE}步骤 1/2: 初始化ClickHouse数据库${NC}"
        python3 scripts/init_clickhouse.py
        
        echo ""
        echo -e "${BLUE}步骤 2/2: 运行端到端验证${NC}"
        python3 scripts/end_to_end_validation.py
        ;;
    4)
        echo -e "${YELLOW}👋 退出验证${NC}"
        exit 0
        ;;
    *)
        echo -e "${RED}❌ 无效选择${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}🎉 验证完成！${NC}"
echo -e "${BLUE}📄 查看详细日志: $LOG_DIR${NC}"
