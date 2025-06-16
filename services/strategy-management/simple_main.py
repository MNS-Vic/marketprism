#!/usr/bin/env python3
"""
MarketPrism 简化策略管理服务
专注于现有服务支持，不扩展复杂策略功能
"""

import asyncio
import sys
import os
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===============================
# 简化数据模型
# ===============================

class StrategyConfig(BaseModel):
    """通用策略配置"""
    name: str = Field(..., description="策略名称")
    symbol: str = Field(..., description="交易对")
    exchange: str = Field("binance", description="交易所")
    strategy_type: str = Field(..., description="策略类型")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="策略参数")

class StrategyStatus(BaseModel):
    """策略状态"""
    strategy_id: str
    name: str
    type: str
    status: str
    created_at: datetime
    last_updated: datetime

# ===============================
# 简化策略管理器
# ===============================

class SimpleStrategyManager:
    """简化策略管理器"""
    
    def __init__(self):
        self.strategies: Dict[str, Dict] = {}
        
    async def create_strategy(self, config: StrategyConfig) -> str:
        """创建策略"""
        strategy_id = f"{config.strategy_type}_{int(datetime.now().timestamp())}"
        
        strategy_data = {
            "id": strategy_id,
            "type": config.strategy_type,
            "config": config.model_dump(),
            "status": "active",
            "created_at": datetime.now(timezone.utc),
            "last_updated": datetime.now(timezone.utc)
        }
        
        self.strategies[strategy_id] = strategy_data
        logger.info(f"策略创建成功: {strategy_id}")
        
        return strategy_id
    
    async def get_all_strategies(self) -> List[StrategyStatus]:
        """获取所有策略"""
        strategies = []
        for strategy_id, strategy_data in self.strategies.items():
            status = StrategyStatus(
                strategy_id=strategy_data["id"],
                name=strategy_data["config"]["name"],
                type=strategy_data["type"],
                status=strategy_data["status"],
                created_at=strategy_data["created_at"],
                last_updated=strategy_data["last_updated"]
            )
            strategies.append(status)
        return strategies

# ===============================
# FastAPI 应用
# ===============================

app = FastAPI(
    title="MarketPrism 简化策略管理服务",
    description="专注于现有服务支持的策略管理API",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化策略管理器
strategy_manager = SimpleStrategyManager()

@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "service": "strategy-management",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "active_strategies": len(strategy_manager.strategies)
    }

@app.post("/api/v1/strategies/grid")
async def create_grid_strategy(config: StrategyConfig):
    """创建网格策略"""
    try:
        config.strategy_type = "grid"
        strategy_id = await strategy_manager.create_strategy(config)
        return {
            "strategy_id": strategy_id,
            "status": "created",
            "message": f"网格策略 {config.name} 创建成功"
        }
    except Exception as e:
        logger.error(f"创建网格策略失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/strategies/signal")
async def create_signal_strategy(config: StrategyConfig):
    """创建信号交易策略"""
    try:
        config.strategy_type = "signal"
        strategy_id = await strategy_manager.create_strategy(config)
        return {
            "strategy_id": strategy_id,
            "status": "created",
            "message": f"信号交易策略 {config.name} 创建成功"
        }
    except Exception as e:
        logger.error(f"创建信号交易策略失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/strategies/dca")
async def create_dca_strategy(config: StrategyConfig):
    """创建定投策略"""
    try:
        config.strategy_type = "dca"
        strategy_id = await strategy_manager.create_strategy(config)
        return {
            "strategy_id": strategy_id,
            "status": "created",
            "message": f"定投策略 {config.name} 创建成功"
        }
    except Exception as e:
        logger.error(f"创建定投策略失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/strategies")
async def list_strategies():
    """获取所有策略列表"""
    try:
        strategies = await strategy_manager.get_all_strategies()
        return {
            "strategies": [strategy.dict() for strategy in strategies],
            "total": len(strategies)
        }
    except Exception as e:
        logger.error(f"获取策略列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/dashboard/overview")
async def get_dashboard_overview():
    """获取仪表板概览 - 为Grafana集成提供数据"""
    try:
        strategies = await strategy_manager.get_all_strategies()
        
        # 统计数据
        total_strategies = len(strategies)
        active_strategies = len([s for s in strategies if s.status == "active"])
        
        # 模拟性能数据
        overview = {
            "total_strategies": total_strategies,
            "active_strategies": active_strategies,
            "paused_strategies": total_strategies - active_strategies,
            "total_pnl": 1250.75,  # 模拟数据
            "daily_pnl": 45.20,    # 模拟数据
            "win_rate": 68.5,      # 模拟数据
            "strategies_by_type": {
                "grid": len([s for s in strategies if s.type == "grid"]),
                "signal": len([s for s in strategies if s.type == "signal"]),
                "dca": len([s for s in strategies if s.type == "dca"])
            },
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        
        return overview
    except Exception as e:
        logger.error(f"获取仪表板概览失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8087)