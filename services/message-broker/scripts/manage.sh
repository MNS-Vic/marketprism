#!/bin/bash

################################################################################
# MarketPrism Message Broker (NATS JetStream) 管理脚本
#
# 功能：独立部署和管理 NATS JetStream 消息代理服务
# 用法：./manage.sh [命令]
#
# 命令：
#   install-deps  - 安装所有依赖（NATS Server、Python依赖）
#   init          - 初始化服务（创建虚拟环境、初始化JetStream流）
#   start         - 启动 NATS Server
#   stop          - 停止 NATS Server
#   restart       - 重启 NATS Server
#   status        - 检查服务状态
#   health        - 健康检查
#   logs          - 查看日志
#   clean         - 清理临时文件和锁文件
################################################################################

set -euo pipefail

# ============================================================================
# 全局变量
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$MODULE_ROOT/../.." && pwd)"

# 模块配置
MODULE_NAME="message-broker"
NATS_VERSION="2.10.7"
NATS_PORT=4222
NATS_MONITOR_PORT=8222
NATS_STORE_DIR="${NATS_STORE_DIR:-/tmp/nats-jetstream}"
NATS_CONFIG="$MODULE_ROOT/config/unified_message_broker.yaml"
JETSTREAM_INIT_CONFIG="$PROJECT_ROOT/scripts/js_init_market_data.yaml"

# 日志和PID
LOG_DIR="$MODULE_ROOT/logs"
LOG_FILE="$LOG_DIR/nats-server.log"
PID_FILE="$LOG_DIR/nats-server.pid"

# 虚拟环境
VENV_DIR="$MODULE_ROOT/venv"

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

log_info() {
    echo -e "${GREEN}[✓]${NC} $@"
}

log_warn() {
    echo -e "${YELLOW}[⚠]${NC} $@"
}

log_error() {
    echo -e "${RED}[✗]${NC} $@"
}

log_step() {
    echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  $@${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

# ============================================================================
# 环境检测
# ============================================================================

detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if [ -f /etc/os-release ]; then
            . /etc/os-release
            OS=$ID
            OS_VERSION=$VERSION_ID
        else
            log_error "无法检测 Linux 发行版"
            exit 1
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
        OS_VERSION=$(sw_vers -productVersion)
    else
        log_error "不支持的操作系统: $OSTYPE"
        exit 1
    fi
}

# ============================================================================
# 依赖安装
# ============================================================================

install_deps() {
    log_step "安装 Message Broker 依赖"

    detect_os
    log_info "检测到操作系统: $OS $OS_VERSION"

    # 安装 NATS Server
    install_nats_server

    # 创建虚拟环境
    create_venv

    # 安装 Python 依赖
    install_python_deps

    log_info "依赖安装完成"
}

install_nats_server() {
    log_info "安装 NATS Server v${NATS_VERSION}..."

    if command -v nats-server &> /dev/null; then
        local installed_version=$(nats-server --version | grep -oP 'v\K[0-9.]+' || echo "unknown")
        if [[ "$installed_version" == "$NATS_VERSION" ]]; then
            log_info "NATS Server v${NATS_VERSION} 已安装"
            return 0
        else
            log_warn "已安装 NATS Server v${installed_version}，将升级到 v${NATS_VERSION}"
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
        log_info "NATS Server 安装成功"
    else
        log_error "NATS Server 安装失败"
        exit 1
    fi
}

create_venv() {
    log_info "创建 Python 虚拟环境..."

    if [ ! -d "$VENV_DIR" ]; then
        python3 -m venv "$VENV_DIR"
        log_info "虚拟环境创建成功: $VENV_DIR"
    else
        log_info "虚拟环境已存在: $VENV_DIR"
    fi
}

install_python_deps() {
    log_info "安装 Python 依赖..."

    source "$VENV_DIR/bin/activate"

    pip install --upgrade pip -q
    pip install -q nats-py PyYAML

    log_info "Python 依赖安装完成"
}

# ============================================================================
# 初始化
# ============================================================================

init_service() {
    log_step "初始化 Message Broker 服务"

    # 创建必要的目录
    mkdir -p "$LOG_DIR"
    mkdir -p "$NATS_STORE_DIR"

    log_info "目录创建完成"

    # 启动 NATS Server（如果未运行）
    if ! is_running; then
        start_service
    fi

    # 初始化 JetStream 流
    init_jetstream

    log_info "Message Broker 初始化完成"
}

init_jetstream() {
    log_info "初始化 NATS JetStream 流..."

    source "$VENV_DIR/bin/activate"

    if [ -f "$MODULE_ROOT/init_jetstream.py" ]; then
        python "$MODULE_ROOT/init_jetstream.py" --config "$JETSTREAM_INIT_CONFIG"
        log_info "JetStream 流初始化完成"
    else
        log_error "找不到 JetStream 初始化脚本"
        exit 1
    fi
}

# ============================================================================
# 服务管理
# ============================================================================

start_service() {
    log_step "启动 NATS Server"

    if is_running; then
        log_warn "NATS Server 已在运行 (PID: $(get_pid))"
        return 0
    fi

    # 创建数据目录
    mkdir -p "$NATS_STORE_DIR"
    mkdir -p "$LOG_DIR"

    # 启动 NATS Server
    nohup nats-server \
        -js \
        -m $NATS_MONITOR_PORT \
        -p $NATS_PORT \
        --store_dir "$NATS_STORE_DIR" \
        > "$LOG_FILE" 2>&1 &

    local pid=$!
    echo $pid > "$PID_FILE"

    # 等待启动
    sleep 3

    # 验证启动
    if is_running && check_health_internal; then
        log_info "NATS Server 启动成功 (PID: $pid)"
        log_info "客户端端口: $NATS_PORT"
        log_info "监控端口: $NATS_MONITOR_PORT"
    else
        log_error "NATS Server 启动失败"
        exit 1
    fi
}

stop_service() {
    log_step "停止 NATS Server"

    if ! is_running; then
        log_warn "NATS Server 未运行"
        return 0
    fi

    local pid=$(get_pid)

    # 尝试优雅停止
    kill $pid 2>/dev/null || true

    # 等待进程结束
    local count=0
    while kill -0 $pid 2>/dev/null && [ $count -lt 10 ]; do
        sleep 1
        count=$((count + 1))
    done

    # 如果还在运行，强制停止
    if kill -0 $pid 2>/dev/null; then
        log_warn "优雅停止失败，强制停止..."
        kill -9 $pid 2>/dev/null || true
    fi

    rm -f "$PID_FILE"
    log_info "NATS Server 已停止"
}

restart_service() {
    log_step "重启 NATS Server"
    stop_service
    sleep 2
    start_service
}




# ============================================================================
# 状态检查
# ============================================================================

is_running() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if kill -0 $pid 2>/dev/null; then
            return 0
        fi
    fi

    # 检查进程名
    if pgrep -x "nats-server" > /dev/null; then
        return 0
    fi

    return 1
}

get_pid() {
    if [ -f "$PID_FILE" ]; then
        cat "$PID_FILE"
    else
        pgrep -x "nats-server" || echo ""
    fi
}

check_status() {
    log_step "检查 NATS Server 状态"

    if is_running; then
        local pid=$(get_pid)
        log_info "NATS Server: 运行中 (PID: $pid)"

        # 检查端口
        if ss -ltn | grep -q ":$NATS_PORT "; then
            log_info "客户端端口: $NATS_PORT 正在监听"
        else
            log_warn "客户端端口: $NATS_PORT 未监听"
        fi

        if ss -ltn | grep -q ":$NATS_MONITOR_PORT "; then
            log_info "监控端口: $NATS_MONITOR_PORT 正在监听"
        else
            log_warn "监控端口: $NATS_MONITOR_PORT 未监听"
        fi
    else
        log_warn "NATS Server: 未运行"
    fi
}

check_health_internal() {
    if curl -s "http://localhost:$NATS_MONITOR_PORT/healthz" | grep -q "ok"; then
        return 0
    else
        return 1
    fi
}

check_health() {
    log_step "NATS Server 健康检查"

    if ! is_running; then
        log_error "NATS Server 未运行"
        return 1
    fi

    # HTTP 健康检查
    if check_health_internal; then
        log_info "健康状态: healthy"
    else
        log_error "健康状态: unhealthy"
        return 1
    fi

    # 检查 JetStream
    local js_info=$(curl -s "http://localhost:$NATS_MONITOR_PORT/jsz" 2>/dev/null)
    if [ -n "$js_info" ]; then
        local stream_count=$(echo "$js_info" | grep -o '"streams":[0-9]*' | grep -o '[0-9]*' || echo "0")
        local consumer_count=$(echo "$js_info" | grep -o '"consumers":[0-9]*' | grep -o '[0-9]*' || echo "0")
        local message_count=$(echo "$js_info" | grep -o '"messages":[0-9]*' | grep -o '[0-9]*' || echo "0")

        log_info "JetStream: 正常"
        log_info "  - 流数量: $stream_count"
        log_info "  - 消费者数量: $consumer_count"
        log_info "  - 消息数量: $message_count"
    else
        log_warn "JetStream: 无法获取信息"
    fi

    log_info "健康检查通过"
}

# ============================================================================
# 日志管理
# ============================================================================

show_logs() {
    log_step "查看 NATS Server 日志"

    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        log_warn "日志文件不存在: $LOG_FILE"
    fi
}

# ============================================================================
# 清理
# ============================================================================

clean_service() {
    log_step "清理 Message Broker 临时文件"

    # 停止服务
    if is_running; then
        log_warn "服务正在运行，将先停止服务"
        stop_service
    fi

    # 清理 PID 文件
    if [ -f "$PID_FILE" ]; then
        rm -f "$PID_FILE"
        log_info "已删除 PID 文件"
    fi

    # 清理日志文件
    if [ -f "$LOG_FILE" ]; then
        > "$LOG_FILE"
        log_info "已清空日志文件"
    fi

    # 清理 JetStream 数据（可选）
    read -p "是否清理 JetStream 数据？这将删除所有消息 (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$NATS_STORE_DIR"
        log_info "已删除 JetStream 数据目录"
    fi

    log_info "清理完成"
}

# ============================================================================
# 主函数
# ============================================================================

show_help() {
    cat << EOF
${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}
${CYAN}  MarketPrism Message Broker 管理脚本${NC}
${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}

${GREEN}用法:${NC}
  $0 [命令]

${GREEN}命令:${NC}
  install-deps  安装所有依赖（NATS Server、Python依赖）
  init          初始化服务（创建虚拟环境、初始化JetStream流）
  start         启动 NATS Server
  stop          停止 NATS Server
  restart       重启 NATS Server
  status        检查服务状态
  health        健康检查
  logs          查看日志
  clean         清理临时文件和锁文件
  help          显示此帮助信息

${GREEN}示例:${NC}
  # 首次部署
  $0 install-deps && $0 init && $0 start

  # 日常运维
  $0 status
  $0 health
  $0 restart

EOF
}

main() {
    case "${1:-help}" in
        install-deps)
            install_deps
            ;;
        init)
            init_service
            ;;
        start)
            start_service
            ;;
        stop)
            stop_service
            ;;
        restart)
            restart_service
            ;;
        status)
            check_status
            ;;
        health)
            check_health
            ;;
        logs)
            show_logs
            ;;
        clean)
            clean_service
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "未知命令: $1"
            show_help
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"
