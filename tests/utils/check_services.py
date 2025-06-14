#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MarketPrism 测试服务检查工具
用于检查测试环境中的服务是否可用
"""

from datetime import datetime, timezone
import os
import sys
import time
import socket
import logging
import argparse
import json
from typing import Dict, List, Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('service_check')

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

# 默认服务配置
DEFAULT_SERVICES = {
    "nats": {
        "host": "localhost",
        "port": 4222,
        "description": "NATS消息服务"
    },
    "clickhouse": {
        "host": "localhost",
        "port": 9000,
        "description": "ClickHouse数据库"
    }
}

def check_port_open(host: str, port: int, timeout: int = 2) -> bool:
    """检查主机端口是否开放"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        logger.error(f"检查端口时出错: {e}")
        return False

def check_nats_service(host: str, port: int) -> Dict:
    """检查NATS服务是否可用"""
    is_available = check_port_open(host, port)
    
    result = {
        "service": "NATS",
        "available": is_available,
        "host": host,
        "port": port
    }
    
    if is_available:
        try:
            # 尝试导入nats客户端
            import nats
            result["client_available"] = True
        except ImportError:
            result["client_available"] = False
            result["client_error"] = "nats客户端库未安装"
    
    return result

def check_clickhouse_service(host: str, port: int) -> Dict:
    """检查ClickHouse服务是否可用"""
    is_available = check_port_open(host, port)
    
    result = {
        "service": "ClickHouse",
        "available": is_available,
        "host": host,
        "port": port
    }
    
    if is_available:
        try:
            # 尝试导入clickhouse客户端
            from clickhouse_driver import Client
            result["client_available"] = True
            
            # 尝试简单连接
            try:
                client = Client(host=host, port=port)
                client.execute("SELECT 1")
                result["connection_test"] = "成功"
            except Exception as e:
                result["connection_test"] = "失败"
                result["connection_error"] = str(e)
        except ImportError:
            result["client_available"] = False
            result["client_error"] = "clickhouse-driver库未安装"
    
    return result

def check_all_services(services: Dict = None, output_format: str = "text") -> List[Dict]:
    """检查所有服务的可用性"""
    services = services or DEFAULT_SERVICES
    results = []
    
    for service_name, config in services.items():
        logger.info(f"检查服务: {config['description']} ({config['host']}:{config['port']})")
        
        if service_name == "nats":
            result = check_nats_service(config['host'], config['port'])
        elif service_name == "clickhouse":
            result = check_clickhouse_service(config['host'], config['port'])
        else:
            result = {
                "service": service_name,
                "available": check_port_open(config['host'], config['port']),
                "host": config['host'],
                "port": config['port']
            }
        
        results.append(result)
        
        # 输出结果
        if output_format == "text":
            status = "✅ 可用" if result["available"] else "❌ 不可用"
            logger.info(f"{result['service']} ({result['host']}:{result['port']}): {status}")
            
            if "client_available" in result:
                client_status = "✅ 已安装" if result["client_available"] else "❌ 未安装"
                logger.info(f"  客户端库: {client_status}")
            
            if "connection_test" in result:
                conn_status = "✅ 成功" if result["connection_test"] == "成功" else "❌ 失败"
                logger.info(f"  连接测试: {conn_status}")
                if "connection_error" in result:
                    logger.info(f"  连接错误: {result['connection_error']}")
    
    return results

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="MarketPrism测试服务检查工具")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    args = parser.parse_args()
    
    if args.format == "text":
        logger.info("开始检查测试服务...")
    
    results = check_all_services(output_format=args.format)
    
    if args.format == "json":
        print(json.dumps(results, indent=2, ensure_ascii=False))
    
    # 检查是否所有服务都可用
    all_available = all(result["available"] for result in results)
    
    if args.format == "text":
        if all_available:
            logger.info("所有服务检查通过 ✅")
        else:
            logger.warning("部分服务不可用 ❌")
    
    return 0 if all_available else 1

if __name__ == "__main__":
    sys.exit(main())