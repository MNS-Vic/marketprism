#!/bin/bash

# Data Storage Service 一键启动脚本
# 这个脚本可以在任何地方独立部署和运行数据存储服务

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
echo "🗄️  MarketPrism Data Storage Service 一键启动器"
echo "=================================================="

# 检测项目根目录
if [ -f "services/data-storage-service/main.py" ]; then
    PROJECT_ROOT=$(pwd)
elif [ -f "../services/data-storage-service/main.py" ]; then
    PROJECT_ROOT=$(cd .. && pwd)
elif [ -f "../../services/data-storage-service/main.py" ]; then
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
    "services/data-storage-service/main.py"
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
    pip install -q aiohttp pyyaml structlog clickhouse-driver clickhouse-connect redis psutil
fi

log_success "依赖安装完成"

# 检查配置文件
log_info "检查配置文件..."
if ! python3 -c "
import yaml
with open('config/services.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)
    storage_config = config.get('services', {}).get('data-storage-service', {})
    if not storage_config:
        print('ERROR: Data Storage Service配置不存在')
        exit(1)
    print(f'Data Storage Service将在端口 {storage_config.get(\"port\", 8082)} 上启动')
    
    # 检查数据库配置
    db_config = storage_config.get('database', {}).get('clickhouse', {})
    print(f'ClickHouse连接: {db_config.get(\"host\", \"localhost\")}:{db_config.get(\"port\", 8123)}')
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
    print(config['services']['data-storage-service']['port'])
")

if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
    log_warning "端口 $PORT 已被占用，尝试停止现有服务..."
    pkill -f "data-storage-service" || true
    sleep 2
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
        log_error "无法释放端口 $PORT，请手动停止占用进程"
        exit 1
    fi
fi

# 检查 ClickHouse 连接（可选）
log_info "检查 ClickHouse 连接..."
CH_HOST=$(python3 -c "
import yaml
with open('config/services.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)
    db_config = config['services']['data-storage-service']['database']['clickhouse']
    print(f\"{db_config.get('host', 'localhost')}:{db_config.get('port', 8123)}\")
")

log_info "ClickHouse 地址: $CH_HOST"
log_warning "注意：如果 ClickHouse 未运行，服务仍然可以启动，但数据存储功能将受限"

# 设置环境变量
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
export MARKETPRISM_ENV="${MARKETPRISM_ENV:-development}"
export MARKETPRISM_LOG_LEVEL="${MARKETPRISM_LOG_LEVEL:-INFO}"

# 创建数据目录
mkdir -p data/storage
mkdir -p logs

# 启动服务
log_info "启动 Data Storage Service..."
log_info "端口: $PORT"
log_info "ClickHouse: $CH_HOST"
log_info "环境: $MARKETPRISM_ENV"
log_info "日志级别: $MARKETPRISM_LOG_LEVEL"

echo ""
echo "🌟 服务访问信息:"
echo "   - 健康检查: http://localhost:$PORT/health"
echo "   - 存储状态: http://localhost:$PORT/api/v1/storage/status"
echo "   - 数据库状态: http://localhost:$PORT/api/v1/storage/database/status"
echo "   - 热存储状态: http://localhost:$PORT/api/v1/storage/hot/status"
echo "   - 冷存储状态: http://localhost:$PORT/api/v1/storage/cold/status"
echo "   - Prometheus指标: http://localhost:$PORT/metrics"
echo ""
echo "💽 存储特性:"
echo "   - 热存储 (Redis): 1小时内数据，快速访问"
echo "   - 冷存储 (ClickHouse): 长期数据，高压缩比"
echo "   - 自动归档: 超过24小时数据自动转移"
echo "   - 数据压缩: 自动优化存储空间"
echo ""
echo "📋 按 Ctrl+C 停止服务"
echo "=================================================="

# 启动服务 (前台运行)
cd services/data-storage-service
python3 main.py 2>&1 | tee ../../logs/data-storage-$(date +%Y%m%d_%H%M%S).log