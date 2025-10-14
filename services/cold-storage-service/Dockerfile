FROM python:3.11-slim

WORKDIR /app

# 安装运行时工具（用于健康检查 curl 等）
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

# 复制冷端模块与上游 data-storage-service（用于导入 replication）
# 注意：构建上下文需要是仓库根（由 docker-compose 指定）
COPY services/cold-storage-service /app
COPY services/data-storage-service /app/services/data-storage-service

# 依赖（最小集）
RUN pip install --no-cache-dir aiohttp pyyaml clickhouse-driver lz4 clickhouse-cityhash

# 默认配置路径可通过环境变量覆盖
ENV COLD_STORAGE_CONFIG="config/cold_storage_config.yaml"

CMD ["python", "main.py"]
