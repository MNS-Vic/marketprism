# Monitoring Service

MarketPrism微服务架构的综合监控服务，提供全面的系统监控、指标收集和告警管理。

## 功能特性

### 📊 系统监控
- **资源监控**: CPU、内存、磁盘使用率实时监控
- **服务监控**: 所有微服务的健康状态跟踪
- **性能监控**: 响应时间、吞吐量、错误率统计
- **网络监控**: 连接状态和流量监控

### 🔔 告警管理
- **智能告警**: 基于阈值的智能告警规则
- **多级告警**: Warning/Critical不同级别告警
- **告警历史**: 完整的告警触发和恢复记录
- **通知集成**: 支持多种通知方式扩展

### 📈 指标收集
- **Prometheus集成**: 标准Prometheus指标格式
- **自定义指标**: 业务相关的自定义指标
- **指标聚合**: 多维度数据聚合和分析
- **数据持久化**: 指标数据的持久化存储

### 🎯 可视化监控
- **实时仪表板**: 系统状态实时显示
- **趋势分析**: 历史数据趋势分析
- **多维视图**: 不同角度的监控视图
- **交互查询**: 灵活的数据查询接口

## 快速开始

### 1. 环境准备

确保以下组件可用：
- Python 3.8+
- psutil库 (系统监控)
- prometheus_client库 (指标暴露)

### 2. 安装依赖

```bash
# 安装Python依赖
pip install psutil prometheus_client aiohttp structlog

# 可选：安装Grafana (用于可视化)
# 详见官方文档: https://grafana.com/docs/grafana/latest/installation/
```

### 3. 配置服务

编辑 `config/services.yaml`：

```yaml
monitoring-service:
  port: 8083
  check_interval: 30
  enable_alerts: true
  prometheus_port: 9090
  
  # 监控的服务列表
  monitored_services:
    market-data-collector:
      host: "localhost"
      port: 8081
      health_endpoint: "/health"
    api-gateway-service:
      host: "localhost" 
      port: 8080
      health_endpoint: "/health"
    data-storage-service:
      host: "localhost"
      port: 8082
      health_endpoint: "/health"
  
  # 告警配置
  alerting:
    email_notifications: false
    webhook_url: ""
    alert_cooldown: 300
```

### 4. 启动服务

```bash
# 直接启动
cd services/monitoring-service
python main.py

# 或使用服务管理器
cd scripts
python start_services.py --service monitoring-service
```

### 5. 验证监控

```bash
# 检查服务状态
curl http://localhost:8083/health

# 查看系统概览
curl http://localhost:8083/api/v1/overview

# 获取Prometheus指标
curl http://localhost:8083/metrics
```

## API接口

### 系统概览

```http
GET /api/v1/overview
```

返回系统整体状态概览：

```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "uptime_seconds": 3600,
  "system_resources": {
    "cpu_usage_percent": 25.5,
    "memory_usage_percent": 60.2,
    "memory_available_gb": 8.5,
    "disk_usage_percent": 45.1,
    "disk_free_gb": 120.5
  },
  "services": {
    "total": 4,
    "healthy": 3,
    "unhealthy": 1,
    "health_percentage": 75.0
  },
  "alerts": {
    "active": 2,
    "critical": 1,
    "warning": 1
  }
}
```

### 服务监控

```http
GET /api/v1/services
```

返回所有服务的健康状态和统计信息：

```json
{
  "health_status": {
    "market-data-collector": {
      "status": "healthy",
      "response_time": 0.05,
      "details": {
        "status": "healthy",
        "uptime": 3600
      }
    }
  },
  "statistics": {
    "market-data-collector": {
      "total_checks": 120,
      "healthy_checks": 118,
      "unhealthy_checks": 2,
      "uptime_percentage": 98.3,
      "avg_response_time": 0.045
    }
  }
}
```

### 服务详情

```http
GET /api/v1/services/{service_name}
```

获取指定服务的详细信息：

```json
{
  "service_name": "market-data-collector",
  "current_status": {
    "status": "healthy",
    "response_time": 0.05
  },
  "statistics": {
    "total_checks": 120,
    "healthy_checks": 118,
    "uptime_percentage": 98.3,
    "avg_response_time": 0.045,
    "last_check_time": "2024-01-01T12:00:00Z"
  }
}
```

### 告警管理

```http
GET /api/v1/alerts
```

获取活跃告警和告警历史：

```json
{
  "active_alerts": [
    {
      "rule_id": "high_cpu_usage",
      "rule_name": "High CPU Usage",
      "severity": "warning",
      "description": "CPU usage is too high",
      "start_time": "2024-01-01T11:50:00Z",
      "value": 92.5
    }
  ],
  "alert_history": [
    {
      "rule_id": "service_down",
      "rule_name": "Service Down", 
      "severity": "critical",
      "start_time": "2024-01-01T10:00:00Z",
      "end_time": "2024-01-01T10:05:00Z",
      "status": "resolved"
    }
  ]
}
```

### Prometheus指标

```http
GET /metrics
```

返回Prometheus格式的指标数据：

```
# HELP system_cpu_usage_percent System CPU usage percentage
# TYPE system_cpu_usage_percent gauge
system_cpu_usage_percent 25.5

# HELP service_status Service health status (1=healthy, 0=unhealthy)
# TYPE service_status gauge
service_status{service_name="market-data-collector"} 1

# HELP service_response_time_seconds Service response time in seconds
# TYPE service_response_time_seconds histogram
service_response_time_seconds_bucket{service_name="market-data-collector",endpoint="/health",le="0.1"} 120
```

## 监控指标

### 系统指标

| 指标名 | 类型 | 描述 |
|--------|------|------|
| `system_cpu_usage_percent` | Gauge | CPU使用率百分比 |
| `system_memory_usage_percent` | Gauge | 内存使用率百分比 |
| `system_disk_usage_percent` | Gauge | 磁盘使用率百分比 |

### 服务指标

| 指标名 | 类型 | 标签 | 描述 |
|--------|------|------|------|
| `service_status` | Gauge | service_name | 服务健康状态 |
| `service_response_time_seconds` | Histogram | service_name, endpoint | 服务响应时间 |
| `service_requests_total` | Counter | service_name, method, status | 服务请求总数 |

### 业务指标

| 指标名 | 类型 | 标签 | 描述 |
|--------|------|------|------|
| `data_processed_total` | Counter | service_name, data_type | 处理的数据总数 |
| `data_processing_errors_total` | Counter | service_name, error_type | 数据处理错误总数 |
| `active_connections` | Gauge | service_name, connection_type | 活跃连接数 |
| `message_queue_size` | Gauge | queue_name | 消息队列大小 |

## 告警规则

### 默认告警规则

#### 1. 高CPU使用率
- **条件**: CPU使用率 > 90%
- **持续时间**: 5分钟
- **严重级别**: Warning
- **描述**: 系统CPU使用率过高

#### 2. 高内存使用率
- **条件**: 内存使用率 > 95%
- **持续时间**: 5分钟
- **严重级别**: Critical
- **描述**: 系统内存使用率过高

#### 3. 服务不可用
- **条件**: 服务状态 = 0
- **持续时间**: 1分钟
- **严重级别**: Critical
- **描述**: 服务无法访问或响应异常

#### 4. 高响应时间
- **条件**: 平均响应时间 > 5秒
- **持续时间**: 3分钟
- **严重级别**: Warning
- **描述**: 服务响应时间过长

#### 5. 数据处理错误
- **条件**: 错误率 > 10%
- **持续时间**: 5分钟
- **严重级别**: Warning
- **描述**: 数据处理错误率过高

### 自定义告警规则

可以通过配置文件或API添加自定义告警规则：

```yaml
alerting:
  custom_rules:
    disk_full:
      name: "Disk Full"
      condition: "disk_usage > 90"
      threshold: 90
      duration: 600
      severity: "critical"
    
    high_error_rate:
      name: "High Error Rate"
      condition: "error_rate > 0.05"
      threshold: 0.05
      duration: 300
      severity: "warning"
```

## 与Grafana集成

### 1. 配置数据源

在Grafana中添加Prometheus数据源：
- URL: `http://localhost:8083/metrics`
- Access: `Server (Default)`

### 2. 导入仪表板

使用预定义的仪表板模板或创建自定义仪表板：

```json
{
  "dashboard": {
    "title": "MarketPrism System Overview",
    "panels": [
      {
        "title": "CPU Usage",
        "type": "singlestat",
        "targets": [
          {
            "expr": "system_cpu_usage_percent"
          }
        ]
      },
      {
        "title": "Service Health",
        "type": "table",
        "targets": [
          {
            "expr": "service_status"
          }
        ]
      }
    ]
  }
}
```

### 3. 配置告警

在Grafana中配置告警通知：
- 设置通知渠道（邮件、Slack等）
- 配置告警规则
- 设置告警阈值

## 性能优化

### 监控间隔调整

```yaml
monitoring-service:
  check_interval: 30  # 检查间隔（秒）
  alert_check_interval: 60  # 告警检查间隔（秒）
```

### 指标保留策略

```yaml
monitoring-service:
  metrics_retention_days: 30
  max_metrics_memory: "1GB"
```

### 并发优化

```yaml
monitoring-service:
  max_concurrent_checks: 10
  timeout_seconds: 5
```

## 故障排除

### 常见问题

1. **服务监控失败**
   - 检查目标服务是否运行
   - 验证健康检查端点是否可访问
   - 检查网络连接和防火墙设置

2. **指标数据异常**
   - 检查系统资源使用情况
   - 验证Prometheus客户端配置
   - 查看服务日志中的错误信息

3. **告警未触发**
   - 检查告警规则配置
   - 验证阈值设置是否合理
   - 确认告警检查循环是否正常运行

### 调试命令

```bash
# 查看服务状态
curl http://localhost:8083/api/v1/overview | jq

# 检查特定服务
curl http://localhost:8083/api/v1/services/market-data-collector | jq

# 查看活跃告警
curl http://localhost:8083/api/v1/alerts | jq '.active_alerts'

# 获取指标快照
curl http://localhost:8083/metrics | grep system_cpu
```

### 日志分析

监控服务使用结构化日志，关键信息包括：

```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "level": "WARNING",
  "logger": "monitoring-service",
  "message": "告警触发",
  "alert_id": "high_cpu_usage",
  "severity": "warning",
  "value": 92.5
}
```

## 扩展和集成

### 添加新监控指标

1. 在PrometheusManager中定义新指标
2. 在监控循环中更新指标值
3. 添加相应的告警规则

### 集成外部监控系统

- **ELK Stack**: 日志聚合和分析
- **Jaeger**: 分布式链路追踪
- **Alertmanager**: 告警路由和通知

### 云监控集成

- **AWS CloudWatch**: AWS云环境监控
- **Azure Monitor**: Azure云环境监控
- **Google Cloud Monitoring**: GCP云环境监控

## 相关服务

- **Message Broker Service**: 消息队列监控
- **Data Storage Service**: 存储服务监控
- **API Gateway Service**: 网关性能监控
- **Market Data Collector**: 数据采集监控

## 支持

如有问题或建议，请查看：
- 项目文档: `docs/monitoring/`
- Prometheus文档: https://prometheus.io/docs/
- Grafana文档: https://grafana.com/docs/
- 问题追踪: GitHub Issues