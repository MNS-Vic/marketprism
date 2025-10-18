#!/bin/bash

################################################################################
# MarketPrism Data Collector 管理脚本
################################################################################

set -euo pipefail
# 兜底：直接运行子 manage.sh 时也有一致的 NATS 环境
export NATS_URL="${NATS_URL:-nats://127.0.0.1:4222}"
export MARKETPRISM_NATS_URL="${MARKETPRISM_NATS_URL:-$NATS_URL}"


SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$MODULE_ROOT/../.." && pwd)"

# 配置
MODULE_NAME="data-collector"
HEALTH_CHECK_PORT=8087
METRICS_PORT=9092
COLLECTOR_CONFIG="$MODULE_ROOT/config/collector/unified_data_collection.yaml"

# 日志和PID
LOG_DIR="$MODULE_ROOT/logs"
LOG_FILE="$LOG_DIR/collector.log"
PID_FILE="$LOG_DIR/collector.pid"
VENV_DIR="$MODULE_ROOT/venv"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[✓]${NC} $@"; }
log_warn() { echo -e "${YELLOW}[⚠]${NC} $@"; }
log_error() { echo -e "${RED}[✗]${NC} $@"; }
log_step() { echo -e "\n${CYAN}━━━━ $@ ━━━━${NC}\n"; }

detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        [ -f /etc/os-release ] && . /etc/os-release && OS=$ID || OS="linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
    else
        log_error "不支持的操作系统"; exit 1
    fi
}

install_deps() {
    log_step "安装依赖"
    detect_os

    # 创建虚拟环境
    if [ ! -d "$VENV_DIR" ]; then
        log_info "创建虚拟环境..."
        python3 -m venv "$VENV_DIR"
    fi

    # 安装 Python 依赖
    log_info "安装 Python 依赖..."
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip -q

    # 🔧 完整的依赖列表，包含验证过程中发现的所有必需包
    local deps=(
        "nats-py" "websockets" "pyyaml" "python-dotenv" "colorlog"
        "pandas" "numpy" "pydantic" "prometheus-client" "click"
        "uvloop" "orjson" "watchdog" "psutil" "PyJWT" "ccxt"
        "arrow" "aiohttp" "requests" "python-dateutil" "structlog"
        "asyncio-mqtt" "aiodns" "certifi"
    )

    log_info "安装依赖包: ${deps[*]}"
    pip install -q "${deps[@]}" || {
        log_error "依赖安装失败"
        return 1
    }

    log_info "依赖安装完成"
}

init_service() {
    log_step "初始化服务"
    mkdir -p "$LOG_DIR"

    # 检查配置文件
    if [ \! -f "$COLLECTOR_CONFIG" ]; then
        log_error "配置文件不存在: $COLLECTOR_CONFIG"
        exit 1
    fi

    log_info "配置文件: $COLLECTOR_CONFIG"
    log_info "初始化完成"
}

start_service() {
    log_step "启动数据采集器"

    # 🔧 自动创建虚拟环境并安装依赖
    if [ ! -d "$VENV_DIR" ]; then
        log_info "创建虚拟环境..."
        python3 -m venv "$VENV_DIR"
        source "$VENV_DIR/bin/activate"
        pip install --upgrade pip -q

        # 安装关键依赖
        local deps=(
            "nats-py" "websockets" "pyyaml" "python-dotenv" "colorlog"
            "pandas" "numpy" "pydantic" "prometheus-client" "click"
            "uvloop" "orjson" "watchdog" "psutil" "PyJWT" "ccxt"
            "arrow" "aiohttp" "requests" "python-dateutil" "structlog"
        )
        pip install -q "${deps[@]}"
    else
        source "$VENV_DIR/bin/activate"
        # 🔧 确保关键依赖已安装（幂等性检查）
        local missing_deps=()
        local deps=("nats-py" "websockets" "pyyaml" "ccxt" "aiohttp" "structlog")
        for dep in "${deps[@]}"; do
            if ! pip show "$dep" >/dev/null 2>&1; then
                missing_deps+=("$dep")
            fi
        done

        if [ ${#missing_deps[@]} -gt 0 ]; then
            log_info "安装缺失的依赖: ${missing_deps[*]}"
            pip install -q "${missing_deps[@]}" || {
                log_error "依赖安装失败"
                return 1
            }
        fi
    fi

    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        log_warn "数据采集器已在运行 (PID: $(cat $PID_FILE))"
        return 0
    fi

    # 🔧 自动创建虚拟环境并安装依赖
    if [ ! -d "$VENV_DIR" ]; then
        log_info "创建虚拟环境..."
        python3 -m venv "$VENV_DIR"
        source "$VENV_DIR/bin/activate"
        log_info "安装 Python 依赖（这可能需要几分钟）..."
        pip install -q --upgrade pip

        # 使用与install_deps相同的依赖列表确保一致性
        local deps=(
            "nats-py" "websockets" "pyyaml" "python-dotenv" "colorlog"
            "pandas" "numpy" "pydantic" "prometheus-client" "click"
            "uvloop" "orjson" "watchdog" "psutil" "PyJWT" "ccxt"
            "arrow" "aiohttp" "requests" "python-dateutil" "structlog"
        )
        pip install -q "${deps[@]}" || {
            log_error "依赖安装失败"
            return 1
        }
        log_info "依赖安装完成"
    else
        source "$VENV_DIR/bin/activate"
        # 确保关键依赖已安装（幂等性检查）
        local missing_deps=()
        local deps=("nats-py" "websockets" "pyyaml" "python-dotenv" "colorlog" "pandas" "numpy" "pydantic" "prometheus-client" "click" "uvloop" "orjson" "watchdog" "psutil" "PyJWT" "ccxt" "arrow" "aiohttp" "requests" "python-dateutil" "structlog")
        for dep in "${deps[@]}"; do
            if ! pip show "$dep" >/dev/null 2>&1; then
                missing_deps+=("$dep")
            fi
        done

        if [ ${#missing_deps[@]} -gt 0 ]; then
            log_info "安装缺失的依赖: ${missing_deps[*]}"
            pip install -q "${missing_deps[@]}" || {
                log_error "依赖安装失败"
                return 1
            }
        fi
    fi

    # 检查配置文件
    if [ ! -f "$COLLECTOR_CONFIG" ]; then
        log_error "配置文件不存在: $COLLECTOR_CONFIG"
        exit 1
    fi

    mkdir -p "$LOG_DIR"
    cd "$MODULE_ROOT"

    # 设置环境变量
    export COLLECTOR_ENABLE_HTTP=1
    export HEALTH_CHECK_PORT=$HEALTH_CHECK_PORT
    export METRICS_PORT=$METRICS_PORT

    # 健康端点冷启动宽限期（默认120秒，可通过环境变量覆盖）
    export HEALTH_GRACE_SECONDS="${HEALTH_GRACE_SECONDS:-120}"

    # 启动采集器
    nohup python "$MODULE_ROOT/main.py" --mode launcher > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"

    # 等待健康端点就绪并返回healthy
    log_info "等待健康端点就绪..."
    SECONDS_WAITED=0
    TIMEOUT=120
    while [ $SECONDS_WAITED -lt $TIMEOUT ]; do
        if curl -sf "http://localhost:$HEALTH_CHECK_PORT/health" 2>/dev/null | grep -q '"status"\s*:\s*"healthy"'; then
            log_info "数据采集器启动成功 (PID: $(cat $PID_FILE))"
            log_info "健康检查端口: $HEALTH_CHECK_PORT"
            log_info "指标端口: $METRICS_PORT"
            break
        fi
        if [ $((SECONDS_WAITED % 5)) -eq 0 ]; then
            log_info "等待健康端点... ($SECONDS_WAITED/$TIMEOUT 秒)"
        fi
        sleep 1
        SECONDS_WAITED=$((SECONDS_WAITED+1))
    done

    if [ $SECONDS_WAITED -ge $TIMEOUT ]; then
        log_error "数据采集器健康端点未在 ${TIMEOUT}s 内就绪"
        tail -30 "$LOG_FILE" || true
        exit 1
    fi
}

stop_service() {
    log_step "停止数据采集器"

    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if kill -0 $pid 2>/dev/null; then
            log_info "停止数据采集器 (PID: $pid)..."
            kill $pid

            # 等待进程结束
            local count=0
            while kill -0 $pid 2>/dev/null && [ $count -lt 15 ]; do
                sleep 1
                count=$((count + 1))
            done

            # 强制停止
            if kill -0 $pid 2>/dev/null; then
                log_warn "优雅停止失败，强制停止..."
                kill -9 $pid 2>/dev/null || true
            fi

            rm -f "$PID_FILE"
            log_info "数据采集器已停止"
        else
            log_warn "PID 文件存在但进程未运行"
            rm -f "$PID_FILE"
        fi
    else
        # 尝试通过进程名停止
        if pgrep -f "$MODULE_ROOT/main.py" > /dev/null; then
            log_info "通过进程名停止..."
            pkill -f "$MODULE_ROOT/main.py"
            sleep 2
            log_info "数据采集器已停止"
        else
            log_warn "数据采集器未运行"
        fi
    fi
}

restart_service() {
    stop_service
    sleep 3
    start_service
}

check_status() {
    log_step "检查状态"

    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        local pid=$(cat "$PID_FILE")
        log_info "数据采集器: 运行中 (PID: $pid)"

        # 检查端口
        if ss -ltn | grep -q ":$HEALTH_CHECK_PORT "; then
            log_info "  健康检查端口 $HEALTH_CHECK_PORT: 监听中"
        else
            log_warn "  健康检查端口 $HEALTH_CHECK_PORT: 未监听"
        fi

        if ss -ltn | grep -q ":$METRICS_PORT "; then
            log_info "  指标端口 $METRICS_PORT: 监听中"
        else
            log_warn "  指标端口 $METRICS_PORT: 未监听"
        fi

        # 显示运行时间
        local start_time=$(ps -o lstart= -p $pid 2>/dev/null || echo "未知")
        log_info "  启动时间: $start_time"
    else
        log_warn "数据采集器: 未运行"
    fi
}

check_health() {
    log_step "健康检查"

    if ! [ -f "$PID_FILE" ] || ! kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        log_error "数据采集器未运行"
        return 1
    fi

    # HTTP 健康检查
    if curl -s "http://localhost:$HEALTH_CHECK_PORT/health" 2>/dev/null | grep -q "healthy"; then
        log_info "健康状态: healthy"
    else
        log_warn "健康检查端点未响应（这是正常的，某些版本可能未实现）"
    fi

    # 🔧 修复：检查日志中的真实错误（排除WARNING级别中包含[ERROR]标签的日志）
    if [ -f "$LOG_FILE" ]; then
        # 只统计真正的ERROR级别日志（行中包含" - ERROR - "）
        local error_count=$(grep -c " - ERROR - " "$LOG_FILE" 2>/dev/null || echo "0")
        # 只统计真正的WARNING级别日志（行中包含" - WARNING - "）
        local warning_count=$(grep -c " - WARNING - " "$LOG_FILE" 2>/dev/null || echo "0")

        # 🔧 新增：统计关键错误类型
        local memory_errors=$(grep " - ERROR - " "$LOG_FILE" 2>/dev/null | grep -c "内存使用达到严重阈值\|内存仍然过高" || echo "0")
        local cpu_errors=$(grep " - ERROR - " "$LOG_FILE" 2>/dev/null | grep -c "CPU使用率达到严重阈值" || echo "0")

        log_info "日志统计:"
        log_info "  真实错误数: $error_count (内存: $memory_errors, CPU: $cpu_errors)"
        log_info "  警告数: $warning_count"

        # 显示最近的数据采集信息
        if grep -q "发布成功\|Published" "$LOG_FILE" 2>/dev/null; then
            log_info "数据采集: 正常"
            local recent_data=$(grep "发布成功\|Published" "$LOG_FILE" | tail -3)
            echo "$recent_data" | while read line; do
                log_info "  $line"
            done
        fi
    fi
}

show_logs() {
    log_step "查看日志"

    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        log_warn "日志文件不存在: $LOG_FILE"
    fi
}

clean_service() {
    log_step "清理"

    # 停止服务
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        log_warn "服务正在运行，将先停止"
        stop_service
    fi

    # 清理 PID 文件
    rm -f "$PID_FILE"

    # 清理日志文件
    if [ -f "$LOG_FILE" ]; then
        > "$LOG_FILE"
        log_info "已清空日志文件"
    fi

    log_info "清理完成"
}

show_help() {
    cat << EOF
${CYAN}MarketPrism Data Collector 管理脚本${NC}

用法: $0 [命令]

命令:
  install-deps  安装依赖
  init          初始化服务
  start         启动数据采集器
  stop          停止数据采集器
  restart       重启数据采集器
  status        检查状态
  health        健康检查
  logs          查看日志
  clean         清理
  help          显示帮助

示例:
  # 首次部署
  $0 install-deps && $0 init && $0 start

  # 日常运维
  $0 status
  $0 health
  $0 restart

环境变量:
  HEALTH_CHECK_PORT     健康检查端口 (默认: 8087)
  METRICS_PORT          Prometheus指标端口 (默认: 9092)
  HEALTH_GRACE_SECONDS  健康端点冷启动宽限期 (默认: 120s；在此时间内即便综合状态未达healthy也返回200)

EOF
}

main() {
    case "${1:-help}" in
        install-deps) install_deps ;;
        init) init_service ;;
        start) start_service ;;
        stop) stop_service ;;
        restart) restart_service ;;
        status) check_status ;;
        health) check_health ;;
        logs) show_logs ;;
        clean) clean_service ;;
        help|--help|-h) show_help ;;
        *) log_error "未知命令: $1"; show_help; exit 1 ;;
    esac
}

main "$@"
