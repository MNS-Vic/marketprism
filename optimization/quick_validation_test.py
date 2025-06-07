#!/usr/bin/env python3
"""
MarketPrism 快速验证测试

验证核心优化组件是否正常工作
"""

import asyncio
import time
import sys
from pathlib import Path

# 添加项目路径
sys.path.append(str(Path(__file__).parent.parent))

from core.networking.optimized_session_manager import SessionManager, SessionConfig
from core.networking.enhanced_exchange_connector import create_exchange_connector

async def quick_validation():
    """快速验证测试"""
    print("🔍 MarketPrism 快速验证测试")
    print("=" * 40)
    
    # 测试1: 优化会话管理器
    print("📊 测试优化会话管理器...")
    try:
        session_config = SessionConfig(proxy_url="http://127.0.0.1:1087")
        manager = SessionManager(session_config)
        
        async with manager.request('GET', 'https://api.binance.com/api/v3/ping') as response:
            success = response.status == 200
            print(f"  ✅ 会话管理器: {'成功' if success else '失败'}")
        
        await manager.close()
    except Exception as e:
        print(f"  ❌ 会话管理器: {e}")
    
    # 测试2: 增强交易所连接器
    print("📊 测试增强交易所连接器...")
    try:
        connector = create_exchange_connector('binance', {
            'http_proxy': 'http://127.0.0.1:1087'
        })
        
        data = await connector.make_request('GET', '/api/v3/ping')
        print(f"  ✅ 交易所连接器: 成功")
        
        await connector.close()
    except Exception as e:
        print(f"  ❌ 交易所连接器: {e}")
    
    # 测试3: 代理配置检查
    print("📊 检查代理配置...")
    try:
        import yaml
        config_path = Path(__file__).parent.parent / "config" / "collector_config.yaml"
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        proxy_config = config.get('proxy', {})
        if proxy_config.get('enabled'):
            http_proxy = proxy_config.get('rest_api', {}).get('http_proxy')
            print(f"  ✅ 代理配置: {http_proxy}")
        else:
            print(f"  ⚠️ 代理配置: 未启用")
    except Exception as e:
        print(f"  ❌ 代理配置: {e}")
    
    print("=" * 40)
    print("🎉 验证完成！")

if __name__ == "__main__":
    asyncio.run(quick_validation())