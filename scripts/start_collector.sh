#!/bin/bash

# MarketPrism数据收集器启动脚本
# 包含完整的预检查和错误处理

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COLLECTOR_DIR="$PROJECT_ROOT/services/data-collector"
VENV_PATH="$PROJECT_ROOT/venv"
CONFIG_FILE="$PROJECT_ROOT/config/collector/unified_data_collection.yaml"

log_info "MarketPrism数据收集器启动脚本"
log_info "项目根目录: $PROJECT_ROOT"

# 1. 检查项目结构
log_info "检查项目结构..."
if [ ! -d "$COLLECTOR_DIR" ]; then
    log_error "数据收集器目录不存在: $COLLECTOR_DIR"
    exit 1
fi

if [ ! -f "$COLLECTOR_DIR/unified_collector_main.py" ]; then
    log_error "主程序文件不存在: $COLLECTOR_DIR/unified_collector_main.py"
    exit 1
fi

if [ ! -f "$CONFIG_FILE" ]; then
    log_error "配置文件不存在: $CONFIG_FILE"
    exit 1
fi

log_success "项目结构检查通过"

# 2. 检查虚拟环境
log_info "检查Python虚拟环境..."
if [ ! -d "$VENV_PATH" ]; then
    log_error "虚拟环境不存在: $VENV_PATH"
    log_info "请先创建虚拟环境: python -m venv venv"
    exit 1
fi

if [ ! -f "$VENV_PATH/bin/python" ]; then
    log_error "虚拟环境Python解释器不存在: $VENV_PATH/bin/python"
    exit 1
fi

log_success "虚拟环境检查通过"

# 3. 检查配置文件语法
log_info "检查配置文件语法..."
if ! "$VENV_PATH/bin/python" -c "import yaml; yaml.safe_load(open('$CONFIG_FILE'))" 2>/dev/null; then
    log_error "配置文件语法错误: $CONFIG_FILE"
    log_info "请检查YAML语法是否正确"
    exit 1
fi

log_success "配置文件语法检查通过"

# 4. 检查NATS服务器
log_info "检查NATS服务器状态..."
if ! command -v nc &> /dev/null; then
    log_warning "nc命令不存在，跳过NATS连接检查"
else
    if ! nc -z localhost 4222 2>/dev/null; then
        log_error "NATS服务器未运行或端口4222不可访问"
        log_info "请启动NATS服务器: systemctl start nats-server"
        exit 1
    fi
    log_success "NATS服务器连接检查通过"
fi

# 5. 检查系统资源
log_info "检查系统资源..."
AVAILABLE_MEMORY=$(free -m | awk 'NR==2{printf "%.0f", $7}')
if [ "$AVAILABLE_MEMORY" -lt 1000 ]; then
    log_warning "可用内存不足1GB (当前: ${AVAILABLE_MEMORY}MB)，可能影响性能"
fi

CPU_CORES=$(nproc)
if [ "$CPU_CORES" -lt 2 ]; then
    log_warning "CPU核心数不足2个 (当前: ${CPU_CORES}个)，可能影响性能"
fi

log_success "系统资源检查完成"

# 6. 显示配置信息
log_info "当前配置信息:"
echo "  - 项目根目录: $PROJECT_ROOT"
echo "  - 虚拟环境: $VENV_PATH"
echo "  - 配置文件: $CONFIG_FILE"
echo "  - 可用内存: ${AVAILABLE_MEMORY}MB"
echo "  - CPU核心: ${CPU_CORES}个"

# 7. 启动确认
echo ""
read -p "是否启动MarketPrism数据收集器? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "启动已取消"
    exit 0
fi

# 8. 启动数据收集器
log_info "启动MarketPrism数据收集器..."
cd "$COLLECTOR_DIR"

# 设置环境变量
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# 启动程序
exec "$VENV_PATH/bin/python" unified_collector_main.py

# 注意：exec会替换当前进程，所以下面的代码不会执行
log_success "数据收集器启动成功"
