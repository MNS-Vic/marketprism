#!/usr/bin/env python3
"""
MarketPrism Python Collector 启动脚本
"""

import asyncio
import sys
import os
from pathlib import Path

# 添加src目录到Python路径
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

from marketprism_collector.config import Config
from marketprism_collector.collector import MarketDataCollector


async def main():
    """主函数"""
    try:
        # 加载配置 - 使用根目录下的config
        project_root = Path(__file__).parent.parent.parent
        config_path = project_root / "config" / "collector" / "python-collector" / "collector.yaml"
        config = Config.load_from_file(str(config_path))
        
        # 创建收集器
        collector = MarketDataCollector(config)
        
        print("🚀 启动MarketPrism Python Collector...")
        print(f"📊 监控端点: http://localhost:{config.collector.http_port}")
        print(f"🏥 健康检查: http://localhost:{config.collector.http_port}/health")
        print(f"📈 Prometheus指标: http://localhost:{config.collector.http_port}/metrics")
        print(f"📋 状态信息: http://localhost:{config.collector.http_port}/status")
        
        # 运行收集器
        await collector.run()
        
    except KeyboardInterrupt:
        print("\n👋 收到停止信号，正在关闭收集器...")
    except Exception as e:
        print(f"❌ 启动收集器失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main()) 