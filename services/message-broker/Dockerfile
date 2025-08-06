# MarketPrism 消息代理服务 - Docker容器化版本
FROM python:3.12-slim

LABEL maintainer="MarketPrism Team"
LABEL description="MarketPrism Message Broker - 容器化消息代理服务"
LABEL version="2.0.0"

# 设置工作目录
WORKDIR /app

# 安装系统依赖（最小化）
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 复制并安装Python依赖
COPY services/message-broker/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 创建非root用户
RUN groupadd -r marketprism && useradd -r -g marketprism marketprism

# 复制应用代码（最小化依赖）
COPY services/message-broker/docker_main.py .
COPY services/message-broker/requirements.txt .

# 创建配置目录
RUN mkdir -p /app/config /app/logs \
    && chown -R marketprism:marketprism /app

# 复制配置文件模板
COPY config/message-broker/ ./config/

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 容器化专用环境变量
ENV NATS_URL=nats://nats:4222
ENV SERVICE_PORT=8085
ENV SERVICE_HOST=0.0.0.0
ENV LOG_LEVEL=INFO
ENV ENVIRONMENT=production

# 暴露端口（更新为8085）
EXPOSE 8085

# 健康检查（更新端口）
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8085/health || exit 1

# 切换到非root用户
USER marketprism

# 启动命令（使用容器化入口）
CMD ["python", "docker_main.py"]
