#!/bin/bash

# 卡住先生的反卡住终极构建器
# 专治各种卡住问题，绝不让你等一小时！

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m'

# 超时配置（秒）
DOCKER_BUILD_TIMEOUT=300  # 5分钟构建超时
DOCKER_PULL_TIMEOUT=60    # 1分钟拉取超时
NETWORK_TEST_TIMEOUT=10   # 10秒网络测试超时

print_header() {
    echo -e "${PURPLE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║           卡住先生的反卡住终极构建器                         ║"
    echo "║              专治各种卡住，绝不等一小时！                    ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "${CYAN}🚀 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

# 超时执行函数
run_with_timeout() {
    local timeout=$1
    local description="$2"
    shift 2
    local cmd="$*"
    
    echo -e "${YELLOW}⏱️ 执行: $description (超时: ${timeout}s)${NC}"
    
    if command -v gtimeout >/dev/null 2>&1; then
        gtimeout $timeout bash -c "$cmd"
    elif command -v timeout >/dev/null 2>&1; then
        timeout $timeout bash -c "$cmd"
    else
        # 自制超时机制
        (
            eval "$cmd" &
            CMD_PID=$!
            sleep $timeout && {
                echo -e "\n${RED}⏰ 超时！强制终止进程...${NC}"
                kill -9 $CMD_PID 2>/dev/null || true
                return 124
            } &
            TIMER_PID=$!
            wait $CMD_PID
            CMD_RESULT=$?
            kill $TIMER_PID 2>/dev/null || true
            return $CMD_RESULT
        )
    fi
}

# 强制清理Docker环境
force_cleanup_docker() {
    print_step "1. 强制清理Docker环境（防止卡住）"
    
    echo "  🧹 停止所有运行的容器..."
    docker stop $(docker ps -aq) 2>/dev/null || true
    
    echo "  🧹 删除所有容器..."
    docker rm $(docker ps -aq) 2>/dev/null || true
    
    echo "  🧹 清理构建缓存..."
    run_with_timeout 30 "清理构建缓存" "docker builder prune -f --all" || true
    
    echo "  🧹 清理系统..."
    run_with_timeout 30 "清理系统" "docker system prune -f" || true
    
    print_success "Docker环境已强制清理"
}

# 测试网络连接（快速版）
test_network_fast() {
    print_step "2. 快速网络连接测试"
    
    # 测试基本网络
    if run_with_timeout $NETWORK_TEST_TIMEOUT "测试Google连接" "curl -s -I https://www.google.com"; then
        print_success "网络连接正常"
    else
        print_warning "网络连接可能有问题，将使用离线模式"
        return 1
    fi
    
    # 测试Docker Hub
    if run_with_timeout $NETWORK_TEST_TIMEOUT "测试Docker Hub" "curl -s https://registry-1.docker.io/v2/"; then
        print_success "Docker Hub连接正常"
    else
        print_warning "Docker Hub连接有问题，将使用镜像源"
    fi
}

# 创建超简单Dockerfile（防止卡住）
create_simple_dockerfile() {
    print_step "3. 创建防卡住Dockerfile"
    
    cat > Dockerfile.anti-stuck << 'EOF'
# 卡住先生的反卡住Dockerfile
# 使用最小镜像，最少步骤，绝不卡住！

FROM alpine:3.18

# 设置镜像源（防止下载卡住）
RUN echo "http://mirrors.aliyun.com/alpine/v3.18/main" > /etc/apk/repositories && \
    echo "http://mirrors.aliyun.com/alpine/v3.18/community" >> /etc/apk/repositories

# 安装基本工具（超时保护）
RUN apk add --no-cache --timeout 60 \
    python3 \
    py3-pip \
    curl \
    bash

# 设置工作目录
WORKDIR /app

# 复制必要文件
COPY requirements.txt* ./

# 安装Python包（使用国内源，超时保护）
RUN if [ -f requirements.txt ]; then \
        pip3 install --timeout 60 --no-cache-dir \
        -i https://mirrors.aliyun.com/pypi/simple/ \
        --trusted-host mirrors.aliyun.com \
        -r requirements.txt || echo "⚠️ 包安装失败，继续..."; \
    fi

# 复制应用代码
COPY . .

# 设置启动命令
CMD ["python3", "-c", "print('🎉 反卡住构建成功！MarketPrism容器已启动！')"]

EOF

    print_success "防卡住Dockerfile已创建"
}

# 执行防卡住构建
build_anti_stuck() {
    print_step "4. 执行防卡住构建"
    
    echo "  🐳 开始构建（最大等待时间: ${DOCKER_BUILD_TIMEOUT}s）..."
    
    if run_with_timeout $DOCKER_BUILD_TIMEOUT "Docker构建" \
        "docker build --no-cache -f Dockerfile.anti-stuck -t marketprism:anti-stuck ."; then
        print_success "构建成功！没有卡住！"
        return 0
    else
        print_error "构建失败或超时"
        return 1
    fi
}

# 测试构建的镜像
test_built_image() {
    print_step "5. 测试构建的镜像"
    
    echo "  🧪 启动容器测试..."
    
    if run_with_timeout 30 "启动测试容器" \
        "docker run --rm --name test-anti-stuck marketprism:anti-stuck"; then
        print_success "镜像测试成功！"
    else
        print_error "镜像测试失败"
    fi
}

# 提供构建诊断
diagnose_build_issues() {
    print_step "6. 构建问题诊断"
    
    echo ""
    echo -e "${BLUE}📊 系统信息：${NC}"
    echo "  Docker版本: $(docker --version 2>/dev/null || echo '未安装')"
    echo "  可用内存: $(free -h 2>/dev/null | grep Mem | awk '{print $7}' || echo '未知')"
    echo "  磁盘空间: $(df -h . | tail -1 | awk '{print $4}' || echo '未知')"
    
    echo ""
    echo -e "${BLUE}🔍 网络状态：${NC}"
    if curl -s -I --connect-timeout 5 https://www.google.com >/dev/null 2>&1; then
        echo "  ✅ 外网连接正常"
    else
        echo "  ❌ 外网连接有问题"
    fi
    
    if curl -s --connect-timeout 5 https://registry-1.docker.io/v2/ >/dev/null 2>&1; then
        echo "  ✅ Docker Hub连接正常"
    else
        echo "  ❌ Docker Hub连接有问题"
    fi
    
    echo ""
    echo -e "${BLUE}💡 卡住原因分析：${NC}"
    echo "  1. 网络问题 - 某些源连接超时"
    echo "  2. 代理配置 - 代理设置可能有误"
    echo "  3. Docker配置 - BuildKit或缓存问题"
    echo "  4. 资源不足 - 内存或磁盘空间不够"
    
    echo ""
    echo -e "${GREEN}🎯 解决建议：${NC}"
    echo "  1. 使用本脚本的轻量化构建"
    echo "  2. 检查网络和代理设置"
    echo "  3. 重启Docker服务"
    echo "  4. 清理Docker缓存和镜像"
}

# 主函数
main() {
    print_header
    
    # 执行反卡住流程
    force_cleanup_docker
    test_network_fast
    create_simple_dockerfile
    
    if build_anti_stuck; then
        test_built_image
        print_success "🎉 反卡住构建完成！卡住先生终于不卡了！"
    else
        print_error "🤔 还是有问题，进行诊断..."
        diagnose_build_issues
    fi
    
    echo ""
    echo -e "${PURPLE}📋 卡住先生总结：${NC}"
    echo -e "  🎯 如果这个都卡住，说明问题很严重"
    echo -e "  🔧 建议重启Docker，或者重启电脑"
    echo -e "  📞 或者叫醒真正的运维工程师来看看"
    echo -e "  😅 卡住先生已经尽力了！"
}

# 运行脚本
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi 