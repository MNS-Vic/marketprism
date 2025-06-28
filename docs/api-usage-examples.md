# MarketPrism监控告警服务 - API使用示例文档

**文档版本**: v2.1.0  
**更新日期**: 2025-06-27  
**适用版本**: MarketPrism v2.1.0-secure-v2及以上

## 📋 概述

本文档提供了MarketPrism监控告警服务所有API端点的详细使用示例，包括认证方法、请求格式和响应示例。

## 🔐 认证方法

### API Key认证示例

```bash
# 方法1: 使用HTTP头（推荐）
curl -H "X-API-Key: mp-monitoring-key-2024" \
     -H "Content-Type: application/json" \
     http://localhost:8082/api/v1/alerts

# 方法2: 使用查询参数（不推荐用于生产环境）
curl "http://localhost:8082/api/v1/alerts?api_key=mp-monitoring-key-2024"
```

### Basic Auth认证示例

```bash
# 方法1: 使用-u参数（推荐）
curl -u admin:marketprism2024! \
     -H "Content-Type: application/json" \
     http://localhost:8082/api/v1/alerts

# 方法2: 使用Authorization头
curl -H "Authorization: Basic YWRtaW46bWFya2V0cHJpc20yMDI0IQ==" \
     -H "Content-Type: application/json" \
     http://localhost:8082/api/v1/alerts
```

## 🌐 公开端点（无需认证）

### 1. 根路径 - 服务信息

**端点**: `GET /`

```bash
# 请求
curl http://localhost:8082/

# 响应示例
{
  "service": "MarketPrism Monitoring & Alerting Service",
  "version": "2.1.0-secure-v2",
  "status": "running",
  "security_enabled": true,
  "uptime_seconds": 3600.5,
  "timestamp": "2025-06-27T23:45:00.000Z",
  "endpoints": {
    "health": "/health",
    "ready": "/ready",
    "alerts": "/api/v1/alerts",
    "rules": "/api/v1/rules",
    "status": "/api/v1/status",
    "version": "/api/v1/version",
    "metrics": "/metrics",
    "login": "/login"
  },
  "authentication": {
    "enabled": true,
    "methods": ["API Key", "Basic Auth"]
  }
}
```

### 2. 健康检查

**端点**: `GET /health`

```bash
# 请求
curl http://localhost:8082/health

# 响应示例
{
  "status": "healthy",
  "version": "2.1.0-secure-v2",
  "timestamp": "2025-06-27T23:45:00.000Z",
  "uptime_seconds": 3600.5,
  "components": {
    "alert_manager": true,
    "rule_engine": true,
    "data_collector": true,
    "api_gateway": true,
    "message_broker": true,
    "data_storage": true,
    "prometheus": true,
    "auth_system": true,
    "security_layer": true
  },
  "security": {
    "auth_enabled": true,
    "auth_attempts": 150,
    "auth_failures": 12
  },
  "metrics": {
    "total_requests": 1250,
    "active_alerts": 2
  }
}
```

### 3. 就绪检查

**端点**: `GET /ready`

```bash
# 请求
curl http://localhost:8082/ready

# 响应示例
{
  "ready": true,
  "timestamp": "2025-06-27T23:45:00.000Z",
  "critical_components": {
    "api_gateway": true,
    "data_storage": true,
    "prometheus": true
  }
}
```

## 🔒 受保护端点（需要认证）

### 1. 告警列表

**端点**: `GET /api/v1/alerts`

**查询参数**:
- `severity`: 告警级别 (critical, high, medium, low)
- `status`: 告警状态 (active, resolved, suppressed)
- `category`: 告警分类 (system, application, network)
- `limit`: 返回数量限制 (默认100)
- `offset`: 偏移量 (默认0)
- `sort_by`: 排序字段 (timestamp, severity, name)
- `sort_order`: 排序方向 (asc, desc)
- `search`: 搜索关键词

```bash
# 基本请求
curl -H "X-API-Key: mp-monitoring-key-2024" \
     http://localhost:8082/api/v1/alerts

# 带参数的请求
curl -H "X-API-Key: mp-monitoring-key-2024" \
     "http://localhost:8082/api/v1/alerts?severity=critical&status=active&limit=10"

# 使用Basic Auth
curl -u admin:marketprism2024! \
     "http://localhost:8082/api/v1/alerts?category=system&sort_by=timestamp&sort_order=desc"

# 响应示例
{
  "alerts": [
    {
      "id": "alert-001",
      "name": "High CPU Usage",
      "severity": "critical",
      "status": "active",
      "category": "system",
      "message": "CPU usage above 90% for 5 minutes",
      "timestamp": "2025-06-27T23:40:00.000Z",
      "source": "monitoring-system",
      "labels": {
        "host": "server-01",
        "service": "marketprism"
      }
    },
    {
      "id": "alert-002",
      "name": "Memory Usage Warning",
      "severity": "high",
      "status": "active",
      "category": "system",
      "message": "Memory usage above 80%",
      "timestamp": "2025-06-27T23:35:00.000Z",
      "source": "monitoring-system",
      "labels": {
        "host": "server-02",
        "service": "marketprism"
      }
    }
  ],
  "total": 2,
  "limit": 100,
  "offset": 0,
  "timestamp": "2025-06-27T23:45:00.000Z"
}
```

### 2. 规则列表

**端点**: `GET /api/v1/rules`

**查询参数**:
- `enabled`: 规则状态 (true, false)
- `category`: 规则分类 (system, application, network)
- `limit`: 返回数量限制 (默认100)
- `offset`: 偏移量 (默认0)
- `search`: 搜索关键词

```bash
# 基本请求
curl -H "X-API-Key: mp-monitoring-key-2024" \
     http://localhost:8082/api/v1/rules

# 查询启用的规则
curl -H "X-API-Key: mp-monitoring-key-2024" \
     "http://localhost:8082/api/v1/rules?enabled=true&category=system"

# 响应示例
{
  "rules": [
    {
      "id": "rule-001",
      "name": "CPU Usage Alert",
      "description": "Alert when CPU usage exceeds 90%",
      "enabled": true,
      "category": "system",
      "condition": "cpu_usage > 90",
      "severity": "critical",
      "actions": ["email", "slack"],
      "created_at": "2025-06-27T10:00:00.000Z"
    }
  ],
  "total": 1,
  "limit": 100,
  "offset": 0,
  "timestamp": "2025-06-27T23:45:00.000Z"
}
```

### 3. 服务状态

**端点**: `GET /api/v1/status`

```bash
# 请求
curl -H "X-API-Key: mp-monitoring-key-2024" \
     http://localhost:8082/api/v1/status

# 响应示例
{
  "service": "MarketPrism Monitoring & Alerting Service",
  "version": "2.1.0-secure-v2",
  "status": "running",
  "uptime_seconds": 3600.5,
  "timestamp": "2025-06-27T23:45:00.000Z",
  "security": {
    "authentication": "enabled",
    "auth_attempts": 150,
    "auth_failures": 12
  },
  "performance": {
    "total_requests": 1250,
    "avg_response_time": 0.023,
    "requests_by_endpoint": {
      "/api/v1/alerts": 450,
      "/api/v1/rules": 200,
      "/health": 600
    }
  }
}
```

### 4. 版本信息

**端点**: `GET /api/v1/version`

```bash
# 请求
curl -H "X-API-Key: mp-monitoring-key-2024" \
     http://localhost:8082/api/v1/version

# 响应示例
{
  "service": "MarketPrism Monitoring & Alerting Service",
  "version": "2.1.0-secure-v2",
  "build_date": "2025-06-27",
  "security_features": [
    "API Key Authentication",
    "Basic Authentication",
    "Input Validation",
    "Security Logging"
  ],
  "api_version": "v1",
  "timestamp": "2025-06-27T23:45:00.000Z"
}
```

### 5. Prometheus指标

**端点**: `GET /metrics`

```bash
# 请求
curl -H "X-API-Key: mp-monitoring-key-2024" \
     http://localhost:8082/metrics

# 响应示例（Prometheus格式）
# HELP marketprism_http_requests_total Total number of HTTP requests
# TYPE marketprism_http_requests_total counter
marketprism_http_requests_total 1250

# HELP marketprism_http_request_duration_seconds HTTP request duration in seconds
# TYPE marketprism_http_request_duration_seconds gauge
marketprism_http_request_duration_seconds 0.023000

# HELP marketprism_active_alerts_total Number of active alerts
# TYPE marketprism_active_alerts_total gauge
marketprism_active_alerts_total 2

# HELP marketprism_service_health Service health status (1=healthy, 0=unhealthy)
# TYPE marketprism_service_health gauge
marketprism_service_health 1

# HELP marketprism_auth_attempts_total Total authentication attempts
# TYPE marketprism_auth_attempts_total counter
marketprism_auth_attempts_total 150

# HELP marketprism_auth_failures_total Total authentication failures
# TYPE marketprism_auth_failures_total counter
marketprism_auth_failures_total 12
```

### 6. 登录接口

**端点**: `POST /login`

```bash
# 请求
curl -X POST \
     -H "Content-Type: application/json" \
     -d '{"username":"admin","password":"marketprism2024!"}' \
     http://localhost:8082/login

# 响应示例（成功）
{
  "success": true,
  "message": "Login successful",
  "api_key": "mp-monitoring-key-2024",
  "instructions": "Use the api_key in X-API-Key header for subsequent requests"
}

# 响应示例（失败）
{
  "error": "Invalid credentials"
}
```

## 🔧 错误处理示例

### 认证错误

```bash
# 无认证访问受保护端点
curl http://localhost:8082/api/v1/alerts

# 响应
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="MarketPrism Monitoring"
Content-Type: application/json

{
  "error": "Authentication required",
  "message": "Use X-API-Key header or Basic Auth"
}
```

### 错误的API Key

```bash
# 错误的API Key
curl -H "X-API-Key: wrong-key" \
     http://localhost:8082/api/v1/alerts

# 响应
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "error": "Authentication required",
  "message": "Use X-API-Key header or Basic Auth"
}
```

### 参数错误

```bash
# 无效的查询参数
curl -H "X-API-Key: mp-monitoring-key-2024" \
     "http://localhost:8082/api/v1/alerts?limit=invalid"

# 响应
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "Invalid parameter",
  "message": "limit must be a valid integer"
}
```

## 📝 编程语言示例

### Python示例

```python
import requests
import json

# 配置
BASE_URL = "http://localhost:8082"
API_KEY = "mp-monitoring-key-2024"
USERNAME = "admin"
PASSWORD = "marketprism2024!"

# API Key认证
def get_alerts_with_api_key():
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    response = requests.get(f"{BASE_URL}/api/v1/alerts", headers=headers)
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return None

# Basic Auth认证
def get_alerts_with_basic_auth():
    auth = (USERNAME, PASSWORD)
    
    response = requests.get(f"{BASE_URL}/api/v1/alerts", auth=auth)
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return None

# 使用示例
if __name__ == "__main__":
    # 使用API Key
    alerts = get_alerts_with_api_key()
    if alerts:
        print(f"Found {alerts['total']} alerts")
    
    # 使用Basic Auth
    alerts = get_alerts_with_basic_auth()
    if alerts:
        print(f"Found {alerts['total']} alerts")
```

### JavaScript示例

```javascript
// 配置
const BASE_URL = "http://localhost:8082";
const API_KEY = "mp-monitoring-key-2024";
const USERNAME = "admin";
const PASSWORD = "marketprism2024!";

// API Key认证
async function getAlertsWithApiKey() {
    try {
        const response = await fetch(`${BASE_URL}/api/v1/alerts`, {
            headers: {
                "X-API-Key": API_KEY,
                "Content-Type": "application/json"
            }
        });
        
        if (response.ok) {
            return await response.json();
        } else {
            console.error(`Error: ${response.status} - ${response.statusText}`);
            return null;
        }
    } catch (error) {
        console.error("Request failed:", error);
        return null;
    }
}

// Basic Auth认证
async function getAlertsWithBasicAuth() {
    const credentials = btoa(`${USERNAME}:${PASSWORD}`);
    
    try {
        const response = await fetch(`${BASE_URL}/api/v1/alerts`, {
            headers: {
                "Authorization": `Basic ${credentials}`,
                "Content-Type": "application/json"
            }
        });
        
        if (response.ok) {
            return await response.json();
        } else {
            console.error(`Error: ${response.status} - ${response.statusText}`);
            return null;
        }
    } catch (error) {
        console.error("Request failed:", error);
        return null;
    }
}

// 使用示例
(async () => {
    // 使用API Key
    const alerts1 = await getAlertsWithApiKey();
    if (alerts1) {
        console.log(`Found ${alerts1.total} alerts`);
    }
    
    // 使用Basic Auth
    const alerts2 = await getAlertsWithBasicAuth();
    if (alerts2) {
        console.log(`Found ${alerts2.total} alerts`);
    }
})();
```

### Shell脚本示例

```bash
#!/bin/bash

# 配置
BASE_URL="http://localhost:8082"
API_KEY="mp-monitoring-key-2024"
USERNAME="admin"
PASSWORD="marketprism2024!"

# API Key认证函数
get_alerts_with_api_key() {
    curl -s -H "X-API-Key: $API_KEY" \
         -H "Content-Type: application/json" \
         "$BASE_URL/api/v1/alerts" | jq '.'
}

# Basic Auth认证函数
get_alerts_with_basic_auth() {
    curl -s -u "$USERNAME:$PASSWORD" \
         -H "Content-Type: application/json" \
         "$BASE_URL/api/v1/alerts" | jq '.'
}

# 健康检查函数
check_health() {
    curl -s "$BASE_URL/health" | jq '.status'
}

# 获取指标函数
get_metrics() {
    curl -s -H "X-API-Key: $API_KEY" \
         "$BASE_URL/metrics"
}

# 使用示例
echo "=== 健康检查 ==="
check_health

echo -e "\n=== 使用API Key获取告警 ==="
get_alerts_with_api_key

echo -e "\n=== 使用Basic Auth获取告警 ==="
get_alerts_with_basic_auth

echo -e "\n=== 获取Prometheus指标 ==="
get_metrics | head -10
```

## 📊 性能测试示例

### 并发测试

```bash
#!/bin/bash

# 并发性能测试
API_KEY="mp-monitoring-key-2024"
BASE_URL="http://localhost:8082"

echo "🚀 MarketPrism API性能测试"
echo "========================="

# 单次请求测试
echo "1. 单次请求响应时间:"
time curl -s -H "X-API-Key: $API_KEY" \
          "$BASE_URL/api/v1/alerts" > /dev/null

# 并发请求测试
echo -e "\n2. 并发请求测试 (10个并发):"
time for i in {1..10}; do
    curl -s -H "X-API-Key: $API_KEY" \
         "$BASE_URL/api/v1/alerts" > /dev/null &
done
wait

# 压力测试
echo -e "\n3. 压力测试 (100个请求):"
time for i in {1..100}; do
    curl -s -H "X-API-Key: $API_KEY" \
         "$BASE_URL/health" > /dev/null
done

echo -e "\n✅ 性能测试完成"
```

---

**使用建议**:
- 生产环境优先使用API Key认证
- 调试时可以使用Basic Auth认证
- 定期轮换认证凭据
- 监控认证失败率

**技术支持**: 如有API使用问题，请参考错误处理部分或联系系统管理员
