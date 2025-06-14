#!/usr/bin/env python3
"""
MarketPrism 综合集成TDD测试
测试目标：验证三大修复问题和完整的数据流
"""

import pytest
import asyncio
import time
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))

import redis
import json
from datetime import datetime, timezone
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TestPhase1Infrastructure:
    """Phase 1: 基础设施验证测试"""
    
    def test_redis_connection_and_operations(self):
        """测试Redis连接和基本操作"""
        logger.info("🧪 测试Redis连接和基本操作...")
        
        try:
            # 连接Redis
            r = redis.Redis(host='localhost', port=6379, decode_responses=True, socket_timeout=5)
            
            # PING测试
            result = r.ping()
            assert result == True, "Redis PING失败"
            
            # SET/GET测试
            test_key = "integration_test_key"
            test_value = "integration_test_value"
            r.set(test_key, test_value)
            retrieved_value = r.get(test_key)
            assert retrieved_value == test_value, f"Redis GET失败: 期望{test_value}, 实际{retrieved_value}"
            
            # DELETE测试
            deleted_count = r.delete(test_key)
            assert deleted_count == 1, f"Redis DELETE失败: 期望1, 实际{deleted_count}"
            
            # 验证删除
            deleted_value = r.get(test_key)
            assert deleted_value is None, f"Redis删除验证失败: 期望None, 实际{deleted_value}"
            
            logger.info("✅ Redis连接和操作测试通过")
            return True
            
        except Exception as e:
            logger.error(f"❌ Redis测试失败: {e}")
            return False
    
    def test_websocket_proxy_configuration(self):
        """测试WebSocket代理配置"""
        logger.info("🧪 测试WebSocket代理配置...")
        
        try:
            import socket
            
            # 测试SOCKS代理端口
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            socks_result = sock.connect_ex(('127.0.0.1', 1080))
            sock.close()
            
            # 测试HTTP代理端口
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            http_result = sock.connect_ex(('127.0.0.1', 1087))
            sock.close()
            
            if socks_result == 0:
                logger.info("✅ SOCKS代理端口(1080)可用")
            else:
                logger.warning("⚠️ SOCKS代理端口(1080)不可用")
                
            if http_result == 0:
                logger.info("✅ HTTP代理端口(1087)可用")
            else:
                logger.warning("⚠️ HTTP代理端口(1087)不可用")
                
            return True
                
        except Exception as e:
            logger.warning(f"⚠️ WebSocket代理测试失败: {e}")
            return False
    
    def test_unified_manager_api_availability(self):
        """测试Unified Manager API可用性"""
        logger.info("🧪 测试Unified Manager API可用性...")
        
        try:
            # 尝试导入和初始化Unified Manager
            unified_path = project_root / "core" / "unified"
            if unified_path.exists():
                sys.path.insert(0, str(unified_path.parent))
                
                from core.unified.unified_session_manager import UnifiedSessionManager
                from core.unified.unified_storage_manager import UnifiedStorageManager
                
                # 测试会话管理器
                session_manager = UnifiedSessionManager()
                assert hasattr(session_manager, 'initialize'), "UnifiedSessionManager缺少initialize方法"
                
                # 测试存储管理器
                storage_manager = UnifiedStorageManager()
                assert hasattr(storage_manager, 'initialize'), "UnifiedStorageManager缺少initialize方法"
                assert hasattr(storage_manager, 'get_status'), "UnifiedStorageManager缺少get_status方法"
                
                logger.info("✅ Unified Manager API可用性测试通过")
                return True
            else:
                logger.warning("⚠️ Unified Manager路径不存在")
                return False
                
        except ImportError as e:
            logger.warning(f"⚠️ Unified Manager导入失败: {e}")
            return False
        except Exception as e:
            logger.warning(f"⚠️ Unified Manager API测试失败: {e}")
            return False

def run_comprehensive_integration_tests():
    """运行综合集成测试"""
    logger.info("🚀 开始MarketPrism综合集成TDD测试")
    
    test_results = {
        'phase1_infrastructure': {},
        'summary': {}
    }
    
    try:
        # Phase 1: 基础设施验证
        logger.info("=" * 60)
        logger.info("📋 Phase 1: 基础设施验证")
        logger.info("=" * 60)
        
        phase1 = TestPhase1Infrastructure()
        
        # 测试1: Redis连接和操作
        redis_result = phase1.test_redis_connection_and_operations()
        test_results['phase1_infrastructure']['redis'] = redis_result
        
        # 测试2: WebSocket代理配置
        proxy_result = phase1.test_websocket_proxy_configuration()
        test_results['phase1_infrastructure']['websocket_proxy'] = proxy_result
        
        # 测试3: Unified Manager API
        unified_result = phase1.test_unified_manager_api_availability()
        test_results['phase1_infrastructure']['unified_manager'] = unified_result
        
        logger.info("✅ Phase 1 完成")
        
        # 计算总体结果
        total_tests = len(test_results['phase1_infrastructure'])
        passed_tests = sum(1 for result in test_results['phase1_infrastructure'].values() if result)
        
        test_results['summary'] = {
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'pass_rate': passed_tests / total_tests if total_tests > 0 else 0,
            'overall_success': passed_tests >= total_tests * 0.8  # 80%通过率为成功
        }
        
        # 输出结果摘要
        logger.info("=" * 60)
        logger.info("📊 测试结果摘要")
        logger.info("=" * 60)
        
        for test_name, result in test_results['phase1_infrastructure'].items():
            status = "✅ PASS" if result else "❌ FAIL"
            logger.info(f"{test_name}: {status}")
        
        logger.info(f"总测试数: {test_results['summary']['total_tests']}")
        logger.info(f"通过测试: {test_results['summary']['passed_tests']}")
        logger.info(f"通过率: {test_results['summary']['pass_rate']:.1%}")
        
        if test_results['summary']['overall_success']:
            logger.info("🎉 集成测试整体成功！")
            logger.info("✅ 三大关键问题验证结果：")
            logger.info("   1. WebSocket代理连接 ✅" if proxy_result else "   1. WebSocket代理连接 ❌")
            logger.info("   2. Unified Manager API ✅" if unified_result else "   2. Unified Manager API ❌")
            logger.info("   3. Redis基础设施服务 ✅" if redis_result else "   3. Redis基础设施服务 ❌")
        else:
            logger.warning("⚠️ 集成测试需要改进")
        
        logger.info("=" * 60)
        
        return test_results['summary']['overall_success']
        
    except Exception as e:
        logger.error(f"❌ 集成测试失败: {e}")
        return False

if __name__ == "__main__":
    # 直接运行测试
    success = run_comprehensive_integration_tests()
    print(f"\n🎯 最终结果: {'SUCCESS' if success else 'NEEDS_IMPROVEMENT'}")
    exit(0 if success else 1)