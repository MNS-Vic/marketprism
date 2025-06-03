#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
MarketPrism配置一致性验证工具

此脚本用于验证MarketPrism项目中的配置文件、docker-compose文件和README.md文档之间的一致性。
主要检查项目包括：
1. 检查docker-compose.yml文件中的服务是否与当前技术栈一致
2. 检查配置文件版本是否与系统版本匹配
3. 检查README.md中的命令示例是否与实际配置一致
4. 检查是否存在冗余配置（如Redis相关配置）
"""

import os
import re
import sys
import yaml
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Set, Optional

# 简化输出，避免编码问题
GREEN_OK = "[OK]"
RED_FAIL = "[FAIL]"
YELLOW_INFO = "[INFO]"

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent.absolute()

# 当前项目技术栈配置
CURRENT_STACK = {
    "message_queue": "nats",  # 消息队列技术（nats或redis）
    "database": "clickhouse",  # 数据库技术
    "monitoring": ["prometheus", "grafana"],  # 监控技术
    "current_version": "1.2.0",  # 当前系统版本
    "deprecated_services": ["redis"],  # 已弃用的服务
    "required_services": ["nats", "clickhouse", "go-collector", "data-ingestion"],  # 必须的服务
    "optional_features": ["ssl"],  # 可选功能
    "optional_files": ["docker-compose.ssl.yml"]  # 可选的配置文件
}

def print_result(message: str, success: bool, details: Optional[str] = None) -> None:
    """打印检查结果"""
    if success:
        print(f"{GREEN_OK} {message}")
    else:
        print(f"{RED_FAIL} {message}")
        if details:
            print(f"  {details}")
    print()

def load_yaml_file(file_path: Path) -> dict:
    """加载YAML文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"{RED_FAIL} 错误: 无法加载YAML文件 {file_path}: {e}")
        return {}

def check_docker_compose() -> Tuple[bool, str]:
    """检查docker-compose.yml文件中的服务是否与当前技术栈一致"""
    print(f"{YELLOW_INFO} 检查docker-compose.yml...")
    docker_compose_file = ROOT_DIR / "docker-compose.yml"
    
    if not docker_compose_file.exists():
        print(f"{RED_FAIL} 找不到docker-compose.yml文件: {docker_compose_file}")
        return False, f"找不到docker-compose.yml文件: {docker_compose_file}"
    
    compose_data = load_yaml_file(docker_compose_file)
    if not compose_data:
        return False, "docker-compose.yml文件为空或格式错误"
    
    services = compose_data.get("services", {})
    volumes = compose_data.get("volumes", {})
    
    # 检查必须的服务是否存在
    for required_service in CURRENT_STACK["required_services"]:
        if required_service not in services:
            return False, f"缺少必需的服务: {required_service}"
    
    # 检查是否存在已弃用的服务
    for deprecated_service in CURRENT_STACK["deprecated_services"]:
        if deprecated_service in services:
            return False, f"发现已弃用的服务: {deprecated_service}"
    
    # 检查服务依赖关系
    for service_name, service_config in services.items():
        if "depends_on" in service_config and isinstance(service_config["depends_on"], list):
            for dependency in service_config["depends_on"]:
                if dependency in CURRENT_STACK["deprecated_services"]:
                    return False, f"服务 {service_name} 依赖于已弃用的服务: {dependency}"
    
    # 检查环境变量
    for service_name, service_config in services.items():
        if "environment" in service_config:
            env_vars = service_config["environment"]
            if isinstance(env_vars, list):
                for env_var in env_vars:
                    if isinstance(env_var, str) and "REDIS" in env_var:
                        return False, f"服务 {service_name} 包含Redis相关环境变量: {env_var}"
            elif isinstance(env_vars, dict):
                for key, value in env_vars.items():
                    if "REDIS" in key:
                        return False, f"服务 {service_name} 包含Redis相关环境变量: {key}={value}"
    
    # 检查数据卷
    for deprecated_service in CURRENT_STACK["deprecated_services"]:
        volume_name = f"{deprecated_service}_data"
        if volume_name in volumes:
            return False, f"发现已弃用的数据卷: {volume_name}"
    
    # 检查SSL配置文件（如果存在）
    ssl_compose_file = ROOT_DIR / "docker-compose.ssl.yml"
    if ssl_compose_file.exists():
        print(f"{YELLOW_INFO} 检查docker-compose.ssl.yml...")
        ssl_compose_data = load_yaml_file(ssl_compose_file)
        if not ssl_compose_data:
            return False, "docker-compose.ssl.yml文件为空或格式错误"
        
        ssl_services = ssl_compose_data.get("services", {})
        
        # 检查必须的服务是否存在于SSL配置中
        for required_service in CURRENT_STACK["required_services"]:
            if required_service not in ssl_services:
                return False, f"docker-compose.ssl.yml中缺少必需的服务: {required_service}"
        
        # 检查是否存在已弃用的服务于SSL配置中
        for deprecated_service in CURRENT_STACK["deprecated_services"]:
            if deprecated_service in ssl_services:
                return False, f"docker-compose.ssl.yml中发现已弃用的服务: {deprecated_service}"
    
    return True, "docker-compose配置与技术栈一致"

def check_config_files() -> Tuple[bool, str]:
    """检查配置文件版本是否与系统版本匹配"""
    print(f"{YELLOW_INFO} 检查配置文件...")
    config_dir = ROOT_DIR / "config"
    if not config_dir.exists() or not config_dir.is_dir():
        return False, f"找不到配置目录: {config_dir}"
    
    # 检查主配置文件
    nats_config_file = config_dir / "nats_base.yaml"
    if not nats_config_file.exists():
        return False, f"找不到NATS主配置文件: {nats_config_file}"
    
    config_data = load_yaml_file(nats_config_file)
    if not config_data:
        return False, "NATS配置文件为空或格式错误"
    
    # 检查配置版本
    config_version = config_data.get("config_version", "未知")
    if config_version != CURRENT_STACK["current_version"]:
        return False, f"配置文件版本 ({config_version}) 与系统版本 ({CURRENT_STACK['current_version']}) 不匹配"
    
    # 检查Redis相关配置
    if "redis" in config_data:
        if config_data.get("redis", {}).get("host", "") != "":
            return False, "配置文件中存在Redis相关配置且不是空配置"
    
    # 深度检查所有配置文件
    for config_file in config_dir.glob("*.yaml"):
        config_data = load_yaml_file(config_file)
        if not config_data:
            continue
        
        # 递归检查是否有Redis相关配置
        def check_redis_config(cfg, path=""):
            if isinstance(cfg, dict):
                for key, value in cfg.items():
                    new_path = f"{path}.{key}" if path else key
                    if key.lower() == "redis":
                        # 检查是否是实际配置还是占位配置（允许存在空的redis部分）
                        if isinstance(value, dict) and value.get("host", "") != "":
                            return False, f"在配置路径 {new_path} 中发现Redis配置"
                    result, msg = check_redis_config(value, new_path)
                    if not result:
                        return result, msg
            elif isinstance(cfg, list):
                for i, item in enumerate(cfg):
                    new_path = f"{path}[{i}]"
                    result, msg = check_redis_config(item, new_path)
                    if not result:
                        return result, msg
            return True, ""
        
        result, msg = check_redis_config(config_data)
        if not result:
            return False, f"在配置文件 {config_file.name} 中: {msg}"
    
    return True, "配置文件版本与系统版本匹配"

def check_readme() -> Tuple[bool, str]:
    """检查README.md中的命令示例是否与实际配置一致"""
    print(f"{YELLOW_INFO} 检查README.md...")
    readme_file = ROOT_DIR / "README.md"
    if not readme_file.exists():
        return False, f"找不到README.md文件: {readme_file}"
    
    try:
        with open(readme_file, 'r', encoding='utf-8') as f:
            readme_content = f.read()
    except Exception as e:
        return False, f"无法读取README.md文件: {e}"
    
    # 检查是否有启动Redis的命令
    redis_command_pattern = r"docker-compose\s+up\s+-d\s+.*redis[^a-zA-Z0-9_-]"
    redis_commands = re.findall(redis_command_pattern, readme_content)
    if redis_commands:
        return False, f"README.md中包含启动Redis的命令: {redis_commands[0]}"
    
    # 检查技术栈描述是否准确
    if "Redis" in readme_content and "消息队列" in readme_content.split("Redis")[0].split("。")[-1]:
        return False, "README.md中将Redis描述为消息队列组件"
    
    # 检查代码示例中是否有Redis客户端
    redis_client_pattern = r"(redis\.Redis|redis_client|RedisClient)"
    redis_clients = re.findall(redis_client_pattern, readme_content)
    
    # 如果存在Redis相关代码，但位于"已弃用"或"历史版本"的标记内，则允许
    if redis_clients:
        # 检查是否在弃用或历史版本部分
        for client in redis_clients:
            # 这个简单检查可能不够完善，但基本能判断是否在历史代码部分
            if "已弃用" not in readme_content.split(client)[0][-200:] and "历史版本" not in readme_content.split(client)[0][-200:]:
                return False, f"README.md中包含Redis客户端代码示例: {client}"
    
    return True, "README.md中的命令与实际配置一致"

def check_ssl_consistency() -> Tuple[bool, str]:
    """检查SSL相关配置的一致性"""
    print(f"{YELLOW_INFO} 检查SSL配置一致性...")
    # 检查SSL目录（如果注释了则跳过）
    ssl_dir = ROOT_DIR / "ssl-certs"
    ssl_compose_file = ROOT_DIR / "docker-compose.ssl.yml"
    ssl_guide_file = ROOT_DIR / "docs" / "ssl_config_guide.md"
    
    # 如果不存在SSL配置文件，则跳过此检查
    if not ssl_compose_file.exists():
        return True, "未使用SSL配置"
    
    # 检查SSL指南文档
    if not ssl_guide_file.exists():
        return False, f"找不到SSL配置指南文件: {ssl_guide_file}"
    
    # 检查SSL配置是否与主配置文件一致
    nats_config_file = ROOT_DIR / "config" / "nats_base.yaml"
    if nats_config_file.exists():
        nats_config = load_yaml_file(nats_config_file)
        
        # 检查是否有SSL相关配置（可以是注释掉的，用字符串检查即可）
        nats_config_str = str(nats_config)
        if "security" not in nats_config_str and "ssl" not in nats_config_str:
            return False, "主配置文件中缺少SSL相关配置选项"
    
    return True, "SSL配置一致"

def main() -> None:
    """主函数"""
    parser = argparse.ArgumentParser(description="MarketPrism配置一致性验证工具")
    parser.add_argument("--fix", action="store_true", help="尝试自动修复发现的问题")
    parser.add_argument("--verbose", action="store_true", help="显示详细输出")
    args = parser.parse_args()
    
    print(f"{YELLOW_INFO} MarketPrism配置一致性验证工具 v{CURRENT_STACK['current_version']}")
    print(f"{YELLOW_INFO} ============================================")
    print()
    
    # 收集所有检查结果
    results = []
    
    # 检查docker-compose.yml
    compose_success, compose_message = check_docker_compose()
    print_result("docker-compose配置与技术栈一致", compose_success, compose_message if not compose_success else None)
    results.append(compose_success)
    
    # 检查配置文件
    config_success, config_message = check_config_files()
    print_result("配置文件版本与系统版本匹配", config_success, config_message if not config_success else None)
    results.append(config_success)
    
    # 检查README.md
    readme_success, readme_message = check_readme()
    print_result("README.md中的命令与实际配置一致", readme_success, readme_message if not readme_success else None)
    results.append(readme_success)
    
    # 检查SSL配置一致性
    ssl_success, ssl_message = check_ssl_consistency()
    print_result("SSL配置一致性", ssl_success, ssl_message if not ssl_success else None)
    results.append(ssl_success)
    
    print(f"{YELLOW_INFO} 验证完成。检查项目配置与当前技术栈的一致性。")
    
    # 如果有任何失败的检查
    if not all(results):
        print(f"{RED_FAIL} 验证失败！请解决上述问题。")
        sys.exit(1)
    else:
        print(f"{GREEN_OK} 所有检查通过！")

if __name__ == "__main__":
    main() 