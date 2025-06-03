#!/bin/bash

# MarketPrism 全面包源测试器
# 轮换测试所有包源和镜像源，找到最佳组合

set -e

# 配置参数
TIMEOUT=8  # 单个测试超时时间（秒）
MAX_TOTAL_TIME=300  # 总测试超时时间（5分钟）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m'

# 结果文件
RESULTS_FILE="/tmp/marketprism_test_results.txt"
BEST_CONFIG_FILE="$PROJECT_ROOT/optimal_config.json"

print_header() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║              MarketPrism 全面包源测试器                      ║"
    echo "║          轮换测试所有源，找到最佳组合                        ║"
    echo "║              设置超时 $TIMEOUT 秒避免卡住                      ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_section() {
    echo -e "${CYAN}🔍 $1${NC}"
}

print_test() {
    echo -n -e "${YELLOW}  ⏱️  测试 $1... ${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_fail() {
    echo -e "${RED}❌ $1${NC}"
}

print_timeout() {
    echo -e "${PURPLE}⏰ 超时${NC}"
}

# 超时测试函数
timeout_test() {
    local test_cmd="$1"
    local test_name="$2"
    
    if command -v gtimeout >/dev/null 2>&1; then
        # macOS with coreutils
        gtimeout $TIMEOUT bash -c "$test_cmd" >/dev/null 2>&1
    elif command -v timeout >/dev/null 2>&1; then
        # Linux
        timeout $TIMEOUT bash -c "$test_cmd" >/dev/null 2>&1
    else
        # 自制超时机制
        (
            eval "$test_cmd" >/dev/null 2>&1 &
            TEST_PID=$!
            sleep $TIMEOUT && kill $TEST_PID 2>/dev/null &
            TIMER_PID=$!
            wait $TEST_PID 2>/dev/null
            TEST_RESULT=$?
            kill $TIMER_PID 2>/dev/null
            exit $TEST_RESULT
        )
    fi
}

# 记录测试结果
record_result() {
    local category="$1"
    local name="$2"
    local url="$3"
    local duration="$4"
    local status="$5"
    
    echo "$category|$name|$url|$duration|$status" >> "$RESULTS_FILE"
}

# 测试代理连接
test_proxy_sources() {
    print_section "1. 测试代理连接"
    
    # 代理配置
    declare -a proxy_ports=(1087 7890 8080 3128 10809)
    declare -a proxy_names=("V2Ray" "Clash" "HTTP代理" "Squid" "ShadowsocksR")
    
    BEST_PROXY=""
    BEST_PROXY_TIME=999
    
    for i in "${!proxy_ports[@]}"; do
        port="${proxy_ports[$i]}"
        name="${proxy_names[$i]}"
        proxy_url="http://127.0.0.1:$port"
        
        print_test "$name ($port)"
        start_time=$(date +%s)
        
        if timeout_test "curl -s -I --connect-timeout 3 --max-time $TIMEOUT --proxy '$proxy_url' https://www.google.com" "$name"; then
            end_time=$(date +%s)
            duration=$((end_time - start_time))
            print_success "成功 (${duration}s)"
            record_result "PROXY" "$name" "$proxy_url" "$duration" "SUCCESS"
            
            if [ $duration -lt $BEST_PROXY_TIME ]; then
                BEST_PROXY="$proxy_url"
                BEST_PROXY_TIME=$duration
            fi
        else
            print_fail "失败"
            record_result "PROXY" "$name" "$proxy_url" "$TIMEOUT" "FAIL"
        fi
    done
    
    if [ -n "$BEST_PROXY" ]; then
        print_success "最佳代理: $BEST_PROXY (${BEST_PROXY_TIME}s)"
        export http_proxy="$BEST_PROXY"
        export https_proxy="$BEST_PROXY"
    else
        echo -e "${YELLOW}  ⚠️  无可用代理，使用直连${NC}"
    fi
}

# 测试Docker镜像源
test_docker_registries() {
    print_section "2. 测试Docker镜像源"
    
    # Docker镜像源配置
    declare -a docker_names=("Docker官方" "中科大" "网易" "DaoCloud" "Azure中国" "阿里云" "腾讯云" "华为云")
    declare -a docker_urls=(
        "https://registry-1.docker.io"
        "https://docker.mirrors.ustc.edu.cn"
        "https://hub-mirror.c.163.com"
        "https://f1361db2.m.daocloud.io"
        "https://dockerhub.azk8s.cn"
        "https://registry.cn-hangzhou.aliyuncs.com"
        "https://mirror.ccs.tencentyun.com"
        "https://05f073ad3c0010ea0f4bc00b7105ec20.mirror.swr.myhuaweicloud.com"
    )
    
    BEST_DOCKER=""
    BEST_DOCKER_TIME=999
    
    for i in "${!docker_names[@]}"; do
        name="${docker_names[$i]}"
        url="${docker_urls[$i]}"
        
        print_test "$name"
        start_time=$(date +%s)
        
        # 测试多种方式
        success=false
        if timeout_test "curl -s --connect-timeout 3 --max-time $TIMEOUT '$url/v2/'" "Docker-v2-$name"; then
            success=true
        elif timeout_test "curl -s --connect-timeout 3 --max-time $TIMEOUT -I '$url'" "Docker-basic-$name"; then
            success=true
        elif timeout_test "ping -c 1 -W 2000 \$(echo '$url' | sed 's|https\\?://||' | cut -d/ -f1)" "Docker-ping-$name"; then
            success=true
        fi
        
        if [ "$success" = true ]; then
            end_time=$(date +%s)
            duration=$((end_time - start_time))
            print_success "成功 (${duration}s)"
            record_result "DOCKER" "$name" "$url" "$duration" "SUCCESS"
            
            if [ $duration -lt $BEST_DOCKER_TIME ]; then
                BEST_DOCKER="$url"
                BEST_DOCKER_TIME=$duration
            fi
        else
            print_timeout
            record_result "DOCKER" "$name" "$url" "$TIMEOUT" "TIMEOUT"
        fi
    done
    
    if [ -n "$BEST_DOCKER" ]; then
        print_success "最佳Docker源: $BEST_DOCKER (${BEST_DOCKER_TIME}s)"
    fi
}

# 测试Python包源
test_python_sources() {
    print_section "3. 测试Python包源"
    
    # Python包源配置
    declare -a python_names=("PyPI官方" "清华大学" "阿里云" "中科大" "豆瓣" "华为云" "腾讯云" "网易" "百度")
    declare -a python_urls=(
        "https://pypi.org/simple/"
        "https://pypi.tuna.tsinghua.edu.cn/simple/"
        "https://mirrors.aliyun.com/pypi/simple/"
        "https://pypi.mirrors.ustc.edu.cn/simple/"
        "https://pypi.douban.com/simple/"
        "https://repo.huaweicloud.com/repository/pypi/simple/"
        "https://mirrors.cloud.tencent.com/pypi/simple/"
        "https://mirrors.163.com/pypi/simple/"
        "https://mirror.baidu.com/pypi/simple/"
    )
    
    BEST_PYTHON=""
    BEST_PYTHON_TIME=999
    
    for i in "${!python_names[@]}"; do
        name="${python_names[$i]}"
        url="${python_urls[$i]}"
        
        print_test "$name"
        start_time=$(date +%s)
        
        if timeout_test "curl -s --connect-timeout 3 --max-time $TIMEOUT '$url'" "Python-$name"; then
            end_time=$(date +%s)
            duration=$((end_time - start_time))
            print_success "成功 (${duration}s)"
            record_result "PYTHON" "$name" "$url" "$duration" "SUCCESS"
            
            if [ $duration -lt $BEST_PYTHON_TIME ]; then
                BEST_PYTHON="$url"
                BEST_PYTHON_TIME=$duration
            fi
        else
            print_timeout
            record_result "PYTHON" "$name" "$url" "$TIMEOUT" "TIMEOUT"
        fi
    done
    
    if [ -n "$BEST_PYTHON" ]; then
        print_success "最佳Python源: $BEST_PYTHON (${BEST_PYTHON_TIME}s)"
    fi
}

# 测试Go代理
test_go_proxies() {
    print_section "4. 测试Go模块代理"
    
    # Go代理配置
    declare -a go_names=("Go官方" "七牛云" "阿里云" "中科大" "GoProxy.CN" "GoProxy.IO" "腾讯云")
    declare -a go_urls=(
        "https://proxy.golang.org"
        "https://goproxy.cn"
        "https://mirrors.aliyun.com/goproxy/"
        "https://goproxy.ustc.edu.cn"
        "https://goproxy.cn"
        "https://goproxy.io"
        "https://mirrors.cloud.tencent.com/go/"
    )
    
    BEST_GO=""
    BEST_GO_TIME=999
    
    for i in "${!go_names[@]}"; do
        name="${go_names[$i]}"
        url="${go_urls[$i]}"
        
        print_test "$name"
        start_time=$(date +%s)
        
        if timeout_test "curl -s --connect-timeout 3 --max-time $TIMEOUT '$url'" "Go-$name"; then
            end_time=$(date +%s)
            duration=$((end_time - start_time))
            print_success "成功 (${duration}s)"
            record_result "GO" "$name" "$url" "$duration" "SUCCESS"
            
            if [ $duration -lt $BEST_GO_TIME ]; then
                BEST_GO="$url"
                BEST_GO_TIME=$duration
            fi
        else
            print_timeout
            record_result "GO" "$name" "$url" "$TIMEOUT" "TIMEOUT"
        fi
    done
    
    if [ -n "$BEST_GO" ]; then
        print_success "最佳Go代理: $BEST_GO (${BEST_GO_TIME}s)"
    fi
}

# 测试Linux包源
test_linux_sources() {
    print_section "5. 测试Linux包源（Debian/Alpine）"
    
    # Debian源配置
    declare -a debian_names=("Debian官方" "清华大学" "中科大" "阿里云" "华为云" "网易")
    declare -a debian_urls=(
        "http://deb.debian.org/debian"
        "https://mirrors.tuna.tsinghua.edu.cn/debian"
        "https://mirrors.ustc.edu.cn/debian"
        "https://mirrors.aliyun.com/debian"
        "https://repo.huaweicloud.com/debian"
        "https://mirrors.163.com/debian"
    )
    
    BEST_DEBIAN=""
    BEST_DEBIAN_TIME=999
    
    for i in "${!debian_names[@]}"; do
        name="${debian_names[$i]}"
        url="${debian_urls[$i]}"
        
        print_test "Debian-$name"
        start_time=$(date +%s)
        
        if timeout_test "curl -s --connect-timeout 3 --max-time $TIMEOUT '$url/dists/bookworm/Release'" "Debian-$name"; then
            end_time=$(date +%s)
            duration=$((end_time - start_time))
            print_success "成功 (${duration}s)"
            record_result "DEBIAN" "$name" "$url" "$duration" "SUCCESS"
            
            if [ $duration -lt $BEST_DEBIAN_TIME ]; then
                BEST_DEBIAN="$url"
                BEST_DEBIAN_TIME=$duration
            fi
        else
            print_timeout
            record_result "DEBIAN" "$name" "$url" "$TIMEOUT" "TIMEOUT"
        fi
    done
    
    # Alpine源配置
    declare -a alpine_names=("Alpine官方" "清华大学" "中科大" "阿里云")
    declare -a alpine_urls=(
        "http://dl-cdn.alpinelinux.org/alpine"
        "https://mirrors.tuna.tsinghua.edu.cn/alpine"
        "https://mirrors.ustc.edu.cn/alpine"
        "https://mirrors.aliyun.com/alpine"
    )
    
    BEST_ALPINE=""
    BEST_ALPINE_TIME=999
    
    for i in "${!alpine_names[@]}"; do
        name="${alpine_names[$i]}"
        url="${alpine_urls[$i]}"
        
        print_test "Alpine-$name"
        start_time=$(date +%s)
        
        if timeout_test "curl -s --connect-timeout 3 --max-time $TIMEOUT '$url/v3.18/main/'" "Alpine-$name"; then
            end_time=$(date +%s)
            duration=$((end_time - start_time))
            print_success "成功 (${duration}s)"
            record_result "ALPINE" "$name" "$url" "$duration" "SUCCESS"
            
            if [ $duration -lt $BEST_ALPINE_TIME ]; then
                BEST_ALPINE="$url"
                BEST_ALPINE_TIME=$duration
            fi
        else
            print_timeout
            record_result "ALPINE" "$name" "$url" "$TIMEOUT" "TIMEOUT"
        fi
    done
    
    if [ -n "$BEST_DEBIAN" ]; then
        print_success "最佳Debian源: $BEST_DEBIAN (${BEST_DEBIAN_TIME}s)"
    fi
    if [ -n "$BEST_ALPINE" ]; then
        print_success "最佳Alpine源: $BEST_ALPINE (${BEST_ALPINE_TIME}s)"
    fi
}

# 生成最优配置
generate_optimal_config() {
    print_section "6. 生成最优配置"
    
    # 生成JSON配置文件
    cat > "$BEST_CONFIG_FILE" << EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "test_timeout": $TIMEOUT,
  "optimal_sources": {
    "proxy": "${BEST_PROXY:-null}",
    "docker_registry": "${BEST_DOCKER:-https://registry-1.docker.io}",
    "python_index": "${BEST_PYTHON:-https://pypi.org/simple/}",
    "go_proxy": "${BEST_GO:-https://proxy.golang.org}",
    "debian_source": "${BEST_DEBIAN:-http://deb.debian.org/debian}",
    "alpine_source": "${BEST_ALPINE:-http://dl-cdn.alpinelinux.org/alpine}"
  },
  "performance": {
    "proxy_time": ${BEST_PROXY_TIME:-999},
    "docker_time": ${BEST_DOCKER_TIME:-999},
    "python_time": ${BEST_PYTHON_TIME:-999},
    "go_time": ${BEST_GO_TIME:-999},
    "debian_time": ${BEST_DEBIAN_TIME:-999},
    "alpine_time": ${BEST_ALPINE_TIME:-999}
  }
}
EOF

    # 生成Docker daemon配置
    cat > docker-daemon-optimal.json << EOF
{
  "experimental": false,
  "features": {
    "buildkit": true
  },
  "registry-mirrors": [
    "${BEST_DOCKER:-https://registry-1.docker.io}"
  ],
  "builder": {
    "gc": {
      "defaultKeepStorage": "20GB",
      "enabled": true
    }
  }
}
EOF

    # 生成环境变量脚本
    cat > scripts/setup_optimal_env.sh << EOF
#!/bin/bash

# 最优环境变量设置 - 自动生成于 $(date)
echo "🔧 设置最优构建环境..."

EOF

    if [ -n "$BEST_PROXY" ]; then
        cat >> scripts/setup_optimal_env.sh << EOF
# 设置代理
export http_proxy="$BEST_PROXY"
export https_proxy="$BEST_PROXY"
export HTTP_PROXY="$BEST_PROXY"
export HTTPS_PROXY="$BEST_PROXY"
echo "✅ 代理: $BEST_PROXY"

EOF
    fi

    cat >> scripts/setup_optimal_env.sh << EOF
# 设置包源
export PIP_INDEX_URL="${BEST_PYTHON:-https://pypi.org/simple/}"
export PIP_TRUSTED_HOST=\$(echo "${BEST_PYTHON:-https://pypi.org/simple/}" | sed 's|https\\?://||' | cut -d/ -f1)
export GOPROXY="${BEST_GO:-https://proxy.golang.org},direct"
export GOSUMDB=off

# Docker主机IP
if [[ "\$OSTYPE" == "darwin"* ]]; then
    export DOCKER_HOST_IP="host.docker.internal"
else
    export DOCKER_HOST_IP="172.17.0.1"
fi

echo "✅ Python包源: ${BEST_PYTHON:-https://pypi.org/simple/}"
echo "✅ Go代理: ${BEST_GO:-https://proxy.golang.org}"
echo "✅ Docker镜像源: ${BEST_DOCKER:-https://registry-1.docker.io}"
echo "🎉 最优环境设置完成！"
EOF

    chmod +x scripts/setup_optimal_env.sh
    
    print_success "配置文件已生成:"
    echo "  📄 optimal_config.json: 完整测试结果"
    echo "  🐳 docker-daemon-optimal.json: Docker优化配置" 
    echo "  📝 scripts/setup_optimal_env.sh: 环境变量脚本"
}

# 显示测试结果
show_test_results() {
    print_section "7. 测试结果总结"
    
    echo ""
    echo -e "${BLUE}📊 最优配置总结：${NC}"
    echo -e "  🌐 代理: ${BEST_PROXY:-${RED}无${NC}}"
    echo -e "  🐳 Docker源: ${BEST_DOCKER:-${RED}默认${NC}} (${BEST_DOCKER_TIME}s)"
    echo -e "  🐍 Python源: ${BEST_PYTHON:-${RED}默认${NC}} (${BEST_PYTHON_TIME}s)"
    echo -e "  🚀 Go代理: ${BEST_GO:-${RED}默认${NC}} (${BEST_GO_TIME}s)"
    echo -e "  🐧 Debian源: ${BEST_DEBIAN:-${RED}默认${NC}} (${BEST_DEBIAN_TIME}s)"
    echo -e "  🏔️  Alpine源: ${BEST_ALPINE:-${RED}默认${NC}} (${BEST_ALPINE_TIME}s)"
    
    echo ""
    echo -e "${BLUE}📈 详细测试结果：${NC}"
    if [ -f "$RESULTS_FILE" ]; then
        echo -e "${CYAN}成功的连接：${NC}"
        grep "SUCCESS" "$RESULTS_FILE" | while IFS='|' read -r category name url duration status; do
            echo "  ✅ $category - $name: ${duration}s"
        done
        
        echo -e "${YELLOW}失败的连接：${NC}"
        grep -E "FAIL|TIMEOUT" "$RESULTS_FILE" | while IFS='|' read -r category name url duration status; do
            echo "  ❌ $category - $name: $status"
        done
    fi
    
    echo ""
    echo -e "${GREEN}🚀 下一步使用方法：${NC}"
    echo "  1. source scripts/setup_optimal_env.sh  # 设置最优环境"
    echo "  2. 复制 docker-daemon-optimal.json 到 ~/.docker/daemon.json"
    echo "  3. 重启Docker服务应用新的镜像源配置"
    echo "  4. 使用优化的构建脚本进行构建"
}

# 主函数
main() {
    # 检查依赖
    if ! command -v curl >/dev/null 2>&1; then
        echo -e "${RED}❌ 需要安装 curl${NC}"
        exit 1
    fi
    
    # 设置总超时
    (
        sleep $MAX_TOTAL_TIME
        echo -e "\n${RED}⏰ 总测试超时 ($MAX_TOTAL_TIME 秒)，强制退出${NC}"
        pkill -f "comprehensive_source_tester" 2>/dev/null || true
    ) &
    GLOBAL_TIMER_PID=$!
    
    # 清理函数
    cleanup() {
        kill $GLOBAL_TIMER_PID 2>/dev/null || true
        rm -f "$RESULTS_FILE"
    }
    trap cleanup EXIT
    
    # 初始化
    rm -f "$RESULTS_FILE"
    cd "$PROJECT_ROOT"
    
    print_header
    
    # 执行测试
    test_proxy_sources
    test_docker_registries  
    test_python_sources
    test_go_proxies
    test_linux_sources
    generate_optimal_config
    show_test_results
    
    # 清理
    kill $GLOBAL_TIMER_PID 2>/dev/null || true
    
    print_success "🎉 全面测试完成！最优配置已保存。"
}

# 如果直接运行脚本
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi 