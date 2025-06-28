#!/bin/bash

# MarketPrism RabbitMQ设置验证脚本

set -e

RABBITMQ_USER="marketprism"
RABBITMQ_PASS="marketprism_monitor_2024"
BASE_URL="http://localhost:15672/api"

echo "🔍 验证MarketPrism RabbitMQ设置"

# 检查RabbitMQ服务状态
echo "1. 检查RabbitMQ服务状态..."
if curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${BASE_URL}/overview" > /dev/null; then
    echo "✅ RabbitMQ服务正常运行"
else
    echo "❌ RabbitMQ服务无法访问"
    exit 1
fi

# 检查虚拟主机
echo "2. 检查虚拟主机..."
VHOSTS=$(curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${BASE_URL}/vhosts")
if echo "$VHOSTS" | grep -q "/monitoring"; then
    echo "✅ 虚拟主机 /monitoring 存在"
else
    echo "❌ 虚拟主机 /monitoring 不存在"
fi

# 检查Exchanges
echo "3. 检查Exchanges..."
EXCHANGES=$(curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${BASE_URL}/exchanges/%2Fmonitoring")

for exchange in "monitoring.direct" "monitoring.topic" "monitoring.fanout" "monitoring.dlx"; do
    if echo "$EXCHANGES" | grep -q "\"name\":\"$exchange\""; then
        echo "✅ Exchange $exchange 存在"
    else
        echo "❌ Exchange $exchange 不存在"
    fi
done

# 检查队列
echo "4. 检查队列..."
QUEUES=$(curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${BASE_URL}/queues/%2Fmonitoring")

for queue in "metrics.prometheus.queue" "alerts.p1.queue" "alerts.p2.queue" "alerts.p3.queue" "alerts.p4.queue" "dashboard.realtime.queue" "services.health.queue"; do
    if echo "$QUEUES" | grep -q "\"name\":\"$queue\""; then
        echo "✅ 队列 $queue 存在"
    else
        echo "❌ 队列 $queue 不存在"
    fi
done

# 检查绑定关系
echo "5. 检查绑定关系..."
BINDINGS=$(curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${BASE_URL}/bindings/%2Fmonitoring")

if echo "$BINDINGS" | grep -q "metrics.prometheus.queue"; then
    echo "✅ metrics.prometheus.queue 绑定存在"
else
    echo "❌ metrics.prometheus.queue 绑定不存在"
fi

if echo "$BINDINGS" | grep -q "dashboard.realtime.queue"; then
    echo "✅ dashboard.realtime.queue 绑定存在"
else
    echo "❌ dashboard.realtime.queue 绑定不存在"
fi

# 显示统计信息
echo "6. 系统统计信息..."
OVERVIEW=$(curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${BASE_URL}/overview")

EXCHANGES_COUNT=$(echo "$OVERVIEW" | grep -o '"exchanges":[0-9]*' | cut -d':' -f2)
QUEUES_COUNT=$(echo "$OVERVIEW" | grep -o '"queues":[0-9]*' | cut -d':' -f2)

echo "📊 Exchanges数量: $EXCHANGES_COUNT"
echo "📊 队列数量: $QUEUES_COUNT"

echo ""
echo "🎉 RabbitMQ设置验证完成！"
echo "🌐 管理界面: http://localhost:15672"
echo "👤 用户名: $RABBITMQ_USER"
echo "🔑 密码: $RABBITMQ_PASS"
echo "🏠 虚拟主机: /monitoring"
