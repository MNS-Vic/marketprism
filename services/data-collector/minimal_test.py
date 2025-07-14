#!/usr/bin/env python3
"""
最小化MarketPrism测试脚本
避免触发自动依赖安装
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

print(f"🔧 项目根目录: {project_root}")

try:
    print("📦 测试基础导入...")
    import asyncio
    import yaml
    print("✅ 基础模块导入成功")
    
    # 测试配置文件
    config_path = project_root / "config" / "collector" / "unified_data_collection.yaml"
    print(f"📄 配置文件: {config_path}")
    
    if config_path.exists():
        print("✅ 配置文件存在")
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        print(f"✅ 配置文件解析成功，包含 {len(config)} 个配置项")
    else:
        print("❌ 配置文件不存在")
        sys.exit(1)
    
    # 测试NATS连接（不启动完整系统）
    print("🔍 检查NATS服务器...")
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('localhost', 4222))
        sock.close()
        if result == 0:
            print("✅ NATS服务器可访问")
        else:
            print("⚠️  NATS服务器不可访问，但这不影响测试")
    except Exception as e:
        print(f"⚠️  NATS连接测试失败: {e}")
    
    print("🎉 基础功能验证完成！")
    print("📝 系统准备就绪，可以启动完整的数据收集器")
    
except Exception as e:
    print(f"❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
