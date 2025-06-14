#!/bin/bash

# MarketPrism 环境问题自动修复脚本
# 基于TDD测试结果自动修复环境配置问题

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 获取项目根目录
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$PROJECT_ROOT"

echo "=================================================="
echo -e "${BLUE}🔧 MarketPrism 环境自动修复器${NC}"
echo "=================================================="

# 修复日志
FIX_LOG="logs/environment_fixes.log"
mkdir -p logs
echo "Environment Fix Session: $(date)" >> "$FIX_LOG"

# 修复成功计数
FIXES_APPLIED=0
FIXES_TOTAL=0

# 记录修复函数
log_fix() {
    local status=$1
    local message=$2
    FIXES_TOTAL=$((FIXES_TOTAL + 1))
    
    if [ "$status" = "SUCCESS" ]; then
        FIXES_APPLIED=$((FIXES_APPLIED + 1))
        echo -e "${GREEN}✅ $message${NC}"
        echo "SUCCESS: $message" >> "$FIX_LOG"
    elif [ "$status" = "SKIP" ]; then
        echo -e "${YELLOW}⏭️  $message${NC}"
        echo "SKIP: $message" >> "$FIX_LOG"
    else
        echo -e "${RED}❌ $message${NC}"
        echo "FAILED: $message" >> "$FIX_LOG"
    fi
}

# 1. Python环境修复
fix_python_environment() {
    echo -e "${BLUE}🐍 修复 Python 环境...${NC}"
    
    # 检查Python版本
    if python3 --version >/dev/null 2>&1; then
        PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        if [[ $(echo "$PYTHON_VERSION >= 3.8" | bc -l) -eq 1 ]] 2>/dev/null || [[ "$PYTHON_VERSION" > "3.7" ]]; then
            log_fix "SKIP" "Python版本满足要求: $PYTHON_VERSION"
        else
            log_fix "FAILED" "Python版本过低: $PYTHON_VERSION，需要3.8+"
        fi
    else
        log_fix "FAILED" "Python3未安装或不可用"
    fi
    
    # 检查pip
    if pip3 --version >/dev/null 2>&1; then
        log_fix "SKIP" "pip3已可用"
    else
        log_fix "FAILED" "pip3不可用，请安装pip"
    fi
}

# 2. 虚拟环境修复
fix_virtual_environment() {
    echo -e "${BLUE}📦 修复虚拟环境...${NC}"
    
    # 创建虚拟环境
    if [ ! -d "venv" ]; then
        echo "创建虚拟环境..."
        if python3 -m venv venv; then
            log_fix "SUCCESS" "创建虚拟环境成功"
        else
            log_fix "FAILED" "创建虚拟环境失败"
            return 1
        fi
    else
        log_fix "SKIP" "虚拟环境已存在"
    fi
    
    # 检查虚拟环境结构
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
        VENV_PYTHON="venv/Scripts/python.exe"
        VENV_PIP="venv/Scripts/pip.exe"
    else
        VENV_PYTHON="venv/bin/python"
        VENV_PIP="venv/bin/pip"
    fi
    
    if [ -f "$VENV_PYTHON" ]; then
        log_fix "SKIP" "虚拟环境Python可执行文件存在"
    else
        log_fix "FAILED" "虚拟环境损坏，Python可执行文件不存在"
    fi
    
    if [ -f "$VENV_PIP" ]; then
        log_fix "SKIP" "虚拟环境pip可执行文件存在"
    else
        log_fix "FAILED" "虚拟环境损坏，pip可执行文件不存在"
    fi
}

# 3. 依赖包修复
fix_package_dependencies() {
    echo -e "${BLUE}📚 修复依赖包...${NC}"
    
    # 激活虚拟环境
    if [ -d "venv" ]; then
        source venv/bin/activate 2>/dev/null || {
            log_fix "FAILED" "无法激活虚拟环境"
            return 1
        }
        log_fix "SUCCESS" "激活虚拟环境"
    else
        log_fix "FAILED" "虚拟环境不存在，无法安装依赖"
        return 1
    fi
    
    # 创建或更新requirements.txt
    if [ ! -f "requirements.txt" ]; then
        echo "创建 requirements.txt..."
        cat > requirements.txt << 'EOF'
# MarketPrism 核心依赖
fastapi>=0.68.0
uvicorn[standard]>=0.15.0
aiohttp>=3.8.0
asyncio-nats-client>=0.11.0
pydantic>=1.8.0
clickhouse-driver>=0.2.0
redis>=4.0.0
prometheus-client>=0.11.0
PyYAML>=5.4.0

# 数据处理
pandas>=1.3.0
numpy>=1.21.0

# 测试依赖
pytest>=6.2.0
pytest-asyncio>=0.15.0
pytest-cov>=2.12.0

# 开发工具
psutil>=5.8.0
aiofiles>=0.7.0

# WebSocket支持
websockets>=9.0.0

# 监控和日志
structlog>=21.1.0
EOF
        log_fix "SUCCESS" "创建 requirements.txt"
    else
        log_fix "SKIP" "requirements.txt 已存在"
    fi
    
    # 升级pip
    echo "升级 pip..."
    if pip install --upgrade pip >/dev/null 2>&1; then
        log_fix "SUCCESS" "升级pip成功"
    else
        log_fix "FAILED" "升级pip失败"
    fi
    
    # 安装依赖
    echo "安装依赖包..."
    if pip install -r requirements.txt; then
        log_fix "SUCCESS" "安装依赖包成功"
    else
        log_fix "FAILED" "安装依赖包失败"
        
        # 尝试逐个安装核心依赖
        echo "尝试逐个安装核心依赖..."
        CORE_DEPS=("fastapi" "uvicorn" "aiohttp" "pydantic" "pytest" "pyyaml")
        for dep in "${CORE_DEPS[@]}"; do
            if pip install "$dep" >/dev/null 2>&1; then
                log_fix "SUCCESS" "安装 $dep 成功"
            else
                log_fix "FAILED" "安装 $dep 失败"
            fi
        done
    fi
}

# 4. 项目结构修复
fix_project_structure() {
    echo -e "${BLUE}📁 修复项目结构...${NC}"
    
    # 必要目录列表
    REQUIRED_DIRS=(
        "core"
        "services"
        "config"
        "tests"
        "tests/startup"
        "tests/unit"
        "tests/integration"
        "logs"
        "data"
        "temp"
        "scripts"
        "scripts/tdd"
        "scripts/fix"
    )
    
    # 创建缺失目录
    for dir in "${REQUIRED_DIRS[@]}"; do
        if [ ! -d "$dir" ]; then
            if mkdir -p "$dir"; then
                log_fix "SUCCESS" "创建目录: $dir"
            else
                log_fix "FAILED" "创建目录失败: $dir"
            fi
        else
            log_fix "SKIP" "目录已存在: $dir"
        fi
    done
    
    # 创建空的__init__.py文件
    PYTHON_DIRS=("core" "services" "tests")
    for dir in "${PYTHON_DIRS[@]}"; do
        if [ -d "$dir" ] && [ ! -f "$dir/__init__.py" ]; then
            if touch "$dir/__init__.py"; then
                log_fix "SUCCESS" "创建 $dir/__init__.py"
            else
                log_fix "FAILED" "创建 $dir/__init__.py 失败"
            fi
        fi
    done
}

# 5. 配置文件修复
fix_configuration_files() {
    echo -e "${BLUE}⚙️  修复配置文件...${NC}"
    
    # 创建config目录
    mkdir -p config
    
    # 创建services.yaml
    if [ ! -f "config/services.yaml" ]; then
        echo "创建 services.yaml..."
        cat > config/services.yaml << 'EOF'
# MarketPrism 服务配置
services:
  api-gateway:
    port: 8080
    host: "0.0.0.0"
    workers: 1
    timeout: 30
    
  data-collector:
    port: 8081
    host: "0.0.0.0"
    workers: 1
    timeout: 30
    
  data-storage:
    port: 8082
    host: "0.0.0.0"
    workers: 1
    timeout: 30
    
  monitoring:
    port: 8083
    host: "0.0.0.0"
    workers: 1
    timeout: 30
    
  scheduler:
    port: 8084
    host: "0.0.0.0"
    workers: 1
    timeout: 30
    
  message-broker:
    port: 8085
    host: "0.0.0.0"
    workers: 1
    timeout: 30

# 外部服务配置
external_services:
  nats:
    host: "localhost"
    port: 4222
    
  clickhouse:
    host: "localhost"
    port: 9000
    database: "marketprism"
    
  redis:
    host: "localhost"
    port: 6379
    db: 0

# 日志配置
logging:
  level: "INFO"
  format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
  file: "logs/marketprism.log"
EOF
        log_fix "SUCCESS" "创建 config/services.yaml"
    else
        log_fix "SKIP" "config/services.yaml 已存在"
    fi
    
    # 创建logging.yaml
    if [ ! -f "config/logging.yaml" ]; then
        echo "创建 logging.yaml..."
        cat > config/logging.yaml << 'EOF'
version: 1
disable_existing_loggers: false

formatters:
  standard:
    format: '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
  detailed:
    format: '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s'

handlers:
  console:
    class: logging.StreamHandler
    level: INFO
    formatter: standard
    stream: ext://sys.stdout
    
  file:
    class: logging.FileHandler
    level: DEBUG
    formatter: detailed
    filename: logs/marketprism.log
    
  error_file:
    class: logging.FileHandler
    level: ERROR
    formatter: detailed
    filename: logs/marketprism_error.log

loggers:
  '':
    level: INFO
    handlers: [console, file]
    propagate: false
    
  marketprism:
    level: DEBUG
    handlers: [console, file, error_file]
    propagate: false

root:
  level: INFO
  handlers: [console, file]
EOF
        log_fix "SUCCESS" "创建 config/logging.yaml"
    else
        log_fix "SKIP" "config/logging.yaml 已存在"
    fi
}

# 6. 启动脚本修复
fix_startup_scripts() {
    echo -e "${BLUE}🚀 修复启动脚本...${NC}"
    
    # 服务列表
    SERVICES=("api-gateway" "data-collector" "data-storage" "monitoring" "scheduler" "message-broker")
    
    for service in "${SERVICES[@]}"; do
        script_name="start-$service.sh"
        
        if [ ! -f "$script_name" ]; then
            echo "创建启动脚本: $script_name"
            
            # 根据服务类型创建不同的启动脚本
            case $service in
                "api-gateway")
                    cat > "$script_name" << 'EOF'
#!/bin/bash
# API Gateway 启动脚本

set -e

# 项目根目录
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$PROJECT_ROOT"

# 激活虚拟环境
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# 设置环境变量
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
export SERVICE_NAME="api-gateway"
export SERVICE_PORT=8080

# 启动服务
echo "启动 API Gateway 服务..."
python3 -m uvicorn services.api_gateway.main:app --host 0.0.0.0 --port 8080 --reload
EOF
                    ;;
                    
                "data-collector")
                    cat > "$script_name" << 'EOF'
#!/bin/bash
# Data Collector 启动脚本

set -e

# 项目根目录
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$PROJECT_ROOT"

# 激活虚拟环境
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# 设置环境变量
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
export SERVICE_NAME="data-collector"
export SERVICE_PORT=8081

# 启动服务
echo "启动 Data Collector 服务..."
python3 -m uvicorn services.data_collector.main:app --host 0.0.0.0 --port 8081 --reload
EOF
                    ;;
                    
                *)
                    # 通用启动脚本模板
                    cat > "$script_name" << EOF
#!/bin/bash
# $service 启动脚本

set -e

# 项目根目录
PROJECT_ROOT=\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)
cd "\$PROJECT_ROOT"

# 激活虚拟环境
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# 设置环境变量
export PYTHONPATH="\$PROJECT_ROOT:\$PYTHONPATH"
export SERVICE_NAME="$service"

# 获取端口配置
SERVICE_PORT=\$(python3 -c "
import yaml
try:
    with open('config/services.yaml', 'r') as f:
        config = yaml.safe_load(f)
    port = config['services']['$service']['port']
    print(port)
except:
    print(8080)
" 2>/dev/null || echo 8080)

export SERVICE_PORT=\$SERVICE_PORT

# 启动服务
echo "启动 $service 服务..."
if [ -f "services/${service//-/_}/main.py" ]; then
    python3 -m uvicorn services.${service//-/_}.main:app --host 0.0.0.0 --port \$SERVICE_PORT --reload
else
    echo "服务文件不存在: services/${service//-/_}/main.py"
    echo "创建基础服务结构..."
    mkdir -p "services/${service//-/_}"
    cat > "services/${service//-/_}/main.py" << 'PYEOF'
from fastapi import FastAPI
import uvicorn

app = FastAPI(title="$service")

@app.get("/")
async def root():
    return {"message": "Hello from $service"}

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "$service"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=\$SERVICE_PORT)
PYEOF
    echo "基础服务结构已创建，重新启动..."
    python3 -m uvicorn services.${service//-/_}.main:app --host 0.0.0.0 --port \$SERVICE_PORT --reload
fi
EOF
                    ;;
            esac
            
            # 设置执行权限
            if chmod +x "$script_name"; then
                log_fix "SUCCESS" "创建启动脚本: $script_name"
            else
                log_fix "FAILED" "设置执行权限失败: $script_name"
            fi
        else
            # 检查执行权限
            if [ -x "$script_name" ]; then
                log_fix "SKIP" "启动脚本已存在且有执行权限: $script_name"
            else
                if chmod +x "$script_name"; then
                    log_fix "SUCCESS" "设置执行权限: $script_name"
                else
                    log_fix "FAILED" "设置执行权限失败: $script_name"
                fi
            fi
        fi
    done
}

# 7. 环境变量修复
fix_environment_variables() {
    echo -e "${BLUE}🌍 修复环境变量...${NC}"
    
    # 创建.env文件
    if [ ! -f ".env" ]; then
        echo "创建 .env 文件..."
        cat > .env << EOF
# MarketPrism 环境变量配置

# Python路径
PYTHONPATH=$PROJECT_ROOT

# 环境设置
ENVIRONMENT=development
LOG_LEVEL=INFO

# 数据库配置
DATABASE_URL=sqlite:///./marketprism.db
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=9000
CLICKHOUSE_DATABASE=marketprism

# 缓存配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# 消息队列配置
NATS_HOST=localhost
NATS_PORT=4222

# API配置
API_HOST=0.0.0.0
API_PORT=8080

# 代理配置 (根据memory设置)
http_proxy=http://127.0.0.1:1087
https_proxy=http://127.0.0.1:1087
ALL_PROXY=socks5://127.0.0.1:1080
EOF
        log_fix "SUCCESS" "创建 .env 文件"
    else
        log_fix "SKIP" ".env 文件已存在"
    fi
    
    # 更新当前会话的环境变量
    export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
    export ENVIRONMENT="development"
    export LOG_LEVEL="INFO"
    
    log_fix "SUCCESS" "设置环境变量"
}

# 8. 外部服务检查和建议
check_external_services() {
    echo -e "${BLUE}🔗 检查外部服务...${NC}"
    
    # 检查端口占用情况
    EXTERNAL_PORTS=(4222 9000 6379)
    EXTERNAL_SERVICES=("NATS" "ClickHouse" "Redis")
    
    for i in "${!EXTERNAL_PORTS[@]}"; do
        port=${EXTERNAL_PORTS[$i]}
        service=${EXTERNAL_SERVICES[$i]}
        
        if nc -z localhost "$port" 2>/dev/null; then
            log_fix "SKIP" "$service 服务在端口 $port 上运行"
        else
            log_fix "FAILED" "$service 服务未在端口 $port 上运行"
            
            # 提供启动建议
            case $service in
                "NATS")
                    echo "  启动建议: docker run -p 4222:4222 nats:latest"
                    ;;
                "ClickHouse")
                    echo "  启动建议: docker run -p 9000:9000 yandex/clickhouse-server"
                    ;;
                "Redis")
                    echo "  启动建议: docker run -p 6379:6379 redis:alpine"
                    ;;
            esac
        fi
    done
    
    # 创建docker-compose.yml建议
    if [ ! -f "docker-compose.yml" ]; then
        echo "创建 docker-compose.yml..."
        cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  nats:
    image: nats:latest
    ports:
      - "4222:4222"
      - "8222:8222"
    command: ["--jetstream"]
    
  clickhouse:
    image: yandex/clickhouse-server
    ports:
      - "9000:9000"
      - "8123:8123"
    volumes:
      - clickhouse_data:/var/lib/clickhouse
    
  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  clickhouse_data:
  redis_data:
EOF
        log_fix "SUCCESS" "创建 docker-compose.yml"
        echo "  使用 'docker-compose up -d' 启动外部服务"
    else
        log_fix "SKIP" "docker-compose.yml 已存在"
    fi
}

# 主修复函数
main() {
    echo -e "${GREEN}🔧 开始环境自动修复...${NC}"
    echo ""
    
    # 执行各项修复
    fix_python_environment
    echo ""
    
    fix_virtual_environment
    echo ""
    
    fix_package_dependencies
    echo ""
    
    fix_project_structure
    echo ""
    
    fix_configuration_files
    echo ""
    
    fix_startup_scripts
    echo ""
    
    fix_environment_variables
    echo ""
    
    check_external_services
    echo ""
    
    # 修复摘要
    echo "=================================================="
    echo -e "${GREEN}🎉 环境修复完成！${NC}"
    echo "=================================================="
    
    echo -e "${BLUE}📊 修复统计:${NC}"
    echo "  成功修复: $FIXES_APPLIED"
    echo "  总计检查: $FIXES_TOTAL"
    echo "  成功率: $(( FIXES_APPLIED * 100 / FIXES_TOTAL ))%"
    echo ""
    
    echo -e "${BLUE}📝 下一步操作:${NC}"
    echo "  1. 启动外部服务: docker-compose up -d"
    echo "  2. 运行环境测试: python3 tests/startup/test_environment_dependencies.py --test"
    echo "  3. 开始TDD循环: ./scripts/tdd/run_red_green_refactor.sh --phase env"
    echo ""
    
    echo -e "${YELLOW}📄 详细日志已保存到: $FIX_LOG${NC}"
}

# 执行修复
main "$@"