"""
统一REST客户端模块

提供统一的REST API客户端，支持：
1. 连接池管理
2. 代理支持
3. 限流控制
4. 重试机制
5. 错误处理
6. 监控统计
"""

import asyncio
import json
import os
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List, Union, Callable
from urllib.parse import urljoin, urlparse
import structlog
import aiohttp
from aiohttp import ClientTimeout, ClientSession, TCPConnector
from dataclasses import dataclass, field

from .types import Exchange


@dataclass
class RestClientConfig:
    """REST客户端配置"""
    # 基础配置
    base_url: str
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # 连接池配置
    max_connections: int = 100
    max_connections_per_host: int = 30
    keepalive_timeout: int = 30
    
    # 限流配置
    rate_limit_per_second: Optional[float] = None
    rate_limit_per_minute: Optional[float] = None
    
    # 认证配置
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    passphrase: Optional[str] = None
    
    # 代理配置
    proxy: Optional[str] = None
    
    # 其他配置
    user_agent: str = "MarketPrism-Collector/1.0"
    verify_ssl: bool = True


@dataclass
class RequestStats:
    """请求统计"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_response_time: float = 0.0
    last_request_time: Optional[datetime] = None
    rate_limit_hits: int = 0
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests
    
    @property
    def average_response_time(self) -> float:
        """平均响应时间"""
        if self.successful_requests == 0:
            return 0.0
        return self.total_response_time / self.successful_requests


class RateLimiter:
    """限流器"""
    
    def __init__(self, per_second: Optional[float] = None, per_minute: Optional[float] = None):
        self.per_second = per_second
        self.per_minute = per_minute
        
        # 请求时间记录
        self.second_requests: List[float] = []
        self.minute_requests: List[float] = []
        
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        """获取请求许可"""
        async with self._lock:
            now = time.time()
            
            # 清理过期记录
            self._cleanup_old_requests(now)
            
            # 检查每秒限制
            if self.per_second and len(self.second_requests) >= self.per_second:
                wait_time = 1.0 - (now - self.second_requests[0])
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                    now = time.time()
                    self._cleanup_old_requests(now)
            
            # 检查每分钟限制
            if self.per_minute and len(self.minute_requests) >= self.per_minute:
                wait_time = 60.0 - (now - self.minute_requests[0])
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                    now = time.time()
                    self._cleanup_old_requests(now)
            
            # 记录请求时间
            self.second_requests.append(now)
            self.minute_requests.append(now)
    
    def _cleanup_old_requests(self, now: float):
        """清理过期的请求记录"""
        # 清理1秒前的记录
        self.second_requests = [t for t in self.second_requests if now - t < 1.0]
        # 清理1分钟前的记录
        self.minute_requests = [t for t in self.minute_requests if now - t < 60.0]


class UnifiedRestClient:
    """统一REST客户端"""
    
    def __init__(self, config: RestClientConfig, name: str = "default"):
        self.config = config
        self.name = name
        self.logger = structlog.get_logger(__name__).bind(client=name)
        
        # 会话和连接
        self.session: Optional[ClientSession] = None
        self.connector: Optional[TCPConnector] = None
        
        # 限流器
        self.rate_limiter = None
        if config.rate_limit_per_second or config.rate_limit_per_minute:
            self.rate_limiter = RateLimiter(
                per_second=config.rate_limit_per_second,
                per_minute=config.rate_limit_per_minute
            )
        
        # 统计信息
        self.stats = RequestStats()
        
        # 状态
        self.is_started = False
    
    async def start(self):
        """启动客户端"""
        if self.is_started:
            return
        
        try:
            # 获取代理设置
            proxy = self.config.proxy
            if not proxy:
                proxy = (
                    os.getenv('https_proxy') or 
                    os.getenv('HTTPS_PROXY') or 
                    os.getenv('http_proxy') or 
                    os.getenv('HTTP_PROXY')
                )
            
            if proxy:
                self.logger.info("使用代理连接", proxy=proxy)
            
            # 创建连接器
            self.connector = TCPConnector(
                limit=self.config.max_connections,
                limit_per_host=self.config.max_connections_per_host,
                ttl_dns_cache=300,
                use_dns_cache=True,
                keepalive_timeout=self.config.keepalive_timeout,
                enable_cleanup_closed=True,
                verify_ssl=self.config.verify_ssl
            )
            
            # 创建会话
            timeout = ClientTimeout(total=self.config.timeout)
            headers = {
                'User-Agent': self.config.user_agent,
                'Content-Type': 'application/json'
            }
            
            self.session = ClientSession(
                connector=self.connector,
                timeout=timeout,
                headers=headers
            )
            
            # 保存代理设置
            if proxy:
                self.session._proxy = proxy
            
            self.is_started = True
            self.logger.info("REST客户端启动成功", base_url=self.config.base_url)
            
        except Exception as e:
            self.logger.error("REST客户端启动失败", error=str(e))
            await self.stop()
            raise
    
    async def stop(self):
        """停止客户端"""
        if not self.is_started:
            return
        
        try:
            if self.session:
                await self.session.close()
            
            if self.connector:
                await self.connector.close()
            
            self.is_started = False
            self.logger.info("REST客户端已停止")
            
        except Exception as e:
            self.logger.error("停止REST客户端失败", error=str(e))
    
    async def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        auth_required: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """发送HTTP请求"""
        if not self.is_started:
            await self.start()
        
        # 限流控制
        if self.rate_limiter:
            await self.rate_limiter.acquire()
        
        # 构建完整URL
        url = urljoin(self.config.base_url, path.lstrip('/'))
        
        # 准备请求头
        request_headers = {}
        if headers:
            request_headers.update(headers)
        
        # 添加认证头
        if auth_required and self.config.api_key:
            request_headers.update(self._get_auth_headers(method, path, params, data))
        
        # 重试逻辑
        last_exception = None
        for attempt in range(self.config.max_retries + 1):
            try:
                start_time = time.time()
                
                # 发送请求
                proxy = getattr(self.session, '_proxy', None)
                async with self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=data if data else None,
                    headers=request_headers,
                    proxy=proxy,
                    **kwargs
                ) as response:
                    
                    # 记录响应时间
                    response_time = time.time() - start_time
                    
                    # 更新统计
                    self._update_stats(True, response_time)
                    
                    # 检查响应状态
                    if response.status == 429:  # 限流
                        self.stats.rate_limit_hits += 1
                        retry_after = int(response.headers.get('Retry-After', self.config.retry_delay))
                        self.logger.warning("遇到限流，等待重试", retry_after=retry_after)
                        await asyncio.sleep(retry_after)
                        continue
                    
                    response.raise_for_status()
                    
                    # 解析响应
                    content_type = response.headers.get('Content-Type', '')
                    if 'application/json' in content_type:
                        result = await response.json()
                    else:
                        text = await response.text()
                        try:
                            result = json.loads(text)
                        except json.JSONDecodeError:
                            result = {'text': text}
                    
                    self.logger.debug(
                        "请求成功",
                        method=method,
                        url=url,
                        status=response.status,
                        response_time=f"{response_time:.3f}s"
                    )
                    
                    return result
                    
            except Exception as e:
                last_exception = e
                self._update_stats(False, 0)
                
                if attempt < self.config.max_retries:
                    wait_time = self.config.retry_delay * (2 ** attempt)  # 指数退避
                    self.logger.warning(
                        "请求失败，准备重试",
                        method=method,
                        url=url,
                        attempt=attempt + 1,
                        max_retries=self.config.max_retries,
                        error=str(e),
                        wait_time=wait_time
                    )
                    await asyncio.sleep(wait_time)
                else:
                    self.logger.error(
                        "请求最终失败",
                        method=method,
                        url=url,
                        error=str(e)
                    )
        
        # 所有重试都失败了
        raise last_exception
    
    async def get(self, path: str, params: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        """GET请求"""
        return await self.request('GET', path, params=params, **kwargs)
    
    async def post(self, path: str, data: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        """POST请求"""
        return await self.request('POST', path, data=data, **kwargs)
    
    async def put(self, path: str, data: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
        """PUT请求"""
        return await self.request('PUT', path, data=data, **kwargs)
    
    async def delete(self, path: str, **kwargs) -> Dict[str, Any]:
        """DELETE请求"""
        return await self.request('DELETE', path, **kwargs)
    
    def _get_auth_headers(
        self, 
        method: str, 
        path: str, 
        params: Optional[Dict[str, Any]], 
        data: Optional[Dict[str, Any]]
    ) -> Dict[str, str]:
        """获取认证头（子类可重写）"""
        headers = {}
        
        if self.config.api_key:
            headers['X-API-KEY'] = self.config.api_key
        
        # 这里可以根据不同交易所的认证方式进行扩展
        return headers
    
    def _update_stats(self, success: bool, response_time: float):
        """更新统计信息"""
        self.stats.total_requests += 1
        self.stats.last_request_time = datetime.utcnow()
        
        if success:
            self.stats.successful_requests += 1
            self.stats.total_response_time += response_time
        else:
            self.stats.failed_requests += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'name': self.name,
            'base_url': self.config.base_url,
            'is_started': self.is_started,
            'total_requests': self.stats.total_requests,
            'successful_requests': self.stats.successful_requests,
            'failed_requests': self.stats.failed_requests,
            'success_rate': round(self.stats.success_rate * 100, 2),
            'average_response_time': round(self.stats.average_response_time, 3),
            'rate_limit_hits': self.stats.rate_limit_hits,
            'last_request_time': self.stats.last_request_time.isoformat() if self.stats.last_request_time else None
        }


class ExchangeRestClient(UnifiedRestClient):
    """交易所专用REST客户端"""
    
    def __init__(self, exchange: Exchange, config: RestClientConfig):
        super().__init__(config, name=f"{exchange.value}_rest")
        self.exchange = exchange
    
    def _get_auth_headers(
        self, 
        method: str, 
        path: str, 
        params: Optional[Dict[str, Any]], 
        data: Optional[Dict[str, Any]]
    ) -> Dict[str, str]:
        """获取交易所特定的认证头"""
        headers = {}
        
        if self.exchange == Exchange.BINANCE:
            headers.update(self._get_binance_auth_headers(method, path, params, data))
        elif self.exchange == Exchange.OKX:
            headers.update(self._get_okx_auth_headers(method, path, params, data))
        # 可以继续添加其他交易所的认证方式
        
        return headers
    
    def _get_binance_auth_headers(
        self, 
        method: str, 
        path: str, 
        params: Optional[Dict[str, Any]], 
        data: Optional[Dict[str, Any]]
    ) -> Dict[str, str]:
        """Binance认证头"""
        headers = {}
        
        if self.config.api_key:
            headers['X-MBX-APIKEY'] = self.config.api_key
        
        # 如果需要签名，可以在这里添加签名逻辑
        # 大户持仓比数据通常不需要签名
        
        return headers
    
    def _get_okx_auth_headers(
        self, 
        method: str, 
        path: str, 
        params: Optional[Dict[str, Any]], 
        data: Optional[Dict[str, Any]]
    ) -> Dict[str, str]:
        """OKX认证头"""
        headers = {}
        
        if self.config.api_key:
            headers['OK-ACCESS-KEY'] = self.config.api_key
        
        if self.config.passphrase:
            headers['OK-ACCESS-PASSPHRASE'] = self.config.passphrase
        
        # 如果需要签名，可以在这里添加签名逻辑
        # 大户持仓比数据通常不需要签名
        
        return headers


class RestClientManager:
    """REST客户端管理器"""
    
    def __init__(self):
        self.clients: Dict[str, UnifiedRestClient] = {}
        self.logger = structlog.get_logger(__name__)
    
    def create_client(self, name: str, config: RestClientConfig) -> UnifiedRestClient:
        """创建REST客户端"""
        if name in self.clients:
            raise ValueError(f"客户端 {name} 已存在")
        
        client = UnifiedRestClient(config, name)
        self.clients[name] = client
        return client
    
    def create_exchange_client(self, exchange: Exchange, config: RestClientConfig) -> ExchangeRestClient:
        """创建交易所REST客户端"""
        name = f"{exchange.value}_rest"
        if name in self.clients:
            raise ValueError(f"交易所客户端 {name} 已存在")
        
        client = ExchangeRestClient(exchange, config)
        self.clients[name] = client
        return client
    
    def get_client(self, name: str) -> Optional[UnifiedRestClient]:
        """获取REST客户端"""
        return self.clients.get(name)
    
    async def start_all(self):
        """启动所有客户端"""
        for client in self.clients.values():
            await client.start()
        
        self.logger.info("所有REST客户端已启动", count=len(self.clients))
    
    async def stop_all(self):
        """停止所有客户端"""
        for client in self.clients.values():
            await client.stop()
        
        self.logger.info("所有REST客户端已停止")
    
    def get_all_stats(self) -> Dict[str, Any]:
        """获取所有客户端统计"""
        return {
            name: client.get_stats() 
            for name, client in self.clients.items()
        }


# 全局客户端管理器实例
rest_client_manager = RestClientManager() 