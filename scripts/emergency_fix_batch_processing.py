#!/usr/bin/env python3
"""
紧急修复批量处理停滞问题
- 清理冲突进程
- 重启 simple_hot_storage
- 监控批量处理恢复状态
"""

import os
import sys
import time
import signal
import subprocess
import asyncio
import aiohttp
from datetime import datetime

def kill_conflicting_processes():
    """清理冲突的 simple_hot_storage 进程"""
    print("🧹 清理冲突进程...")
    try:
        # 查找所有相关进程
        result = subprocess.run(['pgrep', '-f', 'simple_hot_storage'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                if pid:
                    print(f"终止进程 PID: {pid}")
                    os.kill(int(pid), signal.SIGTERM)
            time.sleep(2)
            
            # 强制终止仍在运行的进程
            result2 = subprocess.run(['pgrep', '-f', 'simple_hot_storage'], 
                                   capture_output=True, text=True)
            if result2.returncode == 0:
                remaining_pids = result2.stdout.strip().split('\n')
                for pid in remaining_pids:
                    if pid:
                        print(f"强制终止进程 PID: {pid}")
                        os.kill(int(pid), signal.SIGKILL)
        print("✅ 进程清理完成")
    except Exception as e:
        print(f"⚠️ 进程清理异常: {e}")

async def check_batch_processing_recovery():
    """检查批量处理恢复状态"""
    print("🔍 检查批量处理恢复状态...")
    
    for attempt in range(30):  # 检查30次，每次间隔2秒
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('http://localhost:8081/metrics', timeout=5) as resp:
                    if resp.status == 200:
                        content = await resp.text()
                        lines = content.split('\n')
                        
                        batch_inserts = 0
                        messages_processed = 0
                        
                        for line in lines:
                            if 'hot_storage_batch_inserts_total' in line:
                                batch_inserts = int(line.split()[-1])
                            elif 'hot_storage_messages_processed_total' in line:
                                messages_processed = int(line.split()[-1])
                        
                        print(f"尝试 {attempt+1}/30: batch_inserts={batch_inserts}, messages_processed={messages_processed}")
                        
                        if batch_inserts > 0:
                            print("✅ 批量处理已恢复！")
                            return True
                            
        except Exception as e:
            print(f"检查失败 {attempt+1}: {e}")
        
        await asyncio.sleep(2)
    
    print("❌ 批量处理未能在60秒内恢复")
    return False

def restart_simple_hot_storage():
    """重启 simple_hot_storage 服务"""
    print("🔄 重启 simple_hot_storage 服务...")
    
    # 激活虚拟环境并启动服务
    cmd = [
        'bash', '-c',
        'source .venv/bin/activate && '
        'HOT_STORAGE_HTTP_PORT=8081 '
        'python services/data-storage-service/simple_hot_storage.py'
    ]
    
    try:
        # 后台启动服务
        process = subprocess.Popen(
            cmd, 
            cwd='/home/ubuntu/marketprism',
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid  # 创建新的进程组
        )
        
        print(f"✅ 服务已启动，PID: {process.pid}")
        
        # 等待服务启动
        time.sleep(5)
        
        return process
        
    except Exception as e:
        print(f"❌ 服务启动失败: {e}")
        return None

async def main():
    """主函数"""
    print(f"=== 紧急修复批量处理 @ {datetime.now().isoformat()} ===")
    
    # 1. 清理冲突进程
    kill_conflicting_processes()
    
    # 2. 重启服务
    process = restart_simple_hot_storage()
    if not process:
        print("❌ 服务启动失败，退出")
        return 1
    
    # 3. 检查恢复状态
    recovery_success = await check_batch_processing_recovery()
    
    if recovery_success:
        print("🎉 紧急修复成功！批量处理已恢复")
        return 0
    else:
        print("❌ 紧急修复失败，需要进一步诊断")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
