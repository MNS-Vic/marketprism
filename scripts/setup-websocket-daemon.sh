#!/bin/bash

# MarketPrism WebSocket守护进程安装脚本

set -e

echo "🚀 开始安装MarketPrism WebSocket守护进程..."

# 检查运行环境
if [ "$EUID" -eq 0 ]; then
    echo "❌ 请不要使用root用户运行此脚本"
    exit 1
fi

# 项目根目录
PROJECT_ROOT="/home/ubuntu/marketprism"
cd "$PROJECT_ROOT"

# 创建必要的目录
echo "📁 创建必要目录..."
mkdir -p logs
mkdir -p data/pids
mkdir -p config/systemd

# 安装Python依赖
echo "📦 安装Python依赖..."
if [ -d "venv" ]; then
    echo "使用现有虚拟环境..."
    source venv/bin/activate
    pip install pyyaml psutil requests
else
    echo "使用系统包管理器安装依赖..."
    sudo apt update
    sudo apt install -y python3-yaml python3-psutil python3-requests
fi

# 设置脚本权限
echo "🔧 设置脚本权限..."
chmod +x scripts/websocket-daemon-manager.py
chmod +x scripts/setup-websocket-daemon.sh

# 创建systemd服务（需要sudo权限）
echo "⚙️ 安装systemd服务..."
if command -v systemctl >/dev/null 2>&1; then
    echo "检测到systemd，安装系统服务..."
    
    # 复制服务文件
    sudo cp config/systemd/marketprism-websocket.service /etc/systemd/system/
    
    # 重新加载systemd
    sudo systemctl daemon-reload
    
    # 启用服务
    sudo systemctl enable marketprism-websocket.service
    
    echo "✅ systemd服务安装完成"
    echo "使用以下命令管理服务:"
    echo "  启动: sudo systemctl start marketprism-websocket"
    echo "  停止: sudo systemctl stop marketprism-websocket"
    echo "  重启: sudo systemctl restart marketprism-websocket"
    echo "  状态: sudo systemctl status marketprism-websocket"
    echo "  日志: sudo journalctl -u marketprism-websocket -f"
else
    echo "⚠️ 未检测到systemd，将使用手动管理模式"
fi

# 创建管理脚本快捷方式
echo "🔗 创建管理脚本快捷方式..."
cat > websocket-daemon << 'EOF'
#!/bin/bash
cd /home/ubuntu/marketprism
python3 scripts/websocket-daemon-manager.py "$@"
EOF

chmod +x websocket-daemon

echo "✅ WebSocket守护进程安装完成！"
echo ""
echo "📋 使用方法:"
echo "  手动管理:"
echo "    启动: ./websocket-daemon start"
echo "    停止: ./websocket-daemon stop"
echo "    重启: ./websocket-daemon restart"
echo "    状态: ./websocket-daemon status"
echo ""
echo "  系统服务管理:"
echo "    启动: sudo systemctl start marketprism-websocket"
echo "    停止: sudo systemctl stop marketprism-websocket"
echo "    开机自启: sudo systemctl enable marketprism-websocket"
echo ""
echo "📊 监控和日志:"
echo "  守护进程日志: tail -f logs/websocket-daemon.log"
echo "  系统日志: sudo journalctl -u marketprism-websocket -f"
echo "  健康检查: curl http://localhost:8092/health"
echo ""
echo "🎯 现在可以启动WebSocket守护服务了！"
