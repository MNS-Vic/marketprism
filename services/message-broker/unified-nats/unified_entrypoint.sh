#!/bin/bash
# MarketPrism统一NATS容器 - 统一启动脚本
#
# 🎯 功能说明：
# 这是MarketPrism统一NATS容器的唯一入口脚本，负责完整的启动流程：
# - 统一管理NATS服务器和JetStream的启动
# - 支持环境变量驱动的配置管理
# - 自动初始化所有8种数据类型的流（包括liquidation强平数据）
# - 提供健康监控和优雅停止
# - 确保与Data Collector的完全兼容性
#
# 🔧 设计理念：
# - 简化Message Broker功能到单一容器，降低部署复杂度
# - 保持与Data Collector的完全兼容性，无需修改客户端代码
# - 提供详细的启动日志和错误处理，便于问题排查
# - 支持容器化部署的最佳实践，适配不同环境
#
# 📋 启动流程：
# 1. 环境验证 - 检查必需的命令和环境变量
# 2. 目录创建 - 创建数据存储和日志目录
# 3. 配置生成 - 根据环境变量生成NATS配置文件
# 4. NATS启动 - 启动NATS服务器并等待就绪
# 5. JetStream初始化 - 创建MARKET_DATA流和所有数据类型主题
# 6. 健康监控 - 启动后台健康检查进程
# 7. 信号处理 - 监听停止信号，执行优雅停止
#
# 🚀 使用方法：
# 1. 配置环境变量（通过.env文件或Docker环境变量）
# 2. 运行容器：docker-compose -f docker-compose.unified.yml up -d
# 3. 验证启动：docker logs marketprism-nats-unified
# 4. 连接测试：curl http://localhost:8222/healthz
#
# 🔍 故障排查：
# - 查看启动日志：docker logs marketprism-nats-unified
# - 检查健康状态：docker exec -it marketprism-nats-unified /app/scripts/health_check.sh full
# - 验证流配置：docker exec -it marketprism-nats-unified python3 /app/scripts/check_streams.py --detailed

set -e

# ==================== 配置变量 ====================
# 从环境变量获取配置，提供合理的默认值
NATS_SERVER_NAME="${NATS_SERVER_NAME:-marketprism-nats-unified}"
NATS_HOST="${NATS_HOST:-0.0.0.0}"
NATS_PORT="${NATS_PORT:-4222}"
NATS_HTTP_PORT="${NATS_HTTP_PORT:-8222}"
NATS_CLUSTER_PORT="${NATS_CLUSTER_PORT:-6222}"

JETSTREAM_ENABLED="${JETSTREAM_ENABLED:-true}"
JETSTREAM_STORE_DIR="${JETSTREAM_STORE_DIR:-/data/jetstream}"
JETSTREAM_MAX_MEMORY="${JETSTREAM_MAX_MEMORY:-1GB}"
JETSTREAM_MAX_FILE="${JETSTREAM_MAX_FILE:-10GB}"

NATS_LOG_FILE="${NATS_LOG_FILE:-/var/log/nats/nats.log}"
NATS_DEBUG="${NATS_DEBUG:-false}"
NATS_TRACE="${NATS_TRACE:-false}"

MONITORING_ENABLED="${MONITORING_ENABLED:-true}"
HEALTH_CHECK_ENABLED="${HEALTH_CHECK_ENABLED:-true}"

STREAM_NAME="${STREAM_NAME:-MARKET_DATA}"
INIT_TIMEOUT="${INIT_TIMEOUT:-60}"

# 脚本路径
SCRIPTS_DIR="/app/scripts"
CONFIG_DIR="/app/config"
NATS_CONFIG_FILE="/app/nats.conf"

# 进程ID变量
NATS_PID=""
HEALTH_MONITOR_PID=""

# ==================== 日志函数 ====================
log_info() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $1"
}

log_error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $1" >&2
}

log_success() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [SUCCESS] $1"
}

log_warn() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [WARN] $1"
}

# ==================== 工具函数 ====================
# 检查命令是否存在
check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "必需的命令不存在: $1"
        return 1
    fi
    return 0
}

# 等待端口可用
wait_for_port() {
    local host="$1"
    local port="$2"
    local timeout="$3"
    local count=0
    
    log_info "等待端口 $host:$port 可用..."
    
    while [ $count -lt "$timeout" ]; do
        if timeout 1 bash -c "</dev/tcp/$host/$port" 2>/dev/null; then
            log_success "端口 $host:$port 已可用"
            return 0
        fi
        sleep 1
        ((count++))
    done
    
    log_error "等待端口 $host:$port 超时"
    return 1
}

# 检查进程是否运行
is_process_running() {
    local pid="$1"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

# ==================== 环境验证 ====================
# 验证运行环境是否满足启动要求
# 检查项目：
# 1. 必需的命令是否存在（nats-server, python3）
# 2. 必需的Python脚本是否存在
# 3. 关键环境变量是否设置
# 4. 端口配置是否有效
validate_environment() {
    log_info "📋 验证运行环境..."

    # 检查必需的命令
    # nats-server: NATS服务器主程序
    # python3: 用于运行配置生成和JetStream初始化脚本
    local required_commands=("nats-server" "python3")
    for cmd in "${required_commands[@]}"; do
        if ! check_command "$cmd"; then
            log_error "环境验证失败：缺少命令 $cmd"
            log_error "请确保Docker镜像包含所有必需的依赖"
            return 1
        fi
    done

    # 检查Python脚本是否存在
    # 这些脚本是统一NATS容器的核心组件
    local required_scripts=(
        "$SCRIPTS_DIR/config_renderer.py"         # NATS配置文件生成器
        "$SCRIPTS_DIR/enhanced_jetstream_init.py" # JetStream流初始化器
        "$SCRIPTS_DIR/check_streams.py"           # 流状态检查工具
    )

    for script in "${required_scripts[@]}"; do
        if [ ! -f "$script" ]; then
            log_error "缺少必需的脚本: $script"
            log_error "请检查Docker镜像构建是否正确复制了所有脚本文件"
            return 1
        fi
    done

    # 验证关键环境变量
    # NATS_SERVER_NAME是NATS服务器的唯一标识
    if [ -z "$NATS_SERVER_NAME" ]; then
        log_error "NATS_SERVER_NAME 不能为空"
        log_error "请在.env文件中设置NATS_SERVER_NAME"
        return 1
    fi

    # 验证端口范围（1-65535）
    # NATS_PORT: 客户端连接端口，Data Collector将连接此端口
    if [ "$NATS_PORT" -lt 1 ] || [ "$NATS_PORT" -gt 65535 ]; then
        log_error "无效的NATS端口: $NATS_PORT"
        log_error "NATS端口必须在1-65535范围内"
        return 1
    fi

    # NATS_HTTP_PORT: HTTP监控端口，用于健康检查和监控
    if [ "$NATS_HTTP_PORT" -lt 1 ] || [ "$NATS_HTTP_PORT" -gt 65535 ]; then
        log_error "无效的HTTP端口: $NATS_HTTP_PORT"
        log_error "HTTP端口必须在1-65535范围内"
        return 1
    fi

    log_success "环境验证通过"
    log_info "  ✅ 必需命令: ${required_commands[*]}"
    log_info "  ✅ Python脚本: ${#required_scripts[@]} 个"
    log_info "  ✅ 环境变量: NATS_SERVER_NAME=$NATS_SERVER_NAME"
    log_info "  ✅ 端口配置: NATS=$NATS_PORT, HTTP=$NATS_HTTP_PORT"
    return 0
}

# ==================== 目录和权限设置 ====================
setup_directories() {
    log_info "📁 创建必要目录..."
    
    # 创建目录
    local directories=(
        "$JETSTREAM_STORE_DIR"
        "$(dirname "$NATS_LOG_FILE")"
        "$CONFIG_DIR"
        "$SCRIPTS_DIR"
    )
    
    for dir in "${directories[@]}"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            log_info "创建目录: $dir"
        fi
    done
    
    # 设置权限（如果以root运行）
    if [ "$(id -u)" -eq 0 ]; then
        # 如果存在nats用户，设置目录所有者
        if id nats &>/dev/null; then
            chown -R nats:nats "$JETSTREAM_STORE_DIR" "$(dirname "$NATS_LOG_FILE")" 2>/dev/null || true
            log_info "设置目录所有者为nats用户"
        fi
    fi
    
    log_success "目录设置完成"
    return 0
}

# ==================== 配置文件生成 ====================
# 根据环境变量生成NATS服务器配置文件
# 功能说明：
# 1. 调用config_renderer.py脚本生成标准的NATS配置文件
# 2. 配置包括：服务器基础设置、JetStream设置、监控设置、认证设置等
# 3. 所有配置都基于环境变量，支持不同环境的灵活配置
# 4. 生成的配置文件将被NATS服务器使用
generate_config() {
    log_info "🔧 生成NATS配置文件..."
    log_info "使用环境变量生成标准NATS配置文件"

    # 使用Python脚本生成配置
    # config_renderer.py会读取所有NATS_*和JETSTREAM_*环境变量
    # 并生成符合NATS服务器要求的配置文件格式
    if python3 "$SCRIPTS_DIR/config_renderer.py" --output "$NATS_CONFIG_FILE"; then
        log_success "NATS配置文件生成成功: $NATS_CONFIG_FILE"

        # 显示配置摘要，便于用户确认配置正确
        log_info "📋 配置摘要:"
        log_info "  服务器名称: $NATS_SERVER_NAME"
        log_info "  监听地址: $NATS_HOST:$NATS_PORT (客户端连接端口)"
        log_info "  HTTP监控: $NATS_HOST:$NATS_HTTP_PORT (健康检查和监控)"
        log_info "  JetStream: $([ "$JETSTREAM_ENABLED" = "true" ] && echo "✅ 启用" || echo "❌ 禁用")"

        # 如果启用了JetStream，显示存储配置
        if [ "$JETSTREAM_ENABLED" = "true" ]; then
            log_info "  📁 存储目录: $JETSTREAM_STORE_DIR"
            log_info "  💾 最大内存: $JETSTREAM_MAX_MEMORY"
            log_info "  📄 最大文件: $JETSTREAM_MAX_FILE"
            log_info "  🔄 流名称: $STREAM_NAME (将自动创建)"
        fi

        # 显示认证状态
        if [ "${NATS_AUTH_ENABLED:-false}" = "true" ]; then
            log_info "  🔐 认证: ✅ 启用"
        else
            log_info "  🔐 认证: ❌ 禁用 (开发环境)"
        fi

        return 0
    else
        log_error "NATS配置文件生成失败"
        log_error "请检查config_renderer.py脚本和环境变量配置"
        return 1
    fi
}

# ==================== NATS服务器启动 ====================
start_nats_server() {
    log_info "🎯 启动NATS服务器..."
    
    # 检查配置文件
    if [ ! -f "$NATS_CONFIG_FILE" ]; then
        log_error "NATS配置文件不存在: $NATS_CONFIG_FILE"
        return 1
    fi
    
    # 启动NATS服务器
    nats-server -c "$NATS_CONFIG_FILE" &
    NATS_PID=$!
    
    log_info "NATS服务器已启动，PID: $NATS_PID"
    
    # 等待NATS服务器启动
    if wait_for_port "localhost" "$NATS_PORT" 30; then
        log_success "NATS服务器启动成功"
        
        # 验证HTTP监控端点
        if wait_for_port "localhost" "$NATS_HTTP_PORT" 10; then
            log_success "HTTP监控端点可用"
        else
            log_warn "HTTP监控端点不可用"
        fi
        
        return 0
    else
        log_error "NATS服务器启动失败"
        return 1
    fi
}

# ==================== JetStream初始化 ====================
# 初始化JetStream流和所有数据类型主题
# 功能说明：
# 1. 检查JetStream是否启用
# 2. 等待NATS服务器完全就绪
# 3. 创建MARKET_DATA流，配置所有8种数据类型的主题
# 4. 验证流创建成功和配置正确
#
# 支持的数据类型：
# - orderbook-data.>      (订单簿数据)
# - trade-data.>          (交易数据)
# - funding-rate-data.>   (资金费率)
# - open-interest-data.>  (未平仓量)
# - lsr-top-position-data.> (LSR顶级持仓)
# - lsr-all-account-data.>  (LSR全账户)
# - volatility_index-data.> (波动率指数)
# - liquidation-data.>    (强平订单数据)
initialize_jetstream() {
    # 检查JetStream是否启用
    if [ "$JETSTREAM_ENABLED" != "true" ]; then
        log_info "JetStream未启用，跳过初始化"
        log_info "注意：没有JetStream，消息将不会持久化存储"
        return 0
    fi

    log_info "🔄 初始化JetStream和数据流..."
    log_info "将创建MARKET_DATA流，支持8种数据类型"

    # 等待NATS服务器完全就绪
    # 给NATS服务器一些时间来完全启动JetStream功能
    log_info "⏳ 等待NATS服务器完全就绪..."
    sleep 3

    # 使用Python脚本初始化JetStream
    # enhanced_jetstream_init.py会：
    # 1. 连接到NATS服务器
    # 2. 检查JetStream是否可用
    # 3. 创建MARKET_DATA流
    # 4. 配置所有8种数据类型的主题模式
    # 5. 设置流的保留策略、存储限制等
    log_info "🚀 运行JetStream初始化脚本..."
    if python3 "$SCRIPTS_DIR/enhanced_jetstream_init.py" --timeout "$INIT_TIMEOUT"; then
        log_success "✅ JetStream初始化成功"
        log_info "📊 MARKET_DATA流已创建，包含8种数据类型主题"

        # 验证流状态
        # 使用check_streams.py验证流是否正确创建和配置
        log_info "🔍 验证流状态和配置..."
        if python3 "$SCRIPTS_DIR/check_streams.py" --stream "$STREAM_NAME" --quiet; then
            log_success "✅ MARKET_DATA流状态验证通过"
            log_info "🎯 所有数据类型主题已正确配置"
        else
            log_warn "⚠️ MARKET_DATA流状态验证失败"
            log_warn "流可能已创建但配置不完整，请检查日志"
        fi

        return 0
    else
        log_error "❌ JetStream初始化失败"
        log_error "可能的原因："
        log_error "  1. NATS服务器未完全启动"
        log_error "  2. JetStream配置错误"
        log_error "  3. 存储目录权限问题"
        log_error "  4. 内存或磁盘空间不足"
        return 1
    fi
}

# ==================== 健康监控启动 ====================
start_health_monitor() {
    if [ "$HEALTH_CHECK_ENABLED" != "true" ]; then
        log_info "健康检查未启用，跳过监控"
        return 0
    fi
    
    log_info "🏥 启动健康监控..."
    
    # 创建健康监控脚本
    cat > /tmp/health_monitor.sh << 'EOF'
#!/bin/bash
HEALTH_CHECK_INTERVAL="${HEALTH_CHECK_INTERVAL:-60}"
HEALTH_SCRIPT="/app/scripts/health_check.sh"

while true; do
    if [ -f "$HEALTH_SCRIPT" ]; then
        if ! bash "$HEALTH_SCRIPT" quick > /dev/null 2>&1; then
            echo "$(date '+%Y-%m-%d %H:%M:%S') [WARN] 健康检查失败"
        fi
    fi
    sleep "$HEALTH_CHECK_INTERVAL"
done
EOF
    
    chmod +x /tmp/health_monitor.sh
    /tmp/health_monitor.sh &
    HEALTH_MONITOR_PID=$!
    
    log_success "健康监控已启动，PID: $HEALTH_MONITOR_PID"
    return 0
}

# ==================== 信号处理 ====================
cleanup() {
    log_info "🛑 收到停止信号，正在优雅停止..."
    
    # 停止健康监控
    if is_process_running "$HEALTH_MONITOR_PID"; then
        log_info "停止健康监控..."
        kill "$HEALTH_MONITOR_PID" 2>/dev/null || true
        wait "$HEALTH_MONITOR_PID" 2>/dev/null || true
    fi
    
    # 停止NATS服务器
    if is_process_running "$NATS_PID"; then
        log_info "停止NATS服务器..."
        kill -TERM "$NATS_PID" 2>/dev/null || true
        
        # 等待优雅停止
        local count=0
        while is_process_running "$NATS_PID" && [ $count -lt 10 ]; do
            sleep 1
            ((count++))
        done
        
        # 强制停止
        if is_process_running "$NATS_PID"; then
            log_warn "强制停止NATS服务器..."
            kill -KILL "$NATS_PID" 2>/dev/null || true
        fi
    fi
    
    log_success "服务已停止"
    exit 0
}

# 设置信号处理
trap cleanup SIGTERM SIGINT

# ==================== 主启动流程 ====================
# MarketPrism统一NATS容器的主启动函数
#
# 启动流程说明：
# 1. validate_environment  - 验证运行环境（命令、脚本、环境变量）
# 2. setup_directories     - 创建必要的目录（数据、日志）
# 3. generate_config       - 生成NATS配置文件
# 4. start_nats_server     - 启动NATS服务器
# 5. initialize_jetstream  - 初始化JetStream和数据流
# 6. start_health_monitor  - 启动健康监控
#
# 如果任何步骤失败，将执行cleanup并退出
# 成功启动后，容器将保持运行状态，等待客户端连接
main() {
    log_info "🚀 启动MarketPrism统一NATS服务"
    log_info "⏰ 启动时间: $(date '+%Y-%m-%d %H:%M:%S')"
    log_info "🐳 容器ID: ${HOSTNAME:-unknown}"
    log_info "📦 版本: MarketPrism统一NATS容器 v2.0.0"

    # 显示当前配置信息，便于用户确认和调试
    log_info ""
    log_info "🔧 当前配置信息:"
    log_info "  服务器名称: $NATS_SERVER_NAME"
    log_info "  监听地址: $NATS_HOST:$NATS_PORT (Data Collector连接此端口)"
    log_info "  HTTP监控: $NATS_HOST:$NATS_HTTP_PORT (健康检查和Web监控)"
    log_info "  JetStream: $([ "$JETSTREAM_ENABLED" = "true" ] && echo "✅ 启用" || echo "❌ 禁用")"
    log_info "  流名称: $STREAM_NAME (将包含所有数据类型)"
    log_info "  健康检查: $([ "$HEALTH_CHECK_ENABLED" = "true" ] && echo "✅ 启用" || echo "❌ 禁用")"
    log_info "  调试模式: $([ "$NATS_DEBUG" = "true" ] && echo "✅ 启用" || echo "❌ 禁用")"

    # 定义启动步骤序列
    # 每个步骤都是一个函数，按顺序执行
    # 如果任何步骤失败，整个启动过程将终止
    local steps=(
        "validate_environment"    # 验证环境：检查命令、脚本、环境变量
        "setup_directories"       # 目录设置：创建数据和日志目录
        "generate_config"         # 配置生成：根据环境变量生成NATS配置
        "start_nats_server"       # NATS启动：启动NATS服务器并等待就绪
        "initialize_jetstream"    # 流初始化：创建JetStream流和数据类型主题
        "start_health_monitor"    # 监控启动：启动后台健康检查进程
    )

    log_info ""
    log_info "📋 开始执行启动步骤 (共${#steps[@]}步):"

    # 逐步执行启动流程
    local step_num=1
    for step in "${steps[@]}"; do
        log_info ""
        log_info "🔄 步骤 $step_num/${#steps[@]}: $step"
        log_info "$(printf '=%.0s' {1..60})"

        if ! $step; then
            log_error "❌ 启动步骤失败: $step (步骤 $step_num/${#steps[@]})"
            log_error "启动过程终止，执行清理操作"
            cleanup
            exit 1
        fi

        log_success "✅ 步骤 $step_num/${#steps[@]} 完成: $step"
        ((step_num++))
    done

    # 显示启动完成信息
    log_info ""
    log_info "$(printf '=%.0s' {1..80})"
    log_success "🎉 MarketPrism统一NATS服务启动完成！"
    log_info "$(printf '=%.0s' {1..80})"

    # 显示服务访问信息
    log_info "📊 服务访问信息:"
    log_info "  🌐 HTTP监控界面: http://localhost:$NATS_HTTP_PORT"
    log_info "  🔌 NATS客户端连接: nats://localhost:$NATS_PORT"
    log_info "  🏥 健康检查: curl http://localhost:$NATS_HTTP_PORT/healthz"
    log_info "  📈 JetStream状态: curl http://localhost:$NATS_HTTP_PORT/jsz"

    # 显示支持的数据类型
    log_info ""
    log_info "📡 支持的数据类型 (8种):"
    log_info "  1. orderbook      - 订单簿数据 (所有交易所)"
    log_info "  2. trade          - 交易数据 (所有交易所)"
    log_info "  3. funding_rate   - 资金费率 (衍生品交易所)"
    log_info "  4. open_interest  - 未平仓量 (衍生品交易所)"
    log_info "  5. lsr_top_position - LSR顶级持仓 (衍生品交易所)"
    log_info "  6. lsr_all_account  - LSR全账户 (衍生品交易所)"
    log_info "  7. volatility_index - 波动率指数 (Deribit)"
    log_info "  8. liquidation    - 强平订单数据 (衍生品交易所)"

    # 显示JetStream流状态（如果启用）
    if [ "$JETSTREAM_ENABLED" = "true" ]; then
        log_info ""
        log_info "📋 JetStream流状态检查:"
        python3 "$SCRIPTS_DIR/check_streams.py" --stream "$STREAM_NAME" --quiet || true
    fi

    # 显示使用提示
    log_info ""
    log_info "🎯 服务已就绪，等待客户端连接..."
    log_info "💡 使用提示:"
    log_info "  - Data Collector可以连接到 nats://localhost:$NATS_PORT"
    log_info "  - 查看实时日志: docker logs -f marketprism-nats-unified"
    log_info "  - 停止服务: docker-compose -f docker-compose.unified.yml down"
    log_info ""

    # 保持容器运行，等待NATS进程
    # 当NATS进程退出时，容器也会退出
    wait "$NATS_PID"
}

# 执行主函数
main "$@"
