#!/usr/bin/env python3
"""
MarketPrism 监控告警服务启动脚本 - 重构版本
专注于核心功能，为Grafana提供数据源支持
"""

import sys
import asyncio
import logging
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 配置基础日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def create_default_config():
    """创建默认配置"""
    return {
        'server': {
            'host': '0.0.0.0',
            'port': 8082
        },
        'alert_rules': {
            'evaluation_interval': 60,
            'default_severity': 'medium'
        },
        'anomaly_detection': {
            'statistical_window': 100,
            'statistical_threshold': 2.0,
            'seasonal_window': 1440,
            'seasonal_period': 1440
        },
        'failure_prediction': {
            'prediction_interval': 300,
            'confidence_threshold': 0.8
        },
        'notifications': {
            'enabled': True,
            'channels': {
                'email': {
                    'enabled': False,
                    'smtp_server': 'localhost',
                    'smtp_port': 587
                },
                'webhook': {
                    'enabled': True,
                    'url': 'http://localhost:8080/webhook'
                }
            }
        }
    }

async def main():
    """主函数"""
    try:
        logger.info("启动MarketPrism监控告警服务...")
        
        # 尝试加载配置
        try:
            from config.unified_config_loader import UnifiedConfigLoader
            config_loader = UnifiedConfigLoader()
            config = config_loader.load_service_config('monitoring-alerting-service')
            logger.info("使用统一配置加载器加载配置")
        except Exception as e:
            logger.warning(f"无法加载统一配置，使用默认配置: {e}")
            config = create_default_config()
        
        # 导入重构后的服务类
        from main import MonitoringAlertingService

        # 创建服务实例
        service = MonitoringAlertingService(config)

        # 启动服务
        host = config.get('server', {}).get('host', '0.0.0.0')
        port = config.get('server', {}).get('port', 8082)

        logger.info(f"MarketPrism监控告警服务将在 {host}:{port} 启动")
        logger.info("重构版本 - 专注于核心功能，为Grafana提供数据源支持")

        # 启动服务（新版本的start方法包含了所有初始化逻辑）
        await service.start(host, port)
        
    except KeyboardInterrupt:
        logger.info("服务被用户中断")
    except Exception as e:
        logger.error(f"服务启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(main())
