#!/usr/bin/env python3
import os
import sys
sys.path.append('/Users/yao/Documents/GitHub/marketprism')

print("🔧 代理配置调试")
print("=" * 30)

# 环境变量
env_http = os.getenv('http_proxy')
env_https = os.getenv('https_proxy')
print(f"环境变量:")
print(f"  http_proxy: {env_http}")
print(f"  https_proxy: {env_https}")

# 降级处理模拟
class NetworkConfig:
    @classmethod
    def get_proxy_url(cls):
        http_proxy = os.getenv('HTTP_PROXY') or os.getenv('http_proxy')
        https_proxy = os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')
        return https_proxy or http_proxy

fallback_proxy = NetworkConfig.get_proxy_url()
print(f"降级处理代理: {fallback_proxy}")

# 测试结果
print(f"\n📊 对比结果:")
print(f"  简单测试用: {env_https}")
print(f"  适配器用: {fallback_proxy}")
print(f"  是否相同: {env_https == fallback_proxy}") 