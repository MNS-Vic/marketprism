#!/bin/bash

################################################################################
# MarketPrism 增强初始化脚本
# 
# 基于端到端验证过程中发现的问题，提供完整的一键初始化功能
# 包括：依赖检查、环境准备、配置修复、服务初始化
################################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 颜色和符号
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${GREEN}✅ $1${NC}"; }
log_warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }
log_step() { echo -e "${BLUE}🔹 $1${NC}"; }
log_section() {
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# 检查系统依赖
check_system_dependencies() {
    log_section "检查系统依赖"
    
    # 检查Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 未安装"
        exit 1
    fi
    log_info "Python3: $(python3 --version)"
    
    # 检查curl
    if ! command -v curl &> /dev/null; then
        log_error "curl 未安装"
        exit 1
    fi
    log_info "curl: 已安装"
    
    # 检查Docker（可选）
    if command -v docker &> /dev/null; then
        log_info "Docker: $(docker --version)"
    else
        log_warn "Docker 未安装（可选）"
    fi
}

# 创建统一虚拟环境
create_unified_venv() {
    log_section "创建统一虚拟环境"

    local venv_path="$PROJECT_ROOT/venv-unified"

    # 先确保系统具备 venv 能力（Debian/Ubuntu 常见缺失）
    if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
        log_step "安装 python3-venv 及相关组件..."
        sudo apt-get update -y >/dev/null 2>&1 || true
        sudo apt-get install -y python3-venv python3.10-venv >/dev/null 2>&1 || true
    fi

    # 创建或修复统一虚拟环境
    if [ ! -d "$venv_path" ]; then
        log_step "创建统一虚拟环境..."
        python3 -m venv "$venv_path" || {
            log_error "虚拟环境创建失败"
            return 1
        }
    fi
    if [ ! -f "$venv_path/bin/activate" ]; then
        # 尝试修复：重新创建
        log_step "修复虚拟环境激活脚本..."
        rm -rf "$venv_path"
        python3 -m venv "$venv_path" || {
            log_error "虚拟环境创建失败"
            return 1
        }
    fi

    # 激活并安装依赖
    source "$venv_path/bin/activate"
    pip install --upgrade pip -q || true

    log_step "安装完整依赖包..."
    local all_deps=(
        # Message Broker 依赖
        "nats-py" "PyYAML" "aiohttp" "requests"
        # Data Storage 依赖
        "clickhouse-driver" "clickhouse-connect" "aiochclient"
        "structlog" "prometheus_client" "sqlparse" "python-dateutil"
        # Data Collector 依赖
        "websockets" "python-dotenv" "colorlog" "pandas" "numpy"
        "pydantic" "click" "uvloop" "orjson" "watchdog" "psutil"
        "PyJWT" "ccxt" "arrow"
        # 通用依赖
        "asyncio-mqtt" "aiodns" "certifi"
    )
    pip install -q "${all_deps[@]}" || {
        log_error "依赖安装失败"
        return 1
    }

    log_info "统一虚拟环境创建完成: $venv_path"

    # 为每个模块创建/修复符号链接（若已存在但目标错误则纠正）
    for module in "message-broker" "data-storage-service" "data-collector"; do
        local module_venv="$PROJECT_ROOT/services/$module/venv"
        if [ -L "$module_venv" ]; then
            local target=$(readlink -f "$module_venv" || echo "")
            if [ "$target" != "$venv_path" ]; then
                rm -f "$module_venv"
                ln -sf "$venv_path" "$module_venv"
                log_info "修复 $module 虚拟环境链接 -> $venv_path"
            fi
        elif [ ! -e "$module_venv" ]; then
            ln -sf "$venv_path" "$module_venv"
            log_info "创建 $module 虚拟环境链接"
        else
            # 存在非符号链接实体，保守处理：提示人工确认
            log_warn "$module 的 venv 存在非符号链接目录/文件，请确认是否需要改为链接到统一环境"
        fi
    done
}

# 检查和修复ClickHouse Schema
fix_clickhouse_schema() {
    log_section "检查和修复ClickHouse Schema"
    
    local schema_file="$PROJECT_ROOT/services/data-storage-service/config/clickhouse_schema_simple.sql"
    
    if [ ! -f "$schema_file" ]; then
        log_step "创建简化ClickHouse Schema..."
        cat > "$schema_file" << 'EOF'
-- MarketPrism 简化ClickHouse Schema
-- 修复数据类型不匹配问题

CREATE TABLE IF NOT EXISTS trades (
    id String,
    timestamp DateTime64(3, 'UTC'),
    exchange String,
    market_type String,
    symbol String,
    side String,
    price Float64,
    quantity Float64,
    trade_id String
) ENGINE = MergeTree()
ORDER BY (exchange, symbol, timestamp)
PARTITION BY toYYYYMM(timestamp);

CREATE TABLE IF NOT EXISTS orderbooks (
    timestamp DateTime64(3, 'UTC'),
    exchange String,
    market_type String,
    symbol String,
    bids Array(Tuple(Float64, Float64)),
    asks Array(Tuple(Float64, Float64))
) ENGINE = MergeTree()
ORDER BY (exchange, symbol, timestamp)
PARTITION BY toYYYYMM(timestamp);

CREATE TABLE IF NOT EXISTS funding_rates (
    timestamp DateTime64(3, 'UTC'),
    exchange String,
    market_type String,
    symbol String,
    funding_rate Float64,
    next_funding_time DateTime64(3, 'UTC')
) ENGINE = MergeTree()
ORDER BY (exchange, symbol, timestamp)
PARTITION BY toYYYYMM(timestamp);

CREATE TABLE IF NOT EXISTS open_interests (
    timestamp DateTime64(3, 'UTC'),
    exchange String,
    market_type String,
    symbol String,
    open_interest Float64
) ENGINE = MergeTree()
ORDER BY (exchange, symbol, timestamp)
PARTITION BY toYYYYMM(timestamp);

CREATE TABLE IF NOT EXISTS liquidations (
    timestamp DateTime64(3, 'UTC'),
    exchange String,
    market_type String,
    symbol String,
    side String,
    price Float64,
    quantity Float64
) ENGINE = MergeTree()
ORDER BY (exchange, symbol, timestamp)
PARTITION BY toYYYYMM(timestamp);

CREATE TABLE IF NOT EXISTS lsr_top_positions (
    timestamp DateTime64(3, 'UTC'),
    exchange String,
    market_type String,
    symbol String,
    long_ratio Float64,
    short_ratio Float64
) ENGINE = MergeTree()
ORDER BY (exchange, symbol, timestamp)
PARTITION BY toYYYYMM(timestamp);

CREATE TABLE IF NOT EXISTS lsr_all_accounts (
    timestamp DateTime64(3, 'UTC'),
    exchange String,
    market_type String,
    symbol String,
    long_ratio Float64,
    short_ratio Float64
) ENGINE = MergeTree()
ORDER BY (exchange, symbol, timestamp)
PARTITION BY toYYYYMM(timestamp);

CREATE TABLE IF NOT EXISTS volatility_indices (
    timestamp DateTime64(3, 'UTC'),
    exchange String,
    market_type String,
    symbol String,
    volatility_index Float64
) ENGINE = MergeTree()
ORDER BY (exchange, symbol, timestamp)
PARTITION BY toYYYYMM(timestamp);
EOF
        log_info "简化Schema文件创建完成"
    else
        log_info "简化Schema文件已存在"
    fi
}

# 检查端口冲突
check_port_conflicts() {
    log_section "检查端口冲突"
    
    local ports=(4222 8222 8123 8085 8086 8087 9093)
    local conflicts=()
    
    for port in "${ports[@]}"; do
        if ss -ltn | grep -q ":$port "; then
            conflicts+=("$port")
        fi
    done
    
    if [ ${#conflicts[@]} -gt 0 ]; then
        log_warn "发现端口冲突: ${conflicts[*]}"
        log_step "尝试清理冲突进程..."
        
        for port in "${conflicts[@]}"; do
            local pid=$(ss -ltnp | grep ":$port " | grep -o 'pid=[0-9]*' | cut -d= -f2 | head -1)
            if [ -n "$pid" ]; then
                log_info "终止占用端口 $port 的进程 (PID: $pid)"
                kill "$pid" 2>/dev/null || true
                sleep 1
            fi
        done
    else
        log_info "所有端口空闲"
    fi
}

# 预检查配置文件
precheck_configs() {
    log_section "预检查配置文件"
    
    local configs=(
        "$PROJECT_ROOT/services/message-broker/config/unified_message_broker.yaml"
        "$PROJECT_ROOT/services/data-storage-service/config/hot_storage_config.yaml"
        "$PROJECT_ROOT/services/data-collector/config/collector/unified_data_collection.yaml"
    )
    
    for config in "${configs[@]}"; do
        if [ -f "$config" ]; then
            log_info "配置文件存在: $(basename "$config")"
        else
            log_warn "配置文件缺失: $config"
        fi
    done
}

# 🔧 新增：自动问题检测和修复
auto_detect_and_fix_issues() {
    log_section "自动问题检测和修复"

    # 检查ClickHouse状态
    check_clickhouse_status

    # 检查虚拟环境
    check_virtual_environments

    # 检查配置文件完整性
    check_configuration_integrity

    log_info "自动问题检测和修复完成"
}

# 🔧 新增：检查ClickHouse状态
check_clickhouse_status() {
    log_info "检查ClickHouse状态..."

    if ! command -v clickhouse-client &> /dev/null; then
        log_warn "ClickHouse客户端未安装"
        return 0  # 在init阶段不强制安装
    fi

    # 检查ClickHouse服务状态
    if ! pgrep -f "clickhouse-server" > /dev/null; then
        log_info "ClickHouse服务未运行，尝试启动..."
        sudo clickhouse start 2>/dev/null || true
        sleep 3
    fi

    # 验证连接
    if clickhouse-client --query "SELECT 1" >/dev/null 2>&1; then
        log_info "ClickHouse状态正常"
    else
        log_warn "ClickHouse连接失败，将在服务初始化时处理"
    fi
}

# 🔧 新增：检查虚拟环境
check_virtual_environments() {
    log_info "检查虚拟环境..."

    local services=("data-collector" "data-storage-service" "message-broker")

    for service in "${services[@]}"; do
        local venv_path="$PROJECT_ROOT/services/$service/venv"
        if [ ! -d "$venv_path" ]; then
            log_warn "服务 $service 的虚拟环境不存在，将在初始化时创建"
        else
            log_info "服务 $service 的虚拟环境存在"
        fi
    done
}

# 🔧 新增：检查配置文件完整性
check_configuration_integrity() {
    log_info "检查配置文件完整性..."

    # 检查关键配置文件
    local config_files=(
        "services/data-storage-service/config/tiered_storage_config.yaml"
        "services/data-collector/config/collector_config.yaml"
    )

    for config_file in "${config_files[@]}"; do
        local full_path="$PROJECT_ROOT/$config_file"
        if [ ! -f "$full_path" ]; then
            log_warn "配置文件不存在: $config_file"
        else
            log_info "配置文件存在: $config_file"
        fi
    done
}

# 主函数
main() {
    log_section "MarketPrism 增强初始化"

    check_system_dependencies
    check_port_conflicts
    create_unified_venv
    fix_clickhouse_schema
    precheck_configs

    # 🔧 新增：自动问题检测和修复
    auto_detect_and_fix_issues

    log_section "初始化完成"
    log_info "现在可以运行以下命令启动系统："
    log_info "  ./scripts/manage_all.sh init"
    log_info "  ./scripts/manage_all.sh start"
    log_info "  ./scripts/manage_all.sh health"
}

main "$@"
