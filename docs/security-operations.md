# MarketPrism监控告警服务 - 安全运维文档

**文档版本**: v2.1.0  
**更新日期**: 2025-06-27  
**适用版本**: MarketPrism v2.1.0-secure-v2及以上

## 📋 概述

本文档详细说明了MarketPrism监控告警服务的安全运维流程，包括认证日志监控、安全事件分析、威胁响应和日常安全维护操作。

## 📊 认证日志监控和分析

### 1. 认证指标监控

#### Prometheus指标查询

```bash
# 认证尝试总数
curl -s "http://localhost:9090/api/v1/query?query=marketprism_auth_attempts_total"

# 认证失败总数
curl -s "http://localhost:9090/api/v1/query?query=marketprism_auth_failures_total"

# 认证失败率（5分钟内）
curl -s "http://localhost:9090/api/v1/query?query=rate(marketprism_auth_failures_total[5m])"

# 认证成功率
curl -s "http://localhost:9090/api/v1/query?query=(rate(marketprism_auth_attempts_total[5m]) - rate(marketprism_auth_failures_total[5m])) / rate(marketprism_auth_attempts_total[5m]) * 100"
```

#### 实时监控脚本

```bash
#!/bin/bash
# auth-monitoring.sh

# 配置
MARKETPRISM_URL="http://localhost:8082"
API_KEY="mp-monitoring-key-2024"
ALERT_THRESHOLD=10  # 5分钟内失败次数阈值

# 获取认证统计
get_auth_stats() {
    curl -s -H "X-API-Key: $API_KEY" \
         "$MARKETPRISM_URL/api/v1/status" | \
         jq '.security'
}

# 检查认证异常
check_auth_anomalies() {
    local stats=$(get_auth_stats)
    local attempts=$(echo "$stats" | jq '.auth_attempts')
    local failures=$(echo "$stats" | jq '.auth_failures')
    
    echo "📊 认证统计 ($(date))"
    echo "总尝试次数: $attempts"
    echo "失败次数: $failures"
    
    if [ "$failures" -gt "$ALERT_THRESHOLD" ]; then
        echo "🚨 警告: 认证失败次数过多 ($failures > $ALERT_THRESHOLD)"
        return 1
    else
        echo "✅ 认证状态正常"
        return 0
    fi
}

# 主循环
while true; do
    check_auth_anomalies
    echo "---"
    sleep 300  # 5分钟检查一次
done
```

### 2. 日志分析

#### 认证日志格式

MarketPrism认证日志包含以下信息：
```json
{
  "timestamp": "2025-06-27T23:45:00.000Z",
  "level": "INFO",
  "event": "auth_attempt",
  "method": "api_key",
  "source_ip": "192.168.1.100",
  "user_agent": "curl/7.68.0",
  "endpoint": "/api/v1/alerts",
  "result": "success",
  "duration_ms": 5
}
```

#### 日志分析脚本

```bash
#!/bin/bash
# analyze-auth-logs.sh

LOG_FILE="/var/log/marketprism/auth.log"
REPORT_FILE="/tmp/auth-analysis-$(date +%Y%m%d).txt"

echo "🔍 MarketPrism认证日志分析报告" > "$REPORT_FILE"
echo "生成时间: $(date)" >> "$REPORT_FILE"
echo "=================================" >> "$REPORT_FILE"

# 统计认证方法使用情况
echo -e "\n📊 认证方法统计:" >> "$REPORT_FILE"
grep "auth_attempt" "$LOG_FILE" | \
    jq -r '.method' | \
    sort | uniq -c | \
    sort -nr >> "$REPORT_FILE"

# 统计失败的IP地址
echo -e "\n🚨 认证失败IP统计:" >> "$REPORT_FILE"
grep "auth_attempt.*failed" "$LOG_FILE" | \
    jq -r '.source_ip' | \
    sort | uniq -c | \
    sort -nr | head -10 >> "$REPORT_FILE"

# 统计访问的端点
echo -e "\n🎯 访问端点统计:" >> "$REPORT_FILE"
grep "auth_attempt" "$LOG_FILE" | \
    jq -r '.endpoint' | \
    sort | uniq -c | \
    sort -nr >> "$REPORT_FILE"

# 时间分布分析
echo -e "\n⏰ 认证时间分布:" >> "$REPORT_FILE"
grep "auth_attempt" "$LOG_FILE" | \
    jq -r '.timestamp' | \
    cut -d'T' -f2 | \
    cut -d':' -f1 | \
    sort | uniq -c >> "$REPORT_FILE"

echo "✅ 分析报告已生成: $REPORT_FILE"
cat "$REPORT_FILE"
```

### 3. 异常检测

#### 自动异常检测脚本

```python
#!/usr/bin/env python3
# auth-anomaly-detection.py

import requests
import json
import time
from datetime import datetime, timedelta
from collections import defaultdict

class AuthAnomalyDetector:
    def __init__(self, marketprism_url, api_key):
        self.marketprism_url = marketprism_url
        self.api_key = api_key
        self.baseline_failure_rate = 0.05  # 5%基线失败率
        self.ip_attempt_threshold = 50     # 单IP尝试次数阈值
        
    def get_auth_stats(self):
        """获取认证统计"""
        try:
            response = requests.get(
                f"{self.marketprism_url}/api/v1/status",
                headers={"X-API-Key": self.api_key},
                timeout=10
            )
            return response.json().get("security", {})
        except Exception as e:
            print(f"获取认证统计失败: {e}")
            return {}
    
    def detect_high_failure_rate(self, stats):
        """检测高失败率"""
        attempts = stats.get("auth_attempts", 0)
        failures = stats.get("auth_failures", 0)
        
        if attempts > 0:
            failure_rate = failures / attempts
            if failure_rate > self.baseline_failure_rate:
                return {
                    "type": "high_failure_rate",
                    "severity": "warning",
                    "message": f"认证失败率过高: {failure_rate:.2%}",
                    "details": {
                        "attempts": attempts,
                        "failures": failures,
                        "failure_rate": failure_rate
                    }
                }
        return None
    
    def detect_brute_force(self, stats):
        """检测暴力破解攻击"""
        failures = stats.get("auth_failures", 0)
        
        # 简单的暴力破解检测：短时间内大量失败
        if failures > 100:  # 假设这是累计值
            return {
                "type": "potential_brute_force",
                "severity": "critical",
                "message": f"检测到潜在暴力破解攻击: {failures}次失败",
                "details": {
                    "failures": failures
                }
            }
        return None
    
    def run_detection(self):
        """运行异常检测"""
        print(f"🔍 开始异常检测 - {datetime.now()}")
        
        stats = self.get_auth_stats()
        if not stats:
            print("❌ 无法获取认证统计")
            return
        
        anomalies = []
        
        # 检测高失败率
        high_failure = self.detect_high_failure_rate(stats)
        if high_failure:
            anomalies.append(high_failure)
        
        # 检测暴力破解
        brute_force = self.detect_brute_force(stats)
        if brute_force:
            anomalies.append(brute_force)
        
        # 报告异常
        if anomalies:
            print("🚨 检测到安全异常:")
            for anomaly in anomalies:
                print(f"  - {anomaly['message']} (严重级别: {anomaly['severity']})")
        else:
            print("✅ 未检测到异常")
        
        return anomalies

def main():
    detector = AuthAnomalyDetector(
        "http://localhost:8082",
        "mp-monitoring-key-2024"
    )
    
    # 持续监控
    while True:
        try:
            anomalies = detector.run_detection()
            
            # 如果检测到严重异常，可以触发告警
            critical_anomalies = [a for a in (anomalies or []) if a['severity'] == 'critical']
            if critical_anomalies:
                print("🚨 触发紧急告警!")
                # 这里可以集成告警系统
            
            time.sleep(300)  # 5分钟检查一次
            
        except KeyboardInterrupt:
            print("\n⏹️ 停止监控")
            break
        except Exception as e:
            print(f"❌ 监控异常: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
```

## 🚨 安全事件响应流程

### 1. 事件分类

#### 安全事件级别定义

| 级别 | 描述 | 响应时间 | 处理流程 |
|------|------|----------|----------|
| **P1 - 紧急** | 服务完全不可用、数据泄露 | 15分钟 | 立即响应 |
| **P2 - 高** | 认证系统异常、暴力破解 | 1小时 | 快速响应 |
| **P3 - 中** | 异常访问模式、配置问题 | 4小时 | 标准响应 |
| **P4 - 低** | 日常安全事件、预防性维护 | 24小时 | 计划响应 |

### 2. 事件响应手册

#### P1级事件响应

```bash
#!/bin/bash
# p1-incident-response.sh

echo "🚨 P1级安全事件响应"
echo "=================="

# 1. 立即隔离
echo "1. 服务隔离..."
docker-compose -f docker-compose.production.yml stop monitoring-service
echo "✅ 监控服务已停止"

# 2. 保存现场
echo "2. 保存现场数据..."
INCIDENT_DIR="/tmp/incident-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$INCIDENT_DIR"

# 保存日志
cp -r /var/log/marketprism/ "$INCIDENT_DIR/logs/"
docker logs marketprism-monitoring > "$INCIDENT_DIR/container-logs.txt"

# 保存配置
cp .env "$INCIDENT_DIR/"
cp docker-compose.production.yml "$INCIDENT_DIR/"

# 保存系统状态
docker ps -a > "$INCIDENT_DIR/docker-status.txt"
netstat -tulpn > "$INCIDENT_DIR/network-status.txt"

echo "✅ 现场数据已保存到: $INCIDENT_DIR"

# 3. 通知相关人员
echo "3. 发送紧急通知..."
# 这里集成告警系统
echo "📧 请手动通知安全团队和运维团队"

# 4. 初步分析
echo "4. 初步分析..."
echo "请检查以下内容:"
echo "- 认证日志异常"
echo "- 网络连接异常"
echo "- 系统资源使用"
echo "- 容器状态异常"

echo "🎯 P1事件响应完成，等待进一步指示"
```

#### P2级事件响应

```bash
#!/bin/bash
# p2-incident-response.sh

echo "⚠️ P2级安全事件响应"
echo "=================="

API_KEY="mp-monitoring-key-2024"
MARKETPRISM_URL="http://localhost:8082"

# 1. 评估威胁
echo "1. 威胁评估..."
auth_stats=$(curl -s -H "X-API-Key: $API_KEY" \
                  "$MARKETPRISM_URL/api/v1/status" | \
                  jq '.security')

echo "认证统计: $auth_stats"

failures=$(echo "$auth_stats" | jq '.auth_failures')
if [ "$failures" -gt 50 ]; then
    echo "🚨 检测到高认证失败率: $failures"
    
    # 2. 临时防护措施
    echo "2. 实施临时防护..."
    
    # 可以考虑临时禁用某些功能或加强认证
    echo "建议措施:"
    echo "- 更换API Key"
    echo "- 加强密码策略"
    echo "- 启用IP白名单"
    
else
    echo "✅ 认证失败率在正常范围内"
fi

# 3. 详细调查
echo "3. 开始详细调查..."
echo "检查项目:"
echo "- 异常IP地址访问"
echo "- 认证方法使用模式"
echo "- 时间分布异常"

echo "🎯 P2事件响应完成"
```

### 3. 自动化响应

#### 自动威胁响应脚本

```python
#!/usr/bin/env python3
# automated-threat-response.py

import requests
import json
import time
import subprocess
from datetime import datetime

class ThreatResponseSystem:
    def __init__(self, marketprism_url, api_key):
        self.marketprism_url = marketprism_url
        self.api_key = api_key
        self.response_actions = {
            "high_failure_rate": self.handle_high_failure_rate,
            "brute_force": self.handle_brute_force,
            "service_down": self.handle_service_down
        }
    
    def get_service_status(self):
        """获取服务状态"""
        try:
            response = requests.get(
                f"{self.marketprism_url}/health",
                timeout=10
            )
            return response.status_code == 200
        except:
            return False
    
    def handle_high_failure_rate(self, details):
        """处理高认证失败率"""
        print("🔧 处理高认证失败率...")
        
        # 记录事件
        self.log_security_event("high_failure_rate", details)
        
        # 可以实施的自动化措施：
        # 1. 发送告警
        self.send_alert("认证失败率过高", details)
        
        # 2. 如果失败率极高，考虑临时限制
        failure_rate = details.get("failure_rate", 0)
        if failure_rate > 0.5:  # 50%以上失败率
            print("⚠️ 失败率极高，建议人工介入")
            return "manual_intervention_required"
        
        return "handled"
    
    def handle_brute_force(self, details):
        """处理暴力破解攻击"""
        print("🛡️ 处理暴力破解攻击...")
        
        # 记录事件
        self.log_security_event("brute_force", details)
        
        # 自动化防护措施
        # 1. 立即告警
        self.send_alert("检测到暴力破解攻击", details)
        
        # 2. 可以考虑临时措施（需要谨慎）
        failures = details.get("failures", 0)
        if failures > 200:
            print("🚨 暴力破解攻击严重，建议立即人工介入")
            return "critical_intervention_required"
        
        return "handled"
    
    def handle_service_down(self, details):
        """处理服务下线"""
        print("🔄 处理服务下线...")
        
        # 记录事件
        self.log_security_event("service_down", details)
        
        # 尝试自动恢复
        try:
            subprocess.run([
                "docker", "restart", "marketprism-monitoring"
            ], check=True)
            
            # 等待服务恢复
            time.sleep(30)
            
            if self.get_service_status():
                print("✅ 服务自动恢复成功")
                return "recovered"
            else:
                print("❌ 自动恢复失败")
                return "recovery_failed"
                
        except Exception as e:
            print(f"❌ 自动恢复异常: {e}")
            return "recovery_error"
    
    def log_security_event(self, event_type, details):
        """记录安全事件"""
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "details": details,
            "response_action": "automated"
        }
        
        # 写入安全事件日志
        with open("/var/log/marketprism/security-events.log", "a") as f:
            f.write(json.dumps(event) + "\n")
    
    def send_alert(self, message, details):
        """发送告警"""
        print(f"📧 发送告警: {message}")
        # 这里可以集成实际的告警系统
        # 例如：Slack、邮件、PagerDuty等
    
    def process_threat(self, threat_type, details):
        """处理威胁"""
        if threat_type in self.response_actions:
            return self.response_actions[threat_type](details)
        else:
            print(f"⚠️ 未知威胁类型: {threat_type}")
            return "unknown_threat"

def main():
    response_system = ThreatResponseSystem(
        "http://localhost:8082",
        "mp-monitoring-key-2024"
    )
    
    print("🤖 自动威胁响应系统启动")
    
    # 示例：处理高失败率威胁
    threat_details = {
        "failure_rate": 0.3,
        "attempts": 100,
        "failures": 30
    }
    
    result = response_system.process_threat("high_failure_rate", threat_details)
    print(f"处理结果: {result}")

if __name__ == "__main__":
    main()
```

## 🔧 日常安全维护

### 1. 定期安全检查

#### 每日安全检查清单

```bash
#!/bin/bash
# daily-security-check.sh

echo "📋 MarketPrism每日安全检查"
echo "========================="
echo "检查日期: $(date)"
echo ""

MARKETPRISM_URL="http://localhost:8082"
API_KEY="mp-monitoring-key-2024"
REPORT_FILE="/var/log/marketprism/daily-security-$(date +%Y%m%d).txt"

# 1. 服务可用性检查
echo "1. 服务可用性检查" | tee -a "$REPORT_FILE"
if curl -s "$MARKETPRISM_URL/health" > /dev/null; then
    echo "   ✅ 服务正常运行" | tee -a "$REPORT_FILE"
else
    echo "   ❌ 服务无响应" | tee -a "$REPORT_FILE"
fi

# 2. 认证状态检查
echo "2. 认证状态检查" | tee -a "$REPORT_FILE"
auth_stats=$(curl -s -H "X-API-Key: $API_KEY" \
                  "$MARKETPRISM_URL/api/v1/status" | \
                  jq '.security')

if [ "$auth_stats" != "null" ]; then
    echo "   ✅ 认证系统正常" | tee -a "$REPORT_FILE"
    echo "   认证统计: $auth_stats" | tee -a "$REPORT_FILE"
else
    echo "   ❌ 认证系统异常" | tee -a "$REPORT_FILE"
fi

# 3. 容器安全检查
echo "3. 容器安全检查" | tee -a "$REPORT_FILE"
container_status=$(docker ps --filter "name=marketprism" --format "table {{.Names}}\t{{.Status}}")
echo "$container_status" | tee -a "$REPORT_FILE"

# 4. 网络安全检查
echo "4. 网络安全检查" | tee -a "$REPORT_FILE"
open_ports=$(netstat -tulpn | grep -E ":(8082|9090|3000)" | wc -l)
echo "   开放端口数量: $open_ports" | tee -a "$REPORT_FILE"

# 5. 日志文件检查
echo "5. 日志文件检查" | tee -a "$REPORT_FILE"
log_size=$(du -sh /var/log/marketprism/ 2>/dev/null | cut -f1)
echo "   日志目录大小: ${log_size:-未知}" | tee -a "$REPORT_FILE"

echo "" | tee -a "$REPORT_FILE"
echo "✅ 每日安全检查完成" | tee -a "$REPORT_FILE"
echo "报告保存至: $REPORT_FILE"
```

### 2. 安全配置审计

#### 配置审计脚本

```bash
#!/bin/bash
# security-config-audit.sh

echo "🔍 MarketPrism安全配置审计"
echo "========================="

# 1. 环境变量安全检查
echo "1. 环境变量安全检查"
if [ -f .env ]; then
    echo "   ✅ .env文件存在"
    
    # 检查文件权限
    env_perms=$(stat -c "%a" .env)
    if [ "$env_perms" = "600" ]; then
        echo "   ✅ .env文件权限正确 ($env_perms)"
    else
        echo "   ⚠️ .env文件权限不安全 ($env_perms)，建议设置为600"
    fi
    
    # 检查必要的安全配置
    if grep -q "AUTH_ENABLED=true" .env; then
        echo "   ✅ 认证已启用"
    else
        echo "   ❌ 认证未启用"
    fi
    
else
    echo "   ❌ .env文件不存在"
fi

# 2. Docker配置安全检查
echo "2. Docker配置安全检查"
if [ -f docker-compose.production.yml ]; then
    echo "   ✅ Docker Compose配置存在"
    
    # 检查是否使用了安全的网络配置
    if grep -q "networks:" docker-compose.production.yml; then
        echo "   ✅ 使用了自定义网络"
    else
        echo "   ⚠️ 未使用自定义网络"
    fi
    
    # 检查健康检查配置
    if grep -q "healthcheck:" docker-compose.production.yml; then
        echo "   ✅ 配置了健康检查"
    else
        echo "   ⚠️ 未配置健康检查"
    fi
    
else
    echo "   ❌ Docker Compose配置不存在"
fi

# 3. 密码强度检查
echo "3. 密码强度检查"
if [ -f .env ]; then
    password=$(grep "MONITORING_PASSWORD=" .env | cut -d'=' -f2)
    password_length=${#password}
    
    if [ "$password_length" -ge 12 ]; then
        echo "   ✅ 密码长度符合要求 ($password_length 字符)"
    else
        echo "   ⚠️ 密码长度不足 ($password_length 字符)，建议至少12字符"
    fi
    
    # 检查密码复杂度
    if echo "$password" | grep -q "[A-Z]" && \
       echo "$password" | grep -q "[a-z]" && \
       echo "$password" | grep -q "[0-9]" && \
       echo "$password" | grep -q "[^A-Za-z0-9]"; then
        echo "   ✅ 密码复杂度符合要求"
    else
        echo "   ⚠️ 密码复杂度不足，建议包含大小写字母、数字和特殊字符"
    fi
fi

echo ""
echo "🎯 安全配置审计完成"
```

### 3. 安全更新和维护

#### 安全更新脚本

```bash
#!/bin/bash
# security-update.sh

echo "🔄 MarketPrism安全更新"
echo "===================="

# 1. 备份当前配置
echo "1. 备份当前配置..."
backup_dir="/backup/marketprism-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup_dir"

cp .env "$backup_dir/" 2>/dev/null || true
cp docker-compose.production.yml "$backup_dir/" 2>/dev/null || true
cp -r config/ "$backup_dir/" 2>/dev/null || true

echo "   ✅ 配置已备份到: $backup_dir"

# 2. 更新API Key
echo "2. 更新API Key..."
new_api_key="mp-$(date +%Y%m%d)-$(openssl rand -hex 16)"
sed -i "s/MONITORING_API_KEY=.*/MONITORING_API_KEY=$new_api_key/" .env
echo "   ✅ API Key已更新: $new_api_key"

# 3. 更新密码（可选）
read -p "是否更新密码? (y/N): " update_password
if [ "$update_password" = "y" ] || [ "$update_password" = "Y" ]; then
    echo "请输入新密码:"
    read -s new_password
    sed -i "s/MONITORING_PASSWORD=.*/MONITORING_PASSWORD=$new_password/" .env
    echo "   ✅ 密码已更新"
fi

# 4. 重启服务
echo "3. 重启服务..."
docker-compose -f docker-compose.production.yml restart monitoring-service
echo "   ✅ 服务已重启"

# 5. 验证更新
echo "4. 验证更新..."
sleep 10

if curl -s -H "X-API-Key: $new_api_key" \
        http://localhost:8082/health > /dev/null; then
    echo "   ✅ 新API Key验证成功"
else
    echo "   ❌ 新API Key验证失败，请检查配置"
fi

echo ""
echo "🎯 安全更新完成"
echo "新API Key: $new_api_key"
echo "请更新相关系统的认证配置"
```

---

**安全运维建议**:
- 每日执行安全检查脚本
- 每周进行配置审计
- 每月更新认证凭据
- 定期备份安全配置
- 监控异常访问模式
- 及时响应安全告警

**紧急联系**: 如发现严重安全事件，请立即联系安全团队并执行相应的事件响应流程

**文档维护**: 请在安全策略变更时及时更新本文档
