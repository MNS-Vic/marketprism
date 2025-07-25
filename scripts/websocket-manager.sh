#!/bin/bash

# WebSocket服务器管理脚本
# 自动化WebSocket服务器的启动、停止、重启和监控

set -e

# 配置
WEBSOCKET_DIR="/home/ubuntu/marketprism/services/monitoring-alerting-service/market-prism-dashboard"
WEBSOCKET_SCRIPT="websocket-server.js"
LOG_DIR="/home/ubuntu/marketprism/logs"
PID_FILE="$LOG_DIR/websocket-server.pid"
LOG_FILE="$LOG_DIR/websocket-server.log"

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

# 检查WebSocket服务器状态
check_status() {
    local pid=$(ps aux | grep "node.*$WEBSOCKET_SCRIPT" | grep -v grep | awk '{print $2}' || echo "")
    
    if [ -n "$pid" ]; then
        echo "running:$pid"
    else
        echo "stopped"
    fi
}

# 启动WebSocket服务器
start_websocket() {
    log_info "启动WebSocket服务器..."
    
    local status=$(check_status)
    
    if [[ "$status" == "running:"* ]]; then
        local pid=$(echo $status | cut -d: -f2)
        log_warning "WebSocket服务器已在运行 (PID: $pid)"
        return 0
    fi
    
    # 确保目录存在
    mkdir -p "$LOG_DIR"
    
    # 切换到WebSocket目录
    cd "$WEBSOCKET_DIR"
    
    # 启动服务器
    nohup node "$WEBSOCKET_SCRIPT" > "$LOG_FILE" 2>&1 &
    local pid=$!
    
    # 保存PID
    echo $pid > "$PID_FILE"
    
    # 等待启动
    sleep 3
    
    # 验证启动
    local new_status=$(check_status)
    
    if [[ "$new_status" == "running:"* ]]; then
        local new_pid=$(echo $new_status | cut -d: -f2)
        log_success "WebSocket服务器已启动 (PID: $new_pid)"
        log_info "日志文件: $LOG_FILE"
        return 0
    else
        log_error "WebSocket服务器启动失败"
        return 1
    fi
}

# 停止WebSocket服务器
stop_websocket() {
    log_info "停止WebSocket服务器..."
    
    local status=$(check_status)
    
    if [[ "$status" == "stopped" ]]; then
        log_warning "WebSocket服务器未运行"
        return 0
    fi
    
    local pid=$(echo $status | cut -d: -f2)
    
    # 尝试优雅停止
    kill "$pid" 2>/dev/null || true
    
    # 等待停止
    sleep 3
    
    # 检查是否已停止
    local new_status=$(check_status)
    
    if [[ "$new_status" == "stopped" ]]; then
        log_success "WebSocket服务器已停止"
        rm -f "$PID_FILE"
        return 0
    else
        # 强制停止
        log_warning "优雅停止失败，强制停止..."
        kill -9 "$pid" 2>/dev/null || true
        sleep 2
        
        local final_status=$(check_status)
        
        if [[ "$final_status" == "stopped" ]]; then
            log_success "WebSocket服务器已强制停止"
            rm -f "$PID_FILE"
            return 0
        else
            log_error "无法停止WebSocket服务器"
            return 1
        fi
    fi
}

# 重启WebSocket服务器
restart_websocket() {
    log_info "重启WebSocket服务器..."
    
    stop_websocket
    sleep 2
    start_websocket
}

# 显示WebSocket服务器状态
show_status() {
    local status=$(check_status)
    
    echo "========================================"
    echo "    WebSocket服务器状态"
    echo "========================================"
    
    if [[ "$status" == "running:"* ]]; then
        local pid=$(echo $status | cut -d: -f2)
        log_success "状态: 运行中"
        echo "PID: $pid"
        
        # 显示端口信息
        local port_info=$(netstat -tlnp | grep ":8089" || echo "")
        if [ -n "$port_info" ]; then
            echo "端口: 8089 (监听中)"
        else
            echo "端口: 8089 (未监听)"
        fi
        
        # 显示内存使用
        local memory=$(ps -p "$pid" -o rss= 2>/dev/null | awk '{print $1/1024 " MB"}' || echo "未知")
        echo "内存使用: $memory"
        
        # 显示运行时间
        local start_time=$(ps -p "$pid" -o lstart= 2>/dev/null || echo "未知")
        echo "启动时间: $start_time"
        
    else
        log_warning "状态: 未运行"
    fi
    
    # 显示日志文件信息
    if [ -f "$LOG_FILE" ]; then
        local log_size=$(du -h "$LOG_FILE" | cut -f1)
        echo "日志文件: $LOG_FILE ($log_size)"
    else
        echo "日志文件: 不存在"
    fi
    
    echo "========================================"
}

# 显示实时日志
show_logs() {
    if [ -f "$LOG_FILE" ]; then
        log_info "显示WebSocket服务器日志 (按Ctrl+C退出):"
        echo ""
        tail -f "$LOG_FILE"
    else
        log_error "日志文件不存在: $LOG_FILE"
        return 1
    fi
}

# 测试WebSocket连接
test_connection() {
    log_info "测试WebSocket连接..."
    
    # 检查端口是否监听
    local port_check=$(netstat -tlnp | grep ":8089" || echo "")
    
    if [ -z "$port_check" ]; then
        log_error "WebSocket端口8089未在监听"
        return 1
    fi
    
    log_success "WebSocket端口8089正在监听"
    
    # 尝试HTTP连接测试
    local http_test=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8089 || echo "000")
    
    if [ "$http_test" = "400" ] || [ "$http_test" = "426" ]; then
        log_success "WebSocket服务器响应正常 (HTTP $http_test)"
        return 0
    else
        log_warning "WebSocket服务器HTTP响应异常 (HTTP $http_test)"
        return 1
    fi
}

# 显示帮助信息
show_help() {
    echo "WebSocket服务器管理脚本"
    echo ""
    echo "用法: $0 {start|stop|restart|status|logs|test|help}"
    echo ""
    echo "命令:"
    echo "  start   - 启动WebSocket服务器"
    echo "  stop    - 停止WebSocket服务器"
    echo "  restart - 重启WebSocket服务器"
    echo "  status  - 显示服务器状态"
    echo "  logs    - 显示实时日志"
    echo "  test    - 测试WebSocket连接"
    echo "  help    - 显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 start    # 启动服务器"
    echo "  $0 status   # 查看状态"
    echo "  $0 logs     # 查看日志"
}

# 主函数
main() {
    case "${1:-help}" in
        start)
            start_websocket
            ;;
        stop)
            stop_websocket
            ;;
        restart)
            restart_websocket
            ;;
        status)
            show_status
            ;;
        logs)
            show_logs
            ;;
        test)
            test_connection
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "未知命令: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"
