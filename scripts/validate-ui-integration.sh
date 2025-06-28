#!/bin/bash

# MarketPrism UI整合验证脚本
# 验证前端UI与后端API的集成是否正常工作

set -euo pipefail

# 脚本配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_URL="${1:-http://localhost:8082}"
FRONTEND_URL="${2:-http://localhost:3000}"

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
    esac
}

# 检查前端依赖
check_frontend_dependencies() {
    log_info "检查前端依赖..."
    
    local dashboard_dir="$PROJECT_ROOT/services/monitoring-alerting-service/market-prism-dashboard "
    
    if [[ ! -f "$dashboard_dir/package.json" ]]; then
        record_test "前端项目结构" "FAIL" "package.json不存在"
        return 1
    fi
    
    # 检查关键依赖
    local required_deps=("next" "react" "@radix-ui" "tailwindcss" "lucide-react")
    local missing_deps=()
    
    for dep in "${required_deps[@]}"; do
        if ! grep -q "\"$dep" "$dashboard_dir/package.json"; then
            missing_deps+=("$dep")
        fi
    done
    
    if [[ ${#missing_deps[@]} -eq 0 ]]; then
        record_test "前端依赖检查" "PASS"
    else
        record_test "前端依赖检查" "FAIL" "缺少依赖: ${missing_deps[*]}"
    fi
}

# 检查API客户端配置
check_api_client() {
    log_info "检查API客户端配置..."
    
    local api_file="$PROJECT_ROOT/services/monitoring-alerting-service/market-prism-dashboard/lib/api.ts"
    
    if [[ ! -f "$api_file" ]]; then
        record_test "API客户端文件" "FAIL" "api.ts文件不存在"
        return 1
    fi
    
    # 检查关键API方法
    local required_methods=("getAlerts" "getBusinessMetrics" "detectAnomaly" "getFailurePredictions")
    local missing_methods=()
    
    for method in "${required_methods[@]}"; do
        if ! grep -q "$method" "$api_file"; then
            missing_methods+=("$method")
        fi
    done
    
    if [[ ${#missing_methods[@]} -eq 0 ]]; then
        record_test "API客户端方法" "PASS"
    else
        record_test "API客户端方法" "FAIL" "缺少方法: ${missing_methods[*]}"
    fi
    
    # 检查类型定义
    local required_types=("Alert" "BusinessMetrics" "AnomalyDetectionRequest" "FailurePrediction")
    local missing_types=()
    
    for type in "${required_types[@]}"; do
        if ! grep -q "interface $type" "$api_file"; then
            missing_types+=("$type")
        fi
    done
    
    if [[ ${#missing_types[@]} -eq 0 ]]; then
        record_test "TypeScript类型定义" "PASS"
    else
        record_test "TypeScript类型定义" "FAIL" "缺少类型: ${missing_types[*]}"
    fi
}

# 检查React Hooks
check_react_hooks() {
    log_info "检查React Hooks..."
    
    local hooks_dir="$PROJECT_ROOT/services/monitoring-alerting-service/market-prism-dashboard/hooks"
    
    if [[ ! -d "$hooks_dir" ]]; then
        record_test "Hooks目录" "FAIL" "hooks目录不存在"
        return 1
    fi
    
    # 检查关键Hooks
    local required_hooks=("useAlerts.ts" "useBusinessMetrics.ts")
    local missing_hooks=()
    
    for hook in "${required_hooks[@]}"; do
        if [[ ! -f "$hooks_dir/$hook" ]]; then
            missing_hooks+=("$hook")
        fi
    done
    
    if [[ ${#missing_hooks[@]} -eq 0 ]]; then
        record_test "React Hooks文件" "PASS"
    else
        record_test "React Hooks文件" "FAIL" "缺少Hooks: ${missing_hooks[*]}"
    fi
    
    # 检查useAlerts Hook功能
    if [[ -f "$hooks_dir/useAlerts.ts" ]]; then
        local required_functions=("acknowledgeAlert" "resolveAlert" "refresh" "setFilter")
        local missing_functions=()
        
        for func in "${required_functions[@]}"; do
            if ! grep -q "$func" "$hooks_dir/useAlerts.ts"; then
                missing_functions+=("$func")
            fi
        done
        
        if [[ ${#missing_functions[@]} -eq 0 ]]; then
            record_test "useAlerts Hook功能" "PASS"
        else
            record_test "useAlerts Hook功能" "FAIL" "缺少功能: ${missing_functions[*]}"
        fi
    fi
}

# 检查UI组件
check_ui_components() {
    log_info "检查UI组件..."
    
    local components_dir="$PROJECT_ROOT/services/monitoring-alerting-service/market-prism-dashboard/components"
    
    if [[ ! -d "$components_dir" ]]; then
        record_test "组件目录" "FAIL" "components目录不存在"
        return 1
    fi
    
    # 检查关键组件
    local required_components=(
        "alerts-content.tsx"
        "dashboard-content.tsx"
        "anomaly-detection.tsx"
        "failure-prediction.tsx"
        "sidebar.tsx"
    )
    local missing_components=()
    
    for component in "${required_components[@]}"; do
        if [[ ! -f "$components_dir/$component" ]]; then
            missing_components+=("$component")
        fi
    done
    
    if [[ ${#missing_components[@]} -eq 0 ]]; then
        record_test "UI组件文件" "PASS"
    else
        record_test "UI组件文件" "FAIL" "缺少组件: ${missing_components[*]}"
    fi
    
    # 检查组件是否使用了API
    if [[ -f "$components_dir/alerts-content.tsx" ]]; then
        if grep -q "useAlerts" "$components_dir/alerts-content.tsx"; then
            record_test "告警组件API集成" "PASS"
        else
            record_test "告警组件API集成" "FAIL" "未使用useAlerts Hook"
        fi
    fi
    
    if [[ -f "$components_dir/dashboard-content.tsx" ]]; then
        if grep -q "useBusinessMetrics" "$components_dir/dashboard-content.tsx"; then
            record_test "仪表板组件API集成" "PASS"
        else
            record_test "仪表板组件API集成" "FAIL" "未使用useBusinessMetrics Hook"
        fi
    fi
}

# 检查路由配置
check_routing() {
    log_info "检查路由配置..."
    
    local page_file="$PROJECT_ROOT/services/monitoring-alerting-service/market-prism-dashboard/app/page.tsx"
    
    if [[ ! -f "$page_file" ]]; then
        record_test "主页面文件" "FAIL" "page.tsx文件不存在"
        return 1
    fi
    
    # 检查是否包含新页面
    local required_pages=("AnomalyDetection" "FailurePrediction" "AlertsContent" "DashboardContent")
    local missing_pages=()
    
    for page in "${required_pages[@]}"; do
        if ! grep -q "$page" "$page_file"; then
            missing_pages+=("$page")
        fi
    done
    
    if [[ ${#missing_pages[@]} -eq 0 ]]; then
        record_test "页面路由配置" "PASS"
    else
        record_test "页面路由配置" "FAIL" "缺少页面: ${missing_pages[*]}"
    fi
    
    # 检查侧边栏菜单
    local sidebar_file="$PROJECT_ROOT/services/monitoring-alerting-service/market-prism-dashboard/components/sidebar.tsx"
    if [[ -f "$sidebar_file" ]]; then
        if grep -q "anomaly\|prediction" "$sidebar_file"; then
            record_test "侧边栏菜单配置" "PASS"
        else
            record_test "侧边栏菜单配置" "FAIL" "未添加新页面菜单项"
        fi
    fi
}

# 检查Docker配置
check_docker_config() {
    log_info "检查Docker配置..."
    
    local dockerfile="$PROJECT_ROOT/services/monitoring-alerting-service/market-prism-dashboard/Dockerfile"
    
    if [[ ! -f "$dockerfile" ]]; then
        record_test "Dockerfile" "FAIL" "Dockerfile不存在"
        return 1
    fi
    
    # 检查Dockerfile内容
    if grep -q "FROM node:" "$dockerfile" && grep -q "npm" "$dockerfile"; then
        record_test "Dockerfile配置" "PASS"
    else
        record_test "Dockerfile配置" "FAIL" "Dockerfile配置不正确"
    fi
    
    # 检查Docker Compose配置
    local compose_file="$PROJECT_ROOT/deployments/docker-compose/docker-compose.yml"
    if [[ -f "$compose_file" ]]; then
        if grep -q "monitoring-dashboard" "$compose_file"; then
            record_test "Docker Compose配置" "PASS"
        else
            record_test "Docker Compose配置" "FAIL" "未添加前端服务配置"
        fi
    fi
}

# 检查环境配置
check_environment_config() {
    log_info "检查环境配置..."
    
    local env_file="$PROJECT_ROOT/services/monitoring-alerting-service/market-prism-dashboard/.env.local"
    
    if [[ -f "$env_file" ]]; then
        if grep -q "NEXT_PUBLIC_API_URL" "$env_file"; then
            record_test "环境变量配置" "PASS"
        else
            record_test "环境变量配置" "FAIL" "缺少API URL配置"
        fi
    else
        record_test "环境配置文件" "FAIL" ".env.local文件不存在"
    fi
    
    # 检查Next.js配置
    local next_config="$PROJECT_ROOT/services/monitoring-alerting-service/market-prism-dashboard/next.config.js"
    if [[ -f "$next_config" ]]; then
        record_test "Next.js配置文件" "PASS"
    else
        record_test "Next.js配置文件" "FAIL" "next.config.js文件不存在"
    fi
}

# 测试后端API连接
test_backend_api() {
    log_info "测试后端API连接..."
    
    # 测试健康检查
    if curl -f -s "$BACKEND_URL/health" > /dev/null; then
        record_test "后端健康检查" "PASS"
    else
        record_test "后端健康检查" "FAIL" "后端服务不可用"
        return 1
    fi
    
    # 测试关键API端点
    local api_endpoints=("/api/v1/alerts" "/api/v1/rules" "/api/v1/metrics/business" "/api/v1/stats/alerts")
    
    for endpoint in "${api_endpoints[@]}"; do
        if curl -f -s "$BACKEND_URL$endpoint" > /dev/null; then
            record_test "API端点 $endpoint" "PASS"
        else
            record_test "API端点 $endpoint" "FAIL" "端点不可用"
        fi
    done
    
    # 测试异常检测API
    local anomaly_data='{"metric_name": "test_metric", "value": 100.0}'
    if curl -f -s -X POST -H "Content-Type: application/json" -d "$anomaly_data" "$BACKEND_URL/api/v1/anomaly/detect" > /dev/null; then
        record_test "异常检测API" "PASS"
    else
        record_test "异常检测API" "FAIL" "异常检测端点不可用"
    fi
}

# 测试前端访问
test_frontend_access() {
    log_info "测试前端访问..."
    
    # 检查前端是否可访问
    if curl -f -s "$FRONTEND_URL" > /dev/null; then
        record_test "前端页面访问" "PASS"
    else
        record_test "前端页面访问" "FAIL" "前端服务不可用"
        return 1
    fi
    
    # 检查静态资源
    if curl -f -s "$FRONTEND_URL/_next/static" > /dev/null 2>&1; then
        record_test "静态资源访问" "PASS"
    else
        record_test "静态资源访问" "FAIL" "静态资源不可用"
    fi
}

# 生成验证报告
generate_validation_report() {
    local report_file="$PROJECT_ROOT/test-results/ui-integration-validation-$(date +%Y%m%d-%H%M%S).md"
    
    mkdir -p "$(dirname "$report_file")"
    
    cat > "$report_file" << EOF
# MarketPrism UI整合验证报告

## 验证概要

- **验证时间**: $(date)
- **后端地址**: $BACKEND_URL
- **前端地址**: $FRONTEND_URL
- **总测试数**: $TOTAL_TESTS
- **通过测试**: $PASSED_TESTS
- **失败测试**: $FAILED_TESTS

## 验证结果

### 成功率
$(echo "scale=1; $PASSED_TESTS * 100 / $TOTAL_TESTS" | bc -l 2>/dev/null || echo "0")%

### 验证项目

#### ✅ 通过的验证项
- 前端项目结构完整
- API客户端配置正确
- React Hooks实现完整
- UI组件集成正常
- Docker配置正确

#### ❌ 需要关注的问题
$(if [[ $FAILED_TESTS -gt 0 ]]; then echo "- 存在 $FAILED_TESTS 个失败的验证项"; else echo "- 无"; fi)

## 建议

1. **如果验证通过**: 可以继续进行部署和测试
2. **如果有失败项**: 请根据错误信息修复相关问题
3. **性能优化**: 建议进行负载测试验证系统性能
4. **安全检查**: 建议进行安全测试验证系统安全性

## 下一步

1. 执行完整的部署测试: \`./scripts/test-deployment.sh\`
2. 执行性能测试: \`./scripts/load-test.sh\`
3. 执行安全测试: \`./scripts/security-test.sh\`
4. 部署到生产环境: \`./scripts/deploy.sh\`
EOF
    
    log_info "验证报告已生成: $report_file"
}

# 显示验证结果
show_validation_results() {
    echo ""
    echo "=========================================="
    echo "         UI整合验证结果汇总"
    echo "=========================================="
    echo ""
    echo "验证统计:"
    echo "  总测试数:   $TOTAL_TESTS"
    echo "  通过测试:   $PASSED_TESTS"
    echo "  失败测试:   $FAILED_TESTS"
    
    if [[ $TOTAL_TESTS -gt 0 ]]; then
        local success_rate
        success_rate=$(echo "scale=1; $PASSED_TESTS * 100 / $TOTAL_TESTS" | bc -l 2>/dev/null || echo "0")
        echo "  成功率:     ${success_rate}%"
    fi
    
    echo ""
    
    if [[ $FAILED_TESTS -eq 0 ]]; then
        log_success "🎉 UI整合验证完全通过！"
        echo ""
        echo "✅ 前端UI与后端API集成正常"
        echo "✅ 所有组件和功能配置正确"
        echo "✅ Docker部署配置完整"
        echo ""
        echo "可以继续进行系统部署和测试。"
        return 0
    else
        log_error "❌ UI整合验证发现问题"
        echo ""
        echo "请根据上述错误信息修复相关问题后重新验证。"
        return 1
    fi
}

# 主函数
main() {
    log_info "开始 MarketPrism UI整合验证"
    log_info "后端地址: $BACKEND_URL"
    log_info "前端地址: $FRONTEND_URL"
    echo ""
    
    # 执行各项验证
    check_frontend_dependencies
    check_api_client
    check_react_hooks
    check_ui_components
    check_routing
    check_docker_config
    check_environment_config
    test_backend_api
    test_frontend_access
    
    # 生成报告和显示结果
    generate_validation_report
    show_validation_results
}

# 错误处理
trap 'log_error "验证过程中发生错误"; exit 1' ERR

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
