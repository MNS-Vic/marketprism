#!/usr/bin/env python3
"""
简化的MarketPrism启动测试脚本
用于验证系统基本功能
"""

import asyncio
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

print(f"🔧 项目根目录: {project_root}")
print(f"🔧 Python路径: {sys.path[:3]}")

try:
    print("📦 导入基础模块...")
    import structlog
    import yaml
    print("✅ 基础模块导入成功")
    
    print("📦 导入MarketPrism模块...")
    from core.config.unified_config_manager import UnifiedConfigManager
    from services.data_collector.unified_data_collector import UnifiedDataCollector
    print("✅ MarketPrism模块导入成功")
    
    async def test_startup():
        """测试启动流程"""
        print("🚀 开始启动测试...")
        
        # 配置文件路径
        config_path = project_root / "config" / "collector" / "unified_data_collection.yaml"
        print(f"📄 配置文件: {config_path}")
        
        if not config_path.exists():
            print(f"❌ 配置文件不存在: {config_path}")
            return False
            
        # 创建收集器
        print("🔧 创建数据收集器...")
        collector = UnifiedDataCollector(config_path=str(config_path), mode='launcher')
        
        # 尝试启动
        print("🚀 启动数据收集器...")
        success = await collector.start()
        
        if success:
            print("✅ 数据收集器启动成功！")
            print("⏱️  运行30秒进行测试...")
            await asyncio.sleep(30)
            
            print("🛑 停止数据收集器...")
            await collector.stop()
            print("✅ 测试完成")
            return True
        else:
            print("❌ 数据收集器启动失败")
            return False
    
    if __name__ == "__main__":
        print("🎯 开始MarketPrism功能验证测试")
        result = asyncio.run(test_startup())
        if result:
            print("🎉 测试成功完成！")
            sys.exit(0)
        else:
            print("💥 测试失败")
            sys.exit(1)
            
except ImportError as e:
    print(f"❌ 模块导入失败: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ 启动失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
