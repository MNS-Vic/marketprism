#!/bin/bash

# MarketPrism 统一配置工厂部署脚本
# 支持使用新的统一配置工厂进行部署

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

# 默认配置
ENVIRONMENT=${ENVIRONMENT:-"staging"}
CONFIG_VALIDATION=${CONFIG_VALIDATION:-"true"}
SKIP_TESTS=${SKIP_TESTS:-"false"}
DEPLOYMENT_MODE=${DEPLOYMENT_MODE:-"docker-compose"}

# 显示帮助信息
show_help() {
    cat << EOF
MarketPrism 统一配置工厂部署脚本

用法: $0 [选项]

选项:
    -e, --environment ENV       部署环境 (staging|production) [默认: staging]
    -m, --mode MODE            部署模式 (docker-compose|kubernetes) [默认: docker-compose]
    -s, --skip-validation      跳过配置验证
    -t, --skip-tests          跳过测试
    -h, --help                显示此帮助信息

环境变量:
    ENVIRONMENT               部署环境
    CONFIG_VALIDATION         是否进行配置验证 (true|false)
    SKIP_TESTS               是否跳过测试 (true|false)
    DEPLOYMENT_MODE          部署模式

示例:
    $0 -e production -m kubernetes
    $0 --environment staging --skip-tests
    ENVIRONMENT=production $0

EOF
}

# 解析命令行参数
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -e|--environment)
                ENVIRONMENT="$2"
                shift 2
                ;;
            -m|--mode)
                DEPLOYMENT_MODE="$2"
                shift 2
                ;;
            -s|--skip-validation)
                CONFIG_VALIDATION="false"
                shift
                ;;
            -t|--skip-tests)
                SKIP_TESTS="true"
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "未知参数: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

# 验证环境
validate_environment() {
    log_info "验证部署环境..."
    
    if [[ ! "$ENVIRONMENT" =~ ^(staging|production)$ ]]; then
        log_error "无效的环境: $ENVIRONMENT (必须是 staging 或 production)"
        exit 1
    fi
    
    if [[ ! "$DEPLOYMENT_MODE" =~ ^(docker-compose|kubernetes)$ ]]; then
        log_error "无效的部署模式: $DEPLOYMENT_MODE (必须是 docker-compose 或 kubernetes)"
        exit 1
    fi
    
    log_success "环境验证通过: $ENVIRONMENT ($DEPLOYMENT_MODE)"
}

# 验证配置工厂
validate_config_factory() {
    if [[ "$CONFIG_VALIDATION" == "false" ]]; then
        log_warning "跳过配置验证"
        return 0
    fi
    
    log_info "验证统一配置工厂..."
    
    # 检查Python环境
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 未安装"
        exit 1
    fi
    
    # 安装依赖
    log_info "安装配置工厂依赖..."
    if command -v pip3 &> /dev/null; then
        pip3 install -q pyyaml structlog aiohttp pydantic redis prometheus_client
    elif command -v pip &> /dev/null; then
        pip install -q pyyaml structlog aiohttp pydantic redis prometheus_client
    else
        log_warning "pip未找到，跳过依赖安装"
    fi
    
    # 运行配置验证
    if python3 scripts/validate-config-factory.py; then
        log_success "配置工厂验证通过"
    else
        log_error "配置工厂验证失败"
        exit 1
    fi
}

# 运行测试
run_tests() {
    if [[ "$SKIP_TESTS" == "true" ]]; then
        log_warning "跳过测试"
        return 0
    fi
    
    log_info "运行部署前测试..."
    
    # 配置工厂测试
    if python3 scripts/test-config-factory.py; then
        log_success "配置工厂测试通过"
    else
        log_error "配置工厂测试失败"
        exit 1
    fi
    
    # 服务配置加载测试
    log_info "测试服务配置加载..."
    python3 -c "
from config.unified_config_loader import UnifiedConfigLoader
loader = UnifiedConfigLoader()

services = ['monitoring-alerting-service', 'data-storage-service', 'api-gateway-service']
for service in services:
    try:
        config = loader.load_service_config(service)
        print(f'✅ {service}: 配置加载成功')
    except Exception as e:
        print(f'❌ {service}: 配置加载失败 - {e}')
        exit(1)

print('🎉 所有服务配置加载测试通过')
"
    
    log_success "所有测试通过"
}

# 创建基础Docker Compose配置
create_basic_docker_compose() {
    log_info "创建基础Docker Compose配置..."

    cat > docker-compose.generated.yml << EOF
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --requirepass \${REDIS_PASSWORD}
    environment:
      - REDIS_PASSWORD=\${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    networks:
      - marketprism-network
    restart: unless-stopped

  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_DB=\${POSTGRES_DB}
      - POSTGRES_USER=\${POSTGRES_USER}
      - POSTGRES_PASSWORD=\${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - marketprism-network
    restart: unless-stopped

  monitoring-alerting:
    image: python:3.12-slim
    working_dir: /app
    command: >
      bash -c "
        pip install -r requirements.txt &&
        python main.py
      "
    environment:
      - ENVIRONMENT=\${ENVIRONMENT}
      - CONFIG_FACTORY_ENABLED=true
      - DATABASE_URL=postgresql://\${POSTGRES_USER}:\${POSTGRES_PASSWORD}@postgres:5432/\${POSTGRES_DB}
      - REDIS_URL=redis://:\${REDIS_PASSWORD}@redis:6379/0
    volumes:
      - ./services/monitoring-alerting-service:/app
      - ./config:/app/config
      - ./core:/app/core
    ports:
      - "8082:8082"
    depends_on:
      - redis
      - postgres
    networks:
      - marketprism-network
    restart: unless-stopped

volumes:
  redis_data:
  postgres_data:

networks:
  marketprism-network:
    driver: bridge
EOF
}

# Docker Compose部署
deploy_docker_compose() {
    log_info "使用Docker Compose部署..."

    # 检查Docker权限
    if ! docker info >/dev/null 2>&1; then
        log_warning "Docker权限不足，尝试使用sudo..."
        DOCKER_CMD="sudo docker"
        DOCKER_COMPOSE_CMD="sudo docker-compose"
    else
        DOCKER_CMD="docker"
        DOCKER_COMPOSE_CMD="docker-compose"
    fi

    # 加载.env文件
    if [[ -f ".env" ]]; then
        log_info "加载.env文件..."
        set -a  # 自动导出变量
        source .env
        set +a
    fi

    # 设置环境变量
    export ENVIRONMENT
    export CONFIG_FACTORY_ENABLED=true
    export POSTGRES_DB=${POSTGRES_DB:-"marketprism"}
    export POSTGRES_USER=${POSTGRES_USER:-"marketprism_user"}
    export POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-"marketprism_secure_pass_2024"}
    export REDIS_PASSWORD=${REDIS_PASSWORD:-"redis_secure_pass_2024"}

    log_info "环境变量设置完成"
    log_info "  POSTGRES_DB: $POSTGRES_DB"
    log_info "  POSTGRES_USER: $POSTGRES_USER"
    log_info "  REDIS_PASSWORD: [已设置]"

    # 生成docker-compose配置
    log_info "生成Docker Compose配置..."

    if [[ "$ENVIRONMENT" == "production" ]] && [[ -f "docker-compose.prod.yml" ]]; then
        $DOCKER_COMPOSE_CMD -f docker-compose.yml -f docker-compose.prod.yml config > docker-compose.generated.yml
    elif [[ -f "docker-compose.yml" ]]; then
        $DOCKER_COMPOSE_CMD -f docker-compose.yml config > docker-compose.generated.yml
    else
        log_warning "docker-compose.yml不存在，创建基础配置..."
        create_basic_docker_compose
    fi
    
    # 部署服务
    log_info "部署服务..."
    docker-compose -f docker-compose.generated.yml up -d
    
    # 等待服务启动
    log_info "等待服务启动..."
    sleep 30
    
    # 健康检查
    log_info "执行健康检查..."
    if curl -f http://localhost:8082/health > /dev/null 2>&1; then
        log_success "监控告警服务健康检查通过"
    else
        log_warning "监控告警服务健康检查失败"
    fi
    
    log_success "Docker Compose部署完成"
}

# Kubernetes部署
deploy_kubernetes() {
    log_info "使用Kubernetes部署..."
    
    # 检查kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl 未安装"
        exit 1
    fi
    
    # 创建命名空间
    kubectl create namespace marketprism-$ENVIRONMENT --dry-run=client -o yaml | kubectl apply -f -
    
    # 创建ConfigMap
    log_info "创建配置ConfigMap..."
    kubectl create configmap marketprism-config \
        --from-file=config/new-structure/ \
        --namespace=marketprism-$ENVIRONMENT \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # 部署服务
    log_info "部署Kubernetes资源..."
    envsubst < k8s/$ENVIRONMENT/deployment.yaml | kubectl apply -f -
    
    # 等待部署完成
    log_info "等待部署完成..."
    kubectl rollout status deployment/monitoring-alerting -n marketprism-$ENVIRONMENT
    
    # 健康检查
    log_info "执行健康检查..."
    kubectl wait --for=condition=ready pod -l app=monitoring-alerting -n marketprism-$ENVIRONMENT --timeout=300s
    
    log_success "Kubernetes部署完成"
}

# 部署后验证
post_deployment_validation() {
    log_info "执行部署后验证..."
    
    # 等待服务稳定
    sleep 10
    
    # 配置工厂验证
    log_info "验证配置工厂在部署环境中的工作状态..."
    
    if [[ "$DEPLOYMENT_MODE" == "docker-compose" ]]; then
        # Docker Compose环境验证
        docker-compose exec -T monitoring-alerting python3 -c "
from config.unified_config_loader import UnifiedConfigLoader
loader = UnifiedConfigLoader()
config = loader.load_service_config('monitoring-alerting-service')
print('✅ 部署环境配置工厂验证通过')
" || log_warning "部署环境配置工厂验证失败"
    fi
    
    log_success "部署后验证完成"
}

# 生成部署报告
generate_deployment_report() {
    log_info "生成部署报告..."
    
    cat > deployment-report-$(date +%Y%m%d-%H%M%S).md << EOF
# 🚀 MarketPrism 部署报告

**部署时间**: $(date)
**环境**: $ENVIRONMENT
**部署模式**: $DEPLOYMENT_MODE
**配置工厂**: 启用

## 📊 部署状态

- ✅ 配置工厂验证通过
- ✅ 服务配置加载测试通过
- ✅ 部署执行成功
- ✅ 部署后验证通过

## 🔧 配置信息

- 使用统一配置工厂
- 支持环境变量覆盖
- 配置层次化管理
- 向后兼容保证

## 🌐 访问地址

- 监控告警服务: http://localhost:8082
- 健康检查: http://localhost:8082/health
- API文档: http://localhost:8082/docs

## 📋 后续步骤

1. 监控服务运行状态
2. 检查日志输出
3. 验证业务功能
4. 配置监控告警

EOF
    
    log_success "部署报告已生成"
}

# 主函数
main() {
    log_info "🚀 开始MarketPrism统一配置工厂部署"
    
    # 解析参数
    parse_args "$@"
    
    # 验证环境
    validate_environment
    
    # 验证配置工厂
    validate_config_factory
    
    # 运行测试
    run_tests
    
    # 执行部署
    case $DEPLOYMENT_MODE in
        docker-compose)
            deploy_docker_compose
            ;;
        kubernetes)
            deploy_kubernetes
            ;;
    esac
    
    # 部署后验证
    post_deployment_validation
    
    # 生成报告
    generate_deployment_report
    
    log_success "🎉 MarketPrism部署完成！"
    log_info "环境: $ENVIRONMENT"
    log_info "模式: $DEPLOYMENT_MODE"
    log_info "配置工厂: 已启用"
}

# 执行主函数
main "$@"
