#!/bin/bash

# MarketPrism 优化Docker构建脚本
# 使用最优配置进行快速构建

set -e

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

print_header() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║              MarketPrism 优化Docker构建                     ║"
    echo "║              使用最优配置进行快速构建                        ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "${CYAN}🔧 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# 设置最优环境
setup_optimal_env() {
    print_step "1. 设置最优构建环境"
    
    # 检查最优配置文件是否存在
    if [ ! -f "$PROJECT_ROOT/optimal_config.json" ]; then
        print_error "最优配置文件不存在，正在运行测试器..."
        "$SCRIPT_DIR/comprehensive_source_tester.sh"
    fi
    
    # 应用最优环境变量
    if [ -f "$SCRIPT_DIR/setup_optimal_env.sh" ]; then
        echo "  📝 应用最优环境变量..."
        source "$SCRIPT_DIR/setup_optimal_env.sh"
        print_success "环境变量已设置"
    else
        print_error "环境变量脚本不存在"
        exit 1
    fi
}

# 验证配置
verify_config() {
    print_step "2. 验证配置有效性"
    
    if [ -f "$SCRIPT_DIR/verify_optimal_config.sh" ]; then
        "$SCRIPT_DIR/verify_optimal_config.sh" || {
            print_error "配置验证失败，请检查网络连接"
            exit 1
        }
        print_success "配置验证通过"
    fi
}

# 清理Docker环境
cleanup_docker() {
    print_step "3. 清理Docker环境"
    
    echo "  🧹 清理构建缓存..."
    docker builder prune -f --filter type=exec.cachemount || true
    docker builder prune -f --filter type=regular || true
    
    echo "  🧹 清理无用镜像..."
    docker image prune -f || true
    
    print_success "Docker环境已清理"
}

# 构建服务
build_service() {
    local service="$1"
    local dockerfile="$2"
    
    print_step "4. 构建 $service 服务"
    
    echo "  🐳 开始构建镜像..."
    
    # 构建参数
    BUILD_ARGS=""
    
    # 添加代理参数
    if [ -n "$http_proxy" ]; then
        BUILD_ARGS="$BUILD_ARGS --build-arg HTTP_PROXY=$http_proxy"
        BUILD_ARGS="$BUILD_ARGS --build-arg HTTPS_PROXY=$https_proxy"
        BUILD_ARGS="$BUILD_ARGS --build-arg http_proxy=$http_proxy"
        BUILD_ARGS="$BUILD_ARGS --build-arg https_proxy=$https_proxy"
    fi
    
    # 添加包源参数
    if [ -n "$PIP_INDEX_URL" ]; then
        BUILD_ARGS="$BUILD_ARGS --build-arg PIP_INDEX_URL=$PIP_INDEX_URL"
        BUILD_ARGS="$BUILD_ARGS --build-arg PIP_TRUSTED_HOST=$PIP_TRUSTED_HOST"
    fi
    
    if [ -n "$GOPROXY" ]; then
        BUILD_ARGS="$BUILD_ARGS --build-arg GOPROXY=$GOPROXY"
        BUILD_ARGS="$BUILD_ARGS --build-arg GOSUMDB=off"
    fi
    
    # Docker主机IP
    if [[ "$OSTYPE" == "darwin"* ]]; then
        BUILD_ARGS="$BUILD_ARGS --build-arg DOCKER_HOST_IP=host.docker.internal"
    else
        BUILD_ARGS="$BUILD_ARGS --build-arg DOCKER_HOST_IP=172.17.0.1"
    fi
    
    echo "  ⚙️  构建参数: $BUILD_ARGS"
    
    # 执行构建
    start_time=$(date +%s)
    
    if docker build \
        $BUILD_ARGS \
        --progress=plain \
        --no-cache \
        -f "$dockerfile" \
        -t "marketprism-${service}:latest" \
        -t "marketprism-${service}:optimized" \
        .; then
        
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        
        print_success "$service 构建完成 (${duration}s)"
        
        # 显示镜像信息
        echo "  📊 镜像信息:"
        docker images | grep "marketprism-${service}" | head -2
        
    else
        print_error "$service 构建失败"
        exit 1
    fi
}

# 构建所有服务
build_all_services() {
    print_step "5. 构建所有服务"
    
    # 检测可用的Dockerfile
    if [ -f "Dockerfile.ultimate" ]; then
        echo "  🎯 使用 Dockerfile.ultimate (最优化版本)"
        build_service "ultimate" "Dockerfile.ultimate"
    elif [ -f "Dockerfile.fast" ]; then
        echo "  🚀 使用 Dockerfile.fast (快速版本)"
        build_service "fast" "Dockerfile.fast"
    elif [ -f "Dockerfile" ]; then
        echo "  📦 使用 Dockerfile (标准版本)"
        build_service "standard" "Dockerfile"
    else
        print_error "未找到任何Dockerfile"
        exit 1
    fi
}

# 运行构建后测试
post_build_test() {
    print_step "6. 构建后测试"
    
    echo "  🧪 测试镜像是否正常运行..."
    
    # 查找构建的镜像
    IMAGE=$(docker images --format "table {{.Repository}}:{{.Tag}}" | grep "marketprism.*:latest" | head -1)
    
    if [ -n "$IMAGE" ]; then
        echo "  🐳 测试镜像: $IMAGE"
        
        # 简单的启动测试
        if docker run --rm --name marketprism-test -d "$IMAGE" sleep 10; then
            sleep 2
            if docker ps | grep -q "marketprism-test"; then
                docker stop marketprism-test >/dev/null 2>&1 || true
                print_success "镜像运行测试通过"
            else
                print_error "镜像启动失败"
            fi
        else
            print_error "无法启动测试容器"
        fi
    else
        print_error "未找到构建的镜像"
    fi
}

# 显示构建总结
show_summary() {
    print_step "7. 构建总结"
    
    echo ""
    echo -e "${BLUE}📊 构建完成总结：${NC}"
    echo -e "  🌐 使用代理: ${http_proxy:-无}"
    echo -e "  🐳 Docker源: https://mirror.ccs.tencentyun.com"
    echo -e "  🐍 Python源: ${PIP_INDEX_URL:-默认}"
    echo -e "  🚀 Go代理: ${GOPROXY:-默认}"
    
    echo ""
    echo -e "${BLUE}📦 构建的镜像：${NC}"
    docker images | grep "marketprism" | head -5
    
    echo ""
    echo -e "${GREEN}🎉 所有构建任务完成！${NC}"
    echo -e "${BLUE}💡 下一步：使用 docker-compose up 启动服务${NC}"
}

# 主函数
main() {
    cd "$PROJECT_ROOT"
    
    print_header
    
    setup_optimal_env
    verify_config
    cleanup_docker
    build_all_services
    post_build_test
    show_summary
}

# 错误处理
trap 'print_error "构建过程中发生错误"; exit 1' ERR

# 运行主函数
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi 