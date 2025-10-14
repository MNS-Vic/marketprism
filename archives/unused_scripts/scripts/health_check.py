#!/usr/bin/env python3
"""
MarketPrism 系统健康检查脚本
用于监控系统状态、性能指标和数据完整性
"""

import asyncio
import aiohttp
import json
import time
import psutil
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import sys
import argparse

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))


class HealthChecker:
    """系统健康检查器"""
    
    def __init__(self):
        self.checks = []
        self.results = {}
        self.start_time = time.time()
        
        # 服务配置
        self.services = {
            "message-broker": {
                "name": "message-broker",
                "port": 8086,
                "health_url": "http://127.0.0.1:8086/api/v1/status",
                "process_name": "python3",
                "log_file": "services/message-broker/logs/broker_managed.log"
            },
            "data-collector": {
                "name": "data-collector", 
                "process_name": "python3",
                "log_file": "services/data-collector/logs/collector_managed.log"
            },
            "data-storage-service": {
                "name": "data-storage-service",
                "port": 8081,
                "health_url": "http://127.0.0.1:8081/health",
                "process_name": "python3",
                "log_file": "services/data-storage-service/logs/storage_managed.log"
            }
        }
        
        # 基础设施配置
        self.infrastructure = {
            "nats": {
                "name": "NATS",
                "port": 4222,
                "monitor_url": "http://127.0.0.1:8222/varz",
                "container_name": "marketprism-nats"
            },
            "clickhouse": {
                "name": "ClickHouse",
                "port": 8123,
                "ping_url": "http://127.0.0.1:8123/ping",
                "container_name": "marketprism-clickhouse-hot"
            }
        }
    
    async def run_all_checks(self) -> Dict[str, Any]:
        """运行所有健康检查"""
        print("🔍 开始系统健康检查...")
        print(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        # 系统资源检查
        await self._check_system_resources()
        
        # 基础设施检查
        await self._check_infrastructure()
        
        # 服务检查
        await self._check_services()
        
        # 数据完整性检查
        await self._check_data_integrity()
        
        # 性能指标检查
        await self._check_performance_metrics()
        
        # 生成总结报告
        return self._generate_summary()
    
    async def _check_system_resources(self):
        """检查系统资源"""
        print("\n📊 系统资源检查:")
        
        # CPU使用率
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_status = "✅" if cpu_percent < 80 else "⚠️" if cpu_percent < 95 else "❌"
        print(f"  CPU使用率: {cpu_percent:.1f}% {cpu_status}")
        
        # 内存使用
        memory = psutil.virtual_memory()
        memory_status = "✅" if memory.percent < 80 else "⚠️" if memory.percent < 90 else "❌"
        print(f"  内存使用: {memory.percent:.1f}% ({memory.used//1024//1024}MB/{memory.total//1024//1024}MB) {memory_status}")
        
        # 磁盘使用
        disk = psutil.disk_usage('/')
        disk_status = "✅" if disk.percent < 80 else "⚠️" if disk.percent < 90 else "❌"
        print(f"  磁盘使用: {disk.percent:.1f}% ({disk.used//1024//1024//1024}GB/{disk.total//1024//1024//1024}GB) {disk_status}")
        
        # 系统负载
        load_avg = psutil.getloadavg()
        load_status = "✅" if load_avg[0] < 2.0 else "⚠️" if load_avg[0] < 4.0 else "❌"
        print(f"  系统负载: {load_avg[0]:.2f} {load_status}")
        
        # 网络连接
        connections = len(psutil.net_connections())
        conn_status = "✅" if connections < 1000 else "⚠️" if connections < 2000 else "❌"
        print(f"  网络连接: {connections} {conn_status}")
        
        self.results["system_resources"] = {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "disk_percent": disk.percent,
            "load_average": load_avg[0],
            "connections": connections,
            "status": "healthy" if all(s == "✅" for s in [cpu_status, memory_status, disk_status, load_status, conn_status]) else "warning"
        }
    
    async def _check_infrastructure(self):
        """检查基础设施"""
        print("\n🏗️ 基础设施检查:")
        
        infra_results = {}
        
        for name, config in self.infrastructure.items():
            print(f"  {config['name']}:")
            
            # 检查Docker容器
            container_status = await self._check_docker_container(config['container_name'])
            print(f"    容器状态: {container_status}")
            
            # 检查端口监听
            port_status = self._check_port_listening(config['port'])
            print(f"    端口{config['port']}: {port_status}")
            
            # 检查服务响应
            if 'monitor_url' in config:
                response_status = await self._check_http_endpoint(config['monitor_url'])
                print(f"    监控接口: {response_status}")
            elif 'ping_url' in config:
                response_status = await self._check_http_endpoint(config['ping_url'])
                print(f"    Ping接口: {response_status}")
            else:
                response_status = "N/A"
            
            infra_results[name] = {
                "container_status": container_status,
                "port_status": port_status,
                "response_status": response_status,
                "overall_status": "healthy" if all("✅" in s for s in [container_status, port_status, response_status] if s != "N/A") else "unhealthy"
            }
        
        self.results["infrastructure"] = infra_results
    
    async def _check_services(self):
        """检查应用服务"""
        print("\n🚀 应用服务检查:")
        
        service_results = {}
        
        for name, config in self.services.items():
            print(f"  {config['name']}:")
            
            # 检查进程
            process_status = self._check_process_running(config['process_name'], name)
            print(f"    进程状态: {process_status}")
            
            # 检查端口（如果有）
            if 'port' in config:
                port_status = self._check_port_listening(config['port'])
                print(f"    端口{config['port']}: {port_status}")
            else:
                port_status = "N/A"
            
            # 检查健康接口（如果有）
            if 'health_url' in config:
                health_status = await self._check_http_endpoint(config['health_url'])
                print(f"    健康检查: {health_status}")
            else:
                health_status = "N/A"
            
            # 检查日志文件
            log_status = self._check_log_file(config['log_file'])
            print(f"    日志文件: {log_status}")
            
            # 检查进程资源使用
            resource_status = self._check_process_resources(config['process_name'], name)
            print(f"    资源使用: {resource_status}")
            
            service_results[name] = {
                "process_status": process_status,
                "port_status": port_status,
                "health_status": health_status,
                "log_status": log_status,
                "resource_status": resource_status,
                "overall_status": "healthy" if "✅" in process_status else "unhealthy"
            }
        
        self.results["services"] = service_results
    
    async def _check_data_integrity(self):
        """检查数据完整性"""
        print("\n📊 数据完整性检查:")
        
        data_results = {}
        
        # 检查ClickHouse数据
        try:
            # 使用POST方式查询（修复后的方式）
            async with aiohttp.ClientSession() as session:
                # 检查表数据量
                tables = ['orderbooks', 'trades', 'liquidations', 'funding_rates', 'open_interests']
                table_counts = {}
                
                for table in tables:
                    try:
                        async with session.post(
                            'http://127.0.0.1:8123/',
                            data=f'SELECT count(*) FROM marketprism_hot.{table}',
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as response:
                            if response.status == 200:
                                count = int(await response.text())
                                table_counts[table] = count
                                status = "✅" if count > 0 else "⚠️"
                                print(f"    {table}: {count:,} 条记录 {status}")
                            else:
                                table_counts[table] = -1
                                print(f"    {table}: 查询失败 ❌")
                    except Exception as e:
                        table_counts[table] = -1
                        print(f"    {table}: 查询异常 ❌ ({str(e)[:50]})")
                
                # 检查最新数据延迟（在ClickHouse端用UTC计算，避免时区误差）
                try:
                    # 1) 总体最新延迟：以高频的 orderbooks 为代表
                    ch_query = "SELECT toInt32(dateDiff('minute', max(timestamp), now())) FROM marketprism_hot.orderbooks"
                    async with session.post(
                        'http://127.0.0.1:8123/',
                        data=ch_query,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        if response.status == 200:
                            lag_text = (await response.text()).strip()
                            age_minutes = int(lag_text) if lag_text else -1
                            age_status = "✅" if 0 <= age_minutes < 10 else "⚠️" if 10 <= age_minutes < 60 else "❌"
                            if age_minutes >= 0:
                                print(f"    最新数据延迟: {age_minutes} 分钟 {age_status}")
                                data_results["latest_data_age_minutes"] = age_minutes
                            else:
                                print(f"    最新数据: 无数据 ❌")
                                data_results["latest_data_age_minutes"] = -1
                        else:
                            print(f"    最新数据: 查询失败 ❌")
                            data_results["latest_data_age_minutes"] = -1
                except Exception as e:
                    print(f"    最新数据: 查询异常 ❌ ({str(e)[:50]})")
                    data_results["latest_data_age_minutes"] = -1

                # 2) 分表延迟：funding_rates 按业务语义对负延迟做0截断
                per_table_lag = {}
                try:
                    lag_queries = {
                        'orderbooks': "SELECT toInt32(dateDiff('minute', max(timestamp), now())) FROM marketprism_hot.orderbooks",
                        'trades': "SELECT toInt32(dateDiff('minute', max(timestamp), now())) FROM marketprism_hot.trades",
                        'liquidations': "SELECT toInt32(dateDiff('minute', max(timestamp), now())) FROM marketprism_hot.liquidations",
                        'funding_rates': "SELECT toInt32(greatest(dateDiff('minute', max(timestamp), now()), 0)) FROM marketprism_hot.funding_rates",
                        'open_interests': "SELECT toInt32(dateDiff('minute', max(timestamp), now())) FROM marketprism_hot.open_interests",
                    }
                    for tbl, q in lag_queries.items():
                        try:
                            async with session.post('http://127.0.0.1:8123/', data=q, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                                if resp.status == 200:
                                    txt = (await resp.text()).strip()
                                    per_table_lag[tbl] = int(txt) if txt else -1
                                else:
                                    per_table_lag[tbl] = -1
                        except Exception:
                            per_table_lag[tbl] = -1
                    print("    分表延迟(分钟): " + ", ".join(f"{k}:{v}" for k, v in per_table_lag.items()))
                except Exception as e:
                    print(f"    分表延迟: 查询异常 ❌ ({str(e)[:50]})")

                data_results["per_table_lag_minutes"] = per_table_lag
                data_results["table_counts"] = table_counts
                data_results["total_records"] = sum(count for count in table_counts.values() if count > 0)

        except Exception as e:
            print(f"    ClickHouse连接失败 ❌ ({str(e)[:50]})")
            data_results["error"] = str(e)
        
        self.results["data_integrity"] = data_results
    
    async def _check_performance_metrics(self):
        """检查性能指标"""
        print("\n⚡ 性能指标检查:")
        
        perf_results = {}
        
        # 检查NATS性能
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('http://127.0.0.1:8222/varz', timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        nats_data = await response.json()
                        in_msgs = nats_data.get('in_msgs', 0)
                        out_msgs = nats_data.get('out_msgs', 0)
                        connections = nats_data.get('connections', 0)
                        
                        print(f"    NATS入站消息: {in_msgs:,}")
                        print(f"    NATS出站消息: {out_msgs:,}")
                        print(f"    NATS连接数: {connections}")
                        
                        perf_results["nats"] = {
                            "in_msgs": in_msgs,
                            "out_msgs": out_msgs,
                            "connections": connections
                        }
                    else:
                        print(f"    NATS监控: 获取失败 ❌")
        except Exception as e:
            print(f"    NATS监控: 连接异常 ❌ ({str(e)[:50]})")
        
        # 检查Broker性能
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('http://127.0.0.1:8086/api/v1/status', timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        broker_data = await response.json()
                        if broker_data.get('status') == 'success':
                            data = broker_data.get('data', {})
                            collectors = data.get('collectors', {})
                            nats_info = data.get('nats_info', {})
                            
                            print(f"    Broker收集器数量: {collectors.get('count', 0)}")
                            print(f"    Broker JetStream流: {nats_info.get('streams_count', 0)}")
                            
                            perf_results["broker"] = {
                                "collectors_count": collectors.get('count', 0),
                                "streams_count": nats_info.get('streams_count', 0)
                            }
                        else:
                            print(f"    Broker状态: 异常 ❌")
                    else:
                        print(f"    Broker状态: 获取失败 ❌")
        except Exception as e:
            print(f"    Broker状态: 连接异常 ❌ ({str(e)[:50]})")
        
        self.results["performance"] = perf_results
    
    async def _check_docker_container(self, container_name: str) -> str:
        """检查Docker容器状态"""
        try:
            result = subprocess.run(
                ['docker', 'ps', '--filter', f'name={container_name}', '--format', '{{.Status}}'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                status = result.stdout.strip()
                if 'Up' in status:
                    return f"运行中 ✅ ({status})"
                else:
                    return f"异常 ❌ ({status})"
            else:
                return "未运行 ❌"
        except Exception as e:
            return f"检查失败 ❌ ({str(e)[:30]})"
    
    def _check_port_listening(self, port: int) -> str:
        """检查端口监听状态"""
        try:
            connections = psutil.net_connections()
            for conn in connections:
                if conn.laddr.port == port and conn.status == 'LISTEN':
                    return f"监听中 ✅"
            return f"未监听 ❌"
        except Exception as e:
            return f"检查失败 ❌ ({str(e)[:30]})"
    
    async def _check_http_endpoint(self, url: str) -> str:
        """检查HTTP端点"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        return "响应正常 ✅"
                    else:
                        return f"响应异常 ❌ (状态码: {response.status})"
        except asyncio.TimeoutError:
            return "响应超时 ❌"
        except Exception as e:
            return f"连接失败 ❌ ({str(e)[:30]})"
    
    def _check_process_running(self, process_name: str, service_name: str) -> str:
        """检查进程运行状态"""
        try:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['name'] == process_name:
                        cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                        if service_name in cmdline:
                            processes.append(proc)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if processes:
                proc = processes[0]  # 取第一个匹配的进程
                uptime = time.time() - proc.create_time()
                uptime_hours = uptime / 3600
                return f"运行中 ✅ (PID: {proc.pid}, 运行: {uptime_hours:.1f}小时)"
            else:
                return "未运行 ❌"
        except Exception as e:
            return f"检查失败 ❌ ({str(e)[:30]})"
    
    def _check_process_resources(self, process_name: str, service_name: str) -> str:
        """检查进程资源使用"""
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['name'] == process_name:
                        cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                        if service_name in cmdline:
                            cpu_percent = proc.cpu_percent()
                            memory_mb = proc.memory_info().rss / 1024 / 1024
                            
                            cpu_status = "✅" if cpu_percent < 80 else "⚠️" if cpu_percent < 95 else "❌"
                            mem_status = "✅" if memory_mb < 500 else "⚠️" if memory_mb < 1000 else "❌"
                            
                            return f"CPU: {cpu_percent:.1f}% {cpu_status}, 内存: {memory_mb:.1f}MB {mem_status}"
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return "进程未找到 ❌"
        except Exception as e:
            return f"检查失败 ❌ ({str(e)[:30]})"
    
    def _check_log_file(self, log_file: str) -> str:
        """检查日志文件"""
        try:
            log_path = Path(log_file)
            if log_path.exists():
                size_mb = log_path.stat().st_size / 1024 / 1024
                mtime = datetime.fromtimestamp(log_path.stat().st_mtime)
                age_minutes = (datetime.now() - mtime).total_seconds() / 60
                
                size_status = "✅" if size_mb < 100 else "⚠️" if size_mb < 500 else "❌"
                age_status = "✅" if age_minutes < 60 else "⚠️"
                
                return f"存在 {size_status} ({size_mb:.1f}MB, {age_minutes:.0f}分钟前更新) {age_status}"
            else:
                return "不存在 ❌"
        except Exception as e:
            return f"检查失败 ❌ ({str(e)[:30]})"
    
    def _generate_summary(self) -> Dict[str, Any]:
        """生成总结报告"""
        print("\n" + "=" * 60)
        print("📋 健康检查总结:")
        
        # 计算总体状态
        overall_status = "healthy"
        issues = []
        
        # 系统资源状态
        sys_res = self.results.get("system_resources", {})
        if sys_res.get("status") != "healthy":
            overall_status = "warning"
            if sys_res.get("cpu_percent", 0) > 90:
                issues.append("CPU使用率过高")
            if sys_res.get("memory_percent", 0) > 90:
                issues.append("内存使用率过高")
            if sys_res.get("disk_percent", 0) > 90:
                issues.append("磁盘使用率过高")
        
        # 基础设施状态
        infra = self.results.get("infrastructure", {})
        unhealthy_infra = [name for name, info in infra.items() if info.get("overall_status") != "healthy"]
        if unhealthy_infra:
            overall_status = "critical"
            issues.extend([f"{name}服务异常" for name in unhealthy_infra])
        
        # 应用服务状态
        services = self.results.get("services", {})
        unhealthy_services = [name for name, info in services.items() if info.get("overall_status") != "healthy"]
        if unhealthy_services:
            overall_status = "critical"
            issues.extend([f"{name}服务异常" for name in unhealthy_services])
        
        # 数据完整性状态
        data = self.results.get("data_integrity", {})
        if data.get("latest_data_age_minutes", 0) > 60:
            overall_status = "warning"
            issues.append("数据更新延迟")
        
        # 输出总结
        status_emoji = {"healthy": "✅", "warning": "⚠️", "critical": "❌"}
        print(f"  总体状态: {overall_status.upper()} {status_emoji.get(overall_status, '❓')}")
        
        if issues:
            print(f"  发现问题: {len(issues)}个")
            for issue in issues:
                print(f"    - {issue}")
        else:
            print("  ✅ 所有检查项目正常")
        
        # 统计信息
        total_records = data.get("total_records", 0)
        if total_records > 0:
            print(f"  📊 数据记录: {total_records:,} 条")
        
        check_duration = time.time() - self.start_time
        print(f"  ⏱️ 检查耗时: {check_duration:.1f} 秒")
        
        return {
            "overall_status": overall_status,
            "issues": issues,
            "check_time": datetime.now().isoformat(),
            "check_duration": check_duration,
            "details": self.results
        }


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="MarketPrism 系统健康检查")
    parser.add_argument("--json", action="store_true", help="输出JSON格式结果")
    parser.add_argument("--output", help="输出文件路径")
    
    args = parser.parse_args()
    
    checker = HealthChecker()
    result = await checker.run_all_checks()
    
    if args.json:
        output = json.dumps(result, indent=2, ensure_ascii=False, default=str)
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"\n结果已保存到: {args.output}")
        else:
            print("\n" + "=" * 60)
            print("JSON输出:")
            print(output)
    
    # 返回退出码
    if result["overall_status"] == "healthy":
        return 0
    elif result["overall_status"] == "warning":
        return 1
    else:
        return 2


if __name__ == "__main__":
    exit(asyncio.run(main()))
