#!/bin/bash
# 彻底修复虚假GitHub导入路径脚本 v2
# 这个版本会修复所有层级的虚假GitHub路径

set -e

echo "🔧 开始彻底修复所有虚假GitHub导入路径..."

# 当前目录
PROJECT_ROOT=$(pwd)
echo "项目根目录: $PROJECT_ROOT"

# 函数：修复单个Go文件中的导入路径
fix_imports_in_go_file() {
    local file="$1"
    echo "  修复文件: $file"
    
    # 备份原文件（如果还没有备份）
    if [ ! -f "$file.backup2" ]; then
        cp "$file" "$file.backup2"
    fi
    
    # 在go-collector服务内，修复所有github.com/marketprism/go-collector路径
    if [[ "$file" == *"services/go-collector"* ]]; then
        # 修复所有go-collector内部引用
        sed -i.tmp 's|"github\.com/marketprism/go-collector/internal/\([^"]*\)"|"./internal/\1"|g' "$file"
        sed -i.tmp 's|github\.com/marketprism/go-collector/internal/\([^"]*\)|./internal/\1|g' "$file"
    fi
    
    # 在data-normalizer服务内，修复所有github.com/marketprism/data-normalizer路径
    if [[ "$file" == *"services/data_normalizer"* ]]; then
        # 修复所有data-normalizer内部引用
        sed -i.tmp 's|"github\.com/marketprism/data-normalizer/internal/\([^"]*\)"|"./internal/\1"|g' "$file"
        sed -i.tmp 's|github\.com/marketprism/data-normalizer/internal/\([^"]*\)|./internal/\1|g' "$file"
    fi
    
    # 修复跨服务的虚假路径
    sed -i.tmp 's|"github\.com/marketprism/services/go-collector/internal/\([^"]*\)"|"./internal/\1"|g' "$file"
    sed -i.tmp 's|"github\.com/marketprism/services/data-normalizer/internal/\([^"]*\)"|"./internal/\1"|g' "$file"
    
    # 清理临时文件
    rm -f "$file.tmp"
}

# 函数：创建正确的go.mod文件
create_correct_go_mod() {
    local service_dir="$1"
    local module_name="$2"
    local go_mod_file="$service_dir/go.mod"
    
    echo "  重新创建go.mod: $go_mod_file"
    
    # 备份原文件
    if [ -f "$go_mod_file" ] && [ ! -f "$go_mod_file.backup2" ]; then
        cp "$go_mod_file" "$go_mod_file.backup2"
    fi
    
    # 获取外部依赖
    local external_deps=""
    if [ -f "$go_mod_file.backup2" ]; then
        external_deps=$(grep -E '^[[:space:]]*github\.com|^[[:space:]]*go\.|^[[:space:]]*golang\.org|^[[:space:]]*gopkg\.in' "$go_mod_file.backup2" | grep -v "github.com/marketprism" || true)
    fi
    
    # 创建新的go.mod
    cat > "$go_mod_file" << EOF
module $module_name

go 1.21

// 本地路径替换 - 防止网络依赖
replace $module_name => ./

require (
    github.com/gorilla/websocket v1.5.0
    github.com/joho/godotenv v1.5.1
    github.com/nats-io/nats.go v1.42.0
    github.com/prometheus/client_golang v1.15.0
    github.com/robfig/cron/v3 v3.0.1
    github.com/spf13/viper v1.16.0
    go.uber.org/zap v1.25.0
    gopkg.in/yaml.v2 v2.4.0
)
EOF
}

# 修复go-collector服务
echo "🔧 修复 go-collector 服务..."
cd "$PROJECT_ROOT/services/go-collector"

# 创建正确的go.mod
create_correct_go_mod "." "github.com/marketprism/go-collector"

# 修复所有Go文件中的导入
find . -name "*.go" -type f | while read -r go_file; do
    fix_imports_in_go_file "$PWD/$go_file"
done

# 修复data-normalizer服务
echo "🔧 修复 data-normalizer 服务..."
cd "$PROJECT_ROOT/services/data_normalizer"

# 创建正确的go.mod
create_correct_go_mod "." "github.com/marketprism/data-normalizer"

# 修复所有Go文件中的导入
find . -name "*.go" -type f | while read -r go_file; do
    fix_imports_in_go_file "$PWD/$go_file"
done

echo "✅ 虚假GitHub导入路径彻底修复完成！"
echo ""
echo "📋 修复总结："
echo "  - 修复了所有层级的github.com/marketprism/*路径"
echo "  - 转换为正确的相对路径导入"
echo "  - 重新创建了干净的go.mod配置"
echo "  - 备份文件保存为 *.backup2"
echo ""
echo "🧪 验证修复结果："
echo "  grep -r 'github.com/marketprism/go-collector/internal' services/go-collector/ --include='*.go'"
echo "  grep -r 'github.com/marketprism/data-normalizer/internal' services/data_normalizer/ --include='*.go'"
echo ""
echo "🧪 测试构建："
echo "  ./scripts/local_build.sh go-collector"
echo "  ./scripts/local_build.sh data-normalizer" 