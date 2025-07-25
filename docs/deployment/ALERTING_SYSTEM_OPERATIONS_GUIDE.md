# 🚨 MarketPrism告警系统运维手册

## 📋 概述

本手册详细说明MarketPrism生产级告警系统的运维管理，包括告警规则管理、通知渠道配置、故障排除和性能优化。

## 🏗️ 告警系统架构

### 核心组件
```
MarketPrism告警系统
├── ProductionAlertingSystem (主控制器)
├── AlertRule (告警规则定义)
├── Alert (告警实例管理)
├── NotificationChannel (通知渠道)
└── AlertPriority (优先级管理)
```

### 告警优先级体系
- **P1 (Critical)**: 严重 - 立即响应 (5分钟内)
- **P2 (High)**: 重要 - 快速响应 (30分钟内)
- **P3 (Medium)**: 一般 - 正常响应 (2小时内)
- **P4 (Low)**: 低级 - 延迟响应 (24小时内)

## 📊 告警规则管理

### 查看当前告警规则
```bash
# 查看所有告警规则
python -c "
from config.alerting.marketprism_alert_rules import setup_marketprism_alerting
alerting_system = setup_marketprism_alerting()
for name, rule in alerting_system.rules.items():
    print(f'{name}: {rule.priority.value} - {rule.description}')
"

# 查看特定优先级的规则
python -c "
from config.alerting.marketprism_alert_rules import setup_marketprism_alerting
from core.observability.alerting.production_alerting_system import AlertPriority
alerting_system = setup_marketprism_alerting()
p1_rules = [r for r in alerting_system.rules.values() if r.priority == AlertPriority.P1]
print(f'P1级告警规则数量: {len(p1_rules)}')
for rule in p1_rules:
    print(f'- {rule.name}: {rule.description}')
"
```

### 添加自定义告警规则
```python
# scripts/add_custom_alert_rule.py
from core.observability.alerting.production_alerting_system import (
    AlertRule, AlertPriority, NotificationChannel
)
from config.alerting.marketprism_alert_rules import setup_marketprism_alerting

# 创建自定义告警规则
custom_rule = AlertRule(
    name="custom_business_metric",
    description="业务指标异常告警",
    priority=AlertPriority.P2,
    metric_name="business_metric_value",
    condition=">",
    threshold=1000,
    duration=300,  # 5分钟
    notification_channels=[
        NotificationChannel.EMAIL,
        NotificationChannel.SLACK
    ],
    summary="业务指标超过阈值",
    suggested_actions=[
        "检查业务逻辑",
        "分析数据异常原因",
        "联系业务团队"
    ]
)

# 添加到告警系统
alerting_system = setup_marketprism_alerting()
alerting_system.add_rule(custom_rule)
print(f"✅ 已添加自定义告警规则: {custom_rule.name}")
```

### 修改告警阈值
```python
# scripts/update_alert_thresholds.py
from config.alerting.marketprism_alert_rules import setup_marketprism_alerting

alerting_system = setup_marketprism_alerting()

# 修改内存使用率告警阈值
if "high_memory_usage" in alerting_system.rules:
    rule = alerting_system.rules["high_memory_usage"]
    old_threshold = rule.threshold
    rule.threshold = 85  # 从80%调整到85%
    print(f"✅ 内存使用率告警阈值已从 {old_threshold}% 调整到 {rule.threshold}%")

# 修改API响应时间告警阈值
if "api_response_slow" in alerting_system.rules:
    rule = alerting_system.rules["api_response_slow"]
    old_threshold = rule.threshold
    rule.threshold = 3000  # 从5000ms调整到3000ms
    print(f"✅ API响应时间告警阈值已从 {old_threshold}ms 调整到 {rule.threshold}ms")
```

## 📢 通知渠道管理

### 配置邮件通知
```bash
# 环境变量配置
export ALERT_EMAIL_SMTP_HOST=smtp.gmail.com
export ALERT_EMAIL_SMTP_PORT=587
export ALERT_EMAIL_USERNAME=alerts@your-domain.com
export ALERT_EMAIL_PASSWORD=your_app_password
export ALERT_EMAIL_FROM=alerts@your-domain.com
export ALERT_EMAIL_TO=admin@your-domain.com,ops@your-domain.com

# 测试邮件通知
python -c "
import asyncio
from core.observability.alerting.production_alerting_system import ProductionAlertingSystem
from core.observability.alerting.production_alerting_system import Alert, AlertPriority, AlertStatus
from datetime import datetime, timezone

async def test_email():
    system = ProductionAlertingSystem()
    await system.start()
    
    # 创建测试告警
    test_alert = Alert(
        rule_name='test_email',
        priority=AlertPriority.P2,
        status=AlertStatus.FIRING,
        metric_name='test_metric',
        current_value=100,
        threshold=50,
        first_triggered=datetime.now(timezone.utc),
        last_triggered=datetime.now(timezone.utc),
        summary='邮件通知测试',
        description='这是一个测试告警，用于验证邮件通知功能'
    )
    
    # 发送测试邮件
    rule = system.rules.get('test_email')
    if rule:
        await system._send_email_notification(test_alert, rule)
    
    await system.stop()

asyncio.run(test_email())
"
```

### 配置Slack通知
```bash
# 配置Slack Webhook
export ALERT_SLACK_WEBHOOK=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK
export ALERT_SLACK_CHANNEL=#alerts

# 测试Slack通知
curl -X POST $ALERT_SLACK_WEBHOOK \
  -H 'Content-Type: application/json' \
  -d '{
    "channel": "#alerts",
    "username": "MarketPrism Alert",
    "text": "🚨 测试告警通知",
    "attachments": [{
      "color": "warning",
      "title": "告警系统测试",
      "text": "这是一个测试消息，验证Slack通知功能是否正常"
    }]
  }'
```

### 配置钉钉通知
```bash
# 配置钉钉机器人
export ALERT_DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN
export ALERT_DINGTALK_SECRET=your_secret_key

# 测试钉钉通知
python -c "
import requests
import json
import os

webhook_url = os.getenv('ALERT_DINGTALK_WEBHOOK')
payload = {
    'msgtype': 'markdown',
    'markdown': {
        'title': 'MarketPrism告警测试',
        'text': '''
**MarketPrism告警系统测试**

**告警类型**: 测试告警
**优先级**: P2 (重要)
**状态**: 测试中
**时间**: 现在

这是一个测试消息，验证钉钉通知功能是否正常。
        '''
    }
}

response = requests.post(webhook_url, json=payload)
print(f'钉钉通知测试结果: {response.status_code}')
"
```

## 🔍 告警监控和分析

### 查看活跃告警
```bash
# 查看当前活跃告警
python scripts/test_alerting_system.py

# 查看告警历史
python -c "
from config.alerting.marketprism_alert_rules import setup_marketprism_alerting
alerting_system = setup_marketprism_alerting()
stats = alerting_system.get_stats()
print(f'总告警数: {stats[\"total_alerts\"]}')
print(f'按优先级分布: {stats[\"alerts_by_priority\"]}')
print(f'通知发送数: {stats[\"notifications_sent\"]}')
"
```

### 告警统计分析
```python
# scripts/alert_analytics.py
import json
from datetime import datetime, timedelta
from config.alerting.marketprism_alert_rules import setup_marketprism_alerting

def generate_alert_report():
    alerting_system = setup_marketprism_alerting()
    
    # 获取统计信息
    stats = alerting_system.get_stats()
    
    # 生成报告
    report = {
        'report_time': datetime.now().isoformat(),
        'system_status': 'operational',
        'total_rules': len(alerting_system.rules),
        'active_alerts': len(alerting_system.active_alerts),
        'statistics': stats,
        'rule_breakdown': {}
    }
    
    # 分析规则分布
    for priority in ['critical', 'high', 'medium', 'low']:
        count = len([r for r in alerting_system.rules.values() 
                    if r.priority.value == priority])
        report['rule_breakdown'][priority] = count
    
    # 保存报告
    with open('tests/reports/alert_analytics_report.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    print("📊 告警分析报告已生成")
    return report

if __name__ == "__main__":
    report = generate_alert_report()
    print(f"告警规则总数: {report['total_rules']}")
    print(f"活跃告警数: {report['active_alerts']}")
    print(f"规则分布: {report['rule_breakdown']}")
```

## 🛠️ 故障排除

### 常见问题诊断

#### 1. 告警未触发
```bash
# 检查告警规则配置
python -c "
from config.alerting.marketprism_alert_rules import setup_marketprism_alerting
alerting_system = setup_marketprism_alerting()
rule = alerting_system.rules.get('your_rule_name')
if rule:
    print(f'规则状态: {\"启用\" if rule.enabled else \"禁用\"}')
    print(f'阈值: {rule.threshold}')
    print(f'条件: {rule.condition}')
    print(f'持续时间: {rule.duration}秒')
else:
    print('规则不存在')
"

# 手动触发告警测试
python -c "
import asyncio
from config.alerting.marketprism_alert_rules import setup_marketprism_alerting

async def test_alert():
    alerting_system = setup_marketprism_alerting()
    await alerting_system.start()
    
    # 模拟触发条件的指标
    test_metrics = {
        'memory_usage_percent': 90,  # 超过阈值
        'cpu_usage_percent': 95,     # 超过阈值
        'service_up': 0              # 服务不可用
    }
    
    alerts = await alerting_system.evaluate_rules(test_metrics)
    print(f'触发的告警数: {len(alerts)}')
    for alert in alerts:
        print(f'- {alert.rule_name}: {alert.summary}')
    
    await alerting_system.stop()

asyncio.run(test_alert())
"
```

#### 2. 通知未发送
```bash
# 检查通知配置
python -c "
from core.observability.alerting.production_alerting_system import ProductionAlertingSystem
system = ProductionAlertingSystem()
config = system.notification_config
print(f'邮件SMTP: {config.email_smtp_host}')
print(f'Slack Webhook: {bool(config.slack_webhook_url)}')
print(f'钉钉Webhook: {bool(config.dingtalk_webhook_url)}')
"

# 测试网络连接
curl -I https://hooks.slack.com
curl -I https://oapi.dingtalk.com
```

#### 3. 性能问题
```bash
# 检查告警评估性能
python -c "
import asyncio
import time
from config.alerting.marketprism_alert_rules import setup_marketprism_alerting

async def performance_test():
    alerting_system = setup_marketprism_alerting()
    await alerting_system.start()
    
    test_metrics = {'memory_usage_percent': 50}
    
    start_time = time.time()
    for i in range(100):
        await alerting_system.evaluate_rules(test_metrics)
    end_time = time.time()
    
    avg_time = (end_time - start_time) / 100
    print(f'平均评估时间: {avg_time:.4f}秒')
    
    await alerting_system.stop()

asyncio.run(performance_test())
"
```

### 日志分析
```bash
# 查看告警系统日志
grep "alerting" /var/log/marketprism/app.log | tail -50

# 查看错误日志
grep "ERROR.*alert" /var/log/marketprism/app.log

# 实时监控告警日志
tail -f /var/log/marketprism/app.log | grep "alert"
```

## 🔧 维护操作

### 定期维护任务

#### 每日检查
```bash
#!/bin/bash
# scripts/daily_alert_check.sh

echo "📅 每日告警系统检查 - $(date)"

# 1. 检查告警系统状态
python scripts/test_alerting_system.py > /tmp/alert_test.log 2>&1
if [ $? -eq 0 ]; then
    echo "✅ 告警系统功能正常"
else
    echo "❌ 告警系统存在问题，请检查日志"
    cat /tmp/alert_test.log
fi

# 2. 检查活跃告警数量
ACTIVE_ALERTS=$(python -c "
from config.alerting.marketprism_alert_rules import setup_marketprism_alerting
alerting_system = setup_marketprism_alerting()
print(len(alerting_system.active_alerts))
")

echo "📊 当前活跃告警数: $ACTIVE_ALERTS"

# 3. 检查通知渠道
if [ -n "$ALERT_SLACK_WEBHOOK" ]; then
    curl -s -o /dev/null -w "%{http_code}" $ALERT_SLACK_WEBHOOK > /tmp/slack_status
    if [ "$(cat /tmp/slack_status)" = "200" ]; then
        echo "✅ Slack通知渠道正常"
    else
        echo "❌ Slack通知渠道异常"
    fi
fi

echo "📅 每日检查完成"
```

#### 每周维护
```bash
#!/bin/bash
# scripts/weekly_alert_maintenance.sh

echo "📅 每周告警系统维护 - $(date)"

# 1. 生成告警统计报告
python scripts/alert_analytics.py

# 2. 清理过期告警历史
python -c "
from config.alerting.marketprism_alert_rules import setup_marketprism_alerting
alerting_system = setup_marketprism_alerting()
# 清理7天前的告警历史
import datetime
cutoff = datetime.datetime.now() - datetime.timedelta(days=7)
old_count = len(alerting_system.alert_history)
alerting_system.alert_history = [
    alert for alert in alerting_system.alert_history 
    if alert.first_triggered > cutoff
]
new_count = len(alerting_system.alert_history)
print(f'清理了 {old_count - new_count} 条过期告警记录')
"

# 3. 检查告警规则有效性
python -c "
from config.alerting.marketprism_alert_rules import create_marketprism_alert_rules
rules = create_marketprism_alert_rules()
print(f'✅ 告警规则配置验证通过，共 {len(rules)} 个规则')
"

echo "📅 每周维护完成"
```

### 配置备份和恢复
```bash
# 备份告警配置
cp config/alerting/marketprism_alert_rules.py config/alerting/marketprism_alert_rules.py.backup.$(date +%Y%m%d)

# 备份环境变量
env | grep ALERT_ > alert_env_backup.$(date +%Y%m%d).txt

# 恢复配置
cp config/alerting/marketprism_alert_rules.py.backup.20250621 config/alerting/marketprism_alert_rules.py
```

## 📈 性能优化

### 告警规则优化
```python
# 优化告警规则性能
def optimize_alert_rules():
    """优化告警规则配置"""
    
    # 1. 调整评估间隔
    # 对于不太重要的指标，增加评估间隔
    
    # 2. 优化阈值设置
    # 避免过于敏感的阈值导致告警风暴
    
    # 3. 合并相似告警
    # 将相关的告警合并为一个复合告警
    
    # 4. 使用告警抑制
    # 在维护期间抑制非关键告警
    
    pass
```

### 通知优化
```python
# 通知频率控制
def optimize_notifications():
    """优化通知频率和内容"""
    
    # 1. 实施告警聚合
    # 将短时间内的多个告警合并为一个通知
    
    # 2. 智能通知路由
    # 根据告警类型和时间路由到不同的通知渠道
    
    # 3. 通知内容优化
    # 提供更多上下文信息和建议操作
    
    pass
```

## 📞 支持和联系

### 紧急联系方式
- **P1级告警**: 立即电话联系 +86-xxx-xxxx-xxxx
- **P2级告警**: 30分钟内响应 alerts@your-domain.com
- **P3/P4级告警**: 工作时间响应 support@your-domain.com

### 升级流程
1. **L1支持**: 运维团队 (0-30分钟)
2. **L2支持**: 技术团队 (30分钟-2小时)
3. **L3支持**: 架构师团队 (2小时+)

### 文档和资源
- **告警规则文档**: `config/alerting/marketprism_alert_rules.py`
- **系统架构**: `core/observability/alerting/production_alerting_system.py`
- **操作脚本**: `scripts/test_alerting_system.py`
- **GitHub仓库**: https://github.com/MNS-Vic/marketprism

---

**运维手册版本**: v1.0  
**最后更新**: 2025-06-21  
**适用版本**: MarketPrism v1.0+
