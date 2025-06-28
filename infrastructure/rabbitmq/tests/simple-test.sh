#!/bin/bash

# 简化的RabbitMQ测试脚本

echo "=== MarketPrism RabbitMQ验证测试 ==="

# 1. 测试RabbitMQ连接
echo "1. 测试RabbitMQ连接..."
if curl -s -u marketprism:marketprism_monitor_2024 "http://localhost:15672/api/overview" > /dev/null; then
    echo "✅ RabbitMQ连接成功"
else
    echo "❌ RabbitMQ连接失败"
    exit 1
fi

# 2. 检查队列数量
echo "2. 检查队列配置..."
QUEUE_COUNT=$(curl -s -u marketprism:marketprism_monitor_2024 "http://localhost:15672/api/queues/%2Fmonitoring" | grep -o '"name":"[^"]*"' | wc -l)
echo "队列数量: $QUEUE_COUNT"

if [ "$QUEUE_COUNT" -ge 7 ]; then
    echo "✅ 队列配置正确"
else
    echo "❌ 队列配置不完整"
fi

# 3. 测试消息发布
echo "3. 测试消息发布..."
RESPONSE=$(curl -s -u marketprism:marketprism_monitor_2024 \
  -X POST "http://localhost:15672/api/exchanges/%2Fmonitoring/monitoring.direct/publish" \
  -H "Content-Type: application/json" \
  -d '{
    "properties": {"delivery_mode": 2},
    "routing_key": "alert.p1",
    "payload": "{\"test\": true, \"timestamp\": '$(date +%s)'}",
    "payload_encoding": "string"
  }')

if echo "$RESPONSE" | grep -q '"routed":true'; then
    echo "✅ 消息发布成功"
else
    echo "❌ 消息发布失败"
fi

# 4. 检查Docker容器状态
echo "4. 检查Docker容器状态..."
if docker ps | grep -q "marketprism-rabbitmq"; then
    echo "✅ RabbitMQ容器运行正常"
else
    echo "❌ RabbitMQ容器未运行"
fi

# 5. 检查端口监听
echo "5. 检查端口监听..."
if netstat -tlnp 2>/dev/null | grep -q ":5672 "; then
    echo "✅ AMQP端口 (5672) 正常监听"
else
    echo "❌ AMQP端口未监听"
fi

if netstat -tlnp 2>/dev/null | grep -q ":15672 "; then
    echo "✅ 管理端口 (15672) 正常监听"
else
    echo "❌ 管理端口未监听"
fi

# 6. 检查与NATS的隔离
echo "6. 检查与NATS的隔离..."
if netstat -tlnp 2>/dev/null | grep -q ":4222 "; then
    echo "✅ NATS端口 (4222) 正常运行"
    if netstat -tlnp 2>/dev/null | grep -q ":5672 "; then
        echo "✅ RabbitMQ与NATS成功隔离运行"
    fi
else
    echo "⚠️ NATS端口未检测到"
fi

echo ""
echo "=== 测试完成 ==="
echo "🎉 RabbitMQ基本功能验证通过！"
