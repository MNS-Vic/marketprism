# MarketPrism监控告警服务 - 部署配置文档

**文档版本**: v2.1.0  
**更新日期**: 2025-06-27  
**适用版本**: MarketPrism v2.1.0-secure-v2及以上

## 📋 概述

本文档详细说明了MarketPrism监控告警服务在不同环境下的认证配置方法，包括环境变量设置、Docker部署配置和安全最佳实践。

## 🔧 环境变量配置

### 核心认证变量

```bash
# 认证开关
AUTH_ENABLED=true                    # 启用/禁用认证 (true/false)

# API Key认证
MONITORING_API_KEY=mp-monitoring-key-2024  # API密钥

# Basic Auth认证  
MONITORING_USERNAME=admin            # 用户名
MONITORING_PASSWORD=marketprism2024! # 密码

# SSL/TLS配置
SSL_ENABLED=false                    # HTTPS开关 (true/false)
```

### 完整环境变量列表

```bash
# ================================
# MarketPrism 认证配置环境变量
# ================================

# 基础配置
ENVIRONMENT=production               # 环境标识 (development/staging/production)
SERVICE_NAME=marketprism-monitoring  # 服务名称
SERVICE_VERSION=2.1.0-secure-v2     # 服务版本

# 认证配置
AUTH_ENABLED=true                    # 认证开关
MONITORING_API_KEY=mp-monitoring-key-2024    # API密钥
MONITORING_USERNAME=admin            # Basic Auth用户名
MONITORING_PASSWORD=marketprism2024! # Basic Auth密码

# 安全配置
SSL_ENABLED=false                    # SSL/TLS开关
REQUIRE_HTTPS=false                  # 强制HTTPS
RATE_LIMIT_ENABLED=true             # 速率限制
MAX_REQUESTS_PER_MINUTE=100         # 每分钟最大请求数

# 服务配置
HOST=0.0.0.0                        # 监听地址
PORT=8082                           # 监听端口
LOG_LEVEL=INFO                      # 日志级别 (DEBUG/INFO/WARNING/ERROR)

# 数据库配置 (可选)
REDIS_URL=redis://localhost:6379    # Redis连接URL
REDIS_PASSWORD=marketprism_redis_2024! # Redis密码

# 监控配置
PROMETHEUS_ENABLED=true              # Prometheus指标开关
METRICS_PATH=/metrics               # 指标路径
HEALTH_CHECK_PATH=/health           # 健康检查路径
```

## 🐳 Docker环境配置

### 1. Docker Compose配置

**文件**: `docker-compose.production.yml`

```yaml
version: '3.8'

services:
  monitoring-service:
    build: 
      context: ./services/monitoring-alerting-service
      dockerfile: Dockerfile
    container_name: marketprism-monitoring
    ports:
      - "8082:8082"
    networks:
      - monitoring-network
    environment:
      # 认证配置
      - AUTH_ENABLED=true
      - MONITORING_API_KEY=${MONITORING_API_KEY}
      - MONITORING_USERNAME=${MONITORING_USERNAME}
      - MONITORING_PASSWORD=${MONITORING_PASSWORD}
      
      # 安全配置
      - SSL_ENABLED=false
      - REQUIRE_HTTPS=false
      - RATE_LIMIT_ENABLED=true
      - MAX_REQUESTS_PER_MINUTE=100
      
      # 服务配置
      - ENVIRONMENT=production
      - LOG_LEVEL=INFO
      - HOST=0.0.0.0
      - PORT=8082
      
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8082/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped
    volumes:
      - ./logs:/app/logs
    depends_on:
      - prometheus
      - redis

networks:
  monitoring-network:
    driver: bridge
    name: marketprism-monitoring
    ipam:
      config:
        - subnet: 172.25.0.0/16
```

### 2. 环境变量文件

**文件**: `.env`

```bash
# MarketPrism生产环境配置
# 请根据实际环境修改以下配置

# ================================
# 认证配置 - 请修改为安全的值
# ================================
MONITORING_API_KEY=mp-monitoring-key-2024-CHANGE-ME
MONITORING_USERNAME=admin
MONITORING_PASSWORD=your-secure-password-here

# ================================
# 外部服务配置
# ================================
GRAFANA_ADMIN_PASSWORD=your-grafana-admin-password
REDIS_PASSWORD=your-redis-password

# ================================
# 安全配置
# ================================
AUTH_ENABLED=true
SSL_ENABLED=false
REQUIRE_HTTPS=false
RATE_LIMIT_ENABLED=true
MAX_REQUESTS_PER_MINUTE=100

# ================================
# 运行环境
# ================================
ENVIRONMENT=production
LOG_LEVEL=INFO
```

### 3. 开发环境配置

**文件**: `.env.development`

```bash
# 开发环境配置
AUTH_ENABLED=false                   # 开发环境可以禁用认证
MONITORING_API_KEY=dev-api-key
MONITORING_USERNAME=dev
MONITORING_PASSWORD=dev123
SSL_ENABLED=false
LOG_LEVEL=DEBUG
ENVIRONMENT=development
```

### 4. 生产环境配置

**文件**: `.env.production`

```bash
# 生产环境配置 - 高安全要求
AUTH_ENABLED=true                    # 生产环境必须启用认证
MONITORING_API_KEY=prod-secure-key-$(date +%Y%m%d)
MONITORING_USERNAME=admin
MONITORING_PASSWORD=Prod@MP2024!SecurePass
SSL_ENABLED=true                     # 生产环境建议启用SSL
REQUIRE_HTTPS=true
RATE_LIMIT_ENABLED=true
MAX_REQUESTS_PER_MINUTE=60          # 生产环境更严格的限制
LOG_LEVEL=INFO
ENVIRONMENT=production
```

## 🚀 部署脚本配置

### 自动化部署脚本

**文件**: `deploy-with-auth.sh`

```bash
#!/bin/bash

# MarketPrism认证配置部署脚本

set -e

echo "🔐 MarketPrism认证配置部署"
echo "========================="

# 检查必要的环境变量
check_env_vars() {
    local required_vars=(
        "MONITORING_API_KEY"
        "MONITORING_USERNAME" 
        "MONITORING_PASSWORD"
    )
    
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            echo "❌ 错误: 环境变量 $var 未设置"
            echo "请设置所有必要的认证环境变量"
            exit 1
        fi
    done
    
    echo "✅ 环境变量检查通过"
}

# 生成安全配置
generate_secure_config() {
    echo "🔧 生成安全配置..."
    
    # 生成随机API Key (如果未提供)
    if [ "$MONITORING_API_KEY" = "GENERATE" ]; then
        MONITORING_API_KEY="mp-$(date +%Y%m%d)-$(openssl rand -hex 16)"
        echo "✅ 生成新的API Key: $MONITORING_API_KEY"
    fi
    
    # 验证密码强度
    if [ ${#MONITORING_PASSWORD} -lt 12 ]; then
        echo "⚠️  警告: 密码长度少于12位，建议使用更强的密码"
    fi
    
    # 创建.env文件
    cat > .env << EOF
# MarketPrism生产环境配置 - 自动生成
# 生成时间: $(date)

MONITORING_API_KEY=$MONITORING_API_KEY
MONITORING_USERNAME=$MONITORING_USERNAME
MONITORING_PASSWORD=$MONITORING_PASSWORD
GRAFANA_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD:-admin123}
REDIS_PASSWORD=${REDIS_PASSWORD:-redis123}
AUTH_ENABLED=true
SSL_ENABLED=${SSL_ENABLED:-false}
ENVIRONMENT=production
LOG_LEVEL=INFO
EOF
    
    echo "✅ 配置文件已生成"
}

# 验证认证配置
verify_auth_config() {
    echo "🧪 验证认证配置..."
    
    # 启动服务
    docker-compose -f docker-compose.production.yml up -d
    
    # 等待服务启动
    echo "等待服务启动..."
    sleep 15
    
    # 测试无认证访问（应该失败）
    if curl -s -f http://localhost:8082/api/v1/alerts > /dev/null; then
        echo "❌ 错误: 无认证访问成功，认证配置可能有问题"
        exit 1
    else
        echo "✅ 无认证访问正确被拒绝"
    fi
    
    # 测试API Key认证
    if curl -s -f -H "X-API-Key: $MONITORING_API_KEY" \
            http://localhost:8082/api/v1/alerts > /dev/null; then
        echo "✅ API Key认证成功"
    else
        echo "❌ 错误: API Key认证失败"
        exit 1
    fi
    
    # 测试Basic Auth认证
    if curl -s -f -u "$MONITORING_USERNAME:$MONITORING_PASSWORD" \
            http://localhost:8082/api/v1/alerts > /dev/null; then
        echo "✅ Basic Auth认证成功"
    else
        echo "❌ 错误: Basic Auth认证失败"
        exit 1
    fi
    
    echo "🎉 认证配置验证成功！"
}

# 显示访问信息
show_access_info() {
    echo ""
    echo "🔗 服务访问信息"
    echo "=============="
    echo "监控服务: http://localhost:8082"
    echo "API Key: $MONITORING_API_KEY"
    echo "用户名: $MONITORING_USERNAME"
    echo "密码: $MONITORING_PASSWORD"
    echo ""
    echo "📝 使用示例:"
    echo "curl -H 'X-API-Key: $MONITORING_API_KEY' http://localhost:8082/api/v1/alerts"
    echo "curl -u '$MONITORING_USERNAME:$MONITORING_PASSWORD' http://localhost:8082/api/v1/alerts"
}

# 主函数
main() {
    check_env_vars
    generate_secure_config
    verify_auth_config
    show_access_info
}

# 执行部署
main "$@"
```

### 使用方法

```bash
# 设置环境变量
export MONITORING_API_KEY="your-secure-api-key"
export MONITORING_USERNAME="admin"
export MONITORING_PASSWORD="your-secure-password"

# 执行部署
chmod +x deploy-with-auth.sh
./deploy-with-auth.sh
```

## 🛡️ 安全最佳实践

### 1. 密码策略建议

**强密码要求**:
- 最少12个字符
- 包含大写字母、小写字母、数字和特殊字符
- 不使用常见密码或字典词汇
- 定期更换（建议30-90天）

**示例强密码**:
```bash
# 好的密码示例
MONITORING_PASSWORD="MP@2024!Secure#Pass"
MONITORING_PASSWORD="MarketPrism$2024&Monitor"
MONITORING_PASSWORD="Secure!MP#2024@Auth"

# 避免的密码示例
MONITORING_PASSWORD="123456"           # 太简单
MONITORING_PASSWORD="password"         # 常见词汇
MONITORING_PASSWORD="marketprism"      # 可预测
```

### 2. API Key安全策略

**API Key生成**:
```bash
# 生成安全的API Key
API_KEY="mp-$(date +%Y%m%d)-$(openssl rand -hex 16)"
echo "Generated API Key: $API_KEY"

# 或使用UUID
API_KEY="mp-$(uuidgen | tr '[:upper:]' '[:lower:]')"
echo "Generated API Key: $API_KEY"
```

**API Key轮换脚本**:
```bash
#!/bin/bash
# api-key-rotation.sh

OLD_KEY="$MONITORING_API_KEY"
NEW_KEY="mp-$(date +%Y%m%d)-$(openssl rand -hex 16)"

echo "🔄 API Key轮换"
echo "旧Key: $OLD_KEY"
echo "新Key: $NEW_KEY"

# 更新环境变量
sed -i "s/MONITORING_API_KEY=$OLD_KEY/MONITORING_API_KEY=$NEW_KEY/" .env

# 重启服务
docker-compose -f docker-compose.production.yml restart monitoring-service

echo "✅ API Key轮换完成"
```

### 3. 环境隔离策略

**不同环境使用不同认证配置**:

```bash
# 开发环境 - 宽松配置
AUTH_ENABLED=false
MONITORING_API_KEY=dev-key-simple

# 测试环境 - 中等安全
AUTH_ENABLED=true  
MONITORING_API_KEY=test-key-$(date +%Y%m%d)
MONITORING_PASSWORD=Test@2024

# 生产环境 - 高安全
AUTH_ENABLED=true
MONITORING_API_KEY=prod-key-$(openssl rand -hex 32)
MONITORING_PASSWORD=$(openssl rand -base64 32)
SSL_ENABLED=true
REQUIRE_HTTPS=true
```

### 4. 配置文件安全

**文件权限设置**:
```bash
# 设置.env文件权限
chmod 600 .env
chown root:root .env

# 设置配置目录权限
chmod 750 config/
chown -R root:marketprism config/
```

**敏感信息保护**:
```bash
# 使用Docker secrets (推荐)
echo "your-secure-password" | docker secret create monitoring_password -

# 在docker-compose.yml中使用
services:
  monitoring-service:
    secrets:
      - monitoring_password
    environment:
      - MONITORING_PASSWORD_FILE=/run/secrets/monitoring_password

secrets:
  monitoring_password:
    external: true
```

## 📊 配置验证

### 验证脚本

```bash
#!/bin/bash
# verify-auth-config.sh

echo "🔍 验证认证配置"
echo "==============="

# 检查环境变量
echo "1. 检查环境变量..."
required_vars=("AUTH_ENABLED" "MONITORING_API_KEY" "MONITORING_USERNAME" "MONITORING_PASSWORD")

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ $var 未设置"
    else
        echo "✅ $var 已设置"
    fi
done

# 检查服务状态
echo ""
echo "2. 检查服务状态..."
if curl -s http://localhost:8082/health > /dev/null; then
    echo "✅ 服务运行正常"
    
    # 检查认证状态
    auth_status=$(curl -s http://localhost:8082/health | jq -r '.security.auth_enabled')
    echo "✅ 认证状态: $auth_status"
else
    echo "❌ 服务无法访问"
fi

# 测试认证
echo ""
echo "3. 测试认证功能..."

# 测试无认证访问
if curl -s -f http://localhost:8082/api/v1/alerts > /dev/null 2>&1; then
    echo "❌ 无认证访问成功（应该失败）"
else
    echo "✅ 无认证访问被正确拒绝"
fi

# 测试API Key认证
if curl -s -f -H "X-API-Key: $MONITORING_API_KEY" \
        http://localhost:8082/api/v1/alerts > /dev/null 2>&1; then
    echo "✅ API Key认证成功"
else
    echo "❌ API Key认证失败"
fi

echo ""
echo "🎯 配置验证完成"
```

## 🔧 故障排除

### 常见配置问题

**1. 环境变量未生效**
```bash
# 检查容器环境变量
docker exec marketprism-monitoring env | grep MONITORING

# 重新加载配置
docker-compose -f docker-compose.production.yml restart monitoring-service
```

**2. 认证配置冲突**
```bash
# 检查多个配置文件
ls -la .env*

# 确保使用正确的配置文件
docker-compose -f docker-compose.production.yml --env-file .env.production up -d
```

**3. 权限问题**
```bash
# 检查文件权限
ls -la .env
ls -la config/

# 修复权限
chmod 600 .env
chmod -R 750 config/
```

---

**配置维护**: 请定期检查和更新认证配置  
**安全审计**: 建议每季度进行一次安全配置审计  
**技术支持**: 配置问题请参考故障排除部分或联系系统管理员
