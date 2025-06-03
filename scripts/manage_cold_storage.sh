#!/bin/bash

# MarketPrism 冷存储管理脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COLD_COMPOSE_FILE="$PROJECT_ROOT/docker-compose.cold-storage.yml"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_message() {
    echo -e "${2}${1}${NC}"
}

# 检查Docker是否运行
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        print_message "❌ Docker未运行，请先启动Docker Desktop" $RED
        exit 1
    fi
}

# 启动冷存储服务
start_cold_storage() {
    print_message "🚀 启动冷存储服务..." $BLUE
    
    # 创建必要的目录
    mkdir -p "$PROJECT_ROOT/data/clickhouse-cold"
    mkdir -p "$PROJECT_ROOT/logs/clickhouse-cold"
    mkdir -p "$PROJECT_ROOT/backup/cold"
    
    # 启动服务
    docker-compose -f "$COLD_COMPOSE_FILE" up -d
    
    print_message "⏱️ 等待服务启动..." $YELLOW
    sleep 10
    
    # 检查服务状态
    if docker-compose -f "$COLD_COMPOSE_FILE" ps | grep -q "Up"; then
        print_message "✅ 冷存储服务启动成功!" $GREEN
        
        # 初始化数据库
        print_message "🔧 初始化冷存储数据库..." $BLUE
        cd "$PROJECT_ROOT"
        python scripts/init_cold_storage.py
        
    else
        print_message "❌ 冷存储服务启动失败" $RED
        docker-compose -f "$COLD_COMPOSE_FILE" logs
        exit 1
    fi
}

# 停止冷存储服务
stop_cold_storage() {
    print_message "🛑 停止冷存储服务..." $BLUE
    docker-compose -f "$COLD_COMPOSE_FILE" down
    print_message "✅ 冷存储服务已停止" $GREEN
}

# 重启冷存储服务
restart_cold_storage() {
    print_message "🔄 重启冷存储服务..." $BLUE
    stop_cold_storage
    sleep 2
    start_cold_storage
}

# 查看服务状态
status_cold_storage() {
    print_message "📊 冷存储服务状态:" $BLUE
    docker-compose -f "$COLD_COMPOSE_FILE" ps
    
    echo ""
    print_message "📋 服务健康检查:" $BLUE
    
    # 检查ClickHouse健康状态
    if curl -s "http://localhost:8124/ping" > /dev/null; then
        print_message "✅ ClickHouse冷存储: 健康" $GREEN
    else
        print_message "❌ ClickHouse冷存储: 不健康" $RED
    fi
}

# 查看日志
logs_cold_storage() {
    print_message "📋 查看冷存储日志:" $BLUE
    docker-compose -f "$COLD_COMPOSE_FILE" logs -f --tail=50
}

# 备份冷存储数据
backup_cold_storage() {
    print_message "💾 开始备份冷存储数据..." $BLUE
    
    BACKUP_DIR="$PROJECT_ROOT/backup/cold/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    
    # 使用clickhouse-backup工具
    docker-compose -f "$COLD_COMPOSE_FILE" exec clickhouse-backup clickhouse-backup create "backup_$(date +%Y%m%d_%H%M%S)"
    
    print_message "✅ 冷存储数据备份完成: $BACKUP_DIR" $GREEN
}

# 查看存储使用情况
storage_info() {
    print_message "💾 冷存储使用情况:" $BLUE
    
    # Docker容器存储使用
    docker system df
    
    echo ""
    
    # 数据目录大小
    if [ -d "$PROJECT_ROOT/data/clickhouse-cold" ]; then
        du -sh "$PROJECT_ROOT/data/clickhouse-cold"
    fi
    
    # 数据库统计
    echo ""
    print_message "📊 数据库统计:" $BLUE
    docker-compose -f "$COLD_COMPOSE_FILE" exec clickhouse-cold clickhouse-client --query "
        SELECT 
            database, 
            table,
            formatReadableSize(sum(bytes)) as size,
            sum(rows) as rows
        FROM system.parts 
        WHERE database = 'marketprism_cold'
        GROUP BY database, table
        ORDER BY sum(bytes) DESC
    " 2>/dev/null || echo "数据库未初始化或无法连接"
}

# 测试冷存储连接
test_connection() {
    print_message "🔗 测试冷存储连接..." $BLUE
    
    # 测试HTTP连接
    if curl -s "http://localhost:8124/ping" | grep -q "Ok"; then
        print_message "✅ HTTP连接正常" $GREEN
    else
        print_message "❌ HTTP连接失败" $RED
    fi
    
    # 测试TCP连接
    if nc -z localhost 9001; then
        print_message "✅ TCP连接正常" $GREEN
    else
        print_message "❌ TCP连接失败" $RED
    fi
    
    # 测试数据库查询
    echo ""
    print_message "🔍 测试数据库查询..." $BLUE
    docker-compose -f "$COLD_COMPOSE_FILE" exec clickhouse-cold clickhouse-client --query "SELECT version()" 2>/dev/null && \
        print_message "✅ 数据库查询正常" $GREEN || \
        print_message "❌ 数据库查询失败" $RED
}

# 显示帮助信息
show_help() {
    echo "MarketPrism 冷存储管理脚本"
    echo ""
    echo "用法: $0 [命令]"
    echo ""
    echo "命令:"
    echo "  start     启动冷存储服务"
    echo "  stop      停止冷存储服务"
    echo "  restart   重启冷存储服务"
    echo "  status    查看服务状态"
    echo "  logs      查看服务日志"
    echo "  backup    备份冷存储数据"
    echo "  storage   查看存储使用情况"
    echo "  test      测试连接"
    echo "  help      显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 start        # 启动冷存储"
    echo "  $0 status       # 查看状态"
    echo "  $0 logs         # 查看日志"
}

# 主函数
main() {
    check_docker
    
    case "${1:-help}" in
        "start")
            start_cold_storage
            ;;
        "stop")
            stop_cold_storage
            ;;
        "restart")
            restart_cold_storage
            ;;
        "status")
            status_cold_storage
            ;;
        "logs")
            logs_cold_storage
            ;;
        "backup")
            backup_cold_storage
            ;;
        "storage")
            storage_info
            ;;
        "test")
            test_connection
            ;;
        "help"|*)
            show_help
            ;;
    esac
}

# 执行主函数
main "$@" 