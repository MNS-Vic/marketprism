#!/bin/bash

# MarketPrism 自动数据归档脚本
# 用于定期将热存储数据归档到冷存储

set -e  # 遇到错误立即退出

# 配置参数
ARCHIVE_DAYS=${ARCHIVE_DAYS:-7}        # 归档天数阈值
LOG_FILE="/var/log/marketprism-archive.log"
LOCK_FILE="/tmp/marketprism-archive.lock"
HOT_CONTAINER="marketprism-clickhouse-1"
COLD_CONTAINER="marketprism-clickhouse-cold"
HOT_DATABASE="marketprism"
COLD_DATABASE="marketprism_cold"

# 日志函数
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# 错误处理函数
error_exit() {
    log "❌ 错误: $1"
    cleanup
    exit 1
}

# 清理函数
cleanup() {
    if [ -f "$LOCK_FILE" ]; then
        rm -f "$LOCK_FILE"
        log "🧹 清理锁文件"
    fi
}

# 信号处理
trap cleanup EXIT INT TERM

# 检查是否已有归档任务在运行
check_lock() {
    if [ -f "$LOCK_FILE" ]; then
        local pid=$(cat "$LOCK_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            log "⚠️ 归档任务已在运行 (PID: $pid)，退出"
            exit 0
        else
            log "🗑️ 发现旧的锁文件，清理中..."
            rm -f "$LOCK_FILE"
        fi
    fi
    
    # 创建锁文件
    echo $$ > "$LOCK_FILE"
    log "🔒 创建归档任务锁 (PID: $$)"
}

# 执行ClickHouse查询
execute_hot_query() {
    local query="$1"
    docker exec "$HOT_CONTAINER" clickhouse-client \
        --database "$HOT_DATABASE" \
        --query "$query" 2>/dev/null || return 1
}

execute_cold_query() {
    local query="$1"
    docker exec "$COLD_CONTAINER" clickhouse-client \
        --database "$COLD_DATABASE" \
        --query "$query" 2>/dev/null || return 1
}

# 检查容器状态
check_containers() {
    log "🔍 检查容器状态..."
    
    if ! docker ps --format '{{.Names}}' | grep -q "^$HOT_CONTAINER$"; then
        error_exit "热存储容器 $HOT_CONTAINER 未运行"
    fi
    
    if ! docker ps --format '{{.Names}}' | grep -q "^$COLD_CONTAINER$"; then
        error_exit "冷存储容器 $COLD_CONTAINER 未运行"
    fi
    
    log "✅ 容器状态检查通过"
}

# 检查数据库连接
check_database_connection() {
    log "🔍 检查数据库连接..."
    
    # 检查热存储连接
    if ! execute_hot_query "SELECT 1" > /dev/null; then
        error_exit "无法连接到热存储数据库"
    fi
    
    # 检查冷存储连接
    if ! execute_cold_query "SELECT 1" > /dev/null; then
        error_exit "无法连接到冷存储数据库"
    fi
    
    log "✅ 数据库连接检查通过"
}

# 获取归档统计
get_archive_stats() {
    log "📊 获取归档统计信息..."
    
    # 热存储总记录数
    local hot_total=$(execute_hot_query "SELECT count() FROM market_data")
    log "📈 热存储总记录数: $hot_total"
    
    # 需要归档的记录数
    local archive_count=$(execute_hot_query "
        SELECT count() FROM market_data 
        WHERE timestamp <= now() - INTERVAL $ARCHIVE_DAYS DAY
    ")
    log "📦 需要归档的记录数: $archive_count"
    
    # 冷存储总记录数
    local cold_total=$(execute_cold_query "SELECT count() FROM market_data")
    log "❄️ 冷存储总记录数: $cold_total"
    
    echo "$archive_count"
}

# 执行数据归档
archive_data() {
    local archive_count="$1"
    
    if [ "$archive_count" -eq 0 ]; then
        log "ℹ️ 没有需要归档的数据"
        return 0
    fi
    
    log "🔄 开始归档 $archive_count 条记录..."
    
    # 步骤1: 导出需要归档的数据
    log "📤 导出归档数据..."
    local temp_file="/tmp/marketprism_archive_$(date +%Y%m%d_%H%M%S).tsv"
    
    execute_hot_query "
        SELECT timestamp, exchange, symbol, data_type, price, volume, raw_data, created_at
        FROM market_data 
        WHERE timestamp <= now() - INTERVAL $ARCHIVE_DAYS DAY
        FORMAT TabSeparated
    " > "$temp_file" || error_exit "数据导出失败"
    
    local exported_lines=$(wc -l < "$temp_file")
    log "📋 成功导出 $exported_lines 行数据到 $temp_file"
    
    # 步骤2: 将数据导入冷存储
    log "📥 导入数据到冷存储..."
    
    # 使用cat和管道将数据导入冷存储
    if cat "$temp_file" | docker exec -i "$COLD_CONTAINER" clickhouse-client \
        --database "$COLD_DATABASE" \
        --query "INSERT INTO market_data FORMAT TabSeparated"; then
        log "✅ 数据成功导入冷存储"
    else
        error_exit "数据导入冷存储失败"
    fi
    
    # 步骤3: 验证冷存储数据
    log "🔍 验证冷存储数据..."
    local cold_count_after=$(execute_cold_query "SELECT count() FROM market_data")
    log "📊 冷存储记录数 (导入后): $cold_count_after"
    
    # 步骤4: 删除热存储中已归档的数据
    log "🗑️ 清理热存储中已归档的数据..."
    
    local delete_result=$(execute_hot_query "
        ALTER TABLE market_data 
        DELETE WHERE timestamp <= now() - INTERVAL $ARCHIVE_DAYS DAY
    ")
    
    if [ $? -eq 0 ]; then
        log "✅ 热存储数据清理完成"
    else
        error_exit "热存储数据清理失败"
    fi
    
    # 步骤5: 验证清理结果
    log "🔍 验证清理结果..."
    local hot_remaining=$(execute_hot_query "SELECT count() FROM market_data")
    log "📊 热存储剩余记录数: $hot_remaining"
    
    # 清理临时文件
    rm -f "$temp_file"
    log "🧹 清理临时文件: $temp_file"
    
    log "🎉 归档任务完成! 已归档 $archive_count 条记录"
}

# 生成归档报告
generate_report() {
    log "📋 生成归档报告..."
    
    # 获取最新统计
    local hot_total=$(execute_hot_query "SELECT count() FROM market_data")
    local hot_latest=$(execute_hot_query "SELECT max(timestamp) FROM market_data")
    local cold_total=$(execute_cold_query "SELECT count() FROM market_data")
    local cold_range=$(execute_cold_query "SELECT min(timestamp), max(timestamp) FROM market_data")
    
    # 存储使用情况
    local hot_size=$(execute_hot_query "
        SELECT formatReadableSize(sum(bytes)) 
        FROM system.parts 
        WHERE database = '$HOT_DATABASE' AND table = 'market_data'
    ")
    
    local cold_size=$(execute_cold_query "
        SELECT formatReadableSize(sum(bytes)) 
        FROM system.parts 
        WHERE database = '$COLD_DATABASE' AND table = 'market_data'
    ")
    
    log "📊 === 归档任务报告 ==="
    log "🔥 热存储: $hot_total 条记录, $hot_size, 最新数据: $hot_latest"
    log "❄️ 冷存储: $cold_total 条记录, $cold_size, 数据范围: $cold_range"
    log "⚙️ 归档策略: 保留最近 $ARCHIVE_DAYS 天数据在热存储"
    log "📈 总数据量: $((hot_total + cold_total)) 条记录"
}

# 主函数
main() {
    log "🚀 开始 MarketPrism 数据归档任务"
    log "⚙️ 配置: 归档阈值 = $ARCHIVE_DAYS 天"
    
    # 检查锁文件
    check_lock
    
    # 系统检查
    check_containers
    check_database_connection
    
    # 获取归档统计
    local archive_count=$(get_archive_stats)
    
    # 执行归档
    archive_data "$archive_count"
    
    # 生成报告
    generate_report
    
    log "✅ 归档任务成功完成"
}

# 帮助信息
show_help() {
    cat << EOF
MarketPrism 自动数据归档脚本

用法:
    $0 [选项]

选项:
    -d, --days DAYS     设置归档天数阈值 (默认: 7)
    -l, --log FILE      设置日志文件路径 (默认: /var/log/marketprism-archive.log)
    -h, --help          显示帮助信息
    --dry-run           试运行模式，只显示统计信息

示例:
    $0                  # 使用默认配置运行归档
    $0 -d 14            # 归档14天前的数据
    $0 --dry-run        # 试运行，查看需要归档的数据量

环境变量:
    ARCHIVE_DAYS        归档天数阈值
    LOG_FILE           日志文件路径

定时任务示例:
    # 每天凌晨2点执行归档
    0 2 * * * /path/to/auto_archive.sh

EOF
}

# 试运行模式
dry_run() {
    log "🧪 试运行模式 - 仅显示统计信息"
    
    check_containers
    check_database_connection
    
    local archive_count=$(get_archive_stats)
    
    log "💡 试运行结果:"
    log "   - 需要归档的记录数: $archive_count"
    log "   - 归档阈值: $ARCHIVE_DAYS 天"
    log "   - 如果执行归档，这些数据将从热存储迁移到冷存储"
    
    log "✅ 试运行完成"
}

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--days)
            ARCHIVE_DAYS="$2"
            shift 2
            ;;
        -l|--log)
            LOG_FILE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "未知选项: $1"
            show_help
            exit 1
            ;;
    esac
done

# 确保日志目录存在
mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true

# 执行主函数或试运行
if [ "$DRY_RUN" = true ]; then
    dry_run
else
    main
fi 