#!/usr/bin/env python3
"""
MarketPrism 统一存储服务启动入口
参考unified_collector_main.py的设计模式

功能特性：
- 整合HTTP API和NATS订阅功能
- 使用统一配置管理器
- 支持环境变量覆盖
- 提供优雅启停机制
- 统一日志和监控
"""

import asyncio
import argparse
import signal
import sys
import os
from pathlib import Path
from typing import Dict, Any, Optional
import structlog
import yaml

# 确保能正确找到项目根目录
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 导入核心组件
from core.config.unified_config_manager import UnifiedConfigManager
from core.storage.unified_storage_manager import UnifiedStorageManager, UnifiedStorageConfig
from main import DataStorageService

class UnifiedStorageServiceLauncher:
    """统一存储服务启动器"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.service: Optional[DataStorageService] = None
        self.is_running = False
        self._service_task: Optional[asyncio.Task] = None

        # 设置日志
        self.logger = structlog.get_logger(__name__)

    async def start(self) -> bool:
        """启动存储服务"""
        try:
            self.logger.info("🚀 启动MarketPrism统一存储服务")
            
            # 1. 加载配置
            success = await self._load_configuration()
            if not success:
                return False
            
            # 2. 初始化服务
            success = await self._initialize_service()
            if not success:
                return False
            
            # 3. 启动服务
            success = await self._start_service()
            if not success:
                return False
            
            self.is_running = True
            self.logger.info("✅ 统一存储服务启动成功")
            return True
            
        except Exception as e:
            self.logger.error("❌ 统一存储服务启动失败", error=str(e), exc_info=True)
            return False
    
    async def _load_configuration(self) -> bool:
        """加载配置"""
        try:
            self.logger.info("📋 加载存储服务配置...")
            
            # 直接读取YAML配置（避免对不存在的 load_config_file 的依赖）
            import yaml
            cfg: dict = {}
            if self.config_path:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    cfg = yaml.safe_load(f) or {}
            else:
                # 使用默认配置路径
                default_path = Path(__file__).parent / "config" / "unified_storage_service.yaml"
                if default_path.exists():
                    with open(default_path, 'r', encoding='utf-8') as f:
                        cfg = yaml.safe_load(f) or {}
                else:
                    # 回退到collector配置
                    fallback_path = project_root / "config" / "collector" / "unified_data_collection.yaml"
                    with open(fallback_path, 'r', encoding='utf-8') as f:
                        cfg = yaml.safe_load(f) or {}
                    self.logger.info("📋 使用collector配置作为回退")

            # 环境变量覆盖关键字段（与统一规范一致）
            nats_servers = os.getenv('MARKETPRISM_NATS_SERVERS') or os.getenv('MARKETPRISM_NATS_URL')
            if nats_servers:
                servers_list = [s.strip() for s in nats_servers.split(',') if s.strip()]
                cfg.setdefault('nats', {})['servers'] = servers_list
                cfg['nats']['enabled'] = True
            ch_host = os.getenv('MARKETPRISM_CLICKHOUSE_HOST')
            ch_port = os.getenv('MARKETPRISM_CLICKHOUSE_PORT')
            ch_db = os.getenv('MARKETPRISM_CLICKHOUSE_DATABASE')
            if ch_host or ch_port or ch_db:
                cfg.setdefault('storage', {}).setdefault('clickhouse', {})
                if ch_host:
                    cfg['storage']['clickhouse']['host'] = ch_host
                if ch_port:
                    try:
                        cfg['storage']['clickhouse']['port'] = int(ch_port)
                    except Exception:
                        cfg['storage']['clickhouse']['port'] = ch_port
                if ch_db:
                    cfg['storage']['clickhouse']['database'] = ch_db

            self.config = cfg
            self.logger.info(
                "✅ 配置加载成功",
                nats_enabled=self.config.get('nats', {}).get('enabled', False),
                storage_enabled=self.config.get('storage', {}).get('enabled', True)
            )
            return True
            
        except Exception as e:
            self.logger.error("❌ 配置加载失败", error=str(e))
            return False
    
    async def _initialize_service(self) -> bool:
        """初始化服务"""
        try:
            self.logger.info("🔧 初始化存储服务组件...")
            
            # 创建存储服务实例
            self.service = DataStorageService(self.config)
            
            self.logger.info("✅ 存储服务组件初始化成功")
            return True
            
        except Exception as e:
            self.logger.error("❌ 存储服务组件初始化失败", error=str(e))
            return False
    
    async def _start_service(self) -> bool:
        """启动服务（后台任务运行 BaseService.run）"""
        try:
            self.logger.info("🚀 启动存储服务...")

            # 以后台任务启动 BaseService.run（避免阻塞本启动器）
            if self._service_task is None or self._service_task.done():
                self._service_task = asyncio.create_task(self.service.run())

            # 简单等待运行就绪
            await asyncio.sleep(1.0)
            self.logger.info("✅ 存储服务启动成功")
            return True

        except Exception as e:
            self.logger.error("❌ 存储服务启动失败", error=str(e))
            return False

    async def stop(self):
        """停止服务"""
        try:
            self.logger.info("🛑 停止统一存储服务")

            self.is_running = False

            # 取消后台运行任务，触发 BaseService.run 清理
            if self._service_task is not None:
                try:
                    self._service_task.cancel()
                    try:
                        await self._service_task
                    except asyncio.CancelledError:
                        pass
                finally:
                    self._service_task = None

            self.logger.info("✅ 统一存储服务已停止")

        except Exception as e:
            self.logger.error("❌ 停止存储服务失败", error=str(e))

    def get_service_info(self) -> Dict[str, Any]:
        """获取服务信息"""
        info = {
            "service": "unified-storage-service",
            "status": "running" if self.is_running else "stopped",
            "config_path": self.config_path,
        }
        
        if self.service:
            info.update({
                "nats_enabled": getattr(self.service, 'nats_enabled', False),
                "storage_manager": self.service.storage_manager is not None,
                "subscriptions": len(getattr(self.service, 'subscriptions', [])),
            })
        
        return info

def setup_logging():
    """设置日志"""
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

async def main():
    """主函数"""
    # 设置日志
    setup_logging()
    logger = structlog.get_logger(__name__)
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="MarketPrism统一存储服务")
    parser.add_argument(
        "--config", "-c",
        type=str,
        help="配置文件路径"
    )
    parser.add_argument(
        "--mode", "-m",
        type=str,
        choices=["production", "development", "test"],
        default="production",
        help="运行模式"
    )
    
    args = parser.parse_args()
    
    # 确定配置路径
    config_path = args.config or os.getenv('MARKETPRISM_STORAGE_CONFIG_PATH')
    
    # 创建服务启动器
    launcher = UnifiedStorageServiceLauncher(config_path=config_path)
    
    # 设置优雅停止信号处理
    stop_event = asyncio.Event()
    
    def signal_handler(signum, frame):
        logger.info(f"📡 收到停止信号 {signum}，开始优雅停止...")
        stop_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # 🚀 启动存储服务
        logger.info("🔄 正在启动统一存储服务...")
        success = await launcher.start()
        
        if not success:
            logger.error("❌ 统一存储服务启动失败")
            print("\n❌ 启动失败！请检查配置和依赖服务。\n")
            return 1
        
        # 显示启动成功信息
        service_info = launcher.get_service_info()
        print("\n" + "="*80)
        print("✅ MarketPrism统一存储服务启动成功！")
        print("="*80)
        print("💾 存储功能:")
        print(f"  • HTTP API: 提供RESTful存储接口")
        if service_info.get('nats_enabled'):
            print(f"  • NATS订阅: 从JetStream消费数据并存储")
            print(f"  • 订阅数量: {service_info.get('subscriptions', 0)}个数据流")
        print(f"  • 存储管理器: {'已初始化' if service_info.get('storage_manager') else '降级模式'}")
        print("🔗 数据流: NATS JetStream → 存储服务 → ClickHouse")
        print("📊 监控: 存储统计和性能监控")
        print("\n💡 按 Ctrl+C 优雅停止服务")
        print("="*80 + "\n")
        
        # 保持运行（除非是测试模式）
        if args.mode != 'test':
            logger.info("✅ 统一存储服务运行中，等待停止信号...")
            
            # 等待停止信号
            while launcher.is_running and not stop_event.is_set():
                await asyncio.sleep(1)
        
        logger.info("🛑 开始停止统一存储服务...")
        await launcher.stop()
        return 0
        
    except Exception as e:
        logger.error("统一存储服务运行失败", error=str(e), exc_info=True)
        return 1

if __name__ == "__main__":
    exit(asyncio.run(main()))
