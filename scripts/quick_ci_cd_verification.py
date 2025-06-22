#!/usr/bin/env python3
"""
MarketPrism CI/CD快速验证脚本
快速验证CI/CD配置和API连接性
"""

import os
import sys
import time
import requests
import logging
from pathlib import Path

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class QuickCICDVerifier:
    """快速CI/CD验证器"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.results = {}
    
    def verify_basic_setup(self) -> bool:
        """验证基本设置"""
        logger.info("🔧 验证基本CI/CD设置...")
        
        try:
            # 检查关键文件
            key_files = [
                '.github/workflows/ci-core-services.yml',
                '.github/workflows/deploy-data-collector.yml', 
                '.github/workflows/tdd-coverage-monitor.yml',
                'docker-compose.ci.yml',
                'tests/utils/api_rate_limiter.py',
                'scripts/ci_cd_runner.py'
            ]
            
            missing_files = []
            for file_path in key_files:
                full_path = self.project_root / file_path
                if not full_path.exists():
                    missing_files.append(file_path)
            
            if missing_files:
                logger.error(f"❌ 缺少关键文件: {missing_files}")
                return False
            
            logger.info("✅ 所有关键CI/CD文件存在")
            return True
            
        except Exception as e:
            logger.error(f"❌ 基本设置验证失败: {e}")
            return False
    
    def verify_api_rate_limiter_basic(self) -> bool:
        """验证API频率限制器基本功能"""
        logger.info("🔧 验证API频率限制器基本功能...")
        
        try:
            # 简单导入测试
            sys.path.insert(0, str(self.project_root))
            from tests.utils.api_rate_limiter import APIRateLimiter, get_rate_limiter
            
            # 创建实例
            rate_limiter = APIRateLimiter()
            
            # 基本功能测试
            can_request = rate_limiter.can_make_request('test', 'endpoint')
            logger.info(f"基本请求检查: {can_request}")
            
            # 配置测试
            config = rate_limiter.get_config('binance')
            logger.info(f"Binance配置: {config.requests_per_second} req/s")
            
            logger.info("✅ API频率限制器基本功能正常")
            return True
            
        except Exception as e:
            logger.error(f"❌ API频率限制器验证失败: {e}")
            return False
    
    def verify_exchange_connectivity_quick(self) -> bool:
        """快速验证交易所连接性"""
        logger.info("🌐 快速验证交易所连接性...")
        
        exchanges = [
            ('Binance', 'https://api.binance.com/api/v3/ping'),
            ('OKX', 'https://www.okx.com/api/v5/public/time')
        ]
        
        success_count = 0
        
        for name, url in exchanges:
            try:
                logger.info(f"测试 {name} API...")
                response = requests.get(url, timeout=5)
                
                if response.status_code == 200:
                    if name == 'OKX':
                        data = response.json()
                        if data.get('code') == '0':
                            logger.info(f"✅ {name} API连接正常")
                            success_count += 1
                        else:
                            logger.warning(f"⚠️ {name} API返回错误: {data.get('code')}")
                    else:
                        logger.info(f"✅ {name} API连接正常")
                        success_count += 1
                else:
                    logger.warning(f"⚠️ {name} API状态码: {response.status_code}")
                    
            except Exception as e:
                logger.warning(f"⚠️ {name} API连接失败: {e}")
            
            # 简单延迟避免频率限制
            time.sleep(1)
        
        if success_count >= 1:
            logger.info(f"✅ 交易所连接性验证通过 ({success_count}/{len(exchanges)})")
            return True
        else:
            logger.error("❌ 所有交易所连接失败")
            return False
    
    def verify_docker_config(self) -> bool:
        """验证Docker配置"""
        logger.info("🐳 验证Docker配置...")
        
        try:
            docker_files = [
                'services/data-collector/Dockerfile',
                'Dockerfile.test',
                'docker-compose.ci.yml'
            ]
            
            for file_path in docker_files:
                full_path = self.project_root / file_path
                if not full_path.exists():
                    logger.error(f"❌ {file_path} 不存在")
                    return False
                
                # 检查关键配置
                with open(full_path, 'r') as f:
                    content = f.read()
                
                if 'RATE_LIMIT_ENABLED' in content or 'CI' in content:
                    logger.info(f"✅ {file_path} 包含CI配置")
                else:
                    logger.warning(f"⚠️ {file_path} 可能缺少CI配置")
            
            logger.info("✅ Docker配置验证通过")
            return True
            
        except Exception as e:
            logger.error(f"❌ Docker配置验证失败: {e}")
            return False
    
    def verify_tdd_integration(self) -> bool:
        """验证TDD集成"""
        logger.info("🧪 验证TDD集成...")
        
        try:
            # 检查pytest配置
            pytest_ini = self.project_root / 'pytest.ini'
            if pytest_ini.exists():
                with open(pytest_ini, 'r') as f:
                    content = f.read()
                
                if 'live_api' in content and 'ci' in content:
                    logger.info("✅ pytest配置包含CI/CD标记")
                else:
                    logger.warning("⚠️ pytest配置可能缺少CI/CD标记")
            
            # 检查测试目录结构
            test_dirs = [
                'tests/unit',
                'tests/integration',
                'tests/utils'
            ]
            
            for test_dir in test_dirs:
                full_path = self.project_root / test_dir
                if full_path.exists():
                    logger.info(f"✅ {test_dir} 目录存在")
                else:
                    logger.warning(f"⚠️ {test_dir} 目录不存在")
            
            # 检查覆盖率配置
            if 'cov' in content and 'coverage' in content:
                logger.info("✅ 覆盖率配置正常")
            
            logger.info("✅ TDD集成验证通过")
            return True
            
        except Exception as e:
            logger.error(f"❌ TDD集成验证失败: {e}")
            return False
    
    def verify_monitoring_config(self) -> bool:
        """验证监控配置"""
        logger.info("📊 验证监控配置...")
        
        try:
            monitoring_files = [
                'monitoring/prometheus.yml'
            ]
            
            for file_path in monitoring_files:
                full_path = self.project_root / file_path
                if full_path.exists():
                    logger.info(f"✅ {file_path} 存在")
                else:
                    logger.warning(f"⚠️ {file_path} 不存在")
            
            # 检查docker-compose中的监控服务
            compose_file = self.project_root / 'docker-compose.ci.yml'
            if compose_file.exists():
                with open(compose_file, 'r') as f:
                    content = f.read()
                
                if 'prometheus' in content:
                    logger.info("✅ Docker Compose包含监控服务")
                else:
                    logger.warning("⚠️ Docker Compose可能缺少监控服务")
            
            logger.info("✅ 监控配置验证通过")
            return True
            
        except Exception as e:
            logger.error(f"❌ 监控配置验证失败: {e}")
            return False
    
    def run_quick_verification(self) -> bool:
        """运行快速验证"""
        logger.info("🚀 开始MarketPrism CI/CD快速验证...")
        logger.info("=" * 60)
        
        verifications = [
            ("基本CI/CD设置", self.verify_basic_setup),
            ("API频率限制器", self.verify_api_rate_limiter_basic),
            ("Docker配置", self.verify_docker_config),
            ("TDD集成", self.verify_tdd_integration),
            ("监控配置", self.verify_monitoring_config),
            ("交易所连接性", self.verify_exchange_connectivity_quick),
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
        logger.info("📊 快速验证结果汇总:")
        logger.info("=" * 60)
        
        for name, result in self.results.items():
            status = "✅" if result == "通过" else "❌"
            logger.info(f"{status} {name}: {result}")
        
        success_rate = (passed / total) * 100
        logger.info(f"\n📈 成功率: {passed}/{total} ({success_rate:.1f}%)")
        
        if passed >= total * 0.8:  # 80%通过率
            logger.info("🎉 CI/CD配置验证通过！")
            return True
        else:
            logger.error("❌ CI/CD配置需要修复。")
            return False

def main():
    """主函数"""
    verifier = QuickCICDVerifier()
    success = verifier.run_quick_verification()
    
    if success:
        logger.info("\n🎯 下一步建议:")
        logger.info("1. 运行完整的CI/CD流水线测试")
        logger.info("2. 验证真实API测试套件")
        logger.info("3. 检查覆盖率报告生成")
        logger.info("4. 测试Docker容器部署")
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
