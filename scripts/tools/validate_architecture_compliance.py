#!/usr/bin/env python3
"""
Python-Collector架构规范符合性验证脚本
"""
import os
import ast
import importlib.util
from pathlib import Path
from typing import List, Dict, Tuple

class ArchitectureComplianceChecker:
    """架构规范符合性检查器"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        self.collector_src = self.project_root / "services/python-collector/src/marketprism_collector"
        self.config_root = self.project_root / "config"
        
        self.compliance_score = 0
        self.total_checks = 0
        self.issues = []
    
    def check_config_usage(self) -> Tuple[bool, str]:
        """检查配置文件使用规范"""
        self.total_checks += 1
        
        config_loader_file = self.collector_src / "config_loader.py"
        config_paths_file = self.collector_src / "config_paths.py"
        
        if not config_loader_file.exists():
            self.issues.append("❌ config_loader.py文件不存在")
            return False, "配置加载器缺失"
        
        if not config_paths_file.exists():
            self.issues.append("❌ config_paths.py文件不存在")
            return False, "配置路径管理器缺失"
        
        try:
            with open(config_paths_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 检查是否正确指向项目根目录config
            if "project_root" in content and "config" in content:
                self.compliance_score += 1
                return True, "✅ 正确使用项目根目录配置"
            else:
                self.issues.append("❌ 配置路径未指向项目根目录")
                return False, "配置路径不规范"
                
        except Exception as e:
            self.issues.append(f"❌ 检查配置使用失败: {e}")
            return False, str(e)
    
    def check_core_integration(self) -> Tuple[bool, str]:
        """检查Core层集成"""
        self.total_checks += 1
        
        core_services_file = self.collector_src / "core_services.py"
        
        if not core_services_file.exists():
            self.issues.append("❌ core_services.py文件不存在")
            return False, "Core服务适配器文件缺失"
        
        try:
            with open(core_services_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 检查是否导入了Core层服务
            core_imports = [
                "from core.monitoring import",
                "from core.security import", 
                "from core.reliability import",
                "from core.storage import",
                "from core.performance import",
                "from core.errors import",
                "from core.logging import",
                "from core.middleware import"
            ]
            
            found_imports = sum(1 for imp in core_imports if imp in content)
            
            if found_imports >= 5:  # 至少使用5个Core服务
                self.compliance_score += 1
                return True, f"✅ 正确集成{found_imports}个Core服务"
            else:
                self.issues.append(f"❌ 只集成了{found_imports}个Core服务")
                return False, "Core层集成不完整"
                
        except Exception as e:
            self.issues.append(f"❌ 检查Core集成失败: {e}")
            return False, str(e)
    
    def check_duplicate_components(self) -> Tuple[bool, str]:
        """检查重复组件"""
        self.total_checks += 1
        
        # 检查不应该存在的重复目录
        duplicate_dirs = ["core", "monitoring", "reliability", "storage"]
        found_duplicates = []
        
        for dir_name in duplicate_dirs:
            dir_path = self.collector_src / dir_name
            if dir_path.exists():
                # 检查是否包含实际代码
                py_files = list(dir_path.rglob("*.py"))
                non_init_files = [f for f in py_files if f.name != "__init__.py"]
                
                if non_init_files:
                    found_duplicates.append(f"{dir_name}({len(non_init_files)}个文件)")
        
        if not found_duplicates:
            self.compliance_score += 1
            return True, "✅ 无重复基础设施组件"
        else:
            self.issues.append(f"❌ 发现重复组件: {', '.join(found_duplicates)}")
            return False, f"存在重复组件: {', '.join(found_duplicates)}"
    
    def check_import_dependencies(self) -> Tuple[bool, str]:
        """检查导入依赖规范"""
        self.total_checks += 1
        
        violations = []
        
        # 检查所有Python文件的导入
        for py_file in self.collector_src.rglob("*.py"):
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 检查是否有不规范的导入
                bad_imports = [
                    "from services.python-collector",  # 不应该有跨服务导入
                    "from config.",  # 应该通过config_paths
                    "import config.",  # 应该通过config_paths
                ]
                
                for bad_import in bad_imports:
                    if bad_import in content:
                        violations.append(f"{py_file.name}: {bad_import}")
                        
            except Exception:
                continue
        
        if not violations:
            self.compliance_score += 1
            return True, "✅ 导入依赖规范"
        else:
            self.issues.extend([f"❌ 不规范导入: {v}" for v in violations])
            return False, f"发现{len(violations)}个不规范导入"
    
    def check_core_services_usage(self) -> Tuple[bool, str]:
        """检查Core服务使用情况"""
        self.total_checks += 1
        
        core_services_usage_count = 0
        
        # 检查Python文件中是否使用了core_services
        for py_file in self.collector_src.rglob("*.py"):
            if py_file.name in ["core_services.py", "config_paths.py"]:
                continue
                
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 检查是否使用了core_services
                core_service_patterns = [
                    "from .core_services import",
                    "from marketprism_collector.core_services import",
                    "core_services.",
                    "get_core_"
                ]
                
                if any(pattern in content for pattern in core_service_patterns):
                    core_services_usage_count += 1
                        
            except Exception:
                continue
        
        if core_services_usage_count >= 2:  # 至少2个文件使用Core服务
            self.compliance_score += 1
            return True, f"✅ {core_services_usage_count}个文件使用Core服务"
        else:
            self.issues.append(f"❌ 只有{core_services_usage_count}个文件使用Core服务")
            return False, "Core服务使用不足"
    
    def run_all_checks(self) -> Dict:
        """运行所有检查"""
        print("🔍 开始架构规范符合性检查...")
        
        checks = [
            ("配置使用规范", self.check_config_usage),
            ("Core层集成", self.check_core_integration), 
            ("重复组件检查", self.check_duplicate_components),
            ("导入依赖规范", self.check_import_dependencies),
            ("Core服务使用", self.check_core_services_usage),
        ]
        
        results = {}
        
        for check_name, check_func in checks:
            success, message = check_func()
            results[check_name] = {
                "success": success,
                "message": message
            }
            print(f"  {message}")
        
        # 计算符合度
        compliance_percentage = (self.compliance_score / self.total_checks) * 100
        
        # 生成报告
        report = {
            "compliance_score": self.compliance_score,
            "total_checks": self.total_checks,
            "compliance_percentage": compliance_percentage,
            "results": results,
            "issues": self.issues
        }
        
        print(f"\n📊 架构规范符合度: {compliance_percentage:.1f}% ({self.compliance_score}/{self.total_checks})")
        
        if self.issues:
            print("\n❌ 发现的问题:")
            for issue in self.issues:
                print(f"  {issue}")
        
        return report

def main():
    checker = ArchitectureComplianceChecker()
    report = checker.run_all_checks()
    
    # 保存报告
    import json
    import os
    
    # 确保temp目录存在
    os.makedirs("temp", exist_ok=True)
    
    with open("temp/architecture_compliance_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n📋 详细报告已保存到: temp/architecture_compliance_report.json")
    
    # 根据符合度给出改进建议
    compliance = report["compliance_percentage"]
    print(f"\n📋 改进建议:")
    
    if compliance >= 95:
        print("  🎉 架构规范符合度优秀，继续保持！")
    elif compliance >= 80:
        print("  ✅ 架构规范符合度良好，还有小幅改进空间")
        print("  💡 建议：解决剩余的小问题以达到95%+符合度")
    elif compliance >= 60:
        print("  ⚠️  架构规范符合度一般，需要重点改进")
        print("  💡 建议：优先解决Core服务集成和重复组件问题")
    else:
        print("  🔴 架构规范符合度较低，需要全面整改")
        print("  💡 建议：按照改进计划逐步实施，从配置管理开始")

if __name__ == "__main__":
    main()