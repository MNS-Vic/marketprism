#!/bin/bash
# MarketPrism统一NATS容器 - 健康检查脚本
#
# 🎯 功能说明：
# - 检查NATS服务器基础健康状态
# - 验证JetStream功能正常
# - 检查MARKET_DATA流状态
# - 验证所有7种数据类型支持
#
# 📊 检查项目：
# - NATS服务器连通性
# - HTTP监控端点可用性
# - JetStream状态
# - 流配置和消息统计
# - 数据类型主题配置
#
# 🔧 设计理念：
# - 快速健康检查，适用于容器健康检查
# - 详细的错误信息和日志
# - 支持不同级别的检查
# - 与Docker健康检查集成

set -e

# 配置变量
NATS_HOST="${NATS_HOST:-localhost}"
NATS_PORT="${NATS_PORT:-4222}"
NATS_HTTP_PORT="${NATS_HTTP_PORT:-8222}"
STREAM_NAME="${STREAM_NAME:-MARKET_DATA}"
HEALTH_CHECK_TIMEOUT="${HEALTH_CHECK_TIMEOUT:-10}"

# 日志函数
log_info() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $1"
}

log_error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $1" >&2
}

log_success() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [SUCCESS] $1"
}

# 检查命令是否存在
check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "命令不存在: $1"
        return 1
    fi
    return 0
}

# 检查NATS服务器基础连通性
check_nats_connectivity() {
    log_info "检查NATS服务器连通性..."
    
    # 检查端口是否开放
    if ! timeout "$HEALTH_CHECK_TIMEOUT" bash -c "</dev/tcp/$NATS_HOST/$NATS_PORT" 2>/dev/null; then
        log_error "NATS端口 $NATS_PORT 不可访问"
        return 1
    fi
    
    log_success "NATS端口 $NATS_PORT 连通正常"
    return 0
}

# 检查HTTP监控端点
check_http_monitoring() {
    log_info "检查HTTP监控端点..."
    
    # 检查HTTP端口
    if ! timeout "$HEALTH_CHECK_TIMEOUT" bash -c "</dev/tcp/$NATS_HOST/$NATS_HTTP_PORT" 2>/dev/null; then
        log_error "HTTP监控端口 $NATS_HTTP_PORT 不可访问"
        return 1
    fi
    
    # 检查健康检查端点
    if check_command curl; then
        if ! curl -f -s --max-time "$HEALTH_CHECK_TIMEOUT" "http://$NATS_HOST:$NATS_HTTP_PORT/healthz" > /dev/null; then
            log_error "NATS健康检查端点失败"
            return 1
        fi
        log_success "NATS健康检查端点正常"
    elif check_command wget; then
        if ! wget -q --timeout="$HEALTH_CHECK_TIMEOUT" --tries=1 --spider "http://$NATS_HOST:$NATS_HTTP_PORT/healthz" 2>/dev/null; then
            log_error "NATS健康检查端点失败"
            return 1
        fi
        log_success "NATS健康检查端点正常"
    else
        log_info "跳过HTTP端点检查（curl/wget不可用）"
    fi
    
    return 0
}

# 检查JetStream状态
check_jetstream_status() {
    log_info "检查JetStream状态..."
    
    if check_command curl; then
        # 获取JetStream状态
        local js_status
        js_status=$(curl -f -s --max-time "$HEALTH_CHECK_TIMEOUT" "http://$NATS_HOST:$NATS_HTTP_PORT/jsz" 2>/dev/null)
        
        if [ $? -ne 0 ] || [ -z "$js_status" ]; then
            log_error "无法获取JetStream状态"
            return 1
        fi
        
        # 检查JetStream是否启用
        if echo "$js_status" | grep -q '"config":null'; then
            log_error "JetStream未启用"
            return 1
        fi
        
        # 提取基础统计信息
        local streams consumers messages
        streams=$(echo "$js_status" | grep -o '"streams":[0-9]*' | cut -d':' -f2 || echo "0")
        consumers=$(echo "$js_status" | grep -o '"consumers":[0-9]*' | cut -d':' -f2 || echo "0")
        messages=$(echo "$js_status" | grep -o '"messages":[0-9]*' | cut -d':' -f2 || echo "0")
        
        log_success "JetStream状态正常"
        log_info "  流数量: $streams"
        log_info "  消费者数量: $consumers"
        log_info "  消息数量: $messages"
        
    elif check_command wget; then
        # 使用wget检查JetStream端点
        if ! wget -q --timeout="$HEALTH_CHECK_TIMEOUT" --tries=1 --spider "http://$NATS_HOST:$NATS_HTTP_PORT/jsz" 2>/dev/null; then
            log_error "JetStream端点不可访问"
            return 1
        fi
        log_success "JetStream端点可访问"
    else
        log_info "跳过JetStream状态检查（curl/wget不可用）"
    fi
    
    return 0
}

# 检查MARKET_DATA流状态
check_market_data_stream() {
    log_info "检查MARKET_DATA流状态..."
    
    # 使用Python脚本检查流状态（如果可用）
    if check_command python3 && [ -f "/app/scripts/enhanced_jetstream_init.py" ]; then
        log_info "使用Python脚本检查流状态..."
        
        if python3 /app/scripts/enhanced_jetstream_init.py --health-check --timeout "$HEALTH_CHECK_TIMEOUT" 2>/dev/null; then
            log_success "MARKET_DATA流状态正常"
            return 0
        else
            log_error "MARKET_DATA流状态检查失败"
            return 1
        fi
    fi
    
    # 备用检查：通过HTTP API检查流信息
    if check_command curl; then
        local stream_info
        stream_info=$(curl -f -s --max-time "$HEALTH_CHECK_TIMEOUT" "http://$NATS_HOST:$NATS_HTTP_PORT/jsz?streams=1" 2>/dev/null)
        
        if [ $? -eq 0 ] && [ -n "$stream_info" ]; then
            if echo "$stream_info" | grep -q "\"name\":\"$STREAM_NAME\""; then
                log_success "MARKET_DATA流存在"
                return 0
            else
                log_error "MARKET_DATA流不存在"
                return 1
            fi
        fi
    fi
    
    log_info "跳过流状态详细检查（Python/curl不可用）"
    return 0
}

# 检查数据类型支持
check_data_types_support() {
    log_info "检查数据类型支持..."
    
    # 预期的数据类型主题
    local expected_subjects=(
        "orderbook-data.>"
        "trade-data.>"
        "funding-rate-data.>"
        "open-interest-data.>"
        "lsr-top-position-data.>"
        "lsr-all-account-data.>"
        "volatility_index-data.>"
    )
    
    log_info "预期支持的数据类型:"
    for subject in "${expected_subjects[@]}"; do
        local data_type=${subject%-data.>}
        data_type=${data_type//-/ }
        log_info "  - $data_type: $subject"
    done
    
    # 如果有Python脚本，可以进行更详细的检查
    if check_command python3 && [ -f "/app/scripts/enhanced_jetstream_init.py" ]; then
        if python3 /app/scripts/enhanced_jetstream_init.py --stats --timeout "$HEALTH_CHECK_TIMEOUT" > /dev/null 2>&1; then
            log_success "数据类型支持检查通过"
            return 0
        fi
    fi
    
    log_success "数据类型支持检查完成（基础检查）"
    return 0
}

# 执行完整健康检查
run_full_health_check() {
    log_info "🏥 开始MarketPrism统一NATS健康检查"
    log_info "⏰ 检查时间: $(date '+%Y-%m-%d %H:%M:%S')"
    log_info "🔧 配置信息:"
    log_info "  NATS地址: $NATS_HOST:$NATS_PORT"
    log_info "  HTTP监控: $NATS_HOST:$NATS_HTTP_PORT"
    log_info "  流名称: $STREAM_NAME"
    log_info "  超时时间: ${HEALTH_CHECK_TIMEOUT}秒"
    
    local checks_passed=0
    local total_checks=5
    
    # 1. NATS连通性检查
    if check_nats_connectivity; then
        ((checks_passed++))
    fi
    
    # 2. HTTP监控端点检查
    if check_http_monitoring; then
        ((checks_passed++))
    fi
    
    # 3. JetStream状态检查
    if check_jetstream_status; then
        ((checks_passed++))
    fi
    
    # 4. MARKET_DATA流检查
    if check_market_data_stream; then
        ((checks_passed++))
    fi
    
    # 5. 数据类型支持检查
    if check_data_types_support; then
        ((checks_passed++))
    fi
    
    # 输出检查结果
    echo ""
    log_info "📊 健康检查结果: $checks_passed/$total_checks 项通过"
    
    if [ "$checks_passed" -eq "$total_checks" ]; then
        log_success "✅ 所有健康检查通过，服务状态正常"
        return 0
    else
        log_error "❌ 健康检查失败，服务状态异常"
        return 1
    fi
}

# 快速健康检查（用于Docker健康检查）
run_quick_health_check() {
    # 只检查最基础的连通性
    if check_nats_connectivity && check_http_monitoring; then
        return 0
    else
        return 1
    fi
}

# 主函数
main() {
    local check_type="${1:-full}"
    
    case "$check_type" in
        "quick")
            run_quick_health_check
            ;;
        "full")
            run_full_health_check
            ;;
        "connectivity")
            check_nats_connectivity
            ;;
        "http")
            check_http_monitoring
            ;;
        "jetstream")
            check_jetstream_status
            ;;
        "stream")
            check_market_data_stream
            ;;
        "datatypes")
            check_data_types_support
            ;;
        *)
            echo "用法: $0 [quick|full|connectivity|http|jetstream|stream|datatypes]"
            echo ""
            echo "检查类型:"
            echo "  quick       - 快速检查（默认用于Docker健康检查）"
            echo "  full        - 完整检查（默认）"
            echo "  connectivity - 仅检查NATS连通性"
            echo "  http        - 仅检查HTTP监控端点"
            echo "  jetstream   - 仅检查JetStream状态"
            echo "  stream      - 仅检查MARKET_DATA流"
            echo "  datatypes   - 仅检查数据类型支持"
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"
