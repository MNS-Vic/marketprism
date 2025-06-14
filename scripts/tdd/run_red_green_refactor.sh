#!/bin/bash

# MarketPrism TDD循环执行脚本
# 实现红-绿-重构的TDD核心循环

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

# 获取项目根目录
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$PROJECT_ROOT"

echo "=================================================="
echo -e "${PURPLE}🔄 MarketPrism TDD 循环执行器${NC}"
echo "=================================================="

# 解析参数
PHASE=""
SERVICE=""
TEST_FILE=""
CONTINUOUS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --phase)
            PHASE="$2"
            shift 2
            ;;
        --service)
            SERVICE="$2"
            shift 2
            ;;
        --test-file)
            TEST_FILE="$2"
            shift 2
            ;;
        --continuous)
            CONTINUOUS=true
            shift
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done

# 如果未指定，尝试自动检测
if [ -z "$TEST_FILE" ]; then
    if [ -n "$PHASE" ]; then
        case $PHASE in
            "env"|"environment")
                TEST_FILE="tests/startup/test_environment_dependencies.py"
                ;;
            "service"|"startup")
                TEST_FILE="tests/startup/test_individual_service_startup.py"
                ;;
            "config"|"port")
                TEST_FILE="tests/config/test_port_configuration.py"
                ;;
            *)
                echo "未知阶段: $PHASE"
                exit 1
                ;;
        esac
    else
        TEST_FILE="tests/startup/test_environment_dependencies.py"
    fi
fi

echo -e "${BLUE}📋 TDD配置${NC}"
echo "  测试文件: $TEST_FILE"
echo "  目标服务: ${SERVICE:-"所有服务"}"
echo "  连续模式: ${CONTINUOUS}"
echo ""

# TDD循环函数
run_tdd_cycle() {
    local cycle_count=1
    
    while true; do
        echo "=================================================="
        echo -e "${PURPLE}🔄 TDD 循环 #$cycle_count${NC}"
        echo "=================================================="
        
        # RED 阶段: 运行测试，期望失败
        echo -e "\n${RED}🔴 RED 阶段: 运行测试 (期望失败)${NC}"
        echo "--------------------------------------------------"
        
        if run_tests "RED"; then
            echo -e "${YELLOW}⚠️  测试意外通过！检查测试是否正确反映了问题${NC}"
        else
            echo -e "${RED}✅ 测试按预期失败，问题已明确定义${NC}"
        fi
        
        # 暂停让用户查看红色阶段结果
        if [ "$CONTINUOUS" = false ]; then
            echo -e "\n${BLUE}按 Enter 进入 GREEN 阶段...${NC}"
            read -r
        else
            sleep 3
        fi
        
        # GREEN 阶段: 最小修复让测试通过
        echo -e "\n${GREEN}🟢 GREEN 阶段: 最小修复让测试通过${NC}"
        echo "--------------------------------------------------"
        
        # 提供修复建议
        suggest_fixes
        
        echo -e "${GREEN}💡 请进行最小修复让测试通过...${NC}"
        if [ "$CONTINUOUS" = false ]; then
            echo -e "${BLUE}修复完成后按 Enter 运行测试...${NC}"
            read -r
        else
            echo -e "${BLUE}自动等待 30 秒进行修复...${NC}"
            sleep 30
        fi
        
        # 运行测试验证修复
        if run_tests "GREEN"; then
            echo -e "${GREEN}🎉 GREEN 阶段成功！测试通过${NC}"
        else
            echo -e "${RED}❌ 修复不足，测试仍然失败${NC}"
            if [ "$CONTINUOUS" = false ]; then
                echo -e "${BLUE}继续修复还是进入下一轮？(继续修复请按 Enter，下一轮请输入 'next')${NC}"
                read -r response
                if [ "$response" = "next" ]; then
                    cycle_count=$((cycle_count + 1))
                    continue
                else
                    continue  # 重新进入GREEN阶段
                fi
            else
                cycle_count=$((cycle_count + 1))
                continue
            fi
        fi
        
        # REFACTOR 阶段: 重构优化
        echo -e "\n${BLUE}🔵 REFACTOR 阶段: 重构优化${NC}"
        echo "--------------------------------------------------"
        
        suggest_refactoring
        
        echo -e "${BLUE}💡 现在可以安全地重构代码...${NC}"
        if [ "$CONTINUOUS" = false ]; then
            echo -e "${BLUE}重构完成后按 Enter 验证测试仍然通过...${NC}"
            read -r
        else
            echo -e "${BLUE}自动等待 20 秒进行重构...${NC}"
            sleep 20
        fi
        
        # 验证重构后测试仍然通过
        if run_tests "REFACTOR"; then
            echo -e "${GREEN}🎉 REFACTOR 阶段成功！重构完成且测试通过${NC}"
        else
            echo -e "${RED}❌ 重构破坏了测试，请回滚重构${NC}"
            if [ "$CONTINUOUS" = false ]; then
                echo -e "${BLUE}回滚后按 Enter 继续...${NC}"
                read -r
            fi
        fi
        
        # 询问是否继续下一轮
        cycle_count=$((cycle_count + 1))
        
        if [ "$CONTINUOUS" = false ]; then
            echo -e "\n${PURPLE}🔄 是否开始下一轮 TDD 循环？(y/n)${NC}"
            read -r response
            if [ "$response" != "y" ] && [ "$response" != "Y" ]; then
                break
            fi
        else
            echo -e "\n${PURPLE}🔄 自动开始下一轮 TDD 循环...${NC}"
            sleep 5
        fi
        
        echo ""
    done
}

# 运行测试函数
run_tests() {
    local phase=$1
    echo -e "${BLUE}🧪 运行测试: $TEST_FILE${NC}"
    
    # 激活虚拟环境
    if [ -d "venv" ]; then
        source venv/bin/activate || echo "⚠️  无法激活虚拟环境"
    fi
    
    # 设置环境变量
    export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
    export TDD_PHASE="$phase"
    
    # 运行特定服务的测试
    if [ -n "$SERVICE" ]; then
        echo "  目标服务: $SERVICE"
        if [[ "$TEST_FILE" == *"individual_service"* ]]; then
            python3 -m pytest "$TEST_FILE::TestIndividualServiceStartup::test_${SERVICE//-/_}_starts_successfully" -v
        else
            python3 -m pytest "$TEST_FILE" -v -k "$SERVICE"
        fi
    else
        python3 -m pytest "$TEST_FILE" -v
    fi
    
    local test_result=$?
    
    # 记录测试结果
    echo "TDD Phase: $phase, Result: $test_result, Time: $(date)" >> "logs/tdd_cycles.log"
    
    return $test_result
}

# 修复建议函数
suggest_fixes() {
    echo -e "${YELLOW}💡 修复建议:${NC}"
    
    if [[ "$TEST_FILE" == *"environment"* ]]; then
        echo "  环境依赖问题修复:"
        echo "    1. 检查虚拟环境: python3 -m venv venv && source venv/bin/activate"
        echo "    2. 安装依赖: pip install -r requirements.txt"
        echo "    3. 设置权限: chmod +x start-*.sh"
        echo "    4. 创建目录: mkdir -p logs data temp"
        echo "    5. 运行自动修复: python3 tests/startup/test_environment_dependencies.py --fix"
        
    elif [[ "$TEST_FILE" == *"individual_service"* ]]; then
        echo "  服务启动问题修复:"
        echo "    1. 检查启动脚本内容和依赖"
        echo "    2. 验证服务代码语法: python3 -m py_compile services/*/main.py"
        echo "    3. 检查端口配置: cat config/services.yaml"
        echo "    4. 启动外部依赖: docker-compose up -d"
        echo "    5. 运行诊断: python3 tests/startup/test_individual_service_startup.py --diagnose"
        
    elif [[ "$TEST_FILE" == *"port"* ]]; then
        echo "  端口配置问题修复:"
        echo "    1. 检查端口冲突: netstat -tulpn | grep ':80[8-9][0-5]'"
        echo "    2. 修改配置文件: vi config/services.yaml"
        echo "    3. 终止占用进程: sudo lsof -ti:8080 | xargs kill -9"
        echo "    4. 验证端口可用: nc -z localhost 8080"
    fi
    
    echo ""
}

# 重构建议函数
suggest_refactoring() {
    echo -e "${BLUE}🔧 重构建议:${NC}"
    echo "  现在测试通过了，可以安全地进行以下重构:"
    echo "    1. 提取公共函数和常量"
    echo "    2. 改进变量和函数命名"
    echo "    3. 添加文档和注释"
    echo "    4. 优化错误处理"
    echo "    5. 提高代码可读性"
    echo "  ⚠️  每次重构后都要运行测试确保功能不变！"
    echo ""
}

# 检查前置条件
check_prerequisites() {
    echo -e "${BLUE}🔍 检查 TDD 前置条件...${NC}"
    
    # 检查测试文件是否存在
    if [ ! -f "$TEST_FILE" ]; then
        echo -e "${RED}❌ 测试文件不存在: $TEST_FILE${NC}"
        exit 1
    fi
    
    # 检查 pytest 是否安装
    if ! command -v python3 >/dev/null 2>&1; then
        echo -e "${RED}❌ Python3 未安装${NC}"
        exit 1
    fi
    
    # 创建日志目录
    mkdir -p logs
    
    echo -e "${GREEN}✅ 前置条件检查通过${NC}"
    echo ""
}

# 显示使用帮助
show_help() {
    echo "MarketPrism TDD 循环执行器"
    echo ""
    echo "用法:"
    echo "  $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --phase <阶段>      指定TDD阶段 (env|service|config)"
    echo "  --service <服务>    指定目标服务"
    echo "  --test-file <文件>  指定测试文件"
    echo "  --continuous        连续模式，不等待用户输入"
    echo ""
    echo "示例:"
    echo "  $0 --phase env                    # 环境依赖TDD"
    echo "  $0 --phase service --service api-gateway  # 特定服务TDD"
    echo "  $0 --continuous                   # 连续模式TDD"
    echo ""
}

# 主执行逻辑
main() {
    if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
        show_help
        exit 0
    fi
    
    check_prerequisites
    
    echo -e "${GREEN}🚀 开始 TDD 红-绿-重构 循环${NC}"
    echo ""
    
    run_tdd_cycle
    
    echo ""
    echo "=================================================="
    echo -e "${PURPLE}🎉 TDD 循环完成！${NC}"
    echo -e "${GREEN}💫 记住 TDD 的核心价值：${NC}"
    echo -e "${GREEN}   📝 测试先行 - 明确问题和期望${NC}"
    echo -e "${GREEN}   🎯 最小修复 - 只做必要的更改${NC}"
    echo -e "${GREEN}   🔧 安全重构 - 在测试保护下改进代码${NC}"
    echo "=================================================="
}

# 执行主函数
main "$@"