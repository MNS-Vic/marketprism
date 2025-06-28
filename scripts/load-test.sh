#!/bin/bash

# MarketPrism 智能监控告警系统负载测试脚本
# 模拟真实负载场景，测试系统在高并发下的性能表现

set -euo pipefail

# 脚本配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BASE_URL="${1:-http://localhost:8082}"
TEST_DURATION="${2:-300}"  # 测试持续时间（秒）
MAX_CONCURRENT="${3:-100}" # 最大并发数

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 测试结果
TEST_RESULTS=()

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

# 检查依赖
check_dependencies() {
    local missing_deps=()
    
    if ! command -v ab &> /dev/null; then
        missing_deps+=("apache2-utils")
    fi
    
    if ! command -v jq &> /dev/null; then
        missing_deps+=("jq")
    fi
    
    if ! command -v curl &> /dev/null; then
        missing_deps+=("curl")
    fi
    
    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        log_error "缺少以下依赖: ${missing_deps[*]}"
        log_error "请安装缺少的依赖后重试"
        exit 1
    fi
}

# 预热测试
warmup_test() {
    log_info "执行预热测试..."
    
    # 发送少量请求预热系统
    for i in {1..10}; do
        curl -s "$BASE_URL/health" > /dev/null || true
        sleep 1
    done
    
    log_success "预热完成"
}

# 基准性能测试
baseline_performance_test() {
    log_info "执行基准性能测试..."
    
    local endpoints=(
        "/health"
        "/ready"
        "/api/v1/alerts"
        "/api/v1/rules"
        "/api/v1/metrics/business"
        "/api/v1/stats/alerts"
    )
    
    for endpoint in "${endpoints[@]}"; do
        log_info "测试端点: $endpoint"
        
        local result
        result=$(ab -n 100 -c 5 -q "$BASE_URL$endpoint" 2>/dev/null | grep -E "(Requests per second|Time per request)" | head -2)
        
        if [[ -n "$result" ]]; then
            local rps=$(echo "$result" | grep "Requests per second" | awk '{print $4}')
            local avg_time=$(echo "$result" | grep "Time per request" | head -1 | awk '{print $4}')
            
            TEST_RESULTS+=("$endpoint: ${rps} req/s, ${avg_time}ms avg")
            log_success "$endpoint: ${rps} req/s, ${avg_time}ms"
        else
            log_error "无法获取 $endpoint 的性能数据"
        fi
    done
}

# 并发压力测试
concurrent_stress_test() {
    log_info "执行并发压力测试..."
    
    local concurrent_levels=(10 25 50 100)
    local test_endpoint="/api/v1/alerts"
    
    for concurrent in "${concurrent_levels[@]}"; do
        if [[ $concurrent -gt $MAX_CONCURRENT ]]; then
            continue
        fi
        
        log_info "测试并发级别: $concurrent"
        
        local result
        result=$(ab -n $((concurrent * 10)) -c $concurrent -t 30 -q "$BASE_URL$test_endpoint" 2>/dev/null)
        
        if [[ -n "$result" ]]; then
            local rps=$(echo "$result" | grep "Requests per second" | awk '{print $4}')
            local avg_time=$(echo "$result" | grep "Time per request" | head -1 | awk '{print $4}')
            local failed=$(echo "$result" | grep "Failed requests" | awk '{print $3}')
            
            TEST_RESULTS+=("并发$concurrent: ${rps} req/s, ${avg_time}ms avg, ${failed} failed")
            
            if [[ ${failed:-0} -eq 0 ]]; then
                log_success "并发$concurrent: ${rps} req/s, ${avg_time}ms, 无失败"
            else
                log_warning "并发$concurrent: ${rps} req/s, ${avg_time}ms, ${failed} 失败"
            fi
        else
            log_error "并发$concurrent: 测试失败"
        fi
        
        # 短暂休息
        sleep 5
    done
}

# 持续负载测试
sustained_load_test() {
    log_info "执行持续负载测试 (${TEST_DURATION}秒)..."
    
    local concurrent=20
    local test_endpoint="/api/v1/alerts"
    
    # 启动后台监控
    monitor_system_resources &
    local monitor_pid=$!
    
    # 执行持续负载测试
    local result
    result=$(ab -n 999999 -c $concurrent -t $TEST_DURATION -q "$BASE_URL$test_endpoint" 2>/dev/null)
    
    # 停止监控
    kill $monitor_pid 2>/dev/null || true
    
    if [[ -n "$result" ]]; then
        local total_requests=$(echo "$result" | grep "Complete requests" | awk '{print $3}')
        local failed_requests=$(echo "$result" | grep "Failed requests" | awk '{print $3}')
        local rps=$(echo "$result" | grep "Requests per second" | awk '{print $4}')
        local avg_time=$(echo "$result" | grep "Time per request" | head -1 | awk '{print $4}')
        
        TEST_RESULTS+=("持续负载: ${total_requests} 总请求, ${failed_requests} 失败, ${rps} req/s")
        
        log_success "持续负载测试完成:"
        log_info "  总请求数: $total_requests"
        log_info "  失败请求: $failed_requests"
        log_info "  平均RPS: $rps"
        log_info "  平均响应时间: ${avg_time}ms"
        
        # 计算成功率
        local success_rate
        success_rate=$(echo "scale=2; ($total_requests - $failed_requests) * 100 / $total_requests" | bc -l 2>/dev/null || echo "0")
        log_info "  成功率: ${success_rate}%"
    else
        log_error "持续负载测试失败"
    fi
}

# 系统资源监控
monitor_system_resources() {
    local monitor_file="$PROJECT_ROOT/test-results/resource-monitor-$(date +%Y%m%d-%H%M%S).log"
    mkdir -p "$(dirname "$monitor_file")"
    
    echo "timestamp,cpu_percent,memory_mb,disk_percent" > "$monitor_file"
    
    while true; do
        local timestamp=$(date +%s)
        local cpu_percent memory_mb disk_percent
        
        # 获取系统资源使用情况
        if command -v docker &> /dev/null; then
            # Docker环境
            local container_stats
            container_stats=$(docker stats --no-stream --format "table {{.CPUPerc}}\t{{.MemUsage}}" 2>/dev/null | grep -v "CPU" | head -1)
            
            if [[ -n "$container_stats" ]]; then
                cpu_percent=$(echo "$container_stats" | awk '{print $1}' | sed 's/%//')
                memory_mb=$(echo "$container_stats" | awk '{print $2}' | sed 's/MiB.*//')
            fi
        fi
        
        # 获取磁盘使用率
        disk_percent=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
        
        echo "$timestamp,${cpu_percent:-0},${memory_mb:-0},${disk_percent:-0}" >> "$monitor_file"
        
        sleep 10
    done
}

# 内存泄漏测试
memory_leak_test() {
    log_info "执行内存泄漏测试..."
    
    local initial_memory final_memory
    
    # 获取初始内存使用
    initial_memory=$(get_memory_usage)
    
    # 执行大量请求
    log_info "发送大量请求以检测内存泄漏..."
    for i in {1..1000}; do
        curl -s "$BASE_URL/api/v1/alerts" > /dev/null &
        
        # 控制并发数
        if (( i % 50 == 0 )); then
            wait
            sleep 1
        fi
    done
    
    wait
    sleep 10
    
    # 获取最终内存使用
    final_memory=$(get_memory_usage)
    
    if [[ -n "$initial_memory" && -n "$final_memory" ]]; then
        local memory_increase=$((final_memory - initial_memory))
        
        TEST_RESULTS+=("内存泄漏测试: 初始${initial_memory}MB, 最终${final_memory}MB, 增长${memory_increase}MB")
        
        if [[ $memory_increase -lt 100 ]]; then
            log_success "内存泄漏测试通过: 内存增长 ${memory_increase}MB"
        else
            log_warning "内存泄漏测试警告: 内存增长 ${memory_increase}MB"
        fi
    else
        log_warning "无法获取内存使用数据"
    fi
}

# 获取内存使用情况
get_memory_usage() {
    if command -v docker &> /dev/null; then
        docker stats --no-stream --format "{{.MemUsage}}" 2>/dev/null | head -1 | awk '{print $1}' | sed 's/MiB//'
    else
        # 系统内存使用
        free -m | grep "^Mem:" | awk '{print $3}'
    fi
}

# 错误处理测试
error_handling_test() {
    log_info "执行错误处理测试..."
    
    local error_scenarios=(
        "GET /api/v1/nonexistent 404"
        "POST /api/v1/alerts 405"
        "GET /api/v1/alerts/invalid-id 404"
    )
    
    for scenario in "${error_scenarios[@]}"; do
        local method endpoint expected_code
        read -r method endpoint expected_code <<< "$scenario"
        
        local actual_code
        actual_code=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" "$BASE_URL$endpoint")
        
        if [[ "$actual_code" == "$expected_code" ]]; then
            log_success "错误处理: $method $endpoint -> $actual_code ✓"
        else
            log_error "错误处理: $method $endpoint -> $actual_code (期望 $expected_code)"
        fi
    done
}

# 生成负载测试报告
generate_load_test_report() {
    local report_file="$PROJECT_ROOT/test-results/load-test-report-$(date +%Y%m%d-%H%M%S).md"
    mkdir -p "$(dirname "$report_file")"
    
    cat > "$report_file" << EOF
# MarketPrism 智能监控告警系统负载测试报告

## 测试概要

- **测试时间**: $(date)
- **测试地址**: $BASE_URL
- **测试持续时间**: ${TEST_DURATION}秒
- **最大并发数**: $MAX_CONCURRENT

## 测试结果

EOF
    
    for result in "${TEST_RESULTS[@]}"; do
        echo "- $result" >> "$report_file"
    done
    
    cat >> "$report_file" << EOF

## 性能建议

基于测试结果，以下是性能优化建议：

1. **响应时间优化**: 如果平均响应时间超过500ms，考虑优化数据库查询和缓存策略
2. **并发处理**: 如果高并发下出现失败请求，考虑增加工作进程数或实施限流
3. **内存管理**: 如果检测到内存泄漏，需要检查代码中的内存使用模式
4. **资源扩容**: 根据负载测试结果规划生产环境的资源配置

## 监控建议

- 设置响应时间告警阈值: 1000ms
- 设置错误率告警阈值: 5%
- 设置内存使用告警阈值: 80%
- 设置CPU使用告警阈值: 70%
EOF
    
    log_info "负载测试报告已生成: $report_file"
}

# 显示测试总结
show_test_summary() {
    echo ""
    echo "=========================================="
    echo "           负载测试结果总结"
    echo "=========================================="
    echo ""
    
    for result in "${TEST_RESULTS[@]}"; do
        echo "  $result"
    done
    
    echo ""
    log_success "负载测试完成！"
    echo ""
    echo "建议："
    echo "1. 查看详细的测试报告文件"
    echo "2. 根据测试结果调整生产环境配置"
    echo "3. 设置相应的监控告警阈值"
    echo "4. 定期执行负载测试以验证性能"
}

# 主函数
main() {
    log_info "开始 MarketPrism 智能监控告警系统负载测试"
    log_info "测试地址: $BASE_URL"
    log_info "测试持续时间: ${TEST_DURATION}秒"
    log_info "最大并发数: $MAX_CONCURRENT"
    echo ""
    
    # 检查依赖
    check_dependencies
    
    # 检查服务可用性
    if ! curl -f -s "$BASE_URL/health" > /dev/null; then
        log_error "服务不可用，请先启动服务"
        exit 1
    fi
    
    # 执行各项测试
    warmup_test
    baseline_performance_test
    concurrent_stress_test
    sustained_load_test
    memory_leak_test
    error_handling_test
    
    # 生成报告
    generate_load_test_report
    show_test_summary
}

# 错误处理
trap 'log_error "负载测试过程中发生错误"; exit 1' ERR

# 执行主函数
main "$@"
