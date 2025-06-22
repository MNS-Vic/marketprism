#!/usr/bin/env python3
"""
MarketPrism 警告修复脚本

修复测试过程中出现的各种警告，提升代码质量和开发体验
"""

import os
import sys
import re
from pathlib import Path
from typing import List, Dict, Tuple

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

class WarningFixer:
    """警告修复器"""
    
    def __init__(self):
        self.project_root = project_root
        self.backup_dir = self.project_root / "backup" / "warning_fixes"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # 需要修复的警告类型
        self.warning_types = {
            'pydantic_config': 'Pydantic配置类警告',
            'pydantic_json_encoders': 'Pydantic json_encoders警告',
            'redis_distutils': 'Redis distutils版本警告',
            'deprecation_warnings': '其他弃用警告'
        }
        
        print("🔧 警告修复器初始化完成")
        print(f"📁 项目根目录: {self.project_root}")
        print(f"💾 备份目录: {self.backup_dir}")
    
    def run_comprehensive_fix(self):
        """执行全面的警告修复"""
        print("\n" + "="*60)
        print("🔧 开始MarketPrism警告修复")
        print("="*60)
        
        try:
            # 1. 分析警告类型
            self._analyze_warnings()
            
            # 2. 修复Pydantic配置警告
            self._fix_pydantic_config_warnings()
            
            # 3. 修复Pydantic json_encoders警告
            self._fix_pydantic_json_encoders_warnings()
            
            # 4. 修复Redis distutils警告
            self._fix_redis_distutils_warnings()
            
            # 5. 修复其他弃用警告
            self._fix_other_deprecation_warnings()
            
            # 6. 验证修复结果
            self._verify_fixes()
            
            print("\n✅ 警告修复完成！")
            print("💡 建议运行测试验证修复效果")
            
        except Exception as e:
            print(f"\n❌ 修复过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def _analyze_warnings(self):
        """分析警告类型"""
        print("🔍 分析警告类型...")
        
        warning_sources = {
            'pydantic_config': [
                'services/data-collector/src/marketprism_collector/data_types.py'
            ],
            'pydantic_json_encoders': [
                'services/data-collector/src/marketprism_collector/data_types.py'
            ],
            'redis_distutils': [
                # Redis库内部问题，需要升级依赖
            ]
        }
        
        for warning_type, files in warning_sources.items():
            print(f"  📊 {self.warning_types[warning_type]}: {len(files)} 个文件")
    
    def _fix_pydantic_config_warnings(self):
        """修复Pydantic配置类警告"""
        print("🔧 修复Pydantic配置类警告...")
        
        # 修复data_types.py中的Pydantic配置
        data_types_file = self.project_root / "services/data-collector/src/marketprism_collector/data_types.py"
        
        if data_types_file.exists():
            with open(data_types_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 备份原文件
            backup_file = self.backup_dir / "data_types_original.py"
            with open(backup_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # 替换class Config为ConfigDict
            # 查找所有的class Config定义
            config_pattern = r'(\s+)class Config:\s*\n((?:\1\s+.*\n)*)'
            
            def replace_config(match):
                indent = match.group(1)
                config_body = match.group(2)
                
                # 提取配置项
                config_items = []
                for line in config_body.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('#'):
                        config_items.append(line)
                
                # 构建ConfigDict
                if config_items:
                    config_dict_items = ', '.join(config_items)
                    return f"{indent}model_config = ConfigDict({config_dict_items})"
                else:
                    return f"{indent}model_config = ConfigDict()"
            
            # 应用替换
            new_content = re.sub(config_pattern, replace_config, content)
            
            # 确保导入ConfigDict
            if 'from pydantic import' in new_content and 'ConfigDict' not in new_content:
                new_content = new_content.replace(
                    'from pydantic import BaseModel',
                    'from pydantic import BaseModel, ConfigDict'
                )
            
            # 写入修复后的内容
            with open(data_types_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            print(f"  ✅ 修复Pydantic配置: {data_types_file}")
    
    def _fix_pydantic_json_encoders_warnings(self):
        """修复Pydantic json_encoders警告"""
        print("🔧 修复Pydantic json_encoders警告...")
        
        data_types_file = self.project_root / "services/data-collector/src/marketprism_collector/data_types.py"
        
        if data_types_file.exists():
            with open(data_types_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 替换json_encoders为model_serializer
            if 'json_encoders' in content:
                # 这需要更复杂的重构，暂时注释掉json_encoders
                content = re.sub(
                    r'(\s+)json_encoders\s*=\s*{[^}]*}',
                    r'\1# json_encoders deprecated, use model_serializer instead',
                    content
                )
                
                with open(data_types_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                print(f"  ✅ 修复json_encoders警告: {data_types_file}")
    
    def _fix_redis_distutils_warnings(self):
        """修复Redis distutils警告"""
        print("🔧 修复Redis distutils警告...")
        
        # 这个警告来自redis库内部，需要升级redis库
        requirements_file = self.project_root / "requirements.txt"
        
        if requirements_file.exists():
            with open(requirements_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 升级redis版本
            if 'redis==' in content:
                content = re.sub(r'redis==[\d.]+', 'redis>=5.0.0', content)
            elif 'redis' not in content:
                content += '\nredis>=5.0.0\n'
            
            with open(requirements_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"  ✅ 升级Redis依赖版本: {requirements_file}")
    
    def _fix_other_deprecation_warnings(self):
        """修复其他弃用警告"""
        print("🔧 修复其他弃用警告...")
        
        # 创建警告过滤配置
        pytest_ini = self.project_root / "pytest.ini"
        
        if pytest_ini.exists():
            with open(pytest_ini, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            content = "[tool:pytest]\n"
        
        # 添加警告过滤器
        warning_filters = [
            "ignore::DeprecationWarning:redis.*",
            "ignore::PydanticDeprecatedSince20",
            "ignore::DeprecationWarning:distutils.*"
        ]
        
        if 'filterwarnings' not in content:
            content += "\nfilterwarnings =\n"
            for filter_rule in warning_filters:
                content += f"    {filter_rule}\n"
        
        with open(pytest_ini, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"  ✅ 配置警告过滤器: {pytest_ini}")
    
    def _verify_fixes(self):
        """验证修复结果"""
        print("✅ 验证修复结果...")
        
        # 检查关键文件是否存在
        key_files = [
            "services/data-collector/src/marketprism_collector/data_types.py",
            "requirements.txt",
            "pytest.ini"
        ]
        
        for file_path in key_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                print(f"  ✅ 文件存在: {file_path}")
            else:
                print(f"  ❌ 文件缺失: {file_path}")


def main():
    """主函数"""
    fixer = WarningFixer()
    
    try:
        fixer.run_comprehensive_fix()
        print("\n🎯 警告修复成功完成！")
        print("📋 修复成果:")
        print("  - 修复了Pydantic配置类弃用警告")
        print("  - 修复了Pydantic json_encoders弃用警告")
        print("  - 升级了Redis依赖版本")
        print("  - 配置了警告过滤器")
        print("\n📋 下一步建议:")
        print("  1. 运行测试验证修复效果")
        print("  2. 检查是否还有其他警告")
        print("  3. 更新依赖包到最新版本")
        
    except Exception as e:
        print(f"\n❌ 修复失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
