#!/bin/bash
# 本地构建脚本 - 绕过网络问题
# 使用方法: ./scripts/local_build.sh [service]
# 例如: ./scripts/local_build.sh go-collector 或 ./scripts/local_build.sh data-normalizer

set -e

# 设置Go环境变量
export GOPROXY=direct
export GOSUMDB=off
export GO111MODULE=on

# 当前目录
PROJECT_ROOT=$(pwd)
echo "项目根目录: $PROJECT_ROOT"

# 服务名称
SERVICE=$1
if [ -z "$SERVICE" ]; then
    echo "错误: 请指定要构建的服务名称"
    echo "用法: $0 [service]"
    echo "可用的服务: go-collector, data-normalizer"
    exit 1
fi

# 检查服务目录是否存在
SERVICE_DIR="$PROJECT_ROOT/services/$SERVICE"
if [ ! -d "$SERVICE_DIR" ]; then
    echo "错误: 服务目录 '$SERVICE_DIR' 不存在"
    exit 1
fi

echo "====== 构建服务: $SERVICE ======"
cd "$SERVICE_DIR"

# 检查和创建vendor目录
echo "正在准备本地依赖..."
if [ ! -d "vendor" ]; then
    echo "未找到vendor目录，尝试创建..."
    
    # 修复go.mod文件，处理内部依赖路径
    echo "更新go.mod文件..."
    
    # 备份原始go.mod
    cp go.mod go.mod.backup
    
    # 修复go.mod，添加正确的replace指令
    if grep -q "github.com/marketprism/services" go.mod; then
        echo "发现需要修复的依赖路径..."
        
        # 获取模块名
        MODULE_NAME=$(head -1 go.mod | awk '{print $2}')
        echo "模块名: $MODULE_NAME"
        
        # 确保有replace指令
        if ! grep -q "replace $MODULE_NAME" go.mod; then
            echo "添加本地replace指令..."
            echo "" >> go.mod
            echo "// 本地路径替换" >> go.mod
            echo "replace $MODULE_NAME => ./" >> go.mod
        fi
        
        # 替换所有github.com/marketprism/services/go-collector的import为本地模块名
        find . -name "*.go" -type f -exec sed -i.bak "s|github\.com/marketprism/services/go-collector|$MODULE_NAME|g" {} \;
        
        # 清理备份文件
        find . -name "*.go.bak" -delete
        
        echo "✅ 已修复import路径"
    fi
fi

# 创建虚拟配置文件
if [ ! -f "config/config.yaml" ]; then
    mkdir -p config
    echo "创建临时配置文件..."
    cat > config/config.yaml << EOF
# 临时配置文件
app_name: "${SERVICE}"
log_level: "info"
EOF
fi

# 清理模块缓存
echo "清理Go模块缓存..."
go clean -modcache || true

# 下载依赖（忽略校验）
echo "下载Go依赖..."
go mod download || echo "部分依赖下载失败，继续尝试构建..."

# 整理依赖
echo "整理Go依赖..."
go mod tidy || echo "依赖整理失败，继续尝试构建..."

# 本地构建(跳过测试)
echo "正在编译 $SERVICE..."

# 创建bin目录
mkdir -p bin

case "$SERVICE" in
    "go-collector")
        if [ -f "cmd/collector/main.go" ]; then
            go build -mod=mod -o bin/collector ./cmd/collector
            echo "✅ 构建完成: $(pwd)/bin/collector"
        elif [ -f "main.go" ]; then
            go build -mod=mod -o bin/collector .
            echo "✅ 构建完成: $(pwd)/bin/collector"
        elif [ -f "collector_integrated.go" ]; then
            go build -mod=mod -o bin/collector ./collector_integrated.go
            echo "✅ 构建完成: $(pwd)/bin/collector"
        else
            echo "❌ 未找到go-collector的main文件"
            exit 1
        fi
        ;;
    "data-normalizer")
        if [ -f "cmd/normalizer/main.go" ]; then
            go build -mod=mod -o bin/normalizer ./cmd/normalizer
            echo "✅ 构建完成: $(pwd)/bin/normalizer"
        elif [ -f "main.go" ]; then
            go build -mod=mod -o bin/normalizer .
            echo "✅ 构建完成: $(pwd)/bin/normalizer"
        else
            echo "❌ 未找到data-normalizer的main文件"
            exit 1
        fi
        ;;
    *)
        echo "未知服务: $SERVICE"
        echo "尝试通用构建..."
        if [ -f "main.go" ]; then
            go build -mod=mod -o bin/$SERVICE .
            echo "✅ 构建完成: $(pwd)/bin/$SERVICE"
        else
            echo "❌ 未找到main.go文件"
            exit 1
        fi
        ;;
esac

# 验证构建结果
if [ -f "bin/$(basename $SERVICE)" ] || [ -f "bin/collector" ] || [ -f "bin/normalizer" ]; then
    echo ""
    echo "📊 构建信息:"
    ls -la bin/
    echo ""
    echo "🎉 $SERVICE 构建成功！"
else
    echo "❌ 构建失败，未找到可执行文件"
    exit 1
fi

echo "====== $SERVICE 构建完成 ======"
