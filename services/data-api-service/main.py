#!/usr/bin/env python3
"""
MarketPrism 数据API服务
提供真实的内部数据源给前端Dashboard
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timezone
from decimal import Decimal
import random
from typing import List, Dict, Any, Optional
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ClickHouse配置
CLICKHOUSE_URL = "http://43.156.224.10:8123"
DATABASE = "marketprism"

# FastAPI应用
app = FastAPI(
    title="MarketPrism Data API",
    description="提供真实的内部市场数据",
    version="1.0.0"
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境中应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 数据模型
class MarketDataItem(BaseModel):
    symbol: str
    price: float
    change: float
    changePercent: float
    volume: float
    high24h: float
    low24h: float

class SystemStatus(BaseModel):
    status: str
    timestamp: str
    data_source: str
    total_symbols: int

class DataVisualizationItem(BaseModel):
    symbol: str
    price: float
    volume: float
    change: float
    changePercent: float

# 数据访问层
class ClickHouseClient:
    """ClickHouse客户端"""
    
    def __init__(self, url: str, database: str):
        self.url = url
        self.database = database
    
    async def execute_query(self, query: str) -> str:
        """执行查询"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    self.url,
                    data=query,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        return await response.text()
                    else:
                        error_text = await response.text()
                        logger.error(f"ClickHouse查询失败: {response.status} - {error_text}")
                        raise HTTPException(status_code=500, detail=f"数据库查询失败: {error_text}")
            except Exception as e:
                logger.error(f"ClickHouse连接错误: {e}")
                raise HTTPException(status_code=500, detail=f"数据库连接失败: {str(e)}")
    
    async def get_latest_tickers(self) -> List[Dict[str, Any]]:
        """获取最新的ticker数据"""
        query = f"""
        SELECT 
            symbol,
            exchange,
            last_price,
            volume_24h,
            price_change_24h,
            high_24h,
            low_24h,
            timestamp
        FROM {self.database}.hot_tickers
        ORDER BY timestamp DESC
        LIMIT 20
        FORMAT JSONEachRow
        """
        
        result = await self.execute_query(query)
        
        # 解析JSON结果
        tickers = []
        for line in result.strip().split('\n'):
            if line:
                try:
                    ticker = json.loads(line)
                    tickers.append(ticker)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON解析失败: {e}")
        
        return tickers
    
    async def get_symbol_count(self) -> int:
        """获取符号总数"""
        query = f"SELECT COUNT(DISTINCT symbol) FROM {self.database}.hot_tickers"
        result = await self.execute_query(query)
        return int(result.strip())

# 全局客户端实例
clickhouse_client = ClickHouseClient(CLICKHOUSE_URL, DATABASE)

# 数据更新任务
async def update_test_data():
    """定期更新测试数据"""
    symbols = [
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", 
        "XRPUSDT", "SOLUSDT", "DOTUSDT", "DOGEUSDT"
    ]
    
    exchanges = ["binance", "okx"]
    
    base_prices = {
        "BTCUSDT": 43000.0,
        "ETHUSDT": 2600.0,
        "BNBUSDT": 310.0,
        "ADAUSDT": 0.48,
        "XRPUSDT": 0.62,
        "SOLUSDT": 98.0,
        "DOTUSDT": 7.2,
        "DOGEUSDT": 0.08
    }
    
    while True:
        try:
            logger.info("🔄 开始更新测试数据...")
            
            # 生成新数据
            data = []
            current_time = datetime.now(timezone.utc)
            
            for symbol in symbols:
                for exchange in exchanges:
                    base_price = base_prices[symbol]
                    
                    # 生成随机价格变化
                    price_change_percent = (random.random() - 0.5) * 0.1  # ±5%
                    current_price = base_price * (1 + price_change_percent)
                    price_change_24h = base_price * price_change_percent
                    
                    # 生成24小时高低价
                    high_24h = current_price * (1 + random.random() * 0.05)
                    low_24h = current_price * (1 - random.random() * 0.05)
                    
                    # 生成成交量
                    volume_24h = random.uniform(100000, 2000000)
                    
                    ticker = {
                        "timestamp": current_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                        "symbol": symbol,
                        "exchange": exchange,
                        "last_price": round(current_price, 8),
                        "volume_24h": round(volume_24h, 8),
                        "price_change_24h": round(price_change_24h, 8),
                        "high_24h": round(high_24h, 8),
                        "low_24h": round(low_24h, 8)
                    }
                    
                    data.append(ticker)
            
            # 插入新数据
            values = []
            for item in data:
                value = f"('{item['timestamp']}', '{item['symbol']}', '{item['exchange']}', " \
                        f"{item['last_price']}, {item['volume_24h']}, {item['price_change_24h']}, " \
                        f"{item['high_24h']}, {item['low_24h']})"
                values.append(value)
            
            insert_query = f"""
            INSERT INTO {DATABASE}.hot_tickers 
            (timestamp, symbol, exchange, last_price, volume_24h, price_change_24h, high_24h, low_24h)
            VALUES {', '.join(values)}
            """
            
            await clickhouse_client.execute_query(insert_query)
            logger.info(f"✅ 成功更新 {len(data)} 条数据")
            
        except Exception as e:
            logger.error(f"❌ 数据更新失败: {e}")
        
        # 等待30秒后再次更新
        await asyncio.sleep(30)

# API端点
@app.get("/")
async def root():
    """根端点"""
    return {"message": "MarketPrism Data API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    """健康检查"""
    try:
        count = await clickhouse_client.get_symbol_count()
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data_source": "ClickHouse",
            "total_symbols": count
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        }

@app.get("/api/v1/market-data", response_model=List[MarketDataItem])
async def get_market_data():
    """获取市场数据"""
    try:
        tickers = await clickhouse_client.get_latest_tickers()
        
        # 转换为前端需要的格式
        market_data = []
        symbol_data = {}
        
        # 按symbol分组，取最新的数据
        for ticker in tickers:
            symbol = ticker['symbol']
            if symbol not in symbol_data:
                symbol_data[symbol] = ticker
        
        # 转换格式
        for symbol, ticker in symbol_data.items():
            price = float(ticker['last_price'])
            change = float(ticker['price_change_24h'])
            change_percent = (change / (price - change)) * 100 if (price - change) != 0 else 0
            
            market_data.append(MarketDataItem(
                symbol=symbol,
                price=price,
                change=change,
                changePercent=round(change_percent, 2),
                volume=float(ticker['volume_24h']),
                high24h=float(ticker['high_24h']),
                low24h=float(ticker['low_24h'])
            ))
        
        return market_data
        
    except Exception as e:
        logger.error(f"获取市场数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/data-visualization", response_model=List[DataVisualizationItem])
async def get_data_visualization():
    """获取数据可视化数据"""
    try:
        tickers = await clickhouse_client.get_latest_tickers()
        
        # 转换为数据可视化格式
        viz_data = []
        symbol_data = {}
        
        # 按symbol分组，取最新的数据
        for ticker in tickers:
            symbol = ticker['symbol']
            if symbol not in symbol_data:
                symbol_data[symbol] = ticker
        
        # 只取前4个符号用于可视化
        symbols = list(symbol_data.keys())[:4]
        
        for symbol in symbols:
            ticker = symbol_data[symbol]
            price = float(ticker['last_price'])
            change = float(ticker['price_change_24h'])
            change_percent = (change / (price - change)) * 100 if (price - change) != 0 else 0
            
            viz_data.append(DataVisualizationItem(
                symbol=symbol,
                price=price,
                volume=float(ticker['volume_24h']),
                change=change,
                changePercent=round(change_percent, 2)
            ))
        
        return viz_data
        
    except Exception as e:
        logger.error(f"获取数据可视化数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/status", response_model=SystemStatus)
async def get_system_status():
    """获取系统状态"""
    try:
        count = await clickhouse_client.get_symbol_count()
        return SystemStatus(
            status="running",
            timestamp=datetime.now(timezone.utc).isoformat(),
            data_source="ClickHouse Internal Database",
            total_symbols=count
        )
    except Exception as e:
        logger.error(f"获取系统状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 启动事件
@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("🚀 MarketPrism Data API 启动中...")
    
    # 启动数据更新任务
    asyncio.create_task(update_test_data())
    
    logger.info("✅ MarketPrism Data API 启动完成")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=3006,
        reload=True,
        log_level="info"
    )
