#!/bin/bash

# Data Collector性能监控脚本
# 专门监控Data Collector API的性能指标

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
CONTAINER_NAME="marketprism-market-data-collector"
SERVICE_URL="http://localhost:8084"
LOG_DIR="/home/ubuntu/marketprism/logs"
MONITOR_LOG="$LOG_DIR/data-collector-monitor.log"

# 日志函数
log_with_timestamp() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$MONITOR_LOG"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
    log_with_timestamp "[INFO] $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
    log_with_timestamp "[SUCCESS] $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
    log_with_timestamp "[WARNING] $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    log_with_timestamp "[ERROR] $1"
}

# 获取容器资源使用情况
get_container_stats() {
    local stats=$(docker stats --no-stream --format "table {{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}\t{{.BlockIO}}\t{{.PIDs}}" $CONTAINER_NAME 2>/dev/null)
    
    if [ $? -eq 0 ]; then
        echo "$stats" | tail -n +2
    else
        echo "N/A	N/A	N/A	N/A	N/A	N/A"
    fi
}

# 获取服务健康状态
get_service_health() {
    local start_time=$(date +%s%3N)
    local response=$(curl -s -w "%{http_code}" -o /tmp/health_response.json --max-time 5 "$SERVICE_URL/health" 2>/dev/null)
    local end_time=$(date +%s%3N)
    local response_time=$((end_time - start_time))
    
    if [ "$response" = "200" ]; then
        local health_data=$(cat /tmp/health_response.json 2>/dev/null)
        echo "healthy|${response_time}ms|$health_data"
    else
        echo "unhealthy|timeout|{}"
    fi
}

# 获取错误日志统计
get_error_stats() {
    local error_count=$(docker logs --since="1m" $CONTAINER_NAME 2>/dev/null | grep -c "\[error\]" || echo "0")
    local warning_count=$(docker logs --since="1m" $CONTAINER_NAME 2>/dev/null | grep -c "\[warning\]" || echo "0")
    local total_logs=$(docker logs --since="1m" $CONTAINER_NAME 2>/dev/null | wc -l || echo "0")
    
    echo "$error_count|$warning_count|$total_logs"
}

# 获取最近的错误信息
get_recent_errors() {
    docker logs --since="5m" $CONTAINER_NAME 2>/dev/null | grep "\[error\]" | tail -5 || echo "无错误"
}

# 分析性能问题
analyze_performance() {
    local cpu_usage="$1"
    local mem_usage="$2"
    local error_count="$3"
    local response_time="$4"
    
    local issues=()
    
    # CPU使用率分析
    local cpu_num=$(echo $cpu_usage | sed 's/%//')
    if (( $(echo "$cpu_num > 80" | bc -l 2>/dev/null || echo "0") )); then
        issues+=("CPU使用率过高: $cpu_usage")
    fi
    
    # 内存使用率分析
    local mem_num=$(echo $mem_usage | sed 's/%//')
    if (( $(echo "$mem_num > 85" | bc -l 2>/dev/null || echo "0") )); then
        issues+=("内存使用率过高: $mem_usage")
    fi
    
    # 错误数量分析
    if [ "$error_count" -gt 0 ]; then
        issues+=("发现 $error_count 个错误")
    fi
    
    # 响应时间分析
    local response_num=$(echo $response_time | sed 's/ms//')
    if [ "$response_num" -gt 1000 ] 2>/dev/null; then
        issues+=("响应时间过长: $response_time")
    fi
    
    if [ ${#issues[@]} -eq 0 ]; then
        echo "性能正常"
    else
        printf '%s\n' "${issues[@]}"
    fi
}

# 生成性能建议
generate_recommendations() {
    local cpu_usage="$1"
    local mem_usage="$2"
    local error_count="$3"
    
    local recommendations=()
    
    local cpu_num=$(echo $cpu_usage | sed 's/%//')
    if (( $(echo "$cpu_num > 70" | bc -l 2>/dev/null || echo "0") )); then
        recommendations+=("• 考虑增加CPU资源限制或优化数据处理算法")
        recommendations+=("• 检查是否有死循环或低效的数据处理逻辑")
    fi
    
    local mem_num=$(echo $mem_usage | sed 's/%//')
    if (( $(echo "$mem_num > 70" | bc -l 2>/dev/null || echo "0") )); then
        recommendations+=("• 考虑增加内存限制或优化内存使用")
        recommendations+=("• 检查是否有内存泄漏")
    fi
    
    if [ "$error_count" -gt 0 ]; then
        recommendations+=("• 检查错误日志并修复代码问题")
        recommendations+=("• 考虑重启服务以清除临时错误状态")
    fi
    
    if [ ${#recommendations[@]} -eq 0 ]; then
        echo "无特殊建议，系统运行良好"
    else
        printf '%s\n' "${recommendations[@]}"
    fi
}

# 显示实时监控
show_realtime_monitor() {
    log_info "开始Data Collector实时监控 (按Ctrl+C退出)"
    echo ""
    
    while true; do
        clear
        echo "========================================"
        echo "    Data Collector实时性能监控"
        echo "========================================"
        echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
        echo ""
        
        # 获取数据
        local stats=$(get_container_stats)
        local health_info=$(get_service_health)
        local error_stats=$(get_error_stats)
        
        # 解析数据
        local cpu_usage=$(echo $stats | awk '{print $1}')
        local mem_usage_raw=$(echo $stats | awk '{print $2}')
        local mem_percent=$(echo $stats | awk '{print $3}')
        local net_io=$(echo $stats | awk '{print $4}')
        local block_io=$(echo $stats | awk '{print $5}')
        local pids=$(echo $stats | awk '{print $6}')
        
        local health_status=$(echo $health_info | cut -d'|' -f1)
        local response_time=$(echo $health_info | cut -d'|' -f2)
        
        local error_count=$(echo $error_stats | cut -d'|' -f1)
        local warning_count=$(echo $error_stats | cut -d'|' -f2)
        local total_logs=$(echo $error_stats | cut -d'|' -f3)
        
        # 显示基本信息
        echo "📊 容器资源使用:"
        echo "  CPU使用率: $cpu_usage"
        echo "  内存使用: $mem_usage_raw ($mem_percent)"
        echo "  网络I/O: $net_io"
        echo "  磁盘I/O: $block_io"
        echo "  进程数: $pids"
        echo ""
        
        echo "🏥 服务健康状态:"
        if [ "$health_status" = "healthy" ]; then
            echo -e "  状态: ${GREEN}健康${NC}"
        else
            echo -e "  状态: ${RED}异常${NC}"
        fi
        echo "  响应时间: $response_time"
        echo ""
        
        echo "📝 日志统计 (最近1分钟):"
        echo "  错误数: $error_count"
        echo "  警告数: $warning_count"
        echo "  总日志数: $total_logs"
        echo ""
        
        # 性能分析
        echo "🔍 性能分析:"
        local analysis=$(analyze_performance "$cpu_usage" "$mem_percent" "$error_count" "$response_time")
        echo "  $analysis"
        echo ""
        
        # 建议
        echo "💡 优化建议:"
        local recommendations=$(generate_recommendations "$cpu_usage" "$mem_percent" "$error_count")
        echo "$recommendations"
        echo ""
        
        echo "========================================"
        
        sleep 5
    done
}

# 生成性能报告
generate_performance_report() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local report_file="$LOG_DIR/data-collector-performance-$(date +%Y%m%d_%H%M%S).md"
    
    log_info "生成Data Collector性能报告: $report_file"
    
    # 获取当前数据
    local stats=$(get_container_stats)
    local health_info=$(get_service_health)
    local error_stats=$(get_error_stats)
    local recent_errors=$(get_recent_errors)
    
    # 解析数据
    local cpu_usage=$(echo $stats | awk '{print $1}')
    local mem_usage_raw=$(echo $stats | awk '{print $2}')
    local mem_percent=$(echo $stats | awk '{print $3}')
    local net_io=$(echo $stats | awk '{print $4}')
    local block_io=$(echo $stats | awk '{print $5}')
    local pids=$(echo $stats | awk '{print $6}')
    
    local health_status=$(echo $health_info | cut -d'|' -f1)
    local response_time=$(echo $health_info | cut -d'|' -f2)
    local health_data=$(echo $health_info | cut -d'|' -f3)
    
    local error_count=$(echo $error_stats | cut -d'|' -f1)
    local warning_count=$(echo $error_stats | cut -d'|' -f2)
    local total_logs=$(echo $error_stats | cut -d'|' -f3)
    
    cat > "$report_file" << EOF
# Data Collector性能报告

**生成时间**: $timestamp  
**服务**: MarketPrism Data Collector API  
**容器**: $CONTAINER_NAME  

## 性能指标概览

### 资源使用情况
- **CPU使用率**: $cpu_usage
- **内存使用**: $mem_usage_raw ($mem_percent)
- **网络I/O**: $net_io
- **磁盘I/O**: $block_io
- **进程数**: $pids

### 服务健康状态
- **状态**: $health_status
- **响应时间**: $response_time
- **健康检查详情**: 
\`\`\`json
$health_data
\`\`\`

### 日志统计 (最近1分钟)
- **错误数**: $error_count
- **警告数**: $warning_count
- **总日志数**: $total_logs

## 性能分析

### 问题识别
$(analyze_performance "$cpu_usage" "$mem_percent" "$error_count" "$response_time")

### 优化建议
$(generate_recommendations "$cpu_usage" "$mem_percent" "$error_count")

## 最近错误日志
\`\`\`
$recent_errors
\`\`\`

## 监控建议
- 定期检查CPU和内存使用率
- 监控错误日志的增长趋势
- 关注响应时间变化
- 及时处理代码错误

EOF
    
    log_success "性能报告已生成: $report_file"
}

# 显示帮助信息
show_help() {
    echo "Data Collector性能监控脚本"
    echo ""
    echo "用法: $0 {monitor|report|stats|errors|help}"
    echo ""
    echo "命令:"
    echo "  monitor - 启动实时监控"
    echo "  report  - 生成性能报告"
    echo "  stats   - 显示当前统计信息"
    echo "  errors  - 显示最近错误"
    echo "  help    - 显示此帮助信息"
    echo ""
}

# 显示当前统计信息
show_current_stats() {
    echo "========================================"
    echo "    Data Collector当前状态"
    echo "========================================"
    
    local stats=$(get_container_stats)
    local health_info=$(get_service_health)
    local error_stats=$(get_error_stats)
    
    echo "📊 资源使用:"
    echo "$stats" | awk '{printf "  CPU: %s, 内存: %s (%s), 网络: %s, 磁盘: %s, 进程: %s\n", $1, $2, $3, $4, $5, $6}'
    echo ""
    
    echo "🏥 服务状态:"
    local health_status=$(echo $health_info | cut -d'|' -f1)
    local response_time=$(echo $health_info | cut -d'|' -f2)
    echo "  状态: $health_status, 响应时间: $response_time"
    echo ""
    
    echo "📝 日志统计:"
    local error_count=$(echo $error_stats | cut -d'|' -f1)
    local warning_count=$(echo $error_stats | cut -d'|' -f2)
    echo "  错误: $error_count, 警告: $warning_count"
    echo ""
}

# 主函数
main() {
    # 确保日志目录存在
    mkdir -p "$LOG_DIR"
    
    case "${1:-help}" in
        monitor)
            show_realtime_monitor
            ;;
        report)
            generate_performance_report
            ;;
        stats)
            show_current_stats
            ;;
        errors)
            echo "最近的错误日志:"
            get_recent_errors
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
