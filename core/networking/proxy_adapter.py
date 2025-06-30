"""
MarketPrism API代理适配器

让现有代码零侵入地使用统一API代理
通过简单的装饰器和替换函数实现

使用方式：
1. 装饰器方式：@use_api_proxy
2. 替换方式：proxy_session = get_proxy_session()
3. 全局方式：enable_global_proxy()
"""

from datetime import datetime, timezone
import asyncio
import functools
import logging
from typing import Dict, Any, Optional, Callable, Union
import aiohttp
from .exchange_api_proxy import ExchangeAPIProxy, get_exchange_proxy

logger = logging.getLogger(__name__)


class ProxySession:
    """代理会话包装器，兼容aiohttp.ClientSession接口"""
    
    def __init__(self, proxy: ExchangeAPIProxy, exchange: str):
        self.proxy = proxy
        self.exchange = exchange
        self._closed = False
    
    async def request(self, method: str, url: str, **kwargs) -> "ProxyResponse":
        """发送请求（兼容aiohttp.ClientSession.request）"""
        if self._closed:
            raise RuntimeError("Session is closed")
        
        # 从URL中提取endpoint
        endpoint = self._extract_endpoint(url)
        
        # 提取参数
        params = kwargs.get('params') or kwargs.get('json') or {}
        
        # 通过代理发送请求
        response_data = await self.proxy.request(
            exchange=self.exchange,
            method=method,
            endpoint=endpoint,
            params=params
        )
        
        return ProxyResponse(response_data, 200)
    
    async def get(self, url: str, **kwargs) -> "ProxyResponse":
        """GET请求"""
        return await self.request('GET', url, **kwargs)
    
    async def post(self, url: str, **kwargs) -> "ProxyResponse":
        """POST请求"""
        return await self.request('POST', url, **kwargs)
    
    async def put(self, url: str, **kwargs) -> "ProxyResponse":
        """PUT请求"""
        return await self.request('PUT', url, **kwargs)
    
    async def delete(self, url: str, **kwargs) -> "ProxyResponse":
        """DELETE请求"""
        return await self.request('DELETE', url, **kwargs)
    
    def _extract_endpoint(self, url: str) -> str:
        """从完整URL中提取endpoint"""
        # 移除基础URL部分
        base_urls = {
            'binance': 'https://api.binance.com',
            'okx': 'https://www.okx.com', 
            'deribit': 'https://www.deribit.com'
        }
        
        base_url = base_urls.get(self.exchange.lower(), '')
        if base_url and url.startswith(base_url):
            return url[len(base_url):]
        
        # 如果不是完整URL，假设已经是endpoint
        return url if url.startswith('/') else f'/{url}'
    
    async def close(self):
        """关闭会话"""
        self._closed = True
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class ProxyResponse:
    """代理响应包装器，兼容aiohttp.ClientResponse接口"""
    
    def __init__(self, data: Dict[str, Any], status: int = 200):
        self._data = data
        self.status = status
        self.headers = {'Content-Type': 'application/json'}
    
    async def json(self) -> Dict[str, Any]:
        """获取JSON数据"""
        return self._data
    
    async def text(self) -> str:
        """获取文本数据"""
        import json
        return json.dumps(self._data)
    
    def raise_for_status(self):
        """检查状态码"""
        if self.status >= 400:
            # 创建一个简单的RequestInfo对象来避免None错误
            from aiohttp import RequestInfo
            from yarl import URL

            # 创建一个虚拟的RequestInfo对象
            request_info = RequestInfo(
                url=URL("http://proxy-adapter"),
                method="GET",
                headers={},
                real_url=URL("http://proxy-adapter")
            )

            raise aiohttp.ClientResponseError(
                request_info=request_info,
                history=(),
                status=self.status,
                message=f"HTTP {self.status}"
            )


# 装饰器
def use_api_proxy(exchange: str):
    """
    装饰器：让现有异步函数使用API代理
    
    用法：
    @use_api_proxy("binance")
    async def get_orderbook(symbol):
        # 原有代码保持不变
        pass
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 注入代理会话
            proxy = get_exchange_proxy()
            proxy_session = ProxySession(proxy, exchange)
            
            # 尝试注入到kwargs中
            if 'session' not in kwargs:
                kwargs['session'] = proxy_session
            
            try:
                return await func(*args, **kwargs)
            finally:
                await proxy_session.close()
        
        return wrapper
    return decorator


def get_proxy_session(exchange: str) -> ProxySession:
    """获取代理会话（替换aiohttp.ClientSession）"""
    proxy = get_exchange_proxy()
    return ProxySession(proxy, exchange)


# 全局代理替换
_original_client_session = None
_global_proxy_enabled = False

def enable_global_proxy():
    """启用全局代理（替换所有aiohttp.ClientSession）"""
    global _original_client_session, _global_proxy_enabled
    
    if _global_proxy_enabled:
        return
    
    # 保存原始ClientSession
    _original_client_session = aiohttp.ClientSession
    
    # 创建代理ClientSession类
    class ProxyClientSession:
        def __init__(self, *args, **kwargs):
            # 尝试从参数中检测交易所
            base_url = kwargs.get('base_url', '')
            self.exchange = self._detect_exchange_from_url(base_url)
            
            if self.exchange:
                self.proxy = get_exchange_proxy()
                self._proxy_mode = True
                logger.info(f"启用代理模式，交易所: {self.exchange}")
            else:
                # 回退到原始ClientSession
                self._original_session = _original_client_session(*args, **kwargs)
                self._proxy_mode = False
        
        def _detect_exchange_from_url(self, url: str) -> Optional[str]:
            """从URL检测交易所"""
            if 'binance' in url.lower():
                return 'binance'
            elif 'okx' in url.lower():
                return 'okx'
            elif 'deribit' in url.lower():
                return 'deribit'
            return None
        
        async def request(self, method: str, url: str, **kwargs):
            if self._proxy_mode:
                proxy_session = ProxySession(self.proxy, self.exchange)
                return await proxy_session.request(method, url, **kwargs)
            else:
                return await self._original_session.request(method, url, **kwargs)
        
        async def get(self, url: str, **kwargs):
            return await self.request('GET', url, **kwargs)
        
        async def post(self, url: str, **kwargs):
            return await self.request('POST', url, **kwargs)
        
        async def close(self):
            if not self._proxy_mode:
                await self._original_session.close()
        
        async def __aenter__(self):
            return self
        
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            await self.close()
    
    # 替换aiohttp.ClientSession
    aiohttp.ClientSession = ProxyClientSession
    _global_proxy_enabled = True
    
    logger.info("全局API代理已启用")


def disable_global_proxy():
    """禁用全局代理"""
    global _original_client_session, _global_proxy_enabled
    
    if not _global_proxy_enabled or not _original_client_session:
        return
    
    # 恢复原始ClientSession
    aiohttp.ClientSession = _original_client_session
    _global_proxy_enabled = False
    
    logger.info("全局API代理已禁用")


# 便利函数：一键启用代理
async def quick_setup_proxy(mode: str = "auto", ips: Optional[list] = None):
    """
    一键启用API代理
    
    Args:
        mode: 代理模式 ("auto", "unified", "distributed")
        ips: IP列表（distributed模式时使用）
    """
    if mode == "auto":
        proxy = ExchangeAPIProxy.auto_configure()
    elif mode == "unified":
        proxy = ExchangeAPIProxy.unified_mode(ips[0] if ips else None)
    elif mode == "distributed":
        proxy = ExchangeAPIProxy.distributed_mode(ips or [])
    else:
        raise ValueError(f"不支持的模式: {mode}")
    
    # 等待环境检测完成
    await asyncio.sleep(1)
    
    logger.info(f"API代理已启用，模式: {mode}")
    return proxy


if __name__ == "__main__":
    # 测试代码
    async def test_adapter():
        print("🔧 MarketPrism API代理适配器测试")
        print("=" * 50)
        
        # 测试1: 装饰器方式
        @use_api_proxy("binance")
        async def get_binance_time(session):
            async with session.get("/api/v3/time") as response:
                return await response.json()
        
        # 测试2: 会话替换方式
        async def test_session_replacement():
            proxy_session = get_proxy_session("binance")
            async with proxy_session as session:
                response = await session.get("/api/v3/ping")
                return await response.json()
        
        try:
            print("\n📡 测试装饰器方式...")
            result1 = await get_binance_time(session=None)
            print(f"✅ 装饰器测试成功: {result1}")
            
            print("\n📡 测试会话替换方式...")
            result2 = await test_session_replacement()
            print(f"✅ 会话替换测试成功: {result2}")
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
        
        # 测试3: 全局代理
        print("\n🌐 测试全局代理...")
        enable_global_proxy()
        
        # 这里应该自动使用代理
        try:
            async with aiohttp.ClientSession(base_url="https://api.binance.com") as session:
                async with session.get("/api/v3/ping") as response:
                    result3 = await response.json()
                    print(f"✅ 全局代理测试成功: {result3}")
        except Exception as e:
            print(f"❌ 全局代理测试失败: {e}")
        finally:
            disable_global_proxy()
        
        print("\n✅ 适配器测试完成")
    
    # 运行测试
    asyncio.run(test_adapter())