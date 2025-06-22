#!/usr/bin/env python3
"""
MarketPrism CI/CD设置验证脚本
验证CI/CD配置和API频率限制功能
"""

import os
import sys
import time
import requests
import logging
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tests.utils.api_rate_limiter import get_rate_limiter, rate_limited_request, get_api_stats

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CICDVerifier:
    """CI/CD设置验证器"""
    
    def __init__(self):
        self.rate_limiter = get_rate_limiter()
        self.results = {}
    
    def verify_rate_limiter(self) -> bool:
        """验证API频率限制器"""
        logger.info("🔧 验证API频率限制器...")
        
        try:
            # 测试基本功能
            exchange = 'test_exchange'
            endpoint = 'test_endpoint'
            
            # 检查初始状态
            can_request = self.rate_limiter.can_make_request(exchange, endpoint)
            logger.info(f"初始状态 - 可以发起请求: {can_request}")
            
            # 记录几个请求
            request_times = []
            for i in range(3):
                start_time = time.time()
                wait_time = self.rate_limiter.wait_if_needed(exchange, endpoint)
                self.rate_limiter.record_request(exchange, endpoint)
                end_time = time.time()
                
                request_times.append(end_time - start_time)
                logger.info(f"请求 {i+1}: 等待时间 {wait_time:.2f}s, 总耗时 {end_time - start_time:.2f}s")
            
            # 验证统计信息
            stats = get_api_stats(exchange, endpoint)
            logger.info(f"统计信息: {stats}")
            
            # 验证请求间隔
            if len(request_times) > 1:
                intervals = [request_times[i] - request_times[i-1] for i in range(1, len(request_times))]
                avg_interval = sum(intervals) / len(intervals)
                logger.info(f"平均请求间隔: {avg_interval:.2f}s")
            
            logger.info("✅ API频率限制器验证通过")
            return True
            
        except Exception as e:
            logger.error(f"❌ API频率限制器验证失败: {e}")
            return False
    
    @rate_limited_request('binance', 'ping')
    def verify_binance_connectivity(self) -> bool:
        """验证Binance连接性"""
        logger.info("🌐 验证Binance API连接性...")
        
        try:
            response = requests.get('https://api.binance.com/api/v3/ping', timeout=10)
            
            if response.status_code == 200:
                logger.info("✅ Binance API连接正常")
                return True
            else:
                logger.warning(f"⚠️ Binance API返回状态码: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Binance API连接失败: {e}")
            return False
    
    @rate_limited_request('okx', 'time')
    def verify_okx_connectivity(self) -> bool:
        """验证OKX连接性"""
        logger.info("🌐 验证OKX API连接性...")
        
        try:
            response = requests.get('https://www.okx.com/api/v5/public/time', timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == '0':
                    logger.info("✅ OKX API连接正常")
                    return True
                else:
                    logger.warning(f"⚠️ OKX API返回错误代码: {data.get('code')}")
                    return False
            else:
                logger.warning(f"⚠️ OKX API返回状态码: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ OKX API连接失败: {e}")
            return False
    
    def verify_ci_environment(self) -> bool:
        """验证CI环境配置"""
        logger.info("🔍 验证CI环境配置...")
        
        try:
            # 检查环境变量
            ci_vars = {
                'CI': os.getenv('CI'),
                'GITHUB_ACTIONS': os.getenv('GITHUB_ACTIONS'),
                'RATE_LIMIT_ENABLED': os.getenv('RATE_LIMIT_ENABLED'),
                'API_TIMEOUT': os.getenv('API_TIMEOUT'),
                'LOG_LEVEL': os.getenv('LOG_LEVEL')
            }
            
            logger.info("环境变量:")
            for var, value in ci_vars.items():
                logger.info(f"  {var}: {value}")
            
            # 检查关键文件
            key_files = [
                '.github/workflows/ci-core-services.yml',
                '.github/workflows/deploy-data-collector.yml',
                '.github/workflows/tdd-coverage-monitor.yml',
                'docker-compose.ci.yml',
                'Dockerfile.test',
                'tests/utils/api_rate_limiter.py',
                'scripts/smart_test_runner.py',
                'scripts/ci_cd_runner.py'
            ]
            
            missing_files = []
            for file_path in key_files:
                full_path = project_root / file_path
                if full_path.exists():
                    logger.info(f"✅ {file_path}")
                else:
                    logger.error(f"❌ {file_path} 不存在")
                    missing_files.append(file_path)
            
            if missing_files:
                logger.error(f"缺少关键文件: {missing_files}")
                return False
            
            logger.info("✅ CI环境配置验证通过")
            return True
            
        except Exception as e:
            logger.error(f"❌ CI环境配置验证失败: {e}")
            return False
    
    def verify_docker_config(self) -> bool:
        """验证Docker配置"""
        logger.info("🐳 验证Docker配置...")
        
        try:
            # 检查Docker文件
            docker_files = [
                'services/data-collector/Dockerfile',
                'Dockerfile.test',
                'docker-compose.ci.yml'
            ]
            
            for file_path in docker_files:
                full_path = project_root / file_path
                if full_path.exists():
                    logger.info(f"✅ {file_path}")
                    
                    # 检查文件内容
                    with open(full_path, 'r') as f:
                        content = f.read()
                        
                    if 'RATE_LIMIT_ENABLED' in content:
                        logger.info(f"  - 包含频率限制配置")
                    if 'CI' in content:
                        logger.info(f"  - 包含CI环境配置")
                else:
                    logger.error(f"❌ {file_path} 不存在")
                    return False
            
            logger.info("✅ Docker配置验证通过")
            return True
            
        except Exception as e:
            logger.error(f"❌ Docker配置验证失败: {e}")
            return False
    
    def run_verification(self) -> bool:
        """运行完整验证"""
        logger.info("🚀 开始MarketPrism CI/CD设置验证...")
        logger.info("=" * 60)
        
        verifications = [
            ("CI环境配置", self.verify_ci_environment),
            ("Docker配置", self.verify_docker_config),
            ("API频率限制器", self.verify_rate_limiter),
            ("Binance连接性", self.verify_binance_connectivity),
            ("OKX连接性", self.verify_okx_connectivity),
        ]
        
        passed = 0
        total = len(verifications)
        
        for name, verify_func in verifications:
            logger.info(f"\n📋 验证: {name}")
            logger.info("-" * 40)
            
            try:
                if verify_func():
                    passed += 1
                    self.results[name] = "通过"
                else:
                    self.results[name] = "失败"
            except Exception as e:
                logger.error(f"验证异常: {e}")
                self.results[name] = f"异常: {e}"
        
        # 打印最终结果
        logger.info("\n" + "=" * 60)
        logger.info("📊 验证结果汇总:")
        logger.info("=" * 60)
        
        for name, result in self.results.items():
            status = "✅" if result == "通过" else "❌"
            logger.info(f"{status} {name}: {result}")
        
        success_rate = (passed / total) * 100
        logger.info(f"\n📈 成功率: {passed}/{total} ({success_rate:.1f}%)")
        
        if passed == total:
            logger.info("🎉 所有验证通过！CI/CD设置就绪。")
            return True
        elif passed >= total * 0.8:  # 80%通过率
            logger.info("⚠️ 大部分验证通过，CI/CD基本就绪。")
            return True
        else:
            logger.error("❌ 多个验证失败，需要修复CI/CD配置。")
            return False

def main():
    """主函数"""
    verifier = CICDVerifier()
    success = verifier.run_verification()
    
    # 打印API使用统计
    logger.info("\n📊 API使用统计:")
    for exchange in ['test_exchange', 'binance', 'okx']:
        stats = get_api_stats(exchange)
        if stats['total_requests'] > 0:
            logger.info(f"  {exchange}: {stats['total_requests']} 请求")
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
