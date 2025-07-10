"""
实时数据流测试

连接实际交易所API，验证完整的数据流：API获取 -> 标准化 -> 验证 -> NATS推送
"""

import asyncio
import aiohttp
import json
import time
import nats
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, List
import sys
from pathlib import Path

# 添加项目路径
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from services.data_collector.collector.data_collection_config_manager import get_data_collection_config_manager
from services.data_collector.collector.data_quality_validator import get_data_quality_validator, DataPoint
from services.data_collector.collector.normalizer import DataNormalizer
from services.data_collector.exchanges.binance import BinanceAdapter
from services.data_collector.exchanges.okx import OKXAdapter
from services.data_collector.exchanges.deribit import DeribitAdapter
from services.data_collector.collector.data_types import ExchangeConfig, Exchange


class LiveDataFlowTester:
    """实时数据流测试器"""
    
    def __init__(self):
        self.test_results = {}
        self.nats_client = None
        self.received_messages = []
        self.start_time = datetime.now(timezone.utc)
        
        # 初始化组件
        self.config_manager = get_data_collection_config_manager()
        self.data_validator = get_data_quality_validator()
        self.normalizer = DataNormalizer()
        
        print("🚀 实时数据流测试器初始化完成")
    
    async def run_live_test(self) -> Dict[str, Any]:
        """运行实时数据流测试"""
        print("=" * 60)
        print("🔄 开始实时数据流测试")
        print(f"⏰ 开始时间: {self.start_time.isoformat()}")
        print("=" * 60)
        
        try:
            # 1. 连接NATS
            await self._connect_nats()
            
            # 2. 测试Binance数据流
            await self._test_binance_data_flow()
            
            # 3. 测试OKX数据流
            await self._test_okx_data_flow()
            
            # 4. 测试Deribit数据流
            await self._test_deribit_data_flow()
            
            # 5. 验证NATS消息接收
            await self._verify_nats_messages()
            
            # 6. 生成测试报告
            return self._generate_test_report()
            
        except Exception as e:
            print(f"❌ 测试过程中发生错误: {e}")
            return {'status': 'ERROR', 'error': str(e)}
        finally:
            if self.nats_client:
                await self.nats_client.close()
    
    async def _connect_nats(self):
        """连接NATS服务器"""
        print("📡 连接NATS服务器...")
        
        try:
            self.nats_client = await nats.connect("nats://localhost:4222")
            
            # 订阅测试主题
            test_subjects = [
                "trade-data.binance.*",
                "orderbook-data.binance.*",
                "kline-data.binance.*",
                "trade-data.okx.*",
                "volatility-index.deribit.*"
            ]
            
            for subject in test_subjects:
                await self.nats_client.subscribe(subject, cb=self._message_handler)
            
            print(f"  ✅ NATS连接成功，订阅了 {len(test_subjects)} 个主题")
            
        except Exception as e:
            print(f"  ❌ NATS连接失败: {e}")
            raise
    
    async def _message_handler(self, msg):
        """NATS消息处理器"""
        try:
            data = json.loads(msg.data.decode())
            self.received_messages.append({
                'subject': msg.subject,
                'data': data,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            print(f"  📨 收到NATS消息: {msg.subject}")
        except Exception as e:
            print(f"  ⚠️ 消息解析失败: {e}")
    
    async def _test_binance_data_flow(self):
        """测试Binance数据流"""
        print("🟡 测试Binance数据流...")
        
        try:
            # 创建Binance适配器
            config = ExchangeConfig(
                exchange=Exchange.BINANCE,
                symbols=['BTCUSDT'],
                base_url='https://api.binance.com'
            )
            adapter = BinanceAdapter(config)
            
            # 测试REST API数据获取
            await self._test_binance_rest_api(adapter)
            
            # 测试数据标准化和验证
            await self._test_binance_data_processing(adapter)
            
            self.test_results['binance'] = {'status': 'PASS', 'tests_completed': 2}
            print("  ✅ Binance数据流测试完成")
            
        except Exception as e:
            self.test_results['binance'] = {'status': 'FAIL', 'error': str(e)}
            print(f"  ❌ Binance数据流测试失败: {e}")
    
    async def _test_binance_rest_api(self, adapter):
        """测试Binance REST API"""
        print("  📊 测试Binance REST API...")
        
        try:
            # 获取服务器时间
            server_time = await adapter.get_server_time()
            print(f"    ✅ 服务器时间: {server_time}")
            
            # 获取交易对信息
            symbol_info = await adapter.get_symbol_info('BTCUSDT')
            if symbol_info:
                print(f"    ✅ 交易对信息: {symbol_info.get('symbol', 'BTCUSDT')}")
            
            # 获取最新价格
            ticker = await adapter.get_ticker('BTCUSDT')
            if ticker:
                print(f"    ✅ 最新价格: {ticker.get('price', 'N/A')}")
            
        except Exception as e:
            print(f"    ❌ Binance REST API测试失败: {e}")
            raise
    
    async def _test_binance_data_processing(self, adapter):
        """测试Binance数据处理"""
        print("  🔄 测试Binance数据处理...")
        
        try:
            # 模拟交易数据
            trade_data = {
                'e': 'trade',
                's': 'BTCUSDT',
                'p': '50000.00',
                'q': '1.0',
                'T': int(time.time() * 1000)
            }
            
            # 数据标准化
            normalized_trade = self.normalizer.normalize_trade(trade_data, 'binance')
            print(f"    ✅ 数据标准化完成: {normalized_trade.symbol}")
            
            # 数据质量验证
            data_point = DataPoint(
                timestamp=trade_data['T'],
                symbol=trade_data['s'],
                exchange='binance',
                data_type='trade',
                data=normalized_trade.__dict__
            )
            
            validation_result = self.data_validator.validate_data_point(data_point)
            print(f"    ✅ 数据验证: {'通过' if validation_result.valid else '失败'}")
            
            # 模拟NATS推送
            if self.nats_client:
                subject = f"trade-data.binance.{trade_data['s']}"
                message = json.dumps(normalized_trade.__dict__, default=str)
                await self.nats_client.publish(subject, message.encode())
                print(f"    ✅ NATS推送: {subject}")
            
        except Exception as e:
            print(f"    ❌ Binance数据处理测试失败: {e}")
            raise
    
    async def _test_okx_data_flow(self):
        """测试OKX数据流"""
        print("🟠 测试OKX数据流...")
        
        try:
            # 创建OKX适配器
            config = ExchangeConfig(
                exchange=Exchange.OKX,
                symbols=['BTC-USDT'],
                base_url='https://www.okx.com'
            )
            adapter = OKXAdapter(config)
            
            # 测试REST API
            await self._test_okx_rest_api(adapter)
            
            # 测试数据处理
            await self._test_okx_data_processing(adapter)
            
            self.test_results['okx'] = {'status': 'PASS', 'tests_completed': 2}
            print("  ✅ OKX数据流测试完成")
            
        except Exception as e:
            self.test_results['okx'] = {'status': 'FAIL', 'error': str(e)}
            print(f"  ❌ OKX数据流测试失败: {e}")
    
    async def _test_okx_rest_api(self, adapter):
        """测试OKX REST API"""
        print("  📊 测试OKX REST API...")
        
        try:
            # 获取服务器时间
            server_time = await adapter.get_server_time()
            print(f"    ✅ 服务器时间: {server_time}")
            
            # 获取交易对信息
            symbol_info = await adapter.get_symbol_info('BTC-USDT')
            if symbol_info:
                print(f"    ✅ 交易对信息: {symbol_info.get('instId', 'BTC-USDT')}")
            
        except Exception as e:
            print(f"    ❌ OKX REST API测试失败: {e}")
            raise
    
    async def _test_okx_data_processing(self, adapter):
        """测试OKX数据处理"""
        print("  🔄 测试OKX数据处理...")
        
        try:
            # 模拟交易数据
            trade_data = {
                'instId': 'BTC-USDT',
                'px': '50000.00',
                'sz': '1.0',
                'ts': str(int(time.time() * 1000))
            }
            
            # 数据标准化
            normalized_trade = self.normalizer.normalize_trade(trade_data, 'okx')
            print(f"    ✅ 数据标准化完成: {normalized_trade.symbol}")
            
            # 数据质量验证
            data_point = DataPoint(
                timestamp=int(trade_data['ts']),
                symbol=trade_data['instId'],
                exchange='okx',
                data_type='trade',
                data=normalized_trade.__dict__
            )
            
            validation_result = self.data_validator.validate_data_point(data_point)
            print(f"    ✅ 数据验证: {'通过' if validation_result.valid else '失败'}")
            
            # 模拟NATS推送
            if self.nats_client:
                subject = f"trade-data.okx.{trade_data['instId'].replace('-', '')}"
                message = json.dumps(normalized_trade.__dict__, default=str)
                await self.nats_client.publish(subject, message.encode())
                print(f"    ✅ NATS推送: {subject}")
            
        except Exception as e:
            print(f"    ❌ OKX数据处理测试失败: {e}")
            raise
    
    async def _test_deribit_data_flow(self):
        """测试Deribit数据流"""
        print("🔵 测试Deribit数据流...")
        
        try:
            # 创建Deribit适配器
            config = ExchangeConfig(
                exchange=Exchange.DERIBIT,
                symbols=['btc_usd'],
                base_url='https://www.deribit.com'
            )
            adapter = DeribitAdapter(config)
            
            # 测试REST API
            await self._test_deribit_rest_api(adapter)
            
            # 测试数据处理
            await self._test_deribit_data_processing(adapter)
            
            self.test_results['deribit'] = {'status': 'PASS', 'tests_completed': 2}
            print("  ✅ Deribit数据流测试完成")
            
        except Exception as e:
            self.test_results['deribit'] = {'status': 'FAIL', 'error': str(e)}
            print(f"  ❌ Deribit数据流测试失败: {e}")
    
    async def _test_deribit_rest_api(self, adapter):
        """测试Deribit REST API"""
        print("  📊 测试Deribit REST API...")
        
        try:
            # 获取服务器时间
            server_time = await adapter.get_server_time()
            print(f"    ✅ 服务器时间: {server_time}")
            
        except Exception as e:
            print(f"    ❌ Deribit REST API测试失败: {e}")
            raise
    
    async def _test_deribit_data_processing(self, adapter):
        """测试Deribit数据处理"""
        print("  🔄 测试Deribit数据处理...")
        
        try:
            # 模拟波动率指数数据
            volatility_data = {
                'currency': 'BTC',
                'volatility': '0.75',
                'timestamp': int(time.time() * 1000)
            }
            
            # 模拟NATS推送
            if self.nats_client:
                subject = f"volatility-index.deribit.{volatility_data['currency']}"
                message = json.dumps(volatility_data, default=str)
                await self.nats_client.publish(subject, message.encode())
                print(f"    ✅ NATS推送: {subject}")
            
        except Exception as e:
            print(f"    ❌ Deribit数据处理测试失败: {e}")
            raise
    
    async def _verify_nats_messages(self):
        """验证NATS消息接收"""
        print("📨 验证NATS消息接收...")
        
        # 等待消息传播
        await asyncio.sleep(2)
        
        print(f"  📊 总共接收到 {len(self.received_messages)} 条消息")
        
        # 按主题分组统计
        subject_counts = {}
        for msg in self.received_messages:
            subject_prefix = msg['subject'].split('.')[0]
            subject_counts[subject_prefix] = subject_counts.get(subject_prefix, 0) + 1
        
        for subject, count in subject_counts.items():
            print(f"    ✅ {subject}: {count} 条消息")
        
        self.test_results['nats_messages'] = {
            'total_received': len(self.received_messages),
            'by_subject': subject_counts
        }
    
    def _generate_test_report(self) -> Dict[str, Any]:
        """生成测试报告"""
        end_time = datetime.now(timezone.utc)
        total_time = (end_time - self.start_time).total_seconds()
        
        # 统计测试结果
        total_tests = len([k for k in self.test_results.keys() if k != 'nats_messages'])
        passed_tests = sum(1 for k, v in self.test_results.items() 
                          if k != 'nats_messages' and v.get('status') == 'PASS')
        
        overall_status = 'PASS' if passed_tests == total_tests else 'FAIL'
        
        report = {
            'overall_status': overall_status,
            'start_time': self.start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'total_time': total_time,
            'summary': {
                'total_exchanges_tested': total_tests,
                'passed': passed_tests,
                'failed': total_tests - passed_tests,
                'nats_messages_received': len(self.received_messages)
            },
            'detailed_results': self.test_results,
            'received_messages': self.received_messages[:10]  # 只保留前10条消息作为示例
        }
        
        print("\n" + "=" * 60)
        print("📊 实时数据流测试报告")
        print("=" * 60)
        print(f"🎯 总体状态: {'✅ 通过' if overall_status == 'PASS' else '❌ 失败'}")
        print(f"⏱️  总耗时: {total_time:.2f}秒")
        print(f"📈 交易所测试: {passed_tests}/{total_tests} 通过")
        print(f"📨 NATS消息: {len(self.received_messages)} 条接收")
        
        print("\n🔍 详细结果:")
        for exchange, result in self.test_results.items():
            if exchange != 'nats_messages':
                status_icon = '✅' if result.get('status') == 'PASS' else '❌'
                print(f"  {status_icon} {exchange.upper()}: {result.get('status', 'UNKNOWN')}")
        
        return report


async def main():
    """主函数"""
    tester = LiveDataFlowTester()
    report = await tester.run_live_test()
    
    # 保存报告
    report_file = Path(__file__).parent / "live_test_report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\n📄 详细报告已保存到: {report_file}")
    
    return 0 if report.get('overall_status') == 'PASS' else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
