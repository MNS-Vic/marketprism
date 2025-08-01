#!/bin/bash
set -e

# MarketPrism 日志清理脚本
# 定期清理应用日志数据卷中的过期日志文件

echo "🧹 MarketPrism 日志清理任务"
echo "时间: $(date)"
echo "=" * 50

# 配置参数
LOG_RETENTION_DAYS=${LOG_RETENTION_DAYS:-7}        # 日志保留天数
MAX_LOG_SIZE_MB=${MAX_LOG_SIZE_MB:-1000}           # 单个数据卷最大大小(MB)
DRY_RUN=${DRY_RUN:-false}                          # 是否为试运行模式

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

# 获取数据卷路径
get_volume_path() {
    local volume_name=$1
    docker volume inspect "$volume_name" --format '{{ .Mountpoint }}' 2>/dev/null
}

# 清理指定数据卷中的日志
cleanup_volume_logs() {
    local volume_name=$1
    local volume_path=$(get_volume_path "$volume_name")
    
    if [ -z "$volume_path" ]; then
        log_warning "数据卷不存在: $volume_name"
        return 1
    fi
    
    log_info "清理数据卷: $volume_name ($volume_path)"
    
    # 检查数据卷大小
    local volume_size_mb=$(du -sm "$volume_path" 2>/dev/null | cut -f1)
    log_info "当前大小: ${volume_size_mb}MB"
    
    # 查找过期日志文件
    local old_files=$(find "$volume_path" -name "*.log*" -type f -mtime +$LOG_RETENTION_DAYS 2>/dev/null)
    local old_count=$(echo "$old_files" | grep -c . || echo "0")
    
    if [ "$old_count" -gt 0 ]; then
        log_info "发现 $old_count 个过期日志文件 (>${LOG_RETENTION_DAYS}天)"
        
        if [ "$DRY_RUN" = "true" ]; then
            log_info "试运行模式 - 将要删除的文件:"
            echo "$old_files" | head -10
            [ "$old_count" -gt 10 ] && log_info "... 还有 $((old_count - 10)) 个文件"
        else
            # 删除过期文件
            echo "$old_files" | xargs rm -f
            log_success "已删除 $old_count 个过期日志文件"
        fi
    else
        log_info "没有发现过期日志文件"
    fi
    
    # 如果数据卷仍然过大，删除最旧的文件
    volume_size_mb=$(du -sm "$volume_path" 2>/dev/null | cut -f1)
    if [ "$volume_size_mb" -gt "$MAX_LOG_SIZE_MB" ]; then
        log_warning "数据卷大小超限: ${volume_size_mb}MB > ${MAX_LOG_SIZE_MB}MB"
        
        # 按修改时间排序，删除最旧的文件直到大小合规
        local files_to_remove=$(find "$volume_path" -name "*.log*" -type f -printf '%T@ %p\n' | sort -n | head -20 | cut -d' ' -f2-)
        
        if [ -n "$files_to_remove" ]; then
            if [ "$DRY_RUN" = "true" ]; then
                log_info "试运行模式 - 将要删除的最旧文件:"
                echo "$files_to_remove" | head -5
            else
                echo "$files_to_remove" | xargs rm -f
                local new_size_mb=$(du -sm "$volume_path" 2>/dev/null | cut -f1)
                log_success "大小优化: ${volume_size_mb}MB -> ${new_size_mb}MB"
            fi
        fi
    fi
    
    # 压缩大型日志文件
    local large_files=$(find "$volume_path" -name "*.log" -type f -size +50M 2>/dev/null)
    if [ -n "$large_files" ]; then
        log_info "压缩大型日志文件..."
        if [ "$DRY_RUN" = "true" ]; then
            log_info "试运行模式 - 将要压缩的文件:"
            echo "$large_files"
        else
            echo "$large_files" | while read -r file; do
                if [ -f "$file" ]; then
                    gzip "$file" && log_success "已压缩: $(basename "$file")"
                fi
            done
        fi
    fi
}

# 清理Docker容器日志
cleanup_docker_logs() {
    log_info "清理Docker容器日志..."
    
    local containers=$(docker ps -a --format "table {{.Names}}" | grep "marketprism-" | tail -n +2)
    
    if [ -n "$containers" ]; then
        echo "$containers" | while read -r container; do
            if [ -n "$container" ]; then
                local log_size=$(docker logs --details "$container" 2>/dev/null | wc -c)
                local log_size_mb=$((log_size / 1024 / 1024))
                
                if [ "$log_size_mb" -gt 100 ]; then
                    log_info "容器 $container 日志大小: ${log_size_mb}MB"
                    if [ "$DRY_RUN" = "false" ]; then
                        # Docker没有直接清理日志的命令，但可以重启容器来清理
                        log_warning "容器日志过大，建议重启容器: $container"
                    fi
                fi
            fi
        done
    fi
}

# 生成清理报告
generate_report() {
    log_info "生成清理报告..."
    
    echo ""
    echo "📊 数据卷状态报告:"
    echo "=" * 50
    
    local volumes=("marketprism-storage-logs" "marketprism-collector-logs" "marketprism-nats-logs")
    
    for volume in "${volumes[@]}"; do
        local volume_path=$(get_volume_path "$volume")
        if [ -n "$volume_path" ]; then
            local size_mb=$(du -sm "$volume_path" 2>/dev/null | cut -f1 || echo "0")
            local file_count=$(find "$volume_path" -type f 2>/dev/null | wc -l)
            echo "  $volume: ${size_mb}MB, $file_count 个文件"
        else
            echo "  $volume: 不存在"
        fi
    done
    
    echo ""
    echo "🔧 清理配置:"
    echo "  - 日志保留天数: $LOG_RETENTION_DAYS"
    echo "  - 最大数据卷大小: ${MAX_LOG_SIZE_MB}MB"
    echo "  - 试运行模式: $DRY_RUN"
}

# 主函数
main() {
    case "${1:-cleanup}" in
        "cleanup")
            log_info "开始日志清理任务..."
            
            # 清理应用日志数据卷
            cleanup_volume_logs "marketprism-storage-logs"
            cleanup_volume_logs "marketprism-collector-logs"
            cleanup_volume_logs "marketprism-nats-logs"
            
            # 清理Docker容器日志
            cleanup_docker_logs
            
            # 生成报告
            generate_report
            
            log_success "日志清理任务完成"
            ;;
        "report")
            generate_report
            ;;
        "dry-run")
            export DRY_RUN=true
            log_info "试运行模式 - 不会实际删除文件"
            main cleanup
            ;;
        *)
            echo "用法: $0 {cleanup|report|dry-run}"
            echo "  cleanup  - 执行日志清理（默认）"
            echo "  report   - 仅生成状态报告"
            echo "  dry-run  - 试运行模式，不实际删除文件"
            echo ""
            echo "环境变量:"
            echo "  LOG_RETENTION_DAYS - 日志保留天数（默认：7）"
            echo "  MAX_LOG_SIZE_MB    - 单个数据卷最大大小MB（默认：1000）"
            echo "  DRY_RUN           - 试运行模式（默认：false）"
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"
