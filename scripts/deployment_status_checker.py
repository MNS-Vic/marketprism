#!/usr/bin/env python3
"""
MarketPrism部署状态检查器
检查当前部署状态并提供下一步行动建议
"""

import os
import sys
import json
import subprocess
import requests
import time
from pathlib import Path
from typing import Dict, Any, List

def run_command(command: str) -> tuple[bool, str]:
    """运行系统命令"""
    try:
        result = subprocess.run(
            command.split(),
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)

def check_local_environment() -> Dict[str, Any]:
    """检查本地环境状态"""
    print("🔍 检查本地环境状态...")
    
    status = {
        'docker_running': False,
        'services_status': {},
        'local_deployment': False,
        'api_accessible': False
    }
    
    # 检查Docker是否运行
    success, output = run_command("docker ps")
    status['docker_running'] = success
    
    if success:
        print("✅ Docker正在运行")
        
        # 检查MarketPrism服务状态
        success, output = run_command("docker-compose ps")
        if success and "marketprism" in output.lower():
            status['local_deployment'] = True
            print("✅ 检测到本地MarketPrism部署")
            
            # 解析服务状态
            lines = output.strip().split('\n')[1:]  # 跳过标题行
            for line in lines:
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 2:
                        service_name = parts[0]
                        service_status = "running" if "Up" in line else "stopped"
                        status['services_status'][service_name] = service_status
        else:
            print("⚠️ 未检测到本地MarketPrism部署")
    else:
        print("❌ Docker未运行或不可用")
    
    # 检查API可访问性
    try:
        response = requests.get('http://localhost:8080/health', timeout=5)
        if response.status_code == 200:
            status['api_accessible'] = True
            print("✅ MarketPrism API可访问")
        else:
            print(f"⚠️ API返回状态码: {response.status_code}")
    except Exception as e:
        print(f"❌ API不可访问: {e}")
    
    return status

def check_github_actions_status() -> Dict[str, Any]:
    """检查GitHub Actions状态"""
    print("\n🔍 检查GitHub Actions状态...")
    
    status = {
        'workflows_exist': False,
        'recent_runs': [],
        'deployment_workflow': False
    }
    
    # 检查工作流文件
    workflows_dir = Path('.github/workflows')
    if workflows_dir.exists():
        workflow_files = list(workflows_dir.glob('*.yml'))
        status['workflows_exist'] = len(workflow_files) > 0
        print(f"✅ 发现 {len(workflow_files)} 个工作流文件")
        
        # 检查是否有部署工作流
        for workflow_file in workflow_files:
            if 'deploy' in workflow_file.name.lower():
                status['deployment_workflow'] = True
                print(f"✅ 发现部署工作流: {workflow_file.name}")
    else:
        print("❌ 未找到GitHub Actions工作流")
    
    return status

def check_configuration_files() -> Dict[str, Any]:
    """检查配置文件状态"""
    print("\n🔍 检查配置文件状态...")
    
    status = {
        'env_example_exists': False,
        'env_file_exists': False,
        'docker_compose_exists': False,
        'proxy_config_exists': False,
        'alert_config_exists': False
    }
    
    # 检查关键配置文件
    config_files = {
        'env_example_exists': '.env.example',
        'env_file_exists': '.env',
        'docker_compose_exists': 'docker-compose.yml',
        'proxy_config_exists': 'config/proxy.yaml',
        'alert_config_exists': 'config/alerting/marketprism_alert_rules.py'
    }
    
    for key, file_path in config_files.items():
        if Path(file_path).exists():
            status[key] = True
            print(f"✅ {file_path} 存在")
        else:
            status[key] = False
            print(f"❌ {file_path} 缺失")
    
    return status

def generate_deployment_recommendations(
    local_status: Dict[str, Any],
    github_status: Dict[str, Any],
    config_status: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """生成部署建议"""
    recommendations = []
    
    # 分析当前状态
    has_local_deployment = local_status['local_deployment']
    has_github_workflows = github_status['workflows_exist']
    has_basic_config = config_status['docker_compose_exists']
    
    if not has_basic_config:
        recommendations.append({
            'priority': 'HIGH',
            'action': 'setup_basic_config',
            'title': '设置基础配置文件',
            'description': '缺少基础配置文件，需要先设置项目配置',
            'commands': [
                'git pull origin main',
                'cp .env.example .env',
                'nano .env  # 编辑配置'
            ],
            'estimated_time': '10分钟'
        })
    
    if not has_local_deployment:
        recommendations.append({
            'priority': 'HIGH',
            'action': 'local_deployment',
            'title': '执行本地部署',
            'description': '尚未在本地部署MarketPrism，建议先本地测试',
            'commands': [
                'python scripts/production_deployment_assistant.py',
                '# 或者手动部署:',
                'docker-compose up -d'
            ],
            'estimated_time': '15分钟'
        })
    
    if has_local_deployment and not local_status['api_accessible']:
        recommendations.append({
            'priority': 'MEDIUM',
            'action': 'fix_api_access',
            'title': '修复API访问问题',
            'description': '服务已部署但API不可访问，需要诊断问题',
            'commands': [
                'docker-compose logs data-collector',
                'docker-compose restart data-collector',
                'curl http://localhost:8080/health'
            ],
            'estimated_time': '10分钟'
        })
    
    if has_local_deployment and local_status['api_accessible']:
        recommendations.append({
            'priority': 'MEDIUM',
            'action': 'run_validation_tests',
            'title': '运行验证测试',
            'description': '本地部署成功，运行完整验证测试',
            'commands': [
                'python scripts/production_readiness_validator.py',
                'python scripts/test_alerting_system.py',
                'python scripts/okx_fallback_and_integration_validator.py'
            ],
            'estimated_time': '10分钟'
        })
    
    if has_github_workflows:
        recommendations.append({
            'priority': 'LOW',
            'action': 'trigger_ci_cd',
            'title': '触发CI/CD流水线',
            'description': '推送代码触发GitHub Actions自动化流程',
            'commands': [
                'git add .',
                'git commit -m "trigger CI/CD pipeline"',
                'git push origin main'
            ],
            'estimated_time': '5分钟'
        })
    
    return recommendations

def main():
    """主函数"""
    print("🚀 MarketPrism部署状态检查器")
    print("=" * 50)
    
    # 检查各项状态
    local_status = check_local_environment()
    github_status = check_github_actions_status()
    config_status = check_configuration_files()
    
    # 生成建议
    recommendations = generate_deployment_recommendations(
        local_status, github_status, config_status
    )
    
    # 输出状态总结
    print("\n📊 状态总结")
    print("-" * 30)
    print(f"Docker运行状态: {'✅' if local_status['docker_running'] else '❌'}")
    print(f"本地部署状态: {'✅' if local_status['local_deployment'] else '❌'}")
    print(f"API可访问性: {'✅' if local_status['api_accessible'] else '❌'}")
    print(f"GitHub工作流: {'✅' if github_status['workflows_exist'] else '❌'}")
    print(f"配置文件完整性: {'✅' if config_status['docker_compose_exists'] else '❌'}")
    
    # 输出建议
    print("\n💡 下一步行动建议")
    print("-" * 30)
    
    if not recommendations:
        print("🎉 系统状态良好，无需特殊操作！")
        print("建议运行监控脚本: python scripts/monitoring_and_maintenance.py")
    else:
        for i, rec in enumerate(recommendations, 1):
            priority_icon = {'HIGH': '🔴', 'MEDIUM': '🟡', 'LOW': '🟢'}.get(rec['priority'], '⚪')
            print(f"\n{i}. {priority_icon} {rec['title']} ({rec['priority']})")
            print(f"   描述: {rec['description']}")
            print(f"   预计时间: {rec['estimated_time']}")
            print("   执行命令:")
            for cmd in rec['commands']:
                print(f"     {cmd}")
    
    # 保存状态报告
    status_report = {
        'timestamp': time.time(),
        'local_status': local_status,
        'github_status': github_status,
        'config_status': config_status,
        'recommendations': recommendations
    }
    
    report_file = Path('deployment_status_report.json')
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(status_report, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\n📄 状态报告已保存: {report_file}")
    
    # 返回退出码
    if local_status['api_accessible']:
        return 0  # 系统运行正常
    elif local_status['local_deployment']:
        return 1  # 部署存在但有问题
    else:
        return 2  # 尚未部署

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
