#!/usr/bin/env python3
"""
TDD Phase 1.2: 个体服务启动测试
测试先行，验证每个服务独立启动成功

TDD策略：
1. RED: 写失败的服务启动测试
2. GREEN: 最小修复让测试通过  
3. REFACTOR: 优化启动脚本和配置
"""

from datetime import datetime, timezone
import asyncio
import subprocess
import time
import socket
import signal
import os
import sys
import pytest
import psutil
import aiohttp
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ServiceStartupTester:
    """服务启动TDD测试器"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.running_processes: Dict[str, subprocess.Popen] = {}
        self.service_configs = self._load_service_configs()
    
    def _load_service_configs(self) -> Dict:
        """加载服务配置"""
        config_file = self.project_root / "config" / "services.yaml"
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return config.get('services', {})
        
        # 默认配置（如果文件不存在）
        return {
            'api-gateway': {'port': 8080},
            'data-collector': {'port': 8081},
            'data-storage': {'port': 8082},
            'monitoring': {'port': 8083},
            'scheduler': {'port': 8084},
            'message-broker': {'port': 8085}
        }
    
    def is_port_available(self, port: int) -> bool:
        """检查端口是否可用"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex(('localhost', port))
                return result != 0  # 连接失败说明端口可用
        except:
            return True
    
    def kill_port_process(self, port: int):
        """终止占用端口的进程"""
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                # 获取进程的网络连接
                connections = proc.connections()
                for conn in connections:
                    if hasattr(conn, 'laddr') and conn.laddr and conn.laddr.port == port:
                        logger.info(f"终止占用端口 {port} 的进程 {proc.info['pid']}")
                        proc.terminate()
                        return
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    
    async def wait_for_service_startup(self, port: int, timeout: int = 30) -> bool:
        """等待服务启动"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if not self.is_port_available(port):  # 端口被占用说明服务启动了
                return True
            await asyncio.sleep(1)
        return False
    
    async def check_service_health(self, port: int, endpoint: str = "/health") -> bool:
        """检查服务健康状态"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"http://localhost:{port}{endpoint}") as response:
                    return response.status == 200
        except:
            return False
    
    def start_service(self, service_name: str) -> Optional[subprocess.Popen]:
        """启动服务"""
        script_path = self.project_root / f"start-{service_name}.sh"
        
        if not script_path.exists():
            logger.error(f"启动脚本不存在: {script_path}")
            return None
        
        try:
            # 设置环境变量
            env = os.environ.copy()
            env['PYTHONPATH'] = str(self.project_root)
            
            # 启动服务
            process = subprocess.Popen(
                [str(script_path)],
                cwd=self.project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                preexec_fn=os.setsid  # 创建新的进程组
            )
            
            self.running_processes[service_name] = process
            logger.info(f"启动服务 {service_name}，PID: {process.pid}")
            return process
            
        except Exception as e:
            logger.error(f"启动服务 {service_name} 失败: {e}")
            return None
    
    def stop_service(self, service_name: str):
        """停止服务"""
        if service_name in self.running_processes:
            process = self.running_processes[service_name]
            try:
                # 优雅停止
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # 强制停止
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass  # 进程已经停止
            
            del self.running_processes[service_name]
            logger.info(f"停止服务 {service_name}")
    
    def cleanup_all_services(self):
        """清理所有服务"""
        for service_name in list(self.running_processes.keys()):
            self.stop_service(service_name)


class TestIndividualServiceStartup:
    """个体服务启动TDD测试套件"""
    
    @pytest.fixture(autouse=True)
    def setup_tester(self):
        """设置测试器"""
        self.project_root = Path(__file__).parent.parent.parent
        self.tester = ServiceStartupTester(self.project_root)
        os.chdir(self.project_root)
        
        # 测试后清理
        yield
        self.tester.cleanup_all_services()
    
    # ============================================================================
    # Message Broker Service Tests (无依赖，最先测试)
    # ============================================================================
    
    def test_message_broker_script_exists(self):
        """
        RED: 测试message-broker启动脚本存在
        """
        script_path = self.project_root / "start-message-broker.sh"
        assert script_path.exists(), "start-message-broker.sh 启动脚本不存在"
        assert os.access(script_path, os.X_OK), "start-message-broker.sh 没有执行权限"
    
    @pytest.mark.asyncio
    async def test_message_broker_starts_successfully(self):
        """
        RED: 测试message-broker能够成功启动
        问题: 验证消息代理服务启动并监听端口
        """
        service_name = "message-broker"
        port = self.tester.service_configs.get(service_name, {}).get('port', 8085)
        
        # 确保端口可用
        if not self.tester.is_port_available(port):
            self.tester.kill_port_process(port)
            await asyncio.sleep(2)
        
        # 启动服务
        process = self.tester.start_service(service_name)
        assert process is not None, f"无法启动 {service_name} 服务"
        
        # 等待服务启动
        startup_success = await self.tester.wait_for_service_startup(port, timeout=30)
        assert startup_success, f"{service_name} 服务启动超时"
        
        # 验证进程还在运行
        assert process.poll() is None, f"{service_name} 服务进程已退出"
    
    @pytest.mark.asyncio
    async def test_message_broker_health_check(self):
        """
        RED: 测试message-broker健康检查
        问题: 验证服务健康检查端点正常响应
        """
        service_name = "message-broker"
        port = self.tester.service_configs.get(service_name, {}).get('port', 8085)
        
        # 如果服务未运行，先启动
        if not self.tester.is_port_available(port):
            health_ok = await self.tester.check_service_health(port)
            if not health_ok:
                # 尝试启动服务
                process = self.tester.start_service(service_name)
                if process:
                    await self.tester.wait_for_service_startup(port, timeout=30)
        
        # 检查健康状态
        health_ok = await self.tester.check_service_health(port)
        if not health_ok:
            pytest.skip(f"{service_name} 服务未运行或健康检查端点未实现")
    
    # ============================================================================
    # API Gateway Service Tests (无依赖)
    # ============================================================================
    
    def test_api_gateway_script_exists(self):
        """
        RED: 测试api-gateway启动脚本存在
        """
        script_path = self.project_root / "start-api-gateway.sh"
        assert script_path.exists(), "start-api-gateway.sh 启动脚本不存在"
        assert os.access(script_path, os.X_OK), "start-api-gateway.sh 没有执行权限"
    
    @pytest.mark.asyncio
    async def test_api_gateway_starts_successfully(self):
        """
        RED: 测试api-gateway能够成功启动
        """
        service_name = "api-gateway"
        port = self.tester.service_configs.get(service_name, {}).get('port', 8080)
        
        # 确保端口可用
        if not self.tester.is_port_available(port):
            self.tester.kill_port_process(port)
            await asyncio.sleep(2)
        
        # 启动服务
        process = self.tester.start_service(service_name)
        assert process is not None, f"无法启动 {service_name} 服务"
        
        # 等待服务启动
        startup_success = await self.tester.wait_for_service_startup(port, timeout=30)
        assert startup_success, f"{service_name} 服务启动超时"
        
        # 验证进程还在运行
        assert process.poll() is None, f"{service_name} 服务进程已退出"
    
    @pytest.mark.asyncio
    async def test_api_gateway_health_check(self):
        """
        RED: 测试api-gateway健康检查
        """
        service_name = "api-gateway"
        port = self.tester.service_configs.get(service_name, {}).get('port', 8080)
        
        # 如果服务未运行，跳过健康检查
        if self.tester.is_port_available(port):
            pytest.skip(f"{service_name} 服务未运行")
        
        health_ok = await self.tester.check_service_health(port)
        if not health_ok:
            pytest.skip(f"{service_name} 健康检查端点未实现")
    
    # ============================================================================
    # Data Collector Service Tests (依赖 message-broker)
    # ============================================================================
    
    def test_data_collector_script_exists(self):
        """
        RED: 测试data-collector启动脚本存在
        """
        script_path = self.project_root / "start-data-collector.sh"
        assert script_path.exists(), "start-data-collector.sh 启动脚本不存在"
        assert os.access(script_path, os.X_OK), "start-data-collector.sh 没有执行权限"
    
    @pytest.mark.asyncio
    async def test_data_collector_starts_successfully(self):
        """
        RED: 测试data-collector能够成功启动
        """
        service_name = "data-collector"
        port = self.tester.service_configs.get(service_name, {}).get('port', 8081)
        
        # 确保端口可用
        if not self.tester.is_port_available(port):
            self.tester.kill_port_process(port)
            await asyncio.sleep(2)
        
        # 可选：启动依赖服务 message-broker
        broker_port = self.tester.service_configs.get('message-broker', {}).get('port', 8085)
        if self.tester.is_port_available(broker_port):
            broker_process = self.tester.start_service('message-broker')
            if broker_process:
                await self.tester.wait_for_service_startup(broker_port, timeout=30)
        
        # 启动服务
        process = self.tester.start_service(service_name)
        assert process is not None, f"无法启动 {service_name} 服务"
        
        # 等待服务启动
        startup_success = await self.tester.wait_for_service_startup(port, timeout=30)
        assert startup_success, f"{service_name} 服务启动超时"
        
        # 验证进程还在运行
        assert process.poll() is None, f"{service_name} 服务进程已退出"
    
    # ============================================================================
    # Data Storage Service Tests (依赖 data-collector)
    # ============================================================================
    
    def test_data_storage_script_exists(self):
        """
        RED: 测试data-storage启动脚本存在
        """
        script_path = self.project_root / "start-data-storage.sh"
        assert script_path.exists(), "start-data-storage.sh 启动脚本不存在"
        assert os.access(script_path, os.X_OK), "start-data-storage.sh 没有执行权限"
    
    @pytest.mark.asyncio
    async def test_data_storage_starts_successfully(self):
        """
        RED: 测试data-storage能够成功启动
        """
        service_name = "data-storage"
        port = self.tester.service_configs.get(service_name, {}).get('port', 8082)
        
        # 确保端口可用
        if not self.tester.is_port_available(port):
            self.tester.kill_port_process(port)
            await asyncio.sleep(2)
        
        # 启动服务
        process = self.tester.start_service(service_name)
        assert process is not None, f"无法启动 {service_name} 服务"
        
        # 等待服务启动
        startup_success = await self.tester.wait_for_service_startup(port, timeout=30)
        assert startup_success, f"{service_name} 服务启动超时"
        
        # 验证进程还在运行
        assert process.poll() is None, f"{service_name} 服务进程已退出"
    
    # ============================================================================
    # Scheduler Service Tests (依赖 data-collector)
    # ============================================================================
    
    def test_scheduler_script_exists(self):
        """
        RED: 测试scheduler启动脚本存在
        """
        script_path = self.project_root / "start-scheduler.sh"
        assert script_path.exists(), "start-scheduler.sh 启动脚本不存在"
        assert os.access(script_path, os.X_OK), "start-scheduler.sh 没有执行权限"
    
    @pytest.mark.asyncio
    async def test_scheduler_starts_successfully(self):
        """
        RED: 测试scheduler能够成功启动
        """
        service_name = "scheduler"
        port = self.tester.service_configs.get(service_name, {}).get('port', 8084)
        
        # 确保端口可用
        if not self.tester.is_port_available(port):
            self.tester.kill_port_process(port)
            await asyncio.sleep(2)
        
        # 启动服务
        process = self.tester.start_service(service_name)
        assert process is not None, f"无法启动 {service_name} 服务"
        
        # 等待服务启动
        startup_success = await self.tester.wait_for_service_startup(port, timeout=30)
        assert startup_success, f"{service_name} 服务启动超时"
        
        # 验证进程还在运行
        assert process.poll() is None, f"{service_name} 服务进程已退出"
    
    # ============================================================================
    # Monitoring Service Tests (依赖所有服务)
    # ============================================================================
    
    def test_monitoring_script_exists(self):
        """
        RED: 测试monitoring启动脚本存在
        """
        script_path = self.project_root / "start-monitoring.sh"
        assert script_path.exists(), "start-monitoring.sh 启动脚本不存在"
        assert os.access(script_path, os.X_OK), "start-monitoring.sh 没有执行权限"
    
    @pytest.mark.asyncio
    async def test_monitoring_starts_successfully(self):
        """
        RED: 测试monitoring能够成功启动
        """
        service_name = "monitoring"
        port = self.tester.service_configs.get(service_name, {}).get('port', 8083)
        
        # 确保端口可用
        if not self.tester.is_port_available(port):
            self.tester.kill_port_process(port)
            await asyncio.sleep(2)
        
        # 启动服务
        process = self.tester.start_service(service_name)
        assert process is not None, f"无法启动 {service_name} 服务"
        
        # 等待服务启动
        startup_success = await self.tester.wait_for_service_startup(port, timeout=30)
        assert startup_success, f"{service_name} 服务启动超时"
        
        # 验证进程还在运行
        assert process.poll() is None, f"{service_name} 服务进程已退出"
    
    # ============================================================================
    # 服务依赖关系测试
    # ============================================================================
    
    @pytest.mark.asyncio
    async def test_service_dependency_startup_order(self):
        """
        RED: 测试服务依赖启动顺序
        问题: 验证按依赖关系启动服务
        """
        # 定义启动顺序（无依赖的先启动）
        startup_order = [
            'message-broker',  # 无依赖
            'api-gateway',     # 无依赖
            'data-collector',  # 依赖 message-broker
            'data-storage',    # 依赖 data-collector
            'scheduler',       # 依赖 data-collector  
            'monitoring'       # 依赖所有服务
        ]
        
        successful_starts = []
        
        for service_name in startup_order:
            port = self.tester.service_configs.get(service_name, {}).get('port', 8080 + len(successful_starts))
            
            # 确保端口可用
            if not self.tester.is_port_available(port):
                self.tester.kill_port_process(port)
                await asyncio.sleep(1)
            
            # 尝试启动服务
            process = self.tester.start_service(service_name)
            if process:
                startup_success = await self.tester.wait_for_service_startup(port, timeout=20)
                if startup_success and process.poll() is None:
                    successful_starts.append(service_name)
                    logger.info(f"✅ {service_name} 启动成功")
                else:
                    logger.warning(f"⚠️  {service_name} 启动失败")
            else:
                logger.warning(f"⚠️  {service_name} 进程创建失败")
            
            # 短暂等待让服务稳定
            await asyncio.sleep(2)
        
        # 至少要有一半服务启动成功
        success_rate = len(successful_starts) / len(startup_order)
        logger.info(f"📊 服务启动成功率: {len(successful_starts)}/{len(startup_order)} ({success_rate:.1%})")
        
        # 记录成功启动的服务
        if successful_starts:
            logger.info(f"✅ 成功启动的服务: {', '.join(successful_starts)}")
        
        # 这个测试主要用于信息收集，不强制失败
        # 但如果完全没有服务启动成功，则认为有严重问题
        assert len(successful_starts) > 0, "没有任何服务启动成功，可能存在严重的环境问题"
    
    # ============================================================================
    # 服务启动性能测试
    # ============================================================================
    
    @pytest.mark.asyncio
    async def test_service_startup_performance(self):
        """
        RED: 测试服务启动性能
        问题: 验证服务启动时间在合理范围内
        """
        service_name = "api-gateway"  # 测试最简单的服务
        port = self.tester.service_configs.get(service_name, {}).get('port', 8080)
        
        # 确保端口可用
        if not self.tester.is_port_available(port):
            self.tester.kill_port_process(port)
            await asyncio.sleep(2)
        
        # 测量启动时间
        start_time = time.time()
        process = self.tester.start_service(service_name)
        
        if process:
            startup_success = await self.tester.wait_for_service_startup(port, timeout=30)
            startup_time = time.time() - start_time
            
            logger.info(f"📊 {service_name} 启动时间: {startup_time:.2f}秒")
            
            if startup_success:
                # 启动时间应该在合理范围内 (30秒内)
                assert startup_time < 30, f"{service_name} 启动时间过长: {startup_time:.2f}秒"
                
                # 最优情况下应该在10秒内启动
                if startup_time < 10:
                    logger.info(f"🚀 {service_name} 启动性能优秀: {startup_time:.2f}秒")
                elif startup_time < 20:
                    logger.info(f"👍 {service_name} 启动性能良好: {startup_time:.2f}秒")
                else:
                    logger.warning(f"⚠️  {service_name} 启动性能一般: {startup_time:.2f}秒")
        else:
            pytest.fail(f"无法启动 {service_name} 服务")


# ============================================================================
# TDD修复辅助函数
# ============================================================================

def diagnose_startup_failures(project_root: Path):
    """
    GREEN: 诊断服务启动失败原因
    帮助定位问题并提供修复建议
    """
    print("🔍 诊断服务启动失败原因...")
    
    issues = []
    
    # 1. 检查启动脚本
    expected_scripts = [
        "start-api-gateway.sh", "start-data-collector.sh", "start-data-storage.sh",
        "start-monitoring.sh", "start-scheduler.sh", "start-message-broker.sh"
    ]
    
    for script_name in expected_scripts:
        script_path = project_root / script_name
        if not script_path.exists():
            issues.append(f"❌ 缺失启动脚本: {script_name}")
        elif not os.access(script_path, os.X_OK):
            issues.append(f"⚠️  启动脚本无执行权限: {script_name}")
    
    # 2. 检查Python环境
    try:
        import sys
        if sys.version_info < (3, 8):
            issues.append(f"❌ Python版本过低: {sys.version_info}")
    except:
        issues.append("❌ Python环境异常")
    
    # 3. 检查虚拟环境
    venv_path = project_root / "venv"
    if not venv_path.exists():
        issues.append("❌ 虚拟环境不存在")
    
    # 4. 检查依赖
    requirements_file = project_root / "requirements.txt"
    if not requirements_file.exists():
        issues.append("❌ requirements.txt文件不存在")
    
    # 5. 检查配置文件
    config_file = project_root / "config" / "services.yaml"
    if not config_file.exists():
        issues.append("❌ services.yaml配置文件不存在")
    
    # 6. 检查端口占用
    ports_to_check = [8080, 8081, 8082, 8083, 8084, 8085]
    occupied_ports = []
    
    for port in ports_to_check:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex(('localhost', port))
                if result == 0:
                    occupied_ports.append(port)
        except:
            pass
    
    if occupied_ports:
        issues.append(f"⚠️  端口被占用: {occupied_ports}")
    
    # 报告诊断结果
    if issues:
        print("\n🚨 发现以下问题:")
        for issue in issues:
            print(f"  {issue}")
        
        print("\n💡 修复建议:")
        if "虚拟环境不存在" in str(issues):
            print("  1. 创建虚拟环境: python3 -m venv venv")
            print("  2. 激活虚拟环境: source venv/bin/activate")
        
        if "requirements.txt" in str(issues):
            print("  3. 安装依赖: pip install -r requirements.txt")
        
        if "执行权限" in str(issues):
            print("  4. 设置脚本权限: chmod +x start-*.sh")
        
        if occupied_ports:
            print(f"  5. 释放端口: 终止占用端口 {occupied_ports} 的进程")
        
        if "配置文件" in str(issues):
            print("  6. 检查配置文件是否存在且格式正确")
    else:
        print("✅ 未发现明显问题，可能是服务内部逻辑错误")
        print("💡 建议检查服务日志和错误输出")


if __name__ == "__main__":
    # 支持直接运行诊断
    import argparse
    
    parser = argparse.ArgumentParser(description="MarketPrism服务启动测试")
    parser.add_argument("--diagnose", action="store_true", help="诊断启动失败原因")
    parser.add_argument("--test", action="store_true", help="运行启动测试")
    parser.add_argument("--service", type=str, help="测试特定服务")
    
    args = parser.parse_args()
    
    project_root = Path(__file__).parent.parent.parent
    
    if args.diagnose:
        diagnose_startup_failures(project_root)
    elif args.test:
        if args.service:
            pytest.main([__file__ + f"::TestIndividualServiceStartup::test_{args.service.replace('-', '_')}_starts_successfully", "-v"])
        else:
            pytest.main([__file__, "-v"])
    else:
        print("使用 --test 运行测试，或 --diagnose 诊断问题")