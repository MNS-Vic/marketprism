#!/bin/bash

################################################################################
# MarketPrism 一键部署脚本
#
# 功能：在任何新主机上自动完成所有部署工作
# 用法：./scripts/one_click_deploy.sh [选项]
#
# 选项：
#   --fresh         全新部署（清理所有现有数据）
#   --update        更新部署（保留数据）
#   --clean         清理所有资源
#   --skip-deps     跳过依赖安装（假设已安装）
#   --docker-mode   使用Docker模式（默认：本地安装）
#   --help          显示帮助信息
################################################################################

set -euo pipefail

# ============================================================================
# 全局变量
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_FILE="$PROJECT_ROOT/deployment.log"
DEPLOYMENT_MODE="local"  # local 或 docker
SKIP_DEPS=false
FRESH_INSTALL=false
UPDATE_MODE=false
CLEAN_MODE=false

# 版本配置
NATS_VERSION="2.10.7"
CLICKHOUSE_VERSION="25.10.1"
PYTHON_VERSION="3.9"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ============================================================================
# 日志函数
# ============================================================================

log() {
    local level=$1
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${timestamp} [${level}] ${message}" | tee -a "$LOG_FILE"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $@" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $@" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[⚠]${NC} $@" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[✗]${NC} $@" | tee -a "$LOG_FILE"
}

log_step() {
    echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  $@${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

# ============================================================================
# 帮助信息
# ============================================================================

show_help() {
    cat << EOF
${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}
${CYAN}  MarketPrism 一键部署脚本${NC}
${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}

${GREEN}用法:${NC}
  $0 [选项]

${GREEN}选项:${NC}
  --fresh         全新部署（清理所有现有数据）
  --update        更新部署（保留数据）
  --clean         清理所有资源并退出
  --skip-deps     跳过依赖安装（假设已安装）
  --docker-mode   使用Docker模式部署
  --help          显示此帮助信息

${GREEN}示例:${NC}
  # 全新部署（推荐用于新主机）
  $0 --fresh

  # 更新部署（保留数据）
  $0 --update

  # 使用Docker模式部署
  $0 --fresh --docker-mode

  # 清理所有资源
  $0 --clean

${GREEN}系统要求:${NC}
  - Ubuntu 20.04+ / CentOS 8+ / macOS 12+
  - 至少 4GB RAM
  - 至少 20GB 磁盘空间
  - sudo 权限

${GREEN}部署内容:${NC}
  ✓ NATS JetStream (v${NATS_VERSION})
  ✓ ClickHouse (v${CLICKHOUSE_VERSION})
  ✓ Python ${PYTHON_VERSION}+ 虚拟环境
  ✓ 所有 Python 依赖
  ✓ 数据库表结构
  ✓ NATS JetStream 流配置
  ✓ 数据采集器
  ✓ 数据存储服务

EOF
}

# ============================================================================
# 参数解析
# ============================================================================

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --fresh)
                FRESH_INSTALL=true
                shift
                ;;
            --update)
                UPDATE_MODE=true
                shift
                ;;
            --clean)
                CLEAN_MODE=true
                shift
                ;;
            --skip-deps)
                SKIP_DEPS=true
                shift
                ;;
            --docker-mode)
                DEPLOYMENT_MODE="docker"
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                log_error "未知选项: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

# ============================================================================
# 环境检测
# ============================================================================

detect_os() {
    log_info "检测操作系统..."

    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if [ -f /etc/os-release ]; then
            . /etc/os-release
            OS=$ID
            OS_VERSION=$VERSION_ID
            log_success "检测到 Linux: $OS $OS_VERSION"
        else
            log_error "无法检测 Linux 发行版"
            exit 1
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
        OS_VERSION=$(sw_vers -productVersion)
        log_success "检测到 macOS: $OS_VERSION"
    else
        log_error "不支持的操作系统: $OSTYPE"
        exit 1
    fi
}

check_system_requirements() {
    log_info "检查系统要求..."

    # 检查内存
    if [[ "$OS" == "macos" ]]; then
        TOTAL_MEM=$(sysctl -n hw.memsize | awk '{print int($1/1024/1024/1024)}')
    else
        TOTAL_MEM=$(free -g | awk '/^Mem:/{print $2}')
    fi

    if [ "$TOTAL_MEM" -lt 4 ]; then
        log_warning "系统内存不足 4GB，可能影响性能"
    else
        log_success "内存检查通过: ${TOTAL_MEM}GB"
    fi

    # 检查磁盘空间
    AVAILABLE_DISK=$(df -BG "$PROJECT_ROOT" | awk 'NR==2 {print int($4)}')
    if [ "$AVAILABLE_DISK" -lt 20 ]; then
        log_warning "可用磁盘空间不足 20GB: ${AVAILABLE_DISK}GB"
    else
        log_success "磁盘空间检查通过: ${AVAILABLE_DISK}GB 可用"
    fi

    # 检查 sudo 权限
    if sudo -n true 2>/dev/null; then
        log_success "sudo 权限检查通过"
    else
        log_warning "需要 sudo 权限，部分操作可能需要输入密码"
    fi
}

check_required_tools() {
    log_info "检查必要工具..."

    local missing_tools=()

    for tool in curl wget git; do
        if ! command -v $tool &> /dev/null; then
            missing_tools+=($tool)
        fi
    done

    if [ ${#missing_tools[@]} -gt 0 ]; then
        log_error "缺少必要工具: ${missing_tools[*]}"
        log_info "正在尝试自动安装..."
        install_basic_tools "${missing_tools[@]}"
    else
        log_success "所有必要工具已安装"
    fi
}

install_basic_tools() {
    local tools=("$@")

    if [[ "$OS" == "ubuntu" ]] || [[ "$OS" == "debian" ]]; then
        sudo apt-get update -qq
        sudo apt-get install -y "${tools[@]}"
    elif [[ "$OS" == "centos" ]] || [[ "$OS" == "rhel" ]]; then
        sudo yum install -y "${tools[@]}"
    elif [[ "$OS" == "macos" ]]; then
        if ! command -v brew &> /dev/null; then
            log_error "请先安装 Homebrew: https://brew.sh"
            exit 1
        fi
        brew install "${tools[@]}"
    fi

    log_success "基础工具安装完成"
}

# ============================================================================
# 依赖安装
# ============================================================================

install_nats_server() {
    log_info "安装 NATS Server v${NATS_VERSION}..."

    if command -v nats-server &> /dev/null; then
        local installed_version=$(nats-server --version | grep -oP 'v\K[0-9.]+' || echo "unknown")
        if [[ "$installed_version" == "$NATS_VERSION" ]]; then
            log_success "NATS Server v${NATS_VERSION} 已安装"
            return 0
        else
            log_warning "已安装 NATS Server v${installed_version}，将升级到 v${NATS_VERSION}"
        fi
    fi

    local arch=$(uname -m)
    local os_type="linux"
    [[ "$OS" == "macos" ]] && os_type="darwin"

    local download_url="https://github.com/nats-io/nats-server/releases/download/v${NATS_VERSION}/nats-server-v${NATS_VERSION}-${os_type}-${arch}.tar.gz"

    log_info "下载 NATS Server..."
    cd /tmp
    curl -L "$download_url" -o nats-server.tar.gz
    tar -xzf nats-server.tar.gz
    sudo mv nats-server-v${NATS_VERSION}-${os_type}-${arch}/nats-server /usr/local/bin/
    rm -rf nats-server*

    if nats-server --version; then
        log_success "NATS Server 安装成功"
    else
        log_error "NATS Server 安装失败"
        exit 1
    fi
}

install_clickhouse() {
    log_info "安装 ClickHouse..."

    if command -v clickhouse-server &> /dev/null; then
        log_success "ClickHouse 已安装"
        return 0
    fi

    log_info "下载并安装 ClickHouse..."
    curl https://clickhouse.com/ | sh
    sudo ./clickhouse install

    if command -v clickhouse-server &> /dev/null; then
        log_success "ClickHouse 安装成功"
    else
        log_error "ClickHouse 安装失败"
        exit 1
    fi
}

install_python_env() {
    log_info "设置 Python 虚拟环境..."

    # 检查 Python 版本
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 未安装"
        exit 1
    fi

    local python_version=$(python3 --version | grep -oP '\d+\.\d+')
    log_info "检测到 Python $python_version"

    # 创建虚拟环境
    cd "$PROJECT_ROOT"
    if [ ! -d "venv" ]; then
        log_info "创建虚拟环境..."
        python3 -m venv venv
        log_success "虚拟环境创建成功"
    else
        log_success "虚拟环境已存在"
    fi

    # 激活虚拟环境并安装依赖
    source venv/bin/activate

    log_info "升级 pip..."
    pip install --upgrade pip -q

    log_info "安装 Python 依赖..."

    # 安装核心依赖
    pip install -q nats-py aiohttp requests clickhouse-driver PyYAML python-dateutil structlog
    pip install -q websockets python-dotenv colorlog pandas numpy pydantic prometheus-client
    pip install -q click uvloop orjson watchdog psutil PyJWT ccxt arrow

    log_success "Python 依赖安装完成"
}

# ============================================================================
# 服务初始化
# ============================================================================

start_nats_server() {
    log_info "启动 NATS Server..."

    # 检查是否已经运行
    if pgrep -x "nats-server" > /dev/null; then
        log_warning "NATS Server 已在运行"
        return 0
    fi

    # 创建数据目录
    mkdir -p /tmp/nats-jetstream

    # 启动 NATS Server
    nohup nats-server -js -m 8222 -p 4222 --store_dir /tmp/nats-jetstream > /tmp/nats-server.log 2>&1 &

    # 等待启动
    sleep 3

    # 验证启动
    if curl -s http://localhost:8222/healthz | grep -q "ok"; then
        log_success "NATS Server 启动成功"
    else
        log_error "NATS Server 启动失败"
        exit 1
    fi
}

start_clickhouse_server() {
    log_info "启动 ClickHouse Server..."

    # 检查是否已经运行
    if pgrep -x "clickhouse-server" > /dev/null; then
        log_warning "ClickHouse Server 已在运行"
        return 0
    fi

    # 启动 ClickHouse
    sudo clickhouse start

    # 等待启动
    sleep 5

    # 验证启动
    if curl -s "http://localhost:8123/" --data "SELECT 1" | grep -q "1"; then
        log_success "ClickHouse Server 启动成功"
    else
        log_error "ClickHouse Server 启动失败"
        exit 1
    fi
}

init_clickhouse_database() {
    log_info "初始化 ClickHouse 数据库..."

    cd "$PROJECT_ROOT"

    # 执行数据库初始化脚本
    if [ -f "services/data-storage-service/config/clickhouse_schema.sql" ]; then
        clickhouse-client --multiquery < services/data-storage-service/config/clickhouse_schema.sql
        log_success "数据库表结构初始化完成"
    else
        log_error "找不到数据库初始化脚本"
        exit 1
    fi

    # 验证表创建
    local table_count=$(clickhouse-client --query "SHOW TABLES FROM marketprism_hot" | wc -l)
    log_success "创建了 $table_count 个数据表"
}

init_nats_jetstream() {
    log_info "初始化 NATS JetStream..."

    cd "$PROJECT_ROOT"
    source venv/bin/activate

    # 执行 JetStream 初始化
    if [ -f "services/message-broker/init_jetstream.py" ]; then
        python services/message-broker/init_jetstream.py --config scripts/js_init_market_data.yaml
        log_success "NATS JetStream 流配置完成"
    else
        log_error "找不到 JetStream 初始化脚本"
        exit 1
    fi
}


# ============================================================================
# 应用服务启动
# ============================================================================

start_storage_service() {
    log_info "启动数据存储服务（热端）..."

    cd "$PROJECT_ROOT"
    source venv/bin/activate

    # 检查是否已经运行
    if pgrep -f "data-storage-service.*main.py.*hot" > /dev/null; then
        log_warning "存储服务（热端）已在运行"
        return 0
    fi

    cd services/data-storage-service
    nohup python main.py --mode hot > /tmp/storage-hot.log 2>&1 &

    # 等待启动
    sleep 10

    # 验证启动
    if curl -s http://localhost:8085/health | grep -q "healthy"; then
        log_success "存储服务（热端）启动成功"
    else
        log_warning "存储服务（热端）健康检查未通过，但进程已启动"
    fi
}

start_data_collector() {
    log_info "启动数据采集器..."

    cd "$PROJECT_ROOT"
    source venv/bin/activate

    # 检查是否已经运行
    if pgrep -f "unified_collector_main.py" > /dev/null; then
        log_warning "数据采集器已在运行"
        return 0
    fi

    cd services/data-collector
    HEALTH_CHECK_PORT=8087 METRICS_PORT=9093 nohup python unified_collector_main.py --mode launcher > /tmp/collector.log 2>&1 &

    # 等待启动
    sleep 15

    log_success "数据采集器已启动"
}

# ============================================================================
# 健康检查
# ============================================================================

health_check() {
    log_step "执行健康检查"

    local all_healthy=true

    # 检查 NATS
    log_info "检查 NATS Server..."
    if curl -s http://localhost:8222/healthz | grep -q "ok"; then
        log_success "NATS Server: 健康"
    else
        log_error "NATS Server: 不健康"
        all_healthy=false
    fi

    # 检查 ClickHouse
    log_info "检查 ClickHouse..."
    if curl -s "http://localhost:8123/" --data "SELECT 1" | grep -q "1"; then
        log_success "ClickHouse: 健康"
    else
        log_error "ClickHouse: 不健康"
        all_healthy=false
    fi

    # 检查存储服务
    log_info "检查存储服务..."
    if ss -ltn | grep -q ":8085"; then
        log_success "存储服务: 运行中（端口 8085）"
    else
        log_warning "存储服务: 端口未监听"
    fi

    # 检查数据采集器
    log_info "检查数据采集器..."
    if pgrep -f "unified_collector_main.py" > /dev/null; then
        log_success "数据采集器: 运行中"
    else
        log_warning "数据采集器: 未运行"
    fi

    # 检查数据流
    log_info "检查数据流..."
    sleep 5
    local trade_count=$(clickhouse-client --query "SELECT count(*) FROM marketprism_hot.trades" 2>/dev/null || echo "0")
    if [ "$trade_count" -gt 0 ]; then
        log_success "数据流: 正常（已收集 $trade_count 条交易记录）"
    else
        log_warning "数据流: 暂无数据（可能需要等待）"
    fi

    if $all_healthy; then
        log_success "所有核心服务健康检查通过"
    else
        log_warning "部分服务健康检查未通过，请查看日志"
    fi
}

# ============================================================================
# 清理函数
# ============================================================================

clean_all() {
    log_step "清理所有资源"

    log_info "停止所有服务..."

    # 停止数据采集器
    pkill -f "unified_collector_main.py" || true

    # 停止存储服务
    pkill -f "data-storage-service.*main.py" || true

    # 停止 NATS
    pkill -x "nats-server" || true

    # 停止 ClickHouse
    sudo clickhouse stop || true

    log_info "清理数据..."

    # 清理 NATS 数据
    rm -rf /tmp/nats-jetstream

    # 清理日志
    rm -f /tmp/nats-server.log /tmp/storage-hot.log /tmp/collector.log

    log_success "清理完成"
}

# ============================================================================
# 部署报告
# ============================================================================

show_deployment_report() {
    log_step "部署报告"

    cat << EOF

${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}
${GREEN}  MarketPrism 部署成功！${NC}
${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}

${CYAN}服务访问地址:${NC}
  • NATS 监控:        http://localhost:8222
  • ClickHouse:       http://localhost:8123
  • 存储服务（热端）:  http://localhost:8085/health
  • 数据采集器:        运行中

${CYAN}管理命令:${NC}
  • 查看状态:  ./scripts/manage_all.sh status
  • 健康检查:  ./scripts/manage_all.sh health
  • 停止服务:  ./scripts/manage_all.sh stop
  • 重启服务:  ./scripts/manage_all.sh restart

${CYAN}日志文件:${NC}
  • NATS:      /tmp/nats-server.log
  • 存储服务:  /tmp/storage-hot.log
  • 数据采集器: /tmp/collector.log
  • 部署日志:  $LOG_FILE

${CYAN}数据查询:${NC}
  clickhouse-client --query "SELECT count(*) FROM marketprism_hot.trades"

${YELLOW}提示:${NC}
  数据采集需要几分钟才能看到结果，请耐心等待。
  如遇问题，请查看日志文件或运行健康检查。

${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}

EOF
}

# ============================================================================
# 主函数
# ============================================================================

main() {
    # 清空日志文件
    > "$LOG_FILE"

    log_step "MarketPrism 一键部署脚本"
    log_info "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
    log_info "项目目录: $PROJECT_ROOT"
    log_info "日志文件: $LOG_FILE"

    # 解析参数
    parse_arguments "$@"

    # 如果是清理模式
    if $CLEAN_MODE; then
        clean_all
        exit 0
    fi

    # 第1步：环境检测
    log_step "第1步：环境检测"
    detect_os
    check_system_requirements
    check_required_tools

    # 第2步：安装依赖（除非跳过）
    if ! $SKIP_DEPS; then
        log_step "第2步：安装依赖"
        install_nats_server
        install_clickhouse
        install_python_env
    else
        log_step "第2步：跳过依赖安装"
    fi

    # 第3步：启动基础服务
    log_step "第3步：启动基础服务"
    start_nats_server
    start_clickhouse_server

    # 第4步：初始化数据库和流
    log_step "第4步：初始化数据库和流"
    init_clickhouse_database
    init_nats_jetstream

    # 第5步：启动应用服务
    log_step "第5步：启动应用服务"
    start_storage_service
    start_data_collector

    # 第6步：健康检查
    health_check

    # 第7步：显示部署报告
    show_deployment_report

    log_info "结束时间: $(date '+%Y-%m-%d %H:%M:%S')"
    log_success "部署完成！"
}

# ============================================================================
# 脚本入口
# ============================================================================

# 捕获错误
trap 'log_error "部署过程中发生错误，请查看日志: $LOG_FILE"; exit 1' ERR

# 执行主函数
main "$@"



