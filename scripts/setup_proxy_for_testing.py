#!/usr/bin/env python3
"""
代理设置脚本 - 用于配置代理来支持完整数据流测试

使用方法:
    python scripts/setup_proxy_for_testing.py
    
或者直接设置特定代理:
    python scripts/setup_proxy_for_testing.py --proxy http://127.0.0.1:1087
"""

import os
import sys
import asyncio
import aiohttp
import argparse
import logging
from typing import List, Optional, Dict, Any

# 添加项目根目录到路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from config.app_config import AppConfig, NetworkConfig

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ProxySetupManager:
    """代理设置管理器"""
    
    def __init__(self):
        self.common_proxy_ports = [1087, 1080, 7890, 8080, 8888, 10809, 10810]
        self.test_urls = [
            "https://api.binance.com/api/v3/time",
            "https://api.okx.com/api/v5/public/time", 
            "https://www.deribit.com/api/v2/public/get_time"
        ]
    
    def detect_system_proxy(self) -> Dict[str, str]:
        """检测系统代理设置"""
        logger.info("🔍 检测系统代理设置...")
        
        proxy_vars = {}
        
        # 检查标准环境变量
        for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY']:
            value = os.environ.get(var) or os.environ.get(var.lower())
            if value:
                proxy_vars[var] = value
                logger.info(f"发现环境变量 {var}: {value}")
        
        if not proxy_vars:
            logger.info("❌ 未发现系统代理设置")
        else:
            logger.info(f"✅ 发现 {len(proxy_vars)} 个代理环境变量")
        
        return proxy_vars
    
    def generate_common_proxies(self) -> List[str]:
        """生成常用代理地址列表"""
        proxies = []
        
        # HTTP代理
        for port in self.common_proxy_ports:
            proxies.append(f"http://127.0.0.1:{port}")
            proxies.append(f"http://localhost:{port}")
        
        # SOCKS代理 (如果支持)
        for port in [1080, 10808, 10809]:
            proxies.append(f"socks5://127.0.0.1:{port}")
        
        return proxies
    
    async def test_proxy(self, proxy: str, test_url: str = None) -> bool:
        """测试单个代理是否可用"""
        test_url = test_url or self.test_urls[0]
        
        try:
            # 设置超时时间较短，快速检测
            timeout = aiohttp.ClientTimeout(total=8, connect=5)
            
            if proxy.startswith('socks'):
                # SOCKS代理需要特殊处理
                import aiohttp_socks
                connector = aiohttp_socks.ProxyConnector.from_url(proxy)
                
                async with aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout
                ) as session:
                    async with session.get(test_url) as response:
                        return response.status == 200
            else:
                # HTTP代理
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(test_url, proxy=proxy) as response:
                        return response.status == 200
                        
        except Exception as e:
            logger.debug(f"代理测试失败 {proxy}: {str(e)}")
            return False
    
    async def test_direct_connection(self) -> bool:
        """测试直连是否可用"""
        logger.info("🔍 测试直连可用性...")
        
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.test_urls[0]) as response:
                    if response.status == 200:
                        logger.info("✅ 直连可用")
                        return True
        except Exception as e:
            logger.info(f"❌ 直连失败: {str(e)}")
            
        return False
    
    async def find_working_proxy(self, proxy_list: List[str] = None) -> Optional[str]:
        """查找可用的代理"""
        logger.info("🔍 搜索可用代理...")
        
        if proxy_list is None:
            proxy_list = self.generate_common_proxies()
        
        logger.info(f"测试 {len(proxy_list)} 个代理地址...")
        
        # 并发测试所有代理
        tasks = []
        for proxy in proxy_list:
            task = asyncio.create_task(self._test_proxy_with_result(proxy))
            tasks.append(task)
        
        # 等待所有任务完成或找到第一个可用代理
        working_proxies = []
        completed_tasks = 0
        
        for task in asyncio.as_completed(tasks):
            result = await task
            completed_tasks += 1
            
            if result['working']:
                working_proxies.append(result)
                logger.info(f"✅ 找到可用代理: {result['proxy']} (响应时间: {result['response_time']:.2f}s)")
            
            # 进度显示
            if completed_tasks % 5 == 0 or completed_tasks == len(tasks):
                logger.info(f"进度: {completed_tasks}/{len(tasks)} 已测试")
        
        if working_proxies:
            # 选择响应时间最快的代理
            best_proxy = min(working_proxies, key=lambda x: x['response_time'])
            logger.info(f"🏆 最佳代理: {best_proxy['proxy']} (响应时间: {best_proxy['response_time']:.2f}s)")
            return best_proxy['proxy']
        else:
            logger.warning("❌ 未找到可用代理")
            return None
    
    async def _test_proxy_with_result(self, proxy: str) -> Dict[str, Any]:
        """测试代理并返回详细结果"""
        import time
        start_time = time.time()
        
        try:
            working = await self.test_proxy(proxy)
            response_time = time.time() - start_time
            
            return {
                'proxy': proxy,
                'working': working,
                'response_time': response_time
            }
        except Exception as e:
            return {
                'proxy': proxy,
                'working': False,
                'response_time': float('inf'),
                'error': str(e)
            }
    
    async def comprehensive_proxy_test(self, proxy: str) -> Dict[str, Any]:
        """全面测试代理的可用性"""
        logger.info(f"🔍 全面测试代理: {proxy}")
        
        results = {
            'proxy': proxy,
            'overall_working': True,
            'test_results': {}
        }
        
        for i, test_url in enumerate(self.test_urls):
            try:
                start_time = asyncio.get_event_loop().time()
                working = await self.test_proxy(proxy, test_url)
                response_time = asyncio.get_event_loop().time() - start_time
                
                results['test_results'][f'test_{i+1}'] = {
                    'url': test_url,
                    'working': working,
                    'response_time': response_time
                }
                
                if working:
                    logger.info(f"  ✅ 测试{i+1}: {test_url} - OK ({response_time:.2f}s)")
                else:
                    logger.warning(f"  ❌ 测试{i+1}: {test_url} - 失败")
                    results['overall_working'] = False
                    
            except Exception as e:
                logger.error(f"  💥 测试{i+1}: {test_url} - 异常: {str(e)}")
                results['test_results'][f'test_{i+1}'] = {
                    'url': test_url,
                    'working': False,
                    'error': str(e)
                }
                results['overall_working'] = False
        
        return results
    
    def apply_proxy_settings(self, proxy: str, enable: bool = True):
        """应用代理设置"""
        logger.info(f"🔧 应用代理设置: {proxy}")
        
        if enable:
            # 设置环境变量
            os.environ['HTTP_PROXY'] = proxy
            os.environ['HTTPS_PROXY'] = proxy
            os.environ['USE_PROXY'] = 'true'
            
            # 更新应用配置
            AppConfig.set_proxy(True, proxy, proxy)
            
            logger.info("✅ 代理设置已应用")
            logger.info(f"   HTTP_PROXY: {proxy}")
            logger.info(f"   HTTPS_PROXY: {proxy}")
            logger.info(f"   USE_PROXY: true")
            
        else:
            # 禁用代理
            for var in ['HTTP_PROXY', 'HTTPS_PROXY']:
                if var in os.environ:
                    del os.environ[var]
            
            os.environ['USE_PROXY'] = 'false'
            AppConfig.set_proxy(False)
            
            logger.info("✅ 代理已禁用")
    
    def save_proxy_config(self, proxy: str):
        """保存代理配置到文件"""
        config_content = f"""# MarketPrism 代理配置
# 使用方法: source scripts/proxy_config.sh

export HTTP_PROXY="{proxy}"
export HTTPS_PROXY="{proxy}"
export USE_PROXY="true"

echo "代理配置已加载: {proxy}"
"""
        
        config_file = os.path.join(project_root, 'scripts', 'proxy_config.sh')
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(config_content)
        
        logger.info(f"✅ 代理配置已保存到: {config_file}")
        logger.info(f"使用方法: source {config_file}")

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='MarketPrism 代理设置工具')
    parser.add_argument('--proxy', type=str, help='直接指定代理地址 (如: http://127.0.0.1:1087)')
    parser.add_argument('--disable', action='store_true', help='禁用代理')
    parser.add_argument('--test-only', action='store_true', help='仅测试代理，不应用设置')
    parser.add_argument('--comprehensive', action='store_true', help='进行全面的代理测试')
    
    args = parser.parse_args()
    
    manager = ProxySetupManager()
    
    if args.disable:
        # 禁用代理
        manager.apply_proxy_settings("", False)
        return
    
    # 检测系统代理
    system_proxies = manager.detect_system_proxy()
    
    # 测试直连
    direct_works = await manager.test_direct_connection()
    
    if args.proxy:
        # 用户指定代理
        proxy = args.proxy
        logger.info(f"🎯 测试用户指定代理: {proxy}")
        
        if args.comprehensive:
            result = await manager.comprehensive_proxy_test(proxy)
            if result['overall_working']:
                logger.info("✅ 代理全面测试通过")
            else:
                logger.warning("⚠️ 代理部分测试失败")
        else:
            working = await manager.test_proxy(proxy)
            if not working:
                logger.error("❌ 指定代理不可用")
                return
        
        if not args.test_only:
            manager.apply_proxy_settings(proxy)
            manager.save_proxy_config(proxy)
        
    else:
        # 自动搜索代理
        if direct_works:
            logger.info("✅ 直连可用，无需代理")
            if not args.test_only:
                manager.apply_proxy_settings("", False)
        else:
            logger.info("❌ 直连不可用，搜索代理...")
            
            # 首先尝试系统代理
            working_proxy = None
            if system_proxies:
                for var, proxy_val in system_proxies.items():
                    if 'NO_PROXY' not in var and await manager.test_proxy(proxy_val):
                        working_proxy = proxy_val
                        logger.info(f"✅ 系统代理可用: {proxy_val}")
                        break
            
            # 如果系统代理不可用，搜索常用代理
            if not working_proxy:
                working_proxy = await manager.find_working_proxy()
            
            if working_proxy:
                if args.comprehensive:
                    result = await manager.comprehensive_proxy_test(working_proxy)
                    if not result['overall_working']:
                        logger.warning("⚠️ 代理在某些测试中失败，但仍将使用")
                
                if not args.test_only:
                    manager.apply_proxy_settings(working_proxy)
                    manager.save_proxy_config(working_proxy)
                
                logger.info(f"🎉 代理设置完成！现在可以运行: python scripts/test_complete_data_flow.py")
            else:
                logger.error("❌ 未找到可用代理，请手动配置")
                logger.info("💡 提示:")
                logger.info("   1. 检查你的代理软件是否正常运行")
                logger.info("   2. 确认代理端口是否正确 (常用端口: 1087, 1080, 7890)")
                logger.info("   3. 手动指定代理: python scripts/setup_proxy_for_testing.py --proxy http://127.0.0.1:YOUR_PORT")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n代理设置被用户中断")
    except Exception as e:
        logger.error(f"代理设置失败: {e}")
        sys.exit(1)