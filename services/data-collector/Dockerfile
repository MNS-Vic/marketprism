# MarketPrism Python Collector Dockerfile - Docker部署简化版
# 🔄 Docker部署简化改造 (2025-08-02)
#
# 简化改造内容:
# - ✅ 运行模式简化: 专注launcher模式（完整数据收集系统）
# - ✅ 健康检查简化: 只保留8086端口健康检查
# - ✅ 端口暴露简化: 8086(健康检查) + 9093(监控)
# - ✅ 启动命令固定: 直接启动launcher模式
# - ✅ 配置路径统一: 使用本地配置文件
#
# 验证结果:
# - ✅ 镜像构建成功，容器启动正常
# - ✅ 与统一NATS容器集成成功
# - ✅ 8种数据类型×5个交易所全部正常工作
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

# 安装Python依赖 (使用--root-user-action=ignore抑制警告)
RUN pip install --no-cache-dir --upgrade pip --root-user-action=ignore && \
    pip install --no-cache-dir -r requirements.txt --root-user-action=ignore && \
    # 确保nats-py版本正确（解决asyncio兼容性问题）
    pip install --no-cache-dir nats-py==2.2.0 --root-user-action=ignore

# 复制源代码和配置
COPY services/data-collector/ ./services/data-collector/
COPY core/ ./core/
COPY config/ ./config/

# 复制入口脚本并设置权限（root阶段）
COPY services/data-collector/entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh

# 创建非root用户
RUN useradd -m -u 1000 collector && \
    chown -R collector:collector /app

# 切换到非root用户
USER collector

# 健康检查（launcher模式专用）
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8086/health || exit 1

# 暴露端口（launcher模式专用）
EXPOSE 8086 9093

# 设置统一启动入口和配置
# 固定使用launcher模式 - 完整数据收集系统
ENV COLLECTOR_MODE=launcher
ENV COLLECTOR_CONFIG_PATH=/app/config/collector/unified_data_collection.yaml

# 工作目录设置为data-collector
WORKDIR /app/services/data-collector

# 入口：先启动独立健康检查再执行主进程
ENTRYPOINT ["/entrypoint.sh"]