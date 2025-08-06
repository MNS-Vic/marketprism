#!/usr/bin/env python3
"""
MarketPrism统一NATS容器 - 配置模板渲染器

🎯 功能说明：
- 环境变量驱动的NATS配置生成
- 支持配置模板渲染和验证
- 与unified_data_collection.yaml兼容
- 提供配置验证和错误检查

🔧 设计理念：
- 简化配置管理，支持环境变量覆盖
- 提供默认值和配置验证
- 生成标准的NATS服务器配置文件
- 支持JetStream和监控配置
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import re

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('ConfigRenderer')


class NATSConfigRenderer:
    """
    NATS配置模板渲染器
    
    负责从环境变量和模板生成NATS服务器配置文件
    """
    
    def __init__(self):
        """初始化配置渲染器"""
        self.env_vars = dict(os.environ)
        self.config_data = {}
        
        logger.info("NATS配置渲染器已初始化")
    
    def load_environment_config(self) -> Dict[str, Any]:
        """
        从环境变量加载配置
        
        Returns:
            配置字典
        """
        config = {
            # NATS服务器基础配置
            'server_name': os.getenv('NATS_SERVER_NAME', 'marketprism-nats-unified'),
            'host': os.getenv('NATS_HOST', '0.0.0.0'),
            'port': int(os.getenv('NATS_PORT', '4222')),
            'http_port': int(os.getenv('NATS_HTTP_PORT', '8222')),
            'cluster_port': int(os.getenv('NATS_CLUSTER_PORT', '6222')),
            
            # JetStream配置
            'jetstream_enabled': os.getenv('JETSTREAM_ENABLED', 'true').lower() == 'true',
            'jetstream_store_dir': os.getenv('JETSTREAM_STORE_DIR', '/data/jetstream'),
            'jetstream_max_memory': self._parse_size(os.getenv('JETSTREAM_MAX_MEMORY', '1GB')),
            'jetstream_max_file': self._parse_size(os.getenv('JETSTREAM_MAX_FILE', '10GB')),
            
            # 日志配置
            'log_file': os.getenv('NATS_LOG_FILE', '/var/log/nats/nats.log'),
            'log_time': os.getenv('NATS_LOG_TIME', 'true').lower() == 'true',
            'debug': os.getenv('NATS_DEBUG', 'false').lower() == 'true',
            'trace': os.getenv('NATS_TRACE', 'false').lower() == 'true',
            
            # 连接配置
            'max_connections': int(os.getenv('NATS_MAX_CONNECTIONS', '1000')),
            'max_control_line': int(os.getenv('NATS_MAX_CONTROL_LINE', '4096')),
            'max_payload': self._parse_size(os.getenv('NATS_MAX_PAYLOAD', '1MB')),
            'max_pending': self._parse_size(os.getenv('NATS_MAX_PENDING', '64MB')),
            
            # 监控配置
            'monitoring_enabled': os.getenv('MONITORING_ENABLED', 'true').lower() == 'true',
            'health_check_enabled': os.getenv('HEALTH_CHECK_ENABLED', 'true').lower() == 'true',
            
            # 认证配置（可选）
            'auth_enabled': os.getenv('NATS_AUTH_ENABLED', 'false').lower() == 'true',
            'auth_username': os.getenv('NATS_AUTH_USERNAME', ''),
            'auth_password': os.getenv('NATS_AUTH_PASSWORD', ''),
            'auth_token': os.getenv('NATS_AUTH_TOKEN', ''),
            
            # 集群配置（可选）
            'cluster_enabled': os.getenv('NATS_CLUSTER_ENABLED', 'false').lower() == 'true',
            'cluster_name': os.getenv('NATS_CLUSTER_NAME', 'marketprism-cluster'),
            'cluster_routes': os.getenv('NATS_CLUSTER_ROUTES', '').split(',') if os.getenv('NATS_CLUSTER_ROUTES') else [],
        }
        
        self.config_data = config
        logger.info("环境变量配置加载完成")
        return config
    
    def _parse_size(self, size_str: str) -> int:
        """
        解析大小字符串（如 1GB, 512MB）
        
        Args:
            size_str: 大小字符串
            
        Returns:
            字节数
        """
        if not size_str:
            return 0
        
        size_str = size_str.upper().strip()
        
        # 提取数字和单位
        match = re.match(r'^(\d+(?:\.\d+)?)\s*([KMGT]?B?)$', size_str)
        if not match:
            logger.warning(f"无法解析大小字符串: {size_str}，使用默认值")
            return 0
        
        number, unit = match.groups()
        number = float(number)
        
        # 单位转换
        multipliers = {
            'B': 1,
            'KB': 1024,
            'MB': 1024 ** 2,
            'GB': 1024 ** 3,
            'TB': 1024 ** 4,
            '': 1  # 无单位默认为字节
        }
        
        multiplier = multipliers.get(unit, 1)
        return int(number * multiplier)
    
    def generate_nats_config(self) -> str:
        """
        生成NATS服务器配置文件内容
        
        Returns:
            NATS配置文件内容
        """
        config = self.config_data or self.load_environment_config()
        
        # 生成配置文件内容
        config_lines = [
            "# MarketPrism统一NATS服务器配置",
            f"# 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"# 容器ID: {os.getenv('HOSTNAME', 'unknown')}",
            "",
            "# ==================== 基础服务器配置 ====================",
            f'server_name: "{config["server_name"]}"',
            f'host: "{config["host"]}"',
            f'port: {config["port"]}',
            "",
            "# ==================== HTTP监控配置 ====================",
            f'http_port: {config["http_port"]}',
            "",
        ]
        
        # JetStream配置
        if config['jetstream_enabled']:
            config_lines.extend([
                "# ==================== JetStream配置 ====================",
                "jetstream {",
                f'    store_dir: "{config["jetstream_store_dir"]}"',
                f'    max_memory_store: {config["jetstream_max_memory"]}',
                f'    max_file_store: {config["jetstream_max_file"]}',
                "}",
                "",
            ])
        
        # 日志配置
        config_lines.extend([
            "# ==================== 日志配置 ====================",
            f'log_file: "{config["log_file"]}"',
            f'logtime: {str(config["log_time"]).lower()}',
            f'debug: {str(config["debug"]).lower()}',
            f'trace: {str(config["trace"]).lower()}',
            "",
        ])
        
        # 连接配置
        config_lines.extend([
            "# ==================== 连接配置 ====================",
            f'max_connections: {config["max_connections"]}',
            f'max_control_line: {config["max_control_line"]}',
            f'max_payload: {config["max_payload"]}',
            f'max_pending: {config["max_pending"]}',
            "",
        ])
        
        # 认证配置（如果启用）
        if config['auth_enabled']:
            config_lines.extend([
                "# ==================== 认证配置 ====================",
                "authorization {",
            ])
            
            if config['auth_username'] and config['auth_password']:
                config_lines.extend([
                    "    users = [",
                    f'        {{user: "{config["auth_username"]}", password: "{config["auth_password"]}"}}',
                    "    ]",
                ])
            elif config['auth_token']:
                config_lines.extend([
                    f'    token: "{config["auth_token"]}"',
                ])
            
            config_lines.extend([
                "}",
                "",
            ])
        
        # 集群配置（如果启用）
        if config['cluster_enabled']:
            config_lines.extend([
                "# ==================== 集群配置 ====================",
                "cluster {",
                f'    name: "{config["cluster_name"]}"',
                f'    listen: "{config["host"]}:{config["cluster_port"]}"',
            ])
            
            if config['cluster_routes']:
                config_lines.extend([
                    "    routes = [",
                ])
                for route in config['cluster_routes']:
                    if route.strip():
                        config_lines.append(f'        "{route.strip()}"')
                config_lines.extend([
                    "    ]",
                ])
            
            config_lines.extend([
                "}",
                "",
            ])
        
        return "\n".join(config_lines)
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """
        验证配置
        
        Args:
            config: 配置字典
            
        Returns:
            错误列表
        """
        errors = []
        
        # 验证端口
        if not (1 <= config['port'] <= 65535):
            errors.append(f"无效的NATS端口: {config['port']}")
        
        if not (1 <= config['http_port'] <= 65535):
            errors.append(f"无效的HTTP端口: {config['http_port']}")
        
        if config['cluster_enabled'] and not (1 <= config['cluster_port'] <= 65535):
            errors.append(f"无效的集群端口: {config['cluster_port']}")
        
        # 验证JetStream配置
        if config['jetstream_enabled']:
            if not config['jetstream_store_dir']:
                errors.append("JetStream存储目录不能为空")
            
            if config['jetstream_max_memory'] <= 0:
                errors.append("JetStream最大内存必须大于0")
            
            if config['jetstream_max_file'] <= 0:
                errors.append("JetStream最大文件存储必须大于0")
        
        # 验证认证配置
        if config['auth_enabled']:
            if not config['auth_username'] and not config['auth_token']:
                errors.append("启用认证时必须提供用户名或令牌")
            
            if config['auth_username'] and not config['auth_password']:
                errors.append("提供用户名时必须提供密码")
        
        # 验证连接配置
        if config['max_connections'] <= 0:
            errors.append("最大连接数必须大于0")
        
        return errors
    
    def render_config_file(self, output_path: str) -> bool:
        """
        渲染并保存配置文件
        
        Args:
            output_path: 输出文件路径
            
        Returns:
            是否成功
        """
        try:
            # 加载配置
            config = self.load_environment_config()
            
            # 验证配置
            errors = self.validate_config(config)
            if errors:
                logger.error("配置验证失败:")
                for error in errors:
                    logger.error(f"  - {error}")
                return False
            
            # 生成配置内容
            config_content = self.generate_nats_config()
            
            # 确保输出目录存在
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入配置文件
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(config_content)
            
            logger.info(f"✅ NATS配置文件已生成: {output_path}")
            logger.info(f"   服务器名称: {config['server_name']}")
            logger.info(f"   监听端口: {config['port']}")
            logger.info(f"   HTTP端口: {config['http_port']}")
            logger.info(f"   JetStream: {'启用' if config['jetstream_enabled'] else '禁用'}")
            logger.info(f"   认证: {'启用' if config['auth_enabled'] else '禁用'}")
            logger.info(f"   集群: {'启用' if config['cluster_enabled'] else '禁用'}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 生成配置文件失败: {e}")
            return False
    
    def print_config_summary(self):
        """打印配置摘要"""
        config = self.config_data or self.load_environment_config()
        
        print("\n" + "="*60)
        print("📋 MarketPrism统一NATS配置摘要")
        print("="*60)
        print(f"服务器名称: {config['server_name']}")
        print(f"监听地址: {config['host']}:{config['port']}")
        print(f"HTTP监控: http://{config['host']}:{config['http_port']}")
        print(f"JetStream: {'✅ 启用' if config['jetstream_enabled'] else '❌ 禁用'}")
        
        if config['jetstream_enabled']:
            print(f"  存储目录: {config['jetstream_store_dir']}")
            print(f"  最大内存: {config['jetstream_max_memory']:,} 字节")
            print(f"  最大文件: {config['jetstream_max_file']:,} 字节")
        
        print(f"认证: {'✅ 启用' if config['auth_enabled'] else '❌ 禁用'}")
        print(f"集群: {'✅ 启用' if config['cluster_enabled'] else '❌ 禁用'}")
        print(f"调试日志: {'✅ 启用' if config['debug'] else '❌ 禁用'}")
        print(f"跟踪日志: {'✅ 启用' if config['trace'] else '❌ 禁用'}")
        print("="*60 + "\n")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='MarketPrism NATS配置渲染器')
    parser.add_argument('--output', '-o', required=True, help='输出配置文件路径')
    parser.add_argument('--template', '-t', help='配置模板文件路径（可选）')
    parser.add_argument('--validate', action='store_true', help='仅验证配置，不生成文件')
    parser.add_argument('--summary', action='store_true', help='显示配置摘要')
    
    args = parser.parse_args()
    
    logger.info("🚀 启动MarketPrism NATS配置渲染器")
    logger.info(f"⏰ 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 创建渲染器
    renderer = NATSConfigRenderer()
    
    try:
        if args.validate:
            # 仅验证配置
            config = renderer.load_environment_config()
            errors = renderer.validate_config(config)
            
            if errors:
                logger.error("❌ 配置验证失败:")
                for error in errors:
                    logger.error(f"  - {error}")
                return 1
            else:
                logger.info("✅ 配置验证通过")
                return 0
        
        elif args.summary:
            # 显示配置摘要
            renderer.print_config_summary()
            return 0
        
        else:
            # 生成配置文件
            success = renderer.render_config_file(args.output)
            if success:
                if args.summary:
                    renderer.print_config_summary()
                return 0
            else:
                return 1
    
    except KeyboardInterrupt:
        logger.info("⏹️ 操作被用户中断")
        return 1
    except Exception as e:
        logger.error(f"❌ 操作异常: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
