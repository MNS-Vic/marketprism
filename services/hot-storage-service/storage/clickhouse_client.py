#!/usr/bin/env python3
"""
ClickHouse客户端优化模块
修复HTTP查询方式，增强错误处理和重试机制
"""

import aiohttp
import asyncio
from typing import Optional, Dict, Any, List, Union
import structlog
from datetime import datetime
import time
import json
import traceback
from decimal import Decimal

logger = structlog.get_logger(__name__)


class ClickHouseConnectionError(Exception):
    """ClickHouse连接错误"""
    pass


class ClickHouseQueryError(Exception):
    """ClickHouse查询错误"""
    pass


class ClickHouseClient:
    """优化的ClickHouse客户端，支持HTTP和TCP连接"""
    
    def __init__(self, 
                 host: str = "127.0.0.1",
                 http_port: int = 8123,
                 tcp_port: int = 9000,
                 database: str = "default",
                 user: str = "default",
                 password: str = "",
                 timeout: int = 30,
                 max_retries: int = 3,
                 retry_delay: float = 1.0):
        self.host = host
        self.http_port = http_port
        self.tcp_port = tcp_port
        self.database = database
        self.user = user
        self.password = password
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        self.http_url = f"http://{host}:{http_port}/"
        self.session: Optional[aiohttp.ClientSession] = None
        self.tcp_client = None
        
        # 连接状态跟踪
        self.http_available = True
        self.tcp_available = False
        self.last_health_check = 0
        self.health_check_interval = 60  # 60秒检查一次
        
        # 性能统计
        self.stats = {
            "queries_total": 0,
            "queries_success": 0,
            "queries_failed": 0,
            "avg_query_time": 0.0,
            "last_error": None,
            "last_error_time": None
        }
    
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def connect(self):
        """建立连接"""
        # 创建HTTP会话
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=20,
            ttl_dns_cache=300,
            ttl_connection_pool=300,
            keepalive_timeout=30
        )
        
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={"User-Agent": "MarketPrism-Storage/1.0"}
        )
        
        # 尝试初始化TCP客户端
        try:
            from clickhouse_driver import Client as CHClient
            self.tcp_client = CHClient(
                host=self.host,
                port=self.tcp_port,
                database=self.database,
                user=self.user,
                password=self.password,
                connect_timeout=self.timeout,
                send_receive_timeout=self.timeout
            )
            # 测试TCP连接
            await asyncio.get_event_loop().run_in_executor(
                None, self.tcp_client.execute, "SELECT 1"
            )
            self.tcp_available = True
            logger.info("ClickHouse TCP连接建立成功", 
                       host=self.host, port=self.tcp_port)
        except Exception as e:
            logger.warning("ClickHouse TCP连接失败，将使用HTTP", 
                          error=str(e))
            self.tcp_client = None
            self.tcp_available = False
        
        # 测试HTTP连接
        await self._test_http_connection()
    
    async def _test_http_connection(self):
        """测试HTTP连接"""
        try:
            result = await self._execute_http_query("SELECT 1")
            if result == "1":
                self.http_available = True
                logger.info("ClickHouse HTTP连接测试成功", 
                           url=self.http_url)
            else:
                raise ClickHouseConnectionError(f"HTTP连接测试失败: {result}")
        except Exception as e:
            self.http_available = False
            logger.error("ClickHouse HTTP连接测试失败", 
                        error=str(e), url=self.http_url)
            raise ClickHouseConnectionError(f"HTTP连接失败: {e}")
    
    async def _execute_http_query(self, query: str, params: Optional[Dict] = None) -> str:
        """执行HTTP查询（修复后的正确方式）"""
        if not self.session:
            raise ClickHouseConnectionError("HTTP会话未初始化")
        
        # 构建查询参数
        query_params = {
            "database": self.database,
        }
        if self.user:
            query_params["user"] = self.user
        if self.password:
            query_params["password"] = self.password
        if params:
            query_params.update(params)
        
        # 使用POST方式发送查询（修复关键点）
        async with self.session.post(
            self.http_url,
            params=query_params,
            data=query.encode('utf-8'),  # 查询作为body发送
            headers={"Content-Type": "text/plain; charset=utf-8"}
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise ClickHouseQueryError(
                    f"HTTP查询失败 (状态码: {response.status}): {error_text}"
                )
            
            result = await response.text()
            return result.strip()
    
    async def execute(self, query: str, params: Optional[Dict] = None) -> Union[str, List[Dict]]:
        """执行查询，自动选择最佳连接方式"""
        start_time = time.time()
        self.stats["queries_total"] += 1
        
        # 健康检查
        if time.time() - self.last_health_check > self.health_check_interval:
            await self._health_check()
        
        last_error = None
        
        # 重试机制
        for attempt in range(self.max_retries):
            try:
                # 优先使用TCP连接
                if self.tcp_available and self.tcp_client:
                    try:
                        result = await asyncio.get_event_loop().run_in_executor(
                            None, self._execute_tcp_query, query, params
                        )
                        self._update_stats(start_time, True)
                        return result
                    except Exception as e:
                        logger.warning("TCP查询失败，切换到HTTP", 
                                     error=str(e), attempt=attempt + 1)
                        self.tcp_available = False
                        last_error = e
                
                # 使用HTTP连接
                if self.http_available:
                    try:
                        result = await self._execute_http_query(query, params)
                        self._update_stats(start_time, True)
                        return result
                    except Exception as e:
                        logger.warning("HTTP查询失败", 
                                     error=str(e), attempt=attempt + 1)
                        last_error = e
                        
                        # 如果是连接错误，标记HTTP不可用
                        if "Connection" in str(e) or "timeout" in str(e).lower():
                            self.http_available = False
                
                # 如果两种连接都不可用，等待后重试
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))
                    # 重新测试连接
                    if not self.http_available:
                        try:
                            await self._test_http_connection()
                        except:
                            pass
                
            except Exception as e:
                last_error = e
                logger.error("查询执行异常", 
                           error=str(e), query=query[:100], attempt=attempt + 1)
        
        # 所有重试都失败
        self._update_stats(start_time, False, last_error)
        raise ClickHouseQueryError(f"查询失败，已重试{self.max_retries}次: {last_error}")
    
    def _execute_tcp_query(self, query: str, params: Optional[Dict] = None):
        """执行TCP查询（同步方法，在线程池中运行）"""
        if not self.tcp_client:
            raise ClickHouseConnectionError("TCP客户端未初始化")
        
        try:
            if params:
                return self.tcp_client.execute(query, params)
            else:
                return self.tcp_client.execute(query)
        except Exception as e:
            # TCP连接失败，标记为不可用
            self.tcp_available = False
            raise e
    
    async def _health_check(self):
        """健康检查"""
        self.last_health_check = time.time()
        
        # 检查HTTP连接
        if not self.http_available:
            try:
                await self._test_http_connection()
            except:
                pass
        
        # 检查TCP连接
        if not self.tcp_available and self.tcp_client:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, self.tcp_client.execute, "SELECT 1"
                )
                self.tcp_available = True
                logger.info("TCP连接恢复")
            except:
                pass
    
    def _update_stats(self, start_time: float, success: bool, error: Optional[Exception] = None):
        """更新统计信息"""
        query_time = time.time() - start_time
        
        if success:
            self.stats["queries_success"] += 1
        else:
            self.stats["queries_failed"] += 1
            self.stats["last_error"] = str(error) if error else "Unknown error"
            self.stats["last_error_time"] = datetime.now().isoformat()
        
        # 更新平均查询时间
        total_queries = self.stats["queries_success"] + self.stats["queries_failed"]
        if total_queries > 0:
            self.stats["avg_query_time"] = (
                (self.stats["avg_query_time"] * (total_queries - 1) + query_time) / total_queries
            )
    
    async def ping(self) -> bool:
        """检查连接是否正常"""
        try:
            result = await self.execute("SELECT 1")
            return str(result).strip() == "1"
        except:
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取客户端统计信息"""
        return {
            **self.stats,
            "http_available": self.http_available,
            "tcp_available": self.tcp_available,
            "connection_info": {
                "host": self.host,
                "http_port": self.http_port,
                "tcp_port": self.tcp_port,
                "database": self.database
            }
        }
    
    async def close(self):
        """关闭连接"""
        if self.session:
            await self.session.close()
            self.session = None
        
        if self.tcp_client:
            try:
                self.tcp_client.disconnect()
            except:
                pass
            self.tcp_client = None
        
        logger.info("ClickHouse客户端连接已关闭")


# 全局客户端实例
_global_client: Optional[ClickHouseClient] = None


async def get_clickhouse_client() -> ClickHouseClient:
    """获取全局ClickHouse客户端实例"""
    global _global_client

    if _global_client is None:
        import os
        _global_client = ClickHouseClient(
            host=os.getenv("CLICKHOUSE_HOST", "127.0.0.1"),
            http_port=int(os.getenv("CLICKHOUSE_HTTP_PORT", "8123")),
            tcp_port=int(os.getenv("CLICKHOUSE_TCP_PORT", "9000")),
            database=os.getenv("CLICKHOUSE_DATABASE", "marketprism_hot"),
            user=os.getenv("CLICKHOUSE_USER", "default"),
            password=os.getenv("CLICKHOUSE_PASSWORD", ""),
            timeout=int(os.getenv("CLICKHOUSE_TIMEOUT", "30")),
            max_retries=int(os.getenv("CLICKHOUSE_MAX_RETRIES", "3"))
        )
        await _global_client.connect()

    return _global_client


async def close_clickhouse_client():
    """关闭全局ClickHouse客户端"""
    global _global_client
    
    if _global_client:
        await _global_client.close()
        _global_client = None
