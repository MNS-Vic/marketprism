#!/bin/bash

# MarketPrism RabbitMQ集成测试脚本
# 全面测试RabbitMQ部署、配置和功能

set -e

# 配置变量
RABBITMQ_USER="marketprism"
RABBITMQ_PASS="marketprism_monitor_2024"
RABBITMQ_HOST="localhost"
RABBITMQ_PORT="15672"
RABBITMQ_VHOST="/monitoring"
BASE_URL="http://${RABBITMQ_HOST}:${RABBITMQ_PORT}/api"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 测试结果统计
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASSED_TESTS++))
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAILED_TESTS++))
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# 测试函数
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    ((TOTAL_TESTS++))
    log_info "测试: $test_name"
    
    if eval "$test_command"; then
        log_success "$test_name"
        return 0
    else
        log_error "$test_name"
        return 1
    fi
}

# 1. 测试RabbitMQ服务连接
test_rabbitmq_connection() {
    curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${BASE_URL}/overview" > /dev/null
}

# 2. 测试虚拟主机存在
test_vhost_exists() {
    curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${BASE_URL}/vhosts" | grep -q "/monitoring"
}

# 3. 测试Exchange存在
test_exchanges_exist() {
    local exchanges=$(curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${BASE_URL}/exchanges/%2Fmonitoring")
    
    echo "$exchanges" | grep -q "monitoring.direct" &&
    echo "$exchanges" | grep -q "monitoring.topic" &&
    echo "$exchanges" | grep -q "monitoring.fanout" &&
    echo "$exchanges" | grep -q "monitoring.dlx"
}

# 4. 测试队列存在
test_queues_exist() {
    local queues=$(curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${BASE_URL}/queues/%2Fmonitoring")
    
    echo "$queues" | grep -q "metrics.prometheus.queue" &&
    echo "$queues" | grep -q "alerts.p1.queue" &&
    echo "$queues" | grep -q "alerts.p2.queue" &&
    echo "$queues" | grep -q "alerts.p3.queue" &&
    echo "$queues" | grep -q "alerts.p4.queue" &&
    echo "$queues" | grep -q "dashboard.realtime.queue" &&
    echo "$queues" | grep -q "services.health.queue"
}

# 5. 测试绑定关系存在
test_bindings_exist() {
    local bindings=$(curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${BASE_URL}/bindings/%2Fmonitoring")
    
    echo "$bindings" | grep -q "metrics.prometheus.queue" &&
    echo "$bindings" | grep -q "alerts.p1.queue" &&
    echo "$bindings" | grep -q "dashboard.realtime.queue"
}

# 6. 测试消息发布 - P1告警
test_publish_p1_alert() {
    local response=$(curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
                          -X POST "${BASE_URL}/exchanges/%2Fmonitoring/monitoring.direct/publish" \
                          -H "Content-Type: application/json" \
                          -d '{
                              "properties": {"delivery_mode": 2},
                              "routing_key": "alert.p1",
                              "payload": "{\"test\": \"p1_alert\", \"timestamp\": '$(date +%s)'}",
                              "payload_encoding": "string"
                          }')
    
    echo "$response" | grep -q '"routed":true'
}

# 7. 测试消息发布 - Prometheus指标
test_publish_metrics() {
    local response=$(curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
                          -X POST "${BASE_URL}/exchanges/%2Fmonitoring/monitoring.topic/publish" \
                          -H "Content-Type: application/json" \
                          -d '{
                              "properties": {"delivery_mode": 2},
                              "routing_key": "metrics.prometheus.data",
                              "payload": "{\"test\": \"metrics\", \"timestamp\": '$(date +%s)'}",
                              "payload_encoding": "string"
                          }')
    
    echo "$response" | grep -q '"routed":true'
}

# 8. 测试消息发布 - Dashboard数据
test_publish_dashboard() {
    local response=$(curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
                          -X POST "${BASE_URL}/exchanges/%2Fmonitoring/monitoring.fanout/publish" \
                          -H "Content-Type: application/json" \
                          -d '{
                              "properties": {"delivery_mode": 2},
                              "routing_key": "",
                              "payload": "{\"test\": \"dashboard\", \"timestamp\": '$(date +%s)'}",
                              "payload_encoding": "string"
                          }')
    
    echo "$response" | grep -q '"routed":true'
}

# 9. 测试消息发布 - 健康状态
test_publish_health() {
    local response=$(curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
                          -X POST "${BASE_URL}/exchanges/%2Fmonitoring/monitoring.topic/publish" \
                          -H "Content-Type: application/json" \
                          -d '{
                              "properties": {"delivery_mode": 2},
                              "routing_key": "services.health.test",
                              "payload": "{\"test\": \"health\", \"timestamp\": '$(date +%s)'}",
                              "payload_encoding": "string"
                          }')
    
    echo "$response" | grep -q '"routed":true'
}

# 10. 测试队列消息计数
test_queue_message_count() {
    sleep 2  # 等待消息路由
    
    local queues=$(curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${BASE_URL}/queues/%2Fmonitoring")
    
    # 检查P1告警队列是否有消息
    local p1_messages=$(echo "$queues" | grep -A 10 "alerts.p1.queue" | grep -o '"messages":[0-9]*' | head -1 | cut -d':' -f2)
    
    # 检查Prometheus指标队列是否有消息
    local metrics_messages=$(echo "$queues" | grep -A 10 "metrics.prometheus.queue" | grep -o '"messages":[0-9]*' | head -1 | cut -d':' -f2)
    
    # 检查Dashboard队列是否有消息
    local dashboard_messages=$(echo "$queues" | grep -A 10 "dashboard.realtime.queue" | grep -o '"messages":[0-9]*' | head -1 | cut -d':' -f2)
    
    [ "$p1_messages" -gt 0 ] && [ "$metrics_messages" -gt 0 ] && [ "$dashboard_messages" -gt 0 ]
}

# 11. 测试TTL配置
test_ttl_configuration() {
    local queues=$(curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${BASE_URL}/queues/%2Fmonitoring")
    
    # 检查P1告警队列TTL (1小时 = 3600000ms)
    echo "$queues" | grep -A 20 "alerts.p1.queue" | grep -q '"x-message-ttl":3600000' &&
    
    # 检查Dashboard队列TTL (1分钟 = 60000ms)
    echo "$queues" | grep -A 20 "dashboard.realtime.queue" | grep -q '"x-message-ttl":60000'
}

# 12. 测试死信队列配置
test_dlx_configuration() {
    local queues=$(curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "${BASE_URL}/queues/%2Fmonitoring")
    
    # 检查死信交换器配置
    echo "$queues" | grep -A 20 "alerts.p1.queue" | grep -q '"x-dead-letter-exchange":"monitoring.dlx"' &&
    echo "$queues" | grep -A 20 "metrics.prometheus.queue" | grep -q '"x-dead-letter-exchange":"monitoring.dlx"'
}

# 13. 测试与现有NATS的隔离
test_nats_isolation() {
    # 检查NATS端口 (4222) 和RabbitMQ端口 (5672) 都在监听
    netstat -tlnp 2>/dev/null | grep -q ":4222 " &&
    netstat -tlnp 2>/dev/null | grep -q ":5672 "
}

# 14. 测试RabbitMQ管理界面
test_management_ui() {
    curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" "http://${RABBITMQ_HOST}:${RABBITMQ_PORT}/" | grep -q "RabbitMQ Management"
}

# 15. 测试Prometheus指标端点
test_prometheus_metrics() {
    curl -s "http://${RABBITMQ_HOST}:15692/metrics" | grep -q "rabbitmq_"
}

# 清理测试消息
cleanup_test_messages() {
    log_info "清理测试消息..."
    
    # 清空所有测试队列
    for queue in "alerts.p1.queue" "alerts.p2.queue" "alerts.p3.queue" "alerts.p4.queue" "metrics.prometheus.queue" "dashboard.realtime.queue" "services.health.queue"; do
        curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASS}" \
             -X DELETE "${BASE_URL}/queues/%2Fmonitoring/${queue}/contents" > /dev/null
    done
    
    log_info "测试消息已清理"
}

# 显示测试结果摘要
show_test_summary() {
    echo ""
    echo "=========================================="
    echo "           测试结果摘要"
    echo "=========================================="
    echo "总测试数: $TOTAL_TESTS"
    echo -e "通过: ${GREEN}$PASSED_TESTS${NC}"
    echo -e "失败: ${RED}$FAILED_TESTS${NC}"
    
    if [ $FAILED_TESTS -eq 0 ]; then
        echo -e "${GREEN}🎉 所有测试通过！RabbitMQ集成部署成功！${NC}"
        return 0
    else
        echo -e "${RED}❌ 有 $FAILED_TESTS 个测试失败，请检查配置${NC}"
        return 1
    fi
}

# 主测试流程
main() {
    echo "=========================================="
    echo "    MarketPrism RabbitMQ集成测试"
    echo "=========================================="
    echo ""
    
    # 基础连接测试
    run_test "RabbitMQ服务连接" "test_rabbitmq_connection"
    run_test "虚拟主机存在" "test_vhost_exists"
    
    # 架构组件测试
    run_test "Exchange配置" "test_exchanges_exist"
    run_test "队列配置" "test_queues_exist"
    run_test "绑定关系配置" "test_bindings_exist"
    
    # 消息发布测试
    run_test "P1告警消息发布" "test_publish_p1_alert"
    run_test "Prometheus指标发布" "test_publish_metrics"
    run_test "Dashboard数据发布" "test_publish_dashboard"
    run_test "健康状态发布" "test_publish_health"
    
    # 功能验证测试
    run_test "队列消息计数" "test_queue_message_count"
    run_test "TTL配置验证" "test_ttl_configuration"
    run_test "死信队列配置" "test_dlx_configuration"
    
    # 系统集成测试
    run_test "与NATS隔离验证" "test_nats_isolation"
    run_test "管理界面访问" "test_management_ui"
    run_test "Prometheus指标" "test_prometheus_metrics"
    
    # 清理和总结
    cleanup_test_messages
    show_test_summary
}

# 执行测试
main "$@"
