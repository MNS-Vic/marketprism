#!/bin/bash
# MarketPrism 依赖安装脚本
# 解决缺失依赖问题，特别是WebSocket代理所需的SOCKS支持

echo "🔧 MarketPrism 依赖安装脚本"
echo "============================================"

# 进入项目根目录
cd "$(dirname "$0")/.."

echo "📍 当前目录: $(pwd)"

# 检查Python环境
echo "🐍 检查Python环境..."
python3 --version
pip3 --version

# 安装基础依赖
echo "📦 安装基础依赖..."
pip3 install -r requirements.txt

# 安装测试依赖
if [ -f "requirements-test.txt" ]; then
    echo "🧪 安装测试依赖..."
    pip3 install -r requirements-test.txt
fi

# 安装WebSocket代理所需的SOCKS支持
echo "🌐 安装SOCKS代理支持..."
pip3 install PySocks

# 安装Docker Python SDK (用于基础设施管理)
echo "🐳 安装Docker Python SDK..."
pip3 install docker

# 安装系统监控依赖
echo "📊 安装系统监控依赖..."
pip3 install psutil

# 安装其他可能缺失的依赖
echo "🔧 安装其他依赖..."
pip3 install pyyaml aiofiles structlog

# 检查关键依赖是否正确安装
echo "✅ 验证关键依赖安装..."

python3 -c "import socks; print('✅ PySocks (SOCKS代理支持) 安装成功')" || echo "❌ PySocks 安装失败"
python3 -c "import docker; print('✅ Docker SDK 安装成功')" || echo "❌ Docker SDK 安装失败"
python3 -c "import psutil; print('✅ psutil (系统监控) 安装成功')" || echo "❌ psutil 安装失败"
python3 -c "import aioredis; print('✅ aioredis 安装成功')" || echo "❌ aioredis 安装失败"
python3 -c "import aiochclient; print('✅ aiochclient 安装成功')" || echo "❌ aiochclient 安装失败"
python3 -c "import nats; print('✅ nats-py 安装成功')" || echo "❌ nats-py 安装失败"

echo "🎉 依赖安装完成!"
echo "============================================"
echo "💡 下一步: 运行综合修复测试"
echo "   python scripts/comprehensive_fix_test.py"