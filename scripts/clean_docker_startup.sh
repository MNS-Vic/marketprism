#!/bin/bash

# MarketPrism Docker容器化干净启动脚本
# 清理所有重复资源，使用标准端口启动完整系统

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 MarketPrism Docker容器化干净启动${NC}"
echo "========================================"

# 1. 完全清理环境
echo -e "\n${YELLOW}🧹 第1步: 完全清理环境${NC}"

echo "停止并删除所有MarketPrism容器..."
docker rm -f $(docker ps -aq --filter "ancestor=marketprism-message-broker") 2>/dev/null || true
docker rm -f $(docker ps -aq --filter "ancestor=marketprism-data-storage") 2>/dev/null || true
docker rm -f $(docker ps -aq --filter "ancestor=marketprism-data-collector") 2>/dev/null || true
docker rm -f $(docker ps -aq --filter "ancestor=clickhouse/clickhouse-server") 2>/dev/null || true

echo "清理Docker网络..."
docker network rm marketprism-network 2>/dev/null || true

echo "清理Python进程..."
pkill -f "unified_collector" 2>/dev/null || true
pkill -f "simple_hot_storage" 2>/dev/null || true

echo -e "${GREEN}✅ 环境清理完成${NC}"

# 2. 创建Docker网络
echo -e "\n${YELLOW}🔧 第2步: 创建Docker网络${NC}"
docker network create marketprism-network
echo -e "${GREEN}✅ 网络创建完成${NC}"

# 3. 启动ClickHouse (标准端口8123)
echo -e "\n${YELLOW}🗄️ 第3步: 启动ClickHouse数据库${NC}"
docker run -d \
    --name marketprism-clickhouse \
    --network marketprism-network \
    -p 8123:8123 \
    -p 9000:9000 \
    clickhouse/clickhouse-server:23.8-alpine

echo "等待ClickHouse启动..."
sleep 15

# 验证ClickHouse
if curl -s http://localhost:8123/ping | grep -q "Ok"; then
    echo -e "${GREEN}✅ ClickHouse启动成功${NC}"
else
    echo -e "${RED}❌ ClickHouse启动失败${NC}"
    exit 1
fi

# 4. 启动NATS消息代理 (标准端口4222)
echo -e "\n${YELLOW}📡 第4步: 启动NATS消息代理${NC}"
docker run -d \
    --name marketprism-nats \
    --network marketprism-network \
    -p 4222:4222 \
    -p 8222:8222 \
    marketprism-message-broker

echo "等待NATS启动..."
sleep 10

# 验证NATS
if curl -s http://localhost:8222/healthz >/dev/null 2>&1; then
    echo -e "${GREEN}✅ NATS启动成功${NC}"
else
    echo -e "${RED}❌ NATS启动失败${NC}"
    exit 1
fi

# 5. 启动数据存储服务 (标准端口8080)
echo -e "\n${YELLOW}💾 第5步: 启动数据存储服务${NC}"
docker run -d \
    --name marketprism-data-storage \
    --network marketprism-network \
    -e CLICKHOUSE_HOST=marketprism-clickhouse \
    -e NATS_URL=nats://marketprism-nats:4222 \
    -e WAIT_FOR_CLICKHOUSE=true \
    -e WAIT_FOR_NATS=true \
    -p 8080:8080 \
    marketprism-data-storage

echo "等待数据存储服务启动..."
sleep 20

# 6. 启动数据收集器 (标准端口8084)
echo -e "\n${YELLOW}📊 第6步: 启动数据收集器${NC}"
docker run -d \
    --name marketprism-data-collector \
    --network marketprism-network \
    -e NATS_URL=nats://marketprism-nats:4222 \
    -e EXCHANGE=binance_spot \
    -p 8084:8080 \
    marketprism-data-collector \
    python unified_collector_main.py --mode collector --exchange binance_spot --log-level INFO

echo "等待数据收集器启动..."
sleep 15

# 7. 验证所有服务
echo -e "\n${YELLOW}🔍 第7步: 验证所有服务${NC}"

echo "检查容器状态:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep marketprism

echo -e "\n检查服务健康状态:"
echo -n "ClickHouse: "
if curl -s http://localhost:8123/ping | grep -q "Ok"; then
    echo -e "${GREEN}✅ 正常${NC}"
else
    echo -e "${RED}❌ 异常${NC}"
fi

echo -n "NATS: "
if curl -s http://localhost:8222/healthz >/dev/null 2>&1; then
    echo -e "${GREEN}✅ 正常${NC}"
else
    echo -e "${RED}❌ 异常${NC}"
fi

echo -n "数据存储服务: "
if curl -s http://localhost:8080/health >/dev/null 2>&1; then
    echo -e "${GREEN}✅ 正常${NC}"
else
    echo -e "${YELLOW}⏳ 启动中${NC}"
fi

echo -n "数据收集器: "
if curl -s http://localhost:8084/health >/dev/null 2>&1; then
    echo -e "${GREEN}✅ 正常${NC}"
else
    echo -e "${YELLOW}⏳ 启动中${NC}"
fi

# 8. 显示访问信息
echo -e "\n${BLUE}📋 服务访问信息${NC}"
echo "========================================"
echo "ClickHouse HTTP:     http://localhost:8123"
echo "NATS监控:           http://localhost:8222"
echo "数据存储服务:        http://localhost:8080"
echo "数据收集器:          http://localhost:8084"
echo ""
echo "查看日志命令:"
echo "docker logs marketprism-clickhouse"
echo "docker logs marketprism-nats"
echo "docker logs marketprism-data-storage"
echo "docker logs marketprism-data-collector"

echo -e "\n${GREEN}🎉 MarketPrism Docker容器化系统启动完成！${NC}"
