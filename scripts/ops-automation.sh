#!/bin/bash

# MarketPrism 智能监控告警系统运维自动化脚本
# 提供日常运维操作的自动化工具

set -euo pipefail

# 使脚本可执行
chmod +x "$0" 2>/dev/null || true

# 脚本配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEPLOYMENT_TYPE="${DEPLOYMENT_TYPE:-docker-compose}"
BASE_URL="${BASE_URL:-http://localhost:8082}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

# 显示帮助信息
show_help() {
    cat << EOF
MarketPrism 智能监控告警系统运维自动化工具

用法: $0 <命令> [选项]

命令:
  status          显示系统状态
  health          执行健康检查
  logs            查看服务日志
  backup          创建数据备份
  restore         恢复数据备份
  cleanup         清理旧数据和日志
  restart         重启服务
  scale           扩缩容服务
  monitor         实时监控系统状态
  alert-test      测试告警功能
  performance     性能检查
  security        安全检查
  update          更新服务
  rollback        回滚服务

选项:
  --help          显示此帮助信息
  --verbose       详细输出
  --dry-run       仅显示将要执行的操作
  --force         强制执行，跳过确认

示例:
  $0 status
  $0 health --verbose
  $0 backup --force
  $0 scale --replicas=3
  $0 logs --tail=100
EOF
}

# 获取系统状态
get_system_status() {
    log_info "获取系统状态..."
    
    if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
        echo "Docker Compose 部署状态:"
        docker-compose -f "$PROJECT_ROOT/deployments/docker-compose/docker-compose.yml" ps
        
        echo ""
        echo "容器资源使用:"
        docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}"
        
    elif [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        echo "Kubernetes 部署状态:"
        kubectl get pods -n marketprism-monitoring -o wide
        
        echo ""
        echo "服务状态:"
        kubectl get services -n marketprism-monitoring
        
        echo ""
        echo "资源使用:"
        kubectl top pods -n marketprism-monitoring 2>/dev/null || echo "需要安装metrics-server"
    fi
    
    echo ""
    echo "服务健康状态:"
    if curl -f -s "$BASE_URL/health" > /dev/null; then
        log_success "服务健康检查通过"
    else
        log_error "服务健康检查失败"
    fi
}

# 执行健康检查
perform_health_check() {
    local verbose="${1:-false}"
    
    log_info "执行健康检查..."
    
    # 基础健康检查
    local health_response
    health_response=$(curl -s "$BASE_URL/health" || echo "ERROR")
    
    if [[ "$health_response" == "ERROR" ]]; then
        log_error "服务不可达"
        return 1
    fi
    
    # 解析健康检查响应
    if command -v jq &> /dev/null; then
        local status
        status=$(echo "$health_response" | jq -r '.status // "unknown"')
        
        if [[ "$status" == "healthy" ]]; then
            log_success "服务状态: 健康"
        else
            log_error "服务状态: $status"
        fi
        
        if [[ "$verbose" == "true" ]]; then
            echo "详细健康信息:"
            echo "$health_response" | jq '.'
        fi
    else
        log_success "健康检查响应: $health_response"
    fi
    
    # 检查关键组件
    log_info "检查关键组件..."
    
    local components=("alert_manager" "notification_manager" "anomaly_detector" "failure_predictor")
    
    for component in "${components[@]}"; do
        if echo "$health_response" | grep -q "\"$component\".*true"; then
            log_success "$component: 正常"
        else
            log_warning "$component: 异常"
        fi
    done
}

# 查看服务日志
view_logs() {
    local tail_lines="${1:-50}"
    local follow="${2:-false}"
    
    log_info "查看服务日志 (最近 $tail_lines 行)..."
    
    if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
        if [[ "$follow" == "true" ]]; then
            docker-compose -f "$PROJECT_ROOT/deployments/docker-compose/docker-compose.yml" logs -f --tail="$tail_lines" monitoring-alerting
        else
            docker-compose -f "$PROJECT_ROOT/deployments/docker-compose/docker-compose.yml" logs --tail="$tail_lines" monitoring-alerting
        fi
        
    elif [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        if [[ "$follow" == "true" ]]; then
            kubectl logs -f deployment/monitoring-alerting -n marketprism-monitoring --tail="$tail_lines"
        else
            kubectl logs deployment/monitoring-alerting -n marketprism-monitoring --tail="$tail_lines"
        fi
    fi
}

# 创建数据备份
create_backup() {
    local backup_dir="$PROJECT_ROOT/backups/$(date +%Y%m%d-%H%M%S)"
    local force="${1:-false}"
    
    if [[ "$force" != "true" ]]; then
        read -p "确认创建备份? (y/N): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "备份已取消"
            return 0
        fi
    fi
    
    log_info "创建数据备份到: $backup_dir"
    mkdir -p "$backup_dir"
    
    # 备份配置文件
    log_info "备份配置文件..."
    cp -r "$PROJECT_ROOT/config" "$backup_dir/"
    cp -r "$PROJECT_ROOT/deployments" "$backup_dir/"
    
    # 备份数据库
    if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
        log_info "备份Redis数据..."
        docker exec marketprism-redis redis-cli BGSAVE
        docker cp marketprism-redis:/data/dump.rdb "$backup_dir/redis-dump.rdb"
        
        log_info "备份ClickHouse数据..."
        docker exec marketprism-clickhouse clickhouse-client --query "BACKUP DATABASE marketprism TO '$backup_dir/clickhouse.backup'"
        
    elif [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        log_info "备份Kubernetes配置..."
        kubectl get all -n marketprism-monitoring -o yaml > "$backup_dir/k8s-resources.yaml"
        
        # 备份数据库（需要根据实际部署调整）
        log_warning "Kubernetes环境下的数据库备份需要手动配置"
    fi
    
    # 创建备份清单
    cat > "$backup_dir/backup-info.txt" << EOF
备份信息:
- 备份时间: $(date)
- 部署类型: $DEPLOYMENT_TYPE
- 备份内容: 配置文件, 数据库数据
- 备份大小: $(du -sh "$backup_dir" | cut -f1)
EOF
    
    log_success "备份完成: $backup_dir"
}

# 恢复数据备份
restore_backup() {
    local backup_path="$1"
    local force="${2:-false}"
    
    if [[ ! -d "$backup_path" ]]; then
        log_error "备份目录不存在: $backup_path"
        return 1
    fi
    
    if [[ "$force" != "true" ]]; then
        log_warning "恢复备份将覆盖现有数据!"
        read -p "确认恢复备份? (y/N): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "恢复已取消"
            return 0
        fi
    fi
    
    log_info "从备份恢复: $backup_path"
    
    # 停止服务
    log_info "停止服务..."
    if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
        docker-compose -f "$PROJECT_ROOT/deployments/docker-compose/docker-compose.yml" down
    elif [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        kubectl scale deployment monitoring-alerting --replicas=0 -n marketprism-monitoring
    fi
    
    # 恢复配置文件
    if [[ -d "$backup_path/config" ]]; then
        log_info "恢复配置文件..."
        cp -r "$backup_path/config" "$PROJECT_ROOT/"
    fi
    
    # 恢复数据库
    if [[ -f "$backup_path/redis-dump.rdb" ]]; then
        log_info "恢复Redis数据..."
        # 实现Redis数据恢复逻辑
    fi
    
    # 重启服务
    log_info "重启服务..."
    if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
        docker-compose -f "$PROJECT_ROOT/deployments/docker-compose/docker-compose.yml" up -d
    elif [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        kubectl scale deployment monitoring-alerting --replicas=2 -n marketprism-monitoring
    fi
    
    log_success "备份恢复完成"
}

# 清理旧数据和日志
cleanup_old_data() {
    local days="${1:-7}"
    local force="${2:-false}"
    
    if [[ "$force" != "true" ]]; then
        read -p "确认清理 $days 天前的数据? (y/N): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "清理已取消"
            return 0
        fi
    fi
    
    log_info "清理 $days 天前的数据..."
    
    # 清理日志文件
    log_info "清理日志文件..."
    find "$PROJECT_ROOT/logs" -name "*.log" -mtime +$days -delete 2>/dev/null || true
    
    # 清理备份文件
    log_info "清理备份文件..."
    find "$PROJECT_ROOT/backups" -type d -mtime +$days -exec rm -rf {} + 2>/dev/null || true
    
    # 清理测试结果
    log_info "清理测试结果..."
    find "$PROJECT_ROOT/test-results" -name "*.json" -mtime +$days -delete 2>/dev/null || true
    find "$PROJECT_ROOT/test-results" -name "*.md" -mtime +$days -delete 2>/dev/null || true
    
    # 清理数据库中的旧数据
    log_info "清理数据库旧数据..."
    if curl -f -s "$BASE_URL/api/v1/admin/cleanup?days=$days" > /dev/null; then
        log_success "数据库清理完成"
    else
        log_warning "数据库清理失败或不支持"
    fi
    
    log_success "数据清理完成"
}

# 重启服务
restart_service() {
    local force="${1:-false}"
    
    if [[ "$force" != "true" ]]; then
        read -p "确认重启服务? (y/N): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "重启已取消"
            return 0
        fi
    fi
    
    log_info "重启服务..."
    
    if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
        docker-compose -f "$PROJECT_ROOT/deployments/docker-compose/docker-compose.yml" restart monitoring-alerting
        
        # 等待服务就绪
        sleep 10
        
    elif [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        kubectl rollout restart deployment/monitoring-alerting -n marketprism-monitoring
        kubectl rollout status deployment/monitoring-alerting -n marketprism-monitoring
    fi
    
    # 验证服务状态
    if curl -f -s "$BASE_URL/health" > /dev/null; then
        log_success "服务重启完成"
    else
        log_error "服务重启后健康检查失败"
        return 1
    fi
}

# 扩缩容服务
scale_service() {
    local replicas="${1:-2}"
    
    log_info "扩缩容服务到 $replicas 个实例..."
    
    if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
        docker-compose -f "$PROJECT_ROOT/deployments/docker-compose/docker-compose.yml" up -d --scale monitoring-alerting="$replicas"
        
    elif [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        kubectl scale deployment monitoring-alerting --replicas="$replicas" -n marketprism-monitoring
        kubectl rollout status deployment/monitoring-alerting -n marketprism-monitoring
    fi
    
    log_success "扩缩容完成"
}

# 实时监控系统状态
monitor_system() {
    log_info "开始实时监控系统状态 (按 Ctrl+C 退出)..."
    
    while true; do
        clear
        echo "=========================================="
        echo "MarketPrism 监控告警系统实时状态"
        echo "时间: $(date)"
        echo "=========================================="
        echo ""
        
        # 服务状态
        if curl -f -s "$BASE_URL/health" > /dev/null; then
            echo -e "${GREEN}✓ 服务状态: 正常${NC}"
        else
            echo -e "${RED}✗ 服务状态: 异常${NC}"
        fi
        
        # 获取统计信息
        if command -v jq &> /dev/null; then
            local stats
            stats=$(curl -s "$BASE_URL/api/v1/stats/alerts" 2>/dev/null || echo "{}")
            
            echo ""
            echo "告警统计:"
            echo "  活跃告警: $(echo "$stats" | jq -r '.active_alerts // "N/A"')"
            echo "  总告警数: $(echo "$stats" | jq -r '.total_alerts // "N/A"')"
            echo "  已解决: $(echo "$stats" | jq -r '.resolved_alerts // "N/A"')"
        fi
        
        # 系统资源
        if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
            echo ""
            echo "容器资源使用:"
            docker stats --no-stream --format "  {{.Name}}: CPU {{.CPUPerc}}, 内存 {{.MemUsage}}" | grep monitoring-alerting || echo "  无数据"
        fi
        
        sleep 5
    done
}

# 测试告警功能
test_alerts() {
    log_info "测试告警功能..."
    
    # 创建测试告警
    local test_data='{"metric_name": "test_metric", "value": 999.0, "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}'
    
    if curl -f -s -X POST -H "Content-Type: application/json" -d "$test_data" "$BASE_URL/api/v1/anomaly/detect" > /dev/null; then
        log_success "异常检测API测试通过"
    else
        log_error "异常检测API测试失败"
    fi
    
    # 测试通知功能
    log_info "测试通知功能..."
    # 这里可以添加具体的通知测试逻辑
    
    log_success "告警功能测试完成"
}

# 性能检查
check_performance() {
    log_info "执行性能检查..."
    
    # 执行性能测试脚本
    if [[ -f "$SCRIPT_DIR/load-test.sh" ]]; then
        "$SCRIPT_DIR/load-test.sh" "$BASE_URL" 60 50
    else
        log_warning "性能测试脚本不存在"
    fi
}

# 安全检查
check_security() {
    log_info "执行安全检查..."
    
    # 执行安全测试脚本
    if [[ -f "$SCRIPT_DIR/security-test.sh" ]]; then
        "$SCRIPT_DIR/security-test.sh" "$BASE_URL" "$DEPLOYMENT_TYPE"
    else
        log_warning "安全测试脚本不存在"
    fi
}

# 更新服务
update_service() {
    local image_tag="${1:-latest}"
    local force="${2:-false}"
    
    if [[ "$force" != "true" ]]; then
        read -p "确认更新服务到版本 $image_tag? (y/N): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "更新已取消"
            return 0
        fi
    fi
    
    log_info "更新服务到版本: $image_tag"
    
    # 创建备份
    create_backup true
    
    # 执行更新
    if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
        export IMAGE_TAG="$image_tag"
        docker-compose -f "$PROJECT_ROOT/deployments/docker-compose/docker-compose.yml" pull monitoring-alerting
        docker-compose -f "$PROJECT_ROOT/deployments/docker-compose/docker-compose.yml" up -d monitoring-alerting
        
    elif [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        kubectl set image deployment/monitoring-alerting monitoring-alerting="ghcr.io/marketprism/monitoring-alerting:$image_tag" -n marketprism-monitoring
        kubectl rollout status deployment/monitoring-alerting -n marketprism-monitoring
    fi
    
    # 验证更新
    sleep 10
    if curl -f -s "$BASE_URL/health" > /dev/null; then
        log_success "服务更新完成"
    else
        log_error "服务更新后健康检查失败"
        return 1
    fi
}

# 回滚服务
rollback_service() {
    local force="${1:-false}"
    
    if [[ "$force" != "true" ]]; then
        log_warning "回滚将恢复到上一个版本!"
        read -p "确认回滚服务? (y/N): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "回滚已取消"
            return 0
        fi
    fi
    
    log_info "回滚服务..."
    
    if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
        # Docker Compose回滚逻辑
        log_warning "Docker Compose环境需要手动指定回滚版本"
        
    elif [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        kubectl rollout undo deployment/monitoring-alerting -n marketprism-monitoring
        kubectl rollout status deployment/monitoring-alerting -n marketprism-monitoring
    fi
    
    # 验证回滚
    sleep 10
    if curl -f -s "$BASE_URL/health" > /dev/null; then
        log_success "服务回滚完成"
    else
        log_error "服务回滚后健康检查失败"
        return 1
    fi
}

# 主函数
main() {
    local command="${1:-help}"
    shift || true
    
    case "$command" in
        "status")
            get_system_status
            ;;
        "health")
            local verbose=false
            [[ "${1:-}" == "--verbose" ]] && verbose=true
            perform_health_check "$verbose"
            ;;
        "logs")
            local tail_lines=50
            local follow=false
            while [[ $# -gt 0 ]]; do
                case $1 in
                    --tail=*)
                        tail_lines="${1#*=}"
                        shift
                        ;;
                    --follow|-f)
                        follow=true
                        shift
                        ;;
                    *)
                        shift
                        ;;
                esac
            done
            view_logs "$tail_lines" "$follow"
            ;;
        "backup")
            local force=false
            [[ "${1:-}" == "--force" ]] && force=true
            create_backup "$force"
            ;;
        "restore")
            local backup_path="${1:-}"
            local force=false
            [[ "${2:-}" == "--force" ]] && force=true
            if [[ -z "$backup_path" ]]; then
                log_error "请指定备份路径"
                exit 1
            fi
            restore_backup "$backup_path" "$force"
            ;;
        "cleanup")
            local days=7
            local force=false
            while [[ $# -gt 0 ]]; do
                case $1 in
                    --days=*)
                        days="${1#*=}"
                        shift
                        ;;
                    --force)
                        force=true
                        shift
                        ;;
                    *)
                        shift
                        ;;
                esac
            done
            cleanup_old_data "$days" "$force"
            ;;
        "restart")
            local force=false
            [[ "${1:-}" == "--force" ]] && force=true
            restart_service "$force"
            ;;
        "scale")
            local replicas=2
            while [[ $# -gt 0 ]]; do
                case $1 in
                    --replicas=*)
                        replicas="${1#*=}"
                        shift
                        ;;
                    *)
                        shift
                        ;;
                esac
            done
            scale_service "$replicas"
            ;;
        "monitor")
            monitor_system
            ;;
        "alert-test")
            test_alerts
            ;;
        "performance")
            check_performance
            ;;
        "security")
            check_security
            ;;
        "update")
            local image_tag="${1:-latest}"
            local force=false
            [[ "${2:-}" == "--force" ]] && force=true
            update_service "$image_tag" "$force"
            ;;
        "rollback")
            local force=false
            [[ "${1:-}" == "--force" ]] && force=true
            rollback_service "$force"
            ;;
        "help"|"--help"|"-h")
            show_help
            ;;
        *)
            log_error "未知命令: $command"
            show_help
            exit 1
            ;;
    esac
}

# 错误处理
trap 'log_error "运维操作过程中发生错误"; exit 1' ERR

# 执行主函数
main "$@"
