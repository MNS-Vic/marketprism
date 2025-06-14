#!/usr/bin/env python3
"""
问题修复验证测试 - 验证之前失败的测试项是否已修复
"""

from datetime import datetime, timezone
import asyncio
import pytest
import aiohttp
import logging
import time
import socket
import psutil
import sys
import importlib.util
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logger = logging.getLogger(__name__)

class FixesVerificationTest:
    """修复验证测试类"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        self.core_dir = self.project_root / "core"
        
    async def test_aioredis_dependency_fixed(self):
        """验证aioredis依赖是否已修复"""
        logger.info("🔍 验证aioredis依赖修复...")
        
        try:
            # 尝试导入aioredis
            import aioredis
            logger.info("✅ aioredis依赖已成功安装")
            
            # 测试统一存储管理器是否能正常导入
            storage_manager_path = self.core_dir / 'storage' / 'unified_storage_manager.py'
            
            if storage_manager_path.exists():
                try:
                    spec = importlib.util.spec_from_file_location("unified_storage_manager", storage_manager_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    logger.info("✅ 统一存储管理器现在可以正常导入")
                    return True
                except Exception as e:
                    logger.error(f"❌ 统一存储管理器导入仍然失败: {e}")
                    return False
            else:
                logger.warning("⚠️ 统一存储管理器文件不存在")
                return False
                
        except ImportError:
            logger.error("❌ aioredis依赖仍然缺失")
            return False
        except Exception as e:
            logger.error(f"❌ aioredis依赖测试失败: {e}")
            return False
    
    async def test_clickhouse_service_fixed(self):
        """验证ClickHouse服务是否已修复"""
        logger.info("🔍 验证ClickHouse服务修复...")
        
        try:
            # 检查ClickHouse进程
            clickhouse_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                if 'clickhouse' in proc.info['name'].lower():
                    clickhouse_processes.append(proc.info)
            
            if clickhouse_processes:
                logger.info(f"✅ 发现ClickHouse进程: {len(clickhouse_processes)}个")
                
                # 检查端口8123是否开放
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result = sock.connect_ex(('localhost', 8123))
                sock.close()
                
                if result == 0:
                    logger.info("✅ ClickHouse端口8123可访问")
                    return True
                else:
                    logger.warning("⚠️ ClickHouse端口8123不可访问")
                    return False
            else:
                logger.warning("⚠️ 未发现ClickHouse进程")
                return False
                
        except Exception as e:
            logger.error(f"❌ ClickHouse服务测试失败: {e}")
            return False
    
    async def test_nats_service_fixed(self):
        """验证NATS服务是否已修复"""
        logger.info("🔍 验证NATS服务修复...")
        
        try:
            # 检查NATS进程
            nats_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                if 'nats' in proc.info['name'].lower() or \
                   any('nats' in str(cmd).lower() for cmd in proc.info['cmdline'] or []):
                    nats_processes.append(proc.info)
            
            if nats_processes:
                logger.info(f"✅ 发现NATS进程: {len(nats_processes)}个")
                
                # 检查端口4222是否开放
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result = sock.connect_ex(('localhost', 4222))
                sock.close()
                
                if result == 0:
                    logger.info("✅ NATS端口4222可访问")
                    return True
                else:
                    logger.warning("⚠️ NATS端口4222不可访问")
                    return False
            else:
                logger.warning("⚠️ 未发现NATS进程")
                return False
                
        except Exception as e:
            logger.error(f"❌ NATS服务测试失败: {e}")
            return False
    
    async def test_exchange_connectivity_fixed(self):
        """验证交易所连接是否已修复"""
        logger.info("🔍 验证交易所连接修复...")
        
        try:
            # 测试交易所连接
            exchanges_to_test = [
                ('Binance', 'https://api.binance.com/api/v3/ping'),
                ('OKX', 'https://www.okx.com/api/v5/public/time'),
            ]
            
            successful_connections = 0
            
            # 使用代理的连接器
            connector = aiohttp.TCPConnector(
                limit=10,
                ttl_dns_cache=300,
                use_dns_cache=True,
                trust_env=True  # 信任环境代理设置
            )
            
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as session:
                
                for exchange_name, test_url in exchanges_to_test:
                    try:
                        logger.info(f"🔗 测试{exchange_name}连接...")
                        start_time = time.time()
                        
                        async with session.get(test_url) as response:
                            response_time = (time.time() - start_time) * 1000
                            
                            if response.status == 200:
                                logger.info(f"✅ {exchange_name} API连接成功 ({response_time:.0f}ms)")
                                successful_connections += 1
                            else:
                                logger.warning(f"⚠️ {exchange_name} API响应状态: {response.status}")
                                
                    except Exception as e:
                        logger.warning(f"⚠️ {exchange_name} API连接失败: {e}")
            
            if successful_connections > 0:
                logger.info(f"✅ 交易所连接修复成功: {successful_connections}/{len(exchanges_to_test)}")
                return True
            else:
                logger.warning("⚠️ 交易所连接仍然失败")
                return False
                
        except Exception as e:
            logger.error(f"❌ 交易所连接测试失败: {e}")
            return False

class FixesTestRunner:
    """修复测试执行器"""
    
    def __init__(self):
        self.test_instance = FixesVerificationTest()
        self.results = {}
    
    async def run_all_fixes_tests(self):
        """运行所有修复验证测试"""
        logger.info("🔧 开始验证问题修复...")
        
        test_methods = [
            ('aioredis依赖修复', self.test_instance.test_aioredis_dependency_fixed),
            ('ClickHouse服务修复', self.test_instance.test_clickhouse_service_fixed), 
            ('NATS服务修复', self.test_instance.test_nats_service_fixed),
            ('交易所连接修复', self.test_instance.test_exchange_connectivity_fixed)
        ]
        
        total_tests = len(test_methods)
        passed_tests = 0
        
        for test_name, test_method in test_methods:
            logger.info(f"\n{'='*50}")
            logger.info(f"🧪 执行修复验证: {test_name}")
            logger.info(f"{'='*50}")
            
            try:
                result = await test_method()
                self.results[test_name] = result
                
                if result:
                    passed_tests += 1
                    logger.info(f"✅ {test_name} 验证通过")
                else:
                    logger.warning(f"⚠️ {test_name} 验证失败")
                    
            except Exception as e:
                logger.error(f"❌ {test_name} 验证异常: {e}")
                self.results[test_name] = False
        
        # 修复总结
        fix_success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        logger.info(f"\n{'='*60}")
        logger.info(f"🔧 问题修复验证总结")
        logger.info(f"{'='*60}")
        logger.info(f"修复验证总数: {total_tests}")
        logger.info(f"修复成功项目: {passed_tests}")
        logger.info(f"仍需修复项目: {total_tests - passed_tests}")
        logger.info(f"修复成功率: {fix_success_rate:.1f}%")
        
        if fix_success_rate == 100:
            logger.info("🎉 所有问题已成功修复！")
        elif fix_success_rate >= 75:
            logger.info("👍 大部分问题已修复，系统状态良好")
        elif fix_success_rate >= 50:
            logger.info("⚠️ 部分问题已修复，仍需继续改进")
        else:
            logger.info("🚨 修复效果有限，需要更多工作")
        
        return self.results

# 如果直接运行此脚本
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    async def main():
        runner = FixesTestRunner()
        results = await runner.run_all_fixes_tests()
        return results
    
    # 运行修复验证测试
    asyncio.run(main())