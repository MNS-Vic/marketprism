#!/usr/bin/env python3
"""
MarketPrism配置文件审计分析工具
分析config目录下所有配置文件，识别重复、过时、未使用的配置
"""

import os
import json
import yaml
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict
import hashlib
import re

class ConfigAuditor:
    def __init__(self, config_root="config"):
        self.config_root = Path(config_root)
        self.files_by_type = defaultdict(list)
        self.files_by_category = defaultdict(list)
        self.duplicate_files = []
        self.unused_files = []
        self.file_dependencies = defaultdict(set)
        
    def scan_config_files(self):
        """扫描所有配置文件"""
        print("🔍 扫描配置文件...")
        
        for file_path in self.config_root.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith('.'):
                # 按文件类型分类
                suffix = file_path.suffix.lower()
                if suffix in ['.yaml', '.yml', '.json', '.xml', '.conf', '.py', '.sql', '.md']:
                    self.files_by_type[suffix].append(file_path)
                    
                # 按功能模块分类
                category = self._categorize_file(file_path)
                self.files_by_category[category].append(file_path)
        
        print(f"✅ 扫描完成，共发现 {sum(len(files) for files in self.files_by_type.values())} 个配置文件")
        
    def _categorize_file(self, file_path):
        """根据路径和文件名对文件进行分类"""
        path_str = str(file_path).lower()
        
        # 监控相关
        if any(keyword in path_str for keyword in ['monitoring', 'prometheus', 'grafana', 'alert']):
            return 'monitoring'
        
        # 交易所相关
        if any(keyword in path_str for keyword in ['exchange', 'binance', 'okx', 'deribit']):
            return 'exchanges'
        
        # 数据库相关
        if any(keyword in path_str for keyword in ['clickhouse', 'storage', 'database']):
            return 'database'
        
        # 消息队列相关
        if any(keyword in path_str for keyword in ['nats', 'message', 'queue']):
            return 'messaging'
        
        # 服务相关
        if any(keyword in path_str for keyword in ['service', 'gateway', 'collector']):
            return 'services'
        
        # 核心配置
        if any(keyword in path_str for keyword in ['core', 'factory', 'unified']):
            return 'core'
        
        # 测试配置
        if any(keyword in path_str for keyword in ['test', 'dev']):
            return 'testing'
        
        # 基础设施
        if any(keyword in path_str for keyword in ['infrastructure', 'systemd', 'proxy']):
            return 'infrastructure'
        
        return 'misc'
    
    def find_duplicate_files(self):
        """查找重复文件（基于内容哈希）"""
        print("🔍 查找重复文件...")
        
        file_hashes = defaultdict(list)
        
        for file_list in self.files_by_type.values():
            for file_path in file_list:
                try:
                    with open(file_path, 'rb') as f:
                        content_hash = hashlib.md5(f.read()).hexdigest()
                        file_hashes[content_hash].append(file_path)
                except Exception as e:
                    print(f"⚠️ 无法读取文件 {file_path}: {e}")
        
        # 找出重复文件
        for content_hash, files in file_hashes.items():
            if len(files) > 1:
                self.duplicate_files.append(files)
        
        print(f"✅ 发现 {len(self.duplicate_files)} 组重复文件")
    
    def analyze_file_dependencies(self):
        """分析文件依赖关系"""
        print("🔍 分析文件依赖关系...")
        
        # 扫描所有文件中的路径引用
        for file_list in self.files_by_type.values():
            for file_path in file_list:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                    # 查找配置文件引用
                    config_refs = re.findall(r'config/[a-zA-Z0-9_/.-]+\.(yaml|yml|json|xml|conf)', content)
                    for ref in config_refs:
                        ref_path = Path(ref)
                        if ref_path.exists():
                            self.file_dependencies[file_path].add(ref_path)
                            
                except Exception as e:
                    continue
        
        print(f"✅ 分析完成，发现 {len(self.file_dependencies)} 个文件有依赖关系")
    
    def identify_unused_files(self):
        """识别未使用的配置文件"""
        print("🔍 识别未使用的配置文件...")
        
        # 获取所有被引用的文件
        referenced_files = set()
        for deps in self.file_dependencies.values():
            referenced_files.update(deps)
        
        # 获取所有配置文件
        all_config_files = set()
        for file_list in self.files_by_type.values():
            all_config_files.update(file_list)
        
        # 找出可能未使用的文件（排除一些重要文件）
        important_patterns = [
            'docker-compose',
            'prometheus.yml',
            'alert_manager.yml',
            'exchanges.yaml',
            'services.yaml'
        ]
        
        for file_path in all_config_files:
            if file_path not in referenced_files:
                # 检查是否是重要文件
                is_important = any(pattern in str(file_path) for pattern in important_patterns)
                if not is_important:
                    self.unused_files.append(file_path)
        
        print(f"✅ 发现 {len(self.unused_files)} 个可能未使用的文件")
    
    def generate_report(self):
        """生成审计报告"""
        print("📊 生成审计报告...")
        
        report = {
            "audit_summary": {
                "total_files": sum(len(files) for files in self.files_by_type.values()),
                "files_by_type": {k: len(v) for k, v in self.files_by_type.items()},
                "files_by_category": {k: len(v) for k, v in self.files_by_category.items()},
                "duplicate_groups": len(self.duplicate_files),
                "potentially_unused": len(self.unused_files),
                "files_with_dependencies": len(self.file_dependencies)
            },
            "file_categories": {},
            "duplicate_files": [],
            "potentially_unused_files": [],
            "recommendations": []
        }
        
        # 详细分类信息
        for category, files in self.files_by_category.items():
            report["file_categories"][category] = [str(f) for f in files]
        
        # 重复文件信息
        for duplicate_group in self.duplicate_files:
            report["duplicate_files"].append([str(f) for f in duplicate_group])
        
        # 可能未使用的文件
        report["potentially_unused_files"] = [str(f) for f in self.unused_files]
        
        # 生成建议
        report["recommendations"] = self._generate_recommendations()
        
        return report
    
    def _generate_recommendations(self):
        """生成整理建议"""
        recommendations = []
        
        # 重复文件建议
        if self.duplicate_files:
            recommendations.append({
                "type": "duplicate_cleanup",
                "priority": "high",
                "description": f"发现 {len(self.duplicate_files)} 组重复文件，建议保留最新版本并删除重复文件"
            })
        
        # 未使用文件建议
        if self.unused_files:
            recommendations.append({
                "type": "unused_cleanup",
                "priority": "medium",
                "description": f"发现 {len(self.unused_files)} 个可能未使用的文件，建议移动到archive目录"
            })
        
        # 分类整理建议
        monitoring_files = len(self.files_by_category.get('monitoring', []))
        if monitoring_files > 10:
            recommendations.append({
                "type": "monitoring_reorganization",
                "priority": "high",
                "description": f"监控配置文件过多({monitoring_files}个)，建议进一步细分组织"
            })
        
        # 命名规范建议
        inconsistent_naming = []
        for category, files in self.files_by_category.items():
            for file_path in files:
                if '_' in file_path.name and '-' in file_path.name:
                    inconsistent_naming.append(file_path)
        
        if inconsistent_naming:
            recommendations.append({
                "type": "naming_standardization",
                "priority": "medium",
                "description": f"发现 {len(inconsistent_naming)} 个文件命名不一致，建议统一使用连字符或下划线"
            })
        
        return recommendations

def main():
    auditor = ConfigAuditor()
    
    # 执行审计
    auditor.scan_config_files()
    auditor.find_duplicate_files()
    auditor.analyze_file_dependencies()
    auditor.identify_unused_files()
    
    # 生成报告
    report = auditor.generate_report()
    
    # 保存报告
    with open('config_audit_report.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    # 打印摘要
    print("\n📊 配置文件审计摘要:")
    print(f"总文件数: {report['audit_summary']['total_files']}")
    print(f"按类型分布: {report['audit_summary']['files_by_type']}")
    print(f"按功能分布: {report['audit_summary']['files_by_category']}")
    print(f"重复文件组: {report['audit_summary']['duplicate_groups']}")
    print(f"可能未使用: {report['audit_summary']['potentially_unused']}")
    
    print(f"\n📋 详细报告已保存到: config_audit_report.json")

if __name__ == "__main__":
    main()
