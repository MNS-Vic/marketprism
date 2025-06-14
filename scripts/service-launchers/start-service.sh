#!/bin/bash

# MarketPrism 微服务选择启动器
# 提供交互式界面选择要启动的服务

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 脚本信息
clear
echo "=================================================="
echo -e "${PURPLE}🚀 MarketPrism 微服务一键启动器${NC}"
echo "=================================================="
echo ""
echo -e "${CYAN}选择要启动的服务:${NC}"
echo ""
echo -e "${BLUE}1.${NC} API Gateway Service (端口: 8080)"
echo -e "   ${YELLOW}→${NC} 统一API网关，请求路由、认证、限流"
echo ""
echo -e "${BLUE}2.${NC} Market Data Collector (端口: 8081)"
echo -e "   ${YELLOW}→${NC} 市场数据采集，支持Binance/OKX/Deribit"
echo ""
echo -e "${BLUE}3.${NC} Data Storage Service (端口: 8082)"
echo -e "   ${YELLOW}→${NC} 数据存储服务，ClickHouse/Redis热冷存储"
echo ""
echo -e "${BLUE}4.${NC} Monitoring Service (端口: 8083)"
echo -e "   ${YELLOW}→${NC} 系统监控，Prometheus指标，智能告警"
echo ""
echo -e "${BLUE}5.${NC} Scheduler Service (端口: 8084)"
echo -e "   ${YELLOW}→${NC} 任务调度服务，定时任务，自动化管理"
echo ""
echo -e "${BLUE}6.${NC} Message Broker Service (端口: 8085)"
echo -e "   ${YELLOW}→${NC} 消息代理，NATS/JetStream，消息队列"
echo ""
echo -e "${BLUE}a.${NC} 全部服务（仅显示命令，不执行）"
echo -e "${BLUE}q.${NC} 退出"
echo ""
echo "=================================================="

# 获取用户输入
read -p "$(echo -e ${CYAN}请选择 [1-6/a/q]: ${NC})" choice

case $choice in
    1)
        echo -e "${GREEN}启动 API Gateway Service...${NC}"
        ./scripts/service-launchers/start-api-gateway.sh
        ;;
    2)
        echo -e "${GREEN}启动 Market Data Collector Service...${NC}"
        ./scripts/service-launchers/start-market-data-collector.sh
        ;;
    3)
        echo -e "${GREEN}启动 Data Storage Service...${NC}"
        ./scripts/service-launchers/start-data-storage.sh
        ;;
    4)
        echo -e "${GREEN}启动 Monitoring Service...${NC}"
        ./scripts/service-launchers/start-monitoring.sh
        ;;
    5)
        echo -e "${GREEN}启动 Scheduler Service...${NC}"
        ./scripts/service-launchers/start-scheduler.sh
        ;;
    6)
        echo -e "${GREEN}启动 Message Broker Service...${NC}"
        ./scripts/service-launchers/start-message-broker.sh
        ;;
    a|A)
        echo ""
        echo -e "${YELLOW}📋 所有服务启动命令:${NC}"
        echo ""
        echo -e "${BLUE}API Gateway:${NC}"
        echo "  ./scripts/service-launchers/start-api-gateway.sh"
        echo ""
        echo -e "${BLUE}Market Data Collector:${NC}"
        echo "  ./scripts/service-launchers/start-market-data-collector.sh"
        echo ""
        echo -e "${BLUE}Data Storage Service:${NC}"
        echo "  ./scripts/service-launchers/start-data-storage.sh"
        echo ""
        echo -e "${BLUE}Monitoring Service:${NC}"
        echo "  ./scripts/service-launchers/start-monitoring.sh"
        echo ""
        echo -e "${BLUE}Scheduler Service:${NC}"
        echo "  ./scripts/service-launchers/start-scheduler.sh"
        echo ""
        echo -e "${BLUE}Message Broker Service:${NC}"
        echo "  ./scripts/service-launchers/start-message-broker.sh"
        echo ""
        echo -e "${CYAN}💡 提示: 可以在不同终端窗口中分别运行这些命令${NC}"
        echo ""
        ;;
    q|Q)
        echo -e "${YELLOW}退出启动器${NC}"
        exit 0
        ;;
    *)
        echo -e "${RED}无效选择，请重新运行脚本${NC}"
        exit 1
        ;;
esac