#!/usr/bin/env python3
"""
数据验证测试脚本
测试所有数据格式验证和错误处理机制
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
import yaml

# 添加当前目录到Python路径
current_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(current_dir))

from simple_hot_storage import DataFormatValidator, DataValidationError


class DataValidationTester:
    """数据验证测试器"""
    
    def __init__(self):
        self.validator = DataFormatValidator()
        self.test_results = {
            "passed": 0,
            "failed": 0,
            "errors": []
        }
    
    def run_all_tests(self):
        """运行所有测试"""
        print("🧪 开始数据验证测试")
        print("=" * 60)
        
        # JSON 数据验证测试
        self._test_json_validation()
        
        # 数值验证测试
        self._test_numeric_validation()
        
        # 时间戳验证测试
        self._test_timestamp_validation()
        
        # 边界情况测试
        self._test_edge_cases()
        
        # 生成测试报告
        self._generate_report()
    
    def _test_json_validation(self):
        """测试JSON数据验证"""
        print("\n📋 测试 JSON 数据验证")
        
        test_cases = [
            # 正常情况
            {
                "name": "有效的字典数据",
                "input": [{"price": "50000.00", "quantity": "1.0"}],
                "expected": '[{"price":"50000.00","quantity":"1.0"}]'
            },
            {
                "name": "有效的JSON字符串",
                "input": '[{"price":"50000.00","quantity":"1.0"}]',
                "expected": '[{"price":"50000.00","quantity":"1.0"}]'
            },
            {
                "name": "空列表",
                "input": [],
                "expected": '[]'
            },
            {
                "name": "None值",
                "input": None,
                "expected": '[]'
            },
            # 错误情况
            {
                "name": "无效的JSON字符串",
                "input": "{'price': '50000.00'}",  # 单引号
                "expected": '[]'
            },
            {
                "name": "非JSON类型",
                "input": 12345,
                "expected": '[]'
            }
        ]
        
        for test_case in test_cases:
            try:
                result = self.validator.validate_json_data(test_case["input"], "test_field")
                if result == test_case["expected"]:
                    print(f"  ✅ {test_case['name']}")
                    self.test_results["passed"] += 1
                else:
                    print(f"  ❌ {test_case['name']}: 期望 {test_case['expected']}, 得到 {result}")
                    self.test_results["failed"] += 1
                    self.test_results["errors"].append(f"JSON验证失败: {test_case['name']}")
            except Exception as e:
                print(f"  ❌ {test_case['name']}: 异常 {e}")
                self.test_results["failed"] += 1
                self.test_results["errors"].append(f"JSON验证异常: {test_case['name']} - {e}")
    
    def _test_numeric_validation(self):
        """测试数值验证"""
        print("\n🔢 测试数值验证")
        
        test_cases = [
            # 正常情况
            {
                "name": "整数",
                "input": 12345,
                "expected": 12345
            },
            {
                "name": "浮点数",
                "input": 123.45,
                "expected": 123.45
            },
            {
                "name": "字符串整数",
                "input": "12345",
                "expected": 12345
            },
            {
                "name": "字符串浮点数",
                "input": "123.45",
                "expected": 123.45
            },
            {
                "name": "None值",
                "input": None,
                "expected": 0
            },
            # 错误情况
            {
                "name": "无效字符串",
                "input": "abc",
                "expected": 0
            },
            {
                "name": "空字符串",
                "input": "",
                "expected": 0
            }
        ]
        
        for test_case in test_cases:
            try:
                result = self.validator.validate_numeric(test_case["input"], "test_field", 0)
                if result == test_case["expected"]:
                    print(f"  ✅ {test_case['name']}")
                    self.test_results["passed"] += 1
                else:
                    print(f"  ❌ {test_case['name']}: 期望 {test_case['expected']}, 得到 {result}")
                    self.test_results["failed"] += 1
                    self.test_results["errors"].append(f"数值验证失败: {test_case['name']}")
            except Exception as e:
                print(f"  ❌ {test_case['name']}: 异常 {e}")
                self.test_results["failed"] += 1
                self.test_results["errors"].append(f"数值验证异常: {test_case['name']} - {e}")
    
    def _test_timestamp_validation(self):
        """测试时间戳验证"""
        print("\n⏰ 测试时间戳验证")
        
        test_cases = [
            # 正常情况
            {
                "name": "ISO格式时间戳",
                "input": "2025-07-27T12:30:45.123456+00:00",
                "expected": "2025-07-27 12:30:45.123456"
            },
            {
                "name": "简单ISO格式",
                "input": "2025-07-27T12:30:45Z",
                "expected": "2025-07-27 12:30:45Z"
            },
            {
                "name": "已格式化时间戳",
                "input": "2025-07-27 12:30:45.123",
                "expected": "2025-07-27 12:30:45.123"
            },
            {
                "name": "None值",
                "input": None,
                "expected_type": str  # 应该返回当前时间字符串
            }
        ]
        
        for test_case in test_cases:
            try:
                result = self.validator.validate_timestamp(test_case["input"], "test_field")
                
                if "expected_type" in test_case:
                    if isinstance(result, test_case["expected_type"]):
                        print(f"  ✅ {test_case['name']}")
                        self.test_results["passed"] += 1
                    else:
                        print(f"  ❌ {test_case['name']}: 期望类型 {test_case['expected_type']}, 得到 {type(result)}")
                        self.test_results["failed"] += 1
                elif result == test_case["expected"]:
                    print(f"  ✅ {test_case['name']}")
                    self.test_results["passed"] += 1
                else:
                    print(f"  ❌ {test_case['name']}: 期望 {test_case['expected']}, 得到 {result}")
                    self.test_results["failed"] += 1
                    self.test_results["errors"].append(f"时间戳验证失败: {test_case['name']}")
            except Exception as e:
                print(f"  ❌ {test_case['name']}: 异常 {e}")
                self.test_results["failed"] += 1
                self.test_results["errors"].append(f"时间戳验证异常: {test_case['name']} - {e}")
    
    def _test_edge_cases(self):
        """测试边界情况"""
        print("\n🔍 测试边界情况")
        
        # 测试极大的JSON数据
        large_data = [{"price": f"{i}.00", "quantity": "1.0"} for i in range(1000)]
        try:
            result = self.validator.validate_json_data(large_data, "large_data")
            if isinstance(result, str) and len(result) > 0:
                print("  ✅ 大型JSON数据处理")
                self.test_results["passed"] += 1
            else:
                print("  ❌ 大型JSON数据处理失败")
                self.test_results["failed"] += 1
        except Exception as e:
            print(f"  ❌ 大型JSON数据处理异常: {e}")
            self.test_results["failed"] += 1
        
        # 测试极值数字
        extreme_numbers = [
            ("极大正数", 1e15, 1e15),
            ("极小正数", 1e-15, 1e-15),
            ("负数", -12345, -12345),
            ("零", 0, 0)
        ]
        
        for name, input_val, expected in extreme_numbers:
            try:
                result = self.validator.validate_numeric(input_val, "test_field", 0)
                if result == expected:
                    print(f"  ✅ {name}")
                    self.test_results["passed"] += 1
                else:
                    print(f"  ❌ {name}: 期望 {expected}, 得到 {result}")
                    self.test_results["failed"] += 1
            except Exception as e:
                print(f"  ❌ {name}: 异常 {e}")
                self.test_results["failed"] += 1
    
    def _generate_report(self):
        """生成测试报告"""
        print("\n" + "=" * 60)
        print("📊 测试报告")
        print("=" * 60)
        
        total_tests = self.test_results["passed"] + self.test_results["failed"]
        success_rate = (self.test_results["passed"] / total_tests * 100) if total_tests > 0 else 0
        
        print(f"总测试数: {total_tests}")
        print(f"通过: {self.test_results['passed']}")
        print(f"失败: {self.test_results['failed']}")
        print(f"成功率: {success_rate:.1f}%")
        
        if self.test_results["errors"]:
            print(f"\n❌ 错误详情:")
            for error in self.test_results["errors"]:
                print(f"  - {error}")
        
        if success_rate == 100:
            print("\n🎉 所有测试通过！数据验证功能正常工作。")
        else:
            print(f"\n⚠️ 有 {self.test_results['failed']} 个测试失败，需要检查。")
        
        return success_rate == 100


def main():
    """主函数"""
    tester = DataValidationTester()
    success = tester.run_all_tests()
    
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
