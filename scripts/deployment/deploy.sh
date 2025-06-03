#!/bin/bash
# MarketPrism 部署脚本

# 终端颜色设置
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
BLUE="\033[0;34m"
RESET="\033[0m"

# 显示帮助信息
show_help() {
    echo "用法: ./deploy.sh [选项]"
    echo ""
    echo "选项:"
    echo "  -p, --proxy    使用代理部署（开发环境）"
    echo "  -n, --no-proxy 不使用代理部署（生产环境）"
    echo "  -h, --help     显示帮助信息"
    echo ""
    echo "示例:"
    echo "  ./deploy.sh --proxy     # 使用代理和开发环境配置启动"
    echo "  ./deploy.sh --no-proxy  # 使用生产环境配置启动（无代理）"
}

# 如果没有参数，显示帮助并退出
if [ $# -eq 0 ]; then
    show_help
    exit 1
fi

# 解析参数
use_proxy=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        -p|--proxy)
            use_proxy=1
            shift
            ;;
        -n|--no-proxy)
            use_proxy=0
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "未知选项: $1"
            show_help
            exit 1
            ;;
    esac
done

echo -e "${GREEN}========== MarketPrism 部署脚本 ==========${RESET}"

# 检查Docker是否启动
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}错误: Docker守护进程未运行!${RESET}"
    echo "请先启动Docker Desktop应用，然后再运行此脚本"
    exit 1
fi

echo -e "${GREEN}检测到Docker正在运行${RESET}"
docker --version
docker-compose --version

# 检查环境文件是否存在
if [ ! -f .env.development ] || [ ! -f .env.production ]; then
    echo -e "${YELLOW}检测到环境配置文件不存在，正在创建...${RESET}"
    
    # 创建环境配置文件
    if [ ! -f create_env_files.sh ]; then
        echo -e "${RED}错误: 找不到创建环境文件的脚本!${RESET}"
        exit 1
    fi
    
    chmod +x create_env_files.sh
    ./create_env_files.sh
fi

# 创建必要的目录
echo -e "${BLUE}创建必要目录...${RESET}"
mkdir -p logs
chmod -R 777 logs

# 设置环境变量
echo -e "${GREEN}设置环境变量...${RESET}"
if [ $use_proxy -eq 1 ]; then
    echo -e "${YELLOW}使用开发环境配置${RESET}"
    env_file=".env.development"
    
    # 设置代理环境变量，仅用于下面的 docker-compose build 命令
    echo -e "${BLUE}从${env_file}读取代理设置${RESET}"
    export $(grep -v '^#' ${env_file} | grep 'http_proxy\|https_proxy\|ALL_PROXY' | xargs)
    
    echo -e "${BLUE}已设置主机代理环境变量:${RESET}"
    echo "http_proxy=${http_proxy}"
    echo "https_proxy=${https_proxy}"
    echo "ALL_PROXY=${ALL_PROXY}"
    
    echo -e "${BLUE}注意: 代理设置将用于Docker镜像构建，但不会传递给容器运行时${RESET}"
else
    echo -e "${YELLOW}使用生产环境配置（无代理）${RESET}"
    env_file=".env.production"
    
    # 确保没有设置代理环境变量
    unset http_proxy
    unset https_proxy
    unset ALL_PROXY
fi

# 导出.env文件中的环境变量
echo -e "${BLUE}加载${env_file}文件...${RESET}"
set -a
source ${env_file}
set +a

echo -e "${GREEN}开始部署MarketPrism...${RESET}"

# 构建和启动服务
echo -e "${GREEN}构建服务...${RESET}"
docker-compose --env-file ${env_file} build --no-cache

if [ $? -ne 0 ]; then
    echo -e "${RED}构建服务失败，请检查日志${RESET}"
    exit 1
fi

echo -e "${GREEN}启动所有服务...${RESET}"
docker-compose --env-file ${env_file} up -d

if [ $? -ne 0 ]; then
    echo -e "${RED}启动服务失败，请检查日志${RESET}"
    exit 1
fi

# 等待服务启动
echo -e "${BLUE}等待服务启动...${RESET}"
sleep 10

# 初始化数据库
echo -e "${GREEN}初始化数据库...${RESET}"
max_retries=3
retry_count=0
db_initialized=false

while [ $retry_count -lt $max_retries ] && [ "$db_initialized" = false ]; do
    python init_db.py
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}数据库初始化成功!${RESET}"
        db_initialized=true
    else
        retry_count=$((retry_count+1))
        if [ $retry_count -lt $max_retries ]; then
            echo -e "${YELLOW}数据库初始化失败，尝试重试 ($retry_count/$max_retries)...${RESET}"
            sleep 5
        else
            echo -e "${YELLOW}警告: 数据库初始化重试次数已用尽，尝试直接在容器内执行SQL...${RESET}"
            
            # 尝试直接在容器内执行SQL
            echo -e "${BLUE}尝试直接在容器中初始化数据库...${RESET}"
            docker-compose exec clickhouse clickhouse-client --query="CREATE DATABASE IF NOT EXISTS marketprism"
            docker-compose exec clickhouse clickhouse-client --query="CREATE DATABASE IF NOT EXISTS marketprism_test"
            docker-compose exec clickhouse clickhouse-client --query="CREATE DATABASE IF NOT EXISTS marketprism_cold"
            
            # 导入表结构
            docker-compose exec clickhouse clickhouse-client --query="$(cat create_tables.sql)"
            
            echo -e "${YELLOW}直接执行SQL完成，继续部署流程...${RESET}"
        fi
    fi
done

# 创建NATS流
echo -e "${GREEN}创建NATS流...${RESET}"
max_retries=3
retry_count=0
streams_created=false

while [ $retry_count -lt $max_retries ] && [ "$streams_created" = false ]; do
    python create_nats_streams.py
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}NATS流创建成功!${RESET}"
        streams_created=true
    else
        retry_count=$((retry_count+1))
        if [ $retry_count -lt $max_retries ]; then
            echo -e "${YELLOW}NATS流创建失败，尝试重试 ($retry_count/$max_retries)...${RESET}"
            sleep 5
        else
            echo -e "${YELLOW}警告: NATS流创建重试次数已用尽，使用备用方法...${RESET}"
            
            # 使用备用方法
            python config_nats_cli.py
            
            if [ $? -ne 0 ]; then
                echo -e "${YELLOW}备用方法也失败，继续部署流程...${RESET}"
            else
                echo -e "${GREEN}使用备用方法创建NATS流成功!${RESET}"
                streams_created=true
            fi
        fi
    fi
done

# 运行集成测试
echo -e "${GREEN}运行集成测试...${RESET}"
python test_core_services.py

# 清理主机上的代理环境变量
if [ $use_proxy -eq 1 ]; then
    echo -e "${BLUE}清理主机代理环境变量...${RESET}"
    unset http_proxy
    unset https_proxy
    unset ALL_PROXY
fi

# 最终提示
echo -e "${GREEN}MarketPrism 服务已启动!${RESET}"
echo ""
echo -e "${GREEN}=== 服务访问信息 ===${RESET}"
echo "NATS 监控界面: http://localhost:8222"
echo "NATS Web UI: http://localhost:8380"
echo "ClickHouse HTTP接口: http://localhost:8123"
echo "Grafana 可视化界面: http://localhost:3000 (用户名/密码: admin/admin)"
echo "Prometheus: http://localhost:9090"
echo ""
echo -e "${YELLOW}常用命令:${RESET}"
echo "查看服务状态: docker-compose ps"
echo "查看服务日志: docker-compose logs -f [服务名]"
echo "停止所有服务: docker-compose down"
echo "重启某个服务: docker-compose restart [服务名]"
