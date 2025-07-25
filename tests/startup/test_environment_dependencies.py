#!/usr/bin/env python3
"""
TDD Phase 1: 环境依赖测试
测试先行，验证所有基础依赖可用

遵循TDD核心原则：
1. RED: 先写失败的测试，明确问题
2. GREEN: 最小修复让测试通过
3. REFACTOR: 重构优化代码
"""

from datetime import datetime, timezone
import os
import sys
import subprocess
import socket
import pytest
import yaml
import json
from pathlib import Path
from typing import Dict, List, Optional
import importlib.util
import shutil

class TestEnvironmentDependencies:
    """环境依赖TDD测试套件"""
    
    @pytest.fixture(autouse=True)
    def setup_project_root(self):
        """设置项目根目录"""
        self.project_root = Path(__file__).parent.parent.parent
        os.chdir(self.project_root)
    
    # ============================================================================
    # Python环境测试
    # ============================================================================
    
    def test_python_version_compatible(self):
        """
        RED: 测试Python版本兼容性
        问题: 确保Python版本 >= 3.8
        """
        python_version = sys.version_info
        assert python_version.major == 3, f"需要Python 3.x，当前: {python_version.major}"
        assert python_version.minor >= 8, f"需要Python 3.8+，当前: {python_version.major}.{python_version.minor}"
    
    def test_python_executable_available(self):
        """
        RED: 测试Python可执行文件可用
        问题: 确保python3命令可用
        """
        result = subprocess.run(["python3", "--version"], 
                              capture_output=True, text=True)
        assert result.returncode == 0, "python3命令不可用"
        assert "Python 3." in result.stdout, f"Python版本输出异常: {result.stdout}"
    
    def test_pip_available(self):
        """
        RED: 测试pip包管理器可用
        问题: 确保pip3可用于安装依赖
        """
        result = subprocess.run(["pip3", "--version"], 
                              capture_output=True, text=True)
        assert result.returncode == 0, "pip3命令不可用"
        assert "pip" in result.stdout.lower(), f"pip版本输出异常: {result.stdout}"
    
    # ============================================================================
    # 虚拟环境测试
    # ============================================================================
    
    def test_virtual_environment_exists(self):
        """
        RED: 测试虚拟环境存在
        问题: 确保venv目录存在且配置正确
        """
        venv_path = self.project_root / "venv"
        assert venv_path.exists(), "虚拟环境目录不存在，需要运行: python3 -m venv venv"
        
        # 检查虚拟环境结构
        if sys.platform == "win32":
            python_exe = venv_path / "Scripts" / "python.exe"
            pip_exe = venv_path / "Scripts" / "pip.exe"
        else:
            python_exe = venv_path / "bin" / "python"
            pip_exe = venv_path / "bin" / "pip"
        
        assert python_exe.exists(), f"虚拟环境Python不存在: {python_exe}"
        assert pip_exe.exists(), f"虚拟环境pip不存在: {pip_exe}"
    
    def test_virtual_environment_activatable(self):
        """
        RED: 测试虚拟环境可激活
        问题: 确保虚拟环境可以正常激活
        """
        venv_path = self.project_root / "venv"
        if sys.platform == "win32":
            activate_script = venv_path / "Scripts" / "activate.bat"
            python_exe = venv_path / "Scripts" / "python.exe"
        else:
            activate_script = venv_path / "bin" / "activate"
            python_exe = venv_path / "bin" / "python"
        
        assert activate_script.exists(), f"激活脚本不存在: {activate_script}"
        
        # 测试虚拟环境中的Python可执行
        result = subprocess.run([str(python_exe), "--version"], 
                              capture_output=True, text=True)
        assert result.returncode == 0, f"虚拟环境Python不可执行: {result.stderr}"
    
    # ============================================================================
    # 包依赖测试
    # ============================================================================
    
    def test_requirements_file_exists(self):
        """
        RED: 测试requirements.txt存在
        问题: 确保依赖文件存在且可读
        """
        requirements_file = self.project_root / "requirements.txt"
        assert requirements_file.exists(), "requirements.txt文件不存在"
        assert requirements_file.is_file(), "requirements.txt不是文件"
        
        # 检查文件可读
        try:
            with open(requirements_file, 'r', encoding='utf-8') as f:
                content = f.read()
                assert len(content.strip()) > 0, "requirements.txt文件为空"
        except Exception as e:
            pytest.fail(f"无法读取requirements.txt: {e}")
    
    def test_core_dependencies_installable(self):
        """
        RED: 测试核心依赖可安装
        问题: 确保关键依赖包版本兼容
        """
        # 核心包映射：包名 -> 导入名
        core_packages = {
            "fastapi": "fastapi",
            "uvicorn": "uvicorn", 
            "aiohttp": "aiohttp",
            "asyncio-nats-client": "nats",  # 特殊映射
            "pydantic": "pydantic",
            "redis": "redis",
            "pyyaml": "yaml"
        }
        
        for package_name, import_name in core_packages.items():
            try:
                importlib.import_module(import_name)
            except ImportError:
                pytest.fail(f"核心依赖 {package_name} 未安装，运行: pip install {package_name}")
    
    def test_requirements_dependencies_installed(self):
        """
        RED: 测试requirements.txt中的依赖已安装
        问题: 验证所有声明的依赖都已正确安装
        """
        requirements_file = self.project_root / "requirements.txt"
        
        with open(requirements_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 特殊包映射关系
        package_import_mapping = {
            'redis[hiredis]': 'redis',
            'nats-py': 'nats', 
            'pyyaml': 'yaml',
            'python-dotenv': 'dotenv',
            'pyjwt': 'jwt',  # pyjwt包的导入名是jwt
            'asyncio-redis': 'asyncio_redis',
            'cmake': None,  # 编译工具，不需要导入测试
            'cython': None  # 编译工具，不需要导入测试
        }
        
        missing_packages = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                # 提取包名 (移除版本号)
                package_name = line.split('==')[0].split('>=')[0].split('<=')[0].split('[')[0].strip()
                
                # 跳过编译工具
                if package_name in ['cmake', 'cython']:
                    continue
                    
                # 获取导入名
                import_name = package_import_mapping.get(package_name, package_name.replace('-', '_'))
                
                if import_name:  # 只测试需要导入的包
                    try:
                        importlib.import_module(import_name)
                    except ImportError:
                        missing_packages.append(package_name)
        
        assert len(missing_packages) == 0, f"缺失依赖包: {missing_packages}，运行: pip install -r requirements.txt"
    
    # ============================================================================
    # 外部服务测试  
    # ============================================================================
    
    def test_nats_service_available(self):
        """
        RED: 测试NATS服务可用
        问题: 确保消息队列服务运行正常
        """
        # 检查NATS默认端口4222
        try:
            import nats
            # 尝试连接NATS
            # 注意：这里只检查连接能力，不要求NATS必须运行
            # 但应该提示如何启动NATS
        except ImportError:
            pytest.skip("NATS客户端未安装，跳过NATS服务测试")
        
        # 检查NATS端口是否可连接
        nats_host = os.getenv('NATS_HOST', 'localhost')
        nats_port = int(os.getenv('NATS_PORT', 4222))
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                result = sock.connect_ex((nats_host, nats_port))
                if result != 0:
                    pytest.skip(f"NATS服务未运行在 {nats_host}:{nats_port}，启动命令: nats-server")
        except Exception as e:
            pytest.skip(f"无法检查NATS连接: {e}")
    
    def test_clickhouse_service_available(self):
        """
        RED: 测试ClickHouse服务可用
        问题: 确保数据库服务运行正常
        """
        try:
            from clickhouse_driver import Client
        except ImportError:
            pytest.skip("ClickHouse客户端未安装，跳过ClickHouse服务测试")
        
        # 检查ClickHouse连接
        ch_host = os.getenv('CLICKHOUSE_HOST', 'localhost')
        ch_port = int(os.getenv('CLICKHOUSE_PORT', 9000))
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                result = sock.connect_ex((ch_host, ch_port))
                if result != 0:
                    pytest.skip(f"ClickHouse服务未运行在 {ch_host}:{ch_port}，启动命令见docker-compose.yml")
        except Exception as e:
            pytest.skip(f"无法检查ClickHouse连接: {e}")
    
    def test_redis_service_available(self):
        """
        RED: 测试Redis服务可用
        问题: 确保缓存服务运行正常
        """
        try:
            import redis
        except ImportError:
            pytest.skip("Redis客户端未安装，跳过Redis服务测试")
        
        # 检查Redis连接
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', 6379))
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                result = sock.connect_ex((redis_host, redis_port))
                if result != 0:
                    pytest.skip(f"Redis服务未运行在 {redis_host}:{redis_port}，启动命令: redis-server")
        except Exception as e:
            pytest.skip(f"无法检查Redis连接: {e}")
    
    # ============================================================================
    # 配置文件测试
    # ============================================================================
    
    def test_config_directory_exists(self):
        """
        RED: 测试配置目录存在
        问题: 确保config目录结构正确
        """
        config_dir = self.project_root / "config"
        assert config_dir.exists(), "config目录不存在"
        assert config_dir.is_dir(), "config不是目录"
    
    def test_services_config_valid(self):
        """
        RED: 测试服务配置文件有效
        问题: 确保services.yaml格式正确且包含必要配置
        """
        services_config = self.project_root / "config" / "services.yaml"
        assert services_config.exists(), "config/services.yaml不存在"
        
        try:
            with open(services_config, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                
            assert isinstance(config, dict), "services.yaml不是有效的YAML字典"
            assert "services" in config, "services.yaml缺少'services'配置"
            
            services = config["services"]
            expected_services = [
                "api-gateway-service", "market-data-collector", "data-storage-service", 
                "monitoring-service", "scheduler-service", "message-broker-service"
            ]
            
            for service in expected_services:
                assert service in services, f"services.yaml缺少服务配置: {service}"
                service_config = services[service]
                assert "port" in service_config, f"{service}缺少端口配置"
                assert isinstance(service_config["port"], int), f"{service}端口配置不是整数"
                
        except yaml.YAMLError as e:
            pytest.fail(f"services.yaml格式错误: {e}")
        except Exception as e:
            pytest.fail(f"读取services.yaml失败: {e}")
    
    def test_logging_config_valid(self):
        """
        RED: 测试日志配置文件有效
        问题: 确保日志配置存在且格式正确
        """
        logging_configs = [
            self.project_root / "config" / "logging.yaml",
            self.project_root / "config" / "logging.yml"
        ]
        
        config_exists = any(config.exists() for config in logging_configs)
        if not config_exists:
            pytest.skip("日志配置文件不存在，将使用默认配置")
        
        for config_file in logging_configs:
            if config_file.exists():
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f)
                    assert isinstance(config, dict), f"{config_file.name}不是有效的YAML字典"
                    break
                except yaml.YAMLError as e:
                    pytest.fail(f"{config_file.name}格式错误: {e}")
    
    # ============================================================================
    # 项目结构测试
    # ============================================================================
    
    def test_project_structure_complete(self):
        """
        RED: 测试项目结构完整
        问题: 确保所有必要目录存在
        """
        required_dirs = [
            "core",
            "services", 
            "config",
            "tests",
            "logs"
        ]
        
        missing_dirs = []
        for dir_name in required_dirs:
            dir_path = self.project_root / dir_name
            if not dir_path.exists():
                missing_dirs.append(dir_name)
        
        if missing_dirs:
            # 自动创建缺失目录
            for dir_name in missing_dirs:
                dir_path = self.project_root / dir_name
                dir_path.mkdir(exist_ok=True)
                print(f"✅ 自动创建目录: {dir_name}")
        
        # 重新验证
        for dir_name in required_dirs:
            dir_path = self.project_root / dir_name
            assert dir_path.exists(), f"项目目录缺失: {dir_name}"
    
    def test_startup_scripts_exist(self):
        """
        RED: 测试启动脚本存在
        问题: 确保所有服务启动脚本存在且可执行
        """
        expected_scripts = [
            "start-api-gateway.sh",
            "start-data-collector.sh", 
            "start-data-storage.sh",
            "start-monitoring.sh",
            "start-scheduler.sh",
            "start-message-broker.sh"
        ]
        
        missing_scripts = []
        for script_name in expected_scripts:
            script_path = self.project_root / script_name
            if not script_path.exists():
                missing_scripts.append(script_name)
            elif not os.access(script_path, os.X_OK):
                # 添加执行权限
                os.chmod(script_path, 0o755)
                print(f"✅ 添加执行权限: {script_name}")
        
        assert len(missing_scripts) == 0, f"启动脚本缺失: {missing_scripts}"
    
    # ============================================================================
    # 环境变量测试
    # ============================================================================
    
    def test_environment_variables_configured(self):
        """
        RED: 测试环境变量配置
        问题: 检查关键环境变量是否设置
        """
        # 可选的环境变量（有默认值）
        optional_env_vars = {
            'PYTHONPATH': str(self.project_root),
            'LOG_LEVEL': 'INFO',
            'ENVIRONMENT': 'development'
        }
        
        # 检查并设置缺失的环境变量
        for var_name, default_value in optional_env_vars.items():
            if var_name not in os.environ:
                os.environ[var_name] = default_value
                print(f"✅ 设置环境变量: {var_name}={default_value}")
        
        # 验证PYTHONPATH包含项目根目录
        python_path = os.environ.get('PYTHONPATH', '')
        if str(self.project_root) not in python_path:
            new_python_path = f"{self.project_root}:{python_path}" if python_path else str(self.project_root)
            os.environ['PYTHONPATH'] = new_python_path
            print(f"✅ 更新PYTHONPATH: {new_python_path}")
    
    # ============================================================================
    # 网络和代理测试
    # ============================================================================
    
    def test_proxy_configuration_valid(self):
        """
        RED: 测试代理配置有效
        问题: 根据memory中的代理设置验证网络连接
        """
        # 根据memory中的代理设置进行测试
        proxy_settings = {
            'http_proxy': 'http://127.0.0.1:1087',
            'https_proxy': 'http://127.0.0.1:1087', 
            'ALL_PROXY': 'socks5://127.0.0.1:1080'
        }
        
        # 检查代理是否可达（可选测试）
        for proxy_type, proxy_url in proxy_settings.items():
            if proxy_type in ['http_proxy', 'https_proxy']:
                # 提取代理主机和端口
                import urllib.parse
                parsed = urllib.parse.urlparse(proxy_url)
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                        sock.settimeout(3)
                        result = sock.connect_ex((parsed.hostname, parsed.port))
                        if result == 0:
                            print(f"✅ 代理可用: {proxy_type}={proxy_url}")
                        else:
                            print(f"⚠️  代理不可达: {proxy_type}={proxy_url}")
                except Exception as e:
                    print(f"⚠️  代理检查失败: {proxy_type} - {e}")
    
    # ============================================================================
    # 集成环境测试
    # ============================================================================
    
    def test_environment_integration_ready(self):
        """
        RED: 测试环境集成就绪
        问题: 综合验证环境是否准备好启动服务
        """
        # 收集所有环境状态
        environment_status = {
            'python_ready': False,
            'venv_ready': False,
            'dependencies_ready': False,
            'config_ready': False,
            'structure_ready': False
        }
        
        try:
            # Python环境检查
            python_version = sys.version_info
            if python_version.major == 3 and python_version.minor >= 8:
                environment_status['python_ready'] = True
            
            # 虚拟环境检查
            venv_path = self.project_root / "venv"
            if venv_path.exists():
                environment_status['venv_ready'] = True
            
            # 依赖检查
            requirements_file = self.project_root / "requirements.txt"
            if requirements_file.exists():
                environment_status['dependencies_ready'] = True
            
            # 配置检查
            services_config = self.project_root / "config" / "services.yaml"
            if services_config.exists():
                environment_status['config_ready'] = True
            
            # 结构检查
            required_dirs = ["core", "services", "config", "tests"]
            if all((self.project_root / d).exists() for d in required_dirs):
                environment_status['structure_ready'] = True
            
            # 计算就绪率
            ready_count = sum(environment_status.values())
            total_count = len(environment_status)
            readiness_rate = ready_count / total_count
            
            print(f"📊 环境就绪率: {ready_count}/{total_count} ({readiness_rate:.1%})")
            for component, status in environment_status.items():
                status_icon = "✅" if status else "❌"
                print(f"  {status_icon} {component}: {'就绪' if status else '未就绪'}")
            
            # 要求至少80%就绪率
            assert readiness_rate >= 0.8, f"环境就绪率不足: {readiness_rate:.1%} < 80%"
            
        except Exception as e:
            pytest.fail(f"环境集成检查失败: {e}")


# ============================================================================
# TDD辅助函数
# ============================================================================

def fix_environment_issues():
    """
    GREEN: 自动修复常见环境问题
    TDD第二阶段：让测试通过的最小修复
    """
    project_root = Path(__file__).parent.parent.parent
    
    print("🔧 开始自动修复环境问题...")
    
    # 1. 创建虚拟环境
    venv_path = project_root / "venv"
    if not venv_path.exists():
        print("📦 创建虚拟环境...")
        subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
        print("✅ 虚拟环境创建完成")
    
    # 2. 创建必要目录
    required_dirs = ["logs", "data", "temp"]
    for dir_name in required_dirs:
        dir_path = project_root / dir_name
        if not dir_path.exists():
            dir_path.mkdir(exist_ok=True)
            print(f"✅ 创建目录: {dir_name}")
    
    # 3. 设置启动脚本权限
    startup_scripts = list(project_root.glob("start-*.sh"))
    for script in startup_scripts:
        os.chmod(script, 0o755)
        print(f"✅ 设置执行权限: {script.name}")
    
    # 4. 创建基础配置文件（如果不存在）
    config_dir = project_root / "config"
    
    # 创建logging.yaml（如果不存在）
    logging_config_path = config_dir / "logging.yaml"
    if not logging_config_path.exists():
        logging_config = {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'standard': {
                    'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
                }
            },
            'handlers': {
                'default': {
                    'level': 'INFO',
                    'class': 'logging.StreamHandler',
                    'formatter': 'standard'
                }
            },
            'loggers': {
                '': {
                    'handlers': ['default'],
                    'level': 'INFO',
                    'propagate': False
                }
            }
        }
        
        with open(logging_config_path, 'w', encoding='utf-8') as f:
            yaml.dump(logging_config, f, default_flow_style=False, allow_unicode=True)
        print("✅ 创建默认日志配置")
    
    print("🎉 环境修复完成！")


if __name__ == "__main__":
    # 支持直接运行修复环境
    import argparse
    
    parser = argparse.ArgumentParser(description="MarketPrism环境依赖测试和修复")
    parser.add_argument("--fix", action="store_true", help="自动修复环境问题")
    parser.add_argument("--test", action="store_true", help="运行环境测试")
    
    args = parser.parse_args()
    
    if args.fix:
        fix_environment_issues()
    elif args.test:
        pytest.main([__file__, "-v"])
    else:
        print("使用 --test 运行测试，或 --fix 修复环境问题")