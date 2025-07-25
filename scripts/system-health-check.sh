#!/bin/bash

# MarketPrism系统健康检查脚本
# 自动化检查所有服务状态并生成报告

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

# 检查Docker服务状态
check_docker_services() {
    log_info "检查Docker服务状态..."
    
    local services=(
        "marketprism-api-gateway:8080"
        "marketprism-monitoring-alerting:8082"
        "marketprism-data-storage-hot:8083"
        "marketprism-market-data-collector:8084"
        "marketprism-scheduler:8085"
        "marketprism-message-broker:8086"
        "marketprism-postgres:5432"
        "marketprism-prometheus:9090"
        "marketprism-nats:4222"
        "marketprism-clickhouse-fixed:8123"
        "marketprism-redis:6379"
    )
    
    local healthy_count=0
    local total_count=${#services[@]}
    
    echo "| 服务名称 | 状态 | 健康检查 | 运行时间 |"
    echo "|---------|------|----------|----------|"
    
    for service_info in "${services[@]}"; do
        local service_name=$(echo $service_info | cut -d: -f1)
        local port=$(echo $service_info | cut -d: -f2)
        
        # 检查容器状态
        local container_status=$(docker ps --format "table {{.Names}}\t{{.Status}}" | grep "$service_name" | awk '{print $2, $3}' || echo "Not Running")
        
        if [[ "$container_status" == *"healthy"* ]]; then
            echo "| $service_name | ✅ 运行中 | ✅ 健康 | $container_status |"
            ((healthy_count++))
        elif [[ "$container_status" == *"unhealthy"* ]]; then
            echo "| $service_name | ⚠️ 运行中 | ❌ 不健康 | $container_status |"
        elif [[ "$container_status" == *"Up"* ]]; then
            echo "| $service_name | ✅ 运行中 | ⏳ 检查中 | $container_status |"
            ((healthy_count++))
        else
            echo "| $service_name | ❌ 停止 | ❌ 不可用 | $container_status |"
        fi
    done
    
    echo ""
    log_info "服务状态总结: $healthy_count/$total_count 服务正常运行"
    
    if [ $healthy_count -eq $total_count ]; then
        log_success "所有服务运行正常！"
        return 0
    else
        log_warning "有 $((total_count - healthy_count)) 个服务存在问题"
        return 1
    fi
}

# 检查服务健康端点
check_service_endpoints() {
    log_info "检查服务健康端点..."
    
    local endpoints=(
        "API Gateway|http://localhost:8080/health"
        "Monitoring|http://localhost:8082/health"
        "Data Storage|http://localhost:8083/health"
        "Data Collector|http://localhost:8084/health"
        "Scheduler|http://localhost:8085/health"
        "Message Broker|http://localhost:8086/health"
        "Prometheus|http://localhost:9090/-/healthy"
        "ClickHouse|http://localhost:8123/ping"
    )
    
    local healthy_endpoints=0
    local total_endpoints=${#endpoints[@]}
    
    echo "| 服务 | 端点 | 状态 | 响应时间 |"
    echo "|------|------|------|----------|"
    
    for endpoint_info in "${endpoints[@]}"; do
        local service_name=$(echo $endpoint_info | cut -d'|' -f1)
        local endpoint_url=$(echo $endpoint_info | cut -d'|' -f2)
        
        local start_time=$(date +%s%3N)
        local response=$(curl -s -w "%{http_code}" -o /dev/null --max-time 5 "$endpoint_url" 2>/dev/null || echo "000")
        local end_time=$(date +%s%3N)
        local response_time=$((end_time - start_time))
        
        if [ "$response" = "200" ]; then
            echo "| $service_name | $endpoint_url | ✅ 正常 | ${response_time}ms |"
            ((healthy_endpoints++))
        else
            echo "| $service_name | $endpoint_url | ❌ 失败 | 超时 |"
        fi
    done
    
    echo ""
    log_info "端点检查总结: $healthy_endpoints/$total_endpoints 端点正常"
    
    if [ $healthy_endpoints -eq $total_endpoints ]; then
        log_success "所有服务端点正常！"
        return 0
    else
        log_warning "有 $((total_endpoints - healthy_endpoints)) 个端点存在问题"
        return 1
    fi
}

# 检查WebSocket连接
check_websocket() {
    log_info "检查WebSocket连接..."
    
    # 检查WebSocket服务器进程
    local ws_process=$(ps aux | grep "websocket-server.js" | grep -v grep || echo "")
    
    if [ -n "$ws_process" ]; then
        log_success "WebSocket服务器进程正在运行"
        
        # 检查端口
        local port_check=$(netstat -tlnp | grep ":8089" || echo "")
        if [ -n "$port_check" ]; then
            log_success "WebSocket端口8089正在监听"
            return 0
        else
            log_error "WebSocket端口8089未在监听"
            return 1
        fi
    else
        log_error "WebSocket服务器进程未运行"
        return 1
    fi
}

# 检查数据流
check_data_flow() {
    log_info "检查数据流状态..."
    
    # 检查NATS连接
    local nats_check=$(nc -z localhost 4222 && echo "OK" || echo "FAIL")
    if [ "$nats_check" = "OK" ]; then
        log_success "NATS消息代理连接正常"
    else
        log_error "NATS消息代理连接失败"
        return 1
    fi
    
    # 检查数据库连接
    local pg_check=$(nc -z localhost 5432 && echo "OK" || echo "FAIL")
    local ch_check=$(nc -z localhost 8123 && echo "OK" || echo "FAIL")
    local redis_check=$(nc -z localhost 6379 && echo "OK" || echo "FAIL")
    
    if [ "$pg_check" = "OK" ] && [ "$ch_check" = "OK" ] && [ "$redis_check" = "OK" ]; then
        log_success "所有数据库连接正常"
        return 0
    else
        log_error "数据库连接存在问题: PostgreSQL=$pg_check, ClickHouse=$ch_check, Redis=$redis_check"
        return 1
    fi
}

# 生成系统报告
generate_system_report() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local report_file="/home/ubuntu/marketprism/logs/system-health-report-$(date +%Y%m%d_%H%M%S).md"
    
    log_info "生成系统健康报告: $report_file"
    
    cat > "$report_file" << EOF
# MarketPrism系统健康报告

**生成时间**: $timestamp  
**检查类型**: 自动化系统健康检查  

## 系统状态总览

EOF
    
    # 添加Docker服务状态
    echo "### Docker服务状态" >> "$report_file"
    echo "" >> "$report_file"
    check_docker_services >> "$report_file" 2>&1
    echo "" >> "$report_file"
    
    # 添加服务端点状态
    echo "### 服务端点状态" >> "$report_file"
    echo "" >> "$report_file"
    check_service_endpoints >> "$report_file" 2>&1
    echo "" >> "$report_file"
    
    # 添加WebSocket状态
    echo "### WebSocket连接状态" >> "$report_file"
    echo "" >> "$report_file"
    check_websocket >> "$report_file" 2>&1
    echo "" >> "$report_file"
    
    # 添加数据流状态
    echo "### 数据流状态" >> "$report_file"
    echo "" >> "$report_file"
    check_data_flow >> "$report_file" 2>&1
    echo "" >> "$report_file"
    
    log_success "系统健康报告已生成: $report_file"
}

# 主函数
main() {
    echo "========================================"
    echo "    MarketPrism系统健康检查工具"
    echo "========================================"
    echo ""
    
    local docker_status=0
    local endpoint_status=0
    local websocket_status=0
    local dataflow_status=0
    
    # 执行所有检查
    check_docker_services || docker_status=1
    echo ""
    
    check_service_endpoints || endpoint_status=1
    echo ""
    
    check_websocket || websocket_status=1
    echo ""
    
    check_data_flow || dataflow_status=1
    echo ""
    
    # 生成报告
    generate_system_report
    echo ""
    
    # 总结
    local total_issues=$((docker_status + endpoint_status + websocket_status + dataflow_status))
    
    if [ $total_issues -eq 0 ]; then
        log_success "🎉 系统健康检查完成：所有组件运行正常！"
        exit 0
    else
        log_warning "⚠️ 系统健康检查完成：发现 $total_issues 个问题需要关注"
        exit 1
    fi
}

# 执行主函数
main "$@"
