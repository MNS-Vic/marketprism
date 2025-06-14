#!/usr/bin/env python3
import subprocess
import time
import sys
import os
from pathlib import Path

def debug_data_collector_startup():
    project_root = Path(__file__).parent.parent
    script_path = project_root / "start-data-collector.sh"
    
    print(f"🔍 调试Data Collector启动...")
    print(f"📁 项目根目录: {project_root}")
    print(f"📜 启动脚本: {script_path}")
    print(f"✅ 脚本存在: {script_path.exists()}")
    print(f"✅ 脚本可执行: {os.access(script_path, os.X_OK)}")
    
    # 设置环境变量
    env = os.environ.copy()
    env['PYTHONPATH'] = str(project_root)
    print(f"🌍 PYTHONPATH: {env.get('PYTHONPATH')}")
    
    # 启动服务并捕获输出
    print(f"🚀 启动Data Collector...")
    try:
        process = subprocess.Popen(
            [str(script_path)],
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True
        )
        
        print(f"🔢 进程PID: {process.pid}")
        
        # 等待几秒钟
        time.sleep(5)
        
        # 检查进程状态
        poll_result = process.poll()
        print(f"📊 进程状态: {poll_result if poll_result is not None else 'Running'}")
        
        # 获取输出
        if poll_result is not None:  # 进程已退出
            stdout, stderr = process.communicate()
            print(f"📤 标准输出:")
            print(stdout)
            print(f"📤 错误输出:")
            print(stderr)
        else:
            # 进程仍在运行，获取部分输出
            print(f"✅ 进程仍在运行")
            process.terminate()
            stdout, stderr = process.communicate()
            print(f"📤 部分标准输出:")
            print(stdout[:1000] if stdout else "无输出")
            print(f"📤 部分错误输出:")
            print(stderr[:1000] if stderr else "无错误")
        
    except Exception as e:
        print(f"❌ 启动失败: {e}")

if __name__ == "__main__":
    debug_data_collector_startup()