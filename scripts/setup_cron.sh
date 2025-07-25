#!/bin/bash

# MarketPrism 定时任务设置脚本
# 用于配置定时数据归档

set -e

# 配置参数
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ARCHIVE_SCRIPT="$SCRIPT_DIR/auto_archive.sh"
MONITOR_SCRIPT="$SCRIPT_DIR/system_monitor.py"
LOG_DIR="$PROJECT_ROOT/logs"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}🎯 MarketPrism 定时任务设置${NC}"
    echo "=" * 50
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️ $1${NC}"
}

# 检查依赖
check_dependencies() {
    print_info "检查系统依赖..."
    
    # 检查cron服务
    if ! command -v crontab &> /dev/null; then
        print_error "crontab 命令未找到，请安装 cron 服务"
        exit 1
    fi
    
    # 检查Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python3 未安装"
        exit 1
    fi
    
    # 检查Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker 未安装"
        exit 1
    fi
    
    # 检查脚本文件
    if [ ! -f "$ARCHIVE_SCRIPT" ]; then
        print_error "归档脚本未找到: $ARCHIVE_SCRIPT"
        exit 1
    fi
    
    if [ ! -f "$MONITOR_SCRIPT" ]; then
        print_error "监控脚本未找到: $MONITOR_SCRIPT"
        exit 1
    fi
    
    # 确保脚本可执行
    chmod +x "$ARCHIVE_SCRIPT"
    
    print_success "依赖检查通过"
}

# 创建日志目录
setup_log_directory() {
    print_info "设置日志目录..."
    
    mkdir -p "$LOG_DIR"
    
    # 创建归档日志文件
    touch "$LOG_DIR/archive.log"
    touch "$LOG_DIR/monitor.log"
    touch "$LOG_DIR/cron.log"
    
    print_success "日志目录创建完成: $LOG_DIR"
}

# 显示当前cron任务
show_current_cron() {
    print_info "当前cron任务:"
    echo "----------------------------------------"
    crontab -l 2>/dev/null | grep -E "(marketprism|archive|monitor)" || echo "暂无相关定时任务"
    echo "----------------------------------------"
}

# 创建cron任务
create_cron_jobs() {
    print_info "配置定时任务..."
    
    # 备份当前crontab
    crontab -l > /tmp/crontab_backup_$(date +%Y%m%d_%H%M%S) 2>/dev/null || true
    
    # 获取当前crontab内容（排除已存在的marketprism任务）
    current_cron=$(crontab -l 2>/dev/null | grep -v "marketprism" || true)
    
    # 创建新的cron任务
    cat > /tmp/marketprism_cron << EOF
# MarketPrism 自动化任务配置
# 生成时间: $(date)

# 每日凌晨2点执行数据归档
0 2 * * * $ARCHIVE_SCRIPT -l $LOG_DIR/archive.log >> $LOG_DIR/cron.log 2>&1

# 每4小时执行系统健康检查
0 */4 * * * /usr/bin/python3 $MONITOR_SCRIPT --health --output json >> $LOG_DIR/monitor.log 2>&1

# 每周日凌晨3点生成系统报告
0 3 * * 0 /usr/bin/python3 $MONITOR_SCRIPT --report --output json > $LOG_DIR/weekly_report_\$(date +\%Y\%m\%d).json 2>&1

# 每天中午12点检查存储使用情况
0 12 * * * /usr/bin/python3 $MONITOR_SCRIPT --storage >> $LOG_DIR/storage_check.log 2>&1

EOF
    
    # 合并现有cron和新任务
    {
        echo "$current_cron"
        echo ""
        cat /tmp/marketprism_cron
    } | crontab -
    
    # 清理临时文件
    rm -f /tmp/marketprism_cron
    
    print_success "定时任务配置完成"
}

# 显示配置的任务
show_configured_tasks() {
    print_info "已配置的定时任务:"
    echo ""
    echo "📅 数据归档: 每日 02:00"
    echo "   - 自动将7天前的数据从热存储迁移到冷存储"
    echo "   - 日志: $LOG_DIR/archive.log"
    echo ""
    echo "🏥 健康检查: 每4小时"
    echo "   - 检查容器状态和数据库连接"
    echo "   - 日志: $LOG_DIR/monitor.log"
    echo ""
    echo "📊 周报告: 每周日 03:00"
    echo "   - 生成完整的系统状态报告"
    echo "   - 输出: $LOG_DIR/weekly_report_YYYYMMDD.json"
    echo ""
    echo "💾 存储检查: 每日 12:00"
    echo "   - 检查存储使用情况和性能"
    echo "   - 日志: $LOG_DIR/storage_check.log"
}

# 测试cron任务
test_cron_jobs() {
    print_info "测试cron任务配置..."
    
    echo "🧪 测试归档脚本..."
    if $ARCHIVE_SCRIPT --dry-run -l $LOG_DIR/test_archive.log; then
        print_success "归档脚本测试通过"
    else
        print_error "归档脚本测试失败"
        return 1
    fi
    
    echo "🧪 测试监控脚本..."
    if python3 $MONITOR_SCRIPT --health > /dev/null; then
        print_success "监控脚本测试通过"
    else
        print_error "监控脚本测试失败"
        return 1
    fi
    
    print_success "所有测试通过"
}

# 移除cron任务
remove_cron_jobs() {
    print_warning "移除MarketPrism定时任务..."
    
    # 备份当前crontab
    crontab -l > /tmp/crontab_backup_removal_$(date +%Y%m%d_%H%M%S) 2>/dev/null || true
    
    # 移除marketprism相关任务
    crontab -l 2>/dev/null | grep -v "marketprism" | crontab - || true
    
    print_success "定时任务已移除"
}

# 显示日志
show_logs() {
    local log_type="$1"
    local lines="${2:-50}"
    
    case "$log_type" in
        "archive")
            if [ -f "$LOG_DIR/archive.log" ]; then
                echo "📋 归档日志 (最近$lines行):"
                tail -n "$lines" "$LOG_DIR/archive.log"
            else
                print_warning "归档日志文件不存在"
            fi
            ;;
        "monitor")
            if [ -f "$LOG_DIR/monitor.log" ]; then
                echo "📋 监控日志 (最近$lines行):"
                tail -n "$lines" "$LOG_DIR/monitor.log"
            else
                print_warning "监控日志文件不存在"
            fi
            ;;
        "cron")
            if [ -f "$LOG_DIR/cron.log" ]; then
                echo "📋 Cron日志 (最近$lines行):"
                tail -n "$lines" "$LOG_DIR/cron.log"
            else
                print_warning "Cron日志文件不存在"
            fi
            ;;
        *)
            print_error "未知的日志类型: $log_type"
            echo "可用类型: archive, monitor, cron"
            ;;
    esac
}

# 显示帮助信息
show_help() {
    cat << EOF
MarketPrism 定时任务设置脚本

用法:
    $0 [选项]

选项:
    install         安装定时任务配置
    remove          移除定时任务配置
    status          显示当前任务状态
    test            测试任务配置
    logs TYPE       显示指定类型的日志 (archive|monitor|cron)
    --help          显示帮助信息

示例:
    $0 install              # 安装定时任务
    $0 status               # 查看当前状态
    $0 logs archive         # 查看归档日志
    $0 test                 # 测试配置

注意:
    - 需要root权限或sudo来修改系统cron配置
    - 安装前会备份现有的crontab配置
    - 所有日志文件存储在 $LOG_DIR

EOF
}

# 主函数
main() {
    print_header
    
    case "${1:-install}" in
        "install")
            check_dependencies
            setup_log_directory
            show_current_cron
            create_cron_jobs
            show_configured_tasks
            echo ""
            test_cron_jobs
            echo ""
            print_success "定时任务安装完成！"
            print_info "使用 '$0 status' 检查状态"
            print_info "使用 '$0 logs archive' 查看归档日志"
            ;;
        
        "remove")
            remove_cron_jobs
            print_info "如需重新安装，运行: $0 install"
            ;;
        
        "status")
            show_current_cron
            echo ""
            if [ -f "$LOG_DIR/archive.log" ]; then
                echo "📋 最近的归档活动:"
                tail -n 5 "$LOG_DIR/archive.log" 2>/dev/null || echo "暂无记录"
            fi
            ;;
        
        "test")
            check_dependencies
            test_cron_jobs
            ;;
        
        "logs")
            if [ -z "$2" ]; then
                print_error "请指定日志类型: archive, monitor, cron"
                exit 1
            fi
            show_logs "$2" "${3:-50}"
            ;;
        
        "--help"|"-h"|"help")
            show_help
            ;;
        
        *)
            print_error "未知操作: $1"
            show_help
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@" 