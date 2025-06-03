#!/usr/bin/env python3
"""
简化的代理配置调试测试

检查代理配置是否正确加载
"""

import os
import yaml
from pathlib import Path
import subprocess


def load_config_file(config_path: str) -> dict:
    """加载YAML配置文件"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"❌ 加载配置文件失败: {e}")
        return {}


def test_proxy_configuration():
    """测试代理配置"""
    print("🔧 代理配置调试测试")
    print("=" * 50)
    
    # 项目根目录
    project_root = Path(__file__).parent
    
    # 1. 测试主配置文件
    main_config_path = project_root / "config" / "collector_config.yaml"
    print(f"📁 主配置文件: {main_config_path}")
    
    if main_config_path.exists():
        main_config = load_config_file(main_config_path)
        proxy_config = main_config.get('proxy', {})
        
        print(f"✅ 主配置加载成功")
        print(f"🔄 代理配置:")
        print(f"   - 启用: {proxy_config.get('enabled', False)}")
        print(f"   - REST API HTTP: {proxy_config.get('rest_api', {}).get('http_proxy', 'None')}")
        print(f"   - REST API HTTPS: {proxy_config.get('rest_api', {}).get('https_proxy', 'None')}")
        print(f"   - WebSocket SOCKS: {proxy_config.get('websocket', {}).get('socks_proxy', 'None')}")
        print(f"   - 排除地址: {proxy_config.get('no_proxy', 'None')}")
        print(f"   - 兼容HTTP: {proxy_config.get('http_proxy', 'None')}")
        print(f"   - 兼容HTTPS: {proxy_config.get('https_proxy', 'None')}")
    else:
        print(f"❌ 主配置文件不存在")
        return
    
    print()
    
    # 2. 测试交易所配置文件
    exchanges_config_dir = project_root / "config" / "exchanges"
    exchange_files = ['binance_futures.yaml', 'okx.yaml', 'deribit.yaml']
    
    for exchange_file in exchange_files:
        exchange_path = exchanges_config_dir / exchange_file
        print(f"📁 {exchange_file}: {exchange_path}")
        
        if exchange_path.exists():
            exchange_config = load_config_file(exchange_path)
            
            # 检查是否有代理配置
            if 'proxy' in exchange_config:
                print(f"   ⚠️  交易所配置文件中发现代理配置（应该移除）")
                print(f"       代理配置: {exchange_config['proxy']}")
            else:
                print(f"   ✅ 无代理配置（正确）")
        else:
            print(f"   ❌ 文件不存在")
    
    print()
    
    # 3. 检查环境变量
    print("🌍 环境变量检查:")
    env_vars = ['http_proxy', 'HTTP_PROXY', 'https_proxy', 'HTTPS_PROXY', 
                'ALL_PROXY', 'all_proxy', 'SOCKS_PROXY', 'socks_proxy']
    
    for var in env_vars:
        value = os.getenv(var)
        if value:
            print(f"   ✅ {var}={value}")
        else:
            print(f"   - {var}=未设置")
    
    print()
    
    # 4. 检查SOCKS代理支持
    print("📦 SOCKS代理支持检查:")
    try:
        import aiohttp_socks
        print(f"   ✅ aiohttp_socks已安装: {aiohttp_socks.__version__}")
    except ImportError:
        print(f"   ❌ aiohttp_socks未安装 - 无法使用SOCKS代理")
        print(f"   💡 安装命令: pip install aiohttp_socks")
    
    print()
    
    # 5. 测试网络连通性
    print("🌐 网络连通性测试:")
    
    # 测试代理端口
    proxy_ports = [1087, 1080]  # 更新为用户实际的代理端口
    for port in proxy_ports:
        # 使用Python的socket检查
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            
            if result == 0:
                print(f"   ✅ 端口 {port} 可访问")
            else:
                print(f"   ❌ 端口 {port} 不可访问")
        except Exception as e:
            print(f"   ❓ 端口 {port} 检查失败: {e}")
    
    print()
    
    # 6. 模拟代理配置应用
    print("🔧 模拟代理配置应用:")
    
    if proxy_config.get('enabled', False):
        print("   ✅ 代理已启用")
        
        # WebSocket代理
        ws_proxy = proxy_config.get('websocket', {}).get('socks_proxy')
        if ws_proxy:
            print(f"   📡 WebSocket SOCKS代理: {ws_proxy}")
        else:
            print(f"   ❌ WebSocket SOCKS代理未配置")
        
        # REST API代理
        rest_http = proxy_config.get('rest_api', {}).get('http_proxy')
        rest_https = proxy_config.get('rest_api', {}).get('https_proxy')
        if rest_http or rest_https:
            print(f"   🌐 REST API HTTP代理: {rest_http}")
            print(f"   🌐 REST API HTTPS代理: {rest_https}")
        else:
            print(f"   ❌ REST API代理未配置")
    else:
        print("   ❌ 代理未启用")


def main():
    """主函数"""
    print("🚀 MarketPrism 代理配置调试")
    print("=" * 60)
    
    # 测试配置
    test_proxy_configuration()
    
    print()
    print("🏁 调试完成")
    print("=" * 60)
    
    # 提供建议
    print("\\n💡 建议:")
    print("1. 如果代理服务器未启动，请启动代理服务")
    print("2. 如果需要SOCKS代理，请安装: pip install aiohttp_socks")
    print("3. 确认代理配置正确，端口可访问")
    print("4. 如果不使用代理，可以在配置中禁用: proxy.enabled = false")
    print("5. 如果端口不可访问，但想测试直连，请临时禁用代理")


if __name__ == "__main__":
    main()