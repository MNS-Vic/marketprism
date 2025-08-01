#!/usr/bin/env python3
"""
Docker配置验证脚本
验证所有Docker配置文件和依赖关系
"""

import os
import yaml
import json
from pathlib import Path
from typing import Dict, List, Tuple


class DockerConfigValidator:
    """Docker配置验证器"""
    
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.errors = []
        self.warnings = []
        
    def validate_all(self) -> bool:
        """验证所有配置"""
        print("🔍 开始验证Docker配置...")
        print("=" * 60)
        
        # 验证文件存在性
        self._validate_file_existence()
        
        # 验证Docker Compose配置
        self._validate_docker_compose()
        
        # 验证Dockerfile
        self._validate_dockerfiles()
        
        # 验证启动脚本
        self._validate_entrypoint_scripts()
        
        # 验证配置文件
        self._validate_config_files()
        
        # 生成报告
        self._generate_report()
        
        return len(self.errors) == 0
    
    def _validate_file_existence(self):
        """验证必需文件存在"""
        print("\n📁 验证文件存在性...")
        
        required_files = [
            "docker-compose.production.yml",
            "services/data-collector/Dockerfile",
            "services/data-collector/docker-entrypoint.sh",
            "services/message-broker/Dockerfile.nats",
            "services/message-broker/docker-entrypoint.sh",
            "services/message-broker/nats_config.yaml",
            "services/message-broker/init_jetstream.py",
            "services/data-storage-service/Dockerfile.production",
            "services/data-storage-service/docker-entrypoint.sh",
            "services/data-storage-service/simple_hot_storage.py",
            "services/data-storage-service/scripts/init_clickhouse_tables.py",
            "services/data-storage-service/config/production_tiered_storage_config.yaml"
        ]
        
        for file_path in required_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                print(f"  ✅ {file_path}")
            else:
                self.errors.append(f"缺少必需文件: {file_path}")
                print(f"  ❌ {file_path}")
    
    def _validate_docker_compose(self):
        """验证Docker Compose配置"""
        print("\n🐳 验证Docker Compose配置...")
        
        compose_file = self.project_root / "docker-compose.production.yml"
        if not compose_file.exists():
            self.errors.append("docker-compose.production.yml 不存在")
            return
        
        try:
            with open(compose_file, 'r', encoding='utf-8') as f:
                compose_config = yaml.safe_load(f)
            
            # 验证服务定义
            services = compose_config.get('services', {})
            expected_services = [
                'clickhouse', 'message-broker', 'data-storage',
                'data-collector-binance-spot', 'data-collector-binance-derivatives'
            ]
            
            for service in expected_services:
                if service in services:
                    print(f"  ✅ 服务定义: {service}")
                else:
                    self.errors.append(f"缺少服务定义: {service}")
                    print(f"  ❌ 服务定义: {service}")
            
            # 验证网络配置
            if 'networks' in compose_config:
                print("  ✅ 网络配置存在")
            else:
                self.warnings.append("缺少网络配置")
                print("  ⚠️ 网络配置缺失")
            
            # 验证数据卷配置
            if 'volumes' in compose_config:
                print("  ✅ 数据卷配置存在")
            else:
                self.warnings.append("缺少数据卷配置")
                print("  ⚠️ 数据卷配置缺失")
                
        except Exception as e:
            self.errors.append(f"Docker Compose配置解析失败: {e}")
            print(f"  ❌ 配置解析失败: {e}")
    
    def _validate_dockerfiles(self):
        """验证Dockerfile"""
        print("\n📦 验证Dockerfile...")
        
        dockerfiles = [
            ("services/data-collector/Dockerfile", "data-collector"),
            ("services/message-broker/Dockerfile.nats", "message-broker"),
            ("services/data-storage-service/Dockerfile.production", "data-storage")
        ]
        
        for dockerfile_path, service_name in dockerfiles:
            full_path = self.project_root / dockerfile_path
            if not full_path.exists():
                self.errors.append(f"{service_name} Dockerfile不存在: {dockerfile_path}")
                print(f"  ❌ {service_name}: {dockerfile_path}")
                continue
            
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 基本验证
                if 'FROM' in content:
                    print(f"  ✅ {service_name}: 基础镜像定义正确")
                else:
                    self.errors.append(f"{service_name} Dockerfile缺少FROM指令")
                    print(f"  ❌ {service_name}: 缺少FROM指令")
                
                if 'EXPOSE' in content:
                    print(f"  ✅ {service_name}: 端口暴露配置存在")
                else:
                    self.warnings.append(f"{service_name} Dockerfile缺少EXPOSE指令")
                    print(f"  ⚠️ {service_name}: 缺少EXPOSE指令")
                    
            except Exception as e:
                self.errors.append(f"{service_name} Dockerfile读取失败: {e}")
                print(f"  ❌ {service_name}: 读取失败 - {e}")
    
    def _validate_entrypoint_scripts(self):
        """验证启动脚本"""
        print("\n🚀 验证启动脚本...")
        
        scripts = [
            ("services/data-collector/docker-entrypoint.sh", "data-collector"),
            ("services/message-broker/docker-entrypoint.sh", "message-broker"),
            ("services/data-storage-service/docker-entrypoint.sh", "data-storage")
        ]
        
        for script_path, service_name in scripts:
            full_path = self.project_root / script_path
            if not full_path.exists():
                self.errors.append(f"{service_name} 启动脚本不存在: {script_path}")
                print(f"  ❌ {service_name}: {script_path}")
                continue
            
            # 检查可执行权限
            if os.access(full_path, os.X_OK):
                print(f"  ✅ {service_name}: 启动脚本可执行")
            else:
                self.warnings.append(f"{service_name} 启动脚本缺少可执行权限")
                print(f"  ⚠️ {service_name}: 缺少可执行权限")
            
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 检查shebang
                if content.startswith('#!/bin/bash'):
                    print(f"  ✅ {service_name}: shebang正确")
                else:
                    self.warnings.append(f"{service_name} 启动脚本缺少正确的shebang")
                    print(f"  ⚠️ {service_name}: shebang不正确")
                    
            except Exception as e:
                self.errors.append(f"{service_name} 启动脚本读取失败: {e}")
                print(f"  ❌ {service_name}: 读取失败 - {e}")
    
    def _validate_config_files(self):
        """验证配置文件"""
        print("\n⚙️ 验证配置文件...")
        
        config_files = [
            ("services/message-broker/nats_config.yaml", "NATS配置"),
            ("services/data-storage-service/config/production_tiered_storage_config.yaml", "存储服务配置")
        ]
        
        for config_path, config_name in config_files:
            full_path = self.project_root / config_path
            if not full_path.exists():
                self.errors.append(f"{config_name}文件不存在: {config_path}")
                print(f"  ❌ {config_name}: {config_path}")
                continue
            
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f)
                
                if config_data:
                    print(f"  ✅ {config_name}: YAML格式正确")
                else:
                    self.warnings.append(f"{config_name} 配置为空")
                    print(f"  ⚠️ {config_name}: 配置为空")
                    
            except Exception as e:
                self.errors.append(f"{config_name} 配置解析失败: {e}")
                print(f"  ❌ {config_name}: 解析失败 - {e}")
    
    def _generate_report(self):
        """生成验证报告"""
        print("\n" + "=" * 60)
        print("📊 验证报告")
        print("=" * 60)
        
        total_checks = len(self.errors) + len(self.warnings)
        if total_checks == 0:
            total_checks = 1  # 避免除零
        
        success_rate = max(0, (total_checks - len(self.errors)) / total_checks * 100)
        
        print(f"总体状态: {'✅ 通过' if len(self.errors) == 0 else '❌ 失败'}")
        print(f"成功率: {success_rate:.1f}%")
        print(f"错误数: {len(self.errors)}")
        print(f"警告数: {len(self.warnings)}")
        
        if self.errors:
            print(f"\n❌ 错误详情:")
            for i, error in enumerate(self.errors, 1):
                print(f"  {i}. {error}")
        
        if self.warnings:
            print(f"\n⚠️ 警告详情:")
            for i, warning in enumerate(self.warnings, 1):
                print(f"  {i}. {warning}")
        
        if len(self.errors) == 0:
            print("\n🎉 所有Docker配置验证通过！")
            print("💡 建议:")
            print("  1. 运行 ./scripts/docker_validation.sh build 构建镜像")
            print("  2. 运行 ./scripts/docker_validation.sh start 启动服务")
            print("  3. 使用 docker-compose -f docker-compose.production.yml logs -f 查看日志")
        else:
            print(f"\n🔧 请修复上述 {len(self.errors)} 个错误后重新验证")


def main():
    """主函数"""
    validator = DockerConfigValidator()
    success = validator.validate_all()
    
    if not success:
        exit(1)


if __name__ == "__main__":
    main()
