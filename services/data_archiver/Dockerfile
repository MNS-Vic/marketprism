# Data Archiver Service Dockerfile
# 用于容器化部署数据归档服务

FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONPATH="/app:/app/services"
ENV PYTHONUNBUFFERED=1
ENV DATA_ARCHIVER_ENV=production

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt /app/
COPY services/data_archiver/requirements_archiver.txt /app/services/data_archiver/

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r services/data_archiver/requirements_archiver.txt

# 复制应用代码
COPY services/data_archiver/ /app/services/data_archiver/
COPY config/ /app/config/
COPY scripts/ /app/scripts/

# 创建必要的目录
RUN mkdir -p /app/logs /app/data /app/archive

# 设置文件权限
RUN chmod +x /app/services/data_archiver/service.py

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "
import sys
sys.path.append('/app')
from services.data_archiver.service import DataArchiverService
try:
    service = DataArchiverService()
    health = service.health_check()
    exit(0 if health.get('overall_health') else 1)
except Exception as e:
    print(f'Health check failed: {e}')
    exit(1)
"

# 暴露端口（如果有HTTP API）
EXPOSE 8080

# 设置用户
RUN useradd -m -u 1001 archiver
RUN chown -R archiver:archiver /app
USER archiver

# 定义数据卷
VOLUME ["/app/data", "/app/archive", "/app/logs", "/app/config"]

# 启动命令
CMD ["python", "/app/services/data_archiver/service.py"]