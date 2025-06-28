#!/bin/bash

# MarketPrism自动修复脚本
# 自动检测并修复常见问题

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

# 修复ClickHouse健康检查问题
fix_clickhouse_health() {
    log_info "检查ClickHouse健康状态..."
    
    local ch_container=$(docker ps | grep clickhouse | awk '{print $1}' | head -1)
    
    if [ -z "$ch_container" ]; then
        log_error "未找到ClickHouse容器"
        return 1
    fi
    
    local ch_status=$(docker ps --format "table {{.Names}}\t{{.Status}}" | grep clickhouse | awk '{print $2}')
    
    if [[ "$ch_status" == *"unhealthy"* ]]; then
        log_warning "ClickHouse健康检查失败，尝试修复..."
        
        # 检查功能是否正常
        local ping_result=$(curl -s http://localhost:8123/ping || echo "FAIL")
        
        if [ "$ping_result" = "Ok." ]; then
            log_info "ClickHouse功能正常，重启容器以修复健康检查..."
            
            # 重启容器
            docker restart "$ch_container"
            
            # 等待重启
            sleep 30
            
            # 检查新状态
            local new_status=$(docker ps --format "table {{.Names}}\t{{.Status}}" | grep clickhouse | awk '{print $2}')
            
            if [[ "$new_status" == *"healthy"* ]] || [[ "$new_status" == *"starting"* ]]; then
                log_success "ClickHouse健康检查已修复"
                return 0
            else
                log_warning "ClickHouse重启后仍有问题，但功能正常"
                return 1
            fi
        else
            log_error "ClickHouse功能异常，需要手动检查"
            return 1
        fi
    else
        log_success "ClickHouse健康状态正常"
        return 0
    fi
}

# 修复WebSocket连接问题
fix_websocket_connection() {
    log_info "检查WebSocket连接状态..."
    
    # 检查WebSocket进程
    local ws_process=$(ps aux | grep "websocket-server.js" | grep -v grep || echo "")
    
    if [ -z "$ws_process" ]; then
        log_warning "WebSocket服务器未运行，尝试启动..."
        
        cd /home/ubuntu/marketprism/services/monitoring-alerting-service/market-prism-dashboard
        
        # 检查是否已有进程在运行
        local existing_process=$(ps aux | grep "node.*websocket-server.js" | grep -v grep || echo "")
        
        if [ -n "$existing_process" ]; then
            log_info "发现现有WebSocket进程，终止后重启..."
            pkill -f "websocket-server.js" || true
            sleep 2
        fi
        
        # 启动WebSocket服务器
        nohup node websocket-server.js > /home/ubuntu/marketprism/logs/websocket-server.log 2>&1 &
        
        sleep 3
        
        # 验证启动
        local new_process=$(ps aux | grep "websocket-server.js" | grep -v grep || echo "")
        
        if [ -n "$new_process" ]; then
            log_success "WebSocket服务器已启动"
            return 0
        else
            log_error "WebSocket服务器启动失败"
            return 1
        fi
    else
        log_success "WebSocket服务器正在运行"
        return 0
    fi
}

# 修复Docker服务问题
fix_docker_services() {
    log_info "检查Docker服务状态..."
    
    local services=(
        "marketprism-api-gateway"
        "marketprism-monitoring-alerting"
        "marketprism-data-storage-hot"
        "marketprism-market-data-collector"
        "marketprism-scheduler"
        "marketprism-message-broker"
        "marketprism-postgres"
        "marketprism-prometheus"
        "marketprism-nats"
        "marketprism-redis"
    )
    
    local fixed_count=0
    
    for service in "${services[@]}"; do
        local container_status=$(docker ps -a --format "table {{.Names}}\t{{.Status}}" | grep "$service" | awk '{print $2}' || echo "")
        
        if [[ "$container_status" == *"Exited"* ]] || [ -z "$container_status" ]; then
            log_warning "服务 $service 未运行，尝试启动..."
            
            docker start "$service" 2>/dev/null || {
                log_error "无法启动服务 $service"
                continue
            }
            
            sleep 5
            
            local new_status=$(docker ps --format "table {{.Names}}\t{{.Status}}" | grep "$service" | awk '{print $2}' || echo "")
            
            if [[ "$new_status" == *"Up"* ]]; then
                log_success "服务 $service 已启动"
                ((fixed_count++))
            else
                log_error "服务 $service 启动失败"
            fi
        fi
    done
    
    if [ $fixed_count -gt 0 ]; then
        log_success "已修复 $fixed_count 个Docker服务"
    else
        log_info "所有Docker服务状态正常"
    fi
    
    return 0
}

# 修复网络连接问题
fix_network_issues() {
    log_info "检查网络连接问题..."
    
    # 检查端口占用
    local ports=("3000" "8080" "8082" "8083" "8084" "8085" "8086" "8089" "9090" "4222" "8123" "5432" "6379")
    
    for port in "${ports[@]}"; do
        local port_status=$(netstat -tlnp | grep ":$port " || echo "")
        
        if [ -z "$port_status" ]; then
            log_warning "端口 $port 未在监听"
        fi
    done
    
    # 检查Docker网络
    local network_status=$(docker network ls | grep marketprism || echo "")
    
    if [ -z "$network_status" ]; then
        log_warning "MarketPrism Docker网络不存在，但服务可能使用默认网络"
    fi
    
    return 0
}

# 清理日志文件
cleanup_logs() {
    log_info "清理旧日志文件..."
    
    local log_dir="/home/ubuntu/marketprism/logs"
    
    # 删除7天前的日志文件
    find "$log_dir" -name "*.log" -mtime +7 -delete 2>/dev/null || true
    find "$log_dir" -name "*-report-*.md" -mtime +7 -delete 2>/dev/null || true
    
    log_success "日志清理完成"
}

# 检查并安装缺失的依赖
check_dependencies() {
    log_info "检查系统依赖..."
    
    # 检查Python虚拟环境
    if [ ! -d "/home/ubuntu/marketprism/venv" ]; then
        log_warning "Python虚拟环境不存在，跳过Python依赖检查"
    else
        log_success "Python虚拟环境存在"
    fi
    
    # 检查Node.js依赖
    if [ ! -d "/home/ubuntu/marketprism/services/monitoring-alerting-service/market-prism-dashboard/node_modules" ]; then
        log_warning "Node.js依赖不完整，建议运行 npm install"
    else
        log_success "Node.js依赖存在"
    fi
    
    return 0
}

# 生成修复报告
generate_fix_report() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local report_file="/home/ubuntu/marketprism/logs/auto-fix-report-$(date +%Y%m%d_%H%M%S).md"
    
    log_info "生成自动修复报告: $report_file"
    
    cat > "$report_file" << EOF
# MarketPrism自动修复报告

**执行时间**: $timestamp  
**修复类型**: 自动化问题修复  

## 修复操作总结

### 执行的修复操作
1. ClickHouse健康检查修复
2. WebSocket连接修复
3. Docker服务状态修复
4. 网络连接检查
5. 日志清理
6. 依赖检查

### 修复结果
- 所有自动修复操作已完成
- 详细结果请查看上述日志输出

### 建议
- 定期运行此脚本以保持系统健康
- 如有持续问题，请手动检查相关服务
- 监控系统资源使用情况

EOF
    
    log_success "自动修复报告已生成: $report_file"
}

# 主函数
main() {
    echo "========================================"
    echo "    MarketPrism自动修复工具"
    echo "========================================"
    echo ""
    
    # 创建日志目录
    mkdir -p /home/ubuntu/marketprism/logs
    
    # 执行修复操作
    log_info "开始执行自动修复操作..."
    echo ""
    
    fix_docker_services
    echo ""
    
    fix_clickhouse_health
    echo ""
    
    fix_websocket_connection
    echo ""
    
    fix_network_issues
    echo ""
    
    check_dependencies
    echo ""
    
    cleanup_logs
    echo ""
    
    # 生成报告
    generate_fix_report
    echo ""
    
    log_success "🔧 自动修复操作完成！"
    log_info "建议运行健康检查脚本验证修复结果"
}

# 执行主函数
main "$@"
