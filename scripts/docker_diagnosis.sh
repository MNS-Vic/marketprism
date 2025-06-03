#!/bin/bash

# 卡住先生的终极诊断器
# 既然构建总是卡住，那就彻底诊断一下到底哪里有问题！

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m'

print_header() {
    echo -e "${RED}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║              卡住先生的终极诊断器                            ║"
    echo "║          既然都卡住，那就查查到底哪里有鬼！                  ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

diagnose_docker() {
    echo -e "${BLUE}🔍 Docker基础诊断：${NC}"
    
    echo "  📋 Docker版本："
    docker --version || echo "    ❌ Docker未安装或无法访问"
    
    echo ""
    echo "  📋 Docker服务状态："
    if docker info >/dev/null 2>&1; then
        echo "    ✅ Docker服务正常运行"
    else
        echo "    ❌ Docker服务异常"
        return 1
    fi
    
    echo ""
    echo "  📋 Docker系统信息："
    docker system df 2>/dev/null || echo "    ❌ 无法获取Docker系统信息"
    
    echo ""
    echo "  📋 当前运行的容器："
    docker ps || echo "    ❌ 无法列出容器"
    
    echo ""
    echo "  📋 Docker进程："
    ps aux | grep -i docker | grep -v grep || echo "    ❌ 未找到Docker进程"
}

diagnose_network() {
    echo -e "${BLUE}🌐 网络连接诊断：${NC}"
    
    echo "  🔗 测试基本网络连接："
    if ping -c 3 8.8.8.8 >/dev/null 2>&1; then
        echo "    ✅ 基本网络连接正常"
    else
        echo "    ❌ 基本网络连接异常"
    fi
    
    echo ""
    echo "  🔗 测试DNS解析："
    if nslookup google.com >/dev/null 2>&1; then
        echo "    ✅ DNS解析正常"
    else
        echo "    ❌ DNS解析异常"
    fi
    
    echo ""
    echo "  🔗 测试Docker Hub连接："
    if curl -s --connect-timeout 10 https://index.docker.io/v1/ >/dev/null 2>&1; then
        echo "    ✅ Docker Hub连接正常"
    else
        echo "    ❌ Docker Hub连接异常"
    fi
    
    echo ""
    echo "  🔗 测试代理设置："
    if [ -n "$http_proxy" ]; then
        echo "    📝 HTTP代理: $http_proxy"
        if curl -s --proxy "$http_proxy" --connect-timeout 10 https://www.google.com >/dev/null 2>&1; then
            echo "    ✅ 代理连接正常"
        else
            echo "    ❌ 代理连接异常"
        fi
    else
        echo "    📝 未设置代理"
    fi
}

diagnose_system_resources() {
    echo -e "${BLUE}💾 系统资源诊断：${NC}"
    
    echo "  📊 内存使用："
    if command -v free >/dev/null 2>&1; then
        free -h | grep -E "(Mem|Swap)"
    else
        # macOS
        echo "    内存总量: $(sysctl -n hw.memsize | awk '{print int($1/1024/1024/1024) "GB"}')"
        echo "    已用内存: $(vm_stat | grep "Pages active" | awk '{print int($3*4096/1024/1024) "MB"}')"
    fi
    
    echo ""
    echo "  📊 磁盘空间："
    df -h | head -5
    
    echo ""
    echo "  📊 CPU负载："
    if command -v uptime >/dev/null 2>&1; then
        uptime
    else
        echo "    无法获取CPU负载信息"
    fi
    
    echo ""
    echo "  📊 活跃进程（按CPU排序）："
    ps aux --sort=-%cpu | head -10 2>/dev/null || ps aux | head -10
}

diagnose_docker_daemon() {
    echo -e "${BLUE}🐳 Docker守护进程诊断：${NC}"
    
    echo "  📋 Docker守护进程配置："
    if [ -f ~/.docker/daemon.json ]; then
        echo "    ✅ 找到用户Docker配置："
        cat ~/.docker/daemon.json 2>/dev/null || echo "    ❌ 无法读取配置文件"
    else
        echo "    📝 用户Docker配置不存在"
    fi
    
    echo ""
    if [ -f /etc/docker/daemon.json ]; then
        echo "    ✅ 找到系统Docker配置："
        cat /etc/docker/daemon.json 2>/dev/null || echo "    ❌ 无法读取系统配置"
    else
        echo "    📝 系统Docker配置不存在"
    fi
    
    echo ""
    echo "  📋 Docker日志（最近20行）："
    if command -v journalctl >/dev/null 2>&1; then
        journalctl -u docker --no-pager -n 20 2>/dev/null || echo "    ❌ 无法获取systemd日志"
    else
        # macOS
        echo "    📝 macOS Docker日志位置: ~/Library/Containers/com.docker.docker/Data/log/"
        echo "    💡 可以在Docker Desktop查看日志"
    fi
}

diagnose_build_locks() {
    echo -e "${BLUE}🔒 构建锁定诊断：${NC}"
    
    echo "  📋 检查Docker构建缓存："
    docker builder ls 2>/dev/null || echo "    ❌ 无法列出构建器"
    
    echo ""
    echo "  📋 检查是否有卡住的构建进程："
    ps aux | grep -E "(docker.*build|buildkit)" | grep -v grep || echo "    📝 未发现构建进程"
    
    echo ""
    echo "  📋 检查临时文件："
    ls -la /tmp/docker* 2>/dev/null || echo "    📝 未发现Docker临时文件"
    
    echo ""
    echo "  📋 检查Docker socket："
    if [ -S /var/run/docker.sock ]; then
        echo "    ✅ Docker socket存在"
        ls -la /var/run/docker.sock
    else
        echo "    ❌ Docker socket不存在或不可访问"
    fi
}

provide_solutions() {
    echo -e "${GREEN}💡 卡住先生的解决建议：${NC}"
    echo ""
    echo -e "${YELLOW}🎯 基于诊断结果，可能的解决方案：${NC}"
    echo ""
    echo "  1. 重启Docker服务："
    echo "     macOS: 重启Docker Desktop应用"
    echo "     Linux: sudo systemctl restart docker"
    echo ""
    echo "  2. 清理Docker环境："
    echo "     docker system prune -f --all"
    echo "     docker builder prune -f --all"
    echo ""
    echo "  3. 检查网络设置："
    echo "     ping 8.8.8.8"
    echo "     curl -I https://www.google.com"
    echo ""
    echo "  4. 检查资源限制："
    echo "     - 确保有足够的磁盘空间（>5GB）"
    echo "     - 确保有足够的内存（>2GB）"
    echo ""
    echo "  5. 如果还是卡住："
    echo "     - 重启电脑"
    echo "     - 重新安装Docker"
    echo "     - 找真正的运维工程师"
    echo ""
    echo -e "${RED}😅 卡住先生已经尽力了！如果这些都不行，那就是玄学问题了...${NC}"
}

main() {
    print_header
    
    echo ""
    diagnose_docker
    echo ""
    diagnose_network  
    echo ""
    diagnose_system_resources
    echo ""
    diagnose_docker_daemon
    echo ""
    diagnose_build_locks
    echo ""
    provide_solutions
}

# 运行诊断
main 