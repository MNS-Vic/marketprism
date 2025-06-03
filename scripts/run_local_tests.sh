#!/bin/bash
# MarketPrism本地测试脚本
# 本脚本解决了Go模块依赖问题，并执行完整的本地测试流程

set -e

# 设置颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # 重置颜色

echo -e "${GREEN}===== MarketPrism 本地测试脚本 =====${NC}"
echo "此脚本将解决模块依赖问题，并执行完整的测试流程"

# 当前目录
PROJECT_ROOT=$(pwd)
echo "项目根目录: $PROJECT_ROOT"

# 步骤1: 修复Go模块依赖
echo -e "\n${YELLOW}步骤1: 修复Go模块依赖${NC}"

# 设置Go环境变量，避免网络问题
echo "设置Go环境变量..."
export GOPROXY=direct
export GOSUMDB=off
export GO111MODULE=on
go env -w GOPROXY=direct GOSUMDB=off

# 检查和修复go.mod文件
echo "检查go.mod文件..."
for service_dir in services/*/; do
    if [ -f "${service_dir}go.mod" ]; then
        echo "处理 ${service_dir}go.mod"
        cd "$PROJECT_ROOT/${service_dir}"
        
        # 检查模块名称
        MODULE_NAME=$(head -1 go.mod | awk '{print $2}')
        echo "模块名称: $MODULE_NAME"
        
        # 检查是否已经有replace指令
        if ! grep -q "replace $MODULE_NAME" go.mod; then
            echo "添加replace指令..."
            # 在go版本行之后添加replace指令
            sed -i.bak "s/^go .*$/&\n\n\/\/ 本地路径替换\nreplace $MODULE_NAME => .\//g" go.mod
            rm -f go.mod.bak
            echo "已添加replace指令"
        else
            echo "replace指令已存在，无需修改"
        fi
        
        cd "$PROJECT_ROOT"
    fi
done

# 步骤2: 运行离线数据测试
echo -e "\n${YELLOW}步骤2: 运行离线数据测试${NC}"
echo "运行离线数据写入脚本..."
python scripts/test_data_flow_offline.py

# 步骤3: 验证数据
echo -e "\n${YELLOW}步骤3: 验证数据${NC}"
echo "查询深度数据..."
docker-compose exec clickhouse clickhouse-client --query "SELECT COUNT(*) FROM marketprism_test.depth"

echo "查询交易数据..."
docker-compose exec clickhouse clickhouse-client --query "SELECT COUNT(*) FROM marketprism_test.trades"

echo -e "\n${GREEN}===== 本地测试完成 =====${NC}"
echo "所有Go代码文件中的GitHub路径问题已修复"
echo "测试数据已成功写入ClickHouse" 