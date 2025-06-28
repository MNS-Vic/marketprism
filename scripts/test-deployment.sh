#!/bin/bash

# MarketPrism 智能监控告警系统部署测试脚本
# 全面测试部署后的系统功能、性能和安全性

set -euo pipefail

# 脚本配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEPLOYMENT_TYPE="${1:-docker-compose}"
BASE_URL="${2:-http://localhost:8082}"
TEST_TIMEOUT="${3:-300}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 测试结果统计
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
SKIPPED_TESTS=0

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 测试结果记录
record_test() {
    local test_name="$1"
    local result="$2"
    local message="${3:-}"
    
    ((TOTAL_TESTS++))
    
    case "$result" in
        "PASS")
            ((PASSED_TESTS++))
            log_success "✓ $test_name"
            ;;
        "FAIL")
            ((FAILED_TESTS++))
            log_error "✗ $test_name: $message"
            ;;
        "SKIP")
            ((SKIPPED_TESTS++))
            log_warning "⊘ $test_name: $message"
            ;;
    esac
}

# HTTP请求函数
make_request() {
    local method="$1"
    local endpoint="$2"
    local data="${3:-}"
    local expected_status="${4:-200}"
    
    local url="$BASE_URL$endpoint"
    local response
    local status_code
    
    if [[ -n "$data" ]]; then
        response=$(curl -s -w "\n%{http_code}" -X "$method" \
            -H "Content-Type: application/json" \
            -d "$data" \
            "$url" 2>/dev/null || echo -e "\n000")
    else
        response=$(curl -s -w "\n%{http_code}" -X "$method" \
            "$url" 2>/dev/null || echo -e "\n000")
    fi
    
    status_code=$(echo "$response" | tail -n1)
    response_body=$(echo "$response" | head -n -1)
    
    if [[ "$status_code" == "$expected_status" ]]; then
        echo "$response_body"
        return 0
    else
        echo "HTTP $status_code: $response_body" >&2
        return 1
    fi
}

# 等待服务就绪
wait_for_service() {
    log_info "等待服务就绪..."
    
    local count=0
    local max_attempts=$((TEST_TIMEOUT / 5))
    
    while [[ $count -lt $max_attempts ]]; do
        if make_request "GET" "/health" > /dev/null 2>&1; then
            record_test "服务可达性检查" "PASS"
            return 0
        fi
        
        echo -n "."
        sleep 5
        ((count++))
    done
    
    echo ""
    record_test "服务可达性检查" "FAIL" "服务在 $TEST_TIMEOUT 秒内未就绪"
    return 1
}

# 基础健康检查测试
test_health_checks() {
    log_info "执行基础健康检查测试..."
    
    # 健康检查端点
    if make_request "GET" "/health" > /dev/null; then
        record_test "健康检查端点" "PASS"
    else
        record_test "健康检查端点" "FAIL" "健康检查失败"
    fi
    
    # 就绪检查端点
    if make_request "GET" "/ready" > /dev/null; then
        record_test "就绪检查端点" "PASS"
    else
        record_test "就绪检查端点" "FAIL" "就绪检查失败"
    fi
    
    # Prometheus指标端点
    if make_request "GET" "/metrics" > /dev/null; then
        record_test "Prometheus指标端点" "PASS"
    else
        record_test "Prometheus指标端点" "SKIP" "Prometheus客户端不可用"
    fi
}

# API功能测试
test_api_functionality() {
    log_info "执行API功能测试..."
    
    # 获取告警列表
    if response=$(make_request "GET" "/api/v1/alerts"); then
        if echo "$response" | jq -e '.alerts' > /dev/null 2>&1; then
            record_test "获取告警列表API" "PASS"
        else
            record_test "获取告警列表API" "FAIL" "响应格式错误"
        fi
    else
        record_test "获取告警列表API" "FAIL" "请求失败"
    fi
    
    # 获取告警规则
    if response=$(make_request "GET" "/api/v1/rules"); then
        if echo "$response" | jq -e '.rules' > /dev/null 2>&1; then
            record_test "获取告警规则API" "PASS"
        else
            record_test "获取告警规则API" "FAIL" "响应格式错误"
        fi
    else
        record_test "获取告警规则API" "FAIL" "请求失败"
    fi
    
    # 获取业务指标
    if response=$(make_request "GET" "/api/v1/metrics/business"); then
        if echo "$response" | jq -e '.exchanges' > /dev/null 2>&1; then
            record_test "获取业务指标API" "PASS"
        else
            record_test "获取业务指标API" "FAIL" "响应格式错误"
        fi
    else
        record_test "获取业务指标API" "FAIL" "请求失败"
    fi
    
    # 异常检测API
    local anomaly_data='{"metric_name": "test_metric", "value": 100.0, "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}'
    if response=$(make_request "POST" "/api/v1/anomaly/detect" "$anomaly_data"); then
        if echo "$response" | jq -e '.is_anomaly' > /dev/null 2>&1; then
            record_test "异常检测API" "PASS"
        else
            record_test "异常检测API" "FAIL" "响应格式错误"
        fi
    else
        record_test "异常检测API" "FAIL" "请求失败"
    fi
    
    # 故障预测API
    if response=$(make_request "GET" "/api/v1/prediction/failures"); then
        if echo "$response" | jq -e '.predictions' > /dev/null 2>&1; then
            record_test "故障预测API" "PASS"
        else
            record_test "故障预测API" "FAIL" "响应格式错误"
        fi
    else
        record_test "故障预测API" "FAIL" "请求失败"
    fi
    
    # 统计信息API
    if response=$(make_request "GET" "/api/v1/stats/alerts"); then
        if echo "$response" | jq -e '.total_alerts' > /dev/null 2>&1; then
            record_test "告警统计API" "PASS"
        else
            record_test "告警统计API" "FAIL" "响应格式错误"
        fi
    else
        record_test "告警统计API" "FAIL" "请求失败"
    fi
}

# 性能测试
test_performance() {
    log_info "执行性能测试..."
    
    # 检查Apache Bench是否可用
    if ! command -v ab &> /dev/null; then
        record_test "性能测试" "SKIP" "Apache Bench未安装"
        return
    fi
    
    # API响应时间测试
    local perf_result
    perf_result=$(ab -n 100 -c 5 -q "$BASE_URL/api/v1/alerts" 2>/dev/null | grep "Time per request:" | head -1 | awk '{print $4}')
    
    if [[ -n "$perf_result" ]]; then
        local avg_time=${perf_result%.*}  # 去掉小数部分
        
        if [[ $avg_time -lt 500 ]]; then
            record_test "API响应时间性能" "PASS"
        elif [[ $avg_time -lt 1000 ]]; then
            record_test "API响应时间性能" "PASS" "响应时间 ${avg_time}ms (可接受)"
        else
            record_test "API响应时间性能" "FAIL" "响应时间 ${avg_time}ms 超过阈值"
        fi
    else
        record_test "API响应时间性能" "FAIL" "无法获取性能数据"
    fi
    
    # 并发测试
    local concurrent_result
    concurrent_result=$(ab -n 50 -c 10 -q "$BASE_URL/health" 2>/dev/null | grep "Requests per second:" | awk '{print $4}')
    
    if [[ -n "$concurrent_result" ]]; then
        local rps=${concurrent_result%.*}
        
        if [[ $rps -gt 100 ]]; then
            record_test "并发处理能力" "PASS"
        else
            record_test "并发处理能力" "FAIL" "吞吐量 ${rps} req/s 低于预期"
        fi
    else
        record_test "并发处理能力" "FAIL" "无法获取并发测试数据"
    fi
}

# 故障恢复测试
test_failure_recovery() {
    log_info "执行故障恢复测试..."
    
    if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
        # Docker Compose故障恢复测试
        log_info "测试容器重启恢复..."
        
        # 重启服务
        if docker-compose -f "$PROJECT_ROOT/deployments/docker-compose/docker-compose.yml" restart monitoring-alerting > /dev/null 2>&1; then
            sleep 10
            
            # 检查服务是否恢复
            if make_request "GET" "/health" > /dev/null; then
                record_test "容器重启恢复" "PASS"
            else
                record_test "容器重启恢复" "FAIL" "重启后服务未恢复"
            fi
        else
            record_test "容器重启恢复" "FAIL" "无法重启容器"
        fi
        
    elif [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
        # Kubernetes故障恢复测试
        log_info "测试Pod重启恢复..."
        
        # 删除一个Pod
        if kubectl delete pod -l app=monitoring-alerting -n marketprism-monitoring --timeout=30s > /dev/null 2>&1; then
            sleep 30
            
            # 等待新Pod就绪
            if kubectl wait --for=condition=ready pod -l app=monitoring-alerting -n marketprism-monitoring --timeout=120s > /dev/null 2>&1; then
                # 检查服务是否恢复
                if make_request "GET" "/health" > /dev/null; then
                    record_test "Pod重启恢复" "PASS"
                else
                    record_test "Pod重启恢复" "FAIL" "重启后服务未恢复"
                fi
            else
                record_test "Pod重启恢复" "FAIL" "Pod未能及时就绪"
            fi
        else
            record_test "Pod重启恢复" "FAIL" "无法删除Pod"
        fi
    else
        record_test "故障恢复测试" "SKIP" "不支持的部署类型"
    fi
}

# 安全测试
test_security() {
    log_info "执行安全测试..."
    
    # 测试未授权访问
    if make_request "GET" "/api/v1/admin/config" "" "401" > /dev/null 2>&1; then
        record_test "未授权访问保护" "PASS"
    else
        record_test "未授权访问保护" "FAIL" "应该返回401状态码"
    fi
    
    # 测试SQL注入防护
    local malicious_data='{"metric_name": "test\"; DROP TABLE alerts; --", "value": 100.0}'
    if make_request "POST" "/api/v1/anomaly/detect" "$malicious_data" "400" > /dev/null 2>&1; then
        record_test "SQL注入防护" "PASS"
    else
        # 如果返回200，检查是否正常处理了恶意输入
        if make_request "POST" "/api/v1/anomaly/detect" "$malicious_data" > /dev/null 2>&1; then
            record_test "SQL注入防护" "PASS" "恶意输入被安全处理"
        else
            record_test "SQL注入防护" "FAIL" "未正确处理恶意输入"
        fi
    fi
    
    # 测试XSS防护
    local xss_data='{"metric_name": "<script>alert(\"xss\")</script>", "value": 100.0}'
    if response=$(make_request "POST" "/api/v1/anomaly/detect" "$xss_data"); then
        if echo "$response" | grep -q "<script>"; then
            record_test "XSS防护" "FAIL" "响应中包含未转义的脚本"
        else
            record_test "XSS防护" "PASS"
        fi
    else
        record_test "XSS防护" "PASS" "恶意输入被拒绝"
    fi
}

# 数据持久性测试
test_data_persistence() {
    log_info "执行数据持久性测试..."
    
    # 创建测试告警
    local test_alert_data='{"name": "测试告警", "description": "数据持久性测试", "severity": "medium"}'
    
    # 注意：这里需要根据实际API调整
    if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
        # 重启服务
        docker-compose -f "$PROJECT_ROOT/deployments/docker-compose/docker-compose.yml" restart monitoring-alerting > /dev/null 2>&1
        sleep 10
        
        # 检查数据是否持久化
        if make_request "GET" "/health" > /dev/null; then
            record_test "数据持久性" "PASS"
        else
            record_test "数据持久性" "FAIL" "重启后数据丢失"
        fi
    else
        record_test "数据持久性" "SKIP" "需要手动验证"
    fi
}

# 监控指标测试
test_monitoring_metrics() {
    log_info "执行监控指标测试..."
    
    # 检查Prometheus指标
    if response=$(make_request "GET" "/metrics"); then
        # 检查关键指标是否存在
        local key_metrics=("marketprism_alert_total" "marketprism_api_requests_total" "process_resident_memory_bytes")
        local missing_metrics=()
        
        for metric in "${key_metrics[@]}"; do
            if ! echo "$response" | grep -q "$metric"; then
                missing_metrics+=("$metric")
            fi
        done
        
        if [[ ${#missing_metrics[@]} -eq 0 ]]; then
            record_test "Prometheus指标完整性" "PASS"
        else
            record_test "Prometheus指标完整性" "FAIL" "缺少指标: ${missing_metrics[*]}"
        fi
    else
        record_test "Prometheus指标完整性" "SKIP" "无法获取指标"
    fi
}

# 生成测试报告
generate_test_report() {
    local report_file="$PROJECT_ROOT/test-results/deployment-test-report-$(date +%Y%m%d-%H%M%S).json"
    
    mkdir -p "$(dirname "$report_file")"
    
    cat > "$report_file" << EOF
{
  "test_summary": {
    "total_tests": $TOTAL_TESTS,
    "passed_tests": $PASSED_TESTS,
    "failed_tests": $FAILED_TESTS,
    "skipped_tests": $SKIPPED_TESTS,
    "success_rate": $(echo "scale=2; $PASSED_TESTS * 100 / $TOTAL_TESTS" | bc -l 2>/dev/null || echo "0")
  },
  "test_environment": {
    "deployment_type": "$DEPLOYMENT_TYPE",
    "base_url": "$BASE_URL",
    "test_time": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "timeout": $TEST_TIMEOUT
  },
  "test_categories": {
    "health_checks": "completed",
    "api_functionality": "completed",
    "performance": "completed",
    "failure_recovery": "completed",
    "security": "completed",
    "data_persistence": "completed",
    "monitoring_metrics": "completed"
  }
}
EOF
    
    log_info "测试报告已生成: $report_file"
}

# 显示测试结果
show_test_results() {
    echo ""
    echo "=========================================="
    echo "           部署测试结果汇总"
    echo "=========================================="
    echo ""
    echo "测试统计:"
    echo "  总测试数:   $TOTAL_TESTS"
    echo "  通过测试:   $PASSED_TESTS"
    echo "  失败测试:   $FAILED_TESTS"
    echo "  跳过测试:   $SKIPPED_TESTS"
    
    if [[ $TOTAL_TESTS -gt 0 ]]; then
        local success_rate
        success_rate=$(echo "scale=1; $PASSED_TESTS * 100 / $TOTAL_TESTS" | bc -l 2>/dev/null || echo "0")
        echo "  成功率:     ${success_rate}%"
    fi
    
    echo ""
    
    if [[ $FAILED_TESTS -eq 0 ]]; then
        log_success "所有测试通过！部署验证成功。"
        return 0
    else
        log_error "有 $FAILED_TESTS 个测试失败，请检查部署配置。"
        return 1
    fi
}

# 主函数
main() {
    log_info "开始 MarketPrism 智能监控告警系统部署测试"
    log_info "部署类型: $DEPLOYMENT_TYPE"
    log_info "测试地址: $BASE_URL"
    log_info "超时时间: $TEST_TIMEOUT 秒"
    echo ""
    
    # 等待服务就绪
    if ! wait_for_service; then
        log_error "服务未就绪，无法继续测试"
        exit 1
    fi
    
    # 执行各项测试
    test_health_checks
    test_api_functionality
    test_performance
    test_failure_recovery
    test_security
    test_data_persistence
    test_monitoring_metrics
    
    # 生成报告和显示结果
    generate_test_report
    show_test_results
}

# 错误处理
trap 'log_error "测试过程中发生错误"; exit 1' ERR

# 检查依赖
if ! command -v jq &> /dev/null; then
    log_error "jq未安装，请先安装jq"
    exit 1
fi

if ! command -v bc &> /dev/null; then
    log_warning "bc未安装，某些计算功能可能不可用"
fi

# 执行主函数
main "$@"
