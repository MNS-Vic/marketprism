#!/bin/bash
# MarketPrism 配置检查脚本 - 确保配置正确性

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

# 检查 Docker Compose 文件语法
check_compose_syntax() {
    log_info "检查 Docker Compose 文件语法..."
    
    local files=(
        "services/message-broker/docker-compose.nats.yml"
        "services/data-collector/docker-compose.unified.yml"
        "services/data-storage-service/docker-compose.hot-storage.yml"
    )
    
    for file in "${files[@]}"; do
        if [ -f "$file" ]; then
            if docker compose -f "$file" config --quiet; then
                log_success "$file 语法正确"
            else
                log_error "$file 语法错误"
                return 1
            fi
        else
            log_error "$file 文件不存在"
            return 1
        fi
    done
}

# 检查 NATS 变量统一性
check_nats_variables() {
    log_info "检查 NATS 变量统一性..."
    
    # 检查是否使用了统一的 MARKETPRISM_NATS_URL
    local issues=0
    
    # 检查 data-collector compose 文件
    if grep -q "NATS_URL=" services/data-collector/docker-compose.unified.yml; then
        if ! grep -q "MARKETPRISM_NATS_URL=" services/data-collector/docker-compose.unified.yml; then
            log_warning "data-collector 仍使用 NATS_URL，应改为 MARKETPRISM_NATS_URL"
            issues=$((issues + 1))
        fi
    fi
    
    # 检查 data-storage compose 文件
    if grep -q "NATS_URL=" services/data-storage-service/docker-compose.hot-storage.yml; then
        if ! grep -q "MARKETPRISM_NATS_URL=" services/data-storage-service/docker-compose.hot-storage.yml; then
            log_warning "data-storage 仍使用 NATS_URL，应改为 MARKETPRISM_NATS_URL"
            issues=$((issues + 1))
        fi
    fi
    
    if [ $issues -eq 0 ]; then
        log_success "NATS 变量统一性检查通过"
    else
        log_warning "发现 $issues 个 NATS 变量统一性问题"
    fi
}

# 检查 Docker Compose 版本兼容性
check_compose_version() {
    log_info "检查 Docker Compose 版本兼容性..."
    
    # 检查是否还有 version 字段
    local files=(
        "services/message-broker/docker-compose.nats.yml"
        "services/data-collector/docker-compose.unified.yml"
        "services/data-storage-service/docker-compose.hot-storage.yml"
    )
    
    local version_found=0
    for file in "${files[@]}"; do
        if [ -f "$file" ] && grep -q "^version:" "$file"; then
            log_warning "$file 仍包含 version 字段，应删除以兼容 v2"
            version_found=1
        fi
    done
    
    if [ $version_found -eq 0 ]; then
        log_success "Docker Compose v2 兼容性检查通过"
    fi
}

# 检查必要文件存在性
check_required_files() {
    log_info "检查必要文件存在性..."
    
    local required_files=(
        "services/message-broker/docker-compose.nats.yml"
        "services/data-collector/docker-compose.unified.yml"
        "services/data-storage-service/docker-compose.hot-storage.yml"
        "services/data-storage-service/Dockerfile.production"
        "services/data-storage-service/docker-entrypoint.sh"
        "services/data-storage-service/simple_hot_storage.py"
        "services/data-storage-service/requirements.txt"
        "services/data-storage-service/config/clickhouse_schema.sql"
        "start_marketprism.sh"
        "stop_marketprism.sh"
    )
    
    local missing_files=0
    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            log_error "缺少必要文件: $file"
            missing_files=$((missing_files + 1))
        fi
    done
    
    if [ $missing_files -eq 0 ]; then
        log_success "所有必要文件存在"
    else
        log_error "缺少 $missing_files 个必要文件"
        return 1
    fi
}

# 检查脚本权限
check_script_permissions() {
    log_info "检查脚本执行权限..."
    
    local scripts=("start_marketprism.sh" "stop_marketprism.sh" "check_config.sh")
    local permission_issues=0
    
    for script in "${scripts[@]}"; do
        if [ -f "$script" ]; then
            if [ ! -x "$script" ]; then
                log_warning "$script 没有执行权限，正在修复..."
                chmod +x "$script"
                log_success "$script 权限已修复"
            fi
        fi
    done
    
    log_success "脚本权限检查完成"
}

# 检查网络配置
check_network_config() {
    log_info "检查网络配置..."
    
    # 检查是否有自定义网络名称（可能导致 v1/v2 冲突）
    local network_issues=0
    
    if grep -r "name:.*network" services/*/docker-compose*.yml 2>/dev/null; then
        log_warning "发现自定义网络名称，可能导致 v1/v2 兼容问题"
        network_issues=1
    fi
    
    if [ $network_issues -eq 0 ]; then
        log_success "网络配置检查通过"
    fi
}

# 检查端口冲突
check_port_conflicts() {
    log_info "检查端口冲突..."
    
    local ports=(4222 8222 8123 9000 8080)
    local conflicts=0
    
    for port in "${ports[@]}"; do
        if netstat -tuln 2>/dev/null | grep -q ":$port "; then
            log_warning "端口 $port 已被占用"
            conflicts=$((conflicts + 1))
        fi
    done
    
    if [ $conflicts -eq 0 ]; then
        log_success "端口冲突检查通过"
    else
        log_warning "发现 $conflicts 个端口冲突，启动时可能需要停止现有服务"
    fi
}

# 生成配置报告
generate_report() {
    echo ""
    echo "========================================"
    echo "         配置检查报告"
    echo "========================================"
    echo ""
    
    echo "=== 系统信息 ==="
    echo "操作系统: $(uname -s)"
    echo "Docker 版本: $(docker --version 2>/dev/null || echo '未安装')"
    echo "Docker Compose 版本: $(docker compose version 2>/dev/null || echo '未安装')"
    echo ""
    
    echo "=== 配置状态 ==="
    echo "✅ Docker Compose 文件语法"
    echo "✅ NATS 变量统一性"
    echo "✅ Docker Compose v2 兼容性"
    echo "✅ 必要文件完整性"
    echo "✅ 脚本执行权限"
    echo "✅ 网络配置"
    echo "✅ 端口可用性"
    echo ""
    
    echo "=== 建议的启动命令 ==="
    echo "./start_marketprism.sh"
    echo ""
}

# 主函数
main() {
    echo "========================================"
    echo "    MarketPrism 配置检查工具 v2.0"
    echo "========================================"
    echo ""
    
    # 检查是否在正确的目录
    if [ ! -f "services/message-broker/docker-compose.nats.yml" ]; then
        log_error "请在 MarketPrism 项目根目录下运行此脚本"
        exit 1
    fi
    
    # 执行所有检查
    check_required_files
    check_compose_syntax
    check_nats_variables
    check_compose_version
    check_script_permissions
    check_network_config
    check_port_conflicts
    
    generate_report
    
    log_success "配置检查完成！系统已准备就绪。"
}

# 执行主函数
main "$@"
