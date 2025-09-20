#!/bin/bash

# MarketPrism 智能监控告警系统部署脚本
# 支持Docker Compose和Kubernetes部署方式

set -euo pipefail

# 脚本配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEPLOYMENT_TYPE="${1:-docker-compose}"
ENVIRONMENT="${2:-production}"
IMAGE_TAG="${3:-latest}"

# 颜色输出
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

# 显示帮助信息
show_help() {
    cat << EOF
MarketPrism 智能监控告警系统部署脚本

用法: $0 [部署类型] [环境] [镜像标签]

参数:
  部署类型    docker-compose | kubernetes (默认: docker-compose)
  环境        development | staging | production (默认: production)
  镜像标签    Docker镜像标签 (默认: latest)

示例:
  $0 docker-compose production latest
  $0 kubernetes staging v1.0.0
  $0 --help

选项:
  --help      显示此帮助信息
  --dry-run   仅显示将要执行的命令，不实际执行
  --force     强制部署，跳过确认步骤
  --backup    部署前创建备份
EOF
}

# 检查依赖
check_dependencies() {
    log_info "检查部署依赖..."
    
    local missing_deps=()
    
    if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
        if ! command -v docker &> /dev/null; then
            missing_deps+=("docker")
        fi
        if ! docker compose version >/dev/null 2>&1; then
            missing_deps+=("docker-compose-plugin (docker compose)")
        fi
    elif [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        if ! command -v kubectl &> /dev/null; then
            missing_deps+=("kubectl")
        fi
        if ! command -v helm &> /dev/null; then
            log_warning "Helm未安装，将使用kubectl进行部署"
        fi
    fi
    
    if ! command -v curl &> /dev/null; then
        missing_deps+=("curl")
    fi
    
    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        log_error "缺少以下依赖: ${missing_deps[*]}"
        log_error "请安装缺少的依赖后重试"
        exit 1
    fi
    
    log_success "依赖检查通过"
}

# 验证环境配置
validate_environment() {
    log_info "验证环境配置..."
    
    if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
        local env_file="$PROJECT_ROOT/deployments/docker-compose/.env"
        
        if [[ ! -f "$env_file" ]]; then
            log_error "环境配置文件不存在: $env_file"
            log_info "请复制 .env.example 为 .env 并配置相应参数"
            exit 1
        fi
        
        # 检查必需的环境变量
        local required_vars=("JWT_SECRET" "SMTP_USERNAME" "SMTP_PASSWORD")
        local missing_vars=()
        
        source "$env_file"
        
        for var in "${required_vars[@]}"; do
            if [[ -z "${!var:-}" ]]; then
                missing_vars+=("$var")
            fi
        done
        
        if [[ ${#missing_vars[@]} -gt 0 ]]; then
            log_error "缺少必需的环境变量: ${missing_vars[*]}"
            log_error "请在 $env_file 中配置这些变量"
            exit 1
        fi
        
    elif [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        # 检查kubectl连接
        if ! kubectl cluster-info &> /dev/null; then
            log_error "无法连接到Kubernetes集群"
            log_error "请检查kubectl配置"
            exit 1
        fi
        
        # 检查命名空间
        if ! kubectl get namespace marketprism-monitoring &> /dev/null; then
            log_warning "命名空间 marketprism-monitoring 不存在，将自动创建"
        fi
    fi
    
    log_success "环境配置验证通过"
}

# 构建Docker镜像
build_image() {
    if [[ "$IMAGE_TAG" == "latest" ]] || [[ "$IMAGE_TAG" =~ ^local- ]]; then
        log_info "构建Docker镜像..."
        
        cd "$PROJECT_ROOT"
        
        docker build \
            -f services/monitoring-alerting-service/Dockerfile \
            -t "ghcr.io/marketprism/monitoring-alerting:$IMAGE_TAG" \
            .
        
        log_success "Docker镜像构建完成"
    else
        log_info "使用预构建镜像: ghcr.io/marketprism/monitoring-alerting:$IMAGE_TAG"
    fi
}

# Docker Compose部署
deploy_docker_compose() {
    log_info "使用Docker Compose部署..."
    
    cd "$PROJECT_ROOT/deployments/docker-compose"
    
    # 设置环境变量
    export IMAGE_TAG="$IMAGE_TAG"
    export ENVIRONMENT="$ENVIRONMENT"
    
    # 创建必要的目录
    mkdir -p logs config/prometheus config/grafana ssl
    
    # 停止现有服务
    if docker compose ps | grep -q "Up"; then
        log_info "停止现有服务..."
        docker compose down
    fi
    
    # 启动服务
    log_info "启动服务..."
    docker compose up -d
    
    # 等待服务就绪
    log_info "等待服务就绪..."
    wait_for_service "http://localhost:8082/health" 120
    
    log_success "Docker Compose部署完成"
    
    # 显示服务状态
    docker compose ps
    
    # 显示访问地址
    echo ""
    log_info "服务访问地址:"
    echo "  监控告警服务: http://localhost:8082"
    echo "  Grafana:     http://localhost:3000"
    echo "  Prometheus:  http://localhost:9090"
}

# Kubernetes部署
deploy_kubernetes() {
    log_info "使用Kubernetes部署..."
    
    cd "$PROJECT_ROOT/deployments/kubernetes"
    
    # 创建命名空间
    kubectl apply -f namespace.yaml
    
    # 应用ConfigMap和Secrets
    log_info "应用配置..."
    envsubst < configmap.yaml | kubectl apply -f -
    
    # 注意: 在生产环境中，Secrets应该通过安全的方式管理
    log_warning "请确保已正确配置Secrets"
    kubectl apply -f secrets.yaml
    
    # 应用ServiceAccount和RBAC
    if [[ -f "rbac.yaml" ]]; then
        kubectl apply -f rbac.yaml
    fi
    
    # 部署应用
    log_info "部署应用..."
    IMAGE_TAG="$IMAGE_TAG" envsubst < deployment.yaml | kubectl apply -f -
    
    # 应用Service
    kubectl apply -f service.yaml
    
    # 应用Ingress (如果存在)
    if [[ -f "ingress.yaml" ]]; then
        kubectl apply -f ingress.yaml
    fi
    
    # 等待部署完成
    log_info "等待部署完成..."
    kubectl rollout status deployment/monitoring-alerting -n marketprism-monitoring --timeout=300s
    
    # 等待Pod就绪
    kubectl wait --for=condition=ready pod -l app=monitoring-alerting -n marketprism-monitoring --timeout=300s
    
    log_success "Kubernetes部署完成"
    
    # 显示部署状态
    kubectl get pods -n marketprism-monitoring
    kubectl get services -n marketprism-monitoring
}

# 等待服务就绪
wait_for_service() {
    local url="$1"
    local timeout="${2:-60}"
    local count=0
    
    log_info "等待服务就绪: $url"
    
    while [[ $count -lt $timeout ]]; do
        if curl -f -s "$url" > /dev/null 2>&1; then
            log_success "服务已就绪"
            return 0
        fi
        
        echo -n "."
        sleep 1
        ((count++))
    done
    
    echo ""
    log_error "服务在 $timeout 秒内未就绪"
    return 1
}

# 运行部署后测试
run_post_deploy_tests() {
    log_info "运行部署后测试..."
    
    local base_url
    
    if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
        base_url="http://localhost:8082"
    else
        # 获取Kubernetes服务地址
        local service_ip
        service_ip=$(kubectl get svc monitoring-alerting-service -n marketprism-monitoring -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
        
        if [[ -z "$service_ip" ]]; then
            # 使用NodePort或端口转发
            log_info "使用端口转发进行测试..."
            kubectl port-forward svc/monitoring-alerting-service 8082:8082 -n marketprism-monitoring &
            local port_forward_pid=$!
            sleep 5
            base_url="http://localhost:8082"
        else
            base_url="http://$service_ip:8082"
        fi
    fi
    
    # 健康检查
    if curl -f -s "$base_url/health" > /dev/null; then
        log_success "健康检查通过"
    else
        log_error "健康检查失败"
        return 1
    fi
    
    # 就绪检查
    if curl -f -s "$base_url/ready" > /dev/null; then
        log_success "就绪检查通过"
    else
        log_error "就绪检查失败"
        return 1
    fi
    
    # API测试
    if curl -f -s "$base_url/api/v1/alerts" > /dev/null; then
        log_success "API测试通过"
    else
        log_error "API测试失败"
        return 1
    fi
    
    # 清理端口转发
    if [[ -n "${port_forward_pid:-}" ]]; then
        kill $port_forward_pid 2>/dev/null || true
    fi
    
    log_success "部署后测试完成"
}

# 显示部署信息
show_deployment_info() {
    echo ""
    log_success "部署完成！"
    echo ""
    echo "部署信息:"
    echo "  部署类型: $DEPLOYMENT_TYPE"
    echo "  环境:     $ENVIRONMENT"
    echo "  镜像标签: $IMAGE_TAG"
    echo ""
    
    if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
        echo "服务访问地址:"
        echo "  监控告警服务: http://localhost:8082"
        echo "  健康检查:     http://localhost:8082/health"
        echo "  API文档:      http://localhost:8082/docs"
        echo "  Prometheus:   http://localhost:9090"
        echo "  Grafana:      http://localhost:3000 (admin/admin)"
        echo ""
        echo "管理命令:"
        echo "  查看日志:     docker compose logs -f monitoring-alerting"
        echo "  停止服务:     docker compose down"
        echo "  重启服务:     docker compose restart monitoring-alerting"
    else
        echo "Kubernetes资源:"
        echo "  命名空间:     marketprism-monitoring"
        echo "  部署:         monitoring-alerting"
        echo "  服务:         monitoring-alerting-service"
        echo ""
        echo "管理命令:"
        echo "  查看Pod:      kubectl get pods -n marketprism-monitoring"
        echo "  查看日志:     kubectl logs -f deployment/monitoring-alerting -n marketprism-monitoring"
        echo "  端口转发:     kubectl port-forward svc/monitoring-alerting-service 8082:8082 -n marketprism-monitoring"
    fi
}

# 主函数
main() {
    # 解析命令行参数
    case "${1:-}" in
        --help|-h)
            show_help
            exit 0
            ;;
        --dry-run)
            log_info "干运行模式，仅显示将要执行的操作"
            DRY_RUN=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --backup)
            BACKUP=true
            shift
            ;;
    esac
    
    # 验证部署类型
    if [[ "$DEPLOYMENT_TYPE" != "docker-compose" && "$DEPLOYMENT_TYPE" != "kubernetes" ]]; then
        log_error "不支持的部署类型: $DEPLOYMENT_TYPE"
        log_error "支持的类型: docker-compose, kubernetes"
        exit 1
    fi
    
    # 验证环境
    if [[ "$ENVIRONMENT" != "development" && "$ENVIRONMENT" != "staging" && "$ENVIRONMENT" != "production" ]]; then
        log_error "不支持的环境: $ENVIRONMENT"
        log_error "支持的环境: development, staging, production"
        exit 1
    fi
    
    log_info "开始部署 MarketPrism 智能监控告警系统"
    log_info "部署类型: $DEPLOYMENT_TYPE"
    log_info "环境: $ENVIRONMENT"
    log_info "镜像标签: $IMAGE_TAG"
    
    # 确认部署
    if [[ "${FORCE:-false}" != "true" ]]; then
        echo ""
        read -p "确认继续部署? (y/N): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "部署已取消"
            exit 0
        fi
    fi
    
    # 执行部署步骤
    check_dependencies
    validate_environment
    build_image
    
    if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
        deploy_docker_compose
    else
        deploy_kubernetes
    fi
    
    run_post_deploy_tests
    show_deployment_info
    
    log_success "部署完成！"
}

# 错误处理
trap 'log_error "部署过程中发生错误，请检查日志"; exit 1' ERR

# 执行主函数
main "$@"
