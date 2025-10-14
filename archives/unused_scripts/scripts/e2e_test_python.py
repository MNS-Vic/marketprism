#!/usr/bin/env python3
"""
端到端测试脚本 - Python版本
用于在终端输出受限的环境中执行完整的OKX强平数据流测试
"""

import os
import sys
import time
import subprocess
import json
import asyncio
from pathlib import Path

# 添加项目路径
sys.path.insert(0, '/home/ubuntu/marketprism')
sys.path.insert(0, '/home/ubuntu/marketprism/services/data-collector')
sys.path.insert(0, '/home/ubuntu/marketprism/services/data-storage-service')

def run_cmd(cmd, cwd=None, timeout=300):
    """执行命令并返回结果"""
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            cwd=cwd or '/home/ubuntu/marketprism',
            capture_output=True, 
            text=True, 
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timeout after {timeout}s"
    except Exception as e:
        return -1, "", str(e)

def log(msg):
    """记录日志"""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{timestamp}] {msg}"
    print(log_msg)
    
    # 写入日志文件
    log_dir = Path('/home/ubuntu/marketprism/e2e_logs')
    log_dir.mkdir(exist_ok=True)
    with open(log_dir / 'python_e2e.log', 'a') as f:
        f.write(log_msg + '\n')

def cleanup():
    """清理容器"""
    log("开始清理容器...")
    
    compose_files = [
        'services/data-collector/docker-compose.unified.yml',
        'services/data-storage-service/docker-compose.hot-storage.yml', 
        'services/message-broker/docker-compose.nats.yml'
    ]
    
    for compose_file in compose_files:
        cmd = f"docker-compose -f {compose_file} down"
        rc, out, err = run_cmd(cmd)
        log(f"清理 {compose_file}: rc={rc}")
        if err:
            log(f"清理错误: {err}")

def main():
    log("=== 开始端到端测试 ===")
    
    try:
        # 1. 启动 NATS
        log("1) 启动 NATS (JetStream)...")
        rc, out, err = run_cmd("docker-compose -f services/message-broker/docker-compose.nats.yml up -d")
        log(f"NATS启动: rc={rc}")
        if rc != 0:
            log(f"NATS启动失败: {err}")
            return False
            
        # 等待NATS就绪
        log("等待NATS监控端口8222...")
        for i in range(30):
            rc, out, err = run_cmd("curl -sf http://localhost:8222/", timeout=5)
            if rc == 0:
                log("NATS已就绪")
                break
            time.sleep(2)
        else:
            log("NATS等待超时")
            return False
            
        # 2. 初始化JetStream
        log("2) 初始化JetStream流...")
        rc, out, err = run_cmd(
            "python services/message-broker/init_jetstream.py --wait --config scripts/js_init_market_data.yaml"
        )
        log(f"JetStream初始化: rc={rc}")
        if rc != 0:
            log(f"JetStream初始化失败: {err}")
            
        # 3. 启动ClickHouse + 存储服务
        log("3) 启动ClickHouse + 热存储服务...")
        rc, out, err = run_cmd(
            "docker-compose -f services/data-storage-service/docker-compose.hot-storage.yml up -d --build",
            timeout=600
        )
        log(f"存储服务启动: rc={rc}")
        
        # 等待ClickHouse就绪
        log("等待ClickHouse端口8123...")
        for i in range(60):
            rc, out, err = run_cmd("curl -sf 'http://localhost:8123/?query=SELECT%201'", timeout=5)
            if rc == 0:
                log("ClickHouse已就绪")
                break
            time.sleep(2)
        else:
            log("ClickHouse等待超时")
            
        # 4. 启动Data Collector
        log("4) 启动Data Collector...")
        rc, out, err = run_cmd(
            "docker-compose -f services/data-collector/docker-compose.unified.yml up -d --build",
            timeout=600
        )
        log(f"Collector启动: rc={rc}")
        
        # 等待一段时间让数据流动
        log("等待数据收集30秒...")
        time.sleep(30)
        
        # 5. 检查ClickHouse中的数据
        log("5) 查询ClickHouse中的OKX强平数据...")
        query = "SELECT timestamp,liquidation_time,exchange,market_type,symbol,side,price,quantity FROM marketprism_hot.liquidations WHERE exchange='okx_derivatives' ORDER BY timestamp DESC LIMIT 10 FORMAT TabSeparated"
        rc, out, err = run_cmd(f"curl -s 'http://localhost:8123/?query={query}'")
        
        log_dir = Path('/home/ubuntu/marketprism/e2e_logs')
        with open(log_dir / 'clickhouse_query.tsv', 'w') as f:
            f.write(out)
        log(f"ClickHouse查询结果已保存到 clickhouse_query.tsv")
        log(f"查询返回 {len(out.splitlines())} 行数据")
        
        # 6. 测试去重 - 重启collector
        log("6) 重启Collector测试去重...")
        rc, out, err = run_cmd("docker-compose -f services/data-collector/docker-compose.unified.yml restart data-collector")
        log(f"Collector重启: rc={rc}")
        
        time.sleep(10)
        
        # 检查去重
        dedup_query = "SELECT symbol,side,liquidation_time,COUNT() cnt,any(price) price,any(quantity) qty FROM marketprism_hot.liquidations WHERE exchange='okx_derivatives' AND timestamp > now()-INTERVAL 10 MINUTE GROUP BY 1,2,3 HAVING cnt > 1 ORDER BY 3 DESC LIMIT 10 FORMAT Pretty"
        rc, out, err = run_cmd(f"curl -s 'http://localhost:8123/?query={dedup_query}'")
        
        with open(log_dir / 'dedup_check.txt', 'w') as f:
            f.write(out)
        log(f"去重检查结果已保存到 dedup_check.txt")
        
        # 7. 检查容器状态
        log("7) 检查容器状态...")
        rc, out, err = run_cmd("docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")
        with open(log_dir / 'docker_status.txt', 'w') as f:
            f.write(out)
        log("容器状态已保存到 docker_status.txt")
        
        log("=== 端到端测试完成 ===")
        return True
        
    except Exception as e:
        log(f"测试过程中出现异常: {e}")
        return False
    finally:
        cleanup()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
