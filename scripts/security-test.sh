#!/bin/bash

# MarketPrism 智能监控告警系统安全测试脚本
# 执行全面的安全验证，包括认证、授权、输入验证和安全配置检查

set -euo pipefail

# 脚本配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BASE_URL="${1:-http://localhost:8082}"
DEPLOYMENT_TYPE="${2:-docker-compose}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 测试结果统计
TOTAL_SECURITY_TESTS=0
PASSED_SECURITY_TESTS=0
FAILED_SECURITY_TESTS=0
SECURITY_ISSUES=()

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

# 安全测试结果记录
record_security_test() {
    local test_name="$1"
    local result="$2"
    local severity="${3:-medium}"
    local message="${4:-}"
    
    ((TOTAL_SECURITY_TESTS++))
    
    case "$result" in
        "PASS")
            ((PASSED_SECURITY_TESTS++))
            log_success "✓ $test_name"
            ;;
        "FAIL")
            ((FAILED_SECURITY_TESTS++))
            log_error "✗ $test_name: $message"
            SECURITY_ISSUES+=("[$severity] $test_name: $message")
            ;;
        "WARNING")
            log_warning "⚠ $test_name: $message"
            SECURITY_ISSUES+=("[warning] $test_name: $message")
            ;;
    esac
}

# HTTP请求函数
make_security_request() {
    local method="$1"
    local endpoint="$2"
    local data="${3:-}"
    local headers="${4:-}"
    local expected_status="${5:-}"
    
    local url="$BASE_URL$endpoint"
    local curl_cmd="curl -s -w '\n%{http_code}' -X $method"
    
    if [[ -n "$headers" ]]; then
        curl_cmd="$curl_cmd $headers"
    fi
    
    if [[ -n "$data" ]]; then
        curl_cmd="$curl_cmd -H 'Content-Type: application/json' -d '$data'"
    fi
    
    curl_cmd="$curl_cmd '$url'"
    
    local response
    response=$(eval "$curl_cmd" 2>/dev/null || echo -e "\n000")
    
    local status_code
    status_code=$(echo "$response" | tail -n1)
    local response_body
    response_body=$(echo "$response" | head -n -1)
    
    if [[ -n "$expected_status" ]]; then
        if [[ "$status_code" == "$expected_status" ]]; then
            echo "$response_body"
            return 0
        else
            return 1
        fi
    else
        echo "$response_body"
        return 0
    fi
}

# 认证和授权测试
test_authentication_authorization() {
    log_info "执行认证和授权测试..."
    
    # 测试未授权访问敏感端点
    local sensitive_endpoints=(
        "/api/v1/admin/config"
        "/api/v1/admin/users"
        "/api/v1/admin/logs"
    )
    
    for endpoint in "${sensitive_endpoints[@]}"; do
        local status_code
        status_code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL$endpoint")
        
        if [[ "$status_code" == "401" || "$status_code" == "403" || "$status_code" == "404" ]]; then
            record_security_test "未授权访问保护 ($endpoint)" "PASS"
        else
            record_security_test "未授权访问保护 ($endpoint)" "FAIL" "high" "返回状态码 $status_code，应该拒绝访问"
        fi
    done
    
    # 测试无效Token
    if make_security_request "GET" "/api/v1/alerts" "" "-H 'Authorization: Bearer invalid_token'" "401" > /dev/null 2>&1; then
        record_security_test "无效Token验证" "PASS"
    else
        record_security_test "无效Token验证" "FAIL" "medium" "应该拒绝无效Token"
    fi
    
    # 测试Token格式验证
    local malformed_tokens=(
        "Bearer "
        "Bearer malformed.token"
        "InvalidFormat token"
    )
    
    for token in "${malformed_tokens[@]}"; do
        local status_code
        status_code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: $token" "$BASE_URL/api/v1/alerts")
        
        if [[ "$status_code" == "401" ]]; then
            record_security_test "Token格式验证 ($token)" "PASS"
        else
            record_security_test "Token格式验证 ($token)" "FAIL" "medium" "应该拒绝格式错误的Token"
        fi
    done
}

# 输入验证测试
test_input_validation() {
    log_info "执行输入验证测试..."
    
    # SQL注入测试
    local sql_injection_payloads=(
        "'; DROP TABLE alerts; --"
        "' OR '1'='1"
        "'; SELECT * FROM users; --"
        "admin'--"
        "' UNION SELECT * FROM information_schema.tables --"
    )
    
    for payload in "${sql_injection_payloads[@]}"; do
        local test_data="{\"metric_name\": \"$payload\", \"value\": 100.0}"
        local response
        response=$(make_security_request "POST" "/api/v1/anomaly/detect" "$test_data")
        
        # 检查响应中是否包含数据库错误信息
        if echo "$response" | grep -qi -E "(sql|database|mysql|postgresql|sqlite|error|exception)"; then
            record_security_test "SQL注入防护 ($payload)" "FAIL" "high" "可能存在SQL注入漏洞"
        else
            record_security_test "SQL注入防护 ($payload)" "PASS"
        fi
    done
    
    # XSS测试
    local xss_payloads=(
        "<script>alert('xss')</script>"
        "<img src=x onerror=alert('xss')>"
        "javascript:alert('xss')"
        "<svg onload=alert('xss')>"
        "';alert('xss');//"
    )
    
    for payload in "${xss_payloads[@]}"; do
        local test_data="{\"name\": \"$payload\", \"description\": \"test\"}"
        local response
        response=$(make_security_request "POST" "/api/v1/anomaly/detect" "$test_data")
        
        # 检查响应中是否包含未转义的脚本
        if echo "$response" | grep -q "<script>\|<img\|javascript:\|<svg"; then
            record_security_test "XSS防护 ($payload)" "FAIL" "high" "响应中包含未转义的脚本"
        else
            record_security_test "XSS防护 ($payload)" "PASS"
        fi
    done
    
    # 命令注入测试
    local command_injection_payloads=(
        "; ls -la"
        "| cat /etc/passwd"
        "&& whoami"
        "; rm -rf /"
        "\$(id)"
    )
    
    for payload in "${command_injection_payloads[@]}"; do
        local test_data="{\"metric_name\": \"test$payload\", \"value\": 100.0}"
        local response
        response=$(make_security_request "POST" "/api/v1/anomaly/detect" "$test_data")
        
        # 检查响应中是否包含命令执行结果
        if echo "$response" | grep -qi -E "(root:|bin/|usr/|etc/|var/)"; then
            record_security_test "命令注入防护 ($payload)" "FAIL" "critical" "可能存在命令注入漏洞"
        else
            record_security_test "命令注入防护 ($payload)" "PASS"
        fi
    done
}

# HTTP安全头检查
test_security_headers() {
    log_info "执行HTTP安全头检查..."
    
    local response_headers
    response_headers=$(curl -s -I "$BASE_URL/health")
    
    # 检查安全头
    local security_headers=(
        "X-Content-Type-Options:nosniff"
        "X-Frame-Options"
        "X-XSS-Protection"
        "Strict-Transport-Security"
        "Content-Security-Policy"
    )
    
    for header in "${security_headers[@]}"; do
        local header_name
        header_name=$(echo "$header" | cut -d: -f1)
        
        if echo "$response_headers" | grep -qi "$header_name"; then
            record_security_test "安全头检查 ($header_name)" "PASS"
        else
            record_security_test "安全头检查 ($header_name)" "WARNING" "low" "缺少安全头"
        fi
    done
    
    # 检查敏感信息泄露
    if echo "$response_headers" | grep -qi -E "(server:|x-powered-by:|x-aspnet-version:)"; then
        record_security_test "服务器信息泄露检查" "WARNING" "low" "响应头中包含服务器信息"
    else
        record_security_test "服务器信息泄露检查" "PASS"
    fi
}

# 容器安全检查
test_container_security() {
    if [[ "$DEPLOYMENT_TYPE" != "docker-compose" ]]; then
        log_info "跳过容器安全检查（非Docker部署）"
        return
    fi
    
    log_info "执行容器安全检查..."
    
    # 检查容器是否以root用户运行
    local container_user
    container_user=$(docker exec marketprism-monitoring-alerting whoami 2>/dev/null || echo "unknown")
    
    if [[ "$container_user" == "root" ]]; then
        record_security_test "容器用户权限检查" "FAIL" "medium" "容器以root用户运行"
    elif [[ "$container_user" != "unknown" ]]; then
        record_security_test "容器用户权限检查" "PASS"
    else
        record_security_test "容器用户权限检查" "WARNING" "low" "无法检查容器用户"
    fi
    
    # 检查容器特权模式
    local privileged
    privileged=$(docker inspect marketprism-monitoring-alerting --format='{{.HostConfig.Privileged}}' 2>/dev/null || echo "unknown")
    
    if [[ "$privileged" == "true" ]]; then
        record_security_test "容器特权模式检查" "FAIL" "high" "容器运行在特权模式"
    elif [[ "$privileged" == "false" ]]; then
        record_security_test "容器特权模式检查" "PASS"
    else
        record_security_test "容器特权模式检查" "WARNING" "low" "无法检查容器特权模式"
    fi
    
    # 检查容器网络模式
    local network_mode
    network_mode=$(docker inspect marketprism-monitoring-alerting --format='{{.HostConfig.NetworkMode}}' 2>/dev/null || echo "unknown")
    
    if [[ "$network_mode" == "host" ]]; then
        record_security_test "容器网络模式检查" "WARNING" "medium" "容器使用host网络模式"
    elif [[ "$network_mode" != "unknown" ]]; then
        record_security_test "容器网络模式检查" "PASS"
    else
        record_security_test "容器网络模式检查" "WARNING" "low" "无法检查容器网络模式"
    fi
}

# 敏感信息泄露检查
test_information_disclosure() {
    log_info "执行敏感信息泄露检查..."
    
    # 检查错误信息泄露
    local error_endpoints=(
        "/api/v1/nonexistent"
        "/api/v1/alerts/invalid-id"
        "/api/v1/rules/999999"
    )
    
    for endpoint in "${error_endpoints[@]}"; do
        local response
        response=$(make_security_request "GET" "$endpoint")
        
        # 检查是否泄露敏感信息
        if echo "$response" | grep -qi -E "(stack trace|file path|database|password|secret|token)"; then
            record_security_test "错误信息泄露检查 ($endpoint)" "FAIL" "medium" "错误响应中包含敏感信息"
        else
            record_security_test "错误信息泄露检查 ($endpoint)" "PASS"
        fi
    done
    
    # 检查调试信息泄露
    local debug_endpoints=(
        "/debug"
        "/api/debug"
        "/api/v1/debug"
        "/.env"
        "/config"
    )
    
    for endpoint in "${debug_endpoints[@]}"; do
        local status_code
        status_code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL$endpoint")
        
        if [[ "$status_code" == "200" ]]; then
            record_security_test "调试信息泄露检查 ($endpoint)" "FAIL" "medium" "调试端点可访问"
        else
            record_security_test "调试信息泄露检查 ($endpoint)" "PASS"
        fi
    done
}

# 拒绝服务攻击测试
test_dos_protection() {
    log_info "执行拒绝服务攻击测试..."
    
    # 大请求体测试
    local large_data
    large_data=$(printf '{"data":"%*s"}' 10000 "")
    
    local status_code
    status_code=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        -H "Content-Type: application/json" \
        -d "$large_data" \
        "$BASE_URL/api/v1/anomaly/detect")
    
    if [[ "$status_code" == "413" || "$status_code" == "400" ]]; then
        record_security_test "大请求体保护" "PASS"
    else
        record_security_test "大请求体保护" "WARNING" "medium" "可能缺少请求大小限制"
    fi
    
    # 快速请求测试
    log_info "测试快速请求限制..."
    local success_count=0
    
    for i in {1..20}; do
        local status_code
        status_code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
        
        if [[ "$status_code" == "200" ]]; then
            ((success_count++))
        fi
    done
    
    if [[ $success_count -eq 20 ]]; then
        record_security_test "请求频率限制" "WARNING" "low" "可能缺少请求频率限制"
    else
        record_security_test "请求频率限制" "PASS"
    fi
}

# 配置安全检查
test_configuration_security() {
    log_info "执行配置安全检查..."
    
    if [[ "$DEPLOYMENT_TYPE" == "docker-compose" ]]; then
        local env_file="$PROJECT_ROOT/deployments/docker-compose/.env"
        
        if [[ -f "$env_file" ]]; then
            # 检查默认密码
            if grep -qi "password.*admin\|password.*123\|password.*password" "$env_file"; then
                record_security_test "默认密码检查" "FAIL" "high" "发现默认密码"
            else
                record_security_test "默认密码检查" "PASS"
            fi
            
            # 检查空密码
            if grep -E "PASSWORD=\s*$|SECRET=\s*$" "$env_file"; then
                record_security_test "空密码检查" "FAIL" "high" "发现空密码"
            else
                record_security_test "空密码检查" "PASS"
            fi
        else
            record_security_test "配置文件检查" "WARNING" "medium" "配置文件不存在"
        fi
    fi
}

# 生成安全测试报告
generate_security_report() {
    local report_file="$PROJECT_ROOT/test-results/security-test-report-$(date +%Y%m%d-%H%M%S).md"
    mkdir -p "$(dirname "$report_file")"
    
    cat > "$report_file" << EOF
# MarketPrism 智能监控告警系统安全测试报告

## 测试概要

- **测试时间**: $(date)
- **测试地址**: $BASE_URL
- **部署类型**: $DEPLOYMENT_TYPE
- **总测试数**: $TOTAL_SECURITY_TESTS
- **通过测试**: $PASSED_SECURITY_TESTS
- **失败测试**: $FAILED_SECURITY_TESTS

## 安全问题汇总

EOF
    
    if [[ ${#SECURITY_ISSUES[@]} -eq 0 ]]; then
        echo "✅ 未发现安全问题" >> "$report_file"
    else
        for issue in "${SECURITY_ISSUES[@]}"; do
            echo "- $issue" >> "$report_file"
        done
    fi
    
    cat >> "$report_file" << EOF

## 安全建议

1. **认证和授权**
   - 实施强密码策略
   - 启用多因素认证
   - 定期轮换API密钥

2. **输入验证**
   - 对所有用户输入进行严格验证
   - 使用参数化查询防止SQL注入
   - 实施输出编码防止XSS

3. **HTTP安全**
   - 配置所有必要的安全头
   - 启用HTTPS
   - 隐藏服务器版本信息

4. **容器安全**
   - 使用非root用户运行容器
   - 避免特权模式
   - 定期更新基础镜像

5. **监控和日志**
   - 启用安全事件日志
   - 实施实时安全监控
   - 设置安全告警

## 合规性检查

- [ ] OWASP Top 10 检查
- [ ] 数据保护法规合规
- [ ] 安全审计要求
- [ ] 渗透测试建议
EOF
    
    log_info "安全测试报告已生成: $report_file"
}

# 显示安全测试结果
show_security_results() {
    echo ""
    echo "=========================================="
    echo "           安全测试结果汇总"
    echo "=========================================="
    echo ""
    echo "测试统计:"
    echo "  总测试数:   $TOTAL_SECURITY_TESTS"
    echo "  通过测试:   $PASSED_SECURITY_TESTS"
    echo "  失败测试:   $FAILED_SECURITY_TESTS"
    
    if [[ $TOTAL_SECURITY_TESTS -gt 0 ]]; then
        local success_rate
        success_rate=$(echo "scale=1; $PASSED_SECURITY_TESTS * 100 / $TOTAL_SECURITY_TESTS" | bc -l 2>/dev/null || echo "0")
        echo "  成功率:     ${success_rate}%"
    fi
    
    echo ""
    
    if [[ ${#SECURITY_ISSUES[@]} -eq 0 ]]; then
        log_success "所有安全测试通过！"
        return 0
    else
        log_error "发现 ${#SECURITY_ISSUES[@]} 个安全问题："
        for issue in "${SECURITY_ISSUES[@]}"; do
            echo "  - $issue"
        done
        echo ""
        log_warning "请查看详细的安全测试报告并及时修复安全问题"
        return 1
    fi
}

# 主函数
main() {
    log_info "开始 MarketPrism 智能监控告警系统安全测试"
    log_info "测试地址: $BASE_URL"
    log_info "部署类型: $DEPLOYMENT_TYPE"
    echo ""
    
    # 检查服务可用性
    if ! curl -f -s "$BASE_URL/health" > /dev/null; then
        log_error "服务不可用，请先启动服务"
        exit 1
    fi
    
    # 执行各项安全测试
    test_authentication_authorization
    test_input_validation
    test_security_headers
    test_container_security
    test_information_disclosure
    test_dos_protection
    test_configuration_security
    
    # 生成报告和显示结果
    generate_security_report
    show_security_results
}

# 错误处理
trap 'log_error "安全测试过程中发生错误"; exit 1' ERR

# 检查依赖
if ! command -v curl &> /dev/null; then
    log_error "curl未安装，请先安装curl"
    exit 1
fi

if ! command -v bc &> /dev/null; then
    log_warning "bc未安装，某些计算功能可能不可用"
fi

# 执行主函数
main "$@"
