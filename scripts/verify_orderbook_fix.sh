#!/bin/bash

################################################################################
# MarketPrism Orderbook 数据修复验证脚本
# 
# 功能：验证 orderbook 数据是否正常采集和存储
################################################################################

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[✓]${NC} $@"; }
log_warn() { echo -e "${YELLOW}[⚠]${NC} $@"; }
log_error() { echo -e "${RED}[✗]${NC} $@"; }
log_step() { echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo -e "${CYAN}  $@${NC}"; echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"; }

check_nats_running() {
    log_step "检查 NATS Server 状态"
    
    if pgrep -x "nats-server" > /dev/null; then
        log_info "NATS Server: 运行中"
    else
        log_error "NATS Server: 未运行"
        log_warn "请先启动 NATS Server: cd services/message-broker && ./scripts/manage.sh start"
        return 1
    fi
    
    # 检查 JetStream
    if curl -s http://localhost:8222/jsz 2>/dev/null | grep -q "MARKET_DATA"; then
        log_info "MARKET_DATA 流: 已创建"
    else
        log_warn "MARKET_DATA 流: 未找到"
        log_warn "请初始化 JetStream: cd services/message-broker && ./scripts/manage.sh init"
        return 1
    fi
}

check_clickhouse_running() {
    log_step "检查 ClickHouse 状态"
    
    if pgrep -x "clickhouse-server" > /dev/null; then
        log_info "ClickHouse Server: 运行中"
    else
        log_error "ClickHouse Server: 未运行"
        log_warn "请先启动 ClickHouse: cd services/data-storage-service && ./scripts/manage.sh start"
        return 1
    fi
    
    # 检查 orderbooks 表
    if clickhouse-client --query "EXISTS TABLE marketprism_hot.orderbooks" 2>/dev/null | grep -q "1"; then
        log_info "orderbooks 表: 已创建"
    else
        log_error "orderbooks 表: 未创建"
        log_warn "请初始化数据库: cd services/data-storage-service && ./scripts/manage.sh init"
        return 1
    fi
}

check_storage_service_running() {
    log_step "检查存储服务状态"
    
    if pgrep -f "data-storage-service.*main.py.*hot" > /dev/null; then
        log_info "热端存储服务: 运行中"
    else
        log_error "热端存储服务: 未运行"
        log_warn "请启动存储服务: cd services/data-storage-service && ./scripts/manage.sh start"
        return 1
    fi
}

check_collector_running() {
    log_step "检查数据采集器状态"
    
    if pgrep -f "unified_collector_main.py" > /dev/null; then
        log_info "数据采集器: 运行中"
    else
        log_error "数据采集器: 未运行"
        log_warn "请启动采集器: cd services/data-collector && ./scripts/manage.sh start"
        return 1
    fi
}

check_nats_messages() {
    log_step "检查 NATS 消息流"
    
    # 检查 MARKET_DATA 流中的消息
    local stream_info=$(curl -s http://localhost:8222/jsz 2>/dev/null)
    
    if echo "$stream_info" | grep -q "MARKET_DATA"; then
        local message_count=$(echo "$stream_info" | grep -A 20 "MARKET_DATA" | grep -o '"messages":[0-9]*' | grep -o '[0-9]*' | head -1)
        
        if [ -n "$message_count" ] && [ "$message_count" -gt 0 ]; then
            log_info "MARKET_DATA 流消息数: $message_count"
        else
            log_warn "MARKET_DATA 流消息数: 0"
            log_warn "可能需要等待数据采集器发布数据"
        fi
    else
        log_error "无法获取 MARKET_DATA 流信息"
        return 1
    fi
}

check_orderbook_data() {
    log_step "检查 ClickHouse 中的 orderbook 数据"
    
    # 查询 orderbook 数据
    local count=$(clickhouse-client --query "SELECT count(*) FROM marketprism_hot.orderbooks" 2>/dev/null || echo "0")
    
    if [ "$count" -gt 0 ]; then
        log_info "orderbook 数据记录数: $count"
        
        # 显示最新的几条数据
        log_info "最新的 orderbook 数据:"
        clickhouse-client --query "
            SELECT 
                timestamp,
                exchange,
                market_type,
                symbol,
                best_bid_price,
                best_ask_price,
                bids_count,
                asks_count
            FROM marketprism_hot.orderbooks 
            ORDER BY timestamp DESC 
            LIMIT 5
            FORMAT Pretty
        " 2>/dev/null || log_warn "无法查询数据详情"
        
        # 按交易所统计
        log_info "按交易所统计:"
        clickhouse-client --query "
            SELECT 
                exchange,
                count(*) as count,
                max(timestamp) as latest_time
            FROM marketprism_hot.orderbooks 
            GROUP BY exchange
            FORMAT Pretty
        " 2>/dev/null || log_warn "无法查询统计信息"
        
    else
        log_warn "orderbook 数据记录数: 0"
        log_warn "可能原因："
        log_warn "  1. 数据采集器刚启动，还未采集到数据"
        log_warn "  2. 存储服务未正确订阅 orderbook 数据"
        log_warn "  3. 网络问题导致无法连接交易所"
        return 1
    fi
}

check_storage_logs() {
    log_step "检查存储服务日志"
    
    local log_file="$PROJECT_ROOT/services/data-storage-service/logs/storage-hot.log"
    
    if [ -f "$log_file" ]; then
        # 检查是否有 orderbook 相关的日志
        local orderbook_logs=$(grep -i "orderbook" "$log_file" | tail -10)
        
        if [ -n "$orderbook_logs" ]; then
            log_info "最近的 orderbook 日志:"
            echo "$orderbook_logs"
        else
            log_warn "日志中未找到 orderbook 相关信息"
        fi
        
        # 检查错误
        local error_count=$(grep -c "ERROR" "$log_file" 2>/dev/null || echo "0")
        if [ "$error_count" -gt 0 ]; then
            log_warn "发现 $error_count 个错误，最近的错误:"
            grep "ERROR" "$log_file" | tail -5
        fi
    else
        log_warn "日志文件不存在: $log_file"
    fi
}

show_summary() {
    log_step "验证总结"
    
    local all_ok=true
    
    # 检查各项状态
    if ! check_nats_running; then all_ok=false; fi
    if ! check_clickhouse_running; then all_ok=false; fi
    if ! check_storage_service_running; then all_ok=false; fi
    if ! check_collector_running; then all_ok=false; fi
    
    # 等待一段时间让数据流动
    log_info "等待 30 秒让数据流动..."
    sleep 30
    
    check_nats_messages
    
    if check_orderbook_data; then
        log_info ""
        log_info "✅ Orderbook 数据修复验证通过！"
        log_info ""
        log_info "数据正在正常采集和存储。"
    else
        all_ok=false
        log_error ""
        log_error "❌ Orderbook 数据验证失败"
        log_error ""
        log_error "请检查："
        log_error "  1. 所有服务是否正常运行"
        log_error "  2. 日志中是否有错误信息"
        log_error "  3. 网络连接是否正常"
    fi
    
    check_storage_logs
    
    if $all_ok; then
        return 0
    else
        return 1
    fi
}

main() {
    log_step "MarketPrism Orderbook 数据修复验证"
    
    cd "$PROJECT_ROOT"
    
    show_summary
}

main "$@"

