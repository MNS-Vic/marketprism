#!/bin/bash

# MarketPrism 快速健康检查脚本
# 用于日常快速检测项目状态

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

echo -e "${PURPLE}🩺 MarketPrism 快速健康检查${NC}"
echo "========================================"

# 检查项目基本结构
echo -e "${BLUE}📂 检查项目结构...${NC}"
required_dirs=("core" "services" "config" "tests")
structure_ok=true

for dir in "${required_dirs[@]}"; do
    if [ -d "$dir" ]; then
        echo -e "${GREEN}  ✅ $dir/ 存在${NC}"
    else
        echo -e "${RED}  ❌ $dir/ 缺失${NC}"
        structure_ok=false
    fi
done

# 检查启动脚本
echo -e "\n${BLUE}🚀 检查启动脚本...${NC}"
startup_scripts=("start-api-gateway.sh" "start-data-collector.sh" "start-data-storage.sh" 
                "start-monitoring.sh" "start-scheduler.sh" "start-message-broker.sh")
scripts_ok=true

for script in "${startup_scripts[@]}"; do
    if [ -f "$script" ]; then
        echo -e "${GREEN}  ✅ $script 存在${NC}"
    else
        echo -e "${RED}  ❌ $script 缺失${NC}"
        scripts_ok=false
    fi
done

# 检查Python环境
echo -e "\n${BLUE}🐍 检查Python环境...${NC}"
python_ok=true

if command -v python3 >/dev/null 2>&1; then
    python_version=$(python3 --version)
    echo -e "${GREEN}  ✅ Python: $python_version${NC}"
else
    echo -e "${RED}  ❌ Python3 未安装${NC}"
    python_ok=false
fi

# 检查虚拟环境
if [ -d "venv" ]; then
    echo -e "${GREEN}  ✅ 虚拟环境存在${NC}"
else
    echo -e "${YELLOW}  ⚠️  虚拟环境不存在，建议创建${NC}"
fi

# 检查关键依赖文件
echo -e "\n${BLUE}📦 检查依赖文件...${NC}"
deps_ok=true

if [ -f "requirements.txt" ]; then
    req_count=$(cat requirements.txt | grep -v '^#' | grep -v '^$' | wc -l)
    echo -e "${GREEN}  ✅ requirements.txt ($req_count 个依赖)${NC}"
else
    echo -e "${RED}  ❌ requirements.txt 缺失${NC}"
    deps_ok=false
fi

# 检查配置文件
echo -e "\n${BLUE}⚙️  检查配置文件...${NC}"
config_ok=true

config_files=("config/services.yaml" "config/database.yaml" "config/logging.yaml")
for config in "${config_files[@]}"; do
    if [ -f "$config" ]; then
        echo -e "${GREEN}  ✅ $config 存在${NC}"
    else
        echo -e "${YELLOW}  ⚠️  $config 缺失${NC}"
    fi
done

# 检查端口占用
echo -e "\n${BLUE}🔌 检查端口状态...${NC}"
ports=(8080 8081 8082 8083 8084 8085)
occupied_ports=0

for port in "${ports[@]}"; do
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${YELLOW}  ⚠️  端口 $port 被占用${NC}"
        occupied_ports=$((occupied_ports + 1))
    else
        echo -e "${GREEN}  ✅ 端口 $port 可用${NC}"
    fi
done

# 检查日志目录
echo -e "\n${BLUE}📝 检查日志状态...${NC}"
if [ -d "logs" ]; then
    log_count=$(find logs -name "*.log" 2>/dev/null | wc -l || echo 0)
    log_size=$(du -sh logs 2>/dev/null | cut -f1 || echo "0B")
    echo -e "${GREEN}  ✅ 日志目录存在 ($log_count 个文件, $log_size)${NC}"
    
    if [ $log_count -gt 50 ]; then
        echo -e "${YELLOW}    ⚠️  日志文件过多，建议清理${NC}"
    fi
else
    echo -e "${YELLOW}  ⚠️  logs/ 目录不存在${NC}"
fi

# 检查测试文件
echo -e "\n${BLUE}🧪 检查测试结构...${NC}"
test_dirs=("tests/unit" "tests/integration" "tests/startup")
tests_ok=true

for test_dir in "${test_dirs[@]}"; do
    if [ -d "$test_dir" ]; then
        test_count=$(find "$test_dir" -name "test_*.py" 2>/dev/null | wc -l || echo 0)
        echo -e "${GREEN}  ✅ $test_dir ($test_count 个测试)${NC}"
    else
        echo -e "${YELLOW}  ⚠️  $test_dir 不存在${NC}"
    fi
done

# 快速语法检查
echo -e "\n${BLUE}🔍 快速语法检查...${NC}"
syntax_errors=0

# 检查主要Python文件
main_files=("core/config/manager.py" "services/api_gateway/main.py")
for file in "${main_files[@]}"; do
    if [ -f "$file" ]; then
        if python3 -m py_compile "$file" 2>/dev/null; then
            echo -e "${GREEN}  ✅ $file 语法正确${NC}"
        else
            echo -e "${RED}  ❌ $file 语法错误${NC}"
            syntax_errors=$((syntax_errors + 1))
        fi
    fi
done

# 生成总结
echo ""
echo "========================================"
echo -e "${PURPLE}📊 健康检查总结${NC}"
echo "========================================"

total_score=0
max_score=100

# 评分
if $structure_ok; then total_score=$((total_score + 20)); fi
if $scripts_ok; then total_score=$((total_score + 20)); fi
if $python_ok; then total_score=$((total_score + 15)); fi
if $deps_ok; then total_score=$((total_score + 10)); fi
if $config_ok; then total_score=$((total_score + 10)); fi
if [ $occupied_ports -eq 0 ]; then total_score=$((total_score + 10)); fi
if [ $syntax_errors -eq 0 ]; then total_score=$((total_score + 15)); fi

echo "项目结构: $(if $structure_ok; then echo "✅ 完整"; else echo "❌ 缺失"; fi)"
echo "启动脚本: $(if $scripts_ok; then echo "✅ 完整"; else echo "❌ 缺失"; fi)"
echo "Python环境: $(if $python_ok; then echo "✅ 正常"; else echo "❌ 异常"; fi)"
echo "依赖配置: $(if $deps_ok; then echo "✅ 正常"; else echo "❌ 异常"; fi)"
echo "端口状态: $(if [ $occupied_ports -eq 0 ]; then echo "✅ 全部可用"; else echo "⚠️ $occupied_ports 个被占用"; fi)"
echo "语法检查: $(if [ $syntax_errors -eq 0 ]; then echo "✅ 无错误"; else echo "❌ $syntax_errors 个错误"; fi)"

echo ""
echo -e "${PURPLE}🏆 健康评分: $total_score/$max_score${NC}"

if [ $total_score -ge 80 ]; then
    echo -e "${GREEN}🎉 项目状态优秀！${NC}"
    exit_code=0
elif [ $total_score -ge 60 ]; then
    echo -e "${YELLOW}⚠️  项目状态良好，有改进空间${NC}"
    exit_code=0
else
    echo -e "${RED}❌ 项目状态需要改进${NC}"
    exit_code=1
fi

# 快速修复建议
if [ $total_score -lt 80 ]; then
    echo ""
    echo -e "${BLUE}💡 快速修复建议:${NC}"
    
    if ! $structure_ok; then
        echo "  • 创建缺失的目录结构"
    fi
    
    if ! $scripts_ok; then
        echo "  • 生成缺失的启动脚本"
    fi
    
    if ! $python_ok; then
        echo "  • 安装Python 3.8+"
    fi
    
    if ! $deps_ok; then
        echo "  • 运行: pip install -r requirements.txt"
    fi
    
    if [ $occupied_ports -gt 0 ]; then
        echo "  • 停止占用端口的进程"
    fi
    
    if [ $syntax_errors -gt 0 ]; then
        echo "  • 修复Python语法错误"
    fi
fi

echo "========================================"

exit $exit_code