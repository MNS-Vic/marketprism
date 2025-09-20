#!/usr/bin/env python3
"""
MarketPrism 监控指标收集和告警脚本
定期检查关键指标并在异常时发送告警
"""

import asyncio
import aiohttp
import nats
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

class MarketPrismMonitor:
    """MarketPrism 系统监控器"""
    
    def __init__(self):
        self.nats_url = "nats://localhost:4222"
        self.storage_metrics_url = "http://localhost:8081/metrics"
        self.clickhouse_url = "http://localhost:8123"
        
        # 告警阈值配置
        self.thresholds = {
            "max_pending_messages": 10000,
            "max_error_rate": 5.0,
            "min_batch_inserts_per_minute": 1,
            "max_batch_processing_delay": 300,  # 5分钟
            "max_ack_pending": 1000,
        }
        
        # 历史数据存储
        self.metrics_history = []
        self.last_alert_time = {}
        
    async def collect_jetstream_metrics(self) -> Dict:
        """收集 JetStream 消费者指标"""
        try:
            nc = await nats.connect(self.nats_url)
            js = nc.jetstream()
            
            consumers = [
                "simple_hot_storage_realtime_trade",
                "simple_hot_storage_realtime_orderbook", 
                "simple_hot_storage_realtime_liquidation"
            ]
            
            metrics = {}
            total_pending = 0
            total_ack_pending = 0
            total_redelivered = 0
            
            for consumer in consumers:
                try:
                    info = await js.consumer_info("MARKET_DATA", consumer)
                    consumer_metrics = {
                        "num_pending": info.num_pending,
                        "num_ack_pending": info.num_ack_pending,
                        "num_redelivered": info.num_redelivered,
                        "deliver_policy": str(info.config.deliver_policy),
                    }
                    metrics[consumer] = consumer_metrics
                    
                    total_pending += info.num_pending
                    total_ack_pending += info.num_ack_pending
                    total_redelivered += info.num_redelivered
                    
                except Exception as e:
                    metrics[consumer] = {"error": str(e)}
            
            metrics["totals"] = {
                "total_pending": total_pending,
                "total_ack_pending": total_ack_pending,
                "total_redelivered": total_redelivered,
            }
            
            await nc.close()
            return metrics
            
        except Exception as e:
            return {"error": f"JetStream 连接失败: {e}"}
    
    async def collect_storage_metrics(self) -> Dict:
        """收集存储服务指标"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.storage_metrics_url, timeout=10) as resp:
                    if resp.status == 200:
                        content = await resp.text()
                        metrics = {}
                        
                        for line in content.split('\n'):
                            if line and not line.startswith('#'):
                                parts = line.split()
                                if len(parts) >= 2:
                                    key = parts[0]
                                    value = parts[1]
                                    try:
                                        metrics[key] = float(value)
                                    except ValueError:
                                        metrics[key] = value
                        
                        return metrics
                    else:
                        return {"error": f"HTTP {resp.status}"}
                        
        except Exception as e:
            return {"error": f"存储服务连接失败: {e}"}
    
    async def collect_clickhouse_metrics(self) -> Dict:
        """收集 ClickHouse 指标"""
        try:
            async with aiohttp.ClientSession() as session:
                queries = {
                    "total_trades": "SELECT count() FROM marketprism_hot.trades",
                    "recent_trades": "SELECT count() FROM marketprism_hot.trades WHERE timestamp > now() - INTERVAL 5 MINUTE",
                    "total_orderbooks": "SELECT count() FROM marketprism_hot.orderbooks",
                    "recent_orderbooks": "SELECT count() FROM marketprism_hot.orderbooks WHERE timestamp > now() - INTERVAL 5 MINUTE",
                }
                
                metrics = {}
                for name, query in queries.items():
                    try:
                        async with session.get(f"{self.clickhouse_url}/?query={query}", timeout=10) as resp:
                            if resp.status == 200:
                                result = await resp.text()
                                metrics[name] = int(result.strip())
                            else:
                                metrics[name] = -1
                    except Exception as e:
                        metrics[name] = -1
                        metrics[f"{name}_error"] = str(e)
                
                return metrics
                
        except Exception as e:
            return {"error": f"ClickHouse 连接失败: {e}"}
    
    def check_alerts(self, all_metrics: Dict) -> List[Dict]:
        """检查告警条件"""
        alerts = []
        current_time = datetime.now()
        
        # 检查消息积压
        js_metrics = all_metrics.get("jetstream", {})
        total_pending = js_metrics.get("totals", {}).get("total_pending", 0)
        if total_pending > self.thresholds["max_pending_messages"]:
            alerts.append({
                "type": "high_pending_messages",
                "severity": "warning",
                "message": f"消息积压过多: {total_pending}",
                "value": total_pending,
                "threshold": self.thresholds["max_pending_messages"]
            })
        
        # 检查批量处理停滞
        storage_metrics = all_metrics.get("storage", {})
        batch_inserts = storage_metrics.get("hot_storage_batch_inserts_total", 0)
        
        # 检查是否有历史数据对比
        if len(self.metrics_history) > 0:
            last_batch_inserts = self.metrics_history[-1].get("storage", {}).get("hot_storage_batch_inserts_total", 0)
            if batch_inserts == last_batch_inserts:
                alerts.append({
                    "type": "batch_processing_stopped",
                    "severity": "critical",
                    "message": "批量处理可能已停止",
                    "value": batch_inserts,
                    "last_value": last_batch_inserts
                })
        
        # 检查错误率
        error_rate = storage_metrics.get("hot_storage_error_rate_percent", 0)
        if error_rate > self.thresholds["max_error_rate"]:
            alerts.append({
                "type": "high_error_rate", 
                "severity": "warning",
                "message": f"错误率过高: {error_rate}%",
                "value": error_rate,
                "threshold": self.thresholds["max_error_rate"]
            })
        
        return alerts
    
    def should_send_alert(self, alert_type: str) -> bool:
        """检查是否应该发送告警（避免重复告警）"""
        last_time = self.last_alert_time.get(alert_type)
        if last_time is None:
            return True
        
        # 5分钟内不重复发送同类型告警
        return (datetime.now() - last_time).total_seconds() > 300
    
    async def send_alert(self, alert: Dict):
        """发送告警（这里只是打印，实际可以集成钉钉/邮件等）"""
        if self.should_send_alert(alert["type"]):
            print(f"🚨 告警: {alert['message']}")
            print(f"   类型: {alert['type']}")
            print(f"   严重程度: {alert['severity']}")
            print(f"   时间: {datetime.now().isoformat()}")
            
            self.last_alert_time[alert["type"]] = datetime.now()
    
    async def run_monitoring_cycle(self):
        """运行一次监控周期"""
        print(f"📊 开始监控周期 @ {datetime.now().isoformat()}")
        
        # 收集所有指标
        all_metrics = {
            "timestamp": datetime.now().isoformat(),
            "jetstream": await self.collect_jetstream_metrics(),
            "storage": await self.collect_storage_metrics(),
            "clickhouse": await self.collect_clickhouse_metrics(),
        }
        
        # 存储历史数据
        self.metrics_history.append(all_metrics)
        if len(self.metrics_history) > 100:  # 只保留最近100次记录
            self.metrics_history.pop(0)
        
        # 检查告警
        alerts = self.check_alerts(all_metrics)
        
        # 发送告警
        for alert in alerts:
            await self.send_alert(alert)
        
        # 打印关键指标
        js_totals = all_metrics["jetstream"].get("totals", {})
        storage_batch = all_metrics["storage"].get("hot_storage_batch_inserts_total", 0)
        ch_recent = all_metrics["clickhouse"].get("recent_trades", 0)
        
        print(f"   消息积压: {js_totals.get('total_pending', 'N/A')}")
        print(f"   批量插入: {storage_batch}")
        print(f"   最近写入: {ch_recent}")
        print(f"   告警数量: {len(alerts)}")
        
        return all_metrics

async def main():
    """主监控循环"""
    monitor = MarketPrismMonitor()
    
    print("🚀 启动 MarketPrism 监控系统")
    print("按 Ctrl+C 停止监控")
    
    try:
        while True:
            await monitor.run_monitoring_cycle()
            await asyncio.sleep(30)  # 每30秒监控一次
            
    except KeyboardInterrupt:
        print("\n👋 监控系统已停止")

if __name__ == "__main__":
    asyncio.run(main())
