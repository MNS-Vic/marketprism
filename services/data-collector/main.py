#!/usr/bin/env python3
"""
MarketPrism Data Collector Service - 简化版微服务入口
功能：收集数据 → 标准化 → 推送NATS + OrderBook增量维护
"""

import asyncio
import sys
import os
import yaml
from pathlib import Path

# 添加项目路径 - 在Docker容器中调整路径
try:
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    sys.path.insert(0, '/app')
except Exception as e:
    print(f"路径配置警告: {e}")
    project_root = Path('/app')
    sys.path.insert(0, '/app')

# 导入服务类
from collector.service import DataCollectorService


async def main():
    """主函数 - 统一微服务入口"""
    try:
        print("🚀 启动MarketPrism Data Collector微服务...")
        print("📊 功能：数据收集 → 标准化 → NATS推送 + OrderBook增量维护")
        print("🌐 访问地址: http://localhost:8084")
        print("=" * 50)

        # 加载服务配置
        config_path = project_root / 'config' / 'services' / 'services.yml'
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                full_config = yaml.safe_load(f) or {}
            # 获取data-collector配置（统一使用data-collector名称）
            service_config = full_config.get('services', {}).get('data-collector', {})
        else:
            # Docker容器中使用环境变量配置
            service_config = {
                'port': int(os.getenv('API_PORT', '8084')),
                'nats_url': os.getenv('NATS_URL', 'nats://nats:4222'),
                'log_level': os.getenv('LOG_LEVEL', 'INFO')
            }
        
        # 确保端口配置
        if 'port' not in service_config:
            service_config['port'] = 8084

        print(f"📋 服务配置: {service_config}")

        # 创建并运行服务
        service = DataCollectorService(config=service_config)
        await service.run()

    except ImportError as e:
        print(f"❌ 微服务框架导入失败: {e}")
        print("请检查依赖是否正确安装")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 服务启动错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
