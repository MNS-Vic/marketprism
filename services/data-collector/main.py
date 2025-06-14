#!/usr/bin/env python3
"""
MarketPrism Data Collector Service
统一的数据采集服务，支持两种运行模式：
1. 完整模式：直接运行完整的collector（包含OrderBook Manager）
2. 微服务模式：作为微服务框架的一部分运行

使用方法：
- python main.py --mode full    # 完整模式
- python main.py --mode service # 微服务模式（默认）
"""

import asyncio
import sys
import os
import argparse
from pathlib import Path
from typing import Dict, Any, Optional
import structlog

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "services" / "data-collector" / "src"))

# 设置PYTHONPATH
data_collector_src = str(project_root / "services" / "data-collector" / "src")
current_pythonpath = os.environ.get('PYTHONPATH', '')
os.environ['PYTHONPATH'] = f"{data_collector_src}:{current_pythonpath}" if current_pythonpath else data_collector_src

async def run_full_mode():
    """运行完整模式的collector（包含OrderBook Manager）"""
    try:
        from marketprism_collector.collector import MarketDataCollector
        from marketprism_collector.config import Config
        
        print("🚀 启动完整模式的MarketPrism Data Collector...")
        print("📊 包含OrderBook Manager功能")
        print("🌐 访问地址: http://localhost:8081")
        print("🔗 OrderBook API: http://localhost:8081/api/v1/orderbook/health")
        print("=" * 50)
        
        # 加载配置
        config_path = project_root / "config" / "collector.yaml"
        print(f"📋 加载配置文件: {config_path}")
        
        if not config_path.exists():
            print(f"❌ 配置文件不存在: {config_path}")
            sys.exit(1)
        
        config = Config.load_from_file(str(config_path))
        print("✅ 配置加载成功")
        
        # 创建并启动collector
        collector = MarketDataCollector(config)
        print("✅ Collector创建成功")
        
        # 启动collector
        await collector.run()
        
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        print("请确保已正确安装依赖并设置了PYTHONPATH")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 启动错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

async def run_service_mode():
    """运行微服务模式"""
    try:
        # 导入微服务框架
        from core.service_framework import BaseService
        from marketprism_collector.collector import MarketDataCollector
        from marketprism_collector.config import Config as CollectorConfig
        from marketprism_collector.data_types import DataType, CollectorMetrics
        
        print("🚀 启动微服务模式的MarketPrism Data Collector...")
        print("🌐 访问地址: http://localhost:8081")
        print("=" * 50)
        
        # 这里可以添加微服务包装器的逻辑
        # 暂时直接运行完整模式
        await run_full_mode()
        
    except ImportError as e:
        print(f"❌ 微服务框架导入失败: {e}")
        print("降级到完整模式...")
        await run_full_mode()
    except Exception as e:
        print(f"❌ 微服务模式启动错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='MarketPrism Data Collector Service')
    parser.add_argument('--mode', choices=['full', 'service'], default='full',
                       help='运行模式: full=完整模式, service=微服务模式')
    parser.add_argument('--config', default='config/collector.yaml',
                       help='配置文件路径')
    
    args = parser.parse_args()
    
    if args.mode == 'full':
        await run_full_mode()
    else:
        await run_service_mode()

if __name__ == "__main__":
    asyncio.run(main()) 