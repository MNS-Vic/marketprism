#!/bin/bash

# MarketPrism RabbitMQ队列和Exchange设置脚本

set -e

# 配置变量
RABBITMQ_HOST="localhost"
RABBITMQ_PORT="15672"
RABBITMQ_USER="marketprism"
RABBITMQ_PASS="marketprism_monitor_2024"
RABBITMQ_VHOST="/monitoring"
BASE_URL="http://${RABBITMQ_HOST}:${RABBITMQ_PORT}/api"

echo "🚀 开始设置MarketPrism RabbitMQ消息架构"

# 等待RabbitMQ启动
echo "等待RabbitMQ启动..."
for i in {1..30}; do
    if curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${BASE_URL}/overview" > /dev/null 2>&1; then
        echo "✅ RabbitMQ已启动"
        break
    fi
    echo "等待中... (${i}/30)"
    sleep 2
done

# 创建虚拟主机
echo "创建虚拟主机: ${RABBITMQ_VHOST}"
curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
     -X PUT "${BASE_URL}/vhosts/%2Fmonitoring" \
     -H "Content-Type: application/json"

# 设置权限
echo "设置用户权限..."
curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
     -X PUT "${BASE_URL}/permissions/%2Fmonitoring/${RABBITMQ_USER}" \
     -H "Content-Type: application/json" \
     -d '{"configure":".*","write":".*","read":".*"}'

# 创建Exchanges
echo "创建Exchanges..."

# monitoring.direct
curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
     -X PUT "${BASE_URL}/exchanges/%2Fmonitoring/monitoring.direct" \
     -H "Content-Type: application/json" \
     -d '{"type":"direct","durable":true,"auto_delete":false,"arguments":{}}'

# monitoring.topic
curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
     -X PUT "${BASE_URL}/exchanges/%2Fmonitoring/monitoring.topic" \
     -H "Content-Type: application/json" \
     -d '{"type":"topic","durable":true,"auto_delete":false,"arguments":{}}'

# monitoring.fanout
curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
     -X PUT "${BASE_URL}/exchanges/%2Fmonitoring/monitoring.fanout" \
     -H "Content-Type: application/json" \
     -d '{"type":"fanout","durable":true,"auto_delete":false,"arguments":{}}'

# monitoring.dlx (死信交换器)
curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
     -X PUT "${BASE_URL}/exchanges/%2Fmonitoring/monitoring.dlx" \
     -H "Content-Type: application/json" \
     -d '{"type":"direct","durable":true,"auto_delete":false,"arguments":{}}'

echo "✅ Exchanges创建完成"

# 创建队列
echo "创建队列..."

# metrics.prometheus.queue
curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
     -X PUT "${BASE_URL}/queues/%2Fmonitoring/metrics.prometheus.queue" \
     -H "Content-Type: application/json" \
     -d '{"durable":true,"auto_delete":false,"arguments":{"x-message-ttl":300000,"x-dead-letter-exchange":"monitoring.dlx","x-dead-letter-routing-key":"metrics.prometheus.dlq"}}'

# alerts.p1.queue
curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
     -X PUT "${BASE_URL}/queues/%2Fmonitoring/alerts.p1.queue" \
     -H "Content-Type: application/json" \
     -d '{"durable":true,"auto_delete":false,"arguments":{"x-message-ttl":3600000,"x-dead-letter-exchange":"monitoring.dlx","x-dead-letter-routing-key":"alerts.p1.dlq"}}'

# alerts.p2.queue
curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
     -X PUT "${BASE_URL}/queues/%2Fmonitoring/alerts.p2.queue" \
     -H "Content-Type: application/json" \
     -d '{"durable":true,"auto_delete":false,"arguments":{"x-message-ttl":1800000,"x-dead-letter-exchange":"monitoring.dlx","x-dead-letter-routing-key":"alerts.p2.dlq"}}'

# alerts.p3.queue
curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
     -X PUT "${BASE_URL}/queues/%2Fmonitoring/alerts.p3.queue" \
     -H "Content-Type: application/json" \
     -d '{"durable":true,"auto_delete":false,"arguments":{"x-message-ttl":900000,"x-dead-letter-exchange":"monitoring.dlx","x-dead-letter-routing-key":"alerts.p3.dlq"}}'

# alerts.p4.queue
curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
     -X PUT "${BASE_URL}/queues/%2Fmonitoring/alerts.p4.queue" \
     -H "Content-Type: application/json" \
     -d '{"durable":true,"auto_delete":false,"arguments":{"x-message-ttl":600000,"x-dead-letter-exchange":"monitoring.dlx","x-dead-letter-routing-key":"alerts.p4.dlq"}}'

# dashboard.realtime.queue
curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
     -X PUT "${BASE_URL}/queues/%2Fmonitoring/dashboard.realtime.queue" \
     -H "Content-Type: application/json" \
     -d '{"durable":true,"auto_delete":false,"arguments":{"x-message-ttl":60000,"x-dead-letter-exchange":"monitoring.dlx","x-dead-letter-routing-key":"dashboard.realtime.dlq"}}'

# services.health.queue
curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
     -X PUT "${BASE_URL}/queues/%2Fmonitoring/services.health.queue" \
     -H "Content-Type: application/json" \
     -d '{"durable":true,"auto_delete":false,"arguments":{"x-message-ttl":120000,"x-dead-letter-exchange":"monitoring.dlx","x-dead-letter-routing-key":"services.health.dlq"}}'

echo "✅ 队列创建完成"

# 创建绑定关系
echo "创建绑定关系..."

# metrics.prometheus.* -> metrics.prometheus.queue
curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
     -X POST "${BASE_URL}/bindings/%2Fmonitoring/e/monitoring.topic/q/metrics.prometheus.queue" \
     -H "Content-Type: application/json" \
     -d '{"routing_key":"metrics.prometheus.*","arguments":{}}'

# alert.p1 -> alerts.p1.queue
curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
     -X POST "${BASE_URL}/bindings/%2Fmonitoring/e/monitoring.direct/q/alerts.p1.queue" \
     -H "Content-Type: application/json" \
     -d '{"routing_key":"alert.p1","arguments":{}}'

# alert.p2 -> alerts.p2.queue
curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
     -X POST "${BASE_URL}/bindings/%2Fmonitoring/e/monitoring.direct/q/alerts.p2.queue" \
     -H "Content-Type: application/json" \
     -d '{"routing_key":"alert.p2","arguments":{}}'

# alert.p3 -> alerts.p3.queue
curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
     -X POST "${BASE_URL}/bindings/%2Fmonitoring/e/monitoring.direct/q/alerts.p3.queue" \
     -H "Content-Type: application/json" \
     -d '{"routing_key":"alert.p3","arguments":{}}'

# alert.p4 -> alerts.p4.queue
curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
     -X POST "${BASE_URL}/bindings/%2Fmonitoring/e/monitoring.direct/q/alerts.p4.queue" \
     -H "Content-Type: application/json" \
     -d '{"routing_key":"alert.p4","arguments":{}}'

# fanout -> dashboard.realtime.queue
curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
     -X POST "${BASE_URL}/bindings/%2Fmonitoring/e/monitoring.fanout/q/dashboard.realtime.queue" \
     -H "Content-Type: application/json" \
     -d '{"routing_key":"","arguments":{}}'

# services.health.* -> services.health.queue
curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
     -X POST "${BASE_URL}/bindings/%2Fmonitoring/e/monitoring.topic/q/services.health.queue" \
     -H "Content-Type: application/json" \
     -d '{"routing_key":"services.health.*","arguments":{}}'

echo "✅ 绑定关系创建完成"

echo "🎉 RabbitMQ消息架构设置完成！"
echo "管理界面: http://${RABBITMQ_HOST}:${RABBITMQ_PORT}"
echo "用户名: ${RABBITMQ_USER}"
echo "密码: ${RABBITMQ_PASS}"
echo "虚拟主机: ${RABBITMQ_VHOST}"
