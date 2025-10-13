FROM python:3.12-slim

WORKDIR /app

# 复制冷端模块与上游 data-storage-service（用于导入 replication）
# 注意：构建上下文需要是仓库根（由 docker-compose 指定）
COPY services/cold-storage-service /app
COPY services/data-storage-service /app/services/data-storage-service

# 依赖（最小集）
RUN pip install --no-cache-dir aiohttp pyyaml clickhouse-driver

# 默认配置路径可通过环境变量覆盖
ENV COLD_STORAGE_CONFIG="config/cold_storage_config.yaml"

CMD ["python", "main.py"]
