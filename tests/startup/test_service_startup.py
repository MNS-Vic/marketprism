#!/usr/bin/env python3
"""
MarketPrism 服务启动测试套件
测试内容:
1. 启动正确性测试 - 服务能否正常启动
2. 功能正常性测试 - 核心API是否工作
3. 冗余检测测试 - 发现未使用、重复、冲突的代码
"""

import asyncio
import aiohttp
import subprocess
import time
import sys
import os
import json
import signal
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import yaml
import psutil
import logging
from datetime import datetime, timedelta, timezone

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ServiceStartupTester:
    """服务启动测试器"""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.services = {
            'api-gateway': {
                'port': 8080,
                'script': 'start-api-gateway.sh',
                'health_endpoint': '/health',
                'key_endpoints': [
                    '/_gateway/status',
                    '/_gateway/services',
                    '/metrics'
                ]
            },
            'data-collector': {
                'port': 8081,
                'script': 'start-data-collector.sh', 
                'health_endpoint': '/health',
                'key_endpoints': [
                    '/api/v1/collector/status',
                    '/metrics'
                ]
            },
            'data-storage': {
                'port': 8082,
                'script': 'start-data-storage.sh',
                'health_endpoint': '/health', 
                'key_endpoints': [
                    '/api/v1/storage/status',
                    '/metrics'
                ]
            },
            'monitoring': {
                'port': 8083,
                'script': 'start-monitoring.sh',
                'health_endpoint': '/health',
                'key_endpoints': [
                    '/api/v1/overview',
                    '/api/v1/services',
                    '/api/v1/alerts',
                    '/metrics'
                ]
            },
            'scheduler': {
                'port': 8084,
                'script': 'start-scheduler.sh',
                'health_endpoint': '/health',
                'key_endpoints': [
                    '/api/v1/scheduler/status',
                    '/api/v1/scheduler/tasks',
                    '/metrics'
                ]
            },
            'message-broker': {
                'port': 8085,
                'script': 'start-message-broker.sh',
                'health_endpoint': '/health',
                'key_endpoints': [
                    '/api/v1/broker/status',
                    '/api/v1/broker/streams',
                    '/metrics'
                ]
            }
        }
        self.running_processes = {}
        self.test_results = {}
    
    async def run_all_tests(self) -> Dict:
        """运行所有测试"""
        logger.info("🚀 开始 MarketPrism 服务启动测试套件")
        
        results = {
            'startup_tests': {},
            'functionality_tests': {},
            'redundancy_tests': {},
            'summary': {}
        }
        
        try:
            # 1. 启动正确性测试
            logger.info("📋 第一阶段: 启动正确性测试")
            results['startup_tests'] = await self.test_startup_correctness()
            
            # 2. 功能正常性测试  
            logger.info("📋 第二阶段: 功能正常性测试")
            results['functionality_tests'] = await self.test_functionality()
            
            # 3. 冗余检测测试
            logger.info("📋 第三阶段: 冗余检测测试")
            results['redundancy_tests'] = await self.test_redundancy()
            
            # 生成汇总
            results['summary'] = self.generate_summary(results)
            
        finally:
            # 清理进程
            await self.cleanup_processes()
        
        return results
    
    async def test_startup_correctness(self) -> Dict:
        """测试启动正确性"""
        results = {}
        
        for service_name, config in self.services.items():
            logger.info(f"🔍 测试 {service_name} 启动...")
            
            result = {
                'script_exists': False,
                'port_available': False,
                'startup_success': False,
                'startup_time': 0,
                'health_check': False,
                'process_stable': False,
                'errors': []
            }
            
            try:
                # 检查启动脚本存在
                script_path = self.project_root / config['script']
                result['script_exists'] = script_path.exists()
                
                if not result['script_exists']:
                    result['errors'].append(f"启动脚本不存在: {script_path}")
                    results[service_name] = result
                    continue
                
                # 检查端口是否可用
                if not self.is_port_available(config['port']):
                    self.kill_port_process(config['port'])
                    time.sleep(2)
                
                result['port_available'] = self.is_port_available(config['port'])
                
                # 启动服务
                start_time = time.time()
                process = await self.start_service(service_name, script_path)
                
                if process:
                    self.running_processes[service_name] = process
                    
                    # 等待服务启动
                    startup_success = await self.wait_for_service(config['port'], timeout=30)
                    result['startup_time'] = time.time() - start_time
                    result['startup_success'] = startup_success
                    
                    if startup_success:
                        # 健康检查
                        result['health_check'] = await self.check_health(config['port'], config['health_endpoint'])
                        
                        # 进程稳定性检查
                        await asyncio.sleep(5)
                        result['process_stable'] = process.poll() is None
                    else:
                        result['errors'].append("服务启动超时")
                else:
                    result['errors'].append("无法启动服务进程")
                    
            except Exception as e:
                result['errors'].append(f"启动测试异常: {str(e)}")
            
            results[service_name] = result
            logger.info(f"✅ {service_name} 启动测试完成: {'成功' if result['startup_success'] else '失败'}")
        
        return results
    
    async def test_functionality(self) -> Dict:
        """测试功能正常性"""
        results = {}
        
        for service_name, config in self.services.items():
            logger.info(f"🔍 测试 {service_name} 功能...")
            
            result = {
                'health_endpoint': False,
                'key_endpoints': {},
                'response_times': {},
                'api_errors': [],
                'prometheus_metrics': False
            }
            
            if service_name not in self.running_processes:
                result['api_errors'].append("服务未运行")
                results[service_name] = result
                continue
            
            try:
                base_url = f"http://localhost:{config['port']}"
                
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                    # 测试健康检查端点
                    health_ok, health_time = await self.test_endpoint(
                        session, f"{base_url}{config['health_endpoint']}"
                    )
                    result['health_endpoint'] = health_ok
                    result['response_times']['health'] = health_time
                    
                    # 测试关键端点
                    for endpoint in config['key_endpoints']:
                        endpoint_ok, endpoint_time = await self.test_endpoint(
                            session, f"{base_url}{endpoint}"
                        )
                        result['key_endpoints'][endpoint] = endpoint_ok
                        result['response_times'][endpoint] = endpoint_time
                        
                        if not endpoint_ok:
                            result['api_errors'].append(f"端点失败: {endpoint}")
                    
                    # 测试Prometheus指标
                    metrics_ok, _ = await self.test_endpoint(session, f"{base_url}/metrics")
                    result['prometheus_metrics'] = metrics_ok
                    
            except Exception as e:
                result['api_errors'].append(f"功能测试异常: {str(e)}")
            
            results[service_name] = result
            logger.info(f"✅ {service_name} 功能测试完成")
        
        return results
    
    async def test_redundancy(self) -> Dict:
        """测试冗余和重复代码"""
        logger.info("🔍 分析代码冗余...")
        
        results = {
            'unused_imports': {},
            'duplicate_code': {},
            'conflicting_ports': {},
            'unused_files': [],
            'code_complexity': {},
            'memory_usage': {}
        }
        
        try:
            # 检查未使用的导入
            results['unused_imports'] = await self.check_unused_imports()
            
            # 检查重复代码
            results['duplicate_code'] = await self.check_duplicate_code()
            
            # 检查端口冲突
            results['conflicting_ports'] = self.check_port_conflicts()
            
            # 检查未使用的文件
            results['unused_files'] = await self.check_unused_files()
            
            # 检查代码复杂度
            results['code_complexity'] = await self.check_code_complexity()
            
            # 检查内存使用
            results['memory_usage'] = await self.check_memory_usage()
            
        except Exception as e:
            logger.error(f"冗余检测异常: {e}")
        
        return results
    
    async def start_service(self, service_name: str, script_path: Path) -> Optional[subprocess.Popen]:
        """启动服务"""
        try:
            # 使用subprocess.Popen启动服务
            process = subprocess.Popen(
                [str(script_path)],
                cwd=self.project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid  # 创建新的进程组
            )
            
            # 等待一下让进程启动
            await asyncio.sleep(2)
            
            if process.poll() is None:  # 进程还在运行
                return process
            else:
                logger.error(f"服务 {service_name} 启动失败")
                return None
                
        except Exception as e:
            logger.error(f"启动服务 {service_name} 异常: {e}")
            return None
    
    async def wait_for_service(self, port: int, timeout: int = 30) -> bool:
        """等待服务启动"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if not self.is_port_available(port):  # 端口被占用说明服务启动了
                return True
            await asyncio.sleep(1)
        
        return False
    
    async def check_health(self, port: int, endpoint: str) -> bool:
        """检查健康状态"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"http://localhost:{port}{endpoint}") as response:
                    return response.status == 200
        except:
            return False
    
    async def test_endpoint(self, session: aiohttp.ClientSession, url: str) -> Tuple[bool, float]:
        """测试端点"""
        start_time = time.time()
        try:
            async with session.get(url) as response:
                response_time = time.time() - start_time
                return response.status < 400, response_time
        except:
            return False, time.time() - start_time
    
    def is_port_available(self, port: int) -> bool:
        """检查端口是否可用"""
        for conn in psutil.net_connections():
            if conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
                return False
        return True
    
    def kill_port_process(self, port: int):
        """杀死占用端口的进程"""
        for proc in psutil.process_iter(['pid', 'name', 'connections']):
            try:
                for conn in proc.info['connections'] or []:
                    if conn.laddr.port == port:
                        logger.info(f"终止占用端口 {port} 的进程 {proc.info['pid']}")
                        proc.terminate()
                        return
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    
    async def check_unused_imports(self) -> Dict:
        """检查未使用的导入"""
        unused_imports = {}
        
        # 扫描所有Python文件
        for py_file in self.project_root.rglob("*.py"):
            if "venv" in str(py_file) or "__pycache__" in str(py_file):
                continue
                
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 简单检查：查找import但在代码中未使用的模块
                import_lines = [line.strip() for line in content.split('\n') if line.strip().startswith(('import ', 'from '))]
                
                unused_in_file = []
                for import_line in import_lines:
                    if 'import ' in import_line:
                        # 提取模块名
                        if import_line.startswith('from '):
                            parts = import_line.split()
                            if len(parts) >= 4:  # from module import something
                                module_name = parts[3].split(',')[0].strip()
                        else:
                            parts = import_line.split()
                            if len(parts) >= 2:  # import module
                                module_name = parts[1].split('.')[0].strip()
                        
                        # 检查是否在代码中使用
                        if module_name and module_name not in content.replace(import_line, ''):
                            unused_in_file.append(import_line)
                
                if unused_in_file:
                    unused_imports[str(py_file.relative_to(self.project_root))] = unused_in_file
                    
            except Exception as e:
                logger.warning(f"检查文件 {py_file} 时出错: {e}")
        
        return unused_imports
    
    async def check_duplicate_code(self) -> Dict:
        """检查重复代码"""
        duplicate_code = {}
        
        # 检查函数级别的重复
        function_signatures = {}
        
        for py_file in self.project_root.rglob("*.py"):
            if "venv" in str(py_file) or "__pycache__" in str(py_file):
                continue
                
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                for i, line in enumerate(lines):
                    line = line.strip()
                    if line.startswith('def ') or line.startswith('class '):
                        # 提取函数/类签名
                        signature = line.split(':')[0].strip()
                        
                        if signature in function_signatures:
                            if signature not in duplicate_code:
                                duplicate_code[signature] = []
                            duplicate_code[signature].append({
                                'file': str(py_file.relative_to(self.project_root)),
                                'line': i + 1
                            })
                        else:
                            function_signatures[signature] = {
                                'file': str(py_file.relative_to(self.project_root)),
                                'line': i + 1
                            }
            except Exception as e:
                logger.warning(f"检查重复代码时出错 {py_file}: {e}")
        
        return duplicate_code
    
    def check_port_conflicts(self) -> Dict:
        """检查端口冲突"""
        conflicts = {}
        used_ports = {}
        
        # 检查配置文件中的端口
        config_file = self.project_root / 'config' / 'services.yaml'
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                
                services = config.get('services', {})
                for service_name, service_config in services.items():
                    port = service_config.get('port')
                    if port:
                        if port in used_ports:
                            conflicts[port] = [used_ports[port], service_name]
                        else:
                            used_ports[port] = service_name
            except Exception as e:
                logger.warning(f"检查端口冲突时出错: {e}")
        
        return conflicts
    
    async def check_unused_files(self) -> List[str]:
        """检查未使用的文件"""
        unused_files = []
        
        # 检查一些可能未使用的文件类型
        suspicious_extensions = ['.pyc', '.log', '.tmp', '.bak', '.old']
        
        for file_path in self.project_root.rglob("*"):
            if file_path.is_file():
                if any(str(file_path).endswith(ext) for ext in suspicious_extensions):
                    unused_files.append(str(file_path.relative_to(self.project_root)))
        
        return unused_files
    
    async def check_code_complexity(self) -> Dict:
        """检查代码复杂度"""
        complexity = {}
        
        for py_file in self.project_root.rglob("*.py"):
            if "venv" in str(py_file) or "__pycache__" in str(py_file):
                continue
            
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 简单的复杂度指标
                lines = len(content.split('\n'))
                functions = content.count('def ')
                classes = content.count('class ')
                
                complexity[str(py_file.relative_to(self.project_root))] = {
                    'lines': lines,
                    'functions': functions,
                    'classes': classes,
                    'complexity_score': lines + functions * 5 + classes * 10
                }
            except Exception as e:
                logger.warning(f"检查代码复杂度时出错 {py_file}: {e}")
        
        return complexity
    
    async def check_memory_usage(self) -> Dict:
        """检查内存使用"""
        memory_usage = {}
        
        for service_name, process in self.running_processes.items():
            try:
                if process and process.poll() is None:
                    proc = psutil.Process(process.pid)
                    memory_info = proc.memory_info()
                    
                    memory_usage[service_name] = {
                        'rss_mb': memory_info.rss / 1024 / 1024,  # MB
                        'vms_mb': memory_info.vms / 1024 / 1024,  # MB
                        'cpu_percent': proc.cpu_percent()
                    }
            except Exception as e:
                logger.warning(f"检查 {service_name} 内存使用时出错: {e}")
        
        return memory_usage
    
    def generate_summary(self, results: Dict) -> Dict:
        """生成测试汇总"""
        summary = {
            'total_services': len(self.services),
            'startup_success': 0,
            'functionality_success': 0,
            'issues_found': [],
            'recommendations': []
        }
        
        # 统计启动成功的服务
        for service_result in results['startup_tests'].values():
            if service_result.get('startup_success', False):
                summary['startup_success'] += 1
        
        # 统计功能正常的服务
        for service_result in results['functionality_tests'].values():
            if service_result.get('health_endpoint', False):
                summary['functionality_success'] += 1
        
        # 收集问题
        redundancy = results['redundancy_tests']
        
        if redundancy.get('unused_imports'):
            summary['issues_found'].append(f"发现 {len(redundancy['unused_imports'])} 个文件有未使用的导入")
        
        if redundancy.get('duplicate_code'):
            summary['issues_found'].append(f"发现 {len(redundancy['duplicate_code'])} 个重复的函数/类")
        
        if redundancy.get('conflicting_ports'):
            summary['issues_found'].append(f"发现 {len(redundancy['conflicting_ports'])} 个端口冲突")
        
        if redundancy.get('unused_files'):
            summary['issues_found'].append(f"发现 {len(redundancy['unused_files'])} 个可能未使用的文件")
        
        # 生成建议
        if summary['startup_success'] < summary['total_services']:
            summary['recommendations'].append("有服务启动失败，检查启动脚本和依赖")
        
        if summary['functionality_success'] < summary['total_services']:
            summary['recommendations'].append("有服务功能异常，检查配置和API端点")
        
        if redundancy.get('unused_imports'):
            summary['recommendations'].append("清理未使用的导入以减少代码冗余")
        
        if redundancy.get('duplicate_code'):
            summary['recommendations'].append("重构重复代码以提高可维护性")
        
        return summary
    
    async def cleanup_processes(self):
        """清理进程"""
        logger.info("🧹 清理测试进程...")
        
        for service_name, process in self.running_processes.items():
            try:
                if process and process.poll() is None:
                    # 终止进程组
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    
                    # 等待进程结束
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        # 强制杀死
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    
                    logger.info(f"已停止 {service_name}")
            except Exception as e:
                logger.warning(f"停止 {service_name} 时出错: {e}")
        
        self.running_processes.clear()

async def main():
    """主函数"""
    # 获取项目根目录
    script_dir = Path(__file__).parent.parent.parent
    
    tester = ServiceStartupTester(str(script_dir))
    
    try:
        # 运行所有测试
        results = await tester.run_all_tests()
        
        # 保存结果
        results_file = script_dir / 'tests' / 'startup' / f'startup_test_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        results_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        
        # 打印汇总
        print("\n" + "="*50)
        print("🎯 MarketPrism 服务启动测试汇总")
        print("="*50)
        
        summary = results['summary']
        print(f"📊 总服务数: {summary['total_services']}")
        print(f"✅ 启动成功: {summary['startup_success']}")
        print(f"🔧 功能正常: {summary['functionality_success']}")
        
        if summary['issues_found']:
            print("\n⚠️  发现的问题:")
            for issue in summary['issues_found']:
                print(f"  • {issue}")
        
        if summary['recommendations']:
            print("\n💡 建议:")
            for rec in summary['recommendations']:
                print(f"  • {rec}")
        
        print(f"\n📁 详细结果保存在: {results_file}")
        print("="*50)
        
        return 0 if summary['startup_success'] == summary['total_services'] else 1
        
    except KeyboardInterrupt:
        logger.info("测试被用户中断")
        return 1
    except Exception as e:
        logger.error(f"测试异常: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))