#!/usr/bin/env python3
"""
错误处理统一迁移脚本

将services中重复的错误处理实现迁移到统一使用core/errors/模块
"""

import os
import sys
import shutil
from pathlib import Path
import re
from typing import List, Dict

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

class ErrorHandlingMigrator:
    """错误处理迁移器"""
    
    def __init__(self):
        self.project_root = project_root
        self.backup_dir = self.project_root / "backup" / "error_migration"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # 需要迁移的文件
        self.duplicate_files = [
            "services/data-collector/src/marketprism_collector/unified_error_manager.py"
        ]
        
        # 需要更新导入的文件
        self.files_to_update = [
            "services/data-collector/src/marketprism_collector/collector.py",
            "services/data-collector/src/marketprism_collector/core_services.py",
            "services/data-collector/src/marketprism_collector/core_integration.py"
        ]
        
        print("🔄 错误处理迁移器初始化完成")
        print(f"📁 项目根目录: {self.project_root}")
        print(f"💾 备份目录: {self.backup_dir}")
    
    def run_migration(self):
        """执行完整迁移"""
        print("\n" + "="*60)
        print("🔄 开始错误处理统一迁移")
        print("="*60)
        
        try:
            # 1. 备份重复文件
            self._backup_duplicate_files()
            
            # 2. 分析重复代码
            self._analyze_duplicate_code()
            
            # 3. 创建适配器
            self._create_collector_error_adapter()
            
            # 4. 更新导入引用
            self._update_import_references()
            
            # 5. 移除重复文件
            self._remove_duplicate_files()
            
            # 6. 验证迁移结果
            self._verify_migration()
            
            print("\n✅ 错误处理迁移完成！")
            print("💡 建议运行测试验证功能正常")
            
        except Exception as e:
            print(f"\n❌ 迁移过程中发生错误: {e}")
            print("🔄 正在回滚...")
            self._rollback_migration()
            raise
    
    def _backup_duplicate_files(self):
        """备份重复文件"""
        print("💾 备份重复文件...")
        
        for file_path in self.duplicate_files:
            source_file = self.project_root / file_path
            if source_file.exists():
                backup_file = self.backup_dir / source_file.name
                shutil.copy2(source_file, backup_file)
                print(f"  💾 备份 {source_file} → {backup_file}")
    
    def _analyze_duplicate_code(self):
        """分析重复代码"""
        print("🔍 分析重复代码...")
        
        duplicate_file = self.project_root / self.duplicate_files[0]
        if not duplicate_file.exists():
            print("  ⚠️ 重复文件不存在，跳过分析")
            return
        
        with open(duplicate_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 分析关键类和函数
        classes = re.findall(r'class\s+(\w+)', content)
        functions = re.findall(r'def\s+(\w+)', content)
        
        print(f"  📊 发现类: {len(classes)} 个")
        print(f"  📊 发现函数: {len(functions)} 个")
        print(f"  📊 文件大小: {len(content.splitlines())} 行")
        
        # 关键类分析
        key_classes = [cls for cls in classes if 'Error' in cls or 'Manager' in cls]
        print(f"  🎯 关键类: {key_classes}")
    
    def _create_collector_error_adapter(self):
        """创建收集器错误适配器"""
        print("🔧 创建收集器错误适配器...")
        
        adapter_content = '''"""
MarketPrism Collector 错误处理适配器

提供收集器特定的错误处理功能，基于core/errors/统一错误处理框架
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass

# 使用Core错误处理模块
from core.errors import (
    UnifiedErrorHandler, get_global_error_handler,
    MarketPrismError, ErrorCategory, ErrorSeverity, ErrorType,
    ErrorContext, ErrorMetadata
)
from core.reliability import (
    get_reliability_manager,
    MarketPrismCircuitBreaker, CircuitBreakerConfig,
    AdaptiveRateLimiter, RateLimitConfig, RequestPriority
)


class CollectorErrorType(Enum):
    """收集器特定的错误类型"""
    EXCHANGE_CONNECTION = "exchange_connection"
    WEBSOCKET_DISCONNECTION = "websocket_disconnection"
    DATA_PARSING = "data_parsing"
    NATS_PUBLISH = "nats_publish"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    AUTH_FAILURE = "auth_failure"
    SUBSCRIPTION_FAILED = "subscription_failed"
    ADAPTER_CREATION = "adapter_creation"
    HEALTH_CHECK = "health_check"
    ORDERBOOK_PROCESSING = "orderbook_processing"


@dataclass
class ExchangeErrorContext:
    """交易所错误上下文"""
    exchange_name: str
    symbol: Optional[str] = None
    operation: Optional[str] = None
    retry_count: int = 0
    last_success_time: Optional[datetime] = None
    connection_state: str = "unknown"
    error_frequency: int = 0


class CollectorErrorAdapter:
    """收集器错误处理适配器 - 基于Core错误处理框架"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 使用Core错误处理器
        self.error_handler = get_global_error_handler()
        self.reliability_manager = get_reliability_manager()
        
        # 收集器特定的上下文
        self.exchange_contexts: Dict[str, ExchangeErrorContext] = {}
    
    async def handle_exchange_error(self, 
                                  exchange: str,
                                  error: Exception,
                                  context: Optional[ExchangeErrorContext] = None) -> Dict[str, Any]:
        """处理交易所错误 - 简化版本"""
        
        # 创建或更新上下文
        if exchange not in self.exchange_contexts:
            self.exchange_contexts[exchange] = ExchangeErrorContext(exchange_name=exchange)
        
        ctx = self.exchange_contexts[exchange]
        if context:
            ctx.symbol = context.symbol or ctx.symbol
            ctx.operation = context.operation or ctx.operation
            ctx.retry_count += 1
        
        # 分类错误
        error_type, severity = self._classify_error(error)
        
        # 转换为MarketPrismError并使用Core处理器
        marketprism_error = self._convert_to_marketprism_error(
            error, error_type, severity, exchange, ctx
        )
        
        error_id = self.error_handler.handle_error(marketprism_error)
        
        return {
            "error_id": error_id,
            "exchange": exchange,
            "error_type": error_type.value,
            "severity": severity.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "context": {
                "retry_count": ctx.retry_count,
                "symbol": ctx.symbol,
                "operation": ctx.operation
            }
        }
    
    def _classify_error(self, error: Exception) -> tuple:
        """分类错误类型和严重性"""
        error_msg = str(error).lower()
        
        if isinstance(error, (ConnectionError, TimeoutError)) or "connection" in error_msg:
            return CollectorErrorType.EXCHANGE_CONNECTION, ErrorSeverity.HIGH
        elif "websocket" in error_msg or "disconnect" in error_msg:
            return CollectorErrorType.WEBSOCKET_DISCONNECTION, ErrorSeverity.MEDIUM
        elif "auth" in error_msg or "unauthorized" in error_msg:
            return CollectorErrorType.AUTH_FAILURE, ErrorSeverity.HIGH
        elif "rate limit" in error_msg or "429" in error_msg:
            return CollectorErrorType.RATE_LIMIT_EXCEEDED, ErrorSeverity.LOW
        elif isinstance(error, (ValueError, KeyError, TypeError)):
            return CollectorErrorType.DATA_PARSING, ErrorSeverity.MEDIUM
        else:
            return CollectorErrorType.EXCHANGE_CONNECTION, ErrorSeverity.MEDIUM
    
    def _convert_to_marketprism_error(self, 
                                    error: Exception,
                                    error_type: CollectorErrorType,
                                    severity: ErrorSeverity,
                                    exchange: str,
                                    context: ExchangeErrorContext) -> MarketPrismError:
        """转换为MarketPrismError"""
        
        metadata = ErrorMetadata(
            error_id=str(id(error)),
            component="collector",
            exchange=exchange,
            symbol=context.symbol,
            operation=context.operation,
            retry_count=context.retry_count,
            first_occurrence=datetime.now(timezone.utc),
            last_occurrence=datetime.now(timezone.utc)
        )
        
        # 映射错误类型
        core_error_type = ErrorType.EXTERNAL_SERVICE_ERROR
        core_category = ErrorCategory.EXTERNAL_SERVICE
        
        if error_type == CollectorErrorType.WEBSOCKET_DISCONNECTION:
            core_error_type = ErrorType.NETWORK_ERROR
            core_category = ErrorCategory.INFRASTRUCTURE
        elif error_type == CollectorErrorType.DATA_PARSING:
            core_error_type = ErrorType.DATA_ERROR
            core_category = ErrorCategory.DATA_PROCESSING
        elif error_type == CollectorErrorType.AUTH_FAILURE:
            core_error_type = ErrorType.AUTHENTICATION_ERROR
            core_category = ErrorCategory.SECURITY
        
        return MarketPrismError(
            message=f"[{exchange}] {error_type.value}: {str(error)}",
            error_type=core_error_type,
            category=core_category,
            severity=severity,
            metadata=metadata,
            cause=error
        )


# 全局实例
collector_error_adapter = CollectorErrorAdapter()


# 便利函数
async def handle_collector_error(exchange: str, error: Exception, **kwargs):
    """处理收集器错误的便利函数"""
    return await collector_error_adapter.handle_exchange_error(exchange, error, **kwargs)


def log_collector_error(message: str, **kwargs):
    """记录收集器错误的便利函数"""
    logger = logging.getLogger("collector_error")
    logger.error(message, **kwargs)
'''
        
        adapter_file = self.project_root / "services/data-collector/src/marketprism_collector/error_adapter.py"
        with open(adapter_file, 'w', encoding='utf-8') as f:
            f.write(adapter_content)
        
        print(f"  ✅ 创建适配器: {adapter_file}")
    
    def _update_import_references(self):
        """更新导入引用"""
        print("🔧 更新导入引用...")
        
        # 导入映射
        import_mappings = {
            "from marketprism_collector.unified_error_manager import": "from marketprism_collector.error_adapter import",
            "from .unified_error_manager import": "from .error_adapter import",
            "CollectorErrorManager": "CollectorErrorAdapter",
            "unified_error_manager": "error_adapter"
        }
        
        for file_path in self.files_to_update:
            file_full_path = self.project_root / file_path
            if file_full_path.exists():
                try:
                    with open(file_full_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # 应用映射
                    updated = False
                    for old_import, new_import in import_mappings.items():
                        if old_import in content:
                            content = content.replace(old_import, new_import)
                            updated = True
                    
                    if updated:
                        with open(file_full_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                        print(f"  ✅ 更新导入: {file_full_path}")
                
                except Exception as e:
                    print(f"  ⚠️ 更新 {file_full_path} 失败: {e}")
    
    def _remove_duplicate_files(self):
        """移除重复文件"""
        print("🗑️ 移除重复文件...")
        
        for file_path in self.duplicate_files:
            file_full_path = self.project_root / file_path
            if file_full_path.exists():
                file_full_path.unlink()
                print(f"  🗑️ 删除: {file_full_path}")
    
    def _verify_migration(self):
        """验证迁移结果"""
        print("✅ 验证迁移结果...")
        
        # 检查适配器文件是否存在
        adapter_file = self.project_root / "services/data-collector/src/marketprism_collector/error_adapter.py"
        if adapter_file.exists():
            print("  ✅ 适配器文件创建成功")
        else:
            print("  ❌ 适配器文件创建失败")
        
        # 检查重复文件是否已删除
        for file_path in self.duplicate_files:
            file_full_path = self.project_root / file_path
            if not file_full_path.exists():
                print(f"  ✅ 重复文件已删除: {file_path}")
            else:
                print(f"  ❌ 重复文件仍存在: {file_path}")
    
    def _rollback_migration(self):
        """回滚迁移"""
        print("🔄 回滚迁移...")
        
        # 恢复备份文件
        for file_path in self.duplicate_files:
            source_file = self.project_root / file_path
            backup_file = self.backup_dir / Path(file_path).name
            
            if backup_file.exists():
                shutil.copy2(backup_file, source_file)
                print(f"  🔄 恢复: {backup_file} → {source_file}")


def main():
    """主函数"""
    migrator = ErrorHandlingMigrator()
    
    try:
        migrator.run_migration()
        print("\n🎯 错误处理迁移成功完成！")
        print("📋 下一步建议:")
        print("  1. 运行测试验证功能正常")
        print("  2. 检查日志确认错误处理工作正常")
        print("  3. 继续进行可靠性管理统一迁移")
        
    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
