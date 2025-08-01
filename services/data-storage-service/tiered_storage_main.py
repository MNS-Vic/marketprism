"""
MarketPrism 分层数据存储服务主程序
支持热端实时存储和冷端归档存储
"""

import asyncio
import argparse
import yaml
import sys
import os
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import structlog

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from hot_storage_service import HotStorageService
from cold_storage_service import ColdStorageService
from core.observability.logging.unified_logger import UnifiedLogger


class TieredStorageServiceManager:
    """分层存储服务管理器"""
    
    def __init__(self, config: Dict[str, Any], mode: str = "hot"):
        """
        初始化分层存储服务管理器
        
        Args:
            config: 服务配置
            mode: 运行模式 ("hot", "cold", "both")
        """
        self.config = config
        self.mode = mode
        self.logger = structlog.get_logger("services.data_storage.manager")
        
        # 服务实例
        self.hot_service: Optional[HotStorageService] = None
        self.cold_service: Optional[ColdStorageService] = None
        
        # 运行状态
        self.is_running = False
    
    async def start(self):
        """启动分层存储服务"""
        try:
            self.logger.info("🚀 启动分层数据存储服务", mode=self.mode)
            
            self.is_running = True
            
            # 根据模式启动相应服务
            if self.mode in ["hot", "both"]:
                await self._start_hot_service()
            
            if self.mode in ["cold", "both"]:
                await self._start_cold_service()
            
            self.logger.info("✅ 分层数据存储服务启动完成", mode=self.mode)
            
            # 如果是both模式，需要并发运行两个服务
            if self.mode == "both":
                await self._run_both_services()
            elif self.mode == "hot":
                await self.hot_service.start()
            elif self.mode == "cold":
                await self.cold_service.start()
            
        except Exception as e:
            self.logger.error("❌ 分层数据存储服务启动失败", error=str(e))
            await self.stop()
            raise
    
    async def _start_hot_service(self):
        """启动热端存储服务"""
        try:
            self.logger.info("🔥 启动热端存储服务")
            self.hot_service = HotStorageService(self.config)
            await self.hot_service.initialize()
            self.logger.info("✅ 热端存储服务初始化完成")
        except Exception as e:
            self.logger.error("❌ 热端存储服务启动失败", error=str(e))
            raise
    
    async def _start_cold_service(self):
        """启动冷端归档服务"""
        try:
            self.logger.info("🧊 启动冷端归档服务")
            self.cold_service = ColdStorageService(self.config)
            await self.cold_service.initialize()
            self.logger.info("✅ 冷端归档服务初始化完成")
        except Exception as e:
            self.logger.error("❌ 冷端归档服务启动失败", error=str(e))
            raise
    
    async def _run_both_services(self):
        """并发运行热端和冷端服务"""
        try:
            # 创建任务
            hot_task = asyncio.create_task(self.hot_service.start())
            cold_task = asyncio.create_task(self.cold_service.start())
            
            # 等待任一任务完成（通常是收到停止信号）
            done, pending = await asyncio.wait(
                [hot_task, cold_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # 取消未完成的任务
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
        except Exception as e:
            self.logger.error("❌ 并发运行服务失败", error=str(e))
            raise
    
    async def stop(self):
        """停止分层存储服务"""
        try:
            self.logger.info("🛑 停止分层数据存储服务")
            
            self.is_running = False
            
            # 停止热端服务
            if self.hot_service:
                await self.hot_service.stop()
                self.logger.info("✅ 热端存储服务已停止")
            
            # 停止冷端服务
            if self.cold_service:
                await self.cold_service.stop()
                self.logger.info("✅ 冷端归档服务已停止")
            
            self.logger.info("✅ 分层数据存储服务已停止")
            
        except Exception as e:
            self.logger.error("❌ 停止分层数据存储服务失败", error=str(e))
    
    def get_stats(self) -> Dict[str, Any]:
        """获取服务统计信息"""
        stats = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": self.mode,
            "is_running": self.is_running
        }
        
        if self.hot_service:
            stats["hot_service"] = self.hot_service.get_stats()
        
        if self.cold_service:
            stats["cold_service"] = self.cold_service.get_stats()
        
        return stats
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": self.mode,
            "services": {}
        }
        
        # 检查热端服务
        if self.hot_service:
            hot_health = await self.hot_service.health_check()
            health_status["services"]["hot_service"] = hot_health
            if hot_health["status"] != "healthy":
                health_status["status"] = "degraded"
        
        # 检查冷端服务
        if self.cold_service:
            cold_health = await self.cold_service.health_check()
            health_status["services"]["cold_service"] = cold_health
            if cold_health["status"] != "healthy":
                health_status["status"] = "degraded"
        
        return health_status


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="MarketPrism 分层数据存储服务")
    
    parser.add_argument(
        "--mode",
        choices=["hot", "cold", "both"],
        default="hot",
        help="运行模式: hot(热端存储), cold(冷端归档), both(同时运行)"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default="config/tiered_storage_config.yaml",
        help="配置文件路径"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="日志级别"
    )
    
    return parser.parse_args()


async def main():
    """主函数"""
    try:
        # 解析命令行参数
        args = parse_arguments()
        
        # 初始化日志
        logger = UnifiedLogger(
            service_name="tiered-data-storage-service",
            log_level=args.log_level
        )
        
        logger.info("🚀 MarketPrism 分层数据存储服务启动",
                   mode=args.mode,
                   config_file=args.config)
        
        # 加载配置
        config_path = Path(__file__).parent / args.config
        if not config_path.exists():
            logger.error("❌ 配置文件不存在", path=str(config_path))
            sys.exit(1)
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 创建并启动服务管理器
        service_manager = TieredStorageServiceManager(config, args.mode)
        await service_manager.start()
        
    except KeyboardInterrupt:
        logger.info("📡 收到中断信号，正在关闭服务...")
    except Exception as e:
        logger.error("❌ 服务启动失败", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
