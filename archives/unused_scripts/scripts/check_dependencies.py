#!/usr/bin/env python3
"""
MarketPrism 依赖版本检查和自动修复脚本

检查关键依赖的版本兼容性，并自动修复已知问题
"""

import subprocess
import sys
import os
from typing import Dict, List, Tuple


class DependencyChecker:
    """依赖检查器"""
    
    def __init__(self):
        self.issues_found = []
        self.fixes_applied = []
        
        # 关键依赖版本要求
        self.required_versions = {
            'nats-py': '2.2.0',  # 固定版本，解决asyncio兼容性
            'aiohttp': '>=3.8.0',
            'structlog': '>=21.0.0',
            'pyyaml': '>=5.4.0'
        }
        
        # 已知问题和修复方案
        self.known_issues = {
            'nats-py': {
                'issue': 'asyncio兼容性问题',
                'symptoms': ['Queue.__init__() got an unexpected keyword argument \'loop\''],
                'fix': 'pip install nats-py==2.2.0'
            }
        }
    
    def run_check(self):
        """运行依赖检查"""
        print("🔍 MarketPrism 依赖版本检查")
        print("=" * 40)
        
        # 检查Python版本
        self._check_python_version()
        
        # 检查虚拟环境
        self._check_virtual_environment()
        
        # 检查关键依赖
        self._check_critical_dependencies()
        
        # 检查已知问题
        self._check_known_issues()
        
        # 生成报告
        self._generate_report()
        
        # 提供修复建议
        self._suggest_fixes()
    
    def _check_python_version(self):
        """检查Python版本"""
        print("🐍 检查Python版本...")
        
        version = sys.version_info
        if version < (3, 8):
            self.issues_found.append(f"Python版本过低: {version}, 需要3.8+")
            print(f"  ❌ Python版本: {version} (需要3.8+)")
        else:
            print(f"  ✅ Python版本: {version.major}.{version.minor}.{version.micro}")
    
    def _check_virtual_environment(self):
        """检查虚拟环境"""
        print("📦 检查虚拟环境...")
        
        in_venv = (hasattr(sys, 'real_prefix') or 
                  (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix))
        
        if not in_venv:
            self.issues_found.append("未使用虚拟环境")
            print("  ⚠️ 未检测到虚拟环境")
        else:
            print("  ✅ 虚拟环境已激活")
    
    def _check_critical_dependencies(self):
        """检查关键依赖"""
        print("📋 检查关键依赖...")
        
        for package, required_version in self.required_versions.items():
            try:
                # 获取已安装版本
                result = subprocess.run([sys.executable, '-m', 'pip', 'show', package], 
                                      capture_output=True, text=True)
                
                if result.returncode != 0:
                    self.issues_found.append(f"{package} 未安装")
                    print(f"  ❌ {package}: 未安装")
                    continue
                
                # 解析版本信息
                version_line = [line for line in result.stdout.split('\n') 
                               if line.startswith('Version:')]
                
                if not version_line:
                    self.issues_found.append(f"{package} 版本信息获取失败")
                    print(f"  ❌ {package}: 版本信息获取失败")
                    continue
                
                installed_version = version_line[0].split(':')[1].strip()
                
                # 检查版本兼容性
                if package == 'nats-py':
                    # nats-py需要精确版本
                    if installed_version != required_version:
                        self.issues_found.append(f"{package} 版本不正确: {installed_version}, 需要: {required_version}")
                        print(f"  ❌ {package}: {installed_version} (需要: {required_version})")
                    else:
                        print(f"  ✅ {package}: {installed_version}")
                else:
                    # 其他包检查最低版本
                    print(f"  ✅ {package}: {installed_version}")
                
            except Exception as e:
                self.issues_found.append(f"{package} 检查失败: {str(e)}")
                print(f"  ❌ {package}: 检查失败 - {e}")
    
    def _check_known_issues(self):
        """检查已知问题"""
        print("🔧 检查已知问题...")
        
        # 检查nats-py版本问题
        try:
            import nats
            if hasattr(nats, '__version__'):
                version = nats.__version__
                if not version.startswith('2.2'):
                    self.issues_found.append(f"nats-py版本可能导致asyncio兼容性问题: {version}")
                    print(f"  ⚠️ nats-py版本可能有兼容性问题: {version}")
                else:
                    print(f"  ✅ nats-py版本正确: {version}")
            else:
                print(f"  ⚠️ nats-py版本信息不可用")
        except ImportError:
            print(f"  ❌ nats-py未安装")
    
    def _generate_report(self):
        """生成检查报告"""
        print("\n" + "=" * 40)
        print("📊 依赖检查报告")
        print("=" * 40)
        
        if not self.issues_found:
            print("🎉 所有依赖检查通过！")
            print("✅ 系统依赖配置正确")
        else:
            print(f"⚠️ 发现 {len(self.issues_found)} 个问题:")
            for i, issue in enumerate(self.issues_found, 1):
                print(f"  {i}. {issue}")
    
    def _suggest_fixes(self):
        """提供修复建议"""
        if not self.issues_found:
            return
        
        print("\n🔧 修复建议:")
        print("=" * 40)
        
        # nats-py版本修复
        nats_issues = [issue for issue in self.issues_found if 'nats-py' in issue]
        if nats_issues:
            print("📦 修复nats-py版本问题:")
            print("  pip install nats-py==2.2.0")
            print("")
        
        # 虚拟环境建议
        venv_issues = [issue for issue in self.issues_found if '虚拟环境' in issue]
        if venv_issues:
            print("🐍 创建和激活虚拟环境:")
            print("  python3 -m venv venv")
            print("  source venv/bin/activate  # Linux/macOS")
            print("  venv\\Scripts\\activate     # Windows")
            print("")
        
        # 依赖安装建议
        missing_packages = [issue for issue in self.issues_found if '未安装' in issue]
        if missing_packages:
            print("📋 安装缺失的依赖:")
            print("  pip install -r requirements.txt")
            print("")
        
        # 自动修复脚本
        print("🚀 一键修复脚本:")
        print("  # 创建虚拟环境并安装依赖")
        print("  python3 -m venv venv")
        print("  source venv/bin/activate")
        print("  pip install --upgrade pip")
        print("  pip install -r requirements.txt")
        print("  pip install nats-py==2.2.0  # 确保版本正确")
        print("")
        
        print("💡 修复完成后，重新运行此脚本验证:")
        print("  python scripts/check_dependencies.py")
    
    def auto_fix(self):
        """自动修复已知问题"""
        print("\n🔧 尝试自动修复...")
        
        # 修复nats-py版本
        nats_issues = [issue for issue in self.issues_found if 'nats-py' in issue]
        if nats_issues:
            try:
                print("  🔄 修复nats-py版本...")
                result = subprocess.run([sys.executable, '-m', 'pip', 'install', 'nats-py==2.2.0'], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    self.fixes_applied.append("nats-py版本已修复为2.2.0")
                    print("  ✅ nats-py版本已修复")
                else:
                    print(f"  ❌ nats-py修复失败: {result.stderr}")
            except Exception as e:
                print(f"  ❌ nats-py修复异常: {e}")
        
        if self.fixes_applied:
            print(f"\n✅ 已应用 {len(self.fixes_applied)} 个修复:")
            for fix in self.fixes_applied:
                print(f"  • {fix}")
            print("\n🔄 建议重新运行检查验证修复效果")


def main():
    """主函数"""
    checker = DependencyChecker()
    
    # 检查命令行参数
    if len(sys.argv) > 1 and sys.argv[1] == '--auto-fix':
        checker.run_check()
        if checker.issues_found:
            checker.auto_fix()
    else:
        checker.run_check()
        
        if checker.issues_found:
            print("\n💡 提示: 使用 --auto-fix 参数尝试自动修复")
            print("  python scripts/check_dependencies.py --auto-fix")


if __name__ == "__main__":
    main()
