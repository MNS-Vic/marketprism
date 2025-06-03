#!/usr/bin/env python3
import subprocess
import sys
import os
import time
import signal
import threading

# 颜色设置
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"

# 环境变量设置
os.environ["NATS_URL"] = "nats://localhost:4222"
os.environ["CLICKHOUSE_HOST"] = "localhost"
os.environ["CLICKHOUSE_PORT"] = "9000"
os.environ["CLICKHOUSE_DATABASE"] = "marketprism"

# 设置日志目录
if not os.path.exists("logs"):
    os.makedirs("logs")

# 运行进程列表
processes = []

def signal_handler(sig, frame):
    print(f"\n{YELLOW}正在停止所有服务...{RESET}")
    for p in processes:
        if p.poll() is None:  # 如果进程还在运行
            p.terminate()
    print(f"{GREEN}所有服务已停止{RESET}")
    sys.exit(0)

# 注册信号处理
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def start_real_collector():
    """启动真实数据收集器"""
    print(f"{BLUE}启动真实数据收集器...{RESET}")
    log_file = open("logs/collector_real.log", "w")
    p = subprocess.Popen(
        ["./services/go-collector/dist/collector", "-config", "config/collector/real_collector_config.json"], 
        stdout=log_file, 
        stderr=subprocess.STDOUT
    )
    print(f"{GREEN}真实数据收集器启动成功，PID: {p.pid}{RESET}")
    return p

def start_data_ingestion():
    """启动数据接收服务"""
    print(f"{BLUE}启动数据接收服务...{RESET}")
    log_file = open("logs/data_ingestion.log", "w")
    p = subprocess.Popen(
        ["python", "-m", "services.ingestion.main"], 
        stdout=log_file, 
        stderr=subprocess.STDOUT
    )
    print(f"{GREEN}数据接收服务启动成功，PID: {p.pid}{RESET}")
    return p

def start_data_archiver():
    """启动数据归档服务"""
    print(f"{BLUE}启动数据归档服务...{RESET}")
    log_file = open("logs/data_archiver.log", "w")
    p = subprocess.Popen(
        ["python", "-m", "services.data_archiver.service"], 
        stdout=log_file, 
        stderr=subprocess.STDOUT
    )
    print(f"{GREEN}数据归档服务启动成功，PID: {p.pid}{RESET}")
    return p

def main():
    print(f"{GREEN}===== MarketPrism 本地服务启动 ====={RESET}")
    print(f"{BLUE}环境设置:{RESET}")
    print(f"  NATS_URL: {os.environ['NATS_URL']}")
    print(f"  CLICKHOUSE_HOST: {os.environ['CLICKHOUSE_HOST']}")
    print(f"  CLICKHOUSE_PORT: {os.environ['CLICKHOUSE_PORT']}")
    print()
    
    # 添加服务启动
    try:
        print(f"{BLUE}正在检查基础设施服务...{RESET}")
        
        # 检查ClickHouse连接
        try:
            subprocess.run(
                ["python", "-c", "import clickhouse_driver; client = clickhouse_driver.Client(host='localhost', port=9000); client.execute('SELECT 1')"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            print(f"{GREEN}✓ ClickHouse连接正常{RESET}")
        except subprocess.CalledProcessError:
            print(f"{RED}✗ ClickHouse连接失败{RESET}")
            print(f"{YELLOW}请确保ClickHouse服务已启动{RESET}")
            return
        
        # 检查NATS连接
        try:
            subprocess.run(
                ["python", "-c", "import nats; import asyncio; async def check(): await nats.connect('nats://localhost:4222'); asyncio.run(check())"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            print(f"{GREEN}✓ NATS连接正常{RESET}")
        except subprocess.CalledProcessError:
            print(f"{RED}✗ NATS连接失败{RESET}")
            print(f"{YELLOW}请确保NATS服务已启动{RESET}")
            return
        
        # 启动真实数据收集器
        collector_process = start_real_collector()
        processes.append(collector_process)
        
        # 给一些时间让收集器启动
        time.sleep(2)
        
        # 启动数据接收服务
        ingestion_process = start_data_ingestion()
        processes.append(ingestion_process)
        
        # 启动数据归档服务（可选）
        # archiver_process = start_data_archiver()
        # processes.append(archiver_process)
        
        print(f"\n{GREEN}所有服务已启动。日志保存在logs/目录{RESET}")
        print(f"{YELLOW}按Ctrl+C停止所有服务{RESET}")
        
        # 等待用户按Ctrl+C
        while True:
            # 检查进程状态
            for i, p in enumerate(processes):
                if p.poll() is not None:  # 进程已结束
                    print(f"{RED}警告: 进程#{i+1} (PID: {p.pid})已结束，返回码: {p.returncode}{RESET}")
                    # 这里可以添加重启逻辑
            time.sleep(5)
    
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)

if __name__ == "__main__":
    main()