#!/bin/bash

# Monitoring Service 一键启动脚本
# 这个脚本可以在任何地方独立部署和运行监控服务

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
echo "📊 MarketPrism Monitoring Service 一键启动器"
echo "=================================================="

# 检测项目根目录
if [ -f "services/monitoring-service/main.py" ]; then
    PROJECT_ROOT=$(pwd)
elif [ -f "../services/monitoring-service/main.py" ]; then
    PROJECT_ROOT=$(cd .. && pwd)
elif [ -f "../../services/monitoring-service/main.py" ]; then
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
    "services/monitoring-service/main.py"
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
    pip install -q aiohttp pyyaml structlog prometheus_client psutil
fi

log_success "依赖安装完成"

# 检查配置文件
log_info "检查配置文件..."
if ! python3 -c "
import yaml
with open('config/services.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)
    monitoring_config = config.get('services', {}).get('monitoring-service', {})
    if not monitoring_config:
        print('ERROR: Monitoring Service配置不存在')
        exit(1)
    print(f'Monitoring Service将在端口 {monitoring_config.get(\"port\", 8083)} 上启动')
    
    # 检查监控的服务列表
    monitored_services = monitoring_config.get('monitored_services', {})
    print(f'监控服务数量: {len(monitored_services)}')
    for service_name, service_config in monitored_services.items():
        print(f'  - {service_name}: {service_config.get(\"host\", \"localhost\")}:{service_config.get(\"port\", \"未知\")}')
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
    print(config['services']['monitoring-service']['port'])
")

if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
    log_warning "端口 $PORT 已被占用，尝试停止现有服务..."
    pkill -f "monitoring-service" || true
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

# 创建监控数据目录
mkdir -p logs/monitoring
mkdir -p data/monitoring

# 启动服务
log_info "启动 Monitoring Service..."
log_info "端口: $PORT"
log_info "环境: $MARKETPRISM_ENV"
log_info "日志级别: $MARKETPRISM_LOG_LEVEL"

echo ""
echo "🌟 服务访问信息:"
echo "   - 健康检查: http://localhost:$PORT/health"
echo "   - 系统概览: http://localhost:$PORT/api/v1/overview"
echo "   - 服务状态: http://localhost:$PORT/api/v1/services"
echo "   - 告警信息: http://localhost:$PORT/api/v1/alerts"
echo "   - Prometheus指标: http://localhost:$PORT/metrics"
echo ""
echo "📈 监控功能:"
echo "   - 系统资源监控 (CPU、内存、磁盘)"
echo "   - 微服务健康检查"
echo "   - Prometheus指标收集"
echo "   - 智能告警系统"
echo "   - 性能监控统计"
echo ""
echo "🔔 告警规则:"
echo "   - CPU使用率 > 90%"
echo "   - 内存使用率 > 95%"
echo "   - 服务下线检测"
echo "   - 响应时间 > 5秒"
echo "   - 数据处理错误率 > 10%"
echo ""
echo "📋 按 Ctrl+C 停止服务"
echo "=================================================="

# 启动服务 (前台运行)
cd services/monitoring-service
python3 main.py 2>&1 | tee ../../logs/monitoring-$(date +%Y%m%d_%H%M%S).log