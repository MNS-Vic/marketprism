#!/bin/bash

# MarketPrism 自动化部署脚本
# Phase 4: 优化与部署 - 一键部署工具

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# 配置
ENVIRONMENT=${1:-"development"}
DEPLOY_MODE=${2:-"docker"}

echo -e "${BLUE}🚀 MarketPrism 部署脚本${NC}"
echo -e "${BLUE}Phase 4: 优化与部署${NC}"
echo "=================================="
echo "环境: $ENVIRONMENT"
echo "部署模式: $DEPLOY_MODE"
echo "项目根目录: $PROJECT_ROOT"
echo "=================================="

# 检查依赖
check_dependencies() {
    echo -e "\n${YELLOW}🔍 检查部署依赖...${NC}"
    
    # 检查Docker
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Docker 未安装${NC}"
        exit 1
    fi
    
    # 检查Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        echo -e "${RED}❌ Docker Compose 未安装${NC}"
        exit 1
    fi
    
    # 检查Python
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌ Python 3 未安装${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ 所有依赖检查通过${NC}"
}

# 环境准备
prepare_environment() {
    echo -e "\n${YELLOW}📦 准备部署环境...${NC}"
    
    cd "$PROJECT_ROOT"
    
    # 创建必要的目录
    mkdir -p logs
    mkdir -p data
    mkdir -p cache
    mkdir -p docker/logs
    mkdir -p docker/data
    
    # 设置权限
    chmod +x scripts/deployment/*.sh
    chmod +x scripts/maintenance/*.sh
    
    echo -e "${GREEN}✅ 环境准备完成${NC}"
}

# 配置验证
validate_configuration() {
    echo -e "\n${YELLOW}🔧 验证配置文件...${NC}"
    
    # 检查核心配置文件
    config_files=(
        "config/services.yaml"
        "docker/docker-compose.yml"
        "requirements.txt"
    )
    
    for file in "${config_files[@]}"; do
        if [ ! -f "$PROJECT_ROOT/$file" ]; then
            echo -e "${RED}❌ 配置文件缺失: $file${NC}"
            exit 1
        fi
    done
    
    # 验证services.yaml
    python3 -c "
import yaml
import sys
try:
    with open('config/services.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    print('✅ services.yaml 配置有效')
except Exception as e:
    print(f'❌ services.yaml 配置错误: {e}')
    sys.exit(1)
"
    
    echo -e "${GREEN}✅ 配置验证完成${NC}"
}

# Docker部署
deploy_docker() {
    echo -e "\n${YELLOW}🐳 Docker 容器化部署...${NC}"
    
    cd "$PROJECT_ROOT"
    
    # 停止现有容器
    echo "停止现有容器..."
    docker-compose -f docker/docker-compose.yml down --remove-orphans || true
    
    # 清理旧镜像（可选）
    if [ "$ENVIRONMENT" = "production" ]; then
        echo "清理旧镜像..."
        docker system prune -f
    fi
    
    # 构建镜像
    echo "构建服务镜像..."
    docker-compose -f docker/docker-compose.yml build --no-cache
    
    # 启动服务
    echo "启动服务..."
    docker-compose -f docker/docker-compose.yml up -d
    
    # 等待服务启动
    echo "等待服务启动..."
    sleep 30
    
    # 检查服务状态
    echo "检查服务状态..."
    docker-compose -f docker/docker-compose.yml ps
    
    echo -e "${GREEN}✅ Docker 部署完成${NC}"
}

# 本地部署
deploy_local() {
    echo -e "\n${YELLOW}💻 本地环境部署...${NC}"
    
    cd "$PROJECT_ROOT"
    
    # 安装Python依赖
    echo "安装Python依赖..."
    pip3 install -r requirements.txt
    
    # 启动基础设施（如果需要）
    if [ "$ENVIRONMENT" = "development" ]; then
        echo "启动开发环境基础设施..."
        docker-compose -f docker-compose-nats.yml up -d || true
    fi
    
    # 启动服务（使用supervisor或systemd）
    echo "启动MarketPrism服务..."
    
    # 这里可以添加具体的服务启动逻辑
    # 比如使用supervisor、systemd或者简单的后台进程
    
    echo -e "${GREEN}✅ 本地部署完成${NC}"
}

# 健康检查
health_check() {
    echo -e "\n${YELLOW}🔍 执行健康检查...${NC}"
    
    # 等待服务完全启动
    sleep 10
    
    # 检查各服务健康状态
    services=(
        "api-gateway-service:8080"
        "data-storage-service:8082"
        "market-data-collector:8081"
        "scheduler-service:8084"
        "monitoring-service:8083"
        "message-broker-service:8085"
    )
    
    all_healthy=true
    
    for service in "${services[@]}"; do
        name=$(echo $service | cut -d: -f1)
        port=$(echo $service | cut -d: -f2)
        
        echo -n "检查 $name ... "
        
        if curl -s -f "http://localhost:$port/health" > /dev/null; then
            echo -e "${GREEN}✅ 健康${NC}"
        else
            echo -e "${RED}❌ 不健康${NC}"
            all_healthy=false
        fi
    done
    
    if [ "$all_healthy" = true ]; then
        echo -e "\n${GREEN}🎉 所有服务健康检查通过！${NC}"
    else
        echo -e "\n${RED}⚠️  部分服务健康检查失败${NC}"
        echo "请检查日志: docker-compose -f docker/docker-compose.yml logs"
        exit 1
    fi
}

# 性能基准测试
run_benchmark() {
    echo -e "\n${YELLOW}📊 执行性能基准测试...${NC}"
    
    cd "$PROJECT_ROOT"
    
    if [ -f "scripts/performance_benchmark.py" ]; then
        echo "运行性能基准测试..."
        python3 scripts/performance_benchmark.py
    else
        echo -e "${YELLOW}⚠️  性能基准测试脚本不存在${NC}"
    fi
}

# 部署后清理
cleanup() {
    echo -e "\n${YELLOW}🧹 执行部署后清理...${NC}"
    
    # 清理临时文件
    find "$PROJECT_ROOT" -name "*.pyc" -delete || true
    find "$PROJECT_ROOT" -name "__pycache__" -type d -exec rm -rf {} + || true
    find "$PROJECT_ROOT" -name "*.log.*" -delete || true
    
    # 清理Docker资源（仅在生产环境）
    if [ "$ENVIRONMENT" = "production" ]; then
        docker system prune -f --volumes || true
    fi
    
    echo -e "${GREEN}✅ 清理完成${NC}"
}

# 显示部署信息
show_deployment_info() {
    echo -e "\n${BLUE}📋 部署信息${NC}"
    echo "=================================="
    echo "🌐 Web访问地址:"
    echo "  - API网关: http://localhost:8080"
    echo "  - 监控服务: http://localhost:8083"
    echo "  - Grafana仪表板: http://localhost:3000 (admin/marketprism_admin)"
    echo "  - Prometheus: http://localhost:9090"
    echo ""
    echo "🔍 服务状态检查:"
    echo "  docker-compose -f docker/docker-compose.yml ps"
    echo ""
    echo "📊 查看日志:"
    echo "  docker-compose -f docker/docker-compose.yml logs -f [service_name]"
    echo ""
    echo "🛑 停止服务:"
    echo "  docker-compose -f docker/docker-compose.yml down"
    echo "=================================="
}

# 主部署流程
main() {
    echo -e "${GREEN}开始 MarketPrism 部署...${NC}"
    
    # 执行部署步骤
    check_dependencies
    prepare_environment
    validate_configuration
    
    # 根据部署模式执行
    case $DEPLOY_MODE in
        "docker")
            deploy_docker
            ;;
        "local")
            deploy_local
            ;;
        *)
            echo -e "${RED}❌ 不支持的部署模式: $DEPLOY_MODE${NC}"
            echo "支持的模式: docker, local"
            exit 1
            ;;
    esac
    
    # 健康检查
    health_check
    
    # 性能测试（可选）
    if [ "$ENVIRONMENT" = "production" ]; then
        run_benchmark
    fi
    
    # 清理
    cleanup
    
    # 显示部署信息
    show_deployment_info
    
    echo -e "\n${GREEN}🎉 MarketPrism 部署完成！${NC}"
}

# 错误处理
trap 'echo -e "\n${RED}❌ 部署过程中发生错误${NC}"; exit 1' ERR

# 运行主流程
main
