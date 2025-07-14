# 使用多阶段构建
FROM python:3.9-slim AS builder

# 接收构建参数 - 代理设置
ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG ALL_PROXY=""
ARG PIP_INDEX_URL="https://pypi.org/simple"
ARG PIP_TRUSTED_HOST="pypi.org"

# 设置构建阶段的环境变量
ENV http_proxy=${HTTP_PROXY}
ENV https_proxy=${HTTPS_PROXY}
ENV ALL_PROXY=${ALL_PROXY}
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
ENV PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
ENV PYTHONUNBUFFERED=1

# 设置腾讯云镜像源
RUN pip config set global.index-url https://mirrors.tencentyun.com/pypi/simple/ && \
    pip config set global.trusted-host mirrors.tencentyun.com

# 添加腾讯云内网镜像源配置
RUN echo "deb http://mirrors.tencentyun.com/debian bullseye main contrib non-free" > /etc/apt/sources.list && \
    echo "deb http://mirrors.tencentyun.com/debian bullseye-updates main contrib non-free" >> /etc/apt/sources.list && \
    echo "deb http://mirrors.tencentyun.com/debian-security bullseye-security main contrib non-free" >> /etc/apt/sources.list

# 安装依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --upgrade pip

# 创建工作目录
WORKDIR /app

# 复制并安装项目依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY services/ /app/services/
COPY scripts/ /app/scripts/
COPY config/ /app/config/
COPY core/ /app/core/

# 创建必要目录
RUN mkdir -p /var/log/marketprism /app/data /app/test_reports

# 在构建结束前清除代理设置
ENV http_proxy=""
ENV https_proxy=""
ENV ALL_PROXY=""

# 最终镜像
FROM python:3.9-slim

# 添加腾讯云内网镜像源配置
RUN echo "deb http://mirrors.tencentyun.com/debian bullseye main contrib non-free" > /etc/apt/sources.list && \
    echo "deb http://mirrors.tencentyun.com/debian bullseye-updates main contrib non-free" >> /etc/apt/sources.list && \
    echo "deb http://mirrors.tencentyun.com/debian-security bullseye-security main contrib non-free" >> /etc/apt/sources.list

# 设置工作目录
WORKDIR /app

# 复制从构建阶段构建的应用
COPY --from=builder /app /app
COPY --from=builder /var/log/marketprism /var/log/marketprism
COPY --from=builder /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages

# 复制监控和部署配置
COPY monitoring/ /app/monitoring/
COPY docs/ /app/docs/

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# 创建非特权用户
RUN useradd -m marketprism && \
    chown -R marketprism:marketprism /app /var/log/marketprism

USER marketprism

# 暴露订单簿管理器和监控端口
EXPOSE 8080 8081 9090

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# 默认命令 - 启动订单簿管理系统
CMD ["python", "-m", "services.data-collector.main"]

# 注意：在docker-compose.yml中添加以下配置
# extra_hosts:
#   - "host.docker.internal:host-gateway" 