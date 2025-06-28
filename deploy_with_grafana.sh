#!/bin/bash

# MarketPrism + Grafana 一键部署脚本

set -e

echo "🚀 MarketPrism + Grafana 集成部署"
echo "=================================="

# 检查Docker和Docker Compose
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装，请先安装Docker"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose 未安装，请先安装Docker Compose"
    exit 1
fi

# 创建必要的目录
echo "📁 创建配置目录..."
mkdir -p config/grafana/provisioning/{datasources,dashboards}
mkdir -p config/grafana/dashboards
mkdir -p logs
mkdir -p data/{prometheus,grafana,redis,clickhouse}

# 设置权限
echo "🔐 设置目录权限..."
sudo chown -R 472:472 data/grafana  # Grafana用户ID
sudo chown -R 65534:65534 data/prometheus  # Nobody用户ID

# 启动服务
echo "🚀 启动MarketPrism + Grafana服务..."
docker-compose -f docker-compose.grafana.yml up -d

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 30

# 检查服务状态
echo "🔍 检查服务状态..."

# 检查监控告警服务
if curl -s http://localhost:8082/health > /dev/null; then
    echo "✅ MarketPrism监控告警服务: 正常"
else
    echo "❌ MarketPrism监控告警服务: 异常"
fi

# 检查Prometheus
if curl -s http://localhost:9090/-/healthy > /dev/null; then
    echo "✅ Prometheus: 正常"
else
    echo "❌ Prometheus: 异常"
fi

# 检查Grafana
if curl -s http://localhost:3000/api/health > /dev/null; then
    echo "✅ Grafana: 正常"
else
    echo "❌ Grafana: 异常"
fi

echo ""
echo "🎉 部署完成！"
echo "=================================="
echo "📊 访问地址:"
echo "- MarketPrism API: http://localhost:8082"
echo "- Prometheus: http://localhost:9090"
echo "- Grafana: http://localhost:3000"
echo ""
echo "🔑 Grafana登录信息:"
echo "- 用户名: admin"
echo "- 密码: marketprism123"
echo ""
echo "📋 下一步操作:"
echo "1. 访问Grafana配置告警通知渠道"
echo "2. 导入MarketPrism仪表板"
echo "3. 设置告警规则"
echo ""
echo "🛠️ 管理命令:"
echo "- 查看日志: docker-compose -f docker-compose.grafana.yml logs -f"
echo "- 停止服务: docker-compose -f docker-compose.grafana.yml down"
echo "- 重启服务: docker-compose -f docker-compose.grafana.yml restart"
