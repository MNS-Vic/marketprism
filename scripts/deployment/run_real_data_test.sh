#!/bin/bash

# MarketPrism 真实数据流集成测试快速启动脚本
# 
# 此脚本将：
# 1. 启动必要的基础设施
# 2. 运行完整的真实数据流集成测试
# 3. 生成详细的测试报告

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# 打印横幅
print_banner() {
    echo -e "${BLUE}"
    echo "=============================================================================="
    echo " MarketPrism 真实数据流集成测试"
    echo " 从真实交易所数据源到ClickHouse存储的完整流程测试"
    echo "=============================================================================="
    echo -e "${NC}"
}

# 打印步骤
print_step() {
    echo -e "${PURPLE}[步骤] $1${NC}"
}

# 清理函数
cleanup() {
    echo -e "${RED}正在清理测试环境...${NC}"
    # 这里可以添加需要的清理操作
    exit 0
}

# 捕获中断信号
trap cleanup INT TERM

print_banner

# 检查Python环境
print_step "检查Python环境和依赖"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到Python3${NC}"
    exit 1
fi

# 检查必要的Python包
required_packages=("pytest" "asyncio" "aiohttp" "docker" "nats-py" "clickhouse-connect" "websockets")
missing_packages=()

for package in "${required_packages[@]}"; do
    if ! python3 -c "import ${package//-/_}" &> /dev/null; then
        missing_packages+=("$package")
    fi
done

if [ ${#missing_packages[@]} -ne 0 ]; then
    echo -e "${YELLOW}警告: 缺少以下Python包: ${missing_packages[*]}${NC}"
    echo -e "${BLUE}尝试安装缺少的包...${NC}"
    for package in "${missing_packages[@]}"; do
        pip install "$package" || echo -e "${YELLOW}警告: 无法安装 $package${NC}"
    done
fi

# 检查Docker
print_step "检查Docker环境"
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}错误: Docker未运行或不可访问${NC}"
    echo -e "${YELLOW}请先启动Docker服务${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker环境正常${NC}"

# 启动基础设施
print_step "启动基础设施服务"
echo -e "${BLUE}启动NATS和ClickHouse...${NC}"
docker-compose up -d nats clickhouse

# 等待服务启动
echo -e "${BLUE}等待服务启动...${NC}"
sleep 10

# 检查服务状态
print_step "检查服务状态"
nats_status=$(docker ps --filter "name=nats" --format "{{.Status}}" | head -1)
clickhouse_status=$(docker ps --filter "name=clickhouse" --format "{{.Status}}" | head -1)

if [[ $nats_status == *"Up"* ]]; then
    echo -e "${GREEN}✅ NATS服务运行正常${NC}"
else
    echo -e "${RED}❌ NATS服务状态异常: $nats_status${NC}"
fi

if [[ $clickhouse_status == *"Up"* ]]; then
    echo -e "${GREEN}✅ ClickHouse服务运行正常${NC}"
else
    echo -e "${RED}❌ ClickHouse服务状态异常: $clickhouse_status${NC}"
fi

# 初始化数据库和流
print_step "初始化数据库和NATS流"
echo -e "${BLUE}初始化ClickHouse数据库...${NC}"
python init_clickhouse.py || echo -e "${YELLOW}警告: ClickHouse初始化可能有问题${NC}"

echo -e "${BLUE}创建NATS流...${NC}"
python create_basic_streams.py || echo -e "${YELLOW}警告: NATS流创建可能有问题${NC}"

# 创建日志目录
mkdir -p tests

# 运行真实数据流集成测试
print_step "开始执行真实数据流集成测试"
echo -e "${BLUE}这将需要几分钟时间来完成所有测试阶段...${NC}"
echo -e "${BLUE}测试包括:${NC}"
echo -e "  • 基础设施验证"
echo -e "  • 真实交易所连接测试"
echo -e "  • 数据收集器启动"
echo -e "  • 端到端数据流验证"
echo -e "  • 性能和稳定性测试"
echo ""

# 运行测试
python tests/run_real_data_integration_tests.py

test_exit_code=$?

# 检查测试结果
print_step "测试完成"
if [ $test_exit_code -eq 0 ]; then
    echo -e "${GREEN}🎉 真实数据流集成测试成功完成！${NC}"
    echo -e "${GREEN}✅ 系统已验证能够从真实交易所收集、处理和存储数据${NC}"
elif [ $test_exit_code -eq 1 ]; then
    echo -e "${YELLOW}⚠️ 测试完成但未达到成功标准${NC}"
    echo -e "${YELLOW}部分测试项目可能失败，请查看详细日志${NC}"
elif [ $test_exit_code -eq 2 ]; then
    echo -e "${YELLOW}⚠️ 测试被用户中断${NC}"
else
    echo -e "${RED}❌ 测试执行过程中出现异常${NC}"
fi

# 显示日志位置
print_step "查看测试结果"
echo -e "${BLUE}测试日志文件:${NC}"
if [ -f "tests/real_data_integration_test.log" ]; then
    echo -e "  📄 主日志: tests/real_data_integration_test.log"
fi

report_files=$(ls tests/real_data_integration_report_*.json 2>/dev/null)
if [ -n "$report_files" ]; then
    echo -e "${BLUE}测试报告文件:${NC}"
    for report in $report_files; do
        echo -e "  📊 报告: $report"
    done
fi

# 提供后续操作建议
echo ""
echo -e "${BLUE}后续操作建议:${NC}"
echo -e "1. 查看详细测试日志: ${YELLOW}cat tests/real_data_integration_test.log${NC}"
echo -e "2. 查看测试报告: ${YELLOW}cat tests/real_data_integration_report_*.json${NC}"
echo -e "3. 检查收集器状态: ${YELLOW}curl http://localhost:8081/health${NC}"
echo -e "4. 查看NATS消息: ${YELLOW}python check_nats_messages.py${NC}"
echo -e "5. 查询ClickHouse数据: ${YELLOW}python -c \"import clickhouse_connect; client = clickhouse_connect.get_client(host='localhost', port=8123); print(client.query('SELECT COUNT(*) FROM marketprism.trades').result_rows)\"${NC}"

echo ""
print_banner
echo -e "${GREEN}真实数据流集成测试执行完成！${NC}"

exit $test_exit_code 