#!/bin/bash

# Scheduler Service 一键启动脚本
# 这个脚本可以在任何地方独立部署和运行调度服务

set -e

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

# 脚本信息
echo "=================================================="
echo "⏰ MarketPrism Scheduler Service 一键启动器"
echo "=================================================="

# 检测项目根目录
if [ -f "services/scheduler-service/main.py" ]; then
    PROJECT_ROOT=$(pwd)
elif [ -f "../services/scheduler-service/main.py" ]; then
    PROJECT_ROOT=$(cd .. && pwd)
elif [ -f "../../services/scheduler-service/main.py" ]; then
    PROJECT_ROOT=$(cd ../.. && pwd)
else
    log_error "无法找到 MarketPrism 项目根目录"
    log_error "请在项目根目录或子目录中运行此脚本"
    exit 1
fi

log_info "项目根目录: $PROJECT_ROOT"
cd "$PROJECT_ROOT"

# 检查 Python 版本
if ! command -v python3 &> /dev/null; then
    log_error "Python3 未安装，请先安装 Python 3.8+"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
log_info "Python 版本: $PYTHON_VERSION"

# 检查必要的文件
REQUIRED_FILES=(
    "services/scheduler-service/main.py"
    "config/services.yaml"
    "core/service_framework.py"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        log_error "缺少必要文件: $file"
        exit 1
    fi
done

log_success "所有必要文件检查通过"

# 检查是否有虚拟环境
if [ ! -d "venv" ]; then
    log_info "创建 Python 虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate
log_success "虚拟环境已激活"

# 安装依赖
if [ -f "requirements.txt" ]; then
    log_info "安装项目依赖..."
    pip install -q -r requirements.txt
else
    log_info "安装基本依赖..."
    pip install -q aiohttp pyyaml structlog schedule croniter psutil
fi

log_success "依赖安装完成"

# 检查配置文件
log_info "检查配置文件..."
if ! python3 -c "
import yaml
with open('config/services.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)
    scheduler_config = config.get('services', {}).get('scheduler-service', {})
    if not scheduler_config:
        print('ERROR: Scheduler Service配置不存在')
        exit(1)
    print(f'Scheduler Service将在端口 {scheduler_config.get(\"port\", 8084)} 上启动')
    
    # 检查默认任务配置
    default_tasks = scheduler_config.get('default_tasks', {})
    print(f'默认任务数量: {len(default_tasks)}')
    for task_name, task_config in default_tasks.items():
        if task_config.get('enabled', False):
            print(f'  - {task_name}: {task_config.get(\"cron\", \"未配置\")}')
"; then
    log_error "配置文件验证失败"
    exit 1
fi

log_success "配置文件验证通过"

# 检查端口是否可用
PORT=$(python3 -c "
import yaml
with open('config/services.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)
    print(config['services']['scheduler-service']['port'])
")

if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
    log_warning "端口 $PORT 已被占用，尝试停止现有服务..."
    pkill -f "scheduler-service" || true
    sleep 2
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
        log_error "无法释放端口 $PORT，请手动停止占用进程"
        exit 1
    fi
fi

# 设置环境变量
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
export MARKETPRISM_ENV="${MARKETPRISM_ENV:-development}"
export MARKETPRISM_LOG_LEVEL="${MARKETPRISM_LOG_LEVEL:-INFO}"

# 创建任务日志目录
mkdir -p logs/scheduler
mkdir -p data/scheduler

# 启动服务
log_info "启动 Scheduler Service..."
log_info "端口: $PORT"
log_info "环境: $MARKETPRISM_ENV"
log_info "日志级别: $MARKETPRISM_LOG_LEVEL"

echo ""
echo "🌟 服务访问信息:"
echo "   - 健康检查: http://localhost:$PORT/health"
echo "   - 调度器状态: http://localhost:$PORT/api/v1/scheduler/status"
echo "   - 任务列表: http://localhost:$PORT/api/v1/scheduler/tasks"
echo "   - 任务历史: http://localhost:$PORT/api/v1/scheduler/history"
echo "   - Prometheus指标: http://localhost:$PORT/metrics"
echo ""
echo "⏱️  默认调度任务:"
echo "   - 数据归档: 每天凌晨2点 (0 2 * * *)"
echo "   - 健康检查: 每5分钟 (*/5 * * * *)"
echo "   - 清理任务: 每小时 (0 * * * *)"
echo ""
echo "📋 按 Ctrl+C 停止服务"
echo "=================================================="

# 启动服务 (前台运行)
cd services/scheduler-service
python3 main.py 2>&1 | tee ../../logs/scheduler-$(date +%Y%m%d_%H%M%S).log