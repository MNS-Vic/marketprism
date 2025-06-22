#!/usr/bin/env python3
"""
MarketPrism告警系统测试脚本
验证生产级告警系统的功能和性能
"""

import asyncio
import sys
import time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.alerting.marketprism_alert_rules import setup_marketprism_alerting

async def test_alerting_system():
    """测试告警系统"""
    print("🚨 开始测试MarketPrism告警系统...")
    
    # 设置告警系统
    alerting_system = setup_marketprism_alerting()
    await alerting_system.start()
    
    print(f"✅ 告警系统已启动，共配置 {len(alerting_system.rules)} 个告警规则")
    
    # 模拟各种场景的指标数据
    test_scenarios = [
        {
            "name": "正常运行状态",
            "metrics": {
                'service_up': 1,
                'binance_connection_status': 1,
                'okx_connection_status': 1,
                'api_response_time_ms': 300,
                'api_error_rate_percent': 2,
                'memory_usage_percent': 45,
                'cpu_usage_percent': 30,
                'disk_usage_percent': 60
            }
        },
        {
            "name": "OKX连接问题",
            "metrics": {
                'service_up': 1,
                'binance_connection_status': 1,
                'okx_connection_status': 0,  # OKX连接失败
                'api_response_time_ms': 500,
                'api_error_rate_percent': 5,
                'memory_usage_percent': 50,
                'cpu_usage_percent': 35
            }
        },
        {
            "name": "高负载状态",
            "metrics": {
                'service_up': 1,
                'binance_connection_status': 1,
                'okx_connection_status': 1,
                'api_response_time_ms': 6000,  # 响应时间过慢
                'api_error_rate_percent': 15,  # 错误率过高
                'memory_usage_percent': 85,    # 内存使用率高
                'cpu_usage_percent': 90        # CPU使用率高
            }
        },
        {
            "name": "系统故障",
            "metrics": {
                'service_up': 0,  # 服务不可用
                'active_exchange_connections': 0,  # 所有交易所连接中断
                'database_connection_status': 0,   # 数据库连接失败
                'api_response_time_ms': 0,
                'api_error_rate_percent': 100,
                'memory_usage_percent': 95,
                'cpu_usage_percent': 95
            }
        }
    ]
    
    # 测试每个场景
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n📊 测试场景 {i}: {scenario['name']}")
        print("-" * 50)
        
        # 评估告警规则
        alerts = await alerting_system.evaluate_rules(scenario['metrics'])
        
        if alerts:
            print(f"🚨 触发了 {len(alerts)} 个告警:")
            for alert in alerts:
                priority_icon = {
                    'critical': '🔴',
                    'high': '🟠', 
                    'medium': '🟡',
                    'low': '🔵'
                }.get(alert.priority.value, '⚪')
                
                print(f"  {priority_icon} [{alert.priority.value.upper()}] {alert.rule_name}")
                print(f"     📝 {alert.summary}")
                print(f"     📊 当前值: {alert.current_value}, 阈值: {alert.threshold}")
        else:
            print("✅ 未触发告警，系统状态正常")
        
        # 处理告警
        await alerting_system.process_alerts(alerts)
        
        # 等待一下再测试下一个场景
        await asyncio.sleep(1)
    
    # 显示统计信息
    print(f"\n📈 告警系统统计信息:")
    stats = alerting_system.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # 显示活跃告警
    active_alerts = list(alerting_system.active_alerts.values())
    if active_alerts:
        print(f"\n🔥 当前活跃告警 ({len(active_alerts)} 个):")
        for alert in active_alerts:
            print(f"  - {alert.rule_name} ({alert.priority.value}): {alert.summary}")
    else:
        print("\n✅ 当前无活跃告警")
    
    # 停止告警系统
    await alerting_system.stop()
    print("\n🛑 告警系统测试完成")

def main():
    """主函数"""
    try:
        asyncio.run(test_alerting_system())
        print("\n🎉 告警系统测试成功完成！")
        return 0
    except Exception as e:
        print(f"\n❌ 告警系统测试失败: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
