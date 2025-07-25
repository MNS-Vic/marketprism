#!/bin/bash
# MarketPrism 端口冲突检测脚本

echo "🔍 MarketPrism 端口冲突检测"
echo "========================="
echo ""

# 检查配置文件中的端口冲突
echo "1. 检查 config/services.yaml 中的端口冲突:"
echo "-------------------------------------------"

# 提取所有端口配置
ports=$(grep -E "^\s*port:\s*[0-9]+" config/services.yaml | sed 's/.*port:\s*//' | sort -n)

# 检查重复端口
duplicates=$(echo "$ports" | uniq -d)

if [ -z "$duplicates" ]; then
    echo "✅ 配置文件中没有发现端口冲突"
else
    echo "🚨 发现端口冲突:"
    for port in $duplicates; do
        echo "   端口 $port 被多个服务使用:"
        grep -B2 -A1 "port:\s*$port" config/services.yaml | grep -E "(^\s*[a-z-]+:|port:)"
        echo ""
    done
fi

echo ""

# 检查Docker Compose端口映射
echo "2. 检查 docker-compose.yml 中的端口映射:"
echo "-------------------------------------------"

if [ -f "docker-compose.yml" ]; then
    # 提取端口映射
    compose_ports=$(grep -E "^\s*-\s*[0-9]+:[0-9]+" docker-compose.yml | sed 's/.*-\s*//' | cut -d':' -f1 | sort -n)
    
    # 检查重复端口
    compose_duplicates=$(echo "$compose_ports" | uniq -d)
    
    if [ -z "$compose_duplicates" ]; then
        echo "✅ Docker Compose中没有发现端口冲突"
    else
        echo "🚨 发现Docker Compose端口冲突:"
        for port in $compose_duplicates; do
            echo "   端口 $port 被多个容器使用:"
            grep -B2 -A1 "$port:" docker-compose.yml
            echo ""
        done
    fi
else
    echo "⚠️  docker-compose.yml 文件不存在"
fi

echo ""

# 检查当前系统端口占用
echo "3. 检查当前系统端口占用 (8000-9999):"
echo "-------------------------------------------"

occupied_ports=$(netstat -tlnp 2>/dev/null | grep -E ":(8[0-9]{3}|9[0-9]{3})" | awk '{print $4}' | cut -d':' -f2 | sort -n | uniq)

if [ -z "$occupied_ports" ]; then
    echo "✅ 8000-9999端口段没有被占用"
else
    echo "📊 当前占用的端口:"
    for port in $occupied_ports; do
        process=$(netstat -tlnp 2>/dev/null | grep ":$port " | awk '{print $7}' | head -1)
        echo "   端口 $port - $process"
    done
fi

echo ""

# 检查Docker容器端口
echo "4. 检查Docker容器端口使用:"
echo "-------------------------------------------"

if command -v docker &> /dev/null; then
    running_containers=$(docker ps --format "table {{.Names}}\t{{.Ports}}" | grep -v "NAMES")
    
    if [ -z "$running_containers" ]; then
        echo "✅ 没有运行中的Docker容器"
    else
        echo "📊 运行中的容器端口:"
        echo "$running_containers"
    fi
else
    echo "⚠️  Docker未安装或不可用"
fi

echo ""

# 端口分配建议
echo "5. 端口分配建议:"
echo "-------------------------------------------"
echo "📋 按照 docs/port-allocation-standard.md 标准:"
echo "   8080-8089: 核心业务服务"
echo "   8090-8099: 支持服务和工具"
echo "   9000-9099: 监控和管理服务"
echo "   4000-4999: 消息队列和数据库"
echo "   3000-3999: 前端和UI服务"

echo ""
echo "🎯 检测完成！"
