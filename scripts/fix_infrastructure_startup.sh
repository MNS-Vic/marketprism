#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}===== MarketPrism 基础设施启动修复脚本 =====${NC}"

# 设置代理环境变量
export http_proxy=http://127.0.0.1:1087
export https_proxy=http://127.0.0.1:1087
export ALL_PROXY=socks5://127.0.0.1:1080
export no_proxy=localhost,127.0.0.1

echo -e "${BLUE}设置网络代理...${NC}"
echo "http_proxy: $http_proxy"
echo "https_proxy: $https_proxy"
echo "ALL_PROXY: $ALL_PROXY"

# 设置必要的环境变量
export NATS_URL=nats://localhost:4222
export CLICKHOUSE_HOST=localhost
export CLICKHOUSE_PORT=8123
export CLICKHOUSE_DATABASE=marketprism
export DEV_MODE=true
export API_PORT=8080
export PROMETHEUS_PORT=9090

echo -e "${BLUE}设置环境变量...${NC}"
echo "NATS_URL: $NATS_URL"
echo "CLICKHOUSE_HOST: $CLICKHOUSE_HOST"

# 创建必要的目录
mkdir -p logs
mkdir -p data/clickhouse-cold
mkdir -p data/nats

# 停止现有容器
echo -e "${BLUE}停止现有容器...${NC}"
docker-compose down 2>/dev/null || true

# 清理Docker系统
echo -e "${BLUE}清理Docker系统...${NC}"
docker system prune -f

# 检查Docker守护进程
echo -e "${BLUE}检查Docker守护进程...${NC}"
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Docker未运行，请先启动Docker${NC}"
    exit 1
fi

# 尝试拉取镜像（使用代理）
echo -e "${BLUE}拉取Docker镜像...${NC}"

# 拉取NATS镜像
echo -e "${YELLOW}拉取NATS镜像...${NC}"
docker pull nats:2.9.15-alpine || {
    echo -e "${RED}NATS镜像拉取失败，尝试使用本地镜像${NC}"
}

# 拉取ClickHouse镜像
echo -e "${YELLOW}拉取ClickHouse镜像...${NC}"
docker pull clickhouse/clickhouse-server:23.3-alpine || {
    echo -e "${RED}ClickHouse镜像拉取失败，尝试使用本地镜像${NC}"
}

# 启动服务
echo -e "${BLUE}启动基础设施服务...${NC}"

# 创建简化的docker-compose配置
cat > docker-compose.infrastructure.yml << 'EOT'
version: '3.8'

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
EOT

# 使用简化配置启动服务
docker-compose -f docker-compose.infrastructure.yml up -d

# 等待服务启动
echo -e "${BLUE}等待服务启动...${NC}"
sleep 10

# 检查服务状态
echo -e "${BLUE}检查服务状态...${NC}"
docker-compose -f docker-compose.infrastructure.yml ps

# 测试NATS连接
echo -e "${BLUE}测试NATS连接...${NC}"
for i in {1..5}; do
    if curl -s http://localhost:8222/healthz > /dev/null; then
        echo -e "${GREEN}✅ NATS服务正常运行${NC}"
        break
    else
        echo -e "${YELLOW}等待NATS服务启动... (尝试 $i/5)${NC}"
        sleep 5
    fi
done

# 测试ClickHouse连接
echo -e "${BLUE}测试ClickHouse连接...${NC}"
for i in {1..5}; do
    if curl -s http://localhost:8123/ping > /dev/null; then
        echo -e "${GREEN}✅ ClickHouse服务正常运行${NC}"
        break
    else
        echo -e "${YELLOW}等待ClickHouse服务启动... (尝试 $i/5)${NC}"
        sleep 5
    fi
done

echo -e "${GREEN}基础设施启动完成！${NC}"
echo -e "${BLUE}服务访问地址：${NC}"
echo "- NATS监控: http://localhost:8222"
echo "- ClickHouse: http://localhost:8123"

# 导出环境变量到文件
cat > .env.infrastructure << EOT
# 基础设施环境变量
NATS_URL=nats://localhost:4222
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_DATABASE=marketprism
DEV_MODE=true
API_PORT=8080
PROMETHEUS_PORT=9090

# 网络代理设置
http_proxy=http://127.0.0.1:1087
https_proxy=http://127.0.0.1:1087
ALL_PROXY=socks5://127.0.0.1:1080
no_proxy=localhost,127.0.0.1
EOT

echo -e "${GREEN}环境变量已保存到 .env.infrastructure${NC}" 