#!/bin/bash
# 修复虚假GitHub导入路径脚本
# 这些路径会导致Go尝试从网络下载本地代码，违背本地构建策略

set -e

echo "🔧 开始修复虚假GitHub导入路径..."

# 当前目录
PROJECT_ROOT=$(pwd)
echo "项目根目录: $PROJECT_ROOT"

# 定义需要修复的虚假路径映射
declare -A PATH_MAPPINGS=(
    # go-collector服务的路径修复
    ["github.com/marketprism/go-collector/internal"]="./internal"
    ["github.com/marketprism/services/go-collector/internal"]="./internal"
    
    # data-normalizer服务的路径修复
    ["github.com/marketprism/data-normalizer/internal"]="./internal"
    
    # 跨服务引用修复（相对路径）
    ["github.com/marketprism/services/go-collector"]="../go-collector"
    ["github.com/marketprism/services/data-normalizer"]="../data-normalizer"
)

# 函数：修复单个文件中的导入路径
fix_imports_in_file() {
    local file="$1"
    echo "  修复文件: $file"
    
    # 备份原文件
    cp "$file" "$file.backup"
    
    # 应用所有路径映射
    for github_path in "${!PATH_MAPPINGS[@]}"; do
        local local_path="${PATH_MAPPINGS[$github_path]}"
        
        # 使用sed替换导入路径
        sed -i.tmp "s|\"$github_path|\"$local_path|g" "$file"
        rm -f "$file.tmp"
    done
}

# 函数：修复Go模块文件
fix_go_mod() {
    local go_mod_file="$1"
    local service_name="$2"
    
    echo "  修复go.mod: $go_mod_file"
    
    # 备份原文件
    cp "$go_mod_file" "$go_mod_file.backup"
    
    # 创建新的go.mod内容
    cat > "$go_mod_file" << EOF
module $service_name

go 1.21

// 本地路径替换 - 防止网络依赖
replace $service_name => ./
EOF
    
    # 如果有require部分，保留外部依赖
    if grep -q "require" "$go_mod_file.backup"; then
        echo "" >> "$go_mod_file"
        sed -n '/^require (/,/^)/p' "$go_mod_file.backup" >> "$go_mod_file"
    fi
}

# 修复go-collector服务
echo "🔧 修复 go-collector 服务..."
cd "$PROJECT_ROOT/services/go-collector"

# 修复go.mod
fix_go_mod "go.mod" "github.com/marketprism/go-collector"

# 修复所有Go文件中的导入
find . -name "*.go" -type f | while read -r go_file; do
    fix_imports_in_file "$go_file"
done

# 修复data-normalizer服务
echo "🔧 修复 data-normalizer 服务..."
cd "$PROJECT_ROOT/services/data_normalizer"

# 修复go.mod
fix_go_mod "go.mod" "github.com/marketprism/data-normalizer"

# 修复所有Go文件中的导入
find . -name "*.go" -type f | while read -r go_file; do
    fix_imports_in_file "$go_file"
done

# 修复根目录的go.mod
echo "🔧 修复根目录 go.mod..."
cd "$PROJECT_ROOT"

if [ -f "go.mod" ]; then
    # 简化根目录的go.mod，移除虚假的replace指令
    cat > go.mod << 'EOF'
module github.com/marketprism

go 1.21

// 不再需要虚假的replace指令
// 每个服务使用自己的独立模块
EOF
fi

echo "✅ 虚假GitHub导入路径修复完成！"
echo ""
echo "📋 修复总结："
echo "  - 移除了所有github.com/marketprism/services/*的虚假路径"
echo "  - 转换为相对路径导入"
echo "  - 简化了go.mod配置"
echo "  - 备份文件保存为 *.backup"
echo ""
echo "🧪 下一步测试："
echo "  ./scripts/local_build.sh go-collector"
echo "  ./scripts/local_build.sh data-normalizer" 