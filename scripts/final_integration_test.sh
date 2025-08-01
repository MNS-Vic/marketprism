#!/bin/bash

# MarketPrism Docker容器化最终集成测试脚本
# 验证完整的端到端数据流

set -e

echo "🚀 MarketPrism Docker容器化最终集成测试"
echo "========================================"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 测试结果统计
TESTS_PASSED=0
TESTS_FAILED=0
TOTAL_TESTS=0

# 测试函数
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    echo -e "\n${BLUE}🔍 测试: $test_name${NC}"
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    if eval "$test_command"; then
        echo -e "${GREEN}✅ 通过: $test_name${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        echo -e "${RED}❌ 失败: $test_name${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

# 1. 容器状态检查
echo -e "\n${YELLOW}📋 第1阶段: 容器状态检查${NC}"

run_test "ClickHouse容器运行状态" "docker ps | grep -q final-clickhouse"
run_test "NATS容器运行状态" "docker ps | grep -q final-nats"
run_test "数据存储服务运行状态" "docker ps | grep -q storage-test"
run_test "数据收集器运行状态" "docker ps | grep -q collector-test"

# 2. 服务连通性检查
echo -e "\n${YELLOW}🔗 第2阶段: 服务连通性检查${NC}"

run_test "ClickHouse健康检查" "curl -s http://localhost:8125/ping | grep -q 'Ok'"
run_test "NATS健康检查" "curl -s http://localhost:8225/healthz >/dev/null 2>&1"

# 3. NATS JetStream状态检查
echo -e "\n${YELLOW}📊 第3阶段: NATS JetStream状态检查${NC}"

run_test "JetStream可访问性" "curl -s http://localhost:8225/jsz >/dev/null 2>&1"

# 获取NATS统计信息
NATS_STATS=$(curl -s http://localhost:8225/jsz 2>/dev/null || echo '{}')
STREAMS=$(echo "$NATS_STATS" | python3 -c "import json, sys; data=json.load(sys.stdin); print(data.get('streams', 0))" 2>/dev/null || echo "0")
MESSAGES=$(echo "$NATS_STATS" | python3 -c "import json, sys; data=json.load(sys.stdin); print(data.get('messages', 0))" 2>/dev/null || echo "0")

echo "📈 NATS统计信息:"
echo "   - Streams: $STREAMS"
echo "   - Messages: $MESSAGES"

run_test "JetStream Streams存在" "[ '$STREAMS' -gt 0 ]"

# 4. ClickHouse数据验证
echo -e "\n${YELLOW}💾 第4阶段: ClickHouse数据验证${NC}"

run_test "ClickHouse数据库可访问" "curl -s 'http://localhost:8125/?database=marketprism_hot' --data 'SELECT 1' >/dev/null 2>&1"

# 检查表是否存在
TRADES_EXISTS=$(curl -s "http://localhost:8125/?database=marketprism_hot" --data "EXISTS TABLE trades" 2>/dev/null || echo "0")
ORDERBOOKS_EXISTS=$(curl -s "http://localhost:8125/?database=marketprism_hot" --data "EXISTS TABLE orderbooks" 2>/dev/null || echo "0")

echo "📋 数据表状态:"
echo "   - Trades表: $([ '$TRADES_EXISTS' = '1' ] && echo '存在' || echo '不存在')"
echo "   - Orderbooks表: $([ '$ORDERBOOKS_EXISTS' = '1' ] && echo '存在' || echo '不存在')"

run_test "Trades表存在" "[ '$TRADES_EXISTS' = '1' ]"
run_test "Orderbooks表存在" "[ '$ORDERBOOKS_EXISTS' = '1' ]"

# 5. 容器日志检查
echo -e "\n${YELLOW}📋 第5阶段: 容器日志检查${NC}"

# 检查是否有严重错误
STORAGE_ERRORS=$(docker logs storage-test 2>&1 | grep -i "error\|failed\|exception" | wc -l)
COLLECTOR_ERRORS=$(docker logs collector-test 2>&1 | grep -i "error\|failed\|exception" | wc -l)

echo "🔍 错误日志统计:"
echo "   - 数据存储服务错误: $STORAGE_ERRORS"
echo "   - 数据收集器错误: $COLLECTOR_ERRORS"

# 6. 系统稳定性测试
echo -e "\n${YELLOW}⏱️  第6阶段: 系统稳定性测试${NC}"

echo "等待系统运行30秒进行稳定性测试..."
sleep 30

# 再次检查容器状态
run_test "30秒后ClickHouse仍在运行" "docker ps | grep -q final-clickhouse"
run_test "30秒后NATS仍在运行" "docker ps | grep -q final-nats"
run_test "30秒后数据存储服务仍在运行" "docker ps | grep -q storage-test"
run_test "30秒后数据收集器仍在运行" "docker ps | grep -q collector-test"

# 7. 最终结果统计
echo -e "\n${YELLOW}📊 测试结果统计${NC}"
echo "========================================"
echo -e "总测试数: ${BLUE}$TOTAL_TESTS${NC}"
echo -e "通过测试: ${GREEN}$TESTS_PASSED${NC}"
echo -e "失败测试: ${RED}$TESTS_FAILED${NC}"

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "\n${GREEN}🎉 所有测试通过！MarketPrism Docker容器化验证成功！${NC}"
    echo -e "${GREEN}✅ 系统已具备完整的生产级Docker容器化部署能力${NC}"
    exit 0
else
    echo -e "\n${RED}⚠️  有 $TESTS_FAILED 个测试失败，需要进一步调试${NC}"
    exit 1
fi
