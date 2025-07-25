#!/usr/bin/env python3
"""
MarketPrism 代码质量检测器
深度检测冗余、重复、冲突的代码和配置
"""

from datetime import datetime, timezone
import os
import sys
import ast
import json
import yaml
import hashlib
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict, Counter
import re
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CodeQualityChecker:
    """代码质量检测器"""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.results = {
            'unused_imports': {},
            'duplicate_functions': {},
            'redundant_configs': {},
            'unused_files': [],
            'port_conflicts': {},
            'duplicate_dependencies': {},
            'dead_code': {},
            'complexity_hotspots': {},
            'naming_inconsistencies': {}
        }
    
    def run_all_checks(self) -> Dict:
        """运行所有检查"""
        logger.info("🔍 开始代码质量检测...")
        
        # 1. 检查未使用的导入
        self.check_unused_imports()
        
        # 2. 检查重复函数
        self.check_duplicate_functions()
        
        # 3. 检查冗余配置
        self.check_redundant_configs()
        
        # 4. 检查未使用的文件
        self.check_unused_files()
        
        # 5. 检查端口冲突
        self.check_port_conflicts()
        
        # 6. 检查重复依赖
        self.check_duplicate_dependencies()
        
        # 7. 检查死代码
        self.check_dead_code()
        
        # 8. 检查复杂度热点
        self.check_complexity_hotspots()
        
        # 9. 检查命名不一致
        self.check_naming_inconsistencies()
        
        return self.results
    
    def check_unused_imports(self):
        """检查未使用的导入"""
        logger.info("🔍 检查未使用的导入...")
        
        for py_file in self.project_root.rglob("*.py"):
            if self._should_skip_file(py_file):
                continue
            
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 解析AST
                tree = ast.parse(content)
                
                # 收集所有导入
                imports = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.append(alias.name.split('.')[0])
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            imports.append(node.module.split('.')[0])
                        for alias in node.names:
                            imports.append(alias.name)
                
                # 检查是否使用
                unused = []
                for imp in imports:
                    if imp not in content or content.count(imp) == 1:  # 只出现在import行
                        unused.append(imp)
                
                if unused:
                    self.results['unused_imports'][str(py_file.relative_to(self.project_root))] = unused
                    
            except Exception as e:
                logger.warning(f"检查导入时出错 {py_file}: {e}")
    
    def check_duplicate_functions(self):
        """检查重复函数"""
        logger.info("🔍 检查重复函数...")
        
        function_hashes = defaultdict(list)
        
        for py_file in self.project_root.rglob("*.py"):
            if self._should_skip_file(py_file):
                continue
            
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                tree = ast.parse(content)
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        # 获取函数体的哈希值
                        func_body = ast.dump(node.body[0] if node.body else ast.Pass())
                        func_hash = hashlib.md5(func_body.encode()).hexdigest()
                        
                        function_hashes[func_hash].append({
                            'file': str(py_file.relative_to(self.project_root)),
                            'function': node.name,
                            'line': node.lineno
                        })
                        
            except Exception as e:
                logger.warning(f"检查函数时出错 {py_file}: {e}")
        
        # 找出重复的函数
        for func_hash, functions in function_hashes.items():
            if len(functions) > 1:
                self.results['duplicate_functions'][func_hash] = functions
    
    def check_redundant_configs(self):
        """检查冗余配置"""
        logger.info("🔍 检查冗余配置...")
        
        config_files = []
        config_files.extend(self.project_root.rglob("*.yaml"))
        config_files.extend(self.project_root.rglob("*.yml"))
        config_files.extend(self.project_root.rglob("*.json"))
        config_files.extend(self.project_root.rglob("*.toml"))
        
        config_contents = {}
        
        for config_file in config_files:
            if self._should_skip_file(config_file):
                continue
            
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    if config_file.suffix in ['.yaml', '.yml']:
                        content = yaml.safe_load(f)
                    elif config_file.suffix == '.json':
                        content = json.load(f)
                    else:
                        content = f.read()
                
                config_contents[str(config_file.relative_to(self.project_root))] = content
                
            except Exception as e:
                logger.warning(f"读取配置文件时出错 {config_file}: {e}")
        
        # 检查重复的配置内容
        content_hashes = defaultdict(list)
        for file_path, content in config_contents.items():
            content_hash = hashlib.md5(str(content).encode()).hexdigest()
            content_hashes[content_hash].append(file_path)
        
        for content_hash, files in content_hashes.items():
            if len(files) > 1:
                self.results['redundant_configs'][content_hash] = files
    
    def check_unused_files(self):
        """检查未使用的文件"""
        logger.info("🔍 检查未使用的文件...")
        
        # 可能未使用的文件类型
        suspicious_patterns = [
            '*.pyc', '*.pyo', '*.pyd',
            '*.log', '*.tmp', '*.bak', '*.old',
            '*~', '*.orig', '*.rej',
            '.DS_Store', 'Thumbs.db'
        ]
        
        for pattern in suspicious_patterns:
            for file_path in self.project_root.rglob(pattern):
                if file_path.is_file():
                    self.results['unused_files'].append(str(file_path.relative_to(self.project_root)))
        
        # 检查可能的孤儿文件
        python_files = set()
        imported_modules = set()
        
        for py_file in self.project_root.rglob("*.py"):
            if self._should_skip_file(py_file):
                continue
            
            python_files.add(str(py_file.relative_to(self.project_root)))
            
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 查找本地导入
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        if node.module and node.module.startswith('.'):
                            # 相对导入
                            module_path = self._resolve_relative_import(py_file, node.module)
                            if module_path:
                                imported_modules.add(module_path)
                        elif node.module and not node.module.startswith(('sys', 'os', 'json', 'yaml', 'asyncio')):
                            # 可能的本地导入
                            module_file = f"{node.module.replace('.', '/')}.py"
                            if (self.project_root / module_file).exists():
                                imported_modules.add(module_file)
                                
            except Exception as e:
                logger.warning(f"分析导入时出错 {py_file}: {e}")
        
        # 找出可能未被导入的Python文件
        orphan_files = python_files - imported_modules
        for orphan in orphan_files:
            if not any(x in orphan for x in ['__main__', 'main.py', 'start-', 'test_']):
                self.results['unused_files'].append(f"可能孤儿文件: {orphan}")
    
    def check_port_conflicts(self):
        """检查端口冲突"""
        logger.info("🔍 检查端口冲突...")
        
        port_usage = defaultdict(list)
        
        # 检查配置文件中的端口
        for config_file in self.project_root.rglob("*.yaml"):
            if self._should_skip_file(config_file):
                continue
            
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    content = yaml.safe_load(f)
                
                ports = self._extract_ports_from_config(content)
                for port in ports:
                    port_usage[port].append(str(config_file.relative_to(self.project_root)))
                    
            except Exception as e:
                logger.warning(f"检查端口配置时出错 {config_file}: {e}")
        
        # 检查Python代码中的端口
        for py_file in self.project_root.rglob("*.py"):
            if self._should_skip_file(py_file):
                continue
            
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 使用正则表达式查找端口号
                port_pattern = r'(?:port\s*[=:]\s*|:)(\d{4,5})'
                ports = re.findall(port_pattern, content, re.IGNORECASE)
                
                for port in ports:
                    if 1000 <= int(port) <= 65535:
                        port_usage[int(port)].append(str(py_file.relative_to(self.project_root)))
                        
            except Exception as e:
                logger.warning(f"检查端口使用时出错 {py_file}: {e}")
        
        # 找出冲突的端口
        for port, files in port_usage.items():
            if len(files) > 1:
                self.results['port_conflicts'][port] = files
    
    def check_duplicate_dependencies(self):
        """检查重复依赖"""
        logger.info("🔍 检查重复依赖...")
        
        requirement_files = []
        requirement_files.extend(self.project_root.rglob("requirements*.txt"))
        requirement_files.extend(self.project_root.rglob("setup.py"))
        requirement_files.extend(self.project_root.rglob("pyproject.toml"))
        
        dependencies = defaultdict(list)
        
        for req_file in requirement_files:
            try:
                with open(req_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if req_file.name.startswith('requirements'):
                    # requirements.txt格式
                    for line in content.split('\n'):
                        line = line.strip()
                        if line and not line.startswith('#'):
                            pkg_name = line.split('=')[0].split('>')[0].split('<')[0].strip()
                            dependencies[pkg_name].append(str(req_file.relative_to(self.project_root)))
                            
            except Exception as e:
                logger.warning(f"检查依赖时出错 {req_file}: {e}")
        
        # 找出重复的依赖
        for pkg, files in dependencies.items():
            if len(files) > 1:
                self.results['duplicate_dependencies'][pkg] = files
    
    def check_dead_code(self):
        """检查死代码"""
        logger.info("🔍 检查死代码...")
        
        defined_functions = set()
        called_functions = set()
        
        for py_file in self.project_root.rglob("*.py"):
            if self._should_skip_file(py_file):
                continue
            
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                tree = ast.parse(content)
                
                # 收集定义的函数
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        defined_functions.add(node.name)
                    elif isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Name):
                            called_functions.add(node.func.id)
                        elif isinstance(node.func, ast.Attribute):
                            called_functions.add(node.func.attr)
                            
            except Exception as e:
                logger.warning(f"检查死代码时出错 {py_file}: {e}")
        
        # 找出可能的死函数
        dead_functions = defined_functions - called_functions
        # 过滤掉常见的入口函数
        dead_functions = {f for f in dead_functions if f not in ['main', '__init__', 'run', 'start']}
        
        self.results['dead_code']['unused_functions'] = list(dead_functions)
    
    def check_complexity_hotspots(self):
        """检查复杂度热点"""
        logger.info("🔍 检查复杂度热点...")
        
        for py_file in self.project_root.rglob("*.py"):
            if self._should_skip_file(py_file):
                continue
            
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 简单的复杂度指标
                lines = len(content.split('\n'))
                functions = content.count('def ')
                classes = content.count('class ')
                nested_loops = len(re.findall(r'for.*for', content))
                nested_ifs = len(re.findall(r'if.*if', content))
                
                complexity_score = (
                    lines * 0.1 +
                    functions * 5 +
                    classes * 10 +
                    nested_loops * 15 +
                    nested_ifs * 10
                )
                
                if complexity_score > 100:  # 高复杂度文件
                    self.results['complexity_hotspots'][str(py_file.relative_to(self.project_root))] = {
                        'score': complexity_score,
                        'lines': lines,
                        'functions': functions,
                        'classes': classes,
                        'nested_complexity': nested_loops + nested_ifs
                    }
                    
            except Exception as e:
                logger.warning(f"检查复杂度时出错 {py_file}: {e}")
    
    def check_naming_inconsistencies(self):
        """检查命名不一致"""
        logger.info("🔍 检查命名不一致...")
        
        naming_patterns = {
            'snake_case': re.compile(r'^[a-z_][a-z0-9_]*$'),
            'camelCase': re.compile(r'^[a-z][a-zA-Z0-9]*$'),
            'PascalCase': re.compile(r'^[A-Z][a-zA-Z0-9]*$'),
            'UPPER_CASE': re.compile(r'^[A-Z_][A-Z0-9_]*$')
        }
        
        function_names = []
        class_names = []
        variable_names = []
        
        for py_file in self.project_root.rglob("*.py"):
            if self._should_skip_file(py_file):
                continue
            
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                tree = ast.parse(content)
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        function_names.append(node.name)
                    elif isinstance(node, ast.ClassDef):
                        class_names.append(node.name)
                    elif isinstance(node, ast.Name):
                        variable_names.append(node.id)
                        
            except Exception as e:
                logger.warning(f"检查命名时出错 {py_file}: {e}")
        
        # 分析命名模式
        inconsistencies = {}
        
        # 检查函数命名
        function_patterns = Counter()
        for name in function_names:
            for pattern_name, pattern in naming_patterns.items():
                if pattern.match(name):
                    function_patterns[pattern_name] += 1
                    break
        
        if len(function_patterns) > 1:
            inconsistencies['functions'] = dict(function_patterns)
        
        # 检查类命名
        class_patterns = Counter()
        for name in class_names:
            for pattern_name, pattern in naming_patterns.items():
                if pattern.match(name):
                    class_patterns[pattern_name] += 1
                    break
        
        if len(class_patterns) > 1:
            inconsistencies['classes'] = dict(class_patterns)
        
        self.results['naming_inconsistencies'] = inconsistencies
    
    def _should_skip_file(self, file_path: Path) -> bool:
        """是否应该跳过文件"""
        skip_patterns = [
            'venv', '__pycache__', '.git', '.pytest_cache',
            'node_modules', '.tox', 'build', 'dist'
        ]
        
        return any(pattern in str(file_path) for pattern in skip_patterns)
    
    def _extract_ports_from_config(self, config: dict, ports: List[int] = None) -> List[int]:
        """从配置中提取端口号"""
        if ports is None:
            ports = []
        
        if isinstance(config, dict):
            for key, value in config.items():
                if 'port' in str(key).lower() and isinstance(value, int):
                    if 1000 <= value <= 65535:
                        ports.append(value)
                elif isinstance(value, (dict, list)):
                    self._extract_ports_from_config(value, ports)
        elif isinstance(config, list):
            for item in config:
                self._extract_ports_from_config(item, ports)
        
        return ports
    
    def _resolve_relative_import(self, file_path: Path, module: str) -> str:
        """解析相对导入的模块路径"""
        try:
            # 简化的相对导入解析
            file_dir = file_path.parent
            parts = module.split('.')
            
            for part in parts:
                if part == '':
                    file_dir = file_dir.parent
                else:
                    file_dir = file_dir / part
            
            module_file = file_dir.with_suffix('.py')
            if module_file.exists():
                return str(module_file.relative_to(self.project_root))
        except:
            pass
        
        return None

def main():
    """主函数"""
    project_root = Path(__file__).parent.parent.parent
    
    checker = CodeQualityChecker(str(project_root))
    results = checker.run_all_checks()
    
    # 保存结果
    results_file = project_root / 'tests' / 'startup' / 'code_quality_results.json'
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    # 打印汇总
    print("\n" + "="*60)
    print("🔍 MarketPrism 代码质量检测报告")
    print("="*60)
    
    issues_count = 0
    
    for category, data in results.items():
        if data:
            count = len(data)
            issues_count += count
            print(f"📋 {category}: {count} 个问题")
    
    print(f"\n📊 总计发现 {issues_count} 个潜在问题")
    
    if issues_count == 0:
        print("🎉 恭喜！代码质量良好，未发现明显问题")
    elif issues_count < 10:
        print("👍 代码质量较好，有少量改进空间")
    elif issues_count < 30:
        print("⚠️  代码质量一般，建议重构部分代码")
    else:
        print("❌ 代码质量需要改进，建议进行大规模重构")
    
    print(f"\n📁 详细结果保存在: {results_file}")
    print("="*60)

if __name__ == "__main__":
    main()