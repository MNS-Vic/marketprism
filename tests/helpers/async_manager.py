"""
异步测试管理器 - 统一处理异步资源清理和任务管理

解决pytest中异步测试的常见问题：
1. Pending tasks未正确清理
2. NATS连接泄漏
3. aiohttp连接池泄漏
4. WebSocket连接未关闭
"""

from datetime import datetime, timezone
import asyncio
import gc
import sys
import weakref
import functools
from typing import Dict, List, Optional, Any, Set
from contextlib import AsyncExitStack
import aiohttp
import pytest
from unittest.mock import AsyncMock

try:
    import nats
    from nats.aio.client import Client as NATSClient
    NATS_AVAILABLE = True
except ImportError:
    NATS_AVAILABLE = False


class AsyncResourceTracker:
    """异步资源追踪器"""
    
    def __init__(self):
        self.tracked_tasks: Set[asyncio.Task] = set()
        self.tracked_sessions: Set[aiohttp.ClientSession] = set()
        self.tracked_nats_clients: Set = set()
        self.tracked_websockets: Set = set()
        self.exit_stack = AsyncExitStack()
        
    def track_task(self, task: asyncio.Task) -> asyncio.Task:
        """追踪异步任务"""
        self.tracked_tasks.add(task)
        # 使用weakref避免循环引用
        weak_ref = weakref.ref(task, lambda ref: self.tracked_tasks.discard(task))
        return task
    
    def track_session(self, session: aiohttp.ClientSession) -> aiohttp.ClientSession:
        """追踪aiohttp会话"""
        self.tracked_sessions.add(session)
        return session
    
    def track_nats_client(self, client) -> Any:
        """追踪NATS客户端"""
        if NATS_AVAILABLE:
            self.tracked_nats_clients.add(client)
        return client
    
    async def cleanup_all(self) -> Dict[str, int]:
        """清理所有追踪的资源"""
        cleanup_stats = {
            'tasks_cancelled': 0,
            'sessions_closed': 0,
            'nats_clients_closed': 0,
            'websockets_closed': 0
        }
        
        # 1. 取消所有追踪的任务
        for task in list(self.tracked_tasks):
            if not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                cleanup_stats['tasks_cancelled'] += 1
        
        # 2. 关闭所有aiohttp会话
        for session in list(self.tracked_sessions):
            if not session.closed:
                await session.close()
                cleanup_stats['sessions_closed'] += 1
        
        # 3. 关闭所有NATS连接
        if NATS_AVAILABLE:
            for client in list(self.tracked_nats_clients):
                if hasattr(client, 'is_connected') and client.is_connected:
                    try:
                        await client.close()
                        cleanup_stats['nats_clients_closed'] += 1
                    except Exception:
                        pass
        
        # 4. 使用exit_stack清理其他资源
        await self.exit_stack.aclose()
        
        # 5. 强制垃圾回收
        gc.collect()
        
        return cleanup_stats


class AsyncTestManager:
    """异步测试管理器 - 主要的异步上下文管理器"""
    
    def __init__(self, test_name: str = "unknown"):
        self.test_name = test_name
        self.resource_tracker = AsyncResourceTracker()
        self.original_loop = None
        
    async def __aenter__(self):
        """进入异步上下文"""
        self.original_loop = asyncio.get_event_loop()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出异步上下文，清理所有资源"""
        try:
            cleanup_stats = await self.resource_tracker.cleanup_all()
            
            if any(cleanup_stats.values()):
                print(f"🧹 [{self.test_name}] 异步资源清理完成: {cleanup_stats}")
                
        except Exception as e:
            print(f"⚠️ [{self.test_name}] 资源清理警告: {e}")
        
        # 等待事件循环处理剩余任务
        await asyncio.sleep(0.01)
        
        # 清理剩余的pending tasks
        await self._cleanup_remaining_tasks()
    
    async def _cleanup_remaining_tasks(self):
        """清理剩余的pending tasks"""
        current_loop = asyncio.get_event_loop()
        pending_tasks = [task for task in asyncio.all_tasks(current_loop) 
                        if not task.done() and task != asyncio.current_task()]
        
        if pending_tasks:
            print(f"⚠️ [{self.test_name}] 发现 {len(pending_tasks)} 个pending tasks，正在清理...")
            
            # 尝试优雅取消
            for task in pending_tasks:
                if not task.done():
                    task.cancel()
            
            # 等待取消完成
            if pending_tasks:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*pending_tasks, return_exceptions=True),
                        timeout=2.0
                    )
                except asyncio.TimeoutError:
                    print(f"⚠️ [{self.test_name}] 部分tasks取消超时")
    
    def create_task(self, coro, name: str = None) -> asyncio.Task:
        """创建并追踪异步任务"""
        task = asyncio.create_task(coro, name=name)
        return self.resource_tracker.track_task(task)
    
    def create_session(self, **kwargs) -> aiohttp.ClientSession:
        """创建并追踪aiohttp会话"""
        session = aiohttp.ClientSession(**kwargs)
        return self.resource_tracker.track_session(session)
    
    def create_nats_client(self, **kwargs):
        """创建并追踪NATS客户端"""
        if not NATS_AVAILABLE:
            return AsyncMock()
        
        client = nats.NATS()
        return self.resource_tracker.track_nats_client(client)


def async_test(test_func):
    """
    异步测试装饰器 - 自动处理资源清理
    
    使用方法:
    @async_test
    async def test_something():
        async with AsyncTestManager("test_something") as manager:
            # 测试代码
            pass
    """
    @functools.wraps(test_func)
    async def wrapper(*args, **kwargs):
        test_name = test_func.__name__
        
        async with AsyncTestManager(test_name) as manager:
            try:
                # 将manager传递给测试函数
                if 'async_manager' in test_func.__code__.co_varnames:
                    kwargs['async_manager'] = manager
                
                result = await test_func(*args, **kwargs)
                return result
                
            except Exception as e:
                print(f"❌ [{test_name}] 测试异常: {e}")
                raise
                
    return wrapper


def async_test_with_cleanup(test_func):
    """
    增强的异步测试装饰器 - 更严格的清理
    
    适用于复杂的异步测试，包含多个服务连接
    """
    @functools.wraps(test_func)
    async def wrapper(*args, **kwargs):
        test_name = test_func.__name__
        
        # 记录测试开始前的任务数量
        initial_tasks = len(asyncio.all_tasks())
        
        try:
            async with AsyncTestManager(test_name) as manager:
                result = await test_func(*args, **kwargs)
                
                # 验证测试后的资源状态
                await asyncio.sleep(0.1)  # 给清理操作时间
                final_tasks = len(asyncio.all_tasks())
                
                if final_tasks > initial_tasks:
                    print(f"⚠️ [{test_name}] 任务数量增加: {initial_tasks} → {final_tasks}")
                
                return result
                
        except Exception as e:
            print(f"❌ [{test_name}] 测试失败: {e}")
            raise
        finally:
            # 强制垃圾回收
            gc.collect()
            
    return wrapper


# Pytest fixture用于异步测试
@pytest.fixture
async def async_manager():
    """Pytest fixture for AsyncTestManager"""
    test_name = "pytest_fixture"
    async with AsyncTestManager(test_name) as manager:
        yield manager


# 兼容性helpers
async def safe_create_task(coro, name: str = None, manager: AsyncTestManager = None) -> asyncio.Task:
    """安全创建异步任务"""
    if manager:
        return manager.create_task(coro, name)
    else:
        return asyncio.create_task(coro, name=name)


async def safe_create_session(manager: AsyncTestManager = None, **kwargs) -> aiohttp.ClientSession:
    """安全创建aiohttp会话"""
    if manager:
        return manager.create_session(**kwargs)
    else:
        return aiohttp.ClientSession(**kwargs)


def get_async_manager() -> Optional[AsyncTestManager]:
    """获取当前异步管理器（如果存在）"""
    # 这是一个简化版本，实际可能需要更复杂的上下文管理
    frame = sys._getframe(1)
    while frame:
        if 'async_manager' in frame.f_locals:
            return frame.f_locals['async_manager']
        frame = frame.f_back
    return None


if __name__ == "__main__":
    # 测试示例
    async def test_async_manager():
        async with AsyncTestManager("test_example") as manager:
            # 创建一些异步资源
            session = manager.create_session()
            task = manager.create_task(asyncio.sleep(0.1), "test_task")
            
            # 等待任务完成
            await task
            
            print("✅ 异步管理器测试完成")
    
    # 运行测试
    asyncio.run(test_async_manager()) 