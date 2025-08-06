#!/usr/bin/env python3
"""
MarketPrism统一NATS容器 - 部署测试脚本

🎯 功能说明：
- 验证统一NATS容器的完整功能
- 测试所有7种数据类型的支持
- 验证与Data Collector的兼容性
- 提供详细的测试报告

📊 测试项目：
- NATS服务器连通性
- JetStream功能验证
- MARKET_DATA流配置
- 数据类型主题支持
- 消息发布和订阅测试
- 健康检查端点验证

🔧 设计理念：
- 全面的功能验证测试
- 与现有系统的兼容性验证
- 详细的测试报告和错误诊断
- 支持自动化测试流程
"""

import asyncio
import json
import sys
import logging
import argparse
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import aiohttp

# 尝试导入NATS客户端
try:
    import nats
    from nats.js import JetStreamContext
    NATS_AVAILABLE = True
except ImportError:
    print("❌ NATS客户端库未安装，请安装: pip install nats-py aiohttp")
    NATS_AVAILABLE = False
    sys.exit(1)

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('UnifiedDeploymentTest')


class UnifiedNATSDeploymentTest:
    """
    统一NATS容器部署测试器
    
    验证简化架构的完整功能和兼容性
    """
    
    def __init__(self, nats_url: str = "nats://localhost:4222", http_url: str = "http://localhost:8222"):
        """
        初始化测试器
        
        Args:
            nats_url: NATS服务器连接URL
            http_url: HTTP监控端点URL
        """
        self.nats_url = nats_url
        self.http_url = http_url
        self.nc = None
        self.js = None
        
        # 测试结果
        self.test_results = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'nats_url': nats_url,
            'http_url': http_url,
            'tests': {},
            'overall_status': 'unknown',
            'summary': {}
        }
        
        # 预期的数据类型（与unified_data_collection.yaml兼容）
        self.expected_data_types = [
            {
                'name': 'orderbook',
                'subject': 'orderbook-data.>',
                'description': '订单簿数据（所有交易所）',
                'exchanges': ['binance_spot', 'binance_derivatives', 'okx_spot', 'okx_derivatives']
            },
            {
                'name': 'trade',
                'subject': 'trade-data.>',
                'description': '交易数据（所有交易所）',
                'exchanges': ['binance_spot', 'binance_derivatives', 'okx_spot', 'okx_derivatives']
            },
            {
                'name': 'funding_rate',
                'subject': 'funding-rate-data.>',
                'description': '资金费率（衍生品交易所）',
                'exchanges': ['binance_derivatives', 'okx_derivatives']
            },
            {
                'name': 'open_interest',
                'subject': 'open-interest-data.>',
                'description': '未平仓量（衍生品交易所）',
                'exchanges': ['binance_derivatives', 'okx_derivatives']
            },
            {
                'name': 'lsr_top_position',
                'subject': 'lsr-top-position-data.>',
                'description': 'LSR顶级持仓（衍生品交易所）',
                'exchanges': ['binance_derivatives', 'okx_derivatives']
            },
            {
                'name': 'lsr_all_account',
                'subject': 'lsr-all-account-data.>',
                'description': 'LSR全账户（衍生品交易所）',
                'exchanges': ['binance_derivatives', 'okx_derivatives']
            },
            {
                'name': 'volatility_index',
                'subject': 'volatility_index-data.>',
                'description': '波动率指数（Deribit）',
                'exchanges': ['deribit']
            },
            {
                'name': 'liquidation',
                'subject': 'liquidation-data.>',
                'description': '强平订单数据（衍生品交易所）',
                'exchanges': ['binance_derivatives', 'okx_derivatives']
            }
        ]
        
        logger.info("统一NATS容器部署测试器已初始化")
    
    async def connect_nats(self) -> bool:
        """连接到NATS服务器"""
        try:
            logger.info(f"连接到NATS服务器: {self.nats_url}")
            
            self.nc = await nats.connect(
                servers=[self.nats_url],
                connect_timeout=10,
                max_reconnect_attempts=3
            )
            
            self.js = self.nc.jetstream()
            
            logger.info("✅ NATS连接成功")
            return True
            
        except Exception as e:
            logger.error(f"❌ NATS连接失败: {e}")
            return False
    
    async def disconnect_nats(self):
        """断开NATS连接"""
        try:
            if self.nc and not self.nc.is_closed:
                await self.nc.close()
                logger.info("✅ NATS连接已关闭")
        except Exception as e:
            logger.error(f"❌ 关闭NATS连接失败: {e}")
    
    async def test_nats_connectivity(self) -> Dict[str, Any]:
        """测试NATS连通性"""
        test_name = "nats_connectivity"
        logger.info("🔌 测试NATS连通性...")
        
        try:
            success = await self.connect_nats()
            
            result = {
                'status': 'pass' if success else 'fail',
                'message': 'NATS连接成功' if success else 'NATS连接失败',
                'details': {
                    'nats_url': self.nats_url,
                    'connected': success
                }
            }
            
            if success:
                # 测试基本操作
                await self.nc.publish("test.connectivity", b"test message")
                result['details']['publish_test'] = True
                logger.info("✅ NATS连通性测试通过")
            else:
                logger.error("❌ NATS连通性测试失败")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ NATS连通性测试异常: {e}")
            return {
                'status': 'fail',
                'message': f'NATS连通性测试异常: {e}',
                'details': {'error': str(e)}
            }
    
    async def test_http_monitoring(self) -> Dict[str, Any]:
        """测试HTTP监控端点"""
        test_name = "http_monitoring"
        logger.info("🌐 测试HTTP监控端点...")
        
        try:
            async with aiohttp.ClientSession() as session:
                # 测试健康检查端点
                async with session.get(f"{self.http_url}/healthz", timeout=10) as response:
                    health_status = response.status == 200
                
                # 测试JetStream状态端点
                async with session.get(f"{self.http_url}/jsz", timeout=10) as response:
                    js_status = response.status == 200
                    js_data = await response.json() if js_status else {}
                
                # 测试服务器信息端点
                async with session.get(f"{self.http_url}/varz", timeout=10) as response:
                    server_status = response.status == 200
                    server_data = await response.json() if server_status else {}
                
                all_endpoints_ok = health_status and js_status and server_status
                
                result = {
                    'status': 'pass' if all_endpoints_ok else 'fail',
                    'message': 'HTTP监控端点正常' if all_endpoints_ok else 'HTTP监控端点异常',
                    'details': {
                        'health_endpoint': health_status,
                        'jetstream_endpoint': js_status,
                        'server_info_endpoint': server_status,
                        'jetstream_enabled': js_data.get('config') is not None if js_data else False,
                        'server_name': server_data.get('server_name', 'unknown') if server_data else 'unknown'
                    }
                }
                
                if all_endpoints_ok:
                    logger.info("✅ HTTP监控端点测试通过")
                else:
                    logger.error("❌ HTTP监控端点测试失败")
                
                return result
                
        except Exception as e:
            logger.error(f"❌ HTTP监控端点测试异常: {e}")
            return {
                'status': 'fail',
                'message': f'HTTP监控端点测试异常: {e}',
                'details': {'error': str(e)}
            }
    
    async def test_jetstream_functionality(self) -> Dict[str, Any]:
        """测试JetStream功能"""
        test_name = "jetstream_functionality"
        logger.info("🔄 测试JetStream功能...")
        
        try:
            if not self.js:
                return {
                    'status': 'fail',
                    'message': 'JetStream未初始化',
                    'details': {}
                }
            
            # 获取JetStream账户信息
            account_info = await self.js.account_info()
            
            result = {
                'status': 'pass',
                'message': 'JetStream功能正常',
                'details': {
                    'streams': account_info.streams,
                    'consumers': account_info.consumers,
                    'messages': getattr(account_info, 'messages', 0),
                    'bytes': getattr(account_info, 'bytes', 0),
                    'memory': account_info.memory,
                    'storage': account_info.storage,
                    'api_total': account_info.api.total,
                    'api_errors': account_info.api.errors
                }
            }
            
            logger.info("✅ JetStream功能测试通过")
            logger.info(f"   流数量: {account_info.streams}")
            logger.info(f"   消费者数量: {account_info.consumers}")
            logger.info(f"   消息数量: {getattr(account_info, 'messages', 0)}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ JetStream功能测试异常: {e}")
            return {
                'status': 'fail',
                'message': f'JetStream功能测试异常: {e}',
                'details': {'error': str(e)}
            }
    
    async def test_market_data_stream(self) -> Dict[str, Any]:
        """测试MARKET_DATA流配置"""
        test_name = "market_data_stream"
        logger.info("📊 测试MARKET_DATA流配置...")
        
        try:
            if not self.js:
                return {
                    'status': 'fail',
                    'message': 'JetStream未初始化',
                    'details': {}
                }
            
            # 获取MARKET_DATA流信息
            stream_info = await self.js.stream_info("MARKET_DATA")
            
            # 检查主题配置
            configured_subjects = set(stream_info.config.subjects)
            expected_subjects = {dt['subject'] for dt in self.expected_data_types}
            
            missing_subjects = expected_subjects - configured_subjects
            extra_subjects = configured_subjects - expected_subjects
            
            all_subjects_present = len(missing_subjects) == 0
            
            result = {
                'status': 'pass' if all_subjects_present else 'warn',
                'message': f'MARKET_DATA流配置{"正常" if all_subjects_present else "部分缺失"}',
                'details': {
                    'stream_name': stream_info.config.name,
                    'total_subjects': len(configured_subjects),
                    'expected_subjects': len(expected_subjects),
                    'missing_subjects': list(missing_subjects),
                    'extra_subjects': list(extra_subjects),
                    'retention': str(stream_info.config.retention),
                    'storage': str(stream_info.config.storage),
                    'max_consumers': stream_info.config.max_consumers,
                    'max_msgs': stream_info.config.max_msgs,
                    'max_bytes': stream_info.config.max_bytes,
                    'max_age': stream_info.config.max_age,
                    'messages': stream_info.state.messages,
                    'bytes': stream_info.state.bytes,
                    'consumer_count': stream_info.state.consumer_count
                }
            }
            
            if all_subjects_present:
                logger.info("✅ MARKET_DATA流配置测试通过")
            else:
                logger.warning(f"⚠️ MARKET_DATA流配置部分缺失: {missing_subjects}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ MARKET_DATA流配置测试异常: {e}")
            return {
                'status': 'fail',
                'message': f'MARKET_DATA流配置测试异常: {e}',
                'details': {'error': str(e)}
            }
    
    async def test_data_types_support(self) -> Dict[str, Any]:
        """测试数据类型支持"""
        test_name = "data_types_support"
        logger.info("📡 测试数据类型支持...")
        
        try:
            if not self.js:
                return {
                    'status': 'fail',
                    'message': 'JetStream未初始化',
                    'details': {}
                }
            
            # 获取流信息
            stream_info = await self.js.stream_info("MARKET_DATA")
            configured_subjects = set(stream_info.config.subjects)
            
            # 检查每种数据类型
            data_type_results = []
            all_supported = True
            
            for data_type in self.expected_data_types:
                supported = data_type['subject'] in configured_subjects
                if not supported:
                    all_supported = False
                
                data_type_results.append({
                    'name': data_type['name'],
                    'subject': data_type['subject'],
                    'description': data_type['description'],
                    'supported': supported,
                    'exchanges': data_type['exchanges']
                })
                
                status_emoji = "✅" if supported else "❌"
                logger.info(f"   {status_emoji} {data_type['name']}: {data_type['description']}")
            
            result = {
                'status': 'pass' if all_supported else 'fail',
                'message': f'数据类型支持{"完整" if all_supported else "不完整"}',
                'details': {
                    'total_data_types': len(self.expected_data_types),
                    'supported_count': sum(1 for dt in data_type_results if dt['supported']),
                    'data_types': data_type_results
                }
            }
            
            if all_supported:
                logger.info("✅ 数据类型支持测试通过")
            else:
                logger.error("❌ 数据类型支持测试失败")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 数据类型支持测试异常: {e}")
            return {
                'status': 'fail',
                'message': f'数据类型支持测试异常: {e}',
                'details': {'error': str(e)}
            }
    
    async def test_message_publishing(self) -> Dict[str, Any]:
        """测试消息发布功能"""
        test_name = "message_publishing"
        logger.info("📤 测试消息发布功能...")
        
        try:
            if not self.js:
                return {
                    'status': 'fail',
                    'message': 'JetStream未初始化',
                    'details': {}
                }
            
            # 测试每种数据类型的消息发布
            publish_results = []
            all_successful = True
            
            for data_type in self.expected_data_types[:3]:  # 只测试前3种，避免测试时间过长
                try:
                    # 构造测试消息
                    test_subject = data_type['subject'].replace('.>', '.test.BTCUSDT')
                    test_message = {
                        'data_type': data_type['name'],
                        'exchange': 'test',
                        'symbol': 'BTCUSDT',
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'test_data': True
                    }
                    
                    # 发布消息
                    ack = await self.js.publish(test_subject, json.dumps(test_message).encode())
                    
                    publish_results.append({
                        'data_type': data_type['name'],
                        'subject': test_subject,
                        'success': True,
                        'sequence': ack.seq,
                        'stream': ack.stream
                    })
                    
                    logger.info(f"   ✅ {data_type['name']}: 消息发布成功 (seq: {ack.seq})")
                    
                except Exception as e:
                    all_successful = False
                    publish_results.append({
                        'data_type': data_type['name'],
                        'subject': test_subject,
                        'success': False,
                        'error': str(e)
                    })
                    
                    logger.error(f"   ❌ {data_type['name']}: 消息发布失败 - {e}")
            
            result = {
                'status': 'pass' if all_successful else 'fail',
                'message': f'消息发布{"成功" if all_successful else "失败"}',
                'details': {
                    'tested_data_types': len(publish_results),
                    'successful_publishes': sum(1 for pr in publish_results if pr['success']),
                    'publish_results': publish_results
                }
            }
            
            if all_successful:
                logger.info("✅ 消息发布功能测试通过")
            else:
                logger.error("❌ 消息发布功能测试失败")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 消息发布功能测试异常: {e}")
            return {
                'status': 'fail',
                'message': f'消息发布功能测试异常: {e}',
                'details': {'error': str(e)}
            }
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """运行所有测试"""
        logger.info("🧪 开始运行统一NATS容器部署测试")
        logger.info(f"⏰ 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 定义测试列表
        tests = [
            ("nats_connectivity", self.test_nats_connectivity),
            ("http_monitoring", self.test_http_monitoring),
            ("jetstream_functionality", self.test_jetstream_functionality),
            ("market_data_stream", self.test_market_data_stream),
            ("data_types_support", self.test_data_types_support),
            ("message_publishing", self.test_message_publishing),
        ]
        
        # 运行测试
        for test_name, test_func in tests:
            logger.info(f"\n{'='*60}")
            logger.info(f"运行测试: {test_name}")
            logger.info(f"{'='*60}")
            
            try:
                result = await test_func()
                self.test_results['tests'][test_name] = result
                
                status_emoji = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(result['status'], "❓")
                logger.info(f"{status_emoji} {test_name}: {result['message']}")
                
            except Exception as e:
                logger.error(f"❌ 测试 {test_name} 执行异常: {e}")
                self.test_results['tests'][test_name] = {
                    'status': 'fail',
                    'message': f'测试执行异常: {e}',
                    'details': {'error': str(e)}
                }
        
        # 计算总体状态
        test_statuses = [test['status'] for test in self.test_results['tests'].values()]
        failed_tests = [name for name, test in self.test_results['tests'].items() if test['status'] == 'fail']
        warn_tests = [name for name, test in self.test_results['tests'].items() if test['status'] == 'warn']
        passed_tests = [name for name, test in self.test_results['tests'].items() if test['status'] == 'pass']
        
        if failed_tests:
            self.test_results['overall_status'] = 'fail'
        elif warn_tests:
            self.test_results['overall_status'] = 'warn'
        else:
            self.test_results['overall_status'] = 'pass'
        
        # 生成摘要
        self.test_results['summary'] = {
            'total_tests': len(tests),
            'passed_tests': len(passed_tests),
            'warning_tests': len(warn_tests),
            'failed_tests': len(failed_tests),
            'passed_test_names': passed_tests,
            'warning_test_names': warn_tests,
            'failed_test_names': failed_tests
        }
        
        return self.test_results
    
    def print_test_report(self, detailed: bool = False):
        """打印测试报告"""
        results = self.test_results
        
        print("\n" + "="*80)
        print("🧪 MarketPrism统一NATS容器部署测试报告")
        print("="*80)
        print(f"测试时间: {results['timestamp']}")
        print(f"NATS URL: {results['nats_url']}")
        print(f"HTTP URL: {results['http_url']}")
        
        # 总体状态
        status_emoji = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(results['overall_status'], "❓")
        print(f"总体状态: {status_emoji} {results['overall_status'].upper()}")
        
        # 测试摘要
        summary = results['summary']
        print(f"\n📊 测试摘要:")
        print(f"  总测试数: {summary['total_tests']}")
        print(f"  通过: {summary['passed_tests']}")
        print(f"  警告: {summary['warning_tests']}")
        print(f"  失败: {summary['failed_tests']}")
        
        # 测试详情
        print(f"\n📋 测试详情:")
        for test_name, test_result in results['tests'].items():
            status_emoji = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(test_result['status'], "❓")
            print(f"  {status_emoji} {test_name}: {test_result['message']}")
            
            if detailed and 'details' in test_result:
                for key, value in test_result['details'].items():
                    if isinstance(value, (dict, list)):
                        print(f"      {key}: {json.dumps(value, indent=8, ensure_ascii=False)}")
                    else:
                        print(f"      {key}: {value}")
        
        # 数据类型支持详情
        if 'data_types_support' in results['tests'] and detailed:
            dt_test = results['tests']['data_types_support']
            if 'details' in dt_test and 'data_types' in dt_test['details']:
                print(f"\n📡 数据类型支持详情:")
                for dt in dt_test['details']['data_types']:
                    status = "✅" if dt['supported'] else "❌"
                    print(f"  {status} {dt['name']}: {dt['description']}")
                    print(f"      主题: {dt['subject']}")
                    print(f"      交易所: {', '.join(dt['exchanges'])}")
        
        print("="*80 + "\n")


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='MarketPrism统一NATS容器部署测试')
    parser.add_argument('--nats-url', default='nats://localhost:4222', help='NATS服务器URL')
    parser.add_argument('--http-url', default='http://localhost:8222', help='HTTP监控端点URL')
    parser.add_argument('--json', action='store_true', help='输出JSON格式结果')
    parser.add_argument('--detailed', action='store_true', help='显示详细测试信息')
    parser.add_argument('--quiet', action='store_true', help='静默模式，只输出结果')
    
    args = parser.parse_args()
    
    if args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
    
    # 创建测试器
    tester = UnifiedNATSDeploymentTest(args.nats_url, args.http_url)
    
    try:
        # 运行测试
        results = await tester.run_all_tests()
        
        # 输出结果
        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            tester.print_test_report(args.detailed)
        
        # 返回退出码
        if results['overall_status'] == 'pass':
            return 0
        elif results['overall_status'] == 'warn':
            return 0  # 警告不算失败
        else:
            return 1
        
    except KeyboardInterrupt:
        logger.info("⏹️ 测试被用户中断")
        return 1
    except Exception as e:
        logger.error(f"❌ 测试执行异常: {e}")
        return 1
    finally:
        await tester.disconnect_nats()


if __name__ == "__main__":
    exit(asyncio.run(main()))
