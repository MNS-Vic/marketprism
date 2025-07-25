#!/bin/bash

# MarketPrism 真实交易所数据收集启动脚本
# 此脚本启动Python收集器连接到真实交易所API

# 设置彩色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}MarketPrism 真实交易所数据收集器${NC}"
echo -e "${YELLOW}准备连接到实际交易所API...${NC}"

# 1. 检查API密钥配置
if [ ! -f .env.exchange ]; then
    echo -e "${RED}错误: 找不到.env.exchange文件，请先配置交易所API密钥${NC}"
    echo "请编辑.env.exchange文件并填入你的API密钥"
    exit 1
fi

# 2. 加载API密钥环境变量
echo -e "${GREEN}加载交易所API配置...${NC}"
set -a
source .env.exchange
set +a

# 3. 加载基本环境配置
echo -e "${GREEN}加载基本环境配置...${NC}"
if [ -f .env.production ]; then
    set -a
    source .env.production
    set +a
else
    set -a
    source .env.development
    set +a
fi

# 4. 确保NATS和ClickHouse服务在运行
echo -e "${YELLOW}确保NATS和ClickHouse服务在运行...${NC}"
docker-compose up -d nats clickhouse

# 5. 等待服务启动
echo -e "${YELLOW}等待服务启动...${NC}"
sleep 5

# 6. 启动Python数据收集器
echo -e "${GREEN}启动真实交易所数据收集器...${NC}"
echo -e "${YELLOW}按Ctrl+C停止数据收集${NC}"

# 设置要收集的交易对和环境变量
export SYMBOLS="BTCUSDT,ETHUSDT,BNBUSDT"
export ENABLE_BINANCE=true
export NATS_URL=nats://localhost:4222
export CLICKHOUSE_HOST=localhost
export CLICKHOUSE_PORT=9000
export CLICKHOUSE_DATABASE=marketprism

# 配置代理 - 尝试几个常用端口
for PORT in 7890 7891 1080 1087 8080; do
    echo -e "${YELLOW}尝试代理端口: $PORT${NC}"
    export http_proxy="http://127.0.0.1:$PORT"
    export https_proxy="http://127.0.0.1:$PORT"
    export ALL_PROXY="socks5://127.0.0.1:$PORT"
    
    # 测试代理是否可用
    if curl -s -m 5 -o /dev/null -x $http_proxy https://api.binance.com/api/v3/ping; then
        echo -e "${GREEN}找到可用代理: $http_proxy${NC}"
        break
    else
        echo -e "${YELLOW}端口 $PORT 不可用${NC}"
        # 最后一个端口也不可用时，清除代理设置
        if [ "$PORT" == "8080" ]; then
            echo -e "${YELLOW}未找到可用代理，将尝试直接连接${NC}"
            unset http_proxy
            unset https_proxy
            unset ALL_PROXY
        fi
    fi
done

# 查看当前NATS状态
echo -e "${YELLOW}NATS状态:${NC}"
curl -s http://localhost:8222/varz | grep "connections"

# 启动数据收集器
echo -e "${GREEN}启动数据收集器...${NC}"
cd services/ingestion
python main.py