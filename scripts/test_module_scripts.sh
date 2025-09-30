#!/bin/bash

################################################################################
# MarketPrism 模块管理脚本测试工具
# 
# 功能：测试三个核心模块的管理脚本是否正常工作
################################################################################

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[✓]${NC} $@"; }
log_warn() { echo -e "${YELLOW}[⚠]${NC} $@"; }
log_error() { echo -e "${RED}[✗]${NC} $@"; }
log_step() { echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo -e "${CYAN}  $@${NC}"; echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"; }

test_script_exists() {
    local module=$1
    local script_path="$PROJECT_ROOT/services/$module/scripts/manage.sh"
    
    if [ -f "$script_path" ]; then
        log_info "$module: 管理脚本存在"
        return 0
    else
        log_error "$module: 管理脚本不存在: $script_path"
        return 1
    fi
}

test_script_executable() {
    local module=$1
    local script_path="$PROJECT_ROOT/services/$module/scripts/manage.sh"
    
    if [ -x "$script_path" ]; then
        log_info "$module: 管理脚本可执行"
        return 0
    else
        log_error "$module: 管理脚本不可执行"
        return 1
    fi
}

test_script_help() {
    local module=$1
    local script_path="$PROJECT_ROOT/services/$module/scripts/manage.sh"
    
    if $script_path help > /dev/null 2>&1; then
        log_info "$module: help 命令正常"
        return 0
    else
        log_error "$module: help 命令失败"
        return 1
    fi
}

test_script_commands() {
    local module=$1
    local script_path="$PROJECT_ROOT/services/$module/scripts/manage.sh"
    
    local commands=("install-deps" "init" "start" "stop" "restart" "status" "health" "logs" "clean")
    local all_ok=true
    
    for cmd in "${commands[@]}"; do
        # 只测试命令是否被识别（不实际执行）
        if $script_path help 2>&1 | grep -q "$cmd"; then
            log_info "$module: $cmd 命令已定义"
        else
            log_warn "$module: $cmd 命令可能未定义"
            all_ok=false
        fi
    done
    
    if $all_ok; then
        return 0
    else
        return 1
    fi
}

test_module() {
    local module=$1
    
    log_step "测试模块: $module"
    
    local all_passed=true
    
    test_script_exists "$module" || all_passed=false
    test_script_executable "$module" || all_passed=false
    test_script_help "$module" || all_passed=false
    test_script_commands "$module" || all_passed=false
    
    if $all_passed; then
        log_info "$module: 所有测试通过 ✓"
        return 0
    else
        log_error "$module: 部分测试失败 ✗"
        return 1
    fi
}

main() {
    log_step "MarketPrism 模块管理脚本测试"
    
    cd "$PROJECT_ROOT"
    
    local all_modules_ok=true
    
    # 测试三个核心模块
    test_module "message-broker" || all_modules_ok=false
    test_module "data-storage-service" || all_modules_ok=false
    test_module "data-collector" || all_modules_ok=false
    
    log_step "测试总结"
    
    if $all_modules_ok; then
        log_info "所有模块的管理脚本测试通过！✓"
        echo ""
        echo "下一步："
        echo "  1. 测试单个模块部署："
        echo "     cd services/message-broker"
        echo "     ./scripts/manage.sh install-deps"
        echo "     ./scripts/manage.sh init"
        echo "     ./scripts/manage.sh start"
        echo ""
        echo "  2. 查看模块部署文档："
        echo "     cat docs/MODULE_DEPLOYMENT.md"
        echo ""
        return 0
    else
        log_error "部分模块的管理脚本测试失败 ✗"
        return 1
    fi
}

main "$@"

