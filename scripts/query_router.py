#!/usr/bin/env python3
"""
MarketPrism 智能查询路由器
自动将查询路由到合适的存储层（热存储/冷存储）
"""

import subprocess
import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union

class QueryRouter:
    """智能查询路由器"""
    
    def __init__(self, hot_retention_days: int = 7):
        """初始化路由器
        
        Args:
            hot_retention_days: 热存储保留天数
        """
        self.hot_retention_days = hot_retention_days
        self.hot_container = "marketprism-clickhouse-1"
        self.cold_container = "marketprism-clickhouse-cold"
        self.hot_database = "marketprism"
        self.cold_database = "marketprism_cold"
    
    def execute_hot_query(self, query: str) -> Optional[str]:
        """执行热存储查询"""
        cmd = [
            "docker", "exec", self.hot_container,
            "clickhouse-client", 
            "--database", self.hot_database,
            "--query", query
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"❌ 热存储查询失败: {e}")
            return None
    
    def execute_cold_query(self, query: str) -> Optional[str]:
        """执行冷存储查询"""
        cmd = [
            "docker", "exec", self.cold_container,
            "clickhouse-client", 
            "--database", self.cold_database,
            "--query", query
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"❌ 冷存储查询失败: {e}")
            return None
    
    def analyze_time_range(self, query: str) -> Dict[str, Any]:
        """分析查询中的时间范围"""
        analysis = {
            "has_time_filter": False,
            "needs_hot": False,
            "needs_cold": False,
            "time_conditions": []
        }
        
        # 查找时间相关的条件
        time_patterns = [
            r"timestamp\s*>=?\s*'([^']+)'",
            r"timestamp\s*<=?\s*'([^']+)'",
            r"timestamp\s*BETWEEN\s*'([^']+)'\s*AND\s*'([^']+)'",
            r"toDate\(timestamp\)\s*>=?\s*'([^']+)'",
            r"toDate\(timestamp\)\s*<=?\s*'([^']+)'",
            r"timestamp\s*>=?\s*now\(\)\s*-\s*INTERVAL\s*(\d+)\s*DAY",
            r"timestamp\s*<=?\s*now\(\)\s*-\s*INTERVAL\s*(\d+)\s*DAY"
        ]
        
        cutoff_date = datetime.now() - timedelta(days=self.hot_retention_days)
        
        for pattern in time_patterns:
            matches = re.finditer(pattern, query, re.IGNORECASE)
            for match in matches:
                analysis["has_time_filter"] = True
                analysis["time_conditions"].append(match.group(0))
                
                if "INTERVAL" in match.group(0):
                    # 处理相对时间
                    interval_match = re.search(r'(\d+)\s*DAY', match.group(0))
                    if interval_match:
                        days = int(interval_match.group(1))
                        if days <= self.hot_retention_days:
                            analysis["needs_hot"] = True
                        else:
                            analysis["needs_cold"] = True
                else:
                    # 处理绝对时间
                    try:
                        date_str = match.group(1)
                        query_date = datetime.strptime(date_str[:19], '%Y-%m-%d %H:%M:%S')
                        
                        if query_date >= cutoff_date:
                            analysis["needs_hot"] = True
                        else:
                            analysis["needs_cold"] = True
                    except (ValueError, IndexError):
                        # 如果无法解析时间，默认查询两个存储
                        analysis["needs_hot"] = True
                        analysis["needs_cold"] = True
        
        # 如果没有时间过滤条件，默认查询两个存储
        if not analysis["has_time_filter"]:
            analysis["needs_hot"] = True
            analysis["needs_cold"] = True
        
        return analysis
    
    def route_query(self, query: str, format_output: str = "pretty") -> Dict[str, Any]:
        """智能路由查询"""
        print(f"🔍 分析查询: {query[:100]}...")
        
        analysis = self.analyze_time_range(query)
        result = {
            "query": query,
            "analysis": analysis,
            "hot_result": None,
            "cold_result": None,
            "combined_result": None,
            "execution_plan": []
        }
        
        # 根据分析结果执行查询
        if analysis["needs_hot"]:
            print("📊 执行热存储查询...")
            result["execution_plan"].append("hot_storage")
            hot_query = query.replace("market_data", "market_data")  # 热存储表名
            result["hot_result"] = self.execute_hot_query(hot_query)
        
        if analysis["needs_cold"]:
            print("❄️ 执行冷存储查询...")
            result["execution_plan"].append("cold_storage")
            cold_query = query.replace("market_data", "market_data")  # 冷存储表名
            result["cold_result"] = self.execute_cold_query(cold_query)
        
        # 合并结果（如果需要）
        if result["hot_result"] and result["cold_result"]:
            print("🔄 合并查询结果...")
            result["combined_result"] = self.combine_results(
                query, result["hot_result"], result["cold_result"]
            )
        elif result["hot_result"]:
            result["combined_result"] = result["hot_result"]
        elif result["cold_result"]:
            result["combined_result"] = result["cold_result"]
        
        return result
    
    def combine_results(self, query: str, hot_result: str, cold_result: str) -> str:
        """合并热存储和冷存储的查询结果"""
        # 简单的合并策略：如果是计数查询，求和；如果是数据查询，合并
        
        if "count()" in query.lower():
            # 计数查询：求和
            try:
                hot_count = int(hot_result) if hot_result.isdigit() else 0
                cold_count = int(cold_result) if cold_result.isdigit() else 0
                return str(hot_count + cold_count)
            except ValueError:
                return f"Hot: {hot_result}, Cold: {cold_result}"
        
        elif "select" in query.lower() and "group by" in query.lower():
            # 聚合查询：需要重新聚合
            return f"=== 热存储结果 ===\n{hot_result}\n\n=== 冷存储结果 ===\n{cold_result}"
        
        else:
            # 普通查询：简单合并
            combined = []
            if cold_result and cold_result.strip():
                combined.append(cold_result)
            if hot_result and hot_result.strip():
                combined.append(hot_result)
            return "\n".join(combined)
    
    def query_market_data(
        self, 
        exchanges: Optional[List[str]] = None,
        symbols: Optional[List[str]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """便捷的市场数据查询接口"""
        
        # 构建查询条件
        conditions = []
        
        if exchanges:
            exchange_list = "', '".join(exchanges)
            conditions.append(f"exchange IN ('{exchange_list}')")
        
        if symbols:
            symbol_list = "', '".join(symbols)
            conditions.append(f"symbol IN ('{symbol_list}')")
        
        if start_time:
            conditions.append(f"timestamp >= '{start_time}'")
        
        if end_time:
            conditions.append(f"timestamp <= '{end_time}'")
        
        # 构建完整查询
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        limit_clause = f" LIMIT {limit}" if limit else ""
        
        query = f"""
            SELECT timestamp, exchange, symbol, data_type, price, volume
            FROM market_data 
            WHERE {where_clause}
            ORDER BY timestamp DESC
            {limit_clause}
        """
        
        return self.route_query(query.strip())
    
    def get_storage_statistics(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        print("📊 获取存储统计信息...")
        
        stats = {
            "hot_storage": {},
            "cold_storage": {},
            "total": {}
        }
        
        # 热存储统计
        hot_count = self.execute_hot_query("SELECT count() FROM market_data")
        hot_size = self.execute_hot_query("""
            SELECT formatReadableSize(sum(bytes)) 
            FROM system.parts 
            WHERE database = 'marketprism' AND table = 'market_data'
        """)
        hot_latest = self.execute_hot_query("SELECT max(timestamp) FROM market_data")
        
        stats["hot_storage"] = {
            "record_count": int(hot_count) if hot_count and hot_count.isdigit() else 0,
            "storage_size": hot_size or "0 B",
            "latest_timestamp": hot_latest or "N/A"
        }
        
        # 冷存储统计
        cold_count = self.execute_cold_query("SELECT count() FROM market_data")
        cold_size = self.execute_cold_query("""
            SELECT formatReadableSize(sum(bytes)) 
            FROM system.parts 
            WHERE database = 'marketprism_cold' AND table = 'market_data'
        """)
        cold_range = self.execute_cold_query("SELECT min(timestamp), max(timestamp) FROM market_data")
        
        stats["cold_storage"] = {
            "record_count": int(cold_count) if cold_count and cold_count.isdigit() else 0,
            "storage_size": cold_size or "0 B",
            "time_range": cold_range or "N/A"
        }
        
        # 总计
        stats["total"] = {
            "total_records": stats["hot_storage"]["record_count"] + stats["cold_storage"]["record_count"],
            "retention_policy": f"Hot: {self.hot_retention_days} days, Cold: unlimited"
        }
        
        return stats

def main():
    """演示查询路由器功能"""
    print("🎯 MarketPrism 智能查询路由器演示")
    print("=" * 60)
    
    router = QueryRouter(hot_retention_days=7)
    
    # 1. 获取存储统计
    print("📊 存储统计信息:")
    stats = router.get_storage_statistics()
    print(f"🔥 热存储: {stats['hot_storage']['record_count']} 条记录, {stats['hot_storage']['storage_size']}")
    print(f"❄️ 冷存储: {stats['cold_storage']['record_count']} 条记录, {stats['cold_storage']['storage_size']}")
    print(f"📈 总计: {stats['total']['total_records']} 条记录")
    print()
    
    # 2. 演示不同类型的查询
    test_queries = [
        # 只查冷存储（历史数据）
        {
            "name": "历史数据查询（只查冷存储）",
            "query": "SELECT count() FROM market_data WHERE timestamp <= now() - INTERVAL 10 DAY"
        },
        # 只查热存储（最新数据）
        {
            "name": "最新数据查询（只查热存储）",
            "query": "SELECT count() FROM market_data WHERE timestamp >= now() - INTERVAL 3 DAY"
        },
        # 跨存储查询（无时间限制）
        {
            "name": "全量数据查询（跨存储）",
            "query": "SELECT count() FROM market_data"
        },
        # 按交易所统计
        {
            "name": "交易所分布统计",
            "query": "SELECT exchange, count() FROM market_data GROUP BY exchange ORDER BY count() DESC"
        }
    ]
    
    for i, test in enumerate(test_queries, 1):
        print(f"🔍 测试 {i}: {test['name']}")
        print(f"📝 查询: {test['query']}")
        
        result = router.route_query(test['query'])
        
        print(f"🎯 执行计划: {' + '.join(result['execution_plan'])}")
        if result['combined_result']:
            print(f"📊 查询结果:")
            # 限制输出长度
            output = result['combined_result']
            if len(output) > 500:
                output = output[:500] + "..."
            print(f"   {output}")
        print("-" * 40)
    
    # 3. 便捷查询API演示
    print("\n🚀 便捷查询API演示:")
    
    # 查询特定交易所的数据
    result = router.query_market_data(
        exchanges=['binance', 'okx'],
        limit=5
    )
    
    print("🏪 Binance和OKX交易所数据（最新5条）:")
    if result['combined_result']:
        print(result['combined_result'][:300] + "..." if len(result['combined_result']) > 300 else result['combined_result'])
    
    print("\n" + "=" * 60)
    print("🎉 智能查询路由器演示完成!")
    print()
    print("✅ 功能特性:")
    print("  • 自动分析查询时间范围")
    print("  • 智能选择存储层")
    print("  • 自动合并跨存储结果")
    print("  • 提供便捷查询API")
    print("  • 优化查询性能")

if __name__ == "__main__":
    main() 