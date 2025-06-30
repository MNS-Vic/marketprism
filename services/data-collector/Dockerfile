# MarketPrism Python Collector Dockerfile
FROM python:3.12-slim

LABEL maintainer="MarketPrism Team"
LABEL description="MarketPrism Python数据收集器"
LABEL version="1.0.0"

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app
ENV RATE_LIMIT_ENABLED=true
ENV API_TIMEOUT=15
ENV LOG_LEVEL=INFO

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    libc6-dev \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 创建工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 复制源代码和配置
COPY services/data-collector/ ./services/data-collector/
COPY services/service_registry.py ./services/
COPY core/ ./core/
COPY config/ ./config/

# 创建非root用户
RUN useradd -m -u 1000 collector && \
    chown -R collector:collector /app

# 切换到非root用户
USER collector

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8084/health || exit 1

# 暴露端口
EXPOSE 8084

# 设置入口点
CMD ["python", "services/data-collector/main.py"]