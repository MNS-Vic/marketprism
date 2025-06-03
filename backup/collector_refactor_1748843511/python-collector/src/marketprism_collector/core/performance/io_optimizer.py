"""
📡 IOOptimizer - IO优化器

网络和磁盘IO优化
提供网络优化、磁盘优化、压缩传输、协议优化等功能
"""

import asyncio
import aiofiles
import aiohttp
import time
import gzip
import brotli
import zlib
import hashlib
import os
from typing import Dict, Any, Optional, List, Callable, Union, BinaryIO, TextIO
from dataclasses import dataclass, field
from enum import Enum
import logging
from collections import defaultdict, deque
import socket
import ssl

logger = logging.getLogger(__name__)


class CompressionType(Enum):
    """压缩类型枚举"""
    NONE = "none"
    GZIP = "gzip"
    DEFLATE = "deflate"
    BROTLI = "brotli"
    LZ4 = "lz4"
    AUTO = "auto"


class IOMode(Enum):
    """IO模式枚举"""
    BLOCKING = "blocking"
    NON_BLOCKING = "non_blocking"
    ASYNC = "async"
    MEMORY_MAPPED = "memory_mapped"


class NetworkProtocol(Enum):
    """网络协议枚举"""
    HTTP_1_1 = "http/1.1"
    HTTP_2 = "http/2"
    HTTP_3 = "http/3"
    WEBSOCKET = "websocket"
    TCP = "tcp"
    UDP = "udp"


@dataclass
class IOConfig:
    """IO配置"""
    # 网络配置
    connection_timeout: float = 10.0
    read_timeout: float = 30.0
    write_timeout: float = 30.0
    max_connections: int = 100
    max_connections_per_host: int = 30
    keepalive_timeout: float = 30.0
    
    # 缓冲区配置
    read_buffer_size: int = 64 * 1024      # 64KB
    write_buffer_size: int = 64 * 1024     # 64KB
    tcp_nodelay: bool = True
    tcp_keepalive: bool = True
    
    # 压缩配置
    compression_enabled: bool = True
    compression_type: CompressionType = CompressionType.AUTO
    compression_level: int = 6
    min_compression_size: int = 1024
    
    # 磁盘IO配置
    disk_io_mode: IOMode = IOMode.ASYNC
    max_file_cache_size: int = 100
    file_buffer_size: int = 8192
    enable_sendfile: bool = True
    
    # 监控配置
    enable_metrics: bool = True
    metrics_interval: float = 60.0


@dataclass
class IOStats:
    """IO统计"""
    # 网络统计
    bytes_sent: int = 0
    bytes_received: int = 0
    requests_sent: int = 0
    responses_received: int = 0
    connection_errors: int = 0
    timeout_errors: int = 0
    
    # 磁盘统计
    files_read: int = 0
    files_written: int = 0
    disk_bytes_read: int = 0
    disk_bytes_written: int = 0
    disk_operations: int = 0
    
    # 压缩统计
    compression_ratio: float = 0.0
    compression_time: float = 0.0
    decompression_time: float = 0.0
    
    # 性能统计
    avg_response_time: float = 0.0
    avg_throughput: float = 0.0
    response_times: deque = field(default_factory=lambda: deque(maxlen=1000))


class CompressionManager:
    """压缩管理器"""
    
    def __init__(self, config: IOConfig):
        self.config = config
        self.stats = {
            "compressed_bytes": 0,
            "uncompressed_bytes": 0,
            "compression_time": 0.0,
            "decompression_time": 0.0
        }
    
    def compress(self, data: Union[str, bytes], 
                compression_type: Optional[CompressionType] = None) -> bytes:
        """压缩数据"""
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        if len(data) < self.config.min_compression_size:
            return data
        
        compression_type = compression_type or self.config.compression_type
        start_time = time.time()
        
        try:
            if compression_type == CompressionType.GZIP:
                compressed = gzip.compress(data, compresslevel=self.config.compression_level)
            elif compression_type == CompressionType.DEFLATE:
                compressed = zlib.compress(data, self.config.compression_level)
            elif compression_type == CompressionType.BROTLI:
                compressed = brotli.compress(data, quality=self.config.compression_level)
            elif compression_type == CompressionType.AUTO:
                # 自动选择最佳压缩算法
                compressed = self._auto_compress(data)
            else:
                compressed = data
            
            # 更新统计
            compression_time = time.time() - start_time
            self.stats["compressed_bytes"] += len(compressed)
            self.stats["uncompressed_bytes"] += len(data)
            self.stats["compression_time"] += compression_time
            
            return compressed
        
        except Exception as e:
            logger.error(f"压缩失败: {e}")
            return data
    
    def decompress(self, data: bytes, 
                  compression_type: CompressionType) -> bytes:
        """解压数据"""
        start_time = time.time()
        
        try:
            if compression_type == CompressionType.GZIP:
                decompressed = gzip.decompress(data)
            elif compression_type == CompressionType.DEFLATE:
                decompressed = zlib.decompress(data)
            elif compression_type == CompressionType.BROTLI:
                decompressed = brotli.decompress(data)
            else:
                decompressed = data
            
            # 更新统计
            decompression_time = time.time() - start_time
            self.stats["decompression_time"] += decompression_time
            
            return decompressed
        
        except Exception as e:
            logger.error(f"解压失败: {e}")
            return data
    
    def _auto_compress(self, data: bytes) -> bytes:
        """自动选择压缩算法"""
        # 尝试不同压缩算法，选择压缩率最高的
        compression_results = {}
        
        try:
            compression_results[CompressionType.GZIP] = gzip.compress(data, compresslevel=6)
        except:
            pass
        
        try:
            compression_results[CompressionType.DEFLATE] = zlib.compress(data, 6)
        except:
            pass
        
        try:
            compression_results[CompressionType.BROTLI] = brotli.compress(data, quality=6)
        except:
            pass
        
        if not compression_results:
            return data
        
        # 选择压缩后大小最小的
        best_type, best_result = min(compression_results.items(), key=lambda x: len(x[1]))
        return best_result
    
    def get_compression_ratio(self) -> float:
        """获取压缩比"""
        if self.stats["uncompressed_bytes"] == 0:
            return 0.0
        return self.stats["compressed_bytes"] / self.stats["uncompressed_bytes"]


class NetworkOptimizer:
    """网络优化器"""
    
    def __init__(self, config: IOConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.connection_pool: Dict[str, List[Any]] = defaultdict(list)
        self.stats = IOStats()
        
    async def start(self):
        """启动网络优化器"""
        if self.session:
            return
        
        # 创建优化的连接器
        connector = aiohttp.TCPConnector(
            limit=self.config.max_connections,
            limit_per_host=self.config.max_connections_per_host,
            ttl_dns_cache=300,
            use_dns_cache=True,
            keepalive_timeout=self.config.keepalive_timeout,
            enable_cleanup_closed=True
        )
        
        # 创建会话
        timeout = aiohttp.ClientTimeout(
            total=self.config.read_timeout,
            connect=self.config.connection_timeout
        )
        
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={'User-Agent': 'MarketPrism-IOOptimizer/1.0'}
        )
        
        logger.info("网络优化器已启动")
    
    async def stop(self):
        """停止网络优化器"""
        if self.session:
            await self.session.close()
            self.session = None
        
        logger.info("网络优化器已停止")
    
    async def request(self, method: str, url: str, **kwargs) -> aiohttp.ClientResponse:
        """优化的HTTP请求"""
        if not self.session:
            await self.start()
        
        start_time = time.time()
        
        try:
            # 添加压缩支持
            headers = kwargs.get('headers', {})
            if self.config.compression_enabled:
                headers['Accept-Encoding'] = 'gzip, deflate, br'
            kwargs['headers'] = headers
            
            response = await self.session.request(method, url, **kwargs)
            
            # 更新统计
            response_time = time.time() - start_time
            self.stats.requests_sent += 1
            self.stats.responses_received += 1
            self.stats.response_times.append(response_time)
            
            return response
        
        except asyncio.TimeoutError:
            self.stats.timeout_errors += 1
            raise
        except Exception as e:
            self.stats.connection_errors += 1
            raise
    
    async def download_file(self, url: str, file_path: str, chunk_size: int = None) -> Dict[str, Any]:
        """优化的文件下载"""
        chunk_size = chunk_size or self.config.read_buffer_size
        start_time = time.time()
        bytes_downloaded = 0
        
        async with self.request('GET', url) as response:
            response.raise_for_status()
            
            async with aiofiles.open(file_path, 'wb') as file:
                async for chunk in response.content.iter_chunked(chunk_size):
                    await file.write(chunk)
                    bytes_downloaded += len(chunk)
        
        download_time = time.time() - start_time
        throughput = bytes_downloaded / download_time if download_time > 0 else 0
        
        self.stats.bytes_received += bytes_downloaded
        
        return {
            "bytes_downloaded": bytes_downloaded,
            "download_time": download_time,
            "throughput": throughput
        }
    
    def configure_socket(self, sock: socket.socket):
        """配置socket选项"""
        # 启用TCP_NODELAY
        if self.config.tcp_nodelay:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        
        # 启用SO_KEEPALIVE
        if self.config.tcp_keepalive:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        
        # 设置缓冲区大小
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.config.read_buffer_size)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, self.config.write_buffer_size)


class DiskOptimizer:
    """磁盘优化器"""
    
    def __init__(self, config: IOConfig):
        self.config = config
        self.file_cache: Dict[str, Any] = {}
        self.stats = IOStats()
        
    async def read_file(self, file_path: str, mode: str = 'r', **kwargs) -> Union[str, bytes]:
        """优化的文件读取"""
        start_time = time.time()
        
        try:
            if self.config.disk_io_mode == IOMode.ASYNC:
                async with aiofiles.open(file_path, mode, **kwargs) as file:
                    content = await file.read()
            else:
                with open(file_path, mode, **kwargs) as file:
                    content = file.read()
            
            # 更新统计
            read_time = time.time() - start_time
            self.stats.files_read += 1
            self.stats.disk_bytes_read += len(content) if isinstance(content, (str, bytes)) else 0
            self.stats.disk_operations += 1
            
            return content
        
        except Exception as e:
            logger.error(f"文件读取失败: {file_path}, error={e}")
            raise
    
    async def write_file(self, file_path: str, content: Union[str, bytes], 
                        mode: str = 'w', **kwargs) -> Dict[str, Any]:
        """优化的文件写入"""
        start_time = time.time()
        
        try:
            if self.config.disk_io_mode == IOMode.ASYNC:
                async with aiofiles.open(file_path, mode, **kwargs) as file:
                    await file.write(content)
            else:
                with open(file_path, mode, **kwargs) as file:
                    file.write(content)
            
            # 更新统计
            write_time = time.time() - start_time
            self.stats.files_written += 1
            self.stats.disk_bytes_written += len(content) if isinstance(content, (str, bytes)) else 0
            self.stats.disk_operations += 1
            
            return {
                "bytes_written": len(content) if isinstance(content, (str, bytes)) else 0,
                "write_time": write_time
            }
        
        except Exception as e:
            logger.error(f"文件写入失败: {file_path}, error={e}")
            raise
    
    async def copy_file(self, src_path: str, dst_path: str, 
                       chunk_size: int = None) -> Dict[str, Any]:
        """优化的文件复制"""
        chunk_size = chunk_size or self.config.file_buffer_size
        start_time = time.time()
        bytes_copied = 0
        
        try:
            if self.config.disk_io_mode == IOMode.ASYNC:
                async with aiofiles.open(src_path, 'rb') as src:
                    async with aiofiles.open(dst_path, 'wb') as dst:
                        while True:
                            chunk = await src.read(chunk_size)
                            if not chunk:
                                break
                            await dst.write(chunk)
                            bytes_copied += len(chunk)
            else:
                with open(src_path, 'rb') as src:
                    with open(dst_path, 'wb') as dst:
                        while True:
                            chunk = src.read(chunk_size)
                            if not chunk:
                                break
                            dst.write(chunk)
                            bytes_copied += len(chunk)
            
            copy_time = time.time() - start_time
            throughput = bytes_copied / copy_time if copy_time > 0 else 0
            
            return {
                "bytes_copied": bytes_copied,
                "copy_time": copy_time,
                "throughput": throughput
            }
        
        except Exception as e:
            logger.error(f"文件复制失败: {src_path} -> {dst_path}, error={e}")
            raise
    
    def cache_file(self, file_path: str, content: Any):
        """缓存文件内容"""
        if len(self.file_cache) >= self.config.max_file_cache_size:
            # 移除最旧的缓存项
            oldest_key = next(iter(self.file_cache))
            del self.file_cache[oldest_key]
        
        self.file_cache[file_path] = {
            "content": content,
            "cached_at": time.time(),
            "access_count": 0
        }
    
    def get_cached_file(self, file_path: str) -> Optional[Any]:
        """获取缓存的文件内容"""
        if file_path in self.file_cache:
            cache_entry = self.file_cache[file_path]
            cache_entry["access_count"] += 1
            return cache_entry["content"]
        return None


class IOOptimizer:
    """
    📡 IO优化器
    
    提供网络优化、磁盘优化、压缩传输、协议优化等功能
    """
    
    def __init__(self, config: Optional[IOConfig] = None):
        self.config = config or IOConfig()
        self.compression_manager = CompressionManager(self.config)
        self.network_optimizer = NetworkOptimizer(self.config)
        self.disk_optimizer = DiskOptimizer(self.config)
        self.stats = IOStats()
        self.metrics_task: Optional[asyncio.Task] = None
        self.is_running = False
        
        logger.info("IOOptimizer初始化完成")
    
    async def start(self):
        """启动IO优化器"""
        if self.is_running:
            return
        
        self.is_running = True
        
        # 启动网络优化器
        await self.network_optimizer.start()
        
        # 启动指标收集
        if self.config.enable_metrics:
            self.metrics_task = asyncio.create_task(self._metrics_loop())
        
        logger.info("IOOptimizer已启动")
    
    async def stop(self):
        """停止IO优化器"""
        if not self.is_running:
            return
        
        self.is_running = False
        
        # 取消指标任务
        if self.metrics_task:
            self.metrics_task.cancel()
        
        # 停止网络优化器
        await self.network_optimizer.stop()
        
        logger.info("IOOptimizer已停止")
    
    # 网络相关方法
    async def http_request(self, method: str, url: str, **kwargs) -> aiohttp.ClientResponse:
        """HTTP请求"""
        return await self.network_optimizer.request(method, url, **kwargs)
    
    async def download_file(self, url: str, file_path: str, **kwargs) -> Dict[str, Any]:
        """下载文件"""
        return await self.network_optimizer.download_file(url, file_path, **kwargs)
    
    # 磁盘相关方法
    async def read_file(self, file_path: str, use_cache: bool = True, **kwargs) -> Union[str, bytes]:
        """读取文件"""
        if use_cache:
            cached_content = self.disk_optimizer.get_cached_file(file_path)
            if cached_content is not None:
                return cached_content
        
        content = await self.disk_optimizer.read_file(file_path, **kwargs)
        
        if use_cache:
            self.disk_optimizer.cache_file(file_path, content)
        
        return content
    
    async def write_file(self, file_path: str, content: Union[str, bytes], 
                        compress: bool = False, **kwargs) -> Dict[str, Any]:
        """写入文件"""
        if compress and self.config.compression_enabled:
            if isinstance(content, str):
                content = content.encode('utf-8')
            content = self.compression_manager.compress(content)
            file_path += '.gz'  # 添加压缩文件扩展名
            kwargs['mode'] = 'wb'
        
        return await self.disk_optimizer.write_file(file_path, content, **kwargs)
    
    async def copy_file(self, src_path: str, dst_path: str, **kwargs) -> Dict[str, Any]:
        """复制文件"""
        return await self.disk_optimizer.copy_file(src_path, dst_path, **kwargs)
    
    # 压缩相关方法
    def compress_data(self, data: Union[str, bytes], 
                     compression_type: Optional[CompressionType] = None) -> bytes:
        """压缩数据"""
        return self.compression_manager.compress(data, compression_type)
    
    def decompress_data(self, data: bytes, 
                       compression_type: CompressionType) -> bytes:
        """解压数据"""
        return self.compression_manager.decompress(data, compression_type)
    
    # 统计和分析方法
    def get_stats(self) -> Dict[str, Any]:
        """获取IO统计"""
        # 合并各组件统计
        network_stats = self.network_optimizer.stats
        disk_stats = self.disk_optimizer.stats
        compression_stats = self.compression_manager.stats
        
        return {
            "network": {
                "bytes_sent": network_stats.bytes_sent,
                "bytes_received": network_stats.bytes_received,
                "requests_sent": network_stats.requests_sent,
                "responses_received": network_stats.responses_received,
                "connection_errors": network_stats.connection_errors,
                "timeout_errors": network_stats.timeout_errors,
                "avg_response_time": (
                    sum(network_stats.response_times) / len(network_stats.response_times)
                    if network_stats.response_times else 0.0
                )
            },
            "disk": {
                "files_read": disk_stats.files_read,
                "files_written": disk_stats.files_written,
                "bytes_read": disk_stats.disk_bytes_read,
                "bytes_written": disk_stats.disk_bytes_written,
                "operations": disk_stats.disk_operations,
                "cache_size": len(self.disk_optimizer.file_cache)
            },
            "compression": {
                "compression_ratio": self.compression_manager.get_compression_ratio(),
                "compression_time": compression_stats["compression_time"],
                "decompression_time": compression_stats["decompression_time"],
                "compressed_bytes": compression_stats["compressed_bytes"],
                "uncompressed_bytes": compression_stats["uncompressed_bytes"]
            }
        }
    
    def get_performance_analysis(self) -> Dict[str, Any]:
        """获取性能分析"""
        stats = self.get_stats()
        analysis = {
            "stats": stats,
            "recommendations": []
        }
        
        # 网络性能分析
        if stats["network"]["connection_errors"] > 0:
            error_rate = stats["network"]["connection_errors"] / max(stats["network"]["requests_sent"], 1)
            if error_rate > 0.1:
                analysis["recommendations"].append("网络连接错误率过高，建议检查网络配置")
        
        if stats["network"]["avg_response_time"] > 5.0:
            analysis["recommendations"].append("平均响应时间过长，建议优化网络配置或增加超时时间")
        
        # 磁盘性能分析
        cache_hit_potential = stats["disk"]["files_read"] > stats["disk"]["cache_size"]
        if cache_hit_potential:
            analysis["recommendations"].append("可以增加文件缓存大小以提高缓存命中率")
        
        # 压缩分析
        compression_ratio = stats["compression"]["compression_ratio"]
        if compression_ratio > 0.8:
            analysis["recommendations"].append("压缩比较低，可以考虑调整压缩算法或压缩级别")
        
        return analysis
    
    def optimize_config(self) -> Dict[str, Any]:
        """优化配置"""
        stats = self.get_stats()
        optimizations = {
            "current_config": {
                "read_buffer_size": self.config.read_buffer_size,
                "write_buffer_size": self.config.write_buffer_size,
                "max_connections": self.config.max_connections,
                "compression_level": self.config.compression_level
            },
            "recommended_config": {},
            "optimizations": []
        }
        
        # 根据统计数据优化配置
        avg_response_time = stats["network"]["avg_response_time"]
        if avg_response_time > 2.0:
            optimizations["recommended_config"]["read_buffer_size"] = self.config.read_buffer_size * 2
            optimizations["optimizations"].append("增加读缓冲区大小以减少响应时间")
        
        connection_errors = stats["network"]["connection_errors"]
        if connection_errors > 10:
            optimizations["recommended_config"]["max_connections"] = min(
                self.config.max_connections * 2, 500
            )
            optimizations["optimizations"].append("增加最大连接数以减少连接错误")
        
        compression_ratio = stats["compression"]["compression_ratio"]
        if compression_ratio > 0.9:
            optimizations["recommended_config"]["compression_level"] = max(
                self.config.compression_level - 1, 1
            )
            optimizations["optimizations"].append("降低压缩级别以提高压缩比")
        
        return optimizations
    
    async def _metrics_loop(self):
        """指标收集循环"""
        while self.is_running:
            try:
                await asyncio.sleep(self.config.metrics_interval)
                await self._update_metrics()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"指标更新失败: {e}")
    
    async def _update_metrics(self):
        """更新指标"""
        stats = self.get_stats()
        
        # 计算吞吐量
        network_stats = stats["network"]
        if network_stats["requests_sent"] > 0:
            total_bytes = network_stats["bytes_sent"] + network_stats["bytes_received"]
            self.stats.avg_throughput = total_bytes / self.config.metrics_interval
        
        logger.debug(f"IO指标更新: {stats}")


# 工具函数

async def bulk_download(optimizer: IOOptimizer, urls: List[str], 
                       destination_dir: str, max_concurrent: int = 10) -> List[Dict[str, Any]]:
    """批量下载文件"""
    semaphore = asyncio.Semaphore(max_concurrent)
    results = []
    
    async def download_single(url: str, index: int):
        async with semaphore:
            file_name = f"file_{index}_{hashlib.md5(url.encode()).hexdigest()[:8]}"
            file_path = os.path.join(destination_dir, file_name)
            try:
                result = await optimizer.download_file(url, file_path)
                result["url"] = url
                result["success"] = True
                return result
            except Exception as e:
                return {"url": url, "success": False, "error": str(e)}
    
    tasks = [download_single(url, i) for i, url in enumerate(urls)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    return results


def io_performance_monitor(func):
    """IO性能监控装饰器"""
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        start_memory = 0  # 可以添加内存监控
        
        try:
            result = await func(*args, **kwargs)
            success = True
            error = None
        except Exception as e:
            result = None
            success = False
            error = str(e)
            raise
        finally:
            duration = time.time() - start_time
            logger.debug(f"IO操作完成: {func.__name__}, duration={duration:.3f}s, success={success}")
            
            # 可以将性能数据发送到监控系统
            if hasattr(args[0], 'performance_callback'):
                await args[0].performance_callback({
                    "function": func.__name__,
                    "duration": duration,
                    "success": success,
                    "error": error
                })
        
        return result
    
    return wrapper