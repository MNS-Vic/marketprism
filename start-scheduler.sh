#!/bin/bash

# ANSI颜色代码
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

if ! python3 -c "import sys; from packaging.version import parse; sys.exit(0) if parse(sys.version) >= parse('$REQUIRED_PYTHON_VERSION') else sys.exit(1)"; then
    echo -e "${RED}❌ 错误: Python 版本不满足要求! 需要 >= $REQUIRED_PYTHON_VERSION, 当前版本为 $CURRENT_PYTHON_VERSION.${NC}"
    echo -e "${YELLOW}请升级您的 Python 版本或使用 pyenv 等工具切换到兼容版本。${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Python 版本检查通过 (${CURRENT_PYTHON_VERSION}).${NC}"

# 检查核心配置文件
CONFIG_PATH="$PROJECT_ROOT/config/services.yaml"
if [ ! -f "$CONFIG_PATH" ]; then
    echo -e "${RED}❌ 错误: 核心配置文件未找到! ($CONFIG_PATH)${NC}"
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

# 设置PYTHONPATH
export PYTHONPATH="$PROJECT_ROOT"
echo -e "${BLUE}PYTHONPATH set to: $PYTHONPATH${NC}"

# 启动服务
echo -e "\n${GREEN}🚀 启动Scheduler服务...${NC}"

python3 "$PROJECT_ROOT/services/scheduler/main.py"