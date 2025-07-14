#!/usr/bin/env python3
"""
端口管理器
实现端口冲突检测和自动清理机制
"""

import os
import socket
import subprocess
import time
import psutil
import structlog
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

logger = structlog.get_logger(__name__)


@dataclass
class PortInfo:
    """端口信息"""
    port: int
    pid: Optional[int] = None
    process_name: Optional[str] = None
    command: Optional[str] = None
    is_available: bool = False


class PortManager:
    """端口管理器"""
    
    def __init__(self):
        self.logger = structlog.get_logger(__name__)
    
    def check_port_availability(self, port: int, host: str = '0.0.0.0') -> PortInfo:
        """
        检查端口可用性
        
        Args:
            port: 端口号
            host: 主机地址
            
        Returns:
            PortInfo: 端口信息
        """
        port_info = PortInfo(port=port)
        
        try:
            # 尝试绑定端口
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                result = sock.bind((host, port))
                port_info.is_available = True
                self.logger.info(f"端口 {port} 可用")
                
        except OSError as e:
            if e.errno == 98:  # Address already in use
                port_info.is_available = False
                # 查找占用端口的进程
                process_info = self._find_process_by_port(port)
                if process_info:
                    port_info.pid = process_info['pid']
                    port_info.process_name = process_info['name']
                    port_info.command = process_info['command']
                
                self.logger.warning(f"端口 {port} 被占用", 
                                  pid=port_info.pid,
                                  process=port_info.process_name)
            else:
                self.logger.error(f"检查端口 {port} 时出错: {e}")
                port_info.is_available = False
        
        return port_info
    
    def _find_process_by_port(self, port: int) -> Optional[Dict[str, Any]]:
        """
        根据端口查找占用的进程
        
        Args:
            port: 端口号
            
        Returns:
            Dict: 进程信息
        """
        try:
            # 使用psutil查找进程
            for conn in psutil.net_connections():
                if conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
                    try:
                        process = psutil.Process(conn.pid)
                        return {
                            'pid': conn.pid,
                            'name': process.name(),
                            'command': ' '.join(process.cmdline()),
                            'status': process.status()
                        }
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
        except Exception as e:
            self.logger.error(f"查找端口 {port} 占用进程时出错: {e}")
        
        return None
    
    def kill_process_by_port(self, port: int, force: bool = False) -> bool:
        """
        杀死占用指定端口的进程
        
        Args:
            port: 端口号
            force: 是否强制杀死
            
        Returns:
            bool: 是否成功
        """
        process_info = self._find_process_by_port(port)
        if not process_info:
            self.logger.info(f"端口 {port} 没有被占用")
            return True
        
        pid = process_info['pid']
        process_name = process_info['name']
        
        try:
            process = psutil.Process(pid)
            
            # 检查是否是我们自己的进程
            if self._is_our_process(process):
                self.logger.info(f"发现我们自己的进程占用端口 {port}，PID: {pid}")
                
                if force:
                    # 强制杀死
                    process.kill()
                    self.logger.info(f"强制杀死进程 {pid} ({process_name})")
                else:
                    # 优雅关闭
                    process.terminate()
                    self.logger.info(f"发送终止信号给进程 {pid} ({process_name})")
                    
                    # 等待进程结束
                    try:
                        process.wait(timeout=10)
                        self.logger.info(f"进程 {pid} 已优雅关闭")
                    except psutil.TimeoutExpired:
                        self.logger.warning(f"进程 {pid} 未在10秒内关闭，强制杀死")
                        process.kill()
                
                return True
            else:
                self.logger.warning(f"端口 {port} 被其他进程占用: {process_name} (PID: {pid})")
                if force:
                    self.logger.warning(f"强制杀死其他进程 {pid} ({process_name})")
                    process.kill()
                    return True
                else:
                    self.logger.info("不会杀死其他进程，请手动处理或使用force=True")
                    return False
                    
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            self.logger.error(f"无法操作进程 {pid}: {e}")
            return False
    
    def _is_our_process(self, process: psutil.Process) -> bool:
        """
        判断是否是我们自己的进程
        
        Args:
            process: 进程对象
            
        Returns:
            bool: 是否是我们的进程
        """
        try:
            cmdline = process.cmdline()
            # 检查命令行是否包含我们的服务标识
            our_identifiers = [
                'data-collector',
                'main.py',
                'marketprism'
            ]
            
            cmdline_str = ' '.join(cmdline).lower()
            return any(identifier in cmdline_str for identifier in our_identifiers)
            
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            return False
    
    def ensure_port_available(self, port: int, force_kill: bool = True) -> bool:
        """
        确保端口可用
        
        Args:
            port: 端口号
            force_kill: 是否强制杀死占用进程
            
        Returns:
            bool: 端口是否可用
        """
        self.logger.info(f"检查端口 {port} 可用性...")
        
        port_info = self.check_port_availability(port)
        
        if port_info.is_available:
            self.logger.info(f"✅ 端口 {port} 可用")
            return True
        
        self.logger.warning(f"❌ 端口 {port} 被占用，尝试清理...")
        
        # 尝试杀死占用进程
        if self.kill_process_by_port(port, force=force_kill):
            # 等待端口释放
            for i in range(10):  # 最多等待10秒
                time.sleep(1)
                port_info = self.check_port_availability(port)
                if port_info.is_available:
                    self.logger.info(f"✅ 端口 {port} 已释放")
                    return True
                self.logger.info(f"等待端口 {port} 释放... ({i+1}/10)")
            
            self.logger.error(f"❌ 端口 {port} 仍然被占用")
            return False
        else:
            self.logger.error(f"❌ 无法清理端口 {port}")
            return False
    
    def find_available_port(self, start_port: int, end_port: int = None) -> Optional[int]:
        """
        查找可用端口
        
        Args:
            start_port: 起始端口
            end_port: 结束端口，默认为start_port + 100
            
        Returns:
            Optional[int]: 可用端口，如果没有则返回None
        """
        if end_port is None:
            end_port = start_port + 100
        
        for port in range(start_port, end_port + 1):
            port_info = self.check_port_availability(port)
            if port_info.is_available:
                self.logger.info(f"找到可用端口: {port}")
                return port
        
        self.logger.error(f"在范围 {start_port}-{end_port} 内没有找到可用端口")
        return None
    
    def get_port_status_report(self, ports: List[int]) -> Dict[int, PortInfo]:
        """
        获取多个端口的状态报告
        
        Args:
            ports: 端口列表
            
        Returns:
            Dict[int, PortInfo]: 端口状态报告
        """
        report = {}
        for port in ports:
            report[port] = self.check_port_availability(port)
        return report


# 全局端口管理器实例
port_manager = PortManager()


def ensure_service_port(port: int, service_name: str = "unknown") -> int:
    """
    确保服务端口可用的便捷函数
    
    Args:
        port: 期望的端口号
        service_name: 服务名称
        
    Returns:
        int: 可用的端口号
    """
    logger.info(f"为服务 {service_name} 确保端口 {port} 可用...")
    
    if port_manager.ensure_port_available(port, force_kill=True):
        logger.info(f"✅ 服务 {service_name} 将使用端口 {port}")
        return port
    else:
        # 如果无法清理原端口，尝试找一个新端口
        logger.warning(f"无法清理端口 {port}，寻找替代端口...")
        alternative_port = port_manager.find_available_port(port + 1, port + 10)
        
        if alternative_port:
            logger.info(f"✅ 服务 {service_name} 将使用替代端口 {alternative_port}")
            return alternative_port
        else:
            logger.error(f"❌ 无法为服务 {service_name} 找到可用端口")
            raise RuntimeError(f"无法为服务 {service_name} 找到可用端口")
