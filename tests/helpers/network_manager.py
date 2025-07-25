"""
网络管理器 - 统一处理代理配置和交易所连通性检测
"""
from datetime import datetime, timezone
import os
import socket
import requests
import pytest
from typing import Dict, Optional
from urllib.parse import urlparse


class NetworkManager:
    """统一网络管理器 - 处理代理配置和网络依赖"""
    
    def __init__(self):
        self.proxy_config = {
            'http': os.getenv('http_proxy', 'http://127.0.0.1:1087'),
            'https': os.getenv('https_proxy', 'http://127.0.0.1:1087'),
            'socks5': os.getenv('ALL_PROXY', 'socks5://127.0.0.1:1080')
        }
        self._session = None
        
    def setup_session(self) -> requests.Session:
        """创建配置了代理的requests会话"""
        if self._session is None:
            self._session = requests.Session()
            self._session.proxies.update({
                'http': self.proxy_config['http'],
                'https': self.proxy_config['https']
            })
            self._session.timeout = 30  # 统一超时
            
            # 设置请求头
            self._session.headers.update({
                'User-Agent': 'MarketPrism-Test/1.0',
                'Accept': 'application/json'
            })
        
        return self._session
    
    def is_network_available(self, host="8.8.8.8", port=53, timeout=3) -> bool:
        """检查基础网络连接"""
        try:
            socket.create_connection((host, port), timeout=timeout)
            return True
        except OSError:
            return False
    
    def is_exchange_reachable(self, exchange='binance') -> bool:
        """检查交易所API是否可达"""
        urls = {
            'binance': 'https://api.binance.com/api/v3/ping',
            'okx': 'https://www.okx.com/api/v5/public/time', 
            'huobi': 'https://api.huobi.pro/v1/common/timestamp',
            'gate': 'https://api.gateio.ws/api/v4/spot/time'
        }
        
        if exchange not in urls:
            return False
            
        try:
            session = self.setup_session()
            response = session.get(urls[exchange], timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"交易所 {exchange} 连接失败: {e}")
            return False
    
    def test_all_exchanges(self) -> Dict[str, bool]:
        """测试所有支持的交易所连通性"""
        exchanges = ['binance', 'okx', 'huobi', 'gate']
        results = {}
        
        for exchange in exchanges:
            results[exchange] = self.is_exchange_reachable(exchange)
            
        return results
    
    def configure_proxy_env(self):
        """配置代理环境变量"""
        os.environ['http_proxy'] = self.proxy_config['http']
        os.environ['https_proxy'] = self.proxy_config['https']
        os.environ['ALL_PROXY'] = self.proxy_config['socks5']
        
        print(f"✅ 代理配置完成:")
        print(f"  ├─ HTTP: {self.proxy_config['http']}")
        print(f"  ├─ HTTPS: {self.proxy_config['https']}")
        print(f"  └─ SOCKS5: {self.proxy_config['socks5']}")
    
    def get_test_decorators(self):
        """返回网络相关的测试装饰器"""
        return {
            'requires_network': pytest.mark.skipif(
                not self.is_network_available(),
                reason="基础网络不可用"
            ),
            'requires_binance': pytest.mark.skipif(
                not self.is_exchange_reachable('binance'),
                reason="Binance API不可达，可能需要配置代理"
            ),
            'requires_okx': pytest.mark.skipif(
                not self.is_exchange_reachable('okx'),
                reason="OKX API不可达，可能需要配置代理" 
            ),
            'requires_any_exchange': pytest.mark.skipif(
                not any(self.test_all_exchanges().values()),
                reason="所有交易所API都不可达，请检查网络和代理配置"
            )
        }


# 全局网络管理器实例
network_manager = NetworkManager()

# 配置代理环境变量
network_manager.configure_proxy_env()

# 获取装饰器
decorators = network_manager.get_test_decorators()

# 导出装饰器供测试使用
requires_network = decorators['requires_network']
requires_binance = decorators['requires_binance']
requires_okx = decorators['requires_okx']
requires_any_exchange = decorators['requires_any_exchange']


def check_network_status():
    """检查网络状态并打印报告"""
    print("🌐 网络连接状态检查:")
    print(f"  ├─ 基础网络: {'✅' if network_manager.is_network_available() else '❌'}")
    
    exchange_status = network_manager.test_all_exchanges()
    print("  └─ 交易所连通性:")
    for exchange, status in exchange_status.items():
        print(f"      ├─ {exchange}: {'✅' if status else '❌'}")
    
    return exchange_status


if __name__ == "__main__":
    # 测试网络管理器
    check_network_status() 