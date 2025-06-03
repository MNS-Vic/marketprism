#!/bin/bash

# 卡住先生的紧急解卡器
# 专治各种卡住不服！

echo "🚨 紧急解卡模式启动！"
echo ""

# 1. 检查当前系统负载
echo "📊 当前系统状态："
uptime
echo ""

# 2. 找出占用CPU的进程
echo "🔍 CPU占用TOP5："
ps aux | sort -nr -k 3 | head -5
echo ""

# 3. 检查Docker进程
echo "🐳 Docker相关进程："
ps aux | grep -i docker | grep -v grep
echo ""

# 4. 强制清理方案
echo "💥 紧急清理选项："
echo "1. 重启Docker Desktop (推荐)"
echo "2. 清理所有Docker容器和镜像"
echo "3. 重启电脑"
echo ""

# 5. 提供一键解决方案
echo "🎯 一键解决方案："
echo "osascript -e 'quit app \"Docker Desktop\"' && sleep 5 && open -a \"Docker Desktop\""
echo ""

# 6. 检查是否有卡住的进程
echo "🔍 可能卡住的进程："
ps aux | awk '$3 > 10.0 || $4 > 10.0' | head -10
echo ""

echo "✅ 诊断完成！选择上面的解决方案执行。" 