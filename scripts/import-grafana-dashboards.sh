#!/bin/bash
# import-grafana-dashboards.sh - 导入MarketPrism Grafana仪表板

set -e

# 配置
GRAFANA_URL="http://localhost:3000"
GRAFANA_USER="admin"
GRAFANA_PASSWORD="marketprism_admin_2024!"
DASHBOARD_DIR="config/grafana/dashboards"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}📊 MarketPrism Grafana仪表板导入工具${NC}"
echo "=================================="
echo ""

# 检查Grafana服务状态
check_grafana_status() {
    echo -n "检查Grafana服务状态: "
    if curl -s "$GRAFANA_URL/api/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ 正常${NC}"
        return 0
    else
        echo -e "${RED}❌ 服务不可用${NC}"
        return 1
    fi
}

# 创建文件夹
create_folder() {
    local folder_name="$1"
    echo -n "创建文件夹 '$folder_name': "
    
    folder_payload=$(cat <<EOF
{
  "title": "$folder_name"
}
EOF
)
    
    response=$(curl -s -w "%{http_code}" \
                    -u "$GRAFANA_USER:$GRAFANA_PASSWORD" \
                    -H "Content-Type: application/json" \
                    -X POST \
                    -d "$folder_payload" \
                    "$GRAFANA_URL/api/folders")
    
    http_code="${response: -3}"
    body="${response%???}"
    
    if [ "$http_code" = "200" ] || [ "$http_code" = "412" ]; then
        echo -e "${GREEN}✅ 成功${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠️ 可能已存在${NC}"
        return 0
    fi
}

# 导入仪表板
import_dashboard() {
    local dashboard_file="$1"
    local dashboard_name=$(basename "$dashboard_file" .json)
    
    echo -n "导入仪表板 '$dashboard_name': "
    
    if [ ! -f "$dashboard_file" ]; then
        echo -e "${RED}❌ 文件不存在${NC}"
        return 1
    fi
    
    # 读取仪表板JSON并包装为导入格式
    dashboard_json=$(cat "$dashboard_file")
    import_payload=$(cat <<EOF
{
  "dashboard": $(echo "$dashboard_json" | jq '.dashboard'),
  "folderId": 0,
  "overwrite": true
}
EOF
)
    
    response=$(curl -s -w "%{http_code}" \
                    -u "$GRAFANA_USER:$GRAFANA_PASSWORD" \
                    -H "Content-Type: application/json" \
                    -X POST \
                    -d "$import_payload" \
                    "$GRAFANA_URL/api/dashboards/db")
    
    http_code="${response: -3}"
    body="${response%???}"
    
    if [ "$http_code" = "200" ]; then
        dashboard_url=$(echo "$body" | jq -r '.url // empty')
        echo -e "${GREEN}✅ 成功${NC}"
        if [ -n "$dashboard_url" ]; then
            echo "   访问地址: $GRAFANA_URL$dashboard_url"
        fi
        return 0
    else
        echo -e "${RED}❌ 失败${NC}"
        echo "   错误信息: $(echo "$body" | jq -r '.message // "未知错误"')"
        return 1
    fi
}

# 配置数据源
configure_datasource() {
    echo -n "检查Prometheus数据源: "
    
    # 检查数据源是否存在
    datasources=$(curl -s -u "$GRAFANA_USER:$GRAFANA_PASSWORD" \
                       "$GRAFANA_URL/api/datasources")
    
    prometheus_exists=$(echo "$datasources" | jq -r '.[] | select(.name=="Prometheus") | .name')
    
    if [ "$prometheus_exists" = "Prometheus" ]; then
        echo -e "${GREEN}✅ 已存在${NC}"
        return 0
    fi
    
    # 创建Prometheus数据源
    datasource_payload=$(cat <<EOF
{
  "name": "Prometheus",
  "type": "prometheus",
  "url": "http://marketprism-prometheus:9090",
  "access": "proxy",
  "isDefault": true,
  "jsonData": {
    "httpMethod": "POST",
    "manageAlerts": true,
    "prometheusType": "Prometheus",
    "prometheusVersion": "2.40.0"
  }
}
EOF
)
    
    response=$(curl -s -w "%{http_code}" \
                    -u "$GRAFANA_USER:$GRAFANA_PASSWORD" \
                    -H "Content-Type: application/json" \
                    -X POST \
                    -d "$datasource_payload" \
                    "$GRAFANA_URL/api/datasources")
    
    http_code="${response: -3}"
    
    if [ "$http_code" = "200" ]; then
        echo -e "${GREEN}✅ 创建成功${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠️ 可能已存在${NC}"
        return 0
    fi
}

# 主执行流程
main() {
    echo "开始导入MarketPrism仪表板..."
    echo ""
    
    # 1. 检查Grafana状态
    if ! check_grafana_status; then
        echo -e "${RED}❌ Grafana服务不可用，请检查服务状态${NC}"
        exit 1
    fi
    
    echo ""
    
    # 2. 配置数据源
    configure_datasource
    
    echo ""
    
    # 3. 创建文件夹
    create_folder "MarketPrism"
    
    echo ""
    
    # 4. 导入仪表板
    echo "导入仪表板文件:"
    
    success_count=0
    total_count=0
    
    for dashboard_file in "$DASHBOARD_DIR"/*.json; do
        if [ -f "$dashboard_file" ]; then
            total_count=$((total_count + 1))
            if import_dashboard "$dashboard_file"; then
                success_count=$((success_count + 1))
            fi
            echo ""
        fi
    done
    
    # 5. 导入结果总结
    echo "=================================="
    echo -e "${BLUE}📊 导入结果总结${NC}"
    echo "总仪表板数: $total_count"
    echo "成功导入: $success_count"
    echo "失败数量: $((total_count - success_count))"
    
    if [ "$success_count" -eq "$total_count" ]; then
        echo -e "${GREEN}✅ 所有仪表板导入成功！${NC}"
    else
        echo -e "${YELLOW}⚠️ 部分仪表板导入失败${NC}"
    fi
    
    echo ""
    echo "🌐 访问Grafana: $GRAFANA_URL"
    echo "👤 用户名: $GRAFANA_USER"
    echo "🔑 密码: $GRAFANA_PASSWORD"
    echo ""
    echo "📊 推荐仪表板:"
    echo "  - MarketPrism监控告警服务 - 主仪表板"
    echo "  - MarketPrism安全监控仪表板"
}

# 执行主流程
main "$@"
