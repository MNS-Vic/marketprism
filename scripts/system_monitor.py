#!/usr/bin/env python3
"""
MarketPrism 系统监控和管理工具
集成冷热存储监控、数据归档、查询路由等功能
"""

import subprocess
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import argparse
import sys
import os

# 导入其他模块
sys.path.append(os.path.dirname(__file__))
from query_router import QueryRouter

class SystemMonitor:
    """系统监控和管理"""
    
    def __init__(self):
        self.hot_container = "marketprism-clickhouse-1"
        self.cold_container = "marketprism-clickhouse-cold"
        self.hot_database = "marketprism"
        self.cold_database = "marketprism_cold"
        self.router = QueryRouter()
    
    def execute_query(self, container: str, database: str, query: str) -> Optional[str]:
        """执行数据库查询"""
        cmd = [
            "docker", "exec", container,
            "clickhouse-client", 
            "--database", database,
            "--query", query
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"❌ 查询失败 ({container}): {e}")
            return None
    
    def check_system_health(self) -> Dict[str, Any]:
        """检查系统健康状态"""
        print("🏥 检查系统健康状态...")
        health = {
            "containers": {},
            "databases": {},
            "storage": {},
            "overall_status": "healthy"
        }
        
        # 检查容器状态
        containers = [self.hot_container, self.cold_container]
        for container in containers:
            try:
                result = subprocess.run(
                    ["docker", "inspect", container, "--format", "{{.State.Status}}"],
                    capture_output=True, text=True, check=True
                )
                status = result.stdout.strip()
                health["containers"][container] = {
                    "status": status,
                    "healthy": status == "running"
                }
                if status != "running":
                    health["overall_status"] = "unhealthy"
            except subprocess.CalledProcessError:
                health["containers"][container] = {
                    "status": "not_found",
                    "healthy": False
                }
                health["overall_status"] = "unhealthy"
        
        # 检查数据库连接
        databases = [
            (self.hot_container, self.hot_database),
            (self.cold_container, self.cold_database)
        ]
        
        for container, database in databases:
            db_key = f"{container}:{database}"
            try:
                result = self.execute_query(container, database, "SELECT 1")
                health["databases"][db_key] = {
                    "connected": result is not None,
                    "response_time": "< 1s"  # 简化的响应时间
                }
                if result is None:
                    health["overall_status"] = "unhealthy"
            except Exception as e:
                health["databases"][db_key] = {
                    "connected": False,
                    "error": str(e)
                }
                health["overall_status"] = "unhealthy"
        
        return health
    
    def get_storage_overview(self) -> Dict[str, Any]:
        """获取存储概览"""
        print("📊 获取存储概览...")
        stats = self.router.get_storage_statistics()
        
        # 添加更多存储信息
        overview = {
            "summary": stats,
            "hot_storage_details": {},
            "cold_storage_details": {},
            "recommendations": []
        }
        
        # 热存储详细信息
        hot_tables = self.execute_query(
            self.hot_container, self.hot_database, 
            "SELECT table, sum(rows) as rows, formatReadableSize(sum(bytes)) as size FROM system.parts WHERE database = 'marketprism' GROUP BY table ORDER BY sum(bytes) DESC"
        )
        
        if hot_tables:
            overview["hot_storage_details"]["tables"] = []
            for line in hot_tables.split('\n'):
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 3:
                        overview["hot_storage_details"]["tables"].append({
                            "table": parts[0],
                            "rows": parts[1],
                            "size": parts[2]
                        })
        
        # 冷存储详细信息
        cold_tables = self.execute_query(
            self.cold_container, self.cold_database,
            "SELECT table, sum(rows) as rows, formatReadableSize(sum(bytes)) as size FROM system.parts WHERE database = 'marketprism_cold' GROUP BY table ORDER BY sum(bytes) DESC"
        )
        
        if cold_tables:
            overview["cold_storage_details"]["tables"] = []
            for line in cold_tables.split('\n'):
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 3:
                        overview["cold_storage_details"]["tables"].append({
                            "table": parts[0],
                            "rows": parts[1],
                            "size": parts[2]
                        })
        
        # 生成建议
        hot_count = stats["hot_storage"]["record_count"]
        cold_count = stats["cold_storage"]["record_count"]
        
        if hot_count > 100000:  # 假设阈值
            overview["recommendations"].append("热存储数据量较大，建议执行归档")
        
        if cold_count == 0:
            overview["recommendations"].append("冷存储为空，系统刚开始运行")
        
        total_records = hot_count + cold_count
        if total_records > 1000000:
            overview["recommendations"].append("总数据量较大，建议优化查询性能")
        
        return overview
    
    def get_data_distribution(self) -> Dict[str, Any]:
        """获取数据分布统计"""
        print("📈 分析数据分布...")
        
        distribution = {
            "by_exchange": {"hot": {}, "cold": {}},
            "by_time": {"hot": {}, "cold": {}},
            "by_data_type": {"hot": {}, "cold": {}}
        }
        
        # 按交易所分布
        hot_exchanges = self.execute_query(
            self.hot_container, self.hot_database,
            "SELECT exchange, count() as count, formatReadableSize(sum(length(raw_data))) as data_size FROM market_data GROUP BY exchange ORDER BY count DESC"
        )
        
        if hot_exchanges:
            for line in hot_exchanges.split('\n'):
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 3:
                        distribution["by_exchange"]["hot"][parts[0]] = {
                            "count": parts[1],
                            "size": parts[2]
                        }
        
        cold_exchanges = self.execute_query(
            self.cold_container, self.cold_database,
            "SELECT exchange, count() as count, formatReadableSize(sum(length(raw_data))) as data_size FROM market_data GROUP BY exchange ORDER BY count DESC"
        )
        
        if cold_exchanges:
            for line in cold_exchanges.split('\n'):
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 3:
                        distribution["by_exchange"]["cold"][parts[0]] = {
                            "count": parts[1],
                            "size": parts[2]
                        }
        
        # 按时间分布 (按天)
        hot_time = self.execute_query(
            self.hot_container, self.hot_database,
            "SELECT toDate(timestamp) as date, count() as count FROM market_data GROUP BY date ORDER BY date DESC LIMIT 7"
        )
        
        if hot_time:
            for line in hot_time.split('\n'):
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        distribution["by_time"]["hot"][parts[0]] = parts[1]
        
        cold_time = self.execute_query(
            self.cold_container, self.cold_database,
            "SELECT toYYYYMM(timestamp) as month, count() as count FROM market_data GROUP BY month ORDER BY month DESC LIMIT 12"
        )
        
        if cold_time:
            for line in cold_time.split('\n'):
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        distribution["by_time"]["cold"][parts[0]] = parts[1]
        
        return distribution
    
    def run_archive_simulation(self, days: int = 7) -> Dict[str, Any]:
        """运行归档模拟"""
        print(f"🧪 模拟 {days} 天归档策略...")
        
        # 计算需要归档的数据
        archive_query = f"SELECT count() FROM market_data WHERE timestamp <= now() - INTERVAL {days} DAY"
        hot_archive_count = self.execute_query(self.hot_container, self.hot_database, archive_query)
        
        # 计算归档后的数据分布
        remaining_query = f"SELECT count() FROM market_data WHERE timestamp > now() - INTERVAL {days} DAY"
        hot_remaining_count = self.execute_query(self.hot_container, self.hot_database, remaining_query)
        
        cold_total = self.execute_query(self.cold_container, self.cold_database, "SELECT count() FROM market_data")
        
        simulation = {
            "archive_threshold_days": days,
            "current_hot_records": int(hot_archive_count or 0) + int(hot_remaining_count or 0),
            "records_to_archive": int(hot_archive_count or 0),
            "records_remaining_hot": int(hot_remaining_count or 0),
            "current_cold_records": int(cold_total or 0),
            "projected_cold_records": int(cold_total or 0) + int(hot_archive_count or 0)
        }
        
        # 计算存储优化
        if simulation["records_to_archive"] > 0:
            simulation["storage_optimization"] = {
                "hot_storage_reduction": f"{simulation['records_to_archive']} 条记录",
                "estimated_space_saved": "预计节省热存储空间",
                "recommended": simulation["records_to_archive"] > 1000
            }
        
        return simulation
    
    def generate_system_report(self) -> Dict[str, Any]:
        """生成完整的系统报告"""
        print("📋 生成系统报告...")
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "health": self.check_system_health(),
            "storage": self.get_storage_overview(),
            "distribution": self.get_data_distribution(),
            "archive_simulation": self.run_archive_simulation(),
            "performance_metrics": self.get_performance_metrics()
        }
        
        return report
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        print("⚡ 收集性能指标...")
        
        metrics = {
            "query_performance": {},
            "storage_io": {},
            "system_load": {}
        }
        
        # 测试查询性能
        test_queries = [
            ("hot_count", "SELECT count() FROM market_data"),
            ("cold_count", "SELECT count() FROM market_data"),
            ("hot_latest", "SELECT max(timestamp) FROM market_data"),
            ("cold_range", "SELECT min(timestamp), max(timestamp) FROM market_data")
        ]
        
        for query_name, query in test_queries:
            if "hot" in query_name:
                start_time = time.time()
                result = self.execute_query(self.hot_container, self.hot_database, query)
                end_time = time.time()
                storage_type = "hot"
            else:
                start_time = time.time()
                result = self.execute_query(self.cold_container, self.cold_database, query)
                end_time = time.time()
                storage_type = "cold"
            
            metrics["query_performance"][query_name] = {
                "storage": storage_type,
                "execution_time_ms": round((end_time - start_time) * 1000, 2),
                "success": result is not None
            }
        
        return metrics
    
    def print_system_status(self):
        """打印系统状态概览"""
        print("🎯 MarketPrism 系统状态概览")
        print("=" * 60)
        
        # 健康检查
        health = self.check_system_health()
        status_emoji = "✅" if health["overall_status"] == "healthy" else "❌"
        print(f"{status_emoji} 系统状态: {health['overall_status'].upper()}")
        
        # 容器状态
        print("\n🐳 容器状态:")
        for container, status in health["containers"].items():
            emoji = "✅" if status["healthy"] else "❌"
            print(f"  {emoji} {container}: {status['status']}")
        
        # 存储概览
        storage = self.get_storage_overview()
        stats = storage["summary"]
        print(f"\n💾 存储概览:")
        print(f"  🔥 热存储: {stats['hot_storage']['record_count']:,} 条记录 ({stats['hot_storage']['storage_size']})")
        print(f"  ❄️ 冷存储: {stats['cold_storage']['record_count']:,} 条记录 ({stats['cold_storage']['storage_size']})")
        print(f"  📈 总计: {stats['total']['total_records']:,} 条记录")
        
        # 归档建议
        simulation = self.run_archive_simulation()
        if simulation["records_to_archive"] > 0:
            print(f"\n📦 归档建议:")
            print(f"  🔄 可归档: {simulation['records_to_archive']:,} 条记录")
            print(f"  💡 建议: {'执行归档' if simulation['records_to_archive'] > 100 else '暂无需要'}")
        
        # 推荐操作
        recommendations = storage.get("recommendations", [])
        if recommendations:
            print(f"\n💡 系统建议:")
            for i, rec in enumerate(recommendations, 1):
                print(f"  {i}. {rec}")
        
        print("\n" + "=" * 60)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="MarketPrism 系统监控和管理工具")
    parser.add_argument("--status", action="store_true", help="显示系统状态概览")
    parser.add_argument("--health", action="store_true", help="执行健康检查")
    parser.add_argument("--storage", action="store_true", help="显示存储概览")
    parser.add_argument("--distribution", action="store_true", help="显示数据分布")
    parser.add_argument("--report", action="store_true", help="生成完整报告")
    parser.add_argument("--archive-sim", type=int, metavar="DAYS", help="模拟归档 (指定天数)")
    parser.add_argument("--performance", action="store_true", help="性能测试")
    parser.add_argument("--output", choices=["json", "pretty"], default="pretty", help="输出格式")
    
    args = parser.parse_args()
    
    monitor = SystemMonitor()
    
    # 如果没有指定任何选项，显示状态概览
    if not any([args.health, args.storage, args.distribution, args.report, args.archive_sim, args.performance]):
        args.status = True
    
    try:
        if args.status:
            monitor.print_system_status()
        
        elif args.health:
            health = monitor.check_system_health()
            if args.output == "json":
                print(json.dumps(health, indent=2, ensure_ascii=False))
            else:
                print("🏥 系统健康检查结果:")
                print(f"整体状态: {health['overall_status']}")
                print("容器状态:", health['containers'])
                print("数据库状态:", health['databases'])
        
        elif args.storage:
            storage = monitor.get_storage_overview()
            if args.output == "json":
                print(json.dumps(storage, indent=2, ensure_ascii=False))
            else:
                print("💾 存储概览:")
                stats = storage["summary"]
                print(f"热存储: {stats['hot_storage']}")
                print(f"冷存储: {stats['cold_storage']}")
                print(f"建议: {storage.get('recommendations', [])}")
        
        elif args.distribution:
            dist = monitor.get_data_distribution()
            if args.output == "json":
                print(json.dumps(dist, indent=2, ensure_ascii=False))
            else:
                print("📈 数据分布分析:")
                print("按交易所分布:", dist["by_exchange"])
                print("按时间分布:", dist["by_time"])
        
        elif args.archive_sim:
            sim = monitor.run_archive_simulation(args.archive_sim)
            if args.output == "json":
                print(json.dumps(sim, indent=2, ensure_ascii=False))
            else:
                print(f"🧪 {args.archive_sim}天归档模拟:")
                print(f"当前热存储: {sim['current_hot_records']:,} 条记录")
                print(f"需要归档: {sim['records_to_archive']:,} 条记录")
                print(f"归档后热存储: {sim['records_remaining_hot']:,} 条记录")
                print(f"归档后冷存储: {sim['projected_cold_records']:,} 条记录")
        
        elif args.performance:
            metrics = monitor.get_performance_metrics()
            if args.output == "json":
                print(json.dumps(metrics, indent=2, ensure_ascii=False))
            else:
                print("⚡ 性能指标:")
                for query, data in metrics["query_performance"].items():
                    print(f"{query}: {data['execution_time_ms']}ms ({data['storage']})")
        
        elif args.report:
            report = monitor.generate_system_report()
            if args.output == "json":
                print(json.dumps(report, indent=2, ensure_ascii=False))
            else:
                print("📋 完整系统报告已生成 (使用 --output json 查看详细信息)")
    
    except KeyboardInterrupt:
        print("\n🛑 操作被用户中断")
    except Exception as e:
        print(f"❌ 执行错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 