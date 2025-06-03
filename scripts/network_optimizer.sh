#!/bin/bash

# MarketPrism 网络优化器
# 测试和优化不同下载源的连接性能
set -e

# 配置参数
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TIMEOUT=10

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

print_header() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║           MarketPrism 网络优化器                           ║"
    echo "║        测试和优化Docker构建网络性能                        ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_section() {
    echo -e "${CYAN}📋 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

test_connection() {
    local url=$1
    local name=$2
    echo -n "测试 $name ($url)... "
    
    start_time=$(date +%s)
    if timeout $TIMEOUT curl -s -I "$url" >/dev/null 2>&1; then
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        echo -e "${GREEN}✅ 成功 (${duration}s)${NC}"
        return 0
    else
        echo -e "${RED}❌ 失败${NC}"
        return 1
    fi
}

test_proxy() {
    local proxy=$1
    local target=$2
    local name=$3
    echo -n "测试代理 $name ($proxy)... "
    
    start_time=$(date +%s)
    if curl -s -I --connect-timeout 3 --max-time 5 --proxy "$proxy" "$target" >/dev/null 2>&1; then
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        echo -e "${GREEN}✅ 成功 (${duration}s)${NC}"
        return 0
    else
        echo -e "${RED}❌ 失败${NC}"
        return 1
    fi
}

test_docker_registry() {
    local registry=$1
    local name=$2
    echo -n "测试Docker镜像源 $name ($registry)... "
    
    # 测试Docker registry连接
    start_time=$(date +%s)
    
    # 尝试多种测试方法
    if curl -s --connect-timeout 3 --max-time 8 "$registry/v2/" >/dev/null 2>&1; then
        # v2 API测试成功
        test_result="v2_api"
    elif curl -s --connect-timeout 3 --max-time 8 -I "$registry" >/dev/null 2>&1; then
        # 基础连接测试成功
        test_result="basic"
    elif ping -c 1 -W 2000 $(echo "$registry" | sed 's|https\?://||' | cut -d/ -f1) >/dev/null 2>&1; then
        # ping测试成功
        test_result="ping"
    else
        echo -e "${RED}❌ 失败${NC}"
        return 1
    fi
    
    end_time=$(date +%s)
    duration=$((end_time - start_time))
    echo -e "${GREEN}✅ 成功 ($test_result, ${duration}s)${NC}"
    echo "$registry:$duration" >> /tmp/docker_registry_results.txt
    return 0
}

# 主函数
main() {
    cd "$PROJECT_ROOT"
    print_header
    
    # 创建结果文件
    rm -f /tmp/docker_registry_results.txt /tmp/proxy_results.txt /tmp/package_source_results.txt
    
    # 1. 检测代理
    print_section "1. 代理检测"
    PROXY_AVAILABLE=false
    
    # 检测常见代理端口
    for port in 1087 7890 8080 3128; do
        if test_proxy "http://127.0.0.1:$port" "https://www.google.com" "本地代理:$port"; then
            PROXY_URL="http://127.0.0.1:$port"
            PROXY_AVAILABLE=true
            echo "$PROXY_URL" > /tmp/best_proxy.txt
            break
        fi
    done
    
    if [ "$PROXY_AVAILABLE" = true ]; then
        print_success "发现可用代理: $PROXY_URL"
        export http_proxy=$PROXY_URL
        export https_proxy=$PROXY_URL
        export HTTP_PROXY=$PROXY_URL
        export HTTPS_PROXY=$PROXY_URL
    else
        print_warning "未发现可用代理，使用直连"
    fi
    
    # 2. 测试Docker镜像源
    print_section "2. Docker镜像源测试"
    
    # Docker镜像源列表（使用英文键名）
    declare -a docker_names=("Docker_Official" "USTC_Mirror" "163_Mirror" "DaoCloud_Mirror" "Azure_Mirror" "Aliyun_Mirror")
    declare -a docker_urls=("https://registry-1.docker.io" "https://docker.mirrors.ustc.edu.cn" "https://hub-mirror.c.163.com" "https://f1361db2.m.daocloud.io" "https://dockerhub.azk8s.cn" "https://registry.cn-hangzhou.aliyuncs.com")
    
    fastest_registry=""
    fastest_time=999
    
    for i in "${!docker_names[@]}"; do
        name="${docker_names[$i]}"
        registry="${docker_urls[$i]}"
        test_docker_registry "$registry" "$name"
    done
    
    # 选择最快的镜像源
    if [ -f /tmp/docker_registry_results.txt ]; then
        fastest_registry=$(sort -t: -k2 -n /tmp/docker_registry_results.txt | head -1 | cut -d: -f1)
        fastest_time=$(sort -t: -k2 -n /tmp/docker_registry_results.txt | head -1 | cut -d: -f2)
        print_success "最快Docker镜像源: $fastest_registry (${fastest_time}s)"
    fi
    
    # 3. 测试Python包源
    print_section "3. Python包源测试"
    
    declare -a python_names=("PyPI_Official" "Tsinghua_Uni" "Aliyun_Mirror" "USTC_Mirror" "Douban_Mirror")
    declare -a python_urls=("https://pypi.org/simple/" "https://pypi.tuna.tsinghua.edu.cn/simple/" "https://mirrors.aliyun.com/pypi/simple/" "https://pypi.mirrors.ustc.edu.cn/simple/" "https://pypi.douban.com/simple/")
    
    fastest_python=""
    for i in "${!python_names[@]}"; do
        name="${python_names[$i]}"
        source="${python_urls[$i]}"
        if test_connection "$source" "$name"; then
            if [ -z "$fastest_python" ]; then
                fastest_python="$source"
            fi
        fi
    done
    
    if [ -n "$fastest_python" ]; then
        print_success "推荐Python包源: $fastest_python"
        echo "$fastest_python" > /tmp/best_python_source.txt
    fi
    
    # 4. 测试Go代理
    print_section "4. Go模块代理测试"
    
    declare -a go_names=("Go_Official" "Qiniu_Cloud" "Aliyun_Mirror" "USTC_Mirror")
    declare -a go_urls=("https://proxy.golang.org" "https://goproxy.cn" "https://mirrors.aliyun.com/goproxy/" "https://goproxy.ustc.edu.cn")
    
    fastest_go=""
    for i in "${!go_names[@]}"; do
        name="${go_names[$i]}"
        proxy="${go_urls[$i]}"
        if test_connection "$proxy" "$name"; then
            if [ -z "$fastest_go" ]; then
                fastest_go="$proxy"
            fi
        fi
    done
    
    if [ -n "$fastest_go" ]; then
        print_success "推荐Go代理: $fastest_go"
        echo "$fastest_go" > /tmp/best_go_proxy.txt
    fi
    
    # 5. 测试Debian包源
    print_section "5. Debian包源测试"
    
    declare -a debian_names=("Debian_Official" "Tsinghua_Uni" "USTC_Mirror" "Aliyun_Mirror")
    declare -a debian_urls=("http://deb.debian.org/debian" "https://mirrors.tuna.tsinghua.edu.cn/debian" "https://mirrors.ustc.edu.cn/debian" "https://mirrors.aliyun.com/debian")
    
    fastest_debian=""
    for i in "${!debian_names[@]}"; do
        name="${debian_names[$i]}"
        source="${debian_urls[$i]}"
        if test_connection "$source/dists/bookworm/Release" "$name"; then
            if [ -z "$fastest_debian" ]; then
                fastest_debian="$source"
            fi
        fi
    done
    
    if [ -n "$fastest_debian" ]; then
        print_success "推荐Debian源: $fastest_debian"
        echo "$fastest_debian" > /tmp/best_debian_source.txt
    fi
    
    # 6. 生成优化配置
    print_section "6. 生成优化配置"
    generate_optimized_config
    
    # 7. 清理临时文件
    rm -f /tmp/docker_registry_results.txt /tmp/proxy_results.txt /tmp/package_source_results.txt
    
    print_success "网络优化完成！查看生成的配置文件。"
}

generate_optimized_config() {
    # 生成Docker daemon配置
    if [ -n "$fastest_registry" ]; then
        cat > "$PROJECT_ROOT/docker-daemon-optimized.json" << EOF
{
  "experimental": false,
  "features": {
    "buildkit": true
  },
  "registry-mirrors": [
    "$fastest_registry"
  ],
  "builder": {
    "gc": {
      "defaultKeepStorage": "20GB",
      "enabled": true
    }
  }
}
EOF
        print_success "已生成优化的Docker配置: docker-daemon-optimized.json"
    fi
    
    # 生成构建环境变量脚本
    cat > "$PROJECT_ROOT/scripts/setup_build_env.sh" << 'EOF'
#!/bin/bash

# 设置构建环境变量 - 自动生成
set -e

echo "🔧 设置优化的构建环境..."

EOF
    
    # 添加代理配置
    if [ "$PROXY_AVAILABLE" = true ]; then
        cat >> "$PROJECT_ROOT/scripts/setup_build_env.sh" << EOF
# 设置代理
export http_proxy=$PROXY_URL
export https_proxy=$PROXY_URL
export HTTP_PROXY=$PROXY_URL
export HTTPS_PROXY=$PROXY_URL
echo "✅ 代理已设置: $PROXY_URL"

EOF
    fi
    
    # 添加Python源配置
    if [ -f /tmp/best_python_source.txt ]; then
        BEST_PYTHON=$(cat /tmp/best_python_source.txt)
        cat >> "$PROJECT_ROOT/scripts/setup_build_env.sh" << EOF
# 设置Python包源
export PIP_INDEX_URL=$BEST_PYTHON
export PIP_TRUSTED_HOST=\$(echo $BEST_PYTHON | sed 's|https\?://||' | cut -d/ -f1)
echo "✅ Python包源已设置: $BEST_PYTHON"

EOF
    fi
    
    # 添加Go代理配置
    if [ -f /tmp/best_go_proxy.txt ]; then
        BEST_GO=$(cat /tmp/best_go_proxy.txt)
        cat >> "$PROJECT_ROOT/scripts/setup_build_env.sh" << EOF
# 设置Go代理
export GOPROXY=$BEST_GO,direct
export GOSUMDB=off
echo "✅ Go代理已设置: $BEST_GO"

EOF
    fi
    
    cat >> "$PROJECT_ROOT/scripts/setup_build_env.sh" << 'EOF'
echo "🎉 构建环境设置完成！"
EOF
    
    chmod +x "$PROJECT_ROOT/scripts/setup_build_env.sh"
    print_success "已生成构建环境脚本: scripts/setup_build_env.sh"
}

# 如果直接运行脚本
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi 