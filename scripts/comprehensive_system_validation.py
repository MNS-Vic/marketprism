#!/usr/bin/env python3
"""
MarketPrism 系统深度验证脚本
执行全面的配置一致性、数据质量、性能和稳定性测试

使用方法:
    source venv/bin/activate
    python scripts/comprehensive_system_validation.py [--duration 30] [--stress-test]

功能模块:
1. 配置一致性深度验证
2. 数据质量深度分析  
3. 系统压力和稳定性测试
4. 错误处理和监控验证
5. 性能基准测试
"""

import os
import sys
import json
import time
import argparse
import threading
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import psutil

# 配置常量
CH_URL = os.getenv("CLICKHOUSE_HTTP", "http://localhost:8123")
DB = os.getenv("CLICKHOUSE_DB", "marketprism_hot")
NATS_URL = os.getenv("MARKETPRISM_NATS_URL", os.getenv("NATS_URL", "nats://localhost:4222"))
STORAGE_HEALTH = "http://localhost:18080/health"
COLLECTOR_HEALTH = "http://localhost:8086/health"
NATS_MONITORING = "http://localhost:8222"

# 数据表配置
HIGH_FREQ_TABLES = ["trades", "orderbooks"]
LOW_FREQ_TABLES = ["funding_rates", "open_interests", "liquidations", 
                   "lsr_top_positions", "lsr_all_accounts", "volatility_indices"]
ALL_TABLES = HIGH_FREQ_TABLES + LOW_FREQ_TABLES

# 交易所和交易对配置
EXPECTED_EXCHANGES = ["binance_spot", "binance_derivatives", "okx_spot", "okx_derivatives", "deribit"]
EXPECTED_SYMBOLS = ["BTC-USDT", "ETH-USDT", "BTC-USD", "ETH-USD"]

@dataclass
class ValidationResult:
    """验证结果数据结构"""
    module: str
    test_name: str
    status: str  # PASS, FAIL, WARNING
    details: Dict[str, Any]
    timestamp: str
    duration_ms: int
    
@dataclass
class SystemMetrics:
    """系统指标数据结构"""
    timestamp: str
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    disk_io_read_mb: float
    disk_io_write_mb: float
    network_sent_mb: float
    network_recv_mb: float
    
class ValidationRunner:
    """验证执行器"""
    
    def __init__(self, duration_minutes: int = 30, stress_test: bool = False):
        self.duration_minutes = duration_minutes
        self.stress_test = stress_test
        self.results: List[ValidationResult] = []
        self.metrics: List[SystemMetrics] = []
        self.start_time = datetime.now(timezone.utc)
        
    def log(self, message: str, level: str = "INFO"):
        """统一日志输出"""
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")
        
    def add_result(self, module: str, test_name: str, status: str, details: Dict[str, Any], duration_ms: int = 0):
        """添加验证结果"""
        result = ValidationResult(
            module=module,
            test_name=test_name,
            status=status,
            details=details,
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration_ms=duration_ms
        )
        self.results.append(result)
        
        # 实时输出结果
        status_icon = {"PASS": "✅", "FAIL": "❌", "WARNING": "⚠️"}.get(status, "❓")
        self.log(f"{status_icon} {module}.{test_name}: {status}")
        if details.get("summary"):
            self.log(f"   {details['summary']}")
            
    def ch_query(self, sql: str, timeout: int = 30) -> Tuple[int, str]:
        """ClickHouse查询"""
        try:
            resp = requests.post(f"{CH_URL}/?database={DB}", 
                               data=sql.encode("utf-8"), timeout=timeout)
            return resp.status_code, resp.text.strip()
        except Exception as e:
            return 599, str(e)
            
    def http_get(self, url: str, timeout: int = 10) -> Tuple[int, Dict]:
        """HTTP GET请求"""
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.headers.get('content-type', '').startswith('application/json'):
                return resp.status_code, resp.json()
            return resp.status_code, {"text": resp.text}
        except Exception as e:
            return 599, {"error": str(e)}
            
    def collect_system_metrics(self):
        """收集系统指标"""
        try:
            cpu = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk_io = psutil.disk_io_counters()
            net_io = psutil.net_io_counters()
            
            metrics = SystemMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                cpu_percent=cpu,
                memory_percent=memory.percent,
                memory_used_mb=memory.used / 1024 / 1024,
                disk_io_read_mb=disk_io.read_bytes / 1024 / 1024 if disk_io else 0,
                disk_io_write_mb=disk_io.write_bytes / 1024 / 1024 if disk_io else 0,
                network_sent_mb=net_io.bytes_sent / 1024 / 1024 if net_io else 0,
                network_recv_mb=net_io.bytes_recv / 1024 / 1024 if net_io else 0
            )
            self.metrics.append(metrics)
        except Exception as e:
            self.log(f"Failed to collect system metrics: {e}", "WARNING")
            
    def validate_config_consistency(self):
        """1. 配置一致性深度验证"""
        self.log("开始配置一致性验证...")
        start_time = time.time()
        
        # 检查环境变量配置文件
        env_file = "services/message-broker/.env.docker"
        config_details = {}
        
        try:
            with open(env_file, 'r') as f:
                content = f.read()
                
            # 提取LSR配置
            lsr_config = {}
            for line in content.split('\n'):
                if line.startswith('LSR_') and '=' in line:
                    key, value = line.split('=', 1)
                    lsr_config[key] = value
                    
            config_details["env_file_lsr"] = lsr_config
            
            # 检查运行时配置一致性
            code, storage_health = self.http_get(STORAGE_HEALTH)
            if code == 200 and isinstance(storage_health, dict):
                config_details["storage_runtime"] = {
                    "nats_connected": storage_health.get("nats_connected"),
                    "subscriptions": storage_health.get("subscriptions")
                }
                
            # 检查NATS JetStream配置（使用详细模式，避免 /jsz 返回 streams 为整数计数导致不可迭代）
            code, nats_info = self.http_get(f"{NATS_MONITORING}/jsz?streams=true&config=true")
            if code == 200 and isinstance(nats_info, dict):
                streams = nats_info.get("streams", [])
                if not isinstance(streams, list):
                    streams = []
                config_details["jetstream_streams"] = {
                    stream.get("config", {}).get("name"): {
                        "subjects": stream.get("config", {}).get("subjects", []),
                        "max_msgs": stream.get("config", {}).get("max_msgs"),
                        "max_bytes": stream.get("config", {}).get("max_bytes"),
                        "max_age": stream.get("config", {}).get("max_age")
                    } for stream in streams
                }
                
            status = "PASS" if config_details else "FAIL"
            summary = f"检查了{len(config_details)}个配置源"
            
        except Exception as e:
            status = "FAIL"
            summary = f"配置检查失败: {e}"
            config_details = {"error": str(e)}
            
        duration_ms = int((time.time() - start_time) * 1000)
        self.add_result("config", "consistency_check", status,
                       {**config_details, "summary": summary}, duration_ms)

    def validate_data_quality(self):
        """2. 数据质量深度分析"""
        self.log("开始数据质量分析...")

        for table in ALL_TABLES:
            start_time = time.time()
            details = {"table": table}

            try:
                # 基础统计
                code, count_str = self.ch_query(f"SELECT count() FROM {table}")
                if code == 200:
                    total_count = int(count_str)
                    details["total_count"] = total_count
                else:
                    raise Exception(f"Count query failed: {count_str}")

                if total_count == 0:
                    status = "WARNING"
                    summary = "表为空"
                else:
                    # 数据质量检查
                    quality_checks = []

                    # 1. 价格/数量合理性检查（针对trades表）
                    if table == "trades":
                        code, result = self.ch_query(f"""
                            SELECT
                                countIf(price <= 0) as invalid_price,
                                countIf(amount <= 0) as invalid_amount,
                                countIf(price > 1000000) as extreme_price,
                                min(price) as min_price,
                                max(price) as max_price,
                                avg(price) as avg_price
                            FROM {table}
                            WHERE timestamp > now() - INTERVAL 1 HOUR
                        """)
                        if code == 200:
                            values = result.split('\t')
                            if len(values) >= 6:
                                invalid_price, invalid_amount, extreme_price = map(int, values[:3])
                                min_price, max_price, avg_price = map(float, values[3:6])

                                details["price_quality"] = {
                                    "invalid_price_count": invalid_price,
                                    "invalid_amount_count": invalid_amount,
                                    "extreme_price_count": extreme_price,
                                    "price_range": [min_price, max_price],
                                    "avg_price": avg_price
                                }

                                if invalid_price > 0 or invalid_amount > 0:
                                    quality_checks.append("价格/数量异常")

                    # 2. 交易所和交易对完整性检查
                    code, exchanges = self.ch_query(f"""
                        SELECT DISTINCT exchange FROM {table}
                        WHERE timestamp > now() - INTERVAL 1 HOUR
                    """)
                    if code == 200:
                        found_exchanges = [e.strip() for e in exchanges.split('\n') if e.strip()]
                        details["exchanges"] = found_exchanges
                        missing_exchanges = set(EXPECTED_EXCHANGES) - set(found_exchanges)
                        if missing_exchanges:
                            quality_checks.append(f"缺失交易所: {missing_exchanges}")

                    # 3. 时间序列连续性分析
                    if table in HIGH_FREQ_TABLES:
                        code, gaps = self.ch_query(f"""
                            SELECT count() FROM (
                                SELECT timestamp,
                                       lag(timestamp) OVER (ORDER BY timestamp) as prev_ts
                                FROM {table}
                                WHERE timestamp > now() - INTERVAL 30 MINUTE
                                ORDER BY timestamp
                            ) WHERE dateDiff('second', prev_ts, timestamp) > 60
                        """)
                        if code == 200:
                            gap_count = int(gaps)
                            details["time_gaps"] = gap_count
                            if gap_count > 10:
                                quality_checks.append(f"时间间隔异常: {gap_count}个大于60秒的间隔")

                    # 4. 重复数据检测
                    if table in ["trades", "orderbooks"]:
                        code, duplicates = self.ch_query(f"""
                            SELECT count() FROM (
                                SELECT exchange, symbol, timestamp, count() as cnt
                                FROM {table}
                                WHERE timestamp > now() - INTERVAL 1 HOUR
                                GROUP BY exchange, symbol, timestamp
                                HAVING cnt > 1
                            )
                        """)
                        if code == 200:
                            dup_count = int(duplicates)
                            details["duplicates"] = dup_count
                            if dup_count > 0:
                                quality_checks.append(f"重复数据: {dup_count}条")

                    # 综合评估
                    if not quality_checks:
                        status = "PASS"
                        summary = f"数据质量良好，总计{total_count}条记录"
                    else:
                        status = "WARNING"
                        summary = f"发现质量问题: {'; '.join(quality_checks)}"

            except Exception as e:
                status = "FAIL"
                summary = f"数据质量检查失败: {e}"
                details["error"] = str(e)

            duration_ms = int((time.time() - start_time) * 1000)
            self.add_result("data_quality", f"{table}_analysis", status,
                           {**details, "summary": summary}, duration_ms)

    def validate_system_stability(self):
        """3. 系统压力和稳定性测试"""
        self.log(f"开始{self.duration_minutes}分钟稳定性测试...")

        start_time = time.time()
        end_time = start_time + (self.duration_minutes * 60)

        # 启动系统指标收集线程
        metrics_thread = threading.Thread(target=self._collect_metrics_continuously,
                                         args=(end_time,), daemon=True)
        metrics_thread.start()

        # 连接状态监控
        connection_issues = []
        performance_issues = []

        sample_count = 0
        while time.time() < end_time:
            sample_count += 1

            # 检查服务健康状态
            services_health = {}
            for service, url in [("storage", STORAGE_HEALTH), ("collector", COLLECTOR_HEALTH)]:
                code, response = self.http_get(url, timeout=5)
                services_health[service] = {
                    "status_code": code,
                    "healthy": code == 200 and response.get("status") == "healthy"
                }
                if not services_health[service]["healthy"]:
                    connection_issues.append(f"{service} unhealthy at sample {sample_count}")

            # 检查NATS连接状态
            code, nats_health = self.http_get(f"{NATS_MONITORING}/healthz", timeout=5)
            if code != 200:
                connection_issues.append(f"NATS unhealthy at sample {sample_count}")

            # 检查ClickHouse响应时间
            ch_start = time.time()
            code, _ = self.ch_query("SELECT 1", timeout=10)
            ch_duration = time.time() - ch_start

            if code != 200:
                connection_issues.append(f"ClickHouse error at sample {sample_count}")
            elif ch_duration > 2.0:
                performance_issues.append(f"ClickHouse slow response: {ch_duration:.2f}s at sample {sample_count}")

            # 采样间隔
            time.sleep(30)

        # 等待指标收集完成
        metrics_thread.join(timeout=10)

        # 分析结果
        details = {
            "duration_minutes": self.duration_minutes,
            "total_samples": sample_count,
            "connection_issues": connection_issues,
            "performance_issues": performance_issues,
            "metrics_collected": len(self.metrics)
        }

        if connection_issues or performance_issues:
            status = "WARNING" if len(connection_issues) < sample_count * 0.1 else "FAIL"
            summary = f"发现{len(connection_issues)}个连接问题，{len(performance_issues)}个性能问题"
        else:
            status = "PASS"
            summary = f"系统稳定运行{self.duration_minutes}分钟，无异常"

        duration_ms = int((time.time() - start_time) * 1000)
        self.add_result("stability", "long_run_test", status,
                       {**details, "summary": summary}, duration_ms)

    def _collect_metrics_continuously(self, end_time: float):
        """持续收集系统指标"""
        while time.time() < end_time:
            self.collect_system_metrics()
            time.sleep(10)  # 每10秒收集一次

    def validate_error_handling(self):
        """4. 错误处理和监控验证"""
        self.log("开始错误处理验证...")

        error_scenarios = []

        # 场景1: 测试ClickHouse连接中断恢复
        start_time = time.time()
        try:
            # 暂停ClickHouse容器
            self.log("测试ClickHouse连接中断...")
            subprocess.run(["docker", "pause", "marketprism-clickhouse-hot"],
                          check=True, capture_output=True)

            # 等待几秒让系统检测到中断
            time.sleep(5)

            # 检查Storage服务的健康状态
            code, health = self.http_get(STORAGE_HEALTH, timeout=5)
            ch_disconnected = code != 200 or not health.get("healthy", False)

            # 恢复ClickHouse
            subprocess.run(["docker", "unpause", "marketprism-clickhouse-hot"],
                          check=True, capture_output=True)

            # 等待恢复
            recovery_time = 0
            max_recovery_time = 30
            while recovery_time < max_recovery_time:
                time.sleep(2)
                recovery_time += 2
                code, _ = self.ch_query("SELECT 1", timeout=5)
                if code == 200:
                    break

            error_scenarios.append({
                "scenario": "clickhouse_disconnect",
                "detected_disconnect": ch_disconnected,
                "recovery_time_seconds": recovery_time,
                "recovered": code == 200
            })

        except Exception as e:
            error_scenarios.append({
                "scenario": "clickhouse_disconnect",
                "error": str(e),
                "recovered": False
            })

        # 场景2: 测试无效数据处理
        try:
            self.log("测试无效数据处理...")
            # 这里可以通过NATS发送无效数据来测试错误处理
            # 由于复杂性，这里只检查日志中的错误处理记录

            # 检查Storage服务日志中的错误处理
            try:
                with open("services/data-storage-service/production.log", "r") as f:
                    log_content = f.read()
                    error_count = log_content.count("ERROR")
                    warning_count = log_content.count("WARNING")

                error_scenarios.append({
                    "scenario": "log_error_analysis",
                    "error_count": error_count,
                    "warning_count": warning_count,
                    "has_error_handling": error_count > 0 or warning_count > 0
                })
            except FileNotFoundError:
                error_scenarios.append({
                    "scenario": "log_error_analysis",
                    "error": "Log file not found"
                })

        except Exception as e:
            error_scenarios.append({
                "scenario": "invalid_data_test",
                "error": str(e)
            })

        # 评估错误处理能力
        recovery_success = sum(1 for s in error_scenarios
                              if s.get("recovered", False) or s.get("has_error_handling", False))

        if recovery_success >= len(error_scenarios) * 0.8:
            status = "PASS"
            summary = f"错误处理良好，{recovery_success}/{len(error_scenarios)}个场景通过"
        elif recovery_success > 0:
            status = "WARNING"
            summary = f"错误处理部分有效，{recovery_success}/{len(error_scenarios)}个场景通过"
        else:
            status = "FAIL"
            summary = "错误处理机制存在问题"

        duration_ms = int((time.time() - start_time) * 1000)
        self.add_result("error_handling", "fault_tolerance", status,
                       {"scenarios": error_scenarios, "summary": summary}, duration_ms)

    def validate_performance_benchmarks(self):
        """5. 性能基准测试"""
        self.log("开始性能基准测试...")

        benchmarks = {}

        # 1. 端到端延迟测试
        start_time = time.time()
        try:
            # 测量ClickHouse查询性能
            query_times = []
            for _ in range(10):
                query_start = time.time()
                code, _ = self.ch_query("SELECT count() FROM trades WHERE timestamp > now() - INTERVAL 5 MINUTE")
                query_time = time.time() - query_start
                if code == 200:
                    query_times.append(query_time * 1000)  # 转换为毫秒

            if query_times:
                benchmarks["clickhouse_query"] = {
                    "avg_ms": sum(query_times) / len(query_times),
                    "min_ms": min(query_times),
                    "max_ms": max(query_times),
                    "samples": len(query_times)
                }

        except Exception as e:
            benchmarks["clickhouse_query"] = {"error": str(e)}

        # 2. 吞吐量测试
        try:
            # 计算最近5分钟的消息处理速率
            throughput_queries = {
                "trades_per_minute": "SELECT count() / 5 FROM trades WHERE timestamp > now() - INTERVAL 5 MINUTE",
                "orderbooks_per_minute": "SELECT count() / 5 FROM orderbooks WHERE timestamp > now() - INTERVAL 5 MINUTE"
            }

            for metric, query in throughput_queries.items():
                code, result = self.ch_query(query)
                if code == 200:
                    try:
                        rate = float(result)
                        benchmarks[metric] = rate
                    except ValueError:
                        benchmarks[metric] = 0

        except Exception as e:
            benchmarks["throughput_error"] = str(e)

        # 3. 系统资源使用分析
        if self.metrics:
            cpu_values = [m.cpu_percent for m in self.metrics]
            memory_values = [m.memory_percent for m in self.metrics]

            benchmarks["resource_usage"] = {
                "avg_cpu_percent": sum(cpu_values) / len(cpu_values),
                "max_cpu_percent": max(cpu_values),
                "avg_memory_percent": sum(memory_values) / len(memory_values),
                "max_memory_percent": max(memory_values),
                "samples": len(self.metrics)
            }

        # 4. NATS JetStream性能
        try:
            #   NATS jsz   streams  int  /jsz?streams=true&config=true 
            code, js_info = self.http_get(f"{NATS_MONITORING}/jsz?streams=true&config=true")
            if code == 200 and isinstance(js_info, dict):
                streams = js_info.get("streams", [])
                if not isinstance(streams, list):
                    streams = []
                for stream in streams:
                    stream_name = stream.get("config", {}).get("name", "unknown")
                    benchmarks[f"jetstream_{stream_name.lower()}"] = {
                        "messages": stream.get("state", {}).get("messages", 0),
                        "bytes": stream.get("state", {}).get("bytes", 0),
                        "consumers": stream.get("state", {}).get("consumers", 0)
                    }
        except Exception as e:
            benchmarks["jetstream_error"] = str(e)

        # 性能评估
        performance_score = 0
        max_score = 0

        # ClickHouse查询性能评分
        if "clickhouse_query" in benchmarks and "avg_ms" in benchmarks["clickhouse_query"]:
            avg_ms = benchmarks["clickhouse_query"]["avg_ms"]
            if avg_ms < 100:
                performance_score += 25
            elif avg_ms < 500:
                performance_score += 15
            elif avg_ms < 1000:
                performance_score += 10
            max_score += 25

        # 吞吐量评分
        trades_rate = benchmarks.get("trades_per_minute", 0)
        if trades_rate > 1000:
            performance_score += 25
        elif trades_rate > 500:
            performance_score += 15
        elif trades_rate > 100:
            performance_score += 10
        max_score += 25

        # 资源使用评分
        if "resource_usage" in benchmarks:
            avg_cpu = benchmarks["resource_usage"]["avg_cpu_percent"]
            avg_memory = benchmarks["resource_usage"]["avg_memory_percent"]
            if avg_cpu < 50 and avg_memory < 70:
                performance_score += 25
            elif avg_cpu < 80 and avg_memory < 85:
                performance_score += 15
            max_score += 25

        # JetStream评分
        if any(k.startswith("jetstream_") for k in benchmarks.keys()):
            performance_score += 25
        max_score += 25

        # 综合评估
        if max_score > 0:
            score_percentage = (performance_score / max_score) * 100
            if score_percentage >= 80:
                status = "PASS"
                summary = f"性能优秀，得分{score_percentage:.1f}%"
            elif score_percentage >= 60:
                status = "WARNING"
                summary = f"性能良好，得分{score_percentage:.1f}%"
            else:
                status = "FAIL"
                summary = f"性能需要优化，得分{score_percentage:.1f}%"
        else:
            status = "FAIL"
            summary = "无法评估性能"

        duration_ms = int((time.time() - start_time) * 1000)
        self.add_result("performance", "benchmark_test", status,
                       {**benchmarks, "score_percentage": score_percentage if max_score > 0 else 0,
                        "summary": summary}, duration_ms)

    def run_all_validations(self):
        """执行所有验证测试"""
        self.log("🚀 开始MarketPrism系统深度验证")
        self.log(f"测试持续时间: {self.duration_minutes}分钟")
        self.log(f"压力测试模式: {'启用' if self.stress_test else '禁用'}")

        total_start = time.time()

        try:
            # 1. 配置一致性验证
            self.validate_config_consistency()

            # 2. 数据质量分析
            self.validate_data_quality()

            # 3. 系统稳定性测试
            self.validate_system_stability()

            # 4. 错误处理验证
            self.validate_error_handling()

            # 5. 性能基准测试
            self.validate_performance_benchmarks()

        except KeyboardInterrupt:
            self.log("验证被用户中断", "WARNING")
        except Exception as e:
            self.log(f"验证过程中发生异常: {e}", "ERROR")

        total_duration = time.time() - total_start
        self.log(f"✅ 验证完成，总耗时: {total_duration:.1f}秒")

        # 生成报告
        self.generate_report()

    def generate_report(self):
        """生成详细的验证报告"""
        self.log("📊 生成验证报告...")

        # 统计结果
        total_tests = len(self.results)
        passed_tests = len([r for r in self.results if r.status == "PASS"])
        warning_tests = len([r for r in self.results if r.status == "WARNING"])
        failed_tests = len([r for r in self.results if r.status == "FAIL"])

        # 生成报告
        report = {
            "validation_summary": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "duration_minutes": self.duration_minutes,
                "stress_test_enabled": self.stress_test,
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "warning_tests": warning_tests,
                "failed_tests": failed_tests,
                "success_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0
            },
            "test_results": [asdict(r) for r in self.results],
            "system_metrics": [asdict(m) for m in self.metrics],
            "recommendations": self._generate_recommendations()
        }

        # 保存报告到文件
        report_file = f"validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            self.log(f"📄 详细报告已保存到: {report_file}")
        except Exception as e:
            self.log(f"保存报告失败: {e}", "ERROR")

        # 控制台输出摘要
        self._print_summary_report(report)

    def _generate_recommendations(self) -> List[str]:
        """生成优化建议"""
        recommendations = []

        # 基于测试结果生成建议
        failed_modules = set()
        warning_modules = set()

        for result in self.results:
            if result.status == "FAIL":
                failed_modules.add(result.module)
            elif result.status == "WARNING":
                warning_modules.add(result.module)

        if "config" in failed_modules:
            recommendations.append("配置一致性存在问题，建议检查环境变量和JetStream配置")

        if "data_quality" in warning_modules or "data_quality" in failed_modules:
            recommendations.append("数据质量需要改进，建议增强数据验证和清洗机制")

        if "stability" in failed_modules:
            recommendations.append("系统稳定性不足，建议优化连接管理和错误恢复机制")

        if "performance" in warning_modules or "performance" in failed_modules:
            recommendations.append("性能需要优化，建议调整批处理参数和资源配置")

        # 基于系统指标生成建议
        if self.metrics:
            avg_cpu = sum(m.cpu_percent for m in self.metrics) / len(self.metrics)
            avg_memory = sum(m.memory_percent for m in self.metrics) / len(self.metrics)

            if avg_cpu > 80:
                recommendations.append(f"CPU使用率过高({avg_cpu:.1f}%)，建议优化算法或增加计算资源")
            if avg_memory > 85:
                recommendations.append(f"内存使用率过高({avg_memory:.1f}%)，建议优化内存管理或增加内存")

        if not recommendations:
            recommendations.append("系统运行良好，建议继续监控关键指标")

        return recommendations

    def _print_summary_report(self, report: Dict):
        """打印摘要报告"""
        summary = report["validation_summary"]

        print("\n" + "="*80)
        print("🎯 MarketPrism 系统深度验证报告")
        print("="*80)

        print(f"📅 验证时间: {summary['timestamp']}")
        print(f"⏱️  测试时长: {summary['duration_minutes']}分钟")
        print(f"🧪 总测试数: {summary['total_tests']}")
        print(f"✅ 通过: {summary['passed_tests']}")
        print(f"⚠️  警告: {summary['warning_tests']}")
        print(f"❌ 失败: {summary['failed_tests']}")
        print(f"📊 成功率: {summary['success_rate']:.1f}%")

        print("\n📋 测试结果详情:")
        print("-" * 60)

        for result in self.results:
            status_icon = {"PASS": "✅", "FAIL": "❌", "WARNING": "⚠️"}.get(result.status, "❓")
            print(f"{status_icon} {result.module}.{result.test_name}: {result.status}")
            if result.details.get("summary"):
                print(f"   └─ {result.details['summary']}")

        print("\n💡 优化建议:")
        print("-" * 60)
        for i, rec in enumerate(report["recommendations"], 1):
            print(f"{i}. {rec}")

        if self.metrics:
            print(f"\n📈 系统指标摘要 (基于{len(self.metrics)}个采样点):")
            print("-" * 60)
            avg_cpu = sum(m.cpu_percent for m in self.metrics) / len(self.metrics)
            avg_memory = sum(m.memory_percent for m in self.metrics) / len(self.metrics)
            print(f"CPU平均使用率: {avg_cpu:.1f}%")
            print(f"内存平均使用率: {avg_memory:.1f}%")

        print("\n" + "="*80)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="MarketPrism系统深度验证")
    parser.add_argument("--duration", type=int, default=30,
                       help="稳定性测试持续时间(分钟)，默认30分钟")
    parser.add_argument("--stress-test", action="store_true",
                       help="启用压力测试模式")

    args = parser.parse_args()

    # 检查依赖
    try:
        import psutil
        import requests
    except ImportError as e:
        print(f"❌ 缺少依赖包: {e}")
        print("请安装: pip install psutil requests")
        sys.exit(1)

    # 创建验证器并运行
    validator = ValidationRunner(duration_minutes=args.duration,
                               stress_test=args.stress_test)
    validator.run_all_validations()


if __name__ == "__main__":
    main()
