#!/bin/bash

# Docker代理设置脚本
# 解决Docker容器访问主机代理的问题

set -e

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
    echo "║              Docker 代理配置器                            ║"
    echo "║      解决容器访问主机代理的网络连接问题                     ║"
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

# 检测主机代理
detect_host_proxy() {
    print_section "1. 检测主机代理"
    
    # 测试常见代理端口
    for port in 1087 7890 8080 3128; do
        if curl -s -I --connect-timeout 2 --max-time 3 --proxy "http://127.0.0.1:$port" https://www.google.com >/dev/null 2>&1; then
            HOST_PROXY_PORT=$port
            HOST_PROXY_URL="http://127.0.0.1:$port"
            print_success "发现主机代理: $HOST_PROXY_URL"
            return 0
        fi
    done
    
    print_warning "未发现可用的主机代理"
    return 1
}

# 获取Docker主机IP
get_docker_host_ip() {
    print_section "2. 获取Docker主机IP"
    
    # 在macOS上，Docker Desktop使用host.docker.internal
    if [[ "$OSTYPE" == "darwin"* ]]; then
        DOCKER_HOST_IP="host.docker.internal"
        print_success "macOS Docker主机IP: $DOCKER_HOST_IP"
        return 0
    fi
    
    # 在Linux上，尝试获取docker0接口IP
    if command -v ip >/dev/null 2>&1; then
        DOCKER_HOST_IP=$(ip route | grep docker0 | awk '{print $9}' | head -1)
        if [ -n "$DOCKER_HOST_IP" ]; then
            print_success "Linux Docker主机IP: $DOCKER_HOST_IP"
            return 0
        fi
    fi
    
    # 默认使用172.17.0.1（Docker默认网关）
    DOCKER_HOST_IP="172.17.0.1"
    print_warning "使用默认Docker主机IP: $DOCKER_HOST_IP"
}

# 测试Docker容器代理连接
test_docker_proxy_connection() {
    print_section "3. 测试Docker容器代理连接"
    
    if [ -z "$HOST_PROXY_PORT" ]; then
        print_warning "跳过代理测试（无主机代理）"
        return 1
    fi
    
    DOCKER_PROXY_URL="http://$DOCKER_HOST_IP:$HOST_PROXY_PORT"
    
    echo "测试从Docker容器访问主机代理..."
    echo "代理地址: $DOCKER_PROXY_URL"
    
    # 启动测试容器来验证代理连接
    docker run --rm alpine:latest sh -c "
        apk add --no-cache curl >/dev/null 2>&1 && 
        curl -s -I --connect-timeout 3 --max-time 5 --proxy '$DOCKER_PROXY_URL' https://www.google.com >/dev/null 2>&1
    " && {
        print_success "Docker容器可以访问主机代理"
        DOCKER_PROXY_WORKS=true
        return 0
    } || {
        print_error "Docker容器无法访问主机代理"
        DOCKER_PROXY_WORKS=false
        return 1
    }
}

# 生成Docker代理配置
generate_docker_proxy_config() {
    print_section "4. 生成Docker代理配置"
    
    # 创建Docker daemon代理配置
    if [ "$DOCKER_PROXY_WORKS" = true ]; then
        cat > ~/.docker/config.json << EOF
{
  "proxies": {
    "default": {
      "httpProxy": "$DOCKER_PROXY_URL",
      "httpsProxy": "$DOCKER_PROXY_URL",
      "noProxy": "localhost,127.0.0.1,::1"
    }
  }
}
EOF
        print_success "已创建Docker客户端代理配置: ~/.docker/config.json"
    fi
    
    # 生成构建时代理参数
    cat > scripts/docker_build_with_proxy.sh << 'EOF'
#!/bin/bash

# Docker构建代理脚本
set -e

# 检测系统类型和代理设置
if [[ "$OSTYPE" == "darwin"* ]]; then
    DOCKER_HOST_IP="host.docker.internal"
else
    DOCKER_HOST_IP="172.17.0.1"
fi

EOF

    if [ -n "$HOST_PROXY_PORT" ]; then
        cat >> scripts/docker_build_with_proxy.sh << EOF
# 代理设置
PROXY_URL="http://\$DOCKER_HOST_IP:$HOST_PROXY_PORT"
PROXY_ARGS="--build-arg http_proxy=\$PROXY_URL --build-arg https_proxy=\$PROXY_URL --build-arg HTTP_PROXY=\$PROXY_URL --build-arg HTTPS_PROXY=\$PROXY_URL"

echo "🌐 使用代理构建: \$PROXY_URL"

EOF
    else
        cat >> scripts/docker_build_with_proxy.sh << 'EOF'
# 无代理设置
PROXY_ARGS=""
echo "🔗 直连构建（无代理）"

EOF
    fi

    cat >> scripts/docker_build_with_proxy.sh << 'EOF'
# 构建函数
build_with_proxy() {
    local dockerfile=$1
    local tag=$2
    local context=${3:-.}
    
    echo "🚀 构建镜像: $tag"
    docker build $PROXY_ARGS -f "$dockerfile" -t "$tag" "$context"
}

# 导出函数供其他脚本使用
export -f build_with_proxy
export PROXY_ARGS
export DOCKER_HOST_IP

echo "✅ Docker代理构建环境已设置"
EOF

    chmod +x scripts/docker_build_with_proxy.sh
    print_success "已创建Docker代理构建脚本: scripts/docker_build_with_proxy.sh"
}

# 生成优化的Dockerfile
generate_optimized_dockerfiles() {
    print_section "5. 生成优化的Dockerfile"
    
    # 创建支持代理的Python Dockerfile
    cat > Dockerfile.proxy << 'DOCKERFILE'
# 支持代理的Python快速构建Dockerfile
FROM python:3.9-alpine

# 接收构建时代理参数
ARG http_proxy
ARG https_proxy
ARG HTTP_PROXY
ARG HTTPS_PROXY

# 设置代理环境变量（如果提供）
ENV http_proxy=${http_proxy}
ENV https_proxy=${https_proxy}
ENV HTTP_PROXY=${HTTP_PROXY}
ENV HTTPS_PROXY=${HTTPS_PROXY}

WORKDIR /app

# 创建非root用户
RUN adduser -D appuser

# 安装系统依赖（如果有代理会使用）
RUN apk add --no-cache curl tzdata

# 复制requirements并安装Python包
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt || \
    pip install --no-cache-dir \
        clickhouse-driver \
        pynats \
        aiofiles \
        python-dateutil \
        pytz

# 复制应用代码
COPY . .
RUN chown -R appuser:appuser /app

# 清理代理环境变量（安全考虑）
ENV http_proxy=
ENV https_proxy=
ENV HTTP_PROXY=
ENV HTTPS_PROXY=

USER appuser
EXPOSE 8080

CMD ["python", "-m", "http.server", "8080"]
DOCKERFILE

    print_success "已创建支持代理的Dockerfile: Dockerfile.proxy"
    
    # 创建支持代理的Go Dockerfile
    cat > services/go-collector/Dockerfile.proxy << 'DOCKERFILE'
# 支持代理的Go快速构建Dockerfile
FROM golang:1.20-alpine AS builder

# 接收构建时代理参数
ARG http_proxy
ARG https_proxy
ARG HTTP_PROXY
ARG HTTPS_PROXY

# 设置代理环境变量
ENV http_proxy=${http_proxy}
ENV https_proxy=${https_proxy}
ENV HTTP_PROXY=${HTTP_PROXY}
ENV HTTPS_PROXY=${HTTPS_PROXY}

WORKDIR /app

# 安装构建依赖
RUN apk add --no-cache git ca-certificates tzdata

# 设置Go环境
ENV CGO_ENABLED=0
ENV GOOS=linux
ENV GOARCH=amd64
ENV GOPROXY=https://proxy.golang.org,direct

# 复制Go模块文件
COPY go.mod go.sum ./
RUN go mod download

# 复制源代码并构建
COPY . .
RUN go build -ldflags="-w -s" -o collector ./cmd/collector

# 运行时镜像
FROM alpine:latest
RUN apk --no-cache add ca-certificates tzdata
WORKDIR /root/
COPY --from=builder /app/collector .
EXPOSE 8080
CMD ["./collector"]
DOCKERFILE

    print_success "已创建支持代理的Go Dockerfile: services/go-collector/Dockerfile.proxy"
}

# 创建测试脚本
create_proxy_test_script() {
    print_section "6. 创建代理测试脚本"
    
    cat > scripts/test_docker_proxy.sh << 'EOF'
#!/bin/bash

# Docker代理测试脚本
echo "🧪 测试Docker代理连接..."

# 检测主机IP
if [[ "$OSTYPE" == "darwin"* ]]; then
    HOST_IP="host.docker.internal"
else
    HOST_IP="172.17.0.1"
fi

# 测试代理端口
for port in 1087 7890 8080; do
    echo -n "测试代理 $HOST_IP:$port... "
    if docker run --rm alpine:latest sh -c "
        apk add --no-cache curl >/dev/null 2>&1 && 
        curl -s -I --connect-timeout 3 --max-time 5 --proxy 'http://$HOST_IP:$port' https://www.google.com >/dev/null 2>&1
    "; then
        echo "✅ 成功"
        echo "可用代理: http://$HOST_IP:$port"
        exit 0
    else
        echo "❌ 失败"
    fi
done

echo "⚠️  所有代理测试失败，将使用直连构建"
EOF

    chmod +x scripts/test_docker_proxy.sh
    print_success "已创建Docker代理测试脚本: scripts/test_docker_proxy.sh"
}

# 主函数
main() {
    print_header
    
    # 初始化变量
    HOST_PROXY_PORT=""
    HOST_PROXY_URL=""
    DOCKER_HOST_IP=""
    DOCKER_PROXY_WORKS=false
    
    # 执行检测和配置
    detect_host_proxy || true
    get_docker_host_ip
    test_docker_proxy_connection || true
    generate_docker_proxy_config
    generate_optimized_dockerfiles
    create_proxy_test_script
    
    print_section "7. 总结"
    echo "📊 配置结果："
    echo "   🖥️  主机代理: ${HOST_PROXY_URL:-无}"
    echo "   🐳 Docker主机IP: $DOCKER_HOST_IP"
    echo "   🔗 容器代理连接: $([ "$DOCKER_PROXY_WORKS" = true ] && echo "✅ 成功" || echo "❌ 失败")"
    
    echo ""
    echo "📝 生成的文件："
    echo "   - scripts/docker_build_with_proxy.sh: 代理构建脚本"
    echo "   - scripts/test_docker_proxy.sh: 代理测试脚本"
    echo "   - Dockerfile.proxy: 支持代理的Python Dockerfile"
    echo "   - services/go-collector/Dockerfile.proxy: 支持代理的Go Dockerfile"
    
    if [ "$DOCKER_PROXY_WORKS" = true ]; then
        echo "   - ~/.docker/config.json: Docker客户端代理配置"
    fi
    
    echo ""
    echo "🚀 下一步："
    echo "   1. 运行 ./scripts/test_docker_proxy.sh 测试代理连接"
    echo "   2. 使用 source scripts/docker_build_with_proxy.sh 设置构建环境"
    echo "   3. 使用 build_with_proxy Dockerfile.proxy your-image:tag 构建镜像"
    
    print_success "Docker代理配置完成！"
}

# 运行主函数
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi 