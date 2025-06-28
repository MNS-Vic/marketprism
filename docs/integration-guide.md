# MarketPrism监控告警服务 - 集成指南文档

**文档版本**: v2.1.0  
**更新日期**: 2025-06-27  
**适用版本**: MarketPrism v2.1.0-secure-v2及以上

## 📋 概述

本文档详细说明了如何将MarketPrism监控告警服务与各种监控系统和第三方服务进行集成，包括Prometheus、Grafana和其他外部系统的认证配置方法。

## 📊 Prometheus集成

### 1. Prometheus抓取配置

**文件**: `prometheus.yml`

```yaml
# MarketPrism监控服务抓取配置
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  # MarketPrism监控告警服务
  - job_name: 'marketprism-monitoring'
    static_configs:
      - targets: ['localhost:8082']  # 或容器IP地址
    scrape_interval: 15s
    metrics_path: /metrics
    
    # 方法1: 使用Basic Auth认证（推荐）
    basic_auth:
      username: 'admin'
      password: 'marketprism2024!'
    
    # 方法2: 使用API Key认证（备选）
    # headers:
    #   X-API-Key: 'mp-monitoring-key-2024'
    
    # 可选: 添加标签
    relabel_configs:
      - source_labels: [__address__]
        target_label: instance
        replacement: 'marketprism-monitoring'
      - target_label: service
        replacement: 'marketprism'
      - target_label: environment
        replacement: 'production'
```

### 2. Docker环境Prometheus配置

**文件**: `config/prometheus-production.yml`

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: 'marketprism-production'
    environment: 'production'

scrape_configs:
  # Prometheus自身监控
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  # MarketPrism监控告警服务 - Docker环境
  - job_name: 'marketprism-monitoring'
    static_configs:
      - targets: ['172.25.0.5:8082']  # 使用容器IP地址
    scrape_interval: 15s
    metrics_path: /metrics
    basic_auth:
      username: 'admin'
      password: 'marketprism2024!'
    
    # 健康检查配置
    params:
      timeout: ['10s']
    
    # 标签配置
    relabel_configs:
      - target_label: job
        replacement: 'marketprism-monitoring'
      - target_label: service
        replacement: 'marketprism'
      - target_label: component
        replacement: 'monitoring-service'
```

### 3. Prometheus告警规则

**文件**: `config/prometheus/rules/marketprism-alerts.yml`

```yaml
groups:
  - name: marketprism-monitoring
    rules:
      # 服务可用性告警
      - alert: MarketPrismServiceDown
        expr: up{job="marketprism-monitoring"} == 0
        for: 1m
        labels:
          severity: critical
          service: marketprism
        annotations:
          summary: "MarketPrism监控服务不可用"
          description: "MarketPrism监控服务已经下线超过1分钟"

      # 认证失败率告警
      - alert: MarketPrismHighAuthFailureRate
        expr: rate(marketprism_auth_failures_total[5m]) > 0.1
        for: 2m
        labels:
          severity: warning
          service: marketprism
        annotations:
          summary: "MarketPrism认证失败率过高"
          description: "认证失败率: {{ $value | humanizePercentage }}"

      # 响应时间告警
      - alert: MarketPrismHighResponseTime
        expr: marketprism_http_request_duration_seconds > 0.5
        for: 5m
        labels:
          severity: warning
          service: marketprism
        annotations:
          summary: "MarketPrism响应时间过长"
          description: "平均响应时间: {{ $value }}秒"

      # 活跃告警数量告警
      - alert: MarketPrismTooManyActiveAlerts
        expr: marketprism_active_alerts_total > 100
        for: 1m
        labels:
          severity: warning
          service: marketprism
        annotations:
          summary: "MarketPrism活跃告警过多"
          description: "当前活跃告警数: {{ $value }}"
```

### 4. 验证Prometheus集成

```bash
#!/bin/bash
# verify-prometheus-integration.sh

echo "🔍 验证Prometheus集成"
echo "==================="

# 检查Prometheus targets
echo "1. 检查Prometheus targets状态:"
curl -s http://localhost:9090/api/v1/targets | \
    jq '.data.activeTargets[] | select(.job=="marketprism-monitoring") | {job: .job, health: .health, lastScrape: .lastScrape}'

# 检查指标是否被收集
echo -e "\n2. 检查MarketPrism指标:"
curl -s "http://localhost:9090/api/v1/query?query=marketprism_http_requests_total" | \
    jq '.data.result[0].value[1] // "无数据"'

# 检查告警规则
echo -e "\n3. 检查告警规则:"
curl -s http://localhost:9090/api/v1/rules | \
    jq '.data.groups[] | select(.name=="marketprism-monitoring") | .rules[].name'

echo -e "\n✅ Prometheus集成验证完成"
```

## 📈 Grafana集成

### 1. Grafana数据源配置

**文件**: `config/grafana/provisioning/datasources/prometheus.yml`

```yaml
apiVersion: 1

datasources:
  # 主要Prometheus数据源
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090  # Docker环境
    # url: http://localhost:9090  # 本地环境
    isDefault: true
    editable: true
    jsonData:
      httpMethod: POST
      manageAlerts: true
      prometheusType: Prometheus
      prometheusVersion: 2.40.0
      cacheLevel: 'High'
      disableRecordingRules: false
      incrementalQueryOverlapWindow: 10m
    secureJsonData: {}

  # MarketPrism直接数据源（可选）
  - name: MarketPrism-Direct
    type: prometheus
    access: proxy
    url: http://marketprism-monitoring:8082/metrics  # Docker环境
    # url: http://localhost:8082/metrics  # 本地环境
    isDefault: false
    editable: true
    basicAuth: true
    basicAuthUser: admin
    secureJsonData:
      basicAuthPassword: marketprism2024!
    jsonData:
      httpMethod: GET
      manageAlerts: false
      prometheusType: Prometheus
```

### 2. Grafana仪表板配置

**文件**: `config/grafana/dashboards/marketprism-dashboard.json`

```json
{
  "dashboard": {
    "id": null,
    "title": "MarketPrism监控告警服务",
    "tags": ["marketprism", "monitoring"],
    "timezone": "browser",
    "panels": [
      {
        "id": 1,
        "title": "服务状态",
        "type": "stat",
        "targets": [
          {
            "expr": "up{job=\"marketprism-monitoring\"}",
            "legendFormat": "服务状态"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "mappings": [
              {"options": {"0": {"text": "离线"}}, "type": "value"},
              {"options": {"1": {"text": "在线"}}, "type": "value"}
            ]
          }
        }
      },
      {
        "id": 2,
        "title": "HTTP请求总数",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(marketprism_http_requests_total[5m])",
            "legendFormat": "请求/秒"
          }
        ]
      },
      {
        "id": 3,
        "title": "认证统计",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(marketprism_auth_attempts_total[5m])",
            "legendFormat": "认证尝试/秒"
          },
          {
            "expr": "rate(marketprism_auth_failures_total[5m])",
            "legendFormat": "认证失败/秒"
          }
        ]
      },
      {
        "id": 4,
        "title": "响应时间",
        "type": "graph",
        "targets": [
          {
            "expr": "marketprism_http_request_duration_seconds",
            "legendFormat": "平均响应时间"
          }
        ]
      }
    ],
    "time": {
      "from": "now-1h",
      "to": "now"
    },
    "refresh": "30s"
  }
}
```

### 3. Grafana告警配置

```json
{
  "alert": {
    "id": 1,
    "name": "MarketPrism服务离线",
    "message": "MarketPrism监控服务已离线",
    "frequency": "10s",
    "conditions": [
      {
        "query": {
          "queryType": "",
          "refId": "A",
          "model": {
            "expr": "up{job=\"marketprism-monitoring\"}",
            "interval": "",
            "legendFormat": "",
            "refId": "A"
          }
        },
        "reducer": {
          "type": "last",
          "params": []
        },
        "evaluator": {
          "params": [1],
          "type": "lt"
        }
      }
    ],
    "executionErrorState": "alerting",
    "noDataState": "no_data",
    "for": "1m"
  }
}
```

### 4. 验证Grafana集成

```bash
#!/bin/bash
# verify-grafana-integration.sh

echo "📊 验证Grafana集成"
echo "=================="

# 检查Grafana健康状态
echo "1. 检查Grafana健康状态:"
curl -s http://localhost:3000/api/health | jq '.database'

# 检查数据源配置
echo -e "\n2. 检查数据源配置:"
curl -s -u admin:marketprism_admin_2024! \
     http://localhost:3000/api/datasources | \
     jq '.[] | {name: .name, type: .type, url: .url}'

# 测试数据源连接
echo -e "\n3. 测试Prometheus数据源连接:"
curl -s -u admin:marketprism_admin_2024! \
     -X POST http://localhost:3000/api/datasources/proxy/1/api/v1/query \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "query=up{job=\"marketprism-monitoring\"}" | \
     jq '.data.result[0].value[1] // "无数据"'

echo -e "\n✅ Grafana集成验证完成"
```

## 🔗 第三方系统集成

### 1. 监控系统集成

#### Zabbix集成

```bash
#!/bin/bash
# zabbix-integration.sh

# Zabbix监控脚本
MARKETPRISM_URL="http://localhost:8082"
API_KEY="mp-monitoring-key-2024"

# 检查服务状态
check_service_status() {
    status=$(curl -s -H "X-API-Key: $API_KEY" \
                  "$MARKETPRISM_URL/health" | \
                  jq -r '.status')
    
    if [ "$status" = "healthy" ]; then
        echo 1  # 健康
    else
        echo 0  # 不健康
    fi
}

# 获取活跃告警数
get_active_alerts() {
    curl -s -H "X-API-Key: $API_KEY" \
         "$MARKETPRISM_URL/metrics" | \
         grep "marketprism_active_alerts_total" | \
         awk '{print $2}'
}

# 获取认证失败率
get_auth_failure_rate() {
    curl -s -H "X-API-Key: $API_KEY" \
         "$MARKETPRISM_URL/api/v1/status" | \
         jq '.security.auth_failures'
}

# 根据参数执行相应检查
case "$1" in
    "status")
        check_service_status
        ;;
    "alerts")
        get_active_alerts
        ;;
    "auth_failures")
        get_auth_failure_rate
        ;;
    *)
        echo "Usage: $0 {status|alerts|auth_failures}"
        exit 1
        ;;
esac
```

#### Nagios集成

```bash
#!/bin/bash
# nagios-check-marketprism.sh

# Nagios插件脚本
STATE_OK=0
STATE_WARNING=1
STATE_CRITICAL=2
STATE_UNKNOWN=3

MARKETPRISM_URL="http://localhost:8082"
API_KEY="mp-monitoring-key-2024"

# 检查服务健康状态
check_health() {
    response=$(curl -s -w "%{http_code}" \
                    -H "X-API-Key: $API_KEY" \
                    "$MARKETPRISM_URL/health")
    
    http_code="${response: -3}"
    body="${response%???}"
    
    if [ "$http_code" = "200" ]; then
        status=$(echo "$body" | jq -r '.status')
        if [ "$status" = "healthy" ]; then
            echo "OK - MarketPrism服务健康"
            exit $STATE_OK
        else
            echo "WARNING - MarketPrism服务状态: $status"
            exit $STATE_WARNING
        fi
    else
        echo "CRITICAL - MarketPrism服务无响应 (HTTP $http_code)"
        exit $STATE_CRITICAL
    fi
}

# 检查认证失败率
check_auth_failures() {
    failures=$(curl -s -H "X-API-Key: $API_KEY" \
                    "$MARKETPRISM_URL/api/v1/status" | \
                    jq '.security.auth_failures')
    
    if [ "$failures" -gt 50 ]; then
        echo "CRITICAL - 认证失败次数过多: $failures"
        exit $STATE_CRITICAL
    elif [ "$failures" -gt 20 ]; then
        echo "WARNING - 认证失败次数较多: $failures"
        exit $STATE_WARNING
    else
        echo "OK - 认证失败次数正常: $failures"
        exit $STATE_OK
    fi
}

# 根据参数执行检查
case "$1" in
    "health")
        check_health
        ;;
    "auth")
        check_auth_failures
        ;;
    *)
        echo "UNKNOWN - Usage: $0 {health|auth}"
        exit $STATE_UNKNOWN
        ;;
esac
```

### 2. 日志系统集成

#### ELK Stack集成

**Filebeat配置**: `filebeat.yml`

```yaml
filebeat.inputs:
  - type: log
    enabled: true
    paths:
      - /var/log/marketprism/*.log
    fields:
      service: marketprism
      component: monitoring
    fields_under_root: true
    
    # 多行日志处理
    multiline.pattern: '^\d{4}-\d{2}-\d{2}'
    multiline.negate: true
    multiline.match: after

output.elasticsearch:
  hosts: ["localhost:9200"]
  index: "marketprism-logs-%{+yyyy.MM.dd}"
  
  # 认证配置
  username: "elastic"
  password: "your-password"

# Kibana仪表板
setup.kibana:
  host: "localhost:5601"

# 日志处理器
processors:
  - add_host_metadata:
      when.not.contains.tags: forwarded
  - add_docker_metadata: ~
  - add_kubernetes_metadata: ~
```

#### Fluentd集成

**Fluentd配置**: `fluent.conf`

```ruby
# MarketPrism日志收集配置
<source>
  @type tail
  path /var/log/marketprism/*.log
  pos_file /var/log/fluentd/marketprism.log.pos
  tag marketprism.logs
  format json
  time_key timestamp
  time_format %Y-%m-%dT%H:%M:%S.%LZ
</source>

# 过滤认证相关日志
<filter marketprism.logs>
  @type grep
  <regexp>
    key message
    pattern /auth|login|authentication/i
  </regexp>
</filter>

# 输出到Elasticsearch
<match marketprism.logs>
  @type elasticsearch
  host localhost
  port 9200
  index_name marketprism-logs
  type_name _doc
  
  # 认证配置
  user elastic
  password your-password
  
  # 缓冲配置
  <buffer>
    @type file
    path /var/log/fluentd/marketprism-buffer
    flush_mode interval
    flush_interval 10s
  </buffer>
</match>
```

### 3. 告警系统集成

#### PagerDuty集成

```python
#!/usr/bin/env python3
# pagerduty-integration.py

import requests
import json
import sys

class PagerDutyIntegration:
    def __init__(self, integration_key):
        self.integration_key = integration_key
        self.api_url = "https://events.pagerduty.com/v2/enqueue"
    
    def send_alert(self, severity, summary, source, custom_details=None):
        payload = {
            "routing_key": self.integration_key,
            "event_action": "trigger",
            "payload": {
                "summary": summary,
                "source": source,
                "severity": severity,
                "custom_details": custom_details or {}
            }
        }
        
        response = requests.post(
            self.api_url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload)
        )
        
        return response.status_code == 202

def check_marketprism_and_alert():
    # MarketPrism配置
    marketprism_url = "http://localhost:8082"
    api_key = "mp-monitoring-key-2024"
    
    # PagerDuty配置
    pagerduty = PagerDutyIntegration("your-pagerduty-integration-key")
    
    try:
        # 检查MarketPrism健康状态
        response = requests.get(
            f"{marketprism_url}/health",
            headers={"X-API-Key": api_key},
            timeout=10
        )
        
        if response.status_code != 200:
            # 发送告警
            pagerduty.send_alert(
                severity="critical",
                summary="MarketPrism监控服务不可用",
                source="marketprism-monitor",
                custom_details={
                    "http_status": response.status_code,
                    "url": marketprism_url
                }
            )
            return False
        
        # 检查认证失败率
        status_response = requests.get(
            f"{marketprism_url}/api/v1/status",
            headers={"X-API-Key": api_key}
        )
        
        if status_response.status_code == 200:
            data = status_response.json()
            auth_failures = data.get("security", {}).get("auth_failures", 0)
            
            if auth_failures > 50:
                pagerduty.send_alert(
                    severity="warning",
                    summary=f"MarketPrism认证失败率过高: {auth_failures}次",
                    source="marketprism-auth-monitor",
                    custom_details={
                        "auth_failures": auth_failures,
                        "service": "marketprism"
                    }
                )
        
        return True
        
    except Exception as e:
        pagerduty.send_alert(
            severity="critical",
            summary=f"MarketPrism监控检查失败: {str(e)}",
            source="marketprism-monitor",
            custom_details={"error": str(e)}
        )
        return False

if __name__ == "__main__":
    success = check_marketprism_and_alert()
    sys.exit(0 if success else 1)
```

#### Slack集成

```bash
#!/bin/bash
# slack-integration.sh

# Slack Webhook配置
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
CHANNEL="#monitoring"
USERNAME="MarketPrism Bot"

# MarketPrism配置
MARKETPRISM_URL="http://localhost:8082"
API_KEY="mp-monitoring-key-2024"

# 发送Slack消息
send_slack_message() {
    local color="$1"
    local title="$2"
    local message="$3"
    
    payload=$(cat <<EOF
{
    "channel": "$CHANNEL",
    "username": "$USERNAME",
    "attachments": [
        {
            "color": "$color",
            "title": "$title",
            "text": "$message",
            "ts": $(date +%s)
        }
    ]
}
EOF
)
    
    curl -X POST -H 'Content-type: application/json' \
         --data "$payload" \
         "$SLACK_WEBHOOK_URL"
}

# 检查服务状态并发送告警
check_and_alert() {
    response=$(curl -s -w "%{http_code}" \
                    -H "X-API-Key: $API_KEY" \
                    "$MARKETPRISM_URL/health")
    
    http_code="${response: -3}"
    
    if [ "$http_code" != "200" ]; then
        send_slack_message "danger" \
                          "🚨 MarketPrism服务告警" \
                          "MarketPrism监控服务无响应 (HTTP $http_code)"
    else
        body="${response%???}"
        status=$(echo "$body" | jq -r '.status')
        
        if [ "$status" != "healthy" ]; then
            send_slack_message "warning" \
                              "⚠️ MarketPrism服务警告" \
                              "MarketPrism服务状态异常: $status"
        fi
    fi
}

# 执行检查
check_and_alert
```

## 🔧 集成验证脚本

### 完整集成验证

```bash
#!/bin/bash
# complete-integration-verification.sh

echo "🔍 MarketPrism完整集成验证"
echo "========================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 配置
MARKETPRISM_URL="http://localhost:8082"
PROMETHEUS_URL="http://localhost:9090"
GRAFANA_URL="http://localhost:3000"
API_KEY="mp-monitoring-key-2024"

# 验证函数
verify_service() {
    local service_name="$1"
    local url="$2"
    local expected_status="$3"
    
    echo -n "验证 $service_name: "
    
    if curl -s "$url" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ 正常${NC}"
        return 0
    else
        echo -e "${RED}❌ 异常${NC}"
        return 1
    fi
}

# 验证认证
verify_auth() {
    echo -n "验证MarketPrism认证: "
    
    # 测试无认证访问（应该失败）
    if curl -s -f "$MARKETPRISM_URL/api/v1/alerts" > /dev/null 2>&1; then
        echo -e "${RED}❌ 认证配置异常${NC}"
        return 1
    fi
    
    # 测试API Key认证（应该成功）
    if curl -s -f -H "X-API-Key: $API_KEY" \
            "$MARKETPRISM_URL/api/v1/alerts" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ 正常${NC}"
        return 0
    else
        echo -e "${RED}❌ API Key认证失败${NC}"
        return 1
    fi
}

# 验证Prometheus集成
verify_prometheus() {
    echo -n "验证Prometheus集成: "
    
    # 检查targets状态
    target_status=$(curl -s "$PROMETHEUS_URL/api/v1/targets" | \
                   jq -r '.data.activeTargets[] | select(.job=="marketprism-monitoring") | .health')
    
    if [ "$target_status" = "up" ]; then
        echo -e "${GREEN}✅ 正常${NC}"
        return 0
    else
        echo -e "${RED}❌ Target状态: $target_status${NC}"
        return 1
    fi
}

# 验证Grafana集成
verify_grafana() {
    echo -n "验证Grafana集成: "
    
    # 检查数据源
    datasource_status=$(curl -s -u admin:marketprism_admin_2024! \
                       "$GRAFANA_URL/api/datasources" | \
                       jq -r '.[] | select(.name=="Prometheus") | .name')
    
    if [ "$datasource_status" = "Prometheus" ]; then
        echo -e "${GREEN}✅ 正常${NC}"
        return 0
    else
        echo -e "${RED}❌ 数据源配置异常${NC}"
        return 1
    fi
}

# 主验证流程
main() {
    echo "开始集成验证..."
    echo ""
    
    # 基础服务验证
    verify_service "MarketPrism" "$MARKETPRISM_URL/health" "200"
    verify_service "Prometheus" "$PROMETHEUS_URL/-/healthy" "200"
    verify_service "Grafana" "$GRAFANA_URL/api/health" "200"
    
    echo ""
    
    # 认证验证
    verify_auth
    
    echo ""
    
    # 集成验证
    verify_prometheus
    verify_grafana
    
    echo ""
    echo "🎯 集成验证完成"
}

# 执行验证
main
```

---

**集成建议**:
- 优先使用Basic Auth进行Prometheus集成
- Grafana数据源配置建议使用代理模式
- 第三方系统集成时注意API Key的安全存储
- 定期验证集成状态和认证配置

**技术支持**: 如有集成问题，请参考相应的验证脚本或联系系统管理员
