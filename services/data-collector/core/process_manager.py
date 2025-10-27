"""
进程管理器 - 负责启动、监控、重启子进程

功能：
1. 子进程生命周期管理（启动、停止、重启）
2. 进程健康监控
3. 故障隔离和自动恢复
4. IPC 通信管理
"""

import asyncio
import multiprocessing as mp
import time
import signal
import sys
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass
from enum import Enum
import logging

from .ipc_protocol import (
    IPCMessage, MessageType, IPCProtocol,
    serialize_message, deserialize_message
)
from .resource_manager import ResourceManager, ResourceLimits


class ProcessState(Enum):
    """进程状态"""
    STARTING = "starting"       # 启动中
    RUNNING = "running"         # 运行中
    STOPPING = "stopping"       # 停止中
    STOPPED = "stopped"         # 已停止
    FAILED = "failed"           # 失败
    RESTARTING = "restarting"   # 重启中


@dataclass
class ProcessInfo:
    """进程信息"""
    exchange: str               # 交易所名称
    pid: Optional[int]          # 进程 ID
    state: ProcessState         # 进程状态
    start_time: float           # 启动时间
    restart_count: int          # 重启次数
    last_heartbeat: float       # 最后心跳时间
    process: Optional[mp.Process] = None  # 进程对象
    pipe_conn: Optional[Any] = None       # Pipe 连接


class ProcessManager:
    """进程管理器"""
    
    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        max_restart_attempts: int = 3,
        restart_cooldown: float = 5.0,
        heartbeat_timeout: float = 30.0
    ):
        """
        初始化进程管理器
        
        Args:
            logger: 日志记录器
            max_restart_attempts: 最大重启尝试次数
            restart_cooldown: 重启冷却时间（秒）
            heartbeat_timeout: 心跳超时时间（秒）
        """
        self.logger = logger or logging.getLogger(__name__)
        self.max_restart_attempts = max_restart_attempts
        self.restart_cooldown = restart_cooldown
        self.heartbeat_timeout = heartbeat_timeout
        
        # 进程信息
        self.processes: Dict[str, ProcessInfo] = {}
        
        # IPC 连接（主进程端）
        self.pipes: Dict[str, mp.connection.Connection] = {}
        
        # 资源管理器
        self.resource_managers: Dict[str, ResourceManager] = {}
        
        # 监控任务
        self.monitor_tasks: Dict[str, asyncio.Task] = {}
        
        # 停止标志
        self.stop_event = asyncio.Event()
        
    def start_process(
        self,
        exchange: str,
        target_func: Callable,
        args: tuple = (),
        kwargs: Optional[Dict[str, Any]] = None,
        resource_limits: Optional[ResourceLimits] = None
    ) -> bool:
        """
        启动子进程
        
        Args:
            exchange: 交易所名称
            target_func: 目标函数
            args: 位置参数
            kwargs: 关键字参数
            resource_limits: 资源限制
            
        Returns:
            bool: 是否启动成功
        """
        try:
            if exchange in self.processes:
                self.logger.warning(f"进程 {exchange} 已存在")
                return False
            
            # 创建 Pipe（双向通信）
            parent_conn, child_conn = mp.Pipe()
            
            # 准备参数
            kwargs = kwargs or {}
            kwargs['pipe_conn'] = child_conn
            kwargs['exchange'] = exchange
            
            # 创建进程
            process = mp.Process(
                target=target_func,
                args=args,
                kwargs=kwargs,
                name=f"collector-{exchange}"
            )
            
            # 启动进程
            process.start()
            
            # 记录进程信息
            process_info = ProcessInfo(
                exchange=exchange,
                pid=process.pid,
                state=ProcessState.STARTING,
                start_time=time.time(),
                restart_count=0,
                last_heartbeat=time.time(),
                process=process,
                pipe_conn=parent_conn
            )
            self.processes[exchange] = process_info
            self.pipes[exchange] = parent_conn
            
            # 创建资源管理器
            if process.pid:
                self.resource_managers[exchange] = ResourceManager(
                    exchange=exchange,
                    pid=process.pid,
                    limits=resource_limits,
                    on_soft_limit=self._on_soft_limit,
                    on_hard_limit=self._on_hard_limit
                )
            
            self.logger.info(f"✅ 进程 {exchange} 启动成功 (PID: {process.pid})")
            
            # 启动监控任务
            self.monitor_tasks[exchange] = asyncio.create_task(
                self._monitor_process(exchange)
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 启动进程 {exchange} 失败: {e}", exc_info=True)
            return False
    
    async def stop_process(self, exchange: str, timeout: float = 10.0) -> bool:
        """
        停止子进程
        
        Args:
            exchange: 交易所名称
            timeout: 超时时间（秒）
            
        Returns:
            bool: 是否停止成功
        """
        if exchange not in self.processes:
            self.logger.warning(f"进程 {exchange} 不存在")
            return False
        
        process_info = self.processes[exchange]
        process_info.state = ProcessState.STOPPING
        
        try:
            # 发送停止命令
            stop_msg = IPCProtocol.create_control_message(
                exchange=exchange,
                command=MessageType.CONTROL_STOP.value
            )
            self._send_message(exchange, stop_msg)
            
            # 等待进程退出
            if process_info.process:
                process_info.process.join(timeout=timeout)
                
                if process_info.process.is_alive():
                    # 强制终止
                    self.logger.warning(f"进程 {exchange} 未响应停止命令，强制终止")
                    process_info.process.terminate()
                    process_info.process.join(timeout=5)
                    
                    if process_info.process.is_alive():
                        # 最后手段：kill
                        process_info.process.kill()
                        process_info.process.join()
            
            # 清理资源
            process_info.state = ProcessState.STOPPED
            if exchange in self.pipes:
                self.pipes[exchange].close()
                del self.pipes[exchange]
            if exchange in self.resource_managers:
                del self.resource_managers[exchange]
            if exchange in self.monitor_tasks:
                self.monitor_tasks[exchange].cancel()
                del self.monitor_tasks[exchange]
            
            self.logger.info(f"✅ 进程 {exchange} 已停止")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 停止进程 {exchange} 失败: {e}", exc_info=True)
            return False
    
    async def restart_process(self, exchange: str) -> bool:
        """
        重启子进程
        
        Args:
            exchange: 交易所名称
            
        Returns:
            bool: 是否重启成功
        """
        if exchange not in self.processes:
            self.logger.warning(f"进程 {exchange} 不存在")
            return False
        
        process_info = self.processes[exchange]
        
        # 检查重启次数
        if process_info.restart_count >= self.max_restart_attempts:
            self.logger.error(
                f"进程 {exchange} 重启次数超过限制 ({self.max_restart_attempts})"
            )
            process_info.state = ProcessState.FAILED
            return False
        
        process_info.state = ProcessState.RESTARTING
        process_info.restart_count += 1
        
        self.logger.info(
            f"🔄 重启进程 {exchange} (第 {process_info.restart_count} 次)"
        )
        
        # 停止进程
        await self.stop_process(exchange)
        
        # 冷却时间
        await asyncio.sleep(self.restart_cooldown)
        
        # TODO: 重新启动进程（需要保存原始启动参数）
        # 这里需要在实际使用时传入启动参数
        self.logger.warning(f"进程 {exchange} 重启功能需要保存原始启动参数")

        return False

    async def stop_all_processes(self, timeout: float = 10.0):
        """停止所有子进程"""
        self.logger.info("🛑 停止所有子进程")
        self.stop_event.set()

        # 并行停止所有进程
        stop_tasks = []
        for exchange in list(self.processes.keys()):
            task = self.stop_process(exchange, timeout=timeout)
            stop_tasks.append(task)

        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)

        # 取消所有监控任务
        for task in self.monitor_tasks.values():
            if not task.done():
                task.cancel()

        self.logger.info("✅ 所有子进程已停止")

    def _send_message(self, exchange: str, msg: IPCMessage) -> bool:
        """发送消息到子进程"""
        if exchange not in self.pipes:
            return False

        try:
            data = serialize_message(msg)
            self.pipes[exchange].send(data)
            return True
        except Exception as e:
            self.logger.error(f"发送消息到 {exchange} 失败: {e}")
            return False

    def _receive_message(self, exchange: str, timeout: float = 0.1) -> Optional[IPCMessage]:
        """从子进程接收消息（非阻塞）"""
        if exchange not in self.pipes:
            return None

        try:
            if self.pipes[exchange].poll(timeout):
                data = self.pipes[exchange].recv()
                return deserialize_message(data)
            return None
        except Exception as e:
            self.logger.error(f"从 {exchange} 接收消息失败: {e}")
            return None

    async def _monitor_process(self, exchange: str):
        """监控子进程"""
        while not self.stop_event.is_set():
            try:
                if exchange not in self.processes:
                    break

                process_info = self.processes[exchange]

                # 检查进程是否存活
                if process_info.process and not process_info.process.is_alive():
                    self.logger.error(f"进程 {exchange} 意外退出")
                    process_info.state = ProcessState.FAILED
                    # 尝试重启
                    await self.restart_process(exchange)
                    break

                # 接收消息
                msg = self._receive_message(exchange, timeout=0.1)
                if msg:
                    await self._handle_message(exchange, msg)

                # 检查心跳超时
                if time.time() - process_info.last_heartbeat > self.heartbeat_timeout:
                    self.logger.warning(f"进程 {exchange} 心跳超时")
                    # 可以选择重启进程

                # 检查资源限制
                if exchange in self.resource_managers:
                    try:
                        usage = self.resource_managers[exchange].get_resource_usage()
                        limits_check = self.resource_managers[exchange].check_limits(usage)

                        # 如果触发硬限制，重启进程
                        if limits_check.get("memory_hard_exceeded"):
                            self.logger.error(
                                f"进程 {exchange} 内存超过硬限制，准备重启"
                            )
                            await self.restart_process(exchange)
                            break
                    except RuntimeError:
                        # 进程已退出
                        pass

                await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"监控进程 {exchange} 时发生异常: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _handle_message(self, exchange: str, msg: IPCMessage):
        """处理来自子进程的消息"""
        if exchange not in self.processes:
            return

        process_info = self.processes[exchange]

        if msg.msg_type == MessageType.HEARTBEAT.value:
            # 更新心跳时间
            process_info.last_heartbeat = time.time()
            if process_info.state == ProcessState.STARTING:
                process_info.state = ProcessState.RUNNING
                self.logger.info(f"进程 {exchange} 已就绪")

        elif msg.msg_type == MessageType.HEALTH.value:
            # 健康状态消息（由 HealthAggregator 处理）
            pass

        elif msg.msg_type == MessageType.METRICS.value:
            # 指标消息（由 MetricsAggregator 处理）
            pass

        elif msg.msg_type == MessageType.LOG.value:
            # 日志消息
            log_data = msg.data
            self.logger.info(f"[{exchange}] {log_data.get('message', '')}")

    def _on_soft_limit(self, exchange: str, resource_type: str, usage: Any):
        """软限制触发回调"""
        self.logger.warning(
            f"⚠️ 进程 {exchange} {resource_type} 超过软限制",
            extra={"usage": usage}
        )

    def _on_hard_limit(self, exchange: str, resource_type: str, usage: Any):
        """硬限制触发回调"""
        self.logger.error(
            f"🔴 进程 {exchange} {resource_type} 超过硬限制",
            extra={"usage": usage}
        )

    def get_process_info(self, exchange: str) -> Optional[ProcessInfo]:
        """获取进程信息"""
        return self.processes.get(exchange)

    def get_all_process_info(self) -> Dict[str, ProcessInfo]:
        """获取所有进程信息"""
        return self.processes.copy()

    def is_process_running(self, exchange: str) -> bool:
        """检查进程是否运行中"""
        if exchange not in self.processes:
            return False
        process_info = self.processes[exchange]
        return process_info.state == ProcessState.RUNNING

