#!/bin/bash

# MarketPrism订单簿管理系统部署脚本
# 用于生产环境自动化部署

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置变量
DEPLOY_ENV=${DEPLOY_ENV:-production}
BACKUP_ENABLED=${BACKUP_ENABLED:-true}
HEALTH_CHECK_TIMEOUT=${HEALTH_CHECK_TIMEOUT:-300}
ROLLBACK_ON_FAILURE=${ROLLBACK_ON_FAILURE:-true}

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
}

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $(date '+%Y-%m-%d %H:%M:%S') $1"
}

# 错误处理
handle_error() {
    log_error "部署失败，错误发生在第 $1 行"
    if [ "$ROLLBACK_ON_FAILURE" = "true" ]; then
        log_warn "开始回滚..."
        rollback_deployment
    fi
    exit 1
}

trap 'handle_error $LINENO' ERR

# 预部署检查
pre_deployment_checks() {
    log_info "开始预部署检查..."
    
    # 检查系统资源
    log_info "检查系统资源..."
    local available_memory=$(free -m | awk 'NR==2{printf "%.1f", $7/1024}')
    local available_disk=$(df -h . | awk 'NR==2{print $4}' | sed 's/G//')
    
    if (( $(echo "$available_memory < 2.0" | bc -l) )); then
        log_error "可用内存不足 (${available_memory}GB)，建议至少2GB"
        exit 1
    fi
    
    if (( $(echo "$available_disk < 10" | bc -l) )); then
        log_error "可用磁盘空间不足 (${available_disk}GB)，建议至少10GB"
        exit 1
    fi
    
    # 检查Docker服务
    if ! systemctl is-active --quiet docker; then
        log_error "Docker服务未运行"
        exit 1
    fi
    
    # 检查配置文件
    if [ ! -f .env ]; then
        log_error ".env配置文件不存在"
        exit 1
    fi
    
    # 验证关键环境变量
    source .env
    local required_vars=(
        "BINANCE_API_KEY"
        "BINANCE_API_SECRET"
        "CLICKHOUSE_PASSWORD"
        "REDIS_PASSWORD"
    )
    
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            log_error "必需的环境变量 $var 未设置"
            exit 1
        fi
    done
    
    log_info "预部署检查完成"
}

# 备份当前部署
backup_current_deployment() {
    if [ "$BACKUP_ENABLED" = "true" ]; then
        log_info "备份当前部署..."
        
        local backup_dir="backups/$(date +%Y%m%d_%H%M%S)"
        mkdir -p "$backup_dir"
        
        # 备份配置文件
        cp .env "$backup_dir/"
        cp docker-compose.yml "$backup_dir/"
        
        # 备份数据库
        if docker-compose ps clickhouse | grep -q "Up"; then
            log_info "备份ClickHouse数据..."
            docker-compose exec -T clickhouse clickhouse-client --query "BACKUP DATABASE marketprism TO Disk('default', '$backup_dir/clickhouse_backup.sql')" || true
        fi
        
        # 备份日志
        if [ -d logs ]; then
            cp -r logs "$backup_dir/"
        fi
        
        log_info "备份完成: $backup_dir"
        echo "$backup_dir" > .last_backup
    fi
}

# 拉取最新代码
pull_latest_code() {
    log_info "拉取最新代码..."
    
    if [ -d .git ]; then
        git fetch origin
        git reset --hard origin/main
        log_info "代码更新完成"
    else
        log_warn "非Git仓库，跳过代码拉取"
    fi
}

# 构建和部署
build_and_deploy() {
    log_info "开始构建和部署..."
    
    # 停止现有服务
    log_info "停止现有服务..."
    docker-compose down --remove-orphans || true
    
    # 清理旧镜像
    log_info "清理旧镜像..."
    docker system prune -f || true
    
    # 构建新镜像
    log_info "构建应用镜像..."
    docker-compose build --no-cache
    
    # 启动基础服务
    log_info "启动基础服务..."
    docker-compose up -d nats clickhouse redis prometheus
    
    # 等待基础服务就绪
    log_info "等待基础服务就绪..."
    sleep 30
    
    # 启动应用服务
    log_info "启动订单簿管理系统..."
    docker-compose up -d orderbook-manager
    
    log_info "部署完成"
}

# 健康检查
health_check() {
    log_info "开始健康检查..."
    
    local start_time=$(date +%s)
    local timeout=$HEALTH_CHECK_TIMEOUT
    
    while true; do
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        
        if [ $elapsed -gt $timeout ]; then
            log_error "健康检查超时 (${timeout}秒)"
            return 1
        fi
        
        # 检查订单簿管理系统
        if curl -f -s http://localhost:8080/health >/dev/null 2>&1; then
            log_info "订单簿管理系统健康检查通过"
            break
        fi
        
        log_info "等待服务就绪... (${elapsed}/${timeout}秒)"
        sleep 10
    done
    
    # 检查其他服务
    local services=(
        "NATS:4222"
        "ClickHouse:8123"
        "Redis:6379"
        "Prometheus:9090"
    )
    
    for service in "${services[@]}"; do
        local name=$(echo $service | cut -d: -f1)
        local port=$(echo $service | cut -d: -f2)
        
        if curl -f -s "http://localhost:$port" >/dev/null 2>&1 || \
           curl -f -s "http://localhost:$port/ping" >/dev/null 2>&1; then
            log_info "$name 健康检查通过"
        else
            log_warn "$name 健康检查失败"
        fi
    done
    
    log_info "健康检查完成"
}

# 回滚部署
rollback_deployment() {
    log_warn "开始回滚部署..."
    
    if [ -f .last_backup ]; then
        local backup_dir=$(cat .last_backup)
        if [ -d "$backup_dir" ]; then
            log_info "恢复配置文件..."
            cp "$backup_dir/.env" .
            cp "$backup_dir/docker-compose.yml" .
            
            log_info "重新部署..."
            docker-compose down
            docker-compose up -d
            
            log_info "回滚完成"
        else
            log_error "备份目录不存在: $backup_dir"
        fi
    else
        log_error "没有找到备份信息"
    fi
}

# 部署后验证
post_deployment_verification() {
    log_info "开始部署后验证..."
    
    # 验证服务状态
    local failed_services=()
    
    if ! docker-compose ps orderbook-manager | grep -q "Up"; then
        failed_services+=("orderbook-manager")
    fi
    
    if ! docker-compose ps nats | grep -q "Up"; then
        failed_services+=("nats")
    fi
    
    if ! docker-compose ps clickhouse | grep -q "Up"; then
        failed_services+=("clickhouse")
    fi
    
    if [ ${#failed_services[@]} -gt 0 ]; then
        log_error "以下服务启动失败: ${failed_services[*]}"
        return 1
    fi
    
    # 验证API响应
    local api_response=$(curl -s http://localhost:8080/health || echo "failed")
    if [[ "$api_response" != *"healthy"* ]] && [[ "$api_response" != *"ok"* ]]; then
        log_error "API健康检查失败"
        return 1
    fi
    
    log_info "部署后验证完成"
}

# 显示部署信息
show_deployment_info() {
    log_info "部署信息:"
    echo ""
    echo "🚀 部署环境: $DEPLOY_ENV"
    echo "📅 部署时间: $(date)"
    echo "🔗 服务地址:"
    echo "  健康检查:   http://localhost:8080/health"
    echo "  指标监控:   http://localhost:8081/metrics"
    echo "  Grafana:    http://localhost:3000"
    echo "  Prometheus: http://localhost:9090"
    echo ""
    echo "📊 服务状态:"
    docker-compose ps
    echo ""
    echo "📋 查看日志: docker-compose logs -f orderbook-manager"
    echo "🛑 停止服务: docker-compose down"
    echo ""
}

# 显示帮助信息
show_help() {
    echo "🚀 MarketPrism订单簿管理系统部署脚本"
    echo "========================================"
    echo ""
    echo "用法:"
    echo "  ./deploy.sh [选项]"
    echo ""
    echo "选项:"
    echo "  -h, --help              显示此帮助信息"
    echo "  -e, --env ENV           设置部署环境 (development, staging, production)"
    echo "  --no-backup             跳过备份步骤"
    echo "  --no-rollback           部署失败时不自动回滚"
    echo "  --skip-health-check     跳过健康检查"
    echo "  --timeout SECONDS       设置健康检查超时时间 (默认: 300秒)"
    echo ""
    echo "环境变量:"
    echo "  DEPLOY_ENV              部署环境 (默认: production)"
    echo "  BACKUP_ENABLED          是否启用备份 (默认: true)"
    echo "  HEALTH_CHECK_TIMEOUT    健康检查超时时间 (默认: 300秒)"
    echo "  ROLLBACK_ON_FAILURE     失败时是否回滚 (默认: true)"
    echo ""
    echo "部署流程:"
    echo "  1. 预部署检查 (系统资源、Docker服务、配置文件)"
    echo "  2. 备份当前部署 (配置文件、数据库、日志)"
    echo "  3. 拉取最新代码 (Git仓库更新)"
    echo "  4. 构建和部署 (Docker镜像构建、服务启动)"
    echo "  5. 健康检查 (服务状态验证)"
    echo "  6. 部署后验证 (功能测试)"
    echo "  7. 显示部署信息"
    echo ""
    echo "示例:"
    echo "  ./deploy.sh                           # 生产环境部署"
    echo "  ./deploy.sh --env staging             # 预发布环境部署"
    echo "  ./deploy.sh --no-backup               # 跳过备份的快速部署"
    echo "  ./deploy.sh --timeout 600             # 设置10分钟健康检查超时"
    echo ""
    echo "注意事项:"
    echo "  • 确保.env文件已正确配置"
    echo "  • 生产环境部署前建议先在staging环境测试"
    echo "  • 部署过程中会自动停止现有服务"
    echo "  • 失败时会自动回滚到上一个版本"
    echo ""
}

# 主函数
main() {
    local deploy_env="$DEPLOY_ENV"
    local backup_enabled="$BACKUP_ENABLED"
    local health_check_timeout="$HEALTH_CHECK_TIMEOUT"
    local rollback_on_failure="$ROLLBACK_ON_FAILURE"
    local skip_health_check=false

    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -e|--env)
                deploy_env="$2"
                shift 2
                ;;
            --no-backup)
                backup_enabled=false
                shift
                ;;
            --no-rollback)
                rollback_on_failure=false
                shift
                ;;
            --skip-health-check)
                skip_health_check=true
                shift
                ;;
            --timeout)
                health_check_timeout="$2"
                shift 2
                ;;
            *)
                log_error "未知选项: $1"
                echo "使用 --help 查看帮助信息"
                exit 1
                ;;
        esac
    done

    # 设置环境变量
    export DEPLOY_ENV="${deploy_env:-production}"
    export BACKUP_ENABLED="${backup_enabled:-true}"
    export HEALTH_CHECK_TIMEOUT="${health_check_timeout:-300}"
    export ROLLBACK_ON_FAILURE="${rollback_on_failure:-true}"

    echo "🚀 MarketPrism订单簿管理系统部署脚本"
    echo "========================================"
    echo "部署环境: $DEPLOY_ENV"
    echo "备份启用: $BACKUP_ENABLED"
    echo "健康检查超时: ${HEALTH_CHECK_TIMEOUT}秒"
    echo "失败回滚: $ROLLBACK_ON_FAILURE"
    echo "========================================"

    pre_deployment_checks

    if [ "$BACKUP_ENABLED" = "true" ]; then
        backup_current_deployment
    fi

    pull_latest_code
    build_and_deploy

    if [ "$skip_health_check" = false ]; then
        health_check
    fi

    post_deployment_verification
    show_deployment_info

    log_info "🎉 MarketPrism订单簿管理系统部署成功！"
}

# 执行主函数
main "$@"
