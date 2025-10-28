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

# 复制应用代码与脚本
COPY services/message-broker/ ./services/message-broker/
COPY core/ ./core/
# 入口仍使用统一入口脚本


# 创建配置目录
RUN mkdir -p /app/config /app/logs \
    && chown -R marketprism:marketprism /app

# 无需复制根目录下的 config/message-broker（实际配置已在 services/message-broker/config 内）

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 容器化专用环境变量
# 仅保留 NATS 相关环境变量（HTTP 层已移除）
ENV MARKETPRISM_NATS_URL=nats://nats:4222
ENV NATS_URL=nats://nats:4222
ENV ENVIRONMENT=production

# manage_all: 此镜像主要用于 js-init；不暴露HTTP端口且不设置健康检查

# 切换到非root用户
USER marketprism

# 启动命令（统一入口）
# 默认执行 JetStream 初始化（compose 中会覆盖为 --wait + 指定脚本配置）
CMD ["python", "services/message-broker/init_jetstream.py", "--wait", "--config", "scripts/js_init_market_data.yaml"]
