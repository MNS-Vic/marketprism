#!/bin/bash

# Market Data Collector Service 一键启动脚本
# 这个脚本可以在任何地方独立部署和运行市场数据采集服务

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
echo "📊 MarketPrism Market Data Collector Service 一键启动器"
echo "=================================================="

# 检测项目根目录
if [ -f "services/market-data-collector/main.py" ]; then
    PROJECT_ROOT=$(pwd)
elif [ -f "../services/market-data-collector/main.py" ]; then
    PROJECT_ROOT=$(cd .. && pwd)
elif [ -f "../../services/market-data-collector/main.py" ]; then
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
    "services/market-data-collector/main.py"
    "config/services.yaml"
    "core/service_framework.py"
    "services/python-collector"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -e "$file" ]; then
        log_error "缺少必要文件/目录: $file"
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
    pip install -q aiohttp pyyaml structlog asyncio-nats websockets asyncio psutil
fi

log_success "依赖安装完成"

# 检查配置文件
log_info "检查配置文件..."
if ! python3 -c "
import yaml
with open('config/services.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)
    collector_config = config.get('services', {}).get('market-data-collector', {})
    if not collector_config:
        print('ERROR: Market Data Collector配置不存在')
        exit(1)
    print(f'Market Data Collector将在端口 {collector_config.get(\"port\", 8081)} 上启动')
    print(f'NATS服务器: {collector_config.get(\"nats_url\", \"nats://localhost:4222\")}')
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
    print(config['services']['market-data-collector']['port'])
")

if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
    log_warning "端口 $PORT 已被占用，尝试停止现有服务..."
    pkill -f "market-data-collector" || true
    sleep 2
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
        log_error "无法释放端口 $PORT，请手动停止占用进程"
        exit 1
    fi
fi

# 检查 NATS 连接（可选）
NATS_URL=$(python3 -c "
import yaml
with open('config/services.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)
    print(config['services']['market-data-collector'].get('nats_url', 'nats://localhost:4222'))
")

log_info "检查 NATS 连接: $NATS_URL"
# 这里可以添加 NATS 连接检查，但不是必须的，服务启动时会自动处理

# 设置环境变量
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
export MARKETPRISM_ENV="${MARKETPRISM_ENV:-development}"
export MARKETPRISM_LOG_LEVEL="${MARKETPRISM_LOG_LEVEL:-INFO}"

# 代理配置（如果需要）
if [ -f "scripts/proxy_config.sh" ]; then
    log_info "加载代理配置..."
    source scripts/proxy_config.sh
fi

# 创建日志目录
mkdir -p logs

# 启动服务
log_info "启动 Market Data Collector Service..."
log_info "端口: $PORT"
log_info "NATS URL: $NATS_URL"
log_info "环境: $MARKETPRISM_ENV"
log_info "日志级别: $MARKETPRISM_LOG_LEVEL"

echo ""
echo "🌟 服务访问信息:"
echo "   - 健康检查: http://localhost:$PORT/health"
echo "   - 数据采集状态: http://localhost:$PORT/api/v1/collector/status"
echo "   - 交易所状态: http://localhost:$PORT/api/v1/collector/exchanges"
echo "   - Prometheus指标: http://localhost:$PORT/metrics"
echo ""
echo "📊 支持的交易所:"
echo "   - Binance (现货/期货)"
echo "   - OKX"
echo "   - Deribit"
echo ""
echo "📋 按 Ctrl+C 停止服务"
echo "=================================================="

# 启动服务 (前台运行)
cd services/market-data-collector
python3 main.py 2>&1 | tee ../../logs/market-data-collector-$(date +%Y%m%d_%H%M%S).log