#!/usr/bin/env python3
"""
MarketPrism 策略管理服务
支持网格策略、信号交易、定投策略等多种量化交易策略管理
"""

import asyncio
import sys
import os
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
import structlog

# 导入MarketPrism核心模块
from core.config.unified_config_manager import UnifiedConfigManager

# 配置结构化日志
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="ISO"),
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

logger = structlog.get_logger()

# ===============================
# 数据模型定义
# ===============================

class GridStrategyConfig(BaseModel):
    """网格策略配置"""
    name: str = Field(..., description="策略名称")
    symbol: str = Field(..., description="交易对，如 BTCUSDT")
    exchange: str = Field("binance", description="交易所")
    lower_price: float = Field(..., description="网格下界价格")
    upper_price: float = Field(..., description="网格上界价格")
    grid_count: int = Field(..., description="网格数量")
    investment_amount: float = Field(..., description="投资金额")
    auto_restart: bool = Field(True, description="自动重启")

class SignalStrategyConfig(BaseModel):
    """信号交易策略配置"""
    name: str = Field(..., description="策略名称")
    symbol: str = Field(..., description="交易对")
    exchange: str = Field("binance", description="交易所")
    signal_source: str = Field(..., description="信号源类型")
    position_size: float = Field(..., description="仓位大小")
    stop_loss: Optional[float] = Field(None, description="止损百分比")
    take_profit: Optional[float] = Field(None, description="止盈百分比")

class DCAStrategyConfig(BaseModel):
    """定投策略配置"""
    name: str = Field(..., description="策略名称")
    symbols: List[str] = Field(..., description="定投币种列表")
    exchange: str = Field("binance", description="交易所")
    interval: str = Field("daily", description="定投间隔：daily/weekly/monthly")
    amount_per_order: float = Field(..., description="每次定投金额")
    allocation: Dict[str, float] = Field(..., description="各币种分配比例")

class StrategyStatus(BaseModel):
    """策略状态"""
    strategy_id: str
    name: str
    type: str
    status: str  # active, paused, stopped, error
    created_at: datetime
    last_updated: datetime
    total_pnl: float
    daily_pnl: float
    current_positions: List[Dict[str, Any]]

class StrategyPerformance(BaseModel):
    """策略表现指标"""
    strategy_id: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    avg_trade_duration: float
    performance_history: List[Dict[str, Any]]

# ===============================
# 策略管理器
# ===============================

class StrategyManager:
    """策略管理器"""
    
    def __init__(self, config_manager: UnifiedConfigManager):
        self.config_manager = config_manager
        self.strategies: Dict[str, Dict] = {}
        self.logger = structlog.get_logger(__name__)
        
    async def create_grid_strategy(self, config: GridStrategyConfig) -> str:
        """创建网格策略"""
        strategy_id = f"grid_{int(datetime.now().timestamp())}"
        
        strategy_data = {
            "id": strategy_id,
            "type": "grid",
            "config": config.model_dump(),
            "status": "active",
            "created_at": datetime.now(timezone.utc),
            "last_updated": datetime.now(timezone.utc),
            "performance": {
                "total_pnl": 0.0,
                "daily_pnl": 0.0,
                "total_trades": 0,
                "win_rate": 0.0
            }
        }
        
        self.strategies[strategy_id] = strategy_data
        
        self.logger.info("网格策略创建成功", 
                        strategy_id=strategy_id, 
                        symbol=config.symbol,
                        grid_count=config.grid_count)
        
        return strategy_id
    
    async def create_signal_strategy(self, config: SignalStrategyConfig) -> str:
        """创建信号交易策略"""
        strategy_id = f"signal_{int(datetime.now().timestamp())}"
        
        strategy_data = {
            "id": strategy_id,
            "type": "signal",
            "config": config.model_dump(),
            "status": "active",
            "created_at": datetime.now(timezone.utc),
            "last_updated": datetime.now(timezone.utc),
            "performance": {
                "total_pnl": 0.0,
                "daily_pnl": 0.0,
                "total_trades": 0,
                "win_rate": 0.0
            }
        }
        
        self.strategies[strategy_id] = strategy_data
        
        self.logger.info("信号交易策略创建成功", 
                        strategy_id=strategy_id, 
                        symbol=config.symbol,
                        signal_source=config.signal_source)
        
        return strategy_id
    
    async def create_dca_strategy(self, config: DCAStrategyConfig) -> str:
        """创建定投策略"""
        strategy_id = f"dca_{int(datetime.now().timestamp())}"
        
        strategy_data = {
            "id": strategy_id,
            "type": "dca",
            "config": config.model_dump(),
            "status": "active",
            "created_at": datetime.now(timezone.utc),
            "last_updated": datetime.now(timezone.utc),
            "performance": {
                "total_pnl": 0.0,
                "daily_pnl": 0.0,
                "total_trades": 0,
                "win_rate": 0.0
            }
        }
        
        self.strategies[strategy_id] = strategy_data
        
        self.logger.info("定投策略创建成功", 
                        strategy_id=strategy_id, 
                        symbols=config.symbols,
                        interval=config.interval)
        
        return strategy_id
    
    async def get_strategy_status(self, strategy_id: str) -> Optional[StrategyStatus]:
        """获取策略状态"""
        if strategy_id not in self.strategies:
            return None
        
        strategy = self.strategies[strategy_id]
        
        return StrategyStatus(
            strategy_id=strategy["id"],
            name=strategy["config"]["name"],
            type=strategy["type"],
            status=strategy["status"],
            created_at=strategy["created_at"],
            last_updated=strategy["last_updated"],
            total_pnl=strategy["performance"]["total_pnl"],
            daily_pnl=strategy["performance"]["daily_pnl"],
            current_positions=[]  # TODO: 实现持仓查询
        )
    
    async def get_all_strategies(self) -> List[StrategyStatus]:
        """获取所有策略状态"""
        strategies = []
        for strategy_id in self.strategies:
            status = await self.get_strategy_status(strategy_id)
            if status:
                strategies.append(status)
        return strategies
    
    async def pause_strategy(self, strategy_id: str) -> bool:
        """暂停策略"""
        if strategy_id not in self.strategies:
            return False
        
        self.strategies[strategy_id]["status"] = "paused"
        self.strategies[strategy_id]["last_updated"] = datetime.now(timezone.utc)
        
        self.logger.info("策略已暂停", strategy_id=strategy_id)
        return True
    
    async def resume_strategy(self, strategy_id: str) -> bool:
        """恢复策略"""
        if strategy_id not in self.strategies:
            return False
        
        self.strategies[strategy_id]["status"] = "active"
        self.strategies[strategy_id]["last_updated"] = datetime.now(timezone.utc)
        
        self.logger.info("策略已恢复", strategy_id=strategy_id)
        return True
    
    async def stop_strategy(self, strategy_id: str) -> bool:
        """停止策略"""
        if strategy_id not in self.strategies:
            return False
        
        self.strategies[strategy_id]["status"] = "stopped"
        self.strategies[strategy_id]["last_updated"] = datetime.now(timezone.utc)
        
        self.logger.info("策略已停止", strategy_id=strategy_id)
        return True

# ===============================
# FastAPI 应用
# ===============================

class StrategyManagementService:
    """策略管理服务"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.app = FastAPI(
            title="MarketPrism 策略管理服务",
            description="量化交易策略管理API",
            version="1.0.0"
        )
        
        # 配置CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # 初始化配置管理器
        self.config_manager = UnifiedConfigManager(
            config_dir=project_root / "config",
            enable_env_override=True,
            enable_hot_reload=True
        )
        self.config_manager.initialize()
        
        # 初始化策略管理器
        self.strategy_manager = StrategyManager(self.config_manager)
        
        self.logger = structlog.get_logger(__name__)
        self._setup_routes()
    
    def _setup_routes(self):
        """设置API路由"""
        
        @self.app.get("/health")
        async def health_check():
            """健康检查"""
            return {
                "status": "healthy",
                "service": "strategy-management",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "active_strategies": len(self.strategy_manager.strategies)
            }
        
        @self.app.post("/api/v1/strategies/grid")
        async def create_grid_strategy(config: GridStrategyConfig):
            """创建网格策略"""
            try:
                strategy_id = await self.strategy_manager.create_grid_strategy(config)
                return {
                    "strategy_id": strategy_id,
                    "status": "created",
                    "message": f"网格策略 {config.name} 创建成功"
                }
            except Exception as e:
                self.logger.error("创建网格策略失败", error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/v1/strategies/signal")
        async def create_signal_strategy(config: SignalStrategyConfig):
            """创建信号交易策略"""
            try:
                strategy_id = await self.strategy_manager.create_signal_strategy(config)
                return {
                    "strategy_id": strategy_id,
                    "status": "created",
                    "message": f"信号交易策略 {config.name} 创建成功"
                }
            except Exception as e:
                self.logger.error("创建信号交易策略失败", error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/v1/strategies/dca")
        async def create_dca_strategy(config: DCAStrategyConfig):
            """创建定投策略"""
            try:
                strategy_id = await self.strategy_manager.create_dca_strategy(config)
                return {
                    "strategy_id": strategy_id,
                    "status": "created",
                    "message": f"定投策略 {config.name} 创建成功"
                }
            except Exception as e:
                self.logger.error("创建定投策略失败", error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/v1/strategies")
        async def list_strategies():
            """获取所有策略列表"""
            try:
                strategies = await self.strategy_manager.get_all_strategies()
                return {
                    "strategies": [strategy.model_dump() for strategy in strategies],
                    "total": len(strategies)
                }
            except Exception as e:
                self.logger.error("获取策略列表失败", error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/v1/strategies/{strategy_id}")
        async def get_strategy_status(strategy_id: str):
            """获取策略状态"""
            try:
                status = await self.strategy_manager.get_strategy_status(strategy_id)
                if not status:
                    raise HTTPException(status_code=404, detail="策略不存在")
                
                return status.model_dump()
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error("获取策略状态失败", strategy_id=strategy_id, error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/v1/strategies/{strategy_id}/pause")
        async def pause_strategy(strategy_id: str):
            """暂停策略"""
            try:
                success = await self.strategy_manager.pause_strategy(strategy_id)
                if not success:
                    raise HTTPException(status_code=404, detail="策略不存在")
                
                return {"message": "策略已暂停", "strategy_id": strategy_id}
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error("暂停策略失败", strategy_id=strategy_id, error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/v1/strategies/{strategy_id}/resume")
        async def resume_strategy(strategy_id: str):
            """恢复策略"""
            try:
                success = await self.strategy_manager.resume_strategy(strategy_id)
                if not success:
                    raise HTTPException(status_code=404, detail="策略不存在")
                
                return {"message": "策略已恢复", "strategy_id": strategy_id}
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error("恢复策略失败", strategy_id=strategy_id, error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/v1/strategies/{strategy_id}/stop")
        async def stop_strategy(strategy_id: str):
            """停止策略"""
            try:
                success = await self.strategy_manager.stop_strategy(strategy_id)
                if not success:
                    raise HTTPException(status_code=404, detail="策略不存在")
                
                return {"message": "策略已停止", "strategy_id": strategy_id}
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error("停止策略失败", strategy_id=strategy_id, error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/v1/strategies/{strategy_id}/performance")
        async def get_strategy_performance(strategy_id: str):
            """获取策略表现"""
            try:
                if strategy_id not in self.strategy_manager.strategies:
                    raise HTTPException(status_code=404, detail="策略不存在")
                
                # TODO: 实现真实的表现分析
                mock_performance = {
                    "strategy_id": strategy_id,
                    "total_return": 12.5,
                    "sharpe_ratio": 1.85,
                    "max_drawdown": 8.3,
                    "win_rate": 68.5,
                    "total_trades": 145,
                    "avg_trade_duration": 2.5,
                    "performance_history": [
                        {"date": "2025-06-14", "pnl": 1.2, "cumulative_return": 12.5},
                        {"date": "2025-06-13", "pnl": -0.3, "cumulative_return": 11.1},
                        {"date": "2025-06-12", "pnl": 2.1, "cumulative_return": 11.4}
                    ]
                }
                
                return mock_performance
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error("获取策略表现失败", strategy_id=strategy_id, error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
    
    async def run(self):
        """运行服务"""
        host = self.config.get('host', '0.0.0.0')
        port = self.config.get('port', 8087)
        
        self.logger.info("策略管理服务启动", host=host, port=port)
        
        config = uvicorn.Config(
            self.app,
            host=host,
            port=port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()

# ===============================
# 主程序
# ===============================

async def main():
    """主程序入口"""
    try:
        # 加载配置
        config_manager = UnifiedConfigManager(
            config_dir=project_root / "config",
            enable_env_override=True,
            enable_hot_reload=True
        )
        config_manager.initialize()
        
        # 获取服务配置
        services_config = config_manager.get_config("services")
        if services_config:
            service_config = services_config.to_dict().get("strategy-management", {
                "host": "0.0.0.0",
                "port": 8087
            })
        else:
            service_config = {
                "host": "0.0.0.0",
                "port": 8087
            }
        
        # 创建并运行服务
        service = StrategyManagementService(service_config)
        await service.run()
        
    except Exception as e:
        logger.error("策略管理服务启动失败", error=str(e))
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())