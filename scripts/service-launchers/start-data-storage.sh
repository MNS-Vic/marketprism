#!/bin/bash

# MarketPrism Data Storage Service Launcher
# 数据存储服务启动脚本
# 端口: 8082

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 服务配置
SERVICE_NAME="data-storage"
SERVICE_PORT=8082
SERVICE_PATH="services/data-storage-service"
SERVICE_MAIN="main.py"
SERVICE_DESCRIPTION="数据存储服务 - ClickHouse/Redis热冷存储管理"

# 项目根目录检测
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

echo -e "${BLUE}🚀 MarketPrism ${SERVICE_DESCRIPTION}${NC}"
echo -e "${BLUE}📁 项目根目录: ${PROJECT_ROOT}${NC}"
echo -e "${BLUE}🔌 监听端口: ${SERVICE_PORT}${NC}"
echo ""

# 切换到项目根目录
cd "$PROJECT_ROOT"

# 检查项目结构
if [[ ! -d "$SERVICE_PATH" ]]; then
    echo -e "${RED}❌ 服务目录不存在: $SERVICE_PATH${NC}"
    exit 1
fi

if [[ ! -f "$SERVICE_PATH/$SERVICE_MAIN" ]]; then
    echo -e "${RED}❌ 服务主文件不存在: $SERVICE_PATH/$SERVICE_MAIN${NC}"
    exit 1
fi

# Python环境检查
echo -e "${YELLOW}🔍 检查Python环境...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3未安装${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo -e "${GREEN}✅ Python版本: $PYTHON_VERSION${NC}"

# 虚拟环境激活
VENV_PATH="$PROJECT_ROOT/venv"
if [[ -d "$VENV_PATH" ]]; then
    echo -e "${YELLOW}🔄 激活虚拟环境...${NC}"
    source "$VENV_PATH/bin/activate"
    echo -e "${GREEN}✅ 虚拟环境已激活${NC}"
else
    echo -e "${YELLOW}⚠️  虚拟环境不存在，创建新环境...${NC}"
    python3 -m venv "$VENV_PATH"
    source "$VENV_PATH/bin/activate"
    echo -e "${GREEN}✅ 虚拟环境已创建并激活${NC}"
fi

# 依赖检查和安装
echo -e "${YELLOW}🔍 检查Python依赖...${NC}"
REQUIRED_PACKAGES=(
    "aiohttp"
    "pyyaml"
    "structlog"
    "prometheus_client"
    "psutil"
    "clickhouse-driver"
    "clickhouse-connect"
    "redis"
    "aiochclient"
)

for package in "${REQUIRED_PACKAGES[@]}"; do
    import_name="$package"
    if [[ "$package" == "pyyaml" ]]; then
        import_name="yaml"
    elif [[ "$package" == "clickhouse-driver" ]]; then
        import_name="clickhouse_driver"
    elif [[ "$package" == "clickhouse-connect" ]]; then
        import_name="clickhouse_connect"
    fi
    
    if ! python -c "import $import_name" 2>/dev/null; then
        echo -e "${YELLOW}📦 安装缺失依赖: $package${NC}"
        pip install "$package" --quiet
    fi
done
echo -e "${GREEN}✅ 所有依赖已安装${NC}"

# 端口冲突检查
echo -e "${YELLOW}🔍 检查端口 $SERVICE_PORT...${NC}"
if lsof -Pi :$SERVICE_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${RED}❌ 端口 $SERVICE_PORT 已被占用${NC}"
    echo -e "${YELLOW}🔍 占用端口的进程:${NC}"
    lsof -Pi :$SERVICE_PORT -sTCP:LISTEN
    echo ""
    read -p "是否强制终止占用进程并继续? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        lsof -Pi :$SERVICE_PORT -sTCP:LISTEN -t | xargs kill -9
        echo -e "${GREEN}✅ 已终止占用进程${NC}"
    else
        echo -e "${YELLOW}⚠️  启动取消${NC}"
        exit 1
    fi
fi

# 配置文件检查
CONFIG_FILE="$PROJECT_ROOT/config/services.yaml"
if [[ -f "$CONFIG_FILE" ]]; then
    echo -e "${GREEN}✅ 配置文件存在: $CONFIG_FILE${NC}"
else
    echo -e "${YELLOW}⚠️  配置文件不存在，将使用默认配置${NC}"
fi

# 日志目录创建
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

# 启动服务
echo ""
echo -e "${GREEN}🚀 启动 ${SERVICE_DESCRIPTION}...${NC}"
echo -e "${BLUE}📁 工作目录: $PROJECT_ROOT/$SERVICE_PATH${NC}"
echo -e "${BLUE}🐍 Python解释器: $(which python)${NC}"
echo -e "${BLUE}📊 实时日志将显示在下方...${NC}"
echo ""
echo -e "${YELLOW}================================================${NC}"

cd "$PROJECT_ROOT/$SERVICE_PATH"

# 设置环境变量
export PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/core:$PYTHONPATH"
export SERVICE_NAME="$SERVICE_NAME"
export SERVICE_PORT="$SERVICE_PORT"

# 启动服务
exec python "$SERVICE_MAIN" 