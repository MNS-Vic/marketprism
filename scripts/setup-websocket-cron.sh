#!/bin/bash
"""
设置WebSocket服务的定时维护任务
"""

PROJECT_ROOT="/home/ubuntu/marketprism"
CRON_FILE="/tmp/websocket-cron"

echo "🚀 设置WebSocket服务定时维护任务..."

# 创建cron任务文件
cat > $CRON_FILE << EOF
# WebSocket服务维护任务
# 每天凌晨2点执行维护
0 2 * * * cd $PROJECT_ROOT && python3 scripts/websocket-maintenance.py >> logs/cron-maintenance.log 2>&1

# 每周日凌晨3点执行深度清理
0 3 * * 0 cd $PROJECT_ROOT && python3 scripts/websocket-maintenance.py && find logs/ -name "*.log" -mtime +30 -delete >> logs/cron-cleanup.log 2>&1

# 每小时检查服务状态（可选，如果需要额外监控）
# 0 * * * * cd $PROJECT_ROOT && curl -s http://localhost:8092/health > /dev/null || echo "WebSocket health check failed at \$(date)" >> logs/cron-health.log
EOF

# 安装cron任务
crontab $CRON_FILE

# 清理临时文件
rm $CRON_FILE

echo "✅ 定时任务设置完成"
echo "📋 当前cron任务:"
crontab -l | grep -E "(websocket|WebSocket)"

echo ""
echo "🔧 手动执行维护命令:"
echo "  维护: cd $PROJECT_ROOT && python3 scripts/websocket-maintenance.py"
echo "  监控: cd $PROJECT_ROOT && python3 scripts/websocket-monitor.py"
echo ""
echo "📝 日志文件位置:"
echo "  守护进程: $PROJECT_ROOT/logs/websocket-daemon.log"
echo "  监控日志: $PROJECT_ROOT/logs/websocket-monitor.log"
echo "  维护日志: $PROJECT_ROOT/logs/websocket-maintenance.log"
