#!/bin/bash

# Market Data Collector Service 一键启动脚本 - 完全自动化
set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "📊 启动 Market Data Collector Service..."

# 脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
VENV_DIR="$PROJECT_ROOT/venv"
PYTHON_VERSION_FILE="$PROJECT_ROOT/.python-version"
REQ_FILE="$PROJECT_ROOT/requirements.txt"

# 检查 .python-version 文件是否存在
if [ ! -f "$PYTHON_VERSION_FILE" ]; then
    echo -e "${RED}❌ 错误: .python-version 文件未找到!${NC}"
    exit 1
fi
REQUIRED_PYTHON_VERSION=$(cat "$PYTHON_VERSION_FILE")

# 检查Python版本
CURRENT_PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')

# 简化版本检查 - 只检查主要版本号
PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')

REQUIRED_MAJOR=$(echo "$REQUIRED_PYTHON_VERSION" | cut -d. -f1)
REQUIRED_MINOR=$(echo "$REQUIRED_PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt "$REQUIRED_MAJOR" ] || ([ "$PYTHON_MAJOR" -eq "$REQUIRED_MAJOR" ] && [ "$PYTHON_MINOR" -lt "$REQUIRED_MINOR" ]); then
    echo -e "${RED}❌ 错误: Python 版本不满足要求! 需要 >= $REQUIRED_PYTHON_VERSION, 当前版本为 $CURRENT_PYTHON_VERSION.${NC}"
    echo -e "${YELLOW}请升级您的 Python 版本或使用 pyenv 等工具切换到兼容版本。${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Python 版本检查通过 (${CURRENT_PYTHON_VERSION}).${NC}"

# 检查核心配置文件
CONFIG_PATH="$PROJECT_ROOT/config/services.yaml"
if [ ! -f "$CONFIG_PATH" ]; then
    echo -e "${RED}❌ 错误: 核心配置文件未找到!${NC}"
    exit 1
fi

# 创建/激活虚拟环境
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}🔧 创建虚拟环境 (Python $CURRENT_PYTHON_VERSION)...${NC}"
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

# 安装/更新依赖
echo -e "${YELLOW}📦 正在安装/更新依赖...${NC}"
if ! pip install -r "$REQ_FILE" -q; then
    echo -e "${RED}❌ 依赖安装失败!${NC}"
    exit 1
fi
echo -e "${GREEN}✅ 依赖安装完成.${NC}"

# 设置PYTHONPATH以解决模块导入问题
export PYTHONPATH="$PROJECT_ROOT/services/data-collector/src:$PROJECT_ROOT"
echo -e "${BLUE}PYTHONPATH set to: $PYTHONPATH${NC}"

# 验证PYTHONPATH中的关键路径
if [ -d "$PROJECT_ROOT/services/data-collector/src/marketprism_collector" ]; then
    echo "✅ Data Collector模块路径存在"
else
    echo "❌ Data Collector模块路径不存在: $PROJECT_ROOT/services/data-collector/src/marketprism_collector"
fi

echo "🔧 避免types模块冲突：不将marketprism_collector直接加入PYTHONPATH"

if [ -f "$PROJECT_ROOT/config/collector.yaml" ]; then
    echo "✅ Collector配置文件存在"
else
    echo "❌ Collector配置文件不存在: $PROJECT_ROOT/config/collector.yaml"
fi

# 代理配置
if [ -f "scripts/proxy_config.sh" ]; then
    source scripts/proxy_config.sh
fi

# 创建日志目录
mkdir -p logs

echo -e "${GREEN}🌟 Data Collector 启动中...${NC}"
echo -e "${BLUE}📊 访问地址: http://localhost:8081${NC}"
echo -e "${BLUE}🏥 健康检查: http://localhost:8081/health${NC}"
echo -e "${BLUE}📈 数据采集状态: http://localhost:8081/api/v1/collector/status${NC}"
echo ""
echo -e "${YELLOW}🔗 支持交易所: Binance, OKX, Deribit${NC}"
echo -e "${YELLOW}📋 按 Ctrl+C 停止服务${NC}"
echo "=================================================="

# 启动服务
echo -e "\n${GREEN}🚀 启动Market Data Collector服务...${NC}"

# 定义主程序路径
MAIN_PY_PATH="$PROJECT_ROOT/services/data-collector/main.py"

# 检查主程序文件是否存在
if [ ! -f "$MAIN_PY_PATH" ]; then
    echo -e "${RED}❌ 错误: 主程序文件未找到! ($MAIN_PY_PATH)${NC}"
    exit 1
fi

# 使用Python直接运行主程序
python3 "$MAIN_PY_PATH" --mode full