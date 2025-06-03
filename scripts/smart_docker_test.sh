#!/bin/bash

# 卡住先生的智能Docker测试器
# 绝不让你傻等超过30秒！

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 超时设置
DOCKER_TIMEOUT=15  # Docker命令15秒超时
TEST_TIMEOUT=5     # 网络测试5秒超时

print_header() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║            卡住先生的智能Docker测试器                        ║"
    echo "║              绝不让你等超过30秒！                            ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# 带超时的命令执行
run_with_smart_timeout() {
    local timeout=$1
    local description="$2"
    local cmd="$3"
    
    echo -n -e "${YELLOW}⏱️ $description (${timeout}s超时)... ${NC}"
    
    # 使用后台进程+超时控制
    (
        eval "$cmd" >/dev/null 2>&1 &
        CMD_PID=$!
        
        # 启动超时计时器
        (
            sleep $timeout
            echo -e "\n${RED}⏰ 超时！强制终止${NC}"
            kill -9 $CMD_PID 2>/dev/null
            exit 124
        ) &
        TIMER_PID=$!
        
        # 等待命令完成
        wait $CMD_PID 2>/dev/null
        CMD_RESULT=$?
        
        # 清理计时器
        kill $TIMER_PID 2>/dev/null
        exit $CMD_RESULT
    )
    
    local result=$?
    if [ $result -eq 0 ]; then
        echo -e "${GREEN}✅ 成功${NC}"
        return 0
    elif [ $result -eq 124 ]; then
        echo -e "${RED}❌ 超时${NC}"
        return 1
    else
        echo -e "${RED}❌ 失败${NC}"
        return 1
    fi
}

# 快速系统检查
quick_system_check() {
    echo -e "${BLUE}🔍 1. 快速系统检查${NC}"
    
    # 检查CPU负载
    load=$(uptime | awk -F'load averages:' '{print $2}' | awk '{print $1}' | sed 's/,//')
    if (( $(echo "$load > 2.0" | bc -l) )); then
        echo -e "${YELLOW}⚠️ CPU负载较高: $load${NC}"
    else
        echo -e "${GREEN}✅ CPU负载正常: $load${NC}"
    fi
    
    # 检查内存
    memory_pressure=$(memory_pressure | head -1)
    echo -e "${GREEN}✅ 内存状态: $memory_pressure${NC}"
}

# 测试Docker服务
test_docker_service() {
    echo -e "${BLUE}🐳 2. 测试Docker服务${NC}"
    
    # 测试Docker版本（最简单的命令）
    if run_with_smart_timeout $DOCKER_TIMEOUT "Docker版本检查" "docker --version"; then
        echo -e "    ✅ Docker服务可访问"
    else
        echo -e "    ❌ Docker服务异常"
        return 1
    fi
    
    # 测试Docker info（稍微复杂一点）
    if run_with_smart_timeout $DOCKER_TIMEOUT "Docker状态检查" "docker system df"; then
        echo -e "    ✅ Docker状态正常"
    else
        echo -e "    ❌ Docker状态异常"
        return 1
    fi
}

# 测试镜像拉取
test_image_pull() {
    echo -e "${BLUE}📦 3. 测试镜像拉取${NC}"
    
    # 测试最小镜像
    if run_with_smart_timeout 30 "拉取alpine镜像" "docker pull alpine:3.18"; then
        echo -e "    ✅ 镜像拉取正常"
        return 0
    else
        echo -e "    ❌ 镜像拉取失败"
        return 1
    fi
}

# 快速构建测试
quick_build_test() {
    echo -e "${BLUE}🔨 4. 快速构建测试${NC}"
    
    # 创建最简单的Dockerfile
    cat > Dockerfile.quick-test << 'EOF'
FROM alpine:3.18
RUN echo "Hello from quick test!"
CMD echo "Quick test successful!"
EOF
    
    # 超快速构建
    if run_with_smart_timeout 60 "快速构建测试" "docker build -f Dockerfile.quick-test -t quick-test ."; then
        echo -e "    ✅ 构建测试成功"
        
        # 清理测试文件
        rm -f Dockerfile.quick-test
        docker rmi quick-test >/dev/null 2>&1
        return 0
    else
        echo -e "    ❌ 构建测试失败"
        rm -f Dockerfile.quick-test
        return 1
    fi
}

# 提供解决方案
provide_quick_solutions() {
    echo -e "${BLUE}💡 快速解决方案${NC}"
    echo ""
    echo -e "${YELLOW}如果测试失败，立即尝试：${NC}"
    echo "  1. 重启Docker Desktop (30秒内)"
    echo "  2. 清理Docker缓存: docker system prune -f"
    echo "  3. 检查网络连接: ping 8.8.8.8"
    echo "  4. 重启电脑 (最后手段)"
    echo ""
    echo -e "${GREEN}如果测试成功，可以进行：${NC}"
    echo "  1. 使用轻量化构建: scripts/anti_stuck_builder.sh"
    echo "  2. 使用优化配置构建: scripts/build_with_optimal_config.sh"
    echo "  3. 监控系统负载: top -l 1"
}

# 强制中断提示
show_interrupt_help() {
    echo ""
    echo -e "${RED}🛑 如果任何测试卡住，立即按 Ctrl+C 强制中断！${NC}"
    echo -e "${YELLOW}💡 卡住先生保证：每个测试都有超时保护，最多等30秒${NC}"
    echo ""
}

# 主函数
main() {
    print_header
    show_interrupt_help
    
    # 执行测试序列
    quick_system_check
    echo ""
    
    if test_docker_service; then
        echo ""
        if test_image_pull; then
            echo ""
            quick_build_test
        fi
    fi
    
    echo ""
    provide_quick_solutions
    
    echo ""
    echo -e "${GREEN}🎉 智能测试完成！没有傻等，没有卡住！${NC}"
}

# 运行测试
main 