#!/bin/bash

# MarketPrism 真实交易所数据收集启动脚本
# 此脚本启动Go收集器连接到真实交易所API

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
    echo "请复制.env.exchange.example为.env.exchange并填入你的API密钥"
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

# 6. 创建基本配置目录
mkdir -p config/collector
# 🔧 配置文件清理：使用统一配置文件
CONFIG_PATH="config/collector/unified_data_collection.yaml"

# 7. 创建收集器配置文件
echo -e "${GREEN}创建收集器配置文件...${NC}"
cat > ${CONFIG_PATH} << EOF
{
    "app_name": "marketprism-collector",
    "environment": "production",
    "log_level": "info",
    "nats_url": "${NATS_URL:-nats://localhost:4222}",
    "symbols": ["BTCUSDT", "ETHUSDT", "BTC-USDT", "ETH-USDT"],
    "exchanges": {
        "binance": {
            "enabled": true,
            "api_key": "${MP_BINANCE_API_KEY}",
            "secret": "${MP_BINANCE_SECRET}",
            "base_url": "https://api.binance.com",
            "ws_url": "wss://stream.binance.com:9443/ws"
        },
        "okex": {
            "enabled": true,
            "api_key": "${MP_OKEX_API_KEY}",
            "secret": "${MP_OKEX_SECRET}",
            "passphrase": "${MP_OKEX_PASSPHRASE}",
            "base_url": "https://www.okx.com",
            "ws_url": "wss://ws.okx.com:8443/ws/v5/public"
        },
        "deribit": {
            "enabled": false,
            "api_key": "${MP_DERIBIT_API_KEY}",
            "secret": "${MP_DERIBIT_SECRET}",
            "base_url": "https://www.deribit.com",
            "ws_url": "wss://www.deribit.com/ws/api/v2"
        }
    }
}
EOF

# 8. 检查Go收集器是否已编译
if [ ! -f services/go-collector/dist/collector ]; then
    echo -e "${YELLOW}编译Go收集器...${NC}"
    cd services/go-collector
    go build -o dist/collector cmd/collector/main.go
    cd ../..
fi

# 9. 启动Go收集器
echo -e "${GREEN}启动真实交易所数据收集器...${NC}"
cd services/go-collector
./dist/collector -config ../../${CONFIG_PATH}