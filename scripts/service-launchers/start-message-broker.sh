#!/bin/bash

# Message Broker Service 一键启动脚本
# 这个脚本可以在任何地方独立部署和运行消息代理服务

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
echo "📨 MarketPrism Message Broker Service 一键启动器"
echo "=================================================="

# 检测项目根目录
if [ -f "services/message-broker-service/main.py" ]; then
    PROJECT_ROOT=$(pwd)
elif [ -f "../services/message-broker-service/main.py" ]; then
    PROJECT_ROOT=$(cd .. && pwd)
elif [ -f "../../services/message-broker-service/main.py" ]; then
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
    "services/message-broker-service/main.py"
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

# 检查 NATS Server
log_info "检查 NATS Server..."
if command -v nats-server &> /dev/null; then
    NATS_VERSION=$(nats-server --version | head -n1)
    log_success "NATS Server 已安装: $NATS_VERSION"
else
    log_warning "NATS Server 未安装，将尝试自动安装..."
    
    # 尝试通过包管理器安装 NATS
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            brew install nats-server
        else
            log_error "请安装 Homebrew 后重试，或手动安装 NATS Server"
            log_error "安装命令: brew install nats-server"
            exit 1
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        log_info "Linux环境，请参考 https://docs.nats.io/running-a-nats-service/introduction/installation 安装 NATS Server"
        log_warning "继续启动，但NATS功能可能受限"
    else
        log_warning "未知操作系统，NATS Server可能需要手动安装"
    fi
fi

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
    pip install -q aiohttp pyyaml structlog asyncio-nats psutil
fi

log_success "依赖安装完成"

# 检查配置文件
log_info "检查配置文件..."
if ! python3 -c "
import yaml
with open('config/services.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)
    broker_config = config.get('services', {}).get('message-broker-service', {})
    if not broker_config:
        print('ERROR: Message Broker Service配置不存在')
        exit(1)
    print(f'Message Broker Service将在端口 {broker_config.get(\"port\", 8085)} 上启动')
    
    # 检查流配置
    streams = broker_config.get('streams', {})
    print(f'配置的流数量: {len(streams)}')
    for stream_name, stream_config in streams.items():
        print(f'  - {stream_name}: {stream_config.get(\"subjects\", [])}')
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
    print(config['services']['message-broker-service']['port'])
")

if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
    log_warning "端口 $PORT 已被占用，尝试停止现有服务..."
    pkill -f "message-broker-service" || true
    sleep 2
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
        log_error "无法释放端口 $PORT，请手动停止占用进程"
        exit 1
    fi
fi

# 检查NATS端口 (4222)
if lsof -Pi :4222 -sTCP:LISTEN -t >/dev/null ; then
    log_info "NATS Server (端口4222) 已在运行"
else
    log_warning "NATS Server 未运行，服务将尝试启动内置NATS"
fi

# 设置环境变量
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
export MARKETPRISM_ENV="${MARKETPRISM_ENV:-development}"
export MARKETPRISM_LOG_LEVEL="${MARKETPRISM_LOG_LEVEL:-INFO}"

# 创建NATS数据目录
mkdir -p data/nats/jetstream
mkdir -p logs/nats

# 启动服务
log_info "启动 Message Broker Service..."
log_info "端口: $PORT"
log_info "NATS端口: 4222"
log_info "环境: $MARKETPRISM_ENV"
log_info "日志级别: $MARKETPRISM_LOG_LEVEL"

echo ""
echo "🌟 服务访问信息:"
echo "   - 健康检查: http://localhost:$PORT/health"
echo "   - 代理状态: http://localhost:$PORT/api/v1/broker/status"
echo "   - 流管理: http://localhost:$PORT/api/v1/broker/streams"
echo "   - 消费者管理: http://localhost:$PORT/api/v1/broker/consumers"
echo "   - 发布消息: http://localhost:$PORT/api/v1/broker/publish"
echo "   - Prometheus指标: http://localhost:$PORT/metrics"
echo ""
echo "📨 消息流:"
echo "   - market_data: 市场数据流 (market.data.>)"
echo "   - alerts: 告警流 (alert.>)"
echo "   - system_events: 系统事件流 (system.event.>)"
echo ""
echo "⚙️  JetStream 特性:"
echo "   - 持久化消息存储"
echo "   - 消息重放和恢复"
echo "   - 分布式发布订阅"
echo "   - 消息确认机制"
echo ""
echo "📋 按 Ctrl+C 停止服务"
echo "=================================================="

# 启动服务 (前台运行)
cd services/message-broker-service
python3 main.py 2>&1 | tee ../../logs/message-broker-$(date +%Y%m%d_%H%M%S).log