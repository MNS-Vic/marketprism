# MarketPrism监控告警服务 - 认证机制说明文档

**文档版本**: v2.1.0  
**更新日期**: 2025-06-27  
**适用版本**: MarketPrism v2.1.0-secure-v2及以上

## 📋 概述

MarketPrism监控告警服务提供了双重认证机制，确保API访问的安全性。本文档详细说明了两种认证方式的配置、使用方法和最佳实践。

## 🔐 支持的认证方式

### 1. API Key认证

**描述**: 基于HTTP头的API密钥认证，适用于服务间通信和自动化脚本。

**安全级别**: ⭐⭐⭐⭐ (高)  
**适用场景**: 
- 服务间API调用
- 自动化监控脚本
- CI/CD流水线集成
- Prometheus数据抓取

**配置方法**:
```bash
# 环境变量配置
MONITORING_API_KEY=mp-monitoring-key-2024
```

**使用方法**:
```bash
# HTTP头方式
curl -H "X-API-Key: mp-monitoring-key-2024" \
     http://localhost:8082/api/v1/alerts

# 查询参数方式（不推荐用于生产环境）
curl "http://localhost:8082/api/v1/alerts?api_key=mp-monitoring-key-2024"
```

**优点**:
- ✅ 简单易用，适合自动化
- ✅ 无需Base64编码
- ✅ 支持HTTP头和查询参数两种方式
- ✅ 便于日志记录和审计

**缺点**:
- ⚠️ 密钥泄露风险较高
- ⚠️ 无用户身份区分
- ⚠️ 查询参数方式可能被日志记录

### 2. Basic Auth认证

**描述**: 标准HTTP基础认证，基于用户名和密码，适用于人工访问和管理操作。

**安全级别**: ⭐⭐⭐⭐⭐ (最高)  
**适用场景**:
- 管理员手动操作
- 调试和故障排除
- 临时访问需求
- 与现有认证系统集成

**配置方法**:
```bash
# 环境变量配置
MONITORING_USERNAME=admin
MONITORING_PASSWORD=marketprism2024!
```

**使用方法**:
```bash
# curl命令
curl -u admin:marketprism2024! \
     http://localhost:8082/api/v1/alerts

# 或使用Authorization头
curl -H "Authorization: Basic YWRtaW46bWFya2V0cHJpc20yMDI0IQ==" \
     http://localhost:8082/api/v1/alerts
```

**优点**:
- ✅ 标准HTTP认证协议
- ✅ 支持用户身份识别
- ✅ 密码可以定期更换
- ✅ 与现有系统兼容性好

**缺点**:
- ⚠️ 需要Base64编码（虽然不是加密）
- ⚠️ 密码管理复杂度较高
- ⚠️ 不适合高频自动化调用

## 🔄 认证方式对比

| 特性 | API Key认证 | Basic Auth认证 |
|------|-------------|----------------|
| **安全级别** | 高 | 最高 |
| **使用复杂度** | 简单 | 中等 |
| **自动化友好** | 优秀 | 良好 |
| **用户识别** | 无 | 有 |
| **密钥轮换** | 简单 | 复杂 |
| **审计能力** | 基础 | 详细 |
| **标准兼容** | 自定义 | HTTP标准 |

## 🚫 公开端点（无需认证）

以下端点无需认证即可访问：

```bash
# 根路径 - 服务信息
GET /

# 健康检查
GET /health

# 就绪检查  
GET /ready
```

**示例**:
```bash
# 无需认证的健康检查
curl http://localhost:8082/health

# 返回示例
{
  "status": "healthy",
  "version": "2.1.0-secure-v2",
  "timestamp": "2025-06-27T23:45:00.000Z",
  "security": {
    "auth_enabled": true,
    "auth_attempts": 25,
    "auth_failures": 3
  }
}
```

## 🛡️ 受保护端点（需要认证）

以下端点需要认证才能访问：

```bash
# API端点
GET /api/v1/alerts      # 告警列表
GET /api/v1/rules       # 规则列表  
GET /api/v1/status      # 服务状态
GET /api/v1/version     # 版本信息
GET /metrics            # Prometheus指标
POST /login             # 登录接口
```

## ❌ 认证失败处理

### 常见错误响应

**1. 无认证信息**
```bash
# 请求
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

**2. 错误的API Key**
```bash
# 请求
curl -H "X-API-Key: wrong-key" http://localhost:8082/api/v1/alerts

# 响应  
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "error": "Authentication required",
  "message": "Use X-API-Key header or Basic Auth"
}
```

**3. 错误的用户名密码**
```bash
# 请求
curl -u admin:wrongpass http://localhost:8082/api/v1/alerts

# 响应
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="MarketPrism Monitoring"
Content-Type: application/json

{
  "error": "Authentication required", 
  "message": "Use X-API-Key header or Basic Auth"
}
```

## 🔧 故障排除指南

### 问题1: API Key认证失败

**症状**: 使用API Key时返回401错误

**排查步骤**:
1. 检查API Key是否正确
```bash
# 检查环境变量
echo $MONITORING_API_KEY

# 检查容器环境变量
docker exec marketprism-monitoring env | grep MONITORING_API_KEY
```

2. 检查HTTP头格式
```bash
# 正确格式
curl -H "X-API-Key: mp-monitoring-key-2024" http://localhost:8082/api/v1/alerts

# 错误格式（注意大小写）
curl -H "x-api-key: mp-monitoring-key-2024" http://localhost:8082/api/v1/alerts
```

3. 检查服务日志
```bash
# 查看认证相关日志
docker logs marketprism-monitoring | grep -i auth
```

### 问题2: Basic Auth认证失败

**症状**: 使用用户名密码时返回401错误

**排查步骤**:
1. 验证用户名密码
```bash
# 检查配置
docker exec marketprism-monitoring env | grep MONITORING_USERNAME
docker exec marketprism-monitoring env | grep MONITORING_PASSWORD
```

2. 测试Base64编码
```bash
# 手动编码验证
echo -n "admin:marketprism2024!" | base64
# 应该输出: YWRtaW46bWFya2V0cHJpc20yMDI0IQ==

# 使用编码后的值
curl -H "Authorization: Basic YWRtaW46bWFya2V0cHJpc20yMDI0IQ==" \
     http://localhost:8082/api/v1/alerts
```

### 问题3: 认证配置未生效

**症状**: 认证似乎被绕过或不工作

**排查步骤**:
1. 检查认证是否启用
```bash
# 检查AUTH_ENABLED环境变量
docker exec marketprism-monitoring env | grep AUTH_ENABLED

# 检查服务状态
curl http://localhost:8082/health | jq '.security.auth_enabled'
```

2. 重启服务应用配置
```bash
# 重启容器
docker restart marketprism-monitoring

# 或重新部署
docker-compose -f docker-compose.production.yml restart monitoring-service
```

### 问题4: 认证性能问题

**症状**: 认证响应缓慢

**排查步骤**:
1. 检查认证统计
```bash
# 查看认证指标
curl -H "X-API-Key: mp-monitoring-key-2024" \
     http://localhost:8082/api/v1/status | jq '.security'
```

2. 监控认证性能
```bash
# 测试认证响应时间
time curl -H "X-API-Key: mp-monitoring-key-2024" \
          http://localhost:8082/api/v1/alerts > /dev/null
```

## 📊 认证统计和监控

### 认证指标

系统提供以下认证相关指标：

```bash
# 查看认证统计
curl -H "X-API-Key: mp-monitoring-key-2024" \
     http://localhost:8082/api/v1/status

# 响应示例
{
  "security": {
    "authentication": "enabled",
    "auth_attempts": 150,
    "auth_failures": 12
  }
}
```

### Prometheus指标

```bash
# 认证尝试总数
marketprism_auth_attempts_total

# 认证失败总数  
marketprism_auth_failures_total
```

## 🔒 安全建议

### API Key安全
1. **定期轮换**: 建议每90天更换API Key
2. **环境隔离**: 不同环境使用不同的API Key
3. **最小权限**: 仅授予必要的访问权限
4. **安全存储**: 使用环境变量或密钥管理系统

### Basic Auth安全
1. **强密码策略**: 使用复杂密码，包含大小写字母、数字和特殊字符
2. **定期更换**: 建议每30-60天更换密码
3. **访问审计**: 定期检查认证日志
4. **HTTPS传输**: 生产环境必须使用HTTPS

### 通用安全
1. **网络隔离**: 限制服务访问的网络范围
2. **日志监控**: 监控异常认证活动
3. **告警设置**: 设置认证失败率告警
4. **备份认证**: 准备应急访问方案

---

**文档维护**: 请在认证配置变更时及时更新本文档  
**技术支持**: 如有问题请查看故障排除指南或联系系统管理员
