FROM python:3.11-slim

WORKDIR /app

# 安装运行时工具（仅 curl 用于健康检查；复制走 HTTP，不再依赖 clickhouse-client）
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl; \
    rm -rf /var/lib/apt/lists/*

# 复制冷端模块源码与共享核心库（构建上下文为仓库根，由 docker-compose 指定）
COPY services/cold-storage-service /app
COPY core /app/core

# 依赖（最小集）
RUN pip install --no-cache-dir aiohttp pyyaml clickhouse-driver lz4 clickhouse-cityhash prometheus_client structlog

# 默认配置路径可通过环境变量覆盖
ENV COLD_STORAGE_CONFIG="config/cold_storage_config.yaml"

CMD ["python", "main.py"]
