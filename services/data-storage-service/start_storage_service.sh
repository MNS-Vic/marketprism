#!/bin/bash

# MarketPrism 统一存储服务启动脚本
# 参考start_marketprism.sh的设计模式

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 显示横幅
show_banner() {
    echo -e "${CYAN}"
    echo "================================================================================"
    echo "💾 MarketPrism 统一存储服务 - 数据持久化与API服务"
    echo "================================================================================"
    echo -e "${NC}"
    echo -e "${BLUE}🎯 架构设计：${NC}数据收集与存储分离，专业化处理"
    echo -e "${BLUE}📋 核心功能：${NC}"
    echo "  • 📡 NATS JetStream订阅：从消息队列消费金融数据"
    echo "  • 💾 数据持久化：实时存储到ClickHouse数据库"
    echo "  • 🌐 HTTP API：提供RESTful数据访问接口"
    echo "  • 📊 统计监控：存储性能和健康状态监控"
    echo "  • 🔄 热冷存储：支持数据生命周期管理"
    echo ""
}

# 检查环境
check_environment() {
    echo -e "${YELLOW}🔍 检查运行环境...${NC}"
    
    # 检查Python虚拟环境
    if [[ -z "$VIRTUAL_ENV" ]]; then
        echo -e "${YELLOW}⚠️  未检测到Python虚拟环境，尝试激活...${NC}"
        if [[ -f "../../venv/bin/activate" ]]; then
            source ../../venv/bin/activate
            echo -e "${GREEN}✅ 虚拟环境激活成功${NC}"
        else
            echo -e "${RED}❌ 找不到虚拟环境，请先创建：python -m venv ../../venv${NC}"
            exit 1
        fi
    else
        echo -e "${GREEN}✅ Python虚拟环境已激活: $VIRTUAL_ENV${NC}"
    fi
    
    # 检查Python版本
    python_version=$(python --version 2>&1)
    echo -e "${GREEN}✅ Python版本: $python_version${NC}"
    
    # 检查配置文件
    config_file="config/unified_storage_service.yaml"
    if [[ -f "$config_file" ]]; then
        echo -e "${GREEN}✅ 存储服务配置文件存在: $config_file${NC}"
    else
        echo -e "${YELLOW}⚠️  存储服务配置文件不存在，将使用collector配置作为回退${NC}"
    fi
    
    # 检查依赖服务
    echo -e "${YELLOW}🔍 检查依赖服务...${NC}"
    
    # 检查NATS服务
    if netstat -tlnp 2>/dev/null | grep -q ":4222"; then
        echo -e "${GREEN}✅ NATS服务器正在运行 (端口4222)${NC}"
    else
        echo -e "${YELLOW}⚠️  NATS服务器未运行，NATS订阅功能将不可用${NC}"
        echo -e "${YELLOW}    启动命令: nats-server --jetstream --store_dir /tmp/nats-jetstream --port 4222${NC}"
    fi
    
    # 检查ClickHouse服务
    if netstat -tlnp 2>/dev/null | grep -q ":8123\|:9000"; then
        echo -e "${GREEN}✅ ClickHouse服务器正在运行${NC}"
    else
        echo -e "${YELLOW}⚠️  ClickHouse服务器未运行，存储功能将不可用${NC}"
        echo -e "${YELLOW}    请确保ClickHouse服务正在运行${NC}"
    fi
    
    echo ""
}

# 显示配置信息
show_config_info() {
    echo -e "${PURPLE}📋 服务配置：${NC}"
    echo "  • 配置文件: config/unified_storage_service.yaml (主配置)"
    echo "  • 回退配置: ../../config/collector/unified_data_collection.yaml"
    echo "  • NATS服务器: localhost:4222"
    echo "  • ClickHouse: localhost:8123"
    echo "  • HTTP API: localhost:8080"
    echo "  • 存储模式: 热存储 + 可选冷存储"
    echo ""
    
    echo -e "${PURPLE}🔧 环境变量覆盖：${NC}"
    echo "  • MARKETPRISM_NATS_SERVERS: NATS服务器地址"
    echo "  • MARKETPRISM_CLICKHOUSE_HOST: ClickHouse主机"
    echo "  • MARKETPRISM_STORAGE_SERVICE_PORT: 服务端口"
    echo ""
}

# 显示架构信息
show_architecture_info() {
    echo -e "${CYAN}🏗️  架构优势：${NC}"
    echo "  • 职责分离: Collector专注数据收集，Storage Service专注存储"
    echo "  • 可扩展性: 支持多实例部署和水平扩展"
    echo "  • 可靠性: JetStream确保数据不丢失，支持消息重放"
    echo "  • 灵活性: HTTP API + NATS订阅双模式支持"
    echo "  • 监控性: 完整的存储统计和健康检查"
    echo ""
    
    echo -e "${CYAN}📊 数据流：${NC}"
    echo "  Exchange → Collector → NATS JetStream → Storage Service → ClickHouse"
    echo "                                      ↓"
    echo "                                  HTTP API ← 客户端查询"
    echo ""
}

# 启动存储服务
start_storage_service() {
    echo -e "${GREEN}🚀 启动MarketPrism统一存储服务...${NC}"
    echo ""
    
    # 启动命令（统一生产入口）
    python main.py "$@"
}

# 显示帮助信息
show_help() {
    echo -e "${CYAN}📖 使用方法：${NC}"
    echo "  $0 [选项]"
    echo ""
    echo -e "${CYAN}选项：${NC}"
    echo "  -c, --config FILE    指定配置文件路径"
    echo "  -m, --mode MODE      运行模式 (production|development|test)"
    echo "  -h, --help           显示帮助信息"
    echo ""
    echo -e "${CYAN}功能说明：${NC}"
    echo "  • NATS订阅: 从JetStream消费实时金融数据并存储"
    echo "  • HTTP API: 提供数据查询和管理接口"
    echo "  • 存储管理: 支持热冷数据生命周期管理"
    echo "  • 监控统计: 实时存储性能和健康状态监控"
    echo ""
    echo -e "${CYAN}API端点：${NC}"
    echo "  • GET  /api/v1/storage/status - 服务状态"
    echo "  • GET  /api/v1/storage/stats - 存储统计"
    echo "  • POST /api/v1/storage/hot/trades - 存储交易数据"
    echo "  • POST /api/v1/storage/hot/orderbooks - 存储订单簿数据"
    echo "  • GET  /api/v1/storage/hot/trades/{exchange}/{symbol} - 查询交易数据"
    echo ""
    echo -e "${CYAN}环境变量：${NC}"
    echo "  • MARKETPRISM_STORAGE_CONFIG_PATH - 配置文件路径"
    echo "  • MARKETPRISM_NATS_SERVERS - NATS服务器地址"
    echo "  • MARKETPRISM_CLICKHOUSE_HOST - ClickHouse主机"
    echo ""
    echo -e "${CYAN}快捷操作：${NC}"
    echo "  • 按 Ctrl+C 优雅停止服务"
    echo "  • 查看日志了解详细运行状态"
    echo "  • 访问 http://localhost:8080/api/v1/storage/status 检查服务状态"
    echo ""
}

# 主函数
main() {
    # 解析命令行参数
    case "${1:-}" in
        -h|--help|help)
            show_banner
            show_help
            exit 0
            ;;
        *)
            ;;
    esac
    
    # 显示横幅
    show_banner
    
    # 检查环境
    check_environment
    
    # 显示配置信息
    show_config_info
    
    # 显示架构信息
    show_architecture_info
    
    # 启动存储服务
    start_storage_service "$@"
}

# 错误处理
trap 'echo -e "\n${RED}❌ 启动过程中发生错误${NC}"; exit 1' ERR

# 执行主函数
main "$@"
