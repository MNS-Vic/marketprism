#!/usr/bin/env python3
"""
批量修复测试文件脚本
自动应用测试修复模式到多个测试文件
"""

import os
import sys
import re
from pathlib import Path
import subprocess
import time

# 添加项目根目录到路径
sys.path.insert(0, os.getcwd())

class TestFileFixer:
    """测试文件修复器"""
    
    def __init__(self):
        self.test_dir = Path("tests/unit/python_collector")
        self.helpers_template = self._load_helpers_template()
        self.fixed_count = 0
        self.failed_count = 0
        
    def _load_helpers_template(self):
        """加载测试助手模板"""
        return '''
# 添加路径
sys.path.insert(0, 'tests')
sys.path.insert(0, os.path.join(os.getcwd(), 'services', 'python-collector', 'src'))

# 导入助手
from helpers import AsyncTestManager, async_test_with_cleanup
'''

    def get_test_files_to_fix(self):
        """获取需要修复的测试文件列表"""
        test_files = []
        
        for test_file in self.test_dir.glob("test_*.py"):
            # 跳过已经修复的文件
            if "_fixed" in test_file.name:
                continue
                
            # 跳过我们已经手动修复的特定文件
            skip_files = [
                "test_types_fixed.py",
                "test_types_fixed_v2.py", 
                "test_types_fixed_v3.py"
            ]
            
            if test_file.name in skip_files:
                continue
                
            test_files.append(test_file)
        
        return test_files
    
    def analyze_test_file(self, test_file):
        """分析测试文件，识别常见问题"""
        content = test_file.read_text()
        issues = []
        
        # 检查异步测试问题
        if re.search(r'@pytest\.mark\.asyncio', content):
            if 'AsyncTestManager' not in content:
                issues.append("missing_async_cleanup")
        
        # 检查导入路径问题  
        if 'from marketprism_collector' in content:
            if 'sys.path.insert' not in content:
                issues.append("missing_import_path")
        
        # 检查Mock缺失问题
        if 'ImportError' not in content and 'except' not in content:
            issues.append("missing_mock_fallback")
            
        return issues
    
    def create_fixed_version(self, test_file):
        """创建测试文件的修复版本"""
        content = test_file.read_text()
        
        # 创建修复版本的文件名
        fixed_name = test_file.stem + "_fixed.py"
        fixed_path = test_file.parent / fixed_name
        
        # 应用修复
        fixed_content = self._apply_fixes(content, test_file.name)
        
        # 写入修复版本
        fixed_path.write_text(fixed_content)
        
        return fixed_path
    
    def _apply_fixes(self, content, filename):
        """应用各种修复到测试内容"""
        lines = content.split('\n')
        fixed_lines = []
        
        # 添加头部注释
        fixed_lines.append(f'"""')
        fixed_lines.append(f'{filename} - 修复版本')
        fixed_lines.append(f'批量修复应用：异步清理、导入路径、Mock回退')
        fixed_lines.append(f'"""')
        
        # 添加标准导入
        fixed_lines.extend([
            'import os',
            'import sys', 
            'import pytest',
            'import asyncio',
            'from unittest.mock import Mock, patch, AsyncMock',
            ''
        ])
        
        # 添加助手导入
        fixed_lines.extend(self.helpers_template.strip().split('\n'))
        fixed_lines.append('')
        
        # 添加Mock回退机制
        mock_section = '''
# 尝试导入实际模块，失败时使用Mock
try:
    # 实际导入将在这里添加
    MODULES_AVAILABLE = True
except ImportError:
    # Mock类将在这里添加  
    MODULES_AVAILABLE = False
'''
        fixed_lines.extend(mock_section.strip().split('\n'))
        fixed_lines.append('')
        
        # 处理原始内容
        skip_imports = True
        for line in lines:
            # 跳过原始导入部分
            if skip_imports:
                if line.strip().startswith('import ') or line.strip().startswith('from '):
                    continue
                if line.strip() == '' and not any(lines[i:i+5]):
                    continue
                skip_imports = False
            
            # 修复异步测试装饰器
            if '@pytest.mark.asyncio' in line:
                fixed_lines.append('    @async_test_with_cleanup')
                fixed_lines.append(line)
                continue
            
            # 包装异步测试体
            if 'async def test_' in line and '@async_test_with_cleanup' in fixed_lines[-2:]:
                fixed_lines.append(line)
                fixed_lines.append('        """修复：使用异步清理"""')
                fixed_lines.append('        async with AsyncTestManager() as manager:')
                continue
            
            fixed_lines.append(line)
        
        return '\n'.join(fixed_lines)
    
    def run_test_and_check(self, test_file):
        """运行测试并检查结果"""
        try:
            result = subprocess.run([
                sys.executable, '-m', 'pytest', 
                str(test_file), '-v', '--tb=short', '--maxfail=3'
            ], capture_output=True, text=True, timeout=30)
            
            # 分析结果
            if result.returncode == 0:
                return "PASSED", result.stdout.count('passed')
            else:
                return "FAILED", result.stdout.count('FAILED')
                
        except subprocess.TimeoutExpired:
            return "TIMEOUT", 0
        except Exception as e:
            return "ERROR", str(e)
    
    def batch_fix_tests(self):
        """批量修复测试"""
        test_files = self.get_test_files_to_fix()
        
        print(f"🔧 开始批量修复 {len(test_files)} 个测试文件...")
        print()
        
        for i, test_file in enumerate(test_files, 1):
            print(f"[{i}/{len(test_files)}] 处理: {test_file.name}")
            
            # 分析问题
            issues = self.analyze_test_file(test_file)
            print(f"   发现问题: {', '.join(issues) if issues else '无'}")
            
            # 创建修复版本
            try:
                fixed_file = self.create_fixed_version(test_file)
                print(f"   ✅ 创建修复版本: {fixed_file.name}")
                
                # 运行测试验证
                status, count = self.run_test_and_check(fixed_file)
                
                if status == "PASSED":
                    print(f"   🎉 测试通过: {count} 个测试")
                    self.fixed_count += 1
                else:
                    print(f"   ⚠️ 测试状态: {status} ({count})")
                    
            except Exception as e:
                print(f"   ❌ 修复失败: {e}")
                self.failed_count += 1
            
            print()
            
            # 避免过快处理
            time.sleep(0.5)
        
        # 总结
        print("=" * 50)
        print(f"📊 批量修复完成")
        print(f"✅ 成功修复: {self.fixed_count} 个文件")
        print(f"❌ 修复失败: {self.failed_count} 个文件")
        print(f"📈 成功率: {(self.fixed_count/(self.fixed_count+self.failed_count)*100):.1f}%")


def main():
    """主函数"""
    print("🧪 MarketPrism 测试批量修复工具")
    print("=" * 50)
    
    fixer = TestFileFixer()
    fixer.batch_fix_tests()


if __name__ == "__main__":
    main() 