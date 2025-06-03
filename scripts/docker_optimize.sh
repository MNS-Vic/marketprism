#!/bin/bash

# MarketPrism Docker 构建优化脚本
# 提供多种优化策略来加速Docker构建和部署

set -e

# 配置参数
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║               MarketPrism Docker 优化工具                  ║"
    echo "║              提升构建和部署速度                             ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_section() {
    echo -e "${CYAN}"
    echo "┌────────────────────────────────────────────────────────────┐"
    echo "│ $1"
    echo "└────────────────────────────────────────────────────────────┘"
    echo -e "${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️ $1${NC}"
}

# 1. 清理优化
cleanup_docker() {
    print_section "清理Docker环境"
    
    print_info "清理未使用的镜像和缓存..."
    docker system prune -f --volumes
    
    print_info "清理构建缓存..."
    docker buildx prune -f
    
    print_info "清理悬挂镜像..."
    docker image prune -f
    
    print_success "Docker环境清理完成"
}

# 2. 并行构建优化
optimize_parallel_build() {
    print_section "配置并行构建"
    
    # 创建优化的docker-compose文件
    cat > "$PROJECT_ROOT/docker-compose.fast.yml" << 'EOF'
version: '3.8'

# 快速构建配置 - 仅核心服务
services:
  # 使用预构建镜像的NATS
  nats:
    image: nats:2.9.15-alpine
    container_name: marketprism-nats-fast
    restart: unless-stopped
    ports:
      - "4222:4222"
      - "8222:8222"
    volumes:
      - nats_data_fast:/data/jetstream
    command:
      - "--jetstream"
      - "--store_dir=/data/jetstream"
      - "--http_port=8222"
      - "--server_name=marketprism"
    networks:
      - marketprism-fast

  # 使用预构建镜像的ClickHouse
  clickhouse:
    image: clickhouse/clickhouse-server:22.3
    container_name: marketprism-clickhouse-fast
    ports:
      - "8123:8123"
      - "9000:9000"
    volumes:
      - clickhouse_data_fast:/var/lib/clickhouse
    restart: unless-stopped
    environment:
      - CLICKHOUSE_DB=marketprism
    networks:
      - marketprism-fast

  # 优化的Go收集器
  go-collector:
    build:
      context: ./services/go-collector
      dockerfile: Dockerfile.fast
      args:
        - GOPROXY=https://goproxy.cn,direct
        - BUILDKIT_INLINE_CACHE=1
    environment:
      - MP_NATS_URL=nats://nats:4222
    depends_on:
      - nats
    networks:
      - marketprism-fast

volumes:
  nats_data_fast:
  clickhouse_data_fast:

networks:
  marketprism-fast:
    driver: bridge
EOF

    print_success "快速构建配置已创建: docker-compose.fast.yml"
}

# 3. 创建优化的Dockerfile
create_optimized_dockerfiles() {
    print_section "创建优化的Dockerfile"
    
    # Go服务优化Dockerfile
    cat > "$PROJECT_ROOT/services/go-collector/Dockerfile.fast" << 'EOF'
# 多阶段构建优化版本
FROM golang:1.20-alpine AS builder

# 安装构建工具
RUN apk add --no-cache git ca-certificates tzdata

# 设置构建环境
ENV CGO_ENABLED=0
ENV GOOS=linux
ENV GOARCH=amd64
ENV GOPROXY=https://goproxy.cn,direct

WORKDIR /build

# 预下载依赖（利用Docker层缓存）
COPY go.mod go.sum ./
RUN go mod download

# 复制源码并构建
COPY . .
RUN go build -ldflags="-w -s" -o collector ./cmd/collector/main.go

# 最小运行时镜像
FROM alpine:latest

RUN apk --no-cache add ca-certificates tzdata curl
WORKDIR /app

# 只复制必要文件
COPY --from=builder /build/collector .
COPY --from=builder /build/config ./config

# 非root用户
RUN adduser -D -s /bin/sh appuser
USER appuser

EXPOSE 8081
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8081/health || exit 1

CMD ["./collector"]
EOF

    # Python服务优化Dockerfile
    cat > "$PROJECT_ROOT/Dockerfile.fast" << 'EOF'
FROM python:3.9-alpine AS builder

# 安装构建依赖
RUN apk add --no-cache gcc musl-dev libffi-dev

# 设置pip优化
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_TRUSTED_HOST=mirrors.aliyun.com
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

# 预安装依赖
COPY requirements.txt .
RUN pip install --user --no-warn-script-location -r requirements.txt

# 运行时镜像
FROM python:3.9-alpine

# 设置时区和用户
RUN apk --no-cache add tzdata curl && \
    adduser -D appuser

WORKDIR /app

# 复制安装的包
COPY --from=builder /root/.local /home/appuser/.local
COPY --chown=appuser:appuser . .

USER appuser
ENV PATH=/home/appuser/.local/bin:$PATH

EXPOSE 8000 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "services.ingestion.app"]
EOF

    print_success "优化的Dockerfile已创建"
}

# 4. 创建预构建镜像脚本
create_prebuild_script() {
    print_section "创建预构建镜像脚本"
    
    cat > "$PROJECT_ROOT/scripts/prebuild_images.sh" << 'EOF'
#!/bin/bash

# 预构建基础镜像脚本
set -e

echo "🚀 开始预构建优化镜像..."

# 构建优化的基础镜像
docker build -t marketprism/python-base:latest -f - . << 'DOCKERFILE'
FROM python:3.9-alpine
RUN apk add --no-cache gcc musl-dev libffi-dev curl tzdata && \
    pip install --upgrade pip && \
    adduser -D appuser
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_TRUSTED_HOST=mirrors.aliyun.com
DOCKERFILE

echo "✅ 基础镜像构建完成"

# 构建依赖层镜像
docker build -t marketprism/python-deps:latest -f - . << 'DOCKERFILE'
FROM marketprism/python-base:latest
COPY requirements.txt /tmp/
RUN pip install --user --no-warn-script-location -r /tmp/requirements.txt
DOCKERFILE

echo "✅ 依赖镜像构建完成"

echo "🎉 预构建完成，后续构建将更快！"
EOF

    chmod +x "$PROJECT_ROOT/scripts/prebuild_images.sh"
    print_success "预构建脚本已创建: scripts/prebuild_images.sh"
}

# 5. 镜像源配置优化
optimize_registry_config() {
    print_section "优化Docker镜像源配置"
    
    # 创建Docker daemon配置
    print_info "配置Docker daemon镜像加速..."
    
    cat > "$PROJECT_ROOT/docker-daemon.json" << 'EOF'
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://dockerhub.azk8s.cn",
    "https://reg-mirror.qiniu.com"
  ],
  "experimental": false,
  "features": {
    "buildkit": true
  },
  "builder": {
    "gc": {
      "defaultKeepStorage": "20GB",
      "enabled": true
    }
  }
}
EOF

    print_warning "请手动将 docker-daemon.json 复制到 Docker 配置目录"
    print_info "macOS: ~/.docker/daemon.json"
    print_info "Linux: /etc/docker/daemon.json"
    print_info "然后重启Docker服务"
}

# 6. 构建缓存优化
optimize_build_cache() {
    print_section "优化构建缓存策略"
    
    cat > "$PROJECT_ROOT/scripts/fast_build.sh" << 'EOF'
#!/bin/bash

# 快速构建脚本 - 利用BuildKit和缓存
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

echo "🚀 使用BuildKit进行快速构建..."

# 构建时使用内联缓存
docker-compose -f docker-compose.fast.yml build \
  --build-arg BUILDKIT_INLINE_CACHE=1 \
  --parallel

echo "✅ 快速构建完成！"

# 启动服务
echo "🔄 启动核心服务..."
docker-compose -f docker-compose.fast.yml up -d

echo "🎉 快速部署完成！"
EOF

    chmod +x "$PROJECT_ROOT/scripts/fast_build.sh"
    print_success "快速构建脚本已创建: scripts/fast_build.sh"
}

# 7. 开发环境优化
create_dev_compose() {
    print_section "创建开发环境优化配置"
    
    cat > "$PROJECT_ROOT/docker-compose.dev.yml" << 'EOF'
version: '3.8'

# 开发环境快速启动配置
services:
  # 开发模式 - 使用卷挂载，避免重复构建
  nats:
    image: nats:2.9.15-alpine
    ports: ["4222:4222", "8222:8222"]
    command: ["--jetstream", "--http_port=8222"]
    
  clickhouse:
    image: clickhouse/clickhouse-server:22.3
    ports: ["8123:8123", "9000:9000"]
    environment:
      - CLICKHOUSE_DB=marketprism
    volumes:
      - clickhouse_dev:/var/lib/clickhouse

  # 开发模式Python服务 - 直接挂载代码
  data-ingestion:
    image: python:3.9-alpine
    volumes:
      - .:/app
      - pip_cache:/root/.cache/pip
    working_dir: /app
    environment:
      - PYTHONPATH=/app
      - PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
    command: sh -c "pip install -r requirements.txt && python -m services.ingestion.app"
    ports: ["8080:8080", "8000:8000"]
    depends_on: [nats, clickhouse]

volumes:
  clickhouse_dev:
  pip_cache:
EOF

    print_success "开发环境配置已创建: docker-compose.dev.yml"
}

# 8. 性能监控
show_build_stats() {
    print_section "构建性能统计"
    
    print_info "当前Docker环境状态:"
    docker system df
    
    echo ""
    print_info "镜像大小统计:"
    docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | head -10
    
    echo ""
    print_info "构建缓存使用情况:"
    docker system df --verbose | grep "Build Cache"
}

# 9. 快速重建脚本
create_quick_rebuild() {
    print_section "创建快速重建脚本"
    
    cat > "$PROJECT_ROOT/scripts/quick_rebuild.sh" << 'EOF'
#!/bin/bash

# 快速重建单个服务
SERVICE=${1:-"go-collector"}

echo "🔄 快速重建服务: $SERVICE"

# 只重建指定服务
docker-compose build --no-cache $SERVICE

# 重启服务
docker-compose up -d $SERVICE

echo "✅ 服务 $SERVICE 重建完成"
EOF

    chmod +x "$PROJECT_ROOT/scripts/quick_rebuild.sh"
    print_success "快速重建脚本已创建: scripts/quick_rebuild.sh"
}

# 主菜单
show_menu() {
    echo ""
    echo "选择优化操作:"
    echo "1. 🧹 清理Docker环境（清理缓存和无用镜像）"
    echo "2. ⚡ 创建快速构建配置"
    echo "3. 🔧 优化Dockerfile"
    echo "4. 📦 创建预构建镜像"
    echo "5. 🌐 配置镜像源加速"
    echo "6. 💾 优化构建缓存"
    echo "7. 🚀 创建开发环境配置"
    echo "8. 📊 显示构建统计"
    echo "9. 🔄 创建快速重建工具"
    echo "10. 🎯 执行全套优化"
    echo "0. 退出"
    echo ""
}

# 执行全套优化
run_full_optimization() {
    print_section "执行全套Docker优化"
    
    cleanup_docker
    optimize_parallel_build
    create_optimized_dockerfiles
    create_prebuild_script
    optimize_registry_config
    optimize_build_cache
    create_dev_compose
    create_quick_rebuild
    
    print_success "全套优化完成！"
    
    echo ""
    echo -e "${GREEN}🎉 优化完成！使用以下命令享受快速构建：${NC}"
    echo ""
    echo -e "${BLUE}# 快速构建和启动${NC}"
    echo "./scripts/fast_build.sh"
    echo ""
    echo -e "${BLUE}# 开发环境启动${NC}"
    echo "docker-compose -f docker-compose.dev.yml up -d"
    echo ""
    echo -e "${BLUE}# 预构建基础镜像${NC}"
    echo "./scripts/prebuild_images.sh"
    echo ""
    echo -e "${BLUE}# 快速重建单个服务${NC}"
    echo "./scripts/quick_rebuild.sh [service-name]"
}

# 主函数
main() {
    print_header
    
    if [ $# -eq 0 ]; then
        # 交互模式
        while true; do
            show_menu
            read -p "请选择操作 (0-10): " choice
            
            case $choice in
                1) cleanup_docker ;;
                2) optimize_parallel_build ;;
                3) create_optimized_dockerfiles ;;
                4) create_prebuild_script ;;
                5) optimize_registry_config ;;
                6) optimize_build_cache ;;
                7) create_dev_compose ;;
                8) show_build_stats ;;
                9) create_quick_rebuild ;;
                10) run_full_optimization ;;
                0) echo "退出优化工具"; exit 0 ;;
                *) print_error "无效选择，请重试" ;;
            esac
            
            echo ""
            read -p "按回车键继续..."
        done
    else
        # 命令行模式
        case "$1" in
            "cleanup") cleanup_docker ;;
            "optimize") run_full_optimization ;;
            "stats") show_build_stats ;;
            "help"|"--help") 
                echo "用法: $0 [cleanup|optimize|stats|help]"
                echo "或直接运行 $0 进入交互模式"
                ;;
            *) 
                print_error "未知参数: $1"
                echo "使用 $0 help 查看帮助"
                exit 1
                ;;
        esac
    fi
}

# 执行主函数
main "$@" 