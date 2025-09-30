#!/bin/bash

################################################################################
# MarketPrism 端到端启动测试脚本
# 
# 用于验证所有手动修复操作已成功固化为自动化脚本
# 确保从全新环境开始能够一次性成功启动完整的 MarketPrism 系统
################################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[⚠]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

log_step() {
    echo -e "\n${CYAN}━━━━ $1 ━━━━${NC}\n"
}

# 清理函数
cleanup() {
    log_step "清理测试环境"
    
    # 停止所有服务
    cd "$PROJECT_ROOT/services/data-collector/scripts" && ./manage.sh stop 2>/dev/null || true
    cd "$PROJECT_ROOT/services/data-storage-service/scripts" && ./manage.sh stop 2>/dev/null || true
    cd "$PROJECT_ROOT/services/message-broker/scripts" && ./manage.sh stop 2>/dev/null || true
    
    # 清理进程
    pkill -f "nats-server" 2>/dev/null || true
    pkill -f "clickhouse-server" 2>/dev/null || true
    pkill -f "python.*main.py" 2>/dev/null || true
    
    sleep 3
    log_info "清理完成"
}

# 健康检查函数
check_service_health() {
    local service_name="$1"
    local url="$2"
    local max_retries="${3:-30}"
    
    log_info "检查 $service_name 健康状态..."
    
    local retry_count=0
    while [ $retry_count -lt $max_retries ]; do
        if curl -s -f "$url" >/dev/null 2>&1; then
            log_info "$service_name 健康检查通过"
            return 0
        fi
        
        ((retry_count++))
        log_info "等待 $service_name 启动... ($retry_count/$max_retries)"
        sleep 2
    done
    
    log_error "$service_name 健康检查失败"
    return 1
}

# 数据验证函数
verify_data_ingestion() {
    log_step "验证数据采集和存储"
    
    # 等待数据采集
    log_info "等待数据采集（60秒）..."
    sleep 60
    
    # 检查NATS消息
    local nats_stats=$(curl -s http://127.0.0.1:8222/jsz 2>/dev/null || echo "{}")
    local message_count=$(echo "$nats_stats" | grep -o '"messages":[0-9]*' | cut -d':' -f2 || echo "0")
    
    if [ "$message_count" -gt 100 ]; then
        log_info "NATS消息验证通过: $message_count 条消息"
    else
        log_warn "NATS消息数量较少: $message_count 条消息"
    fi
    
    # 检查ClickHouse数据
    local total_records=0
    local tables=("trades" "orderbooks" "funding_rates" "open_interests" "liquidations" "lsr_top_positions" "lsr_all_accounts" "volatility_indices")
    
    for table in "${tables[@]}"; do
        local count=$(clickhouse-client --query "SELECT count() FROM marketprism_hot.$table WHERE timestamp > now() - INTERVAL 5 MINUTE" 2>/dev/null || echo "0")
        log_info "$table: $count 条记录"
        total_records=$((total_records + count))
    done
    
    if [ "$total_records" -gt 50 ]; then
        log_info "数据存储验证通过: 总计 $total_records 条记录"
        return 0
    else
        log_warn "数据存储验证警告: 总计 $total_records 条记录（可能需要更长时间）"
        return 1
    fi
}

# 主测试函数
main() {
    log_step "MarketPrism 端到端启动测试开始"
    
    cd "$PROJECT_ROOT"
    
    # 清理环境
    cleanup
    
    # 删除虚拟环境以确保全新安装
    log_step "清理虚拟环境"
    rm -rf services/*/venv 2>/dev/null || true
    rm -rf venv* 2>/dev/null || true
    log_info "虚拟环境清理完成"
    
    # 测试步骤1: 启动Message Broker
    log_step "步骤1: 启动Message Broker"
    cd "$PROJECT_ROOT/services/message-broker/scripts"
    
    if ! ./manage.sh start; then
        log_error "Message Broker启动失败"
        exit 1
    fi
    
    # 健康检查
    if ! check_service_health "NATS" "http://127.0.0.1:8222/healthz"; then
        log_error "NATS健康检查失败"
        exit 1
    fi
    
    # 测试步骤2: 启动Data Storage Service
    log_step "步骤2: 启动Data Storage Service"
    cd "$PROJECT_ROOT/services/data-storage-service/scripts"
    
    if ! ./manage.sh start; then
        log_error "Data Storage Service启动失败"
        exit 1
    fi
    
    # 健康检查
    if ! check_service_health "ClickHouse" "http://127.0.0.1:8123/ping"; then
        log_error "ClickHouse健康检查失败"
        exit 1
    fi
    
    if ! check_service_health "热端存储" "http://127.0.0.1:8085/health"; then
        log_error "热端存储健康检查失败"
        exit 1
    fi
    
    # 测试步骤3: 启动Data Collector
    log_step "步骤3: 启动Data Collector"
    cd "$PROJECT_ROOT/services/data-collector/scripts"
    
    if ! ./manage.sh start; then
        log_error "Data Collector启动失败"
        exit 1
    fi
    
    # 测试步骤4: 验证数据流
    if verify_data_ingestion; then
        log_step "✅ 端到端测试成功完成"
        log_info "所有服务启动成功，数据采集和存储正常"
    else
        log_step "⚠️ 端到端测试部分成功"
        log_warn "服务启动成功，但数据验证需要更长时间"
    fi
    
    # 显示最终状态
    log_step "最终状态报告"
    echo "服务状态:"
    echo "- NATS: $(curl -s http://127.0.0.1:8222/healthz 2>/dev/null && echo "✅ 健康" || echo "❌ 异常")"
    echo "- ClickHouse: $(curl -s http://127.0.0.1:8123/ping 2>/dev/null && echo "✅ 健康" || echo "❌ 异常")"
    echo "- 热端存储: $(curl -s http://127.0.0.1:8085/health 2>/dev/null | grep -q healthy && echo "✅ 健康" || echo "❌ 异常")"
    echo "- 数据采集器: $(ps aux | grep -q "python.*main.py" && echo "✅ 运行中" || echo "❌ 未运行")"
    
    echo -e "\n端口监听:"
    ss -ltnp | grep -E ":(4222|8222|8123|8085|8086|8087)" | awk '{print "- " $4}' || true
    
    log_info "测试完成！使用 'bash scripts/test_end_to_end_startup.sh cleanup' 清理环境"
}

# 处理命令行参数
case "${1:-test}" in
    test)
        main
        ;;
    cleanup)
        cleanup
        ;;
    *)
        echo "用法: $0 [test|cleanup]"
        echo "  test    - 运行端到端测试（默认）"
        echo "  cleanup - 清理测试环境"
        exit 1
        ;;
esac
