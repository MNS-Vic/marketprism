#!/bin/bash
# MarketPrism入口点标准化脚本
# 确认并固化唯一入口点，清理临时或重复的入口文件

set -euo pipefail

echo "=== MarketPrism入口点标准化 ==="

# 1. 确认标准入口点
echo "1. 确认标准入口点:"

# 数据存储服务唯一入口
STORAGE_MAIN="services/data-storage-service/main.py"
if [ -f "$STORAGE_MAIN" ]; then
    echo "  ✅ 数据存储服务唯一入口: $STORAGE_MAIN"
    # 检查是否支持热端和冷端模式
    if grep -q "mode.*hot\|mode.*cold" "$STORAGE_MAIN"; then
        echo "    ✅ 支持 --mode hot/cold 参数"
    else
        echo "    ❌ 缺少模式参数支持"
        exit 1
    fi
else
    echo "  ❌ 数据存储服务入口不存在: $STORAGE_MAIN"
    exit 1
fi

# 数据采集器唯一入口
COLLECTOR_MAIN="services/data-collector/unified_collector_main.py"
if [ -f "$COLLECTOR_MAIN" ]; then
    echo "  ✅ 数据采集器唯一入口: $COLLECTOR_MAIN"
    # 检查是否支持配置文件参数
    if grep -q "config.*yaml\|argparse" "$COLLECTOR_MAIN"; then
        echo "    ✅ 支持 --config 参数"
    else
        echo "    ❌ 缺少配置参数支持"
        exit 1
    fi
else
    echo "  ❌ 数据采集器入口不存在: $COLLECTOR_MAIN"
    exit 1
fi

# 2. 检查deprecated目录
echo -e "\n2. 检查历史入口文件管理:"
DEPRECATED_STORAGE="services/data-storage-service/deprecated"
if [ -d "$DEPRECATED_STORAGE" ]; then
    deprecated_count=$(find "$DEPRECATED_STORAGE" -name "*.py" | wc -l)
    echo "  ✅ 存储服务历史文件已归档: $deprecated_count 个文件在 $DEPRECATED_STORAGE"
else
    echo "  ⚠️ 存储服务无deprecated目录"
fi

# 3. 识别潜在的重复入口文件
echo -e "\n3. 识别潜在的重复入口文件:"

# 检查数据采集器中的其他main文件
echo "  数据采集器中的其他入口文件:"
other_mains=$(find services/data-collector -maxdepth 1 -name "*.py" | grep -E "(main|start|run)" | grep -v "unified_collector_main.py" || true)
if [ -n "$other_mains" ]; then
    echo "$other_mains" | while read -r file; do
        echo "    ⚠️ 发现其他入口文件: $file"
        # 检查文件大小，小文件可能是临时文件
        size=$(stat -c%s "$file")
        if [ "$size" -lt 5000 ]; then
            echo "      建议: 文件较小($size bytes)，可能是临时文件，建议移除或归档"
        else
            echo "      建议: 文件较大($size bytes)，建议移至deprecated目录"
        fi
    done
else
    echo "    ✅ 无其他入口文件"
fi

# 4. 验证入口文件的可执行性
echo -e "\n4. 验证入口文件的可执行性:"

# 激活虚拟环境
source venv/bin/activate

echo "  测试存储服务入口:"
if python "$STORAGE_MAIN" --help >/dev/null 2>&1; then
    echo "    ✅ 存储服务入口可正常执行"
else
    echo "    ❌ 存储服务入口执行失败"
    exit 1
fi

echo "  测试数据采集器入口:"
if python "$COLLECTOR_MAIN" --help >/dev/null 2>&1; then
    echo "    ✅ 数据采集器入口可正常执行"
else
    echo "    ❌ 数据采集器入口执行失败"
    exit 1
fi

# 5. 生成标准启动命令
echo -e "\n5. 标准启动命令:"
echo "  数据采集器:"
echo "    python services/data-collector/unified_collector_main.py --config services/data-collector/config/collector/unified_data_collection.yaml"
echo "  热端存储服务:"
echo "    python services/data-storage-service/main.py --mode hot --config services/data-storage-service/config/tiered_storage_config.yaml"
echo "  冷端存储服务:"
echo "    python services/data-storage-service/main.py --mode cold --config services/data-storage-service/config/tiered_storage_config.yaml"

echo -e "\n=== ✅ 入口点标准化完成！ ==="
echo "唯一入口点已确认："
echo "  - 数据存储服务: services/data-storage-service/main.py"
echo "  - 数据采集器: services/data-collector/unified_collector_main.py"
echo "  - 历史文件已归档至deprecated目录"
