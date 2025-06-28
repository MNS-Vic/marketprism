#!/usr/bin/env python3
"""
MarketPrism 数据迁移服务
负责将热数据定时迁移到冷存储
"""

import asyncio
import os
import sys
from pathlib import Path
import structlog
from datetime import datetime
import signal
import json

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from core.service_framework import BaseService
from core.storage.storage_config_manager import StorageConfigManager
from core.storage.data_migration_service import DataMigrationService

logger = structlog.get_logger(__name__)

class DataMigrationServiceApp(BaseService):
    """数据迁移服务应用"""
    
    def __init__(self, config: dict):
        super().__init__("data-migration-service", config)
        self.storage_config_manager = None
        self.migration_service = None
        self.migration_task = None
        self.is_running = False
        
    async def on_startup(self):
        """服务启动初始化"""
        try:
            # 设置API路由
            self.setup_routes()
            
            # 初始化存储配置管理器
            config_path = project_root / "config" / "storage_unified.yaml"
            self.storage_config_manager = StorageConfigManager(str(config_path))
            
            # 只有热存储模式才启动迁移服务
            if self.storage_config_manager.is_hot_storage():
                self.migration_service = DataMigrationService(self.storage_config_manager)
                await self.migration_service.start()
                
                # 启动定时迁移任务
                self.migration_task = asyncio.create_task(self._migration_scheduler())
                self.is_running = True
                
                self.logger.info("数据迁移服务已启动")
            else:
                self.logger.info("当前为冷存储模式，跳过迁移服务启动")
                
        except Exception as e:
            self.logger.error(f"数据迁移服务启动失败: {e}")
            raise
    
    async def on_shutdown(self):
        """服务关闭清理"""
        self.is_running = False
        
        if self.migration_task:
            self.migration_task.cancel()
            try:
                await self.migration_task
            except asyncio.CancelledError:
                pass
        
        if self.migration_service:
            await self.migration_service.stop()
        
        self.logger.info("数据迁移服务已关闭")
    
    def setup_routes(self):
        """设置API路由"""
        self.app.router.add_get("/api/v1/migration/status", self.get_migration_status)
        self.app.router.add_post("/api/v1/migration/execute", self.execute_migration)
        self.app.router.add_get("/api/v1/migration/stats", self.get_migration_stats)
        self.app.router.add_get("/api/v1/migration/config", self.get_migration_config)
    
    async def _migration_scheduler(self):
        """迁移调度器"""
        migration_config = self.storage_config_manager.get_migration_config()
        
        while self.is_running:
            try:
                # 检查是否在迁移时间窗口内
                current_hour = datetime.now().hour
                start_hour = migration_config.strategy.get('migration_window', {}).get('start_hour', 2)
                end_hour = migration_config.strategy.get('migration_window', {}).get('end_hour', 6)
                
                if start_hour <= current_hour < end_hour:
                    self.logger.info("开始执行定时数据迁移")
                    results = await self.migration_service.execute_migration_cycle()
                    
                    success_count = sum(1 for r in results if r.success)
                    total_records = sum(r.migrated_records for r in results if r.success)
                    
                    self.logger.info(
                        f"定时迁移完成: {success_count}/{len(results)} 任务成功, "
                        f"迁移记录数: {total_records}"
                    )
                    
                    # 迁移完成后等待到下一个周期
                    await asyncio.sleep(3600)  # 等待1小时
                else:
                    # 不在迁移时间窗口内，等待30分钟后再检查
                    await asyncio.sleep(1800)
                    
            except Exception as e:
                self.logger.error(f"定时迁移执行失败: {e}")
                await asyncio.sleep(300)  # 错误后等待5分钟
    
    async def get_migration_status(self, request):
        """获取迁移状态"""
        if not self.migration_service:
            return self.json_response({
                'enabled': False,
                'reason': 'Migration service not available (cold storage mode or initialization failed)'
            })
        
        status = await self.migration_service.get_migration_status()
        return self.json_response(status)
    
    async def execute_migration(self, request):
        """手动执行迁移"""
        if not self.migration_service:
            return self.json_response({
                'success': False,
                'error': 'Migration service not available'
            }, status=400)
        
        try:
            self.logger.info("手动执行数据迁移")
            results = await self.migration_service.execute_migration_cycle()
            
            success_count = sum(1 for r in results if r.success)
            total_records = sum(r.migrated_records for r in results if r.success)
            
            return self.json_response({
                'success': True,
                'total_tasks': len(results),
                'successful_tasks': success_count,
                'failed_tasks': len(results) - success_count,
                'total_records_migrated': total_records,
                'results': [
                    {
                        'table': r.task.table_name,
                        'partition': r.task.partition_id,
                        'success': r.success,
                        'records': r.migrated_records,
                        'duration': r.duration_seconds,
                        'error': r.error_message
                    }
                    for r in results
                ]
            })
            
        except Exception as e:
            self.logger.error(f"手动迁移执行失败: {e}")
            return self.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    async def get_migration_stats(self, request):
        """获取迁移统计"""
        if not self.migration_service:
            return self.json_response({
                'enabled': False,
                'stats': {}
            })
        
        stats = self.migration_service.get_migration_stats()
        return self.json_response({
            'enabled': True,
            'stats': stats
        })
    
    async def get_migration_config(self, request):
        """获取迁移配置"""
        if not self.storage_config_manager:
            return self.json_response({
                'error': 'Configuration manager not available'
            }, status=500)
        
        migration_config = self.storage_config_manager.get_migration_config()
        return self.json_response({
            'enabled': migration_config.enabled,
            'schedule_cron': migration_config.schedule_cron,
            'cold_storage_endpoint': migration_config.cold_storage_endpoint,
            'batch_size': migration_config.batch_size,
            'parallel_workers': migration_config.parallel_workers,
            'verification_enabled': migration_config.verification_enabled
        })

async def main():
    """主函数"""
    # 配置日志
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # 服务配置
    config = {
        'port': int(os.getenv('API_PORT', 8088)),
        'host': '0.0.0.0'
    }
    
    # 创建并运行服务
    service = DataMigrationServiceApp(config)
    
    # 设置信号处理
    def signal_handler(signum, frame):
        logger.info(f"收到信号 {signum}，准备关闭服务")
        asyncio.create_task(service.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await service.run()
    except KeyboardInterrupt:
        logger.info("收到键盘中断，关闭服务")
    except Exception as e:
        logger.error(f"服务运行异常: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
