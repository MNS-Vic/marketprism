#!/bin/bash

# Docker腾讯云镜像源和代理配置脚本
# 配置腾讯云镜像源加速Docker镜像拉取，并设置代理

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
    echo "║          Docker 腾讯云镜像源配置器                         ║"
    echo "║         配置腾讯云镜像源 + 宿主机代理                      ║"
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

# 检测操作系统
detect_os() {
    print_section "1. 检测操作系统"
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
        DOCKER_HOST_IP="host.docker.internal"
        print_success "检测到 macOS 系统"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
        DOCKER_HOST_IP="172.17.0.1"
        print_success "检测到 Linux 系统"
    else
        OS="unknown"
        print_warning "未知操作系统: $OSTYPE"
    fi
}

# 检测宿主机代理
detect_host_proxy() {
    print_section "2. 检测宿主机代理"
    
    # 检查环境变量
    if [ -n "$HTTP_PROXY" ]; then
        HOST_PROXY_URL="$HTTP_PROXY"
        print_success "从环境变量发现代理: $HOST_PROXY_URL"
        HOST_PROXY_PORT=$(echo $HTTP_PROXY | sed -n 's/.*:\([0-9]*\)$/\1/p')
        return 0
    fi
    
    # 测试常见代理端口
    for port in 1087 7890 8080 3128; do
        if curl -s -I --connect-timeout 2 --max-time 3 --proxy "http://127.0.0.1:$port" https://www.google.com >/dev/null 2>&1; then
            HOST_PROXY_PORT=$port
            HOST_PROXY_URL="http://127.0.0.1:$port"
            print_success "发现宿主机代理: $HOST_PROXY_URL"
            return 0
        fi
    done
    
    print_warning "未发现可用的宿主机代理"
    return 1
}

# 配置Docker镜像源 (腾讯云)
configure_docker_mirrors() {
    print_section "3. 配置Docker腾讯云镜像源"
    
    # 创建Docker daemon配置目录
    DOCKER_CONFIG_DIR=""
    if [[ "$OS" == "macos" ]]; then
        # macOS Docker Desktop 配置通过GUI或~/.docker/daemon.json
        DOCKER_CONFIG_DIR="$HOME/.docker"
        DAEMON_CONFIG="$DOCKER_CONFIG_DIR/daemon.json"
    elif [[ "$OS" == "linux" ]]; then
        # Linux Docker daemon配置
        DOCKER_CONFIG_DIR="/etc/docker"
        DAEMON_CONFIG="$DOCKER_CONFIG_DIR/daemon.json"
        # 确保目录存在
        sudo mkdir -p "$DOCKER_CONFIG_DIR" 2>/dev/null || true
    fi
    
    # 创建daemon.json配置文件
    DAEMON_JSON_CONTENT='{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://ccr.ccs.tencentyun.com",
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ],
  "insecure-registries": [],
  "experimental": false,
  "features": {
    "buildkit": true
  },
  "builder": {
    "gc": {
      "enabled": true,
      "defaultKeepStorage": "20GB"
    }
  }'
    
    # 如果有代理，添加代理配置
    if [ -n "$HOST_PROXY_URL" ]; then
        DAEMON_JSON_CONTENT=$(echo "$DAEMON_JSON_CONTENT" | jq --arg proxy "$HOST_PROXY_URL" '.proxies = {
          "http-proxy": $proxy,
          "https-proxy": $proxy,
          "no-proxy": "localhost,127.0.0.1,::1,*.tencentyun.com,*.tencent.com"
        }')
    fi
    
    # 写入配置文件
    if [[ "$OS" == "macos" ]]; then
        mkdir -p "$DOCKER_CONFIG_DIR"
        echo "$DAEMON_JSON_CONTENT" > "$DAEMON_CONFIG"
        print_success "已配置Docker Desktop镜像源: $DAEMON_CONFIG"
        print_warning "请重启Docker Desktop以应用配置"
    elif [[ "$OS" == "linux" ]]; then
        echo "$DAEMON_JSON_CONTENT" | sudo tee "$DAEMON_CONFIG" > /dev/null
        print_success "已配置Docker daemon镜像源: $DAEMON_CONFIG"
        
        # 重启Docker服务
        if systemctl is-active --quiet docker; then
            print_section "重启Docker服务..."
            sudo systemctl daemon-reload
            sudo systemctl restart docker
            print_success "Docker服务已重启"
        fi
    fi
}

# 创建优化的Docker Compose文件
create_optimized_compose() {
    print_section "4. 创建优化的Docker Compose配置"
    
    # 创建使用腾讯云镜像的compose文件
    cat > docker/docker-compose.infrastructure.tencent.yml << 'EOF'
services:
  nats:
    image: ccr.ccs.tencentyun.com/tke-market/nats:2.9.15-alpine
    container_name: marketprism-nats
    ports:
      - "4222:4222"
      - "8222:8222"
      - "6222:6222"
    command: [
      "--jetstream",
      "--store_dir=/data",
      "--max_memory_store=1GB",
      "--max_file_store=10GB",
      "--http_port=8222"
    ]
    volumes:
      - ./data/nats:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:8222/healthz"]
      interval: 10s
      timeout: 5s
      retries: 3
    networks:
      - marketprism-net

  clickhouse:
    image: ccr.ccs.tencentyun.com/tke-market/clickhouse-server:23.3
    container_name: marketprism-clickhouse
    ports:
      - "8123:8123"
      - "9000:9000"
    environment:
      CLICKHOUSE_DB: marketprism
      CLICKHOUSE_USER: default
      CLICKHOUSE_PASSWORD: ""
    volumes:
      - ./data/clickhouse-cold:/var/lib/clickhouse
      - ./config/clickhouse-cold:/etc/clickhouse-server/config.d
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:8123/ping"]
      interval: 10s
      timeout: 5s
      retries: 3
    networks:
      - marketprism-net

  redis:
    image: ccr.ccs.tencentyun.com/tke-market/redis:7-alpine
    container_name: marketprism-redis
    ports:
      - "6379:6379"
    volumes:
      - ./data/redis:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
    networks:
      - marketprism-net

networks:
  marketprism-net:
    driver: bridge
    name: marketprism-net

volumes:
  nats-data:
  clickhouse-data:
  redis-data:
EOF
    
    print_success "已创建腾讯云优化的Docker Compose: docker/docker-compose.infrastructure.tencent.yml"
}

# 创建Docker构建脚本
create_build_scripts() {
    print_section "5. 创建Docker构建脚本"
    
    # 更新构建脚本以使用腾讯云镜像源
    cat > scripts/docker_build_with_tencent_proxy.sh << 'EOF'
#!/bin/bash

# Docker腾讯云镜像源 + 代理构建脚本
set -e

# 检测系统类型
if [[ "$OSTYPE" == "darwin"* ]]; then
    DOCKER_HOST_IP="host.docker.internal"
else
    DOCKER_HOST_IP="172.17.0.1"
fi

# 检测代理设置
if [ -n "$HTTP_PROXY" ]; then
    PROXY_URL="$HTTP_PROXY"
    # 将127.0.0.1替换为Docker主机IP
    DOCKER_PROXY_URL=$(echo "$PROXY_URL" | sed "s/127\.0\.0\.1/$DOCKER_HOST_IP/g")
    PROXY_ARGS="--build-arg http_proxy=$DOCKER_PROXY_URL --build-arg https_proxy=$DOCKER_PROXY_URL --build-arg HTTP_PROXY=$DOCKER_PROXY_URL --build-arg HTTPS_PROXY=$DOCKER_PROXY_URL"
    echo "🌐 使用代理构建: $DOCKER_PROXY_URL"
else
    PROXY_ARGS=""
    echo "🔗 直连构建（无代理）"
fi

# 腾讯云镜像源构建参数
MIRROR_ARGS="--build-arg PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple --build-arg PIP_TRUSTED_HOST=mirrors.cloud.tencent.com"

# 构建函数
build_with_tencent_proxy() {
    local dockerfile=$1
    local tag=$2
    local context=${3:-.}
    
    echo "🚀 使用腾讯云镜像源构建: $tag"
    echo "   Dockerfile: $dockerfile"
    echo "   Context: $context"
    
    docker build $PROXY_ARGS $MIRROR_ARGS -f "$dockerfile" -t "$tag" "$context"
}

# 导出函数和变量
export -f build_with_tencent_proxy
export PROXY_ARGS
export MIRROR_ARGS
export DOCKER_HOST_IP

echo "✅ Docker腾讯云构建环境已设置"
EOF
    
    chmod +x scripts/docker_build_with_tencent_proxy.sh
    print_success "已创建腾讯云Docker构建脚本: scripts/docker_build_with_tencent_proxy.sh"
}

# 创建腾讯云优化的Dockerfile
create_tencent_dockerfile() {
    print_section "6. 创建腾讯云优化的Dockerfile"
    
    cat > Dockerfile.tencent << 'DOCKERFILE'
# 腾讯云优化的Python Dockerfile
FROM ccr.ccs.tencentyun.com/tke-market/python:3.9-slim

# 接收构建时代理和镜像源参数
ARG http_proxy
ARG https_proxy
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple
ARG PIP_TRUSTED_HOST=mirrors.cloud.tencent.com

# 设置环境变量
ENV http_proxy=$http_proxy
ENV https_proxy=$https_proxy
ENV HTTP_PROXY=$HTTP_PROXY
ENV HTTPS_PROXY=$HTTPS_PROXY
ENV PIP_INDEX_URL=$PIP_INDEX_URL
ENV PIP_TRUSTED_HOST=$PIP_TRUSTED_HOST

# 更新系统并安装基础工具 (使用腾讯云镜像源)
RUN sed -i 's/deb.debian.org/mirrors.cloud.tencent.com/g' /etc/apt/sources.list && \
    sed -i 's/security.debian.org/mirrors.cloud.tencent.com/g' /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        wget \
        git \
        gcc \
        g++ \
        make \
        pkg-config \
        libffi-dev \
        libssl-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 升级pip并配置腾讯云镜像源
RUN python -m pip install --upgrade pip -i $PIP_INDEX_URL --trusted-host $PIP_TRUSTED_HOST

# 设置工作目录
WORKDIR /app

# 复制requirements文件
COPY requirements.txt .

# 安装Python依赖 (使用腾讯云镜像源)
RUN pip install --no-cache-dir -r requirements.txt -i $PIP_INDEX_URL --trusted-host $PIP_TRUSTED_HOST

# 复制应用代码
COPY . .

# 设置Python路径
ENV PYTHONPATH=/app

# 默认命令
CMD ["python", "-c", "print('MarketPrism Container Ready with Tencent Cloud Mirrors')"]
DOCKERFILE
    
    print_success "已创建腾讯云优化的Dockerfile: Dockerfile.tencent"
}

# 测试配置
test_configuration() {
    print_section "7. 测试配置"
    
    echo "测试腾讯云镜像源连接..."
    
    # 测试腾讯云容器镜像服务
    if curl -s --connect-timeout 5 --max-time 10 https://ccr.ccs.tencentyun.com/v2/ >/dev/null 2>&1; then
        print_success "腾讯云容器镜像服务连接正常"
    else
        print_warning "腾讯云容器镜像服务连接异常"
    fi
    
    # 测试腾讯云PyPI镜像源
    if curl -s --connect-timeout 5 --max-time 10 https://mirrors.cloud.tencent.com/pypi/simple/ >/dev/null 2>&1; then
        print_success "腾讯云PyPI镜像源连接正常"
    else
        print_warning "腾讯云PyPI镜像源连接异常"
    fi
    
    # 如果有代理，测试代理连接
    if [ -n "$HOST_PROXY_URL" ]; then
        if curl -s -I --connect-timeout 3 --max-time 5 --proxy "$HOST_PROXY_URL" https://www.google.com >/dev/null 2>&1; then
            print_success "宿主机代理连接正常: $HOST_PROXY_URL"
        else
            print_warning "宿主机代理连接异常: $HOST_PROXY_URL"
        fi
    fi
}

# 主函数
main() {
    print_header
    
    detect_os
    detect_host_proxy || true
    configure_docker_mirrors
    create_optimized_compose
    create_build_scripts
    create_tencent_dockerfile
    test_configuration
    
    echo
    print_section "✅ 配置完成总结"
    echo "配置的组件:"
    echo "   🐳 Docker镜像源: 腾讯云 + 备用镜像源"
    echo "   🌐 代理设置: $([ -n "$HOST_PROXY_URL" ] && echo "$HOST_PROXY_URL" || echo "无代理")"
    echo "   🖥️  系统类型: $OS"
    echo "   📦 Docker主机IP: $DOCKER_HOST_IP"
    echo
    echo "生成的文件:"
    echo "   - docker/docker-compose.infrastructure.tencent.yml: 腾讯云优化的基础设施"
    echo "   - scripts/docker_build_with_tencent_proxy.sh: 腾讯云构建脚本"
    echo "   - Dockerfile.tencent: 腾讯云优化的Dockerfile"
    echo "   - ~/.docker/daemon.json (macOS) 或 /etc/docker/daemon.json (Linux): Docker镜像源配置"
    echo
    echo "下一步操作:"
    if [[ "$OS" == "macos" ]]; then
        echo "   1. 重启Docker Desktop以应用镜像源配置"
    else
        echo "   1. Docker服务已自动重启"
    fi
    echo "   2. 使用腾讯云基础设施: docker-compose -f docker/docker-compose.infrastructure.tencent.yml up -d"
    echo "   3. 使用腾讯云构建: source scripts/docker_build_with_tencent_proxy.sh && build_with_tencent_proxy Dockerfile.tencent your-image:tag"
    echo
    print_success "Docker腾讯云配置完成！"
}

# 运行主函数
main "$@"