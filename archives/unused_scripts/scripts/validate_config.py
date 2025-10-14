#!/usr/bin/env python3
"""
MarketPrism配置文件验证脚本

验证配置文件中的数据类型名称是否正确，避免常见的配置错误
"""

import sys
import yaml
from pathlib import Path
from typing import List, Dict, Any

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "services" / "data-collector"))

try:
    from collector.data_types import DataType
except ImportError as e:
    print(f"❌ 无法导入数据类型定义: {e}")
    sys.exit(1)

# 有效的数据类型名称
VALID_DATA_TYPES = {dt.value for dt in DataType}

# 常见错误映射
COMMON_ERRORS = {
    "trades": "trade",
    "positions": "lsr_top_position", 
    "accounts": "lsr_all_account",
    "funding": "funding_rate",
    "interest": "open_interest",
    "vol_index": "volatility_index",
    "liquidations": "liquidation"
}

def validate_data_types(data_types: List[str], exchange_name: str) -> List[str]:
    """验证数据类型列表"""
    errors = []
    
    for data_type in data_types:
        if data_type not in VALID_DATA_TYPES:
            error_msg = f"❌ {exchange_name}: 无效的数据类型 '{data_type}'"
            
            # 检查是否是常见错误
            if data_type in COMMON_ERRORS:
                correct_type = COMMON_ERRORS[data_type]
                error_msg += f" → 应该是 '{correct_type}'"
            
            errors.append(error_msg)
    
    return errors

def validate_exchange_config(exchange_name: str, config: Dict[str, Any]) -> List[str]:
    """验证单个交易所配置"""
    errors = []
    
    # 检查是否启用
    if not config.get('enabled', False):
        return []  # 未启用的交易所跳过验证
    
    # 检查数据类型配置
    data_types = config.get('data_types', [])
    if not data_types:
        errors.append(f"⚠️ {exchange_name}: 未配置数据类型")
        return errors
    
    # 验证数据类型名称
    type_errors = validate_data_types(data_types, exchange_name)
    errors.extend(type_errors)
    
    # 检查交易对配置
    symbols = config.get('symbols', [])
    if not symbols:
        errors.append(f"⚠️ {exchange_name}: 未配置交易对")
    
    return errors

def validate_config_file(config_path: Path) -> bool:
    """验证配置文件"""
    print(f"🔍 验证配置文件: {config_path}")
    
    # 检查文件是否存在
    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        return False
    
    # 加载配置文件
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"❌ YAML语法错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 配置文件加载失败: {e}")
        return False
    
    print("✅ 配置文件语法正确")
    
    # 验证交易所配置
    exchanges = config.get('exchanges', {})
    if not exchanges:
        print("❌ 未找到交易所配置")
        return False
    
    all_errors = []
    enabled_exchanges = 0
    
    for exchange_name, exchange_config in exchanges.items():
        if exchange_config.get('enabled', False):
            enabled_exchanges += 1
            errors = validate_exchange_config(exchange_name, exchange_config)
            all_errors.extend(errors)
    
    # 显示验证结果
    if enabled_exchanges == 0:
        print("⚠️ 没有启用的交易所")
        return False
    
    print(f"📊 启用的交易所数量: {enabled_exchanges}")
    
    if all_errors:
        print("\n❌ 发现配置错误:")
        for error in all_errors:
            print(f"  {error}")
        return False
    
    print("✅ 所有配置验证通过")
    return True

def show_valid_data_types():
    """显示有效的数据类型"""
    print("\n📋 有效的数据类型:")
    
    print("\n🔴 实时数据类型 (WebSocket):")
    realtime_types = ["trade", "orderbook", "liquidation"]
    for dt in realtime_types:
        if dt in VALID_DATA_TYPES:
            print(f"  ✅ {dt}")
    
    print("\n🟡 定时数据类型 (REST API):")
    scheduled_types = ["funding_rate", "open_interest", "volatility_index"]
    for dt in scheduled_types:
        if dt in VALID_DATA_TYPES:
            print(f"  ✅ {dt}")
    
    print("\n🟠 高频数据类型 (10秒间隔):")
    highfreq_types = ["lsr_top_position", "lsr_all_account"]
    for dt in highfreq_types:
        if dt in VALID_DATA_TYPES:
            print(f"  ✅ {dt}")
    
    print("\n❌ 常见错误:")
    for wrong, correct in COMMON_ERRORS.items():
        print(f"  '{wrong}' → '{correct}'")

def main():
    """主函数"""
    print("🚀 MarketPrism配置验证工具")
    print("=" * 50)
    
    # 默认配置文件路径
    default_config = project_root / "config" / "collector" / "unified_data_collection.yaml"
    
    # 检查命令行参数
    if len(sys.argv) > 1:
        if sys.argv[1] in ["-h", "--help"]:
            print("用法: python validate_config.py [配置文件路径]")
            print(f"默认配置文件: {default_config}")
            show_valid_data_types()
            return
        config_path = Path(sys.argv[1])
    else:
        config_path = default_config
    
    # 验证配置
    success = validate_config_file(config_path)
    
    if not success:
        print("\n💡 提示: 使用 --help 查看有效的数据类型")
        sys.exit(1)
    
    print("\n🎉 配置验证完成，可以安全启动系统！")

if __name__ == "__main__":
    main()
