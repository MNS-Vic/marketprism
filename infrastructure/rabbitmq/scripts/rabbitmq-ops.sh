#!/bin/bash

# MarketPrism RabbitMQ运维脚本
# 提供常用的RabbitMQ管理和监控功能

set -e

# 配置变量
RABBITMQ_USER="marketprism"
RABBITMQ_PASS="marketprism_monitor_2024"
RABBITMQ_HOST="localhost"
RABBITMQ_PORT="15672"
RABBITMQ_VHOST="/monitoring"
BASE_URL="http://${RABBITMQ_HOST}:${RABBITMQ_PORT}/api"

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

# 检查RabbitMQ连接
check_connection() {
    log_info "检查RabbitMQ连接..."
    
    if curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${BASE_URL}/overview" > /dev/null; then
        log_success "RabbitMQ连接正常"
        return 0
    else
        log_error "RabbitMQ连接失败"
        return 1
    fi
}

# 显示集群状态
show_cluster_status() {
    log_info "获取RabbitMQ集群状态..."
    
    local overview=$(curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${BASE_URL}/overview")
    
    echo "=== RabbitMQ集群状态 ==="
    echo "节点: $(echo "$overview" | grep -o '"node":"[^"]*"' | cut -d'"' -f4)"
    echo "版本: $(echo "$overview" | grep -o '"rabbitmq_version":"[^"]*"' | cut -d'"' -f4)"
    echo "Erlang版本: $(echo "$overview" | grep -o '"erlang_version":"[^"]*"' | cut -d'"' -f4)"
    
    local exchanges=$(echo "$overview" | grep -o '"exchanges":[0-9]*' | cut -d':' -f2)
    local queues=$(echo "$overview" | grep -o '"queues":[0-9]*' | cut -d':' -f2)
    local connections=$(echo "$overview" | grep -o '"connections":[0-9]*' | cut -d':' -f2)
    local channels=$(echo "$overview" | grep -o '"channels":[0-9]*' | cut -d':' -f2)
    
    echo "Exchanges: $exchanges"
    echo "队列: $queues"
    echo "连接: $connections"
    echo "通道: $channels"
}

# 显示队列状态
show_queue_status() {
    log_info "获取队列状态..."
    
    local queues=$(curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${BASE_URL}/queues/%2Fmonitoring")
    
    echo "=== 队列状态 ==="
    echo "$queues" | grep -o '"name":"[^"]*"' | while read -r line; do
        local queue_name=$(echo "$line" | cut -d'"' -f4)
        local messages=$(echo "$queues" | grep -A 20 "\"name\":\"$queue_name\"" | grep -o '"messages":[0-9]*' | head -1 | cut -d':' -f2)
        local consumers=$(echo "$queues" | grep -A 20 "\"name\":\"$queue_name\"" | grep -o '"consumers":[0-9]*' | head -1 | cut -d':' -f2)
        
        printf "%-30s 消息: %-6s 消费者: %-3s\n" "$queue_name" "$messages" "$consumers"
    done
}

# 显示连接信息
show_connections() {
    log_info "获取连接信息..."
    
    local connections=$(curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${BASE_URL}/connections")
    
    echo "=== 活跃连接 ==="
    echo "$connections" | grep -o '"name":"[^"]*"' | while read -r line; do
        local conn_name=$(echo "$line" | cut -d'"' -f4)
        local peer_host=$(echo "$connections" | grep -A 10 "\"name\":\"$conn_name\"" | grep -o '"peer_host":"[^"]*"' | head -1 | cut -d'"' -f4)
        local state=$(echo "$connections" | grep -A 10 "\"name\":\"$conn_name\"" | grep -o '"state":"[^"]*"' | head -1 | cut -d'"' -f4)
        
        printf "%-40s %-15s %s\n" "$conn_name" "$peer_host" "$state"
    done
}

# 清空队列
purge_queue() {
    local queue_name="$1"
    
    if [ -z "$queue_name" ]; then
        log_error "请指定队列名称"
        echo "用法: $0 purge <queue_name>"
        return 1
    fi
    
    log_warning "准备清空队列: $queue_name"
    read -p "确认清空队列 $queue_name 吗? (y/N): " confirm
    
    if [[ $confirm =~ ^[Yy]$ ]]; then
        curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
             -X DELETE "${BASE_URL}/queues/%2Fmonitoring/${queue_name}/contents"
        
        if [ $? -eq 0 ]; then
            log_success "队列 $queue_name 已清空"
        else
            log_error "清空队列 $queue_name 失败"
        fi
    else
        log_info "操作已取消"
    fi
}

# 发送测试消息
send_test_message() {
    local exchange="$1"
    local routing_key="$2"
    local message="$3"
    
    if [ -z "$exchange" ] || [ -z "$routing_key" ]; then
        log_error "请指定exchange和routing_key"
        echo "用法: $0 send <exchange> <routing_key> [message]"
        return 1
    fi
    
    if [ -z "$message" ]; then
        message="{\"test\": true, \"timestamp\": $(date +%s), \"source\": \"rabbitmq-ops\"}"
    fi
    
    log_info "发送测试消息到 $exchange/$routing_key"
    
    local response=$(curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
                          -X POST "${BASE_URL}/exchanges/%2Fmonitoring/${exchange}/publish" \
                          -H "Content-Type: application/json" \
                          -d "{
                              \"properties\": {\"delivery_mode\": 2},
                              \"routing_key\": \"$routing_key\",
                              \"payload\": \"$message\",
                              \"payload_encoding\": \"string\"
                          }")
    
    if echo "$response" | grep -q '"routed":true'; then
        log_success "消息发送成功并已路由"
    elif echo "$response" | grep -q '"routed":false'; then
        log_warning "消息发送成功但未路由到任何队列"
    else
        log_error "消息发送失败"
    fi
}

# 监控队列堆积
monitor_queue_backlog() {
    log_info "监控队列消息堆积..."
    
    while true; do
        clear
        echo "=== RabbitMQ队列监控 ($(date)) ==="
        echo "按 Ctrl+C 退出"
        echo ""
        
        local queues=$(curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${BASE_URL}/queues/%2Fmonitoring")
        
        printf "%-30s %-8s %-8s %-10s\n" "队列名称" "消息数" "消费者" "状态"
        echo "--------------------------------------------------------------------"
        
        echo "$queues" | grep -o '"name":"[^"]*"' | while read -r line; do
            local queue_name=$(echo "$line" | cut -d'"' -f4)
            local messages=$(echo "$queues" | grep -A 20 "\"name\":\"$queue_name\"" | grep -o '"messages":[0-9]*' | head -1 | cut -d':' -f2)
            local consumers=$(echo "$queues" | grep -A 20 "\"name\":\"$queue_name\"" | grep -o '"consumers":[0-9]*' | head -1 | cut -d':' -f2)
            
            local status="正常"
            if [ "$messages" -gt 1000 ]; then
                status="堆积"
            elif [ "$consumers" -eq 0 ] && [ "$messages" -gt 0 ]; then
                status="无消费者"
            fi
            
            printf "%-30s %-8s %-8s %-10s\n" "$queue_name" "$messages" "$consumers" "$status"
        done
        
        sleep 5
    done
}

# 备份队列定义
backup_definitions() {
    local backup_file="rabbitmq_definitions_$(date +%Y%m%d_%H%M%S).json"
    
    log_info "备份RabbitMQ定义到 $backup_file"
    
    curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
         "${BASE_URL}/definitions" > "$backup_file"
    
    if [ $? -eq 0 ]; then
        log_success "定义已备份到 $backup_file"
    else
        log_error "备份失败"
    fi
}

# 显示帮助信息
show_help() {
    echo "MarketPrism RabbitMQ运维脚本"
    echo ""
    echo "用法: $0 <command> [options]"
    echo ""
    echo "命令:"
    echo "  status          显示集群状态"
    echo "  queues          显示队列状态"
    echo "  connections     显示连接信息"
    echo "  purge <queue>   清空指定队列"
    echo "  send <exchange> <routing_key> [message]  发送测试消息"
    echo "  monitor         监控队列堆积情况"
    echo "  backup          备份队列定义"
    echo "  check           检查连接状态"
    echo "  help            显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 status"
    echo "  $0 purge alerts.p1.queue"
    echo "  $0 send monitoring.direct alert.p1 '{\"test\": true}'"
    echo "  $0 monitor"
}

# 主函数
main() {
    case "${1:-help}" in
        "status")
            check_connection && show_cluster_status
            ;;
        "queues")
            check_connection && show_queue_status
            ;;
        "connections")
            check_connection && show_connections
            ;;
        "purge")
            check_connection && purge_queue "$2"
            ;;
        "send")
            check_connection && send_test_message "$2" "$3" "$4"
            ;;
        "monitor")
            check_connection && monitor_queue_backlog
            ;;
        "backup")
            check_connection && backup_definitions
            ;;
        "check")
            check_connection
            ;;
        "help"|*)
            show_help
            ;;
    esac
}

# 执行主函数
main "$@"
