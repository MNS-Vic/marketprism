#!/usr/bin/env python
# coding: utf-8

import subprocess
import sys
import time
import json
import os

def run_command(command):
    """运行命令并返回结果"""
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"命令执行失败: {e}")
        print(f"错误输出: {e.stderr}")
        return None

def check_collector_metrics():
    """检查go-collector指标端点"""
    print("检查go-collector指标端点...")
    
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:8001/metrics") as response:
            metrics = response.read().decode('utf-8')
            print(f"[OK] 成功连接到go-collector指标端点，内容长度: {len(metrics)}")
            return True
    except Exception as e:
        print(f"[ERROR] 无法连接到go-collector指标端点: {str(e)}")
        return False

def inspect_container():
    """检查go-collector容器配置"""
    print("\n检查go-collector容器配置...")
    
    # 获取容器ID
    cmd = 'docker ps --filter "name=go-collector" --format "{{.ID}}"'
    container_id = run_command(cmd)
    
    if not container_id:
        print("[ERROR] 未找到go-collector容器")
        return None
    
    container_id = container_id.strip()
    print(f"找到go-collector容器ID: {container_id}")
    
    # 检查容器端口映射
    cmd = f'docker inspect {container_id}'
    result = run_command(cmd)
    
    if not result:
        print("[ERROR] 无法检查容器配置")
        return None
    
    try:
        container_info = json.loads(result)
        port_bindings = container_info[0]['HostConfig']['PortBindings']
        
        print("当前端口映射:")
        for container_port, host_bindings in port_bindings.items():
            for binding in host_bindings:
                print(f"  容器端口 {container_port} -> 主机端口 {binding.get('HostPort', '未设置')}")
        
        # 检查环境变量
        env_vars = container_info[0]['Config']['Env']
        print("\n环境变量:")
        metrics_port = None
        for env in env_vars:
            if "METRICS_PORT" in env:
                metrics_port = env.split("=")[1]
                print(f"  {env} (指标端口)")
            else:
                print(f"  {env}")
        
        return {
            "container_id": container_id,
            "port_bindings": port_bindings,
            "metrics_port": metrics_port
        }
    
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"[ERROR] 解析容器配置失败: {str(e)}")
        return None

def update_docker_compose():
    """更新docker-compose.yml文件的端口映射"""
    print("\n更新docker-compose.yml文件...")
    
    docker_compose_path = "docker-compose.yml"
    
    # 检查文件是否存在
    if not os.path.exists(docker_compose_path):
        print(f"[ERROR] 文件不存在: {docker_compose_path}")
        return False
    
    # 读取文件内容
    try:
        with open(docker_compose_path, "r") as f:
            content = f.read()
        
        # 检查go-collector部分
        if "go-collector:" not in content:
            print("[ERROR] docker-compose.yml中未找到go-collector服务")
            return False
        
        # 分析go-collector端口映射
        import re
        ports_section = re.search(r"go-collector:.*?ports:(.*?)(?:volumes:|depends_on:|environment:|restart:)", content, re.DOTALL)
        
        if not ports_section:
            print("[ERROR] 无法在docker-compose.yml中找到go-collector的ports部分")
            return False
        
        ports_text = ports_section.group(1)
        
        # 检查端口映射中是否有8001:8000
        if "8001:8000" in ports_text:
            print("[OK] 端口映射已存在: 8001:8000，无需修改")
            return True
        
        # 更新端口映射
        new_content = content.replace(
            ports_text,
            ports_text.replace("- \"8001:8000\"", "- \"8001:8000\"  # Prometheus指标端口\n      - \"8000:8000\"  # 内部监控端口")
            if "8001:8000" in ports_text else
            ports_text.replace("ports:", "ports:\n      - \"8001:8000\"  # Prometheus指标端口")
        )
        
        # 写回文件
        with open(docker_compose_path, "w") as f:
            f.write(new_content)
            
        print("[OK] 已更新docker-compose.yml文件，添加正确的端口映射")
        return True
        
    except Exception as e:
        print(f"[ERROR] 更新docker-compose.yml文件失败: {str(e)}")
        return False

def restart_container():
    """重启go-collector容器"""
    print("\n重启go-collector容器...")
    
    cmd = 'docker-compose restart go-collector'
    result = run_command(cmd)
    
    if result is not None:
        print("[OK] go-collector容器已重启")
        
        # 等待容器启动
        print("等待容器就绪...")
        time.sleep(5)
        return True
    else:
        print("[ERROR] 重启go-collector容器失败")
        return False

def update_container_ports():
    """直接更新容器端口映射"""
    print("\n临时方案：直接更新容器端口映射...")
    
    # 获取容器ID
    cmd = 'docker ps --filter "name=go-collector" --format "{{.ID}}"'
    container_id = run_command(cmd)
    
    if not container_id:
        print("[ERROR] 未找到go-collector容器")
        return False
    
    container_id = container_id.strip()
    
    # 停止容器
    cmd = f'docker stop {container_id}'
    run_command(cmd)
    
    # 创建端口映射
    cmd = f'docker commit {container_id} go-collector-fixed'
    run_command(cmd)
    
    # 重新启动带有正确端口映射的容器
    cmd = f'docker run -d --name go-collector-fixed -p 8001:8000 -p 8000:8000 --network marketprism-network --restart unless-stopped go-collector-fixed'
    result = run_command(cmd)
    
    if result:
        print("[OK] 已创建新容器并设置正确的端口映射")
        return True
    else:
        print("[ERROR] 创建新容器失败")
        return False

def main():
    """主函数"""
    print("===== 修复go-collector指标端口问题 =====")
    
    # 检查当前状态
    metrics_accessible = check_collector_metrics()
    
    if metrics_accessible:
        print("[OK] go-collector指标端点可访问，无需修复")
        return
    
    # 检查容器配置
    container_config = inspect_container()
    
    if not container_config:
        print("[ERROR] 无法获取容器配置，修复失败")
        return
    
    # 更新docker-compose.yml
    updated = update_docker_compose()
    
    if updated:
        # 重启容器
        restarted = restart_container()
        
        if restarted:
            # 再次检查指标端点
            if check_collector_metrics():
                print("\n[OK] 修复成功！go-collector指标端点现在可访问")
            else:
                print("\n[WARN] 容器已重启，但指标端点仍不可访问")
                print("尝试备用方案...")
                
                if update_container_ports():
                    time.sleep(5)
                    if check_collector_metrics():
                        print("\n[OK] 备用方案成功！go-collector指标端点现在可访问")
                    else:
                        print("\n[ERROR] 所有修复尝试都失败")
        else:
            print("[ERROR] 无法重启容器，修复失败")
    else:
        print("[ERROR] 无法更新docker-compose.yml，修复失败")
    
    print("\n===== 修复完成 =====")

if __name__ == "__main__":
    main() 