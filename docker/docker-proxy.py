#!/usr/bin/env python
# coding: utf-8

"""
Docker代理服务

这个脚本在宿主机上运行，作为Docker容器和宿主机代理之间的桥梁。
解决Docker容器无法直接访问宿主机127.0.0.1地址的问题。

使用方法:
1. 在宿主机上运行此脚本: python docker-proxy.py
2. 在Docker容器中使用宿主机的IP地址+此脚本监听的端口作为代理

示例:
如果宿主机IP是192.168.1.100，本脚本默认监听1088端口
在Docker容器中设置http_proxy=http://192.168.1.100:1088
"""

import socket
import select
import threading
import time
import os
import sys
import argparse

# 默认配置
DEFAULT_LISTEN_PORT = 1088  # 本脚本监听的端口
DEFAULT_PROXY_HOST = "127.0.0.1"  # 宿主机上实际代理的地址
DEFAULT_PROXY_PORT = 1087  # 宿主机上实际代理的端口
DEFAULT_BUFFER_SIZE = 8192  # 缓冲区大小
DEFAULT_TIMEOUT = 60  # 连接超时时间(秒)

class ProxyServer:
    def __init__(self, listen_port, proxy_host, proxy_port, buffer_size=DEFAULT_BUFFER_SIZE, timeout=DEFAULT_TIMEOUT):
        self.listen_port = listen_port
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.buffer_size = buffer_size
        self.timeout = timeout
        self.server_socket = None
        self.connections = []
        self.running = False
        
    def start(self):
        """启动代理服务器"""
        try:
            # 创建服务器socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # 绑定所有接口
            self.server_socket.bind(('0.0.0.0', self.listen_port))
            self.server_socket.listen(100)
            
            self.running = True
            print(f"代理服务器运行在 0.0.0.0:{self.listen_port}")
            print(f"所有请求会转发到 {self.proxy_host}:{self.proxy_port}")
            
            # 开始接受连接
            self._accept_connections()
            
        except Exception as e:
            print(f"启动代理服务器出错: {str(e)}")
            self.stop()
            
    def stop(self):
        """停止代理服务器"""
        self.running = False
        
        # 关闭所有连接
        for conn in self.connections:
            try:
                conn.close()
            except:
                pass
                
        # 关闭服务器socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
                
        print("代理服务器已停止")
        
    def _accept_connections(self):
        """接受客户端连接"""
        while self.running:
            try:
                # 等待新连接
                client_socket, client_addr = self.server_socket.accept()
                print(f"接受来自 {client_addr[0]}:{client_addr[1]} 的连接")
                
                # 创建新线程处理连接
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, client_addr)
                )
                client_thread.daemon = True
                client_thread.start()
                
            except Exception as e:
                if self.running:
                    print(f"接受连接出错: {str(e)}")
                    time.sleep(0.1)
                    
    def _handle_client(self, client_socket, client_addr):
        """处理客户端连接"""
        # 连接到实际代理服务器
        try:
            proxy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            proxy_socket.connect((self.proxy_host, self.proxy_port))
            
            # 添加到连接列表
            self.connections.append(client_socket)
            self.connections.append(proxy_socket)
            
            # 双向转发数据
            self._forward_data(client_socket, proxy_socket)
            
        except Exception as e:
            print(f"处理客户端连接出错: {str(e)}")
            
        finally:
            # 关闭连接
            try:
                client_socket.close()
            except:
                pass
                
            try:
                proxy_socket.close()
            except:
                pass
                
            # 从连接列表中移除
            if client_socket in self.connections:
                self.connections.remove(client_socket)
                
            if proxy_socket in self.connections:
                self.connections.remove(proxy_socket)
                
    def _forward_data(self, client_socket, proxy_socket):
        """在客户端和代理服务器之间转发数据"""
        client_socket.setblocking(False)
        proxy_socket.setblocking(False)
        
        while self.running:
            # 使用select监控两个socket
            readable, _, exceptional = select.select(
                [client_socket, proxy_socket], 
                [], 
                [client_socket, proxy_socket], 
                1.0
            )
            
            # 处理可读socket
            for sock in readable:
                # 从一个socket读取数据
                try:
                    data = sock.recv(self.buffer_size)
                    
                    # 如果没有数据，表示连接已关闭
                    if not data:
                        return
                        
                    # 确定目标socket
                    if sock == client_socket:
                        target = proxy_socket
                    else:
                        target = client_socket
                        
                    # 发送数据到目标socket
                    target.send(data)
                    
                except Exception as e:
                    print(f"转发数据出错: {str(e)}")
                    return
                    
            # 处理异常socket
            if exceptional:
                print("连接异常，关闭")
                return

def get_host_ip():
    """获取宿主机IP地址"""
    try:
        # 创建一个临时socket连接来获取本机IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))  # 连接到Google DNS
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"  # 失败则返回本地回环地址

def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='Docker容器代理服务')
    parser.add_argument('-l', '--listen-port', type=int, default=DEFAULT_LISTEN_PORT,
                        help=f'代理服务监听端口 (默认: {DEFAULT_LISTEN_PORT})')
    parser.add_argument('-p', '--proxy-host', default=DEFAULT_PROXY_HOST,
                        help=f'宿主机上实际代理的地址 (默认: {DEFAULT_PROXY_HOST})')
    parser.add_argument('-P', '--proxy-port', type=int, default=DEFAULT_PROXY_PORT,
                        help=f'宿主机上实际代理的端口 (默认: {DEFAULT_PROXY_PORT})')
    
    args = parser.parse_args()
    
    # 获取宿主机IP地址
    host_ip = get_host_ip()
    
    # 显示配置信息
    print("Docker容器代理服务")
    print("=" * 50)
    print(f"宿主机IP: {host_ip}")
    print(f"监听端口: {args.listen_port}")
    print(f"转发到: {args.proxy_host}:{args.proxy_port}")
    print("=" * 50)
    print(f"Docker容器中使用: http://{host_ip}:{args.listen_port}")
    print("=" * 50)
    
    # 创建并启动代理服务器
    proxy_server = ProxyServer(
        listen_port=args.listen_port,
        proxy_host=args.proxy_host,
        proxy_port=args.proxy_port
    )
    
    try:
        proxy_server.start()
    except KeyboardInterrupt:
        print("\n接收到中断信号，停止服务...")
    finally:
        proxy_server.stop()

if __name__ == "__main__":
    main() 