#!/bin/bash
# MarketPrism 数据验证脚本 - 检查数据流是否正常

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

# 检查服务健康状态
check_services_health() {
    log_info "检查服务健康状态..."
    
    local all_healthy=true
    
    # NATS 健康检查
    if curl -fsS http://localhost:8222/healthz >/dev/null 2>&1; then
        log_success "NATS: 健康"
    else
        log_error "NATS: 不健康"
        all_healthy=false
    fi
    
    # ClickHouse 健康检查
    if curl -fsS http://localhost:8123/ping >/dev/null 2>&1; then
        log_success "ClickHouse: 健康"
    else
        log_error "ClickHouse: 不健康"
        all_healthy=false
    fi
    
    # 热存储服务健康检查
    if curl -fsS http://localhost:8080/health >/dev/null 2>&1; then
        log_success "热存储服务: 健康"
    else
        log_error "热存储服务: 不健康"
        all_healthy=false
    fi
    
    if [ "$all_healthy" = true ]; then
        log_success "所有服务健康"
        return 0
    else
        log_error "部分服务不健康"
        return 1
    fi
}

# 检查数据表统计
check_data_statistics() {
    local time_window="$1"
    local window_desc="$2"
    
    log_info "检查 $window_desc 数据统计..."
    
    local tables=("orderbooks" "trades" "funding_rates" "open_interests" "liquidations")
    local total_records=0
    
    echo ""
    printf "%-20s %-10s %-20s %-20s\n" "表名" "记录数" "最早时间" "最新时间"
    echo "--------------------------------------------------------------------------------"
    
    for table in "${tables[@]}"; do
        local result=$(docker exec marketprism-clickhouse-hot bash -lc "clickhouse-client --query=\"SELECT count() as count, min(timestamp) as earliest, max(timestamp) as latest FROM marketprism_hot.$table WHERE timestamp > now() - INTERVAL $time_window\"" 2>/dev/null || echo "0	NULL	NULL")
        
        local count=$(echo "$result" | cut -f1)
        local earliest=$(echo "$result" | cut -f2)
        local latest=$(echo "$result" | cut -f3)
        
        printf "%-20s %-10s %-20s %-20s\n" "$table" "$count" "$earliest" "$latest"
        
        if [ "$count" != "NULL" ] && [ "$count" -gt 0 ]; then
            total_records=$((total_records + count))
        fi
    done
    
    echo "--------------------------------------------------------------------------------"
    echo "总记录数: $total_records"
    echo ""
    
    if [ $total_records -gt 0 ]; then
        log_success "$window_desc 有数据流入 (总计 $total_records 条记录)"
        return 0
    else
        log_warning "$window_desc 无数据流入"
        return 1
    fi
}

# 检查数据延迟
check_data_latency() {
    log_info "检查数据延迟..."
    
    local tables=("orderbooks" "trades" "open_interests" "liquidations")
    
    echo ""
    printf "%-20s %-15s %-20s\n" "表名" "延迟(秒)" "最新时间戳"
    echo "--------------------------------------------------------"
    
    for table in "${tables[@]}"; do
        local result=$(docker exec marketprism-clickhouse-hot bash -lc "clickhouse-client --query=\"SELECT toInt64(now() - max(timestamp)) as lag_seconds, max(timestamp) as latest_ts FROM marketprism_hot.$table\"" 2>/dev/null || echo "NULL	NULL")
        
        local lag=$(echo "$result" | cut -f1)
        local latest=$(echo "$result" | cut -f2)
        
        if [ "$lag" != "NULL" ] && [ "$lag" -lt 300 ]; then
            printf "%-20s %-15s %-20s\n" "$table" "${lag}s ✅" "$latest"
        elif [ "$lag" != "NULL" ]; then
            printf "%-20s %-15s %-20s\n" "$table" "${lag}s ⚠️" "$latest"
        else
            printf "%-20s %-15s %-20s\n" "$table" "无数据 ❌" "NULL"
        fi
    done
    
    echo ""
}

# 检查存储服务日志
check_storage_logs() {
    log_info "检查存储服务最新日志..."
    
    echo ""
    echo "=== 最近 20 条存储服务日志 ==="
    docker compose -f services/data-storage-service/docker-compose.hot-storage.yml logs --tail=20 hot-storage-service | tail -10
    echo ""
}

# 检查数据收集器日志
check_collector_logs() {
    log_info "检查数据收集器最新日志..."
    
    echo ""
    echo "=== 最近 10 条数据收集器日志 ==="
    docker compose -f services/data-collector/docker-compose.unified.yml logs --tail=10 data-collector | tail -5
    echo ""
}

# 生成数据验证报告
generate_data_report() {
    echo ""
    echo "========================================"
    echo "         数据验证报告"
    echo "========================================"
    echo ""
    
    echo "=== 验证时间 ==="
    echo "系统时间: $(date)"
    echo "数据库时间: $(docker exec marketprism-clickhouse-hot bash -lc "clickhouse-client --query=\"SELECT now()\"" 2>/dev/null || echo "无法获取")"
    echo ""
    
    echo "=== 服务状态 ==="
    echo "• NATS: http://localhost:8222"
    echo "• ClickHouse: http://localhost:8123"
    echo "• 热存储服务: http://localhost:8080/health"
    echo ""
    
    echo "=== 数据概览 ==="
    echo "• 最近 10 分钟: $(check_data_statistics "10 MINUTE" "最近10分钟" | grep "总记录数" | cut -d: -f2 | xargs || echo "0") 条记录"
    echo "• 最近 1 小时: $(check_data_statistics "1 HOUR" "最近1小时" | grep "总记录数" | cut -d: -f2 | xargs || echo "0") 条记录"
    echo ""
    
    echo "=== 建议操作 ==="
    if check_services_health >/dev/null 2>&1; then
        echo "✅ 系统运行正常，继续监控数据流"
    else
        echo "❌ 发现问题，建议："
        echo "   1. 检查服务日志: docker compose -f services/xxx/docker-compose.yml logs"
        echo "   2. 重启服务: ./stop_marketprism.sh && ./start_marketprism.sh"
        echo "   3. 查看详细错误: ./verify_data.sh"
    fi
    echo ""
}

# 主函数
main() {
    echo "========================================"
    echo "    MarketPrism 数据验证工具 v2.0"
    echo "========================================"
    echo ""
    
    # 检查是否在正确的目录
    if [ ! -f "services/message-broker/docker-compose.nats.yml" ]; then
        log_error "请在 MarketPrism 项目根目录下运行此脚本"
        exit 1
    fi
    
    # 执行验证
    check_services_health
    echo ""
    
    check_data_statistics "10 MINUTE" "最近10分钟"
    check_data_statistics "1 HOUR" "最近1小时"
    
    check_data_latency
    
    if [ "$1" = "--verbose" ] || [ "$1" = "-v" ]; then
        check_storage_logs
        check_collector_logs
    fi
    
    generate_data_report
    
    log_success "数据验证完成！"
}

# 执行主函数
main "$@"
