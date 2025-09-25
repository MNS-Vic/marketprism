#!/bin/bash
# MarketPrism配置验证和固化脚本
# 确保所有关键配置的正确性和一致性

set -euo pipefail

echo "=== MarketPrism配置验证和固化 ==="

# 激活虚拟环境
source venv/bin/activate

# 1. 验证端口配置
echo "1. 验证端口配置:"
echo "  数据采集器健康检查端口:"
COLLECTOR_PORT=$(grep -A2 "health_check:" services/data-collector/config/collector/unified_data_collection.yaml | grep "port:" | awk '{print $2}' | head -1)
echo "    配置值: $COLLECTOR_PORT (应为8087)"
if [ "$COLLECTOR_PORT" = "8087" ]; then
    echo "    ✅ 正确"
else
    echo "    ❌ 错误，应为8087"
    exit 1
fi

echo "  热端存储服务端口:"
HOT_PORT=$(grep "http_port:" services/data-storage-service/config/tiered_storage_config.yaml | awk '{print $2}' | head -1)
echo "    配置值: $HOT_PORT (应为8085)"
if [ "$HOT_PORT" = "8085" ]; then
    echo "    ✅ 正确"
else
    echo "    ❌ 错误，应为8085"
    exit 1
fi

echo "  冷端存储服务端口:"
COLD_PORT=$(grep -A1 "cold_storage:" services/data-storage-service/config/tiered_storage_config.yaml | grep "http_port:" | awk '{print $2}')
echo "    配置值: $COLD_PORT (应为8086)"
if [ "$COLD_PORT" = "8086" ]; then
    echo "    ✅ 正确"
else
    echo "    ❌ 错误，应为8086"
    exit 1
fi

# 2. 验证ClickHouse连接配置
echo -e "\n2. 验证ClickHouse连接配置:"
echo "  检查ClickHouse可用性:"
if curl -s "http://127.0.0.1:8123/?query=SELECT%201" >/dev/null; then
    echo "    ✅ ClickHouse连接正常"
else
    echo "    ❌ ClickHouse连接失败"
    exit 1
fi

# 3. 验证冷端表DateTime64精度
echo -e "\n3. 验证冷端表DateTime64精度:"
tables=("funding_rates" "liquidations" "open_interests" "lsr_top_positions" "lsr_all_accounts" "volatility_indices")
for table in "${tables[@]}"; do
    type=$(curl -s "http://127.0.0.1:8123/?query=SELECT%20type%20FROM%20system.columns%20WHERE%20database%3D%27marketprism_cold%27%20AND%20table%3D%27$table%27%20AND%20name%3D%27created_at%27" 2>/dev/null || echo "")
    echo "  表 $table created_at字段: $type"
    if [ "$type" = "DateTime64(3)" ]; then
        echo "    ✅ 正确"
    else
        echo "    ❌ 错误，应为DateTime64(3)"
        exit 1
    fi
done

# 4. 验证配置文件完整性
echo -e "\n4. 验证配置文件完整性:"
config_files=(
    "services/data-storage-service/config/tiered_storage_config.yaml"
    "services/data-collector/config/collector/unified_data_collection.yaml"
)

for config in "${config_files[@]}"; do
    if [ -f "$config" ]; then
        echo "  ✅ $config 存在"
    else
        echo "  ❌ $config 不存在"
        exit 1
    fi
done

# 5. 验证NATS配置
echo -e "\n5. 验证NATS JetStream:"
if curl -s http://127.0.0.1:8222/healthz >/dev/null; then
    echo "  ✅ NATS JetStream运行正常"
else
    echo "  ❌ NATS JetStream不可用"
    exit 1
fi

echo -e "\n=== ✅ 所有配置验证通过！ ==="
echo "MarketPrism项目配置已固化，关键修复点："
echo "  - 端口冲突已解决：数据采集器8087，热端8085，冷端8086"
echo "  - DateTime64(3)精度已统一：所有冷端表created_at字段"
echo "  - 配置文件完整性已确认：唯一配置入口已建立"
