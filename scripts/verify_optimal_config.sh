#!/bin/bash

# 最优配置验证脚本
# 快速测试当前最优配置是否工作正常

set -e

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

TIMEOUT=5

print_header() {
    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║                    最优配置验证测试                           ║"
    echo "║              验证当前环境配置是否正常工作                     ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

test_with_timeout() {
    local cmd="$1"
    local name="$2"
    
    echo -n -e "${YELLOW}  ⏱️  测试 $name... ${NC}"
    
    if command -v gtimeout >/dev/null 2>&1; then
        if gtimeout $TIMEOUT bash -c "$cmd" >/dev/null 2>&1; then
            echo -e "${GREEN}✅ 成功${NC}"
            return 0
        else
            echo -e "${RED}❌ 失败${NC}"
            return 1
        fi
    elif command -v timeout >/dev/null 2>&1; then
        if timeout $TIMEOUT bash -c "$cmd" >/dev/null 2>&1; then
            echo -e "${GREEN}✅ 成功${NC}"
            return 0
        else
            echo -e "${RED}❌ 失败${NC}"
            return 1
        fi
    else
        # 自制超时机制
        (
            eval "$cmd" >/dev/null 2>&1 &
            TEST_PID=$!
            sleep $TIMEOUT && kill $TEST_PID 2>/dev/null &
            TIMER_PID=$!
            wait $TEST_PID 2>/dev/null
            TEST_RESULT=$?
            kill $TIMER_PID 2>/dev/null
            exit $TEST_RESULT
        )
        
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✅ 成功${NC}"
            return 0
        else
            echo -e "${RED}❌ 失败${NC}"
            return 1
        fi
    fi
}

main() {
    print_header
    
    echo -e "${BLUE}🔍 1. 测试代理连接${NC}"
    test_with_timeout "curl -s -I --proxy '$http_proxy' https://www.google.com" "代理连接"
    
    echo -e "${BLUE}🔍 2. 测试Docker镜像源${NC}"
    test_with_timeout "curl -s 'https://mirror.ccs.tencentyun.com/v2/'" "腾讯云Docker镜像源"
    
    echo -e "${BLUE}🔍 3. 测试Python包源${NC}"
    test_with_timeout "curl -s '$PIP_INDEX_URL'" "华为云Python包源"
    
    echo -e "${BLUE}🔍 4. 测试Go模块代理${NC}"
    test_with_timeout "curl -s '$GOPROXY'" "GoProxy.IO代理"
    
    echo -e "${BLUE}🔍 5. 测试环境变量设置${NC}"
    
    echo -n -e "${YELLOW}  📝 检查代理设置... ${NC}"
    if [ -n "$http_proxy" ] && [ -n "$https_proxy" ]; then
        echo -e "${GREEN}✅ 已设置${NC} ($http_proxy)"
    else
        echo -e "${RED}❌ 未设置${NC}"
    fi
    
    echo -n -e "${YELLOW}  📝 检查Python包源... ${NC}"
    if [ -n "$PIP_INDEX_URL" ]; then
        echo -e "${GREEN}✅ 已设置${NC} ($PIP_INDEX_URL)"
    else
        echo -e "${RED}❌ 未设置${NC}"
    fi
    
    echo -n -e "${YELLOW}  📝 检查Go代理... ${NC}"
    if [ -n "$GOPROXY" ]; then
        echo -e "${GREEN}✅ 已设置${NC} ($GOPROXY)"
    else
        echo -e "${RED}❌ 未设置${NC}"
    fi
    
    echo ""
    echo -e "${GREEN}🎉 配置验证完成！如果上述测试都通过，说明最优配置生效。${NC}"
    echo -e "${BLUE}💡 如有失败项目，请重新运行 comprehensive_source_tester.sh 更新配置。${NC}"
}

# 运行主函数
main "$@" 