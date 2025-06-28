#!/bin/bash

# MarketPrism系统监控脚本
# 持续监控系统状态并在发现问题时自动修复

set -e

# 配置
MONITOR_INTERVAL=60  # 监控间隔（秒）
LOG_DIR="/home/ubuntu/marketprism/logs"
MONITOR_LOG="$LOG_DIR/system-monitor.log"
SCRIPT_DIR="/home/ubuntu/marketprism/scripts"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_with_timestamp() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$MONITOR_LOG"
}

log_info() {
    log_with_timestamp "[INFO] $1"
}

log_success() {
    log_with_timestamp "[SUCCESS] $1"
}

log_warning() {
    log_with_timestamp "[WARNING] $1"
}

log_error() {
    log_with_timestamp "[ERROR] $1"
}

# 检查关键服务
check_critical_services() {
    local issues=0
    
    # 检查Docker服务
    local docker_services=(
        "marketprism-api-gateway"
        "marketprism-monitoring-alerting"
        "marketprism-data-storage-hot"
        "marketprism-market-data-collector"
        "marketprism-scheduler"
        "marketprism-message-broker"
        "marketprism-prometheus"
        "marketprism-nats"
        "marketprism-redis"
    )
    
    for service in "${docker_services[@]}"; do
        local status=$(docker ps --format "{{.Names}}\t{{.Status}}" | grep "$service" | awk '{print $2}' || echo "")
        
        if [[ ! "$status" == *"Up"* ]]; then
            log_error "Docker服务 $service 未运行"
            ((issues++))
        fi
    done
    
    # 检查WebSocket服务器
    local ws_process=$(ps aux | grep "websocket-server.js" | grep -v grep || echo "")
    if [ -z "$ws_process" ]; then
        log_error "WebSocket服务器未运行"
        ((issues++))
    fi
    
    # 检查关键端口
    local critical_ports=("3000" "8089" "9090" "4222" "8123" "5432" "6379")
    
    for port in "${critical_ports[@]}"; do
        local port_status=$(netstat -tlnp | grep ":$port " || echo "")
        if [ -z "$port_status" ]; then
            log_error "关键端口 $port 未在监听"
            ((issues++))
        fi
    done
    
    return $issues
}

# 检查系统资源
check_system_resources() {
    local issues=0
    
    # 检查CPU使用率
    local cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')
    local cpu_percent=$(echo $cpu_usage | sed 's/%//')
    
    if (( $(echo "$cpu_percent > 90" | bc -l) )); then
        log_warning "CPU使用率过高: ${cpu_percent}%"
        ((issues++))
    fi
    
    # 检查内存使用率
    local memory_info=$(free | grep Mem)
    local total_mem=$(echo $memory_info | awk '{print $2}')
    local used_mem=$(echo $memory_info | awk '{print $3}')
    local memory_percent=$(echo "scale=2; $used_mem * 100 / $total_mem" | bc)
    
    if (( $(echo "$memory_percent > 90" | bc -l) )); then
        log_warning "内存使用率过高: ${memory_percent}%"
        ((issues++))
    fi
    
    # 检查磁盘使用率
    local disk_usage=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
    
    if [ "$disk_usage" -gt 90 ]; then
        log_warning "磁盘使用率过高: ${disk_usage}%"
        ((issues++))
    fi
    
    return $issues
}

# 检查网络连接
check_network_connectivity() {
    local issues=0
    
    # 检查本地服务连接
    local services=(
        "localhost:8080"
        "localhost:8082"
        "localhost:8083"
        "localhost:8084"
        "localhost:8085"
        "localhost:8086"
        "localhost:9090"
        "localhost:4222"
        "localhost:8123"
        "localhost:5432"
        "localhost:6379"
    )
    
    for service in "${services[@]}"; do
        local host=$(echo $service | cut -d: -f1)
        local port=$(echo $service | cut -d: -f2)
        
        if ! nc -z "$host" "$port" 2>/dev/null; then
            log_error "无法连接到 $service"
            ((issues++))
        fi
    done
    
    return $issues
}

# 自动修复问题
auto_fix_issues() {
    log_info "检测到问题，尝试自动修复..."
    
    # 运行自动修复脚本
    if [ -f "$SCRIPT_DIR/auto-fix-issues.sh" ]; then
        bash "$SCRIPT_DIR/auto-fix-issues.sh" >> "$MONITOR_LOG" 2>&1
        log_info "自动修复脚本执行完成"
    else
        log_error "自动修复脚本不存在: $SCRIPT_DIR/auto-fix-issues.sh"
    fi
}

# 发送告警通知
send_alert() {
    local message="$1"
    local severity="$2"
    
    # 记录告警
    log_error "ALERT [$severity]: $message"
    
    # 这里可以添加其他通知方式，如邮件、Slack等
    # 例如：
    # echo "$message" | mail -s "MarketPrism Alert [$severity]" admin@example.com
    # curl -X POST -H 'Content-type: application/json' --data '{"text":"'$message'"}' YOUR_SLACK_WEBHOOK_URL
}

# 生成监控报告
generate_monitor_report() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local report_file="$LOG_DIR/monitor-report-$(date +%Y%m%d_%H%M%S).md"
    
    cat > "$report_file" << EOF
# MarketPrism系统监控报告

**生成时间**: $timestamp  
**监控类型**: 自动化系统监控  

## 系统状态概览

### 服务状态
$(docker ps --format "table {{.Names}}\t{{.Status}}" | grep marketprism)

### 系统资源
- **CPU使用率**: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}')
- **内存使用率**: $(free | grep Mem | awk '{printf "%.1f%%", $3/$2 * 100.0}')
- **磁盘使用率**: $(df / | tail -1 | awk '{print $5}')

### 网络连接
- **WebSocket端口**: $(netstat -tlnp | grep ":8089" | wc -l) 个连接
- **数据库连接**: $(netstat -tlnp | grep -E ":(5432|8123|6379)" | wc -l) 个端口

### 最近告警
$(tail -20 "$MONITOR_LOG" | grep "ALERT" || echo "无告警")

EOF
    
    log_info "监控报告已生成: $report_file"
}

# 监控循环
monitor_loop() {
    log_info "开始系统监控循环 (间隔: ${MONITOR_INTERVAL}秒)"
    
    local consecutive_failures=0
    local max_consecutive_failures=3
    
    while true; do
        local total_issues=0
        
        # 执行各项检查
        check_critical_services || total_issues=$((total_issues + $?))
        check_system_resources || total_issues=$((total_issues + $?))
        check_network_connectivity || total_issues=$((total_issues + $?))
        
        if [ $total_issues -eq 0 ]; then
            if [ $consecutive_failures -gt 0 ]; then
                log_success "系统状态已恢复正常"
                consecutive_failures=0
            fi
        else
            ((consecutive_failures++))
            log_warning "发现 $total_issues 个问题 (连续失败: $consecutive_failures 次)"
            
            # 如果连续失败次数达到阈值，尝试自动修复
            if [ $consecutive_failures -ge $max_consecutive_failures ]; then
                send_alert "系统连续 $consecutive_failures 次检查失败，尝试自动修复" "HIGH"
                auto_fix_issues
                consecutive_failures=0
            fi
        fi
        
        # 每小时生成一次报告
        local current_minute=$(date +%M)
        if [ "$current_minute" = "00" ]; then
            generate_monitor_report
        fi
        
        sleep $MONITOR_INTERVAL
    done
}

# 显示帮助信息
show_help() {
    echo "MarketPrism系统监控脚本"
    echo ""
    echo "用法: $0 {start|check|report|help}"
    echo ""
    echo "命令:"
    echo "  start  - 启动持续监控"
    echo "  check  - 执行一次检查"
    echo "  report - 生成监控报告"
    echo "  help   - 显示此帮助信息"
    echo ""
    echo "配置:"
    echo "  监控间隔: ${MONITOR_INTERVAL}秒"
    echo "  日志文件: $MONITOR_LOG"
    echo ""
}

# 主函数
main() {
    # 确保日志目录存在
    mkdir -p "$LOG_DIR"
    
    case "${1:-help}" in
        start)
            monitor_loop
            ;;
        check)
            log_info "执行系统检查..."
            local total_issues=0
            check_critical_services || total_issues=$((total_issues + $?))
            check_system_resources || total_issues=$((total_issues + $?))
            check_network_connectivity || total_issues=$((total_issues + $?))
            
            if [ $total_issues -eq 0 ]; then
                log_success "系统检查完成：无问题发现"
            else
                log_warning "系统检查完成：发现 $total_issues 个问题"
            fi
            ;;
        report)
            generate_monitor_report
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            echo "未知命令: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"
