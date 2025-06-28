# MarketPrism 监控告警服务 Docker镜像 - 安全加固生产版本
# 包含完整的认证和安全功能

FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖（最小化）
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制requirements文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 设置Python路径
ENV PYTHONPATH=/app

# 创建非root用户
RUN useradd --create-home --shell /bin/bash marketprism && \
    chown -R marketprism:marketprism /app

USER marketprism

# 暴露端口
EXPOSE 8082

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8082/health || exit 1

# 启动命令 - 使用安全加固版本
CMD ["python", "main_secure_v2.py"]
