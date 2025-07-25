#!/bin/bash

# 简化的Docker腾讯云镜像源配置脚本
set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🐳 配置Docker使用腾讯云镜像源...${NC}"

# 检测代理
PROXY_URL=""
if [ -n "$HTTP_PROXY" ]; then
    PROXY_URL="$HTTP_PROXY"
    echo -e "${GREEN}✅ 检测到代理: $PROXY_URL${NC}"
fi

# 创建Docker配置目录
mkdir -p ~/.docker

# 创建daemon.json配置
cat > ~/.docker/daemon.json << 'EOF'
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://ccr.ccs.tencentyun.com",
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ],
  "experimental": false,
  "features": {
    "buildkit": true
  }
}
EOF

echo -e "${GREEN}✅ 已配置Docker镜像源: ~/.docker/daemon.json${NC}"

# 创建腾讯云优化的基础设施配置
cat > docker/docker-compose.infrastructure.tencent.yml << 'EOF'
services:
  nats:
    image: nats:2.9.15-alpine
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

  clickhouse:
    image: clickhouse/clickhouse-server:23.3-alpine
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

  redis:
    image: redis:7-alpine
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
EOF

echo -e "${GREEN}✅ 已创建腾讯云基础设施配置: docker/docker-compose.infrastructure.tencent.yml${NC}"

# 创建构建脚本
cat > scripts/docker_build_with_proxy.sh << 'EOF'
#!/bin/bash

# Docker代理构建脚本
set -e

# macOS Docker使用host.docker.internal访问宿主机
DOCKER_HOST_IP="host.docker.internal"

# 检测代理
if [ -n "$HTTP_PROXY" ]; then
    # 将127.0.0.1替换为Docker主机IP
    DOCKER_PROXY_URL=$(echo "$HTTP_PROXY" | sed "s/127\.0\.0\.1/$DOCKER_HOST_IP/g")
    PROXY_ARGS="--build-arg http_proxy=$DOCKER_PROXY_URL --build-arg https_proxy=$DOCKER_PROXY_URL"
    echo "🌐 使用代理构建: $DOCKER_PROXY_URL"
else
    PROXY_ARGS=""
    echo "🔗 直连构建（无代理）"
fi

# 构建函数
build_with_proxy() {
    local dockerfile=$1
    local tag=$2
    local context=${3:-.}
    
    echo "🚀 构建镜像: $tag"
    docker build $PROXY_ARGS -f "$dockerfile" -t "$tag" "$context"
}

# 导出函数
export -f build_with_proxy
export PROXY_ARGS

echo "✅ Docker代理构建环境已设置"
EOF

chmod +x scripts/docker_build_with_proxy.sh
echo -e "${GREEN}✅ 已创建代理构建脚本: scripts/docker_build_with_proxy.sh${NC}"

echo -e "${YELLOW}⚠️  请重启Docker Desktop以应用镜像源配置${NC}"
echo -e "${BLUE}下一步: docker-compose -f docker/docker-compose.infrastructure.tencent.yml up -d${NC}"