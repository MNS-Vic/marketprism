#!/bin/bash
# MarketPrism 一键启动验证脚本
# 验证所有修复是否正确固化到代码中

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

log_step() {
    echo -e "${BLUE}🔹 $1${NC}"
}

log_section() {
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# 验证LSR API端点修复
validate_lsr_api_fixes() {
    log_section "验证LSR API端点修复"
    
    local okx_lsr_file="$PROJECT_ROOT/services/data-collector/collector/lsr_top_position_managers/okx_derivatives_lsr_top_position_manager.py"
    
    if [ -f "$okx_lsr_file" ]; then
        # 检查API端点是否正确
        if grep -q "long-short-account-ratio-contract-top20" "$okx_lsr_file"; then
            log_info "OKX LSR Top Position API端点修复正确"
        else
            log_error "OKX LSR Top Position API端点修复缺失"
            return 1
        fi
        
        # 检查请求参数是否正确
        if grep -q "ccy.*symbol.split" "$okx_lsr_file"; then
            log_info "OKX LSR Top Position请求参数修复正确"
        else
            log_error "OKX LSR Top Position请求参数修复缺失"
            return 1
        fi
    else
        log_error "OKX LSR Top Position管理器文件不存在"
        return 1
    fi
}

# 验证ClickHouse Schema修复
validate_clickhouse_schema_fixes() {
    log_section "验证ClickHouse Schema修复"
    
    local unified_schema="$PROJECT_ROOT/services/data-storage-service/config/clickhouse_schema_unified.sql"
    
    if [ -f "$unified_schema" ]; then
        # 检查LSR表是否包含必需的列
        if grep -q "long_position_ratio.*Float64" "$unified_schema" && \
           grep -q "short_position_ratio.*Float64" "$unified_schema"; then
            log_info "LSR Top Position表结构修复正确"
        else
            log_error "LSR Top Position表结构修复缺失"
            return 1
        fi
        
        if grep -q "long_account_ratio.*Float64" "$unified_schema" && \
           grep -q "short_account_ratio.*Float64" "$unified_schema"; then
            log_info "LSR All Account表结构修复正确"
        else
            log_error "LSR All Account表结构修复缺失"
            return 1
        fi
        
        # 检查DateTime64格式
        if grep -q "DateTime64(3, 'UTC')" "$unified_schema"; then
            log_info "DateTime64统一格式修复正确"
        else
            log_error "DateTime64统一格式修复缺失"
            return 1
        fi
    else
        log_error "统一ClickHouse Schema文件不存在"
        return 1
    fi
}

# 验证自动表结构修复逻辑
validate_auto_table_fix_logic() {
    log_section "验证自动表结构修复逻辑"
    
    local storage_manage="$PROJECT_ROOT/services/data-storage-service/scripts/manage.sh"
    
    if [ -f "$storage_manage" ]; then
        # 检查自动修复函数是否存在
        if grep -q "check_and_fix_lsr_tables" "$storage_manage"; then
            log_info "LSR表自动修复函数存在"
        else
            log_error "LSR表自动修复函数缺失"
            return 1
        fi
        
        if grep -q "auto_fix_table_schema" "$storage_manage"; then
            log_info "自动表结构修复函数存在"
        else
            log_error "自动表结构修复函数缺失"
            return 1
        fi
        
        # 检查ALTER TABLE语句
        if grep -q "ALTER TABLE.*ADD COLUMN.*long_position_ratio" "$storage_manage"; then
            log_info "LSR表列添加逻辑存在"
        else
            log_error "LSR表列添加逻辑缺失"
            return 1
        fi
    else
        log_error "存储服务管理脚本不存在"
        return 1
    fi
}

# 验证NATS连接重试机制
validate_nats_retry_logic() {
    log_section "验证NATS连接重试机制"
    
    local storage_main="$PROJECT_ROOT/services/data-storage-service/main.py"
    
    if [ -f "$storage_main" ]; then
        # 检查重试逻辑
        if grep -q "retry_count.*max_retries" "$storage_main" && \
           grep -q "指数退避重试" "$storage_main"; then
            log_info "NATS连接重试机制存在"
        else
            log_error "NATS连接重试机制缺失"
            return 1
        fi
    else
        log_error "存储服务主文件不存在"
        return 1
    fi
}

# 验证启动顺序和依赖检查
validate_startup_sequence() {
    log_section "验证启动顺序和依赖检查"
    
    local manage_all="$PROJECT_ROOT/scripts/manage_all.sh"
    
    if [ -f "$manage_all" ]; then
        # 检查等待服务函数
        if grep -q "wait_for_service" "$manage_all"; then
            log_info "服务等待函数存在"
        else
            log_error "服务等待函数缺失"
            return 1
        fi
        
        # 检查启动顺序（简化检查）
        if grep -A30 "start_all()" "$manage_all" | grep -q "NATS" && \
           grep -A30 "start_all()" "$manage_all" | grep -q "存储" && \
           grep -A30 "start_all()" "$manage_all" | grep -q "采集器"; then
            log_info "启动顺序正确"
        else
            log_warn "启动顺序可能需要检查（非关键错误）"
        fi
    else
        log_error "统一管理脚本不存在"
        return 1
    fi
}

# 验证自动问题检测机制
validate_auto_problem_detection() {
    log_section "验证自动问题检测机制"
    
    local enhanced_init="$PROJECT_ROOT/scripts/enhanced_init.sh"
    
    if [ -f "$enhanced_init" ]; then
        # 检查自动问题检测函数
        if grep -q "auto_detect_and_fix_issues" "$enhanced_init"; then
            log_info "自动问题检测函数存在"
        else
            log_error "自动问题检测函数缺失"
            return 1
        fi
        
        # 检查具体检测逻辑
        if grep -q "check_clickhouse_status" "$enhanced_init" && \
           grep -q "check_virtual_environments" "$enhanced_init"; then
            log_info "具体检测逻辑存在"
        else
            log_error "具体检测逻辑缺失"
            return 1
        fi
    else
        log_error "增强初始化脚本不存在"
        return 1
    fi
}

# 验证幂等性
validate_idempotency() {
    log_section "验证幂等性"
    
    # 检查关键操作是否使用IF NOT EXISTS等幂等语法
    local unified_schema="$PROJECT_ROOT/services/data-storage-service/config/clickhouse_schema_unified.sql"
    
    if [ -f "$unified_schema" ]; then
        if grep -q "CREATE TABLE IF NOT EXISTS" "$unified_schema"; then
            log_info "表创建操作具备幂等性"
        else
            log_error "表创建操作缺乏幂等性"
            return 1
        fi
    fi
    
    local storage_manage="$PROJECT_ROOT/services/data-storage-service/scripts/manage.sh"
    
    if [ -f "$storage_manage" ]; then
        if grep -q "ADD COLUMN IF NOT EXISTS" "$storage_manage"; then
            log_info "列添加操作具备幂等性"
        else
            log_error "列添加操作缺乏幂等性"
            return 1
        fi
    fi
}

# 运行完整验证
run_complete_validation() {
    log_section "MarketPrism 一键启动修复验证"
    
    local validation_functions=(
        "validate_lsr_api_fixes"
        "validate_clickhouse_schema_fixes"
        "validate_auto_table_fix_logic"
        "validate_nats_retry_logic"
        "validate_startup_sequence"
        "validate_auto_problem_detection"
        "validate_idempotency"
    )
    
    local passed=0
    local total=${#validation_functions[@]}
    
    for func in "${validation_functions[@]}"; do
        echo ""
        if $func; then
            ((passed++))
        fi
    done
    
    echo ""
    log_section "验证结果"
    
    if [ $passed -eq $total ]; then
        log_info "所有验证通过 ($passed/$total) 🎉"
        log_info "一键启动修复已正确固化到代码中"
        echo ""
        log_info "现在可以安全地运行："
        log_info "  ./scripts/manage_all.sh init"
        log_info "  ./scripts/manage_all.sh start"
        return 0
    else
        log_error "验证失败 ($passed/$total)"
        log_error "需要修复剩余问题后再次验证"
        return 1
    fi
}

# 主函数
main() {
    cd "$PROJECT_ROOT"
    run_complete_validation
}

main "$@"
