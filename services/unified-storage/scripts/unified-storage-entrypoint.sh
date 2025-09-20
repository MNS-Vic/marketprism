#!/bin/bash
set -e

echo "🚀 启动MarketPrism统一存储服务..."

# 等待NATS服务可用
echo "⏳ 等待NATS服务..."
while ! curl -f http://nats-container:8222/healthz >/dev/null 2>&1; do
    echo "等待NATS服务启动..."
    sleep 5
done
echo "✅ NATS服务已就绪"

# 设置文件描述符限制
ulimit -n 65536

# 初始化ClickHouse数据目录
echo "📊 初始化ClickHouse..."
mkdir -p /var/lib/clickhouse
chown -R clickhouse:clickhouse /var/lib/clickhouse

# 创建日志目录
mkdir -p /var/log/supervisor
mkdir -p /var/log/clickhouse-server

# 启动supervisord
exec "$@"
