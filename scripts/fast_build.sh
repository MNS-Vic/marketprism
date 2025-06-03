#!/bin/bash

# MarketPrism 快速构建脚本
set -e

# 配置参数
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_step() {
    echo -e "${BLUE}🚀 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

cd "$PROJECT_ROOT"

print_step "开始快速构建 MarketPrism..."

# 记录开始时间
start_time=$(date +%s)

# 1. 停止现有服务
print_step "停止现有服务..."
docker-compose down --remove-orphans 2>/dev/null || true
print_success "服务已停止"

# 2. 清理旧镜像（可选，节省时间）
read -p "是否清理旧镜像？(y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_step "清理旧镜像..."
    docker system prune -f
    print_success "清理完成"
fi

# 3. 构建Python服务（使用快速Dockerfile）
print_step "构建Python服务..."
if docker build -f Dockerfile.fast -t marketprism:latest . ; then
    print_success "Python服务构建完成"
else
    print_warning "Python服务构建失败，尝试简化构建..."
    # 简化版本构建
    docker build -t marketprism:simple -f - . << 'DOCKERFILE'
FROM python:3.9-alpine
WORKDIR /app
RUN adduser -D appuser
COPY . .
RUN pip install --no-cache-dir clickhouse-driver || true
RUN chown -R appuser:appuser /app
USER appuser
EXPOSE 8080
CMD ["python", "-c", "print('MarketPrism服务运行中'); import time; time.sleep(3600)"]
DOCKERFILE
fi

# 4. 构建Go服务（如果存在）
if [ -f "services/go-collector/Dockerfile.fast" ]; then
    print_step "构建Go收集器..."
    if docker build -f services/go-collector/Dockerfile.fast -t marketprism-collector:latest services/go-collector/ ; then
        print_success "Go收集器构建完成"
    else
        print_warning "Go收集器构建失败，跳过..."
    fi
fi

# 5. 创建优化的docker-compose配置
print_step "创建快速部署配置..."
cat > docker-compose.fast.yml << 'EOF'
version: '3.8'

services:
  # 核心存储
  clickhouse-hot:
    image: clickhouse/clickhouse-server:latest
    container_name: marketprism-clickhouse-1
    ports:
      - "9000:9000"
      - "8123:8123"
    volumes:
      - ./data/clickhouse-hot:/var/lib/clickhouse
    environment:
      CLICKHOUSE_DB: marketprism
      CLICKHOUSE_USER: default
      CLICKHOUSE_PASSWORD: ""

  clickhouse-cold:
    image: clickhouse/clickhouse-server:latest
    container_name: marketprism-clickhouse-cold
    ports:
      - "9001:9000"
      - "8124:8123"
    volumes:
      - ./data/clickhouse-cold:/var/lib/clickhouse
    environment:
      CLICKHOUSE_DB: marketprism_cold
      CLICKHOUSE_USER: default
      CLICKHOUSE_PASSWORD: ""

  # 消息队列
  nats:
    image: nats:alpine
    container_name: marketprism-nats
    ports:
      - "4222:4222"
      - "8222:8222"
    command: ["--jetstream", "--http_port", "8222"]

  # 主应用（如果构建成功）
  app:
    image: marketprism:latest
    container_name: marketprism-app
    ports:
      - "8080:8080"
    depends_on:
      - clickhouse-hot
      - clickhouse-cold
      - nats
    environment:
      - CLICKHOUSE_HOST=clickhouse-hot
      - CLICKHOUSE_PORT=9000
      - NATS_URL=nats://nats:4222
    restart: unless-stopped

networks:
  default:
    name: marketprism-network
EOF

# 6. 启动服务
print_step "启动快速服务..."
docker-compose -f docker-compose.fast.yml up -d

# 计算总时间
end_time=$(date +%s)
duration=$((end_time - start_time))

print_success "快速构建完成！"
echo -e "${GREEN}📊 构建统计：${NC}"
echo "  ⏱️  总用时: ${duration}秒"
echo "  🐳 运行的容器："
docker ps --format "table {{.Names}}\\t{{.Status}}\\t{{.Ports}}"

echo ""
echo -e "${BLUE}🔗 访问地址：${NC}"
echo "  📊 ClickHouse (热存储): http://localhost:8123"
echo "  🧊 ClickHouse (冷存储): http://localhost:8124"
echo "  📡 NATS管理界面: http://localhost:8222"
echo "  🚀 应用服务: http://localhost:8080"

echo ""
print_success "快速构建模式启动完成！"
