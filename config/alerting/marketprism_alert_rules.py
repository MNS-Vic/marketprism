"""
MarketPrism专用告警规则配置
定义生产环境的关键告警规则，包括API连接、性能、资源使用等
"""

import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from core.observability.alerting.production_alerting_system import (
    AlertRule, AlertPriority, NotificationChannel
)

def create_marketprism_alert_rules():
    """创建MarketPrism专用告警规则"""
    
    rules = []
    
    # ==================== P1级告警（严重 - 立即响应） ====================
    
    # 1. 系统完全不可用
    rules.append(AlertRule(
        name="system_down",
        description="MarketPrism数据收集器服务完全不可用",
        priority=AlertPriority.P1,
        metric_name="service_up",
        condition="==",
        threshold=0,
        duration=60,  # 1分钟
        evaluation_interval=30,
        notification_channels=[
            NotificationChannel.EMAIL,
            NotificationChannel.SLACK,
            NotificationChannel.DINGTALK,
            NotificationChannel.LOG
        ],
        notification_interval=300,  # 5分钟重复通知
        max_notifications=20,
        summary="MarketPrism服务不可用",
        description_template="MarketPrism数据收集器服务已离线超过1分钟，当前状态: {current_value}",
        runbook_url="https://docs.marketprism.com/runbooks/system-down",
        suggested_actions=[
            "立即检查服务状态: docker-compose ps",
            "查看服务日志: docker-compose logs data-collector",
            "重启服务: docker-compose restart data-collector",
            "检查资源使用: docker stats",
            "联系运维团队"
        ]
    ))
    
    # 2. 所有交易所连接中断
    rules.append(AlertRule(
        name="all_exchanges_down",
        description="所有交易所API连接中断",
        priority=AlertPriority.P1,
        metric_name="active_exchange_connections",
        condition="==",
        threshold=0,
        duration=300,  # 5分钟
        evaluation_interval=60,
        notification_channels=[
            NotificationChannel.EMAIL,
            NotificationChannel.SLACK,
            NotificationChannel.DINGTALK
        ],
        notification_interval=600,  # 10分钟重复通知
        summary="所有交易所连接中断",
        description_template="所有交易所API连接已中断超过5分钟，当前连接数: {current_value}",
        runbook_url="https://docs.marketprism.com/runbooks/exchange-connections",
        suggested_actions=[
            "检查网络连接状态",
            "验证代理配置: config/proxy.yaml",
            "测试交易所API: python scripts/test_exchange_apis.py",
            "检查API密钥和权限",
            "联系交易所技术支持"
        ]
    ))
    
    # 3. 数据库连接失败
    rules.append(AlertRule(
        name="database_connection_failed",
        description="数据库连接失败",
        priority=AlertPriority.P1,
        metric_name="database_connection_status",
        condition="==",
        threshold=0,
        duration=120,  # 2分钟
        evaluation_interval=30,
        notification_channels=[
            NotificationChannel.EMAIL,
            NotificationChannel.SLACK,
            NotificationChannel.LOG
        ],
        notification_interval=300,
        summary="数据库连接失败",
        description_template="数据库连接已失败超过2分钟，连接状态: {current_value}",
        runbook_url="https://docs.marketprism.com/runbooks/database-issues",
        suggested_actions=[
            "检查数据库服务状态: docker-compose ps postgres",
            "查看数据库日志: docker-compose logs postgres",
            "验证数据库配置: .env文件",
            "检查磁盘空间",
            "重启数据库服务"
        ]
    ))
    
    # ==================== P2级告警（重要 - 快速响应） ====================
    
    # 4. 单个交易所连接中断
    rules.append(AlertRule(
        name="exchange_connection_down",
        description="单个交易所连接中断",
        priority=AlertPriority.P2,
        metric_name="binance_connection_status",
        condition="==",
        threshold=0,
        duration=300,  # 5分钟
        evaluation_interval=60,
        notification_channels=[
            NotificationChannel.SLACK,
            NotificationChannel.LOG
        ],
        notification_interval=900,  # 15分钟重复通知
        summary="Binance连接中断",
        description_template="Binance API连接已中断超过5分钟，连接状态: {current_value}",
        runbook_url="https://docs.marketprism.com/runbooks/exchange-specific",
        suggested_actions=[
            "检查Binance API状态",
            "验证网络连接",
            "检查API频率限制",
            "切换到备用交易所"
        ]
    ))
    
    # 5. OKX连接问题（考虑到之前的测试结果）
    rules.append(AlertRule(
        name="okx_connection_issues",
        description="OKX API连接问题",
        priority=AlertPriority.P2,
        metric_name="okx_connection_status",
        condition="==",
        threshold=0,
        duration=600,  # 10分钟
        evaluation_interval=120,
        notification_channels=[
            NotificationChannel.SLACK,
            NotificationChannel.LOG
        ],
        notification_interval=1800,  # 30分钟重复通知
        summary="OKX连接问题",
        description_template="OKX API连接存在问题，连接状态: {current_value}",
        runbook_url="https://docs.marketprism.com/runbooks/okx-connection",
        suggested_actions=[
            "检查代理配置: config/proxy.yaml",
            "运行OKX连接优化器: python scripts/okx_api_integration_optimizer.py",
            "验证网络环境",
            "使用Binance作为主要数据源"
        ]
    ))
    
    # 6. API响应时间过慢
    rules.append(AlertRule(
        name="api_response_slow",
        description="API响应时间过慢",
        priority=AlertPriority.P2,
        metric_name="api_response_time_ms",
        condition=">",
        threshold=5000,  # 5秒
        duration=300,  # 5分钟
        evaluation_interval=60,
        notification_channels=[
            NotificationChannel.SLACK,
            NotificationChannel.LOG
        ],
        notification_interval=1200,  # 20分钟重复通知
        summary="API响应时间过慢",
        description_template="API响应时间过慢，当前响应时间: {current_value}ms，阈值: {threshold}ms",
        suggested_actions=[
            "检查网络延迟",
            "验证代理配置",
            "检查交易所API状态",
            "考虑切换到更快的交易所"
        ]
    ))
    
    # 7. 错误率过高
    rules.append(AlertRule(
        name="high_error_rate",
        description="API错误率过高",
        priority=AlertPriority.P2,
        metric_name="api_error_rate_percent",
        condition=">",
        threshold=10,  # 10%
        duration=300,  # 5分钟
        evaluation_interval=60,
        notification_channels=[
            NotificationChannel.SLACK,
            NotificationChannel.EMAIL,
            NotificationChannel.LOG
        ],
        notification_interval=900,  # 15分钟重复通知
        summary="API错误率过高",
        description_template="API错误率过高，当前错误率: {current_value}%，阈值: {threshold}%",
        suggested_actions=[
            "检查API调用日志",
            "验证API密钥和权限",
            "检查频率限制设置",
            "分析错误类型和原因"
        ]
    ))
    
    # ==================== P3级告警（一般 - 正常响应） ====================
    
    # 8. 内存使用率过高
    rules.append(AlertRule(
        name="high_memory_usage",
        description="内存使用率过高",
        priority=AlertPriority.P3,
        metric_name="memory_usage_percent",
        condition=">",
        threshold=80,  # 80%
        duration=600,  # 10分钟
        evaluation_interval=120,
        notification_channels=[
            NotificationChannel.SLACK,
            NotificationChannel.LOG
        ],
        notification_interval=1800,  # 30分钟重复通知
        summary="内存使用率过高",
        description_template="内存使用率过高，当前使用率: {current_value}%，阈值: {threshold}%",
        suggested_actions=[
            "检查内存泄漏",
            "重启服务释放内存",
            "优化数据缓存策略",
            "考虑增加内存资源"
        ]
    ))
    
    # 9. CPU使用率过高
    rules.append(AlertRule(
        name="high_cpu_usage",
        description="CPU使用率过高",
        priority=AlertPriority.P3,
        metric_name="cpu_usage_percent",
        condition=">",
        threshold=85,  # 85%
        duration=600,  # 10分钟
        evaluation_interval=120,
        notification_channels=[
            NotificationChannel.SLACK,
            NotificationChannel.LOG
        ],
        notification_interval=1800,  # 30分钟重复通知
        summary="CPU使用率过高",
        description_template="CPU使用率过高，当前使用率: {current_value}%，阈值: {threshold}%",
        suggested_actions=[
            "检查CPU密集型任务",
            "优化数据处理算法",
            "考虑增加CPU资源",
            "分析性能瓶颈"
        ]
    ))
    
    # 10. 磁盘空间不足
    rules.append(AlertRule(
        name="low_disk_space",
        description="磁盘空间不足",
        priority=AlertPriority.P3,
        metric_name="disk_usage_percent",
        condition=">",
        threshold=85,  # 85%
        duration=300,  # 5分钟
        evaluation_interval=300,
        notification_channels=[
            NotificationChannel.SLACK,
            NotificationChannel.EMAIL,
            NotificationChannel.LOG
        ],
        notification_interval=3600,  # 1小时重复通知
        summary="磁盘空间不足",
        description_template="磁盘空间不足，当前使用率: {current_value}%，阈值: {threshold}%",
        suggested_actions=[
            "清理日志文件",
            "删除临时文件",
            "压缩历史数据",
            "扩展磁盘空间"
        ]
    ))
    
    # ==================== P4级告警（低级 - 延迟响应） ====================
    
    # 11. 数据延迟
    rules.append(AlertRule(
        name="data_lag",
        description="数据更新延迟",
        priority=AlertPriority.P4,
        metric_name="data_lag_seconds",
        condition=">",
        threshold=300,  # 5分钟
        duration=900,  # 15分钟
        evaluation_interval=300,
        notification_channels=[
            NotificationChannel.LOG
        ],
        notification_interval=3600,  # 1小时重复通知
        summary="数据更新延迟",
        description_template="数据更新延迟，当前延迟: {current_value}秒，阈值: {threshold}秒",
        suggested_actions=[
            "检查数据处理流程",
            "优化数据同步机制",
            "检查网络连接质量"
        ]
    ))
    
    # 12. 连接池使用率高
    rules.append(AlertRule(
        name="high_connection_pool_usage",
        description="连接池使用率过高",
        priority=AlertPriority.P4,
        metric_name="connection_pool_usage_percent",
        condition=">",
        threshold=80,  # 80%
        duration=1200,  # 20分钟
        evaluation_interval=300,
        notification_channels=[
            NotificationChannel.LOG
        ],
        notification_interval=7200,  # 2小时重复通知
        summary="连接池使用率过高",
        description_template="连接池使用率过高，当前使用率: {current_value}%，阈值: {threshold}%",
        suggested_actions=[
            "检查连接泄漏",
            "优化连接复用",
            "增加连接池大小"
        ]
    ))
    
    return rules

def setup_marketprism_alerting():
    """设置MarketPrism告警系统"""
    from core.observability.alerting.production_alerting_system import get_alerting_system
    
    # 获取告警系统
    alerting_system = get_alerting_system()
    
    # 添加所有告警规则
    rules = create_marketprism_alert_rules()
    for rule in rules:
        alerting_system.add_rule(rule)
    
    print(f"✅ 已添加 {len(rules)} 个MarketPrism告警规则")
    
    # 添加一些抑制规则（在维护期间）
    # alerting_system.add_suppression_rule(
    #     labels_filter={"component": "maintenance"},
    #     duration=3600  # 1小时
    # )
    
    return alerting_system

if __name__ == "__main__":
    # 测试告警规则配置
    alerting_system = setup_marketprism_alerting()
    
    print("\n📊 告警系统统计:")
    stats = alerting_system.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("\n🚨 已配置的告警规则:")
    for rule_name, rule in alerting_system.rules.items():
        print(f"  - {rule_name} ({rule.priority.value}): {rule.description}")
