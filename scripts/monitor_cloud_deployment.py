#!/usr/bin/env python3
"""
GitHub Actions云端部署监控脚本
实时监控部署状态并提供详细的进度报告
"""

import json
import subprocess
import time
import sys
from datetime import datetime
from typing import Dict, Any, List

class CloudDeploymentMonitor:
    def __init__(self):
        self.repo_info = self.get_repo_info()
        
    def get_repo_info(self) -> Dict[str, str]:
        """获取仓库信息"""
        try:
            result = subprocess.run(
                ['gh', 'repo', 'view', '--json', 'nameWithOwner'],
                capture_output=True, text=True, check=True
            )
            repo_data = json.loads(result.stdout)
            return {
                'name': repo_data['nameWithOwner'],
                'url': f"https://github.com/{repo_data['nameWithOwner']}"
            }
        except Exception as e:
            print(f"❌ 获取仓库信息失败: {e}")
            sys.exit(1)
    
    def get_latest_workflow_run(self, workflow_name: str = "cloud-deployment.yml") -> Dict[str, Any]:
        """获取最新的工作流运行信息"""
        try:
            result = subprocess.run([
                'gh', 'run', 'list',
                '--workflow', workflow_name,
                '--limit', '1',
                '--json', 'databaseId,status,conclusion,createdAt,updatedAt,url,headBranch'
            ], capture_output=True, text=True, check=True)
            
            runs = json.loads(result.stdout)
            return runs[0] if runs else None
        except Exception as e:
            print(f"❌ 获取工作流运行信息失败: {e}")
            return None
    
    def get_workflow_jobs(self, run_id: str) -> List[Dict[str, Any]]:
        """获取工作流作业信息"""
        try:
            result = subprocess.run([
                'gh', 'run', 'view', run_id,
                '--json', 'jobs'
            ], capture_output=True, text=True, check=True)
            
            data = json.loads(result.stdout)
            return data.get('jobs', [])
        except Exception as e:
            print(f"❌ 获取作业信息失败: {e}")
            return []
    
    def get_job_logs(self, run_id: str, job_name: str) -> str:
        """获取作业日志"""
        try:
            result = subprocess.run([
                'gh', 'run', 'view', run_id,
                '--log', '--job', job_name
            ], capture_output=True, text=True, check=True)
            
            return result.stdout
        except Exception as e:
            return f"获取日志失败: {e}"
    
    def format_duration(self, start_time: str, end_time: str = None) -> str:
        """格式化持续时间"""
        try:
            start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_time.replace('Z', '+00:00')) if end_time else datetime.now()
            
            duration = end - start
            total_seconds = int(duration.total_seconds())
            
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            
            if hours > 0:
                return f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                return f"{minutes}m {seconds}s"
            else:
                return f"{seconds}s"
        except Exception:
            return "未知"
    
    def print_status_icon(self, status: str, conclusion: str = None) -> str:
        """获取状态图标"""
        if status == "completed":
            if conclusion == "success":
                return "✅"
            elif conclusion == "failure":
                return "❌"
            elif conclusion == "cancelled":
                return "⏹️"
            else:
                return "⚠️"
        elif status == "in_progress":
            return "🔄"
        elif status == "queued":
            return "⏳"
        else:
            return "❓"
    
    def monitor_deployment(self, run_id: str = None, follow: bool = True):
        """监控部署进度"""
        print("☁️ MarketPrism云端部署监控")
        print("=" * 50)
        
        if not run_id:
            # 获取最新的工作流运行
            latest_run = self.get_latest_workflow_run()
            if not latest_run:
                print("❌ 未找到工作流运行记录")
                return
            
            run_id = str(latest_run['databaseId'])
            print(f"📍 监控最新运行: {run_id}")
        
        print(f"🔗 工作流链接: {self.repo_info['url']}/actions/runs/{run_id}")
        print()
        
        if follow:
            self.follow_deployment(run_id)
        else:
            self.show_deployment_status(run_id)
    
    def follow_deployment(self, run_id: str):
        """跟踪部署进度"""
        print("👀 实时跟踪部署进度...")
        print("按 Ctrl+C 停止监控")
        print()
        
        try:
            while True:
                # 清屏（可选）
                # print("\033[2J\033[H")
                
                self.show_deployment_status(run_id)
                
                # 检查是否完成
                run_info = self.get_latest_workflow_run()
                if run_info and str(run_info['databaseId']) == run_id:
                    if run_info['status'] == 'completed':
                        print(f"\n🎉 部署完成！结果: {run_info['conclusion']}")
                        break
                
                print("\n⏳ 等待30秒后刷新...")
                time.sleep(30)
                
        except KeyboardInterrupt:
            print("\n\n⏹️ 监控已停止")
    
    def show_deployment_status(self, run_id: str):
        """显示部署状态"""
        # 获取运行信息
        run_info = self.get_latest_workflow_run()
        if not run_info or str(run_info['databaseId']) != run_id:
            print("❌ 无法获取运行信息")
            return
        
        # 显示总体状态
        status_icon = self.print_status_icon(run_info['status'], run_info.get('conclusion'))
        duration = self.format_duration(run_info['createdAt'], run_info.get('updatedAt'))
        
        print(f"📊 部署状态: {status_icon} {run_info['status']}")
        if run_info.get('conclusion'):
            print(f"📋 部署结果: {run_info['conclusion']}")
        print(f"⏱️ 运行时间: {duration}")
        print(f"🌿 分支: {run_info['headBranch']}")
        print()
        
        # 获取作业信息
        jobs = self.get_workflow_jobs(run_id)
        if jobs:
            print("📋 作业状态:")
            for job in jobs:
                job_icon = self.print_status_icon(job['status'], job.get('conclusion'))
                job_duration = self.format_duration(job['startedAt'], job.get('completedAt')) if job.get('startedAt') else "未开始"
                
                print(f"  {job_icon} {job['name']}")
                print(f"     状态: {job['status']}")
                if job.get('conclusion'):
                    print(f"     结果: {job['conclusion']}")
                print(f"     耗时: {job_duration}")
                
                # 显示步骤详情
                if job.get('steps'):
                    failed_steps = [step for step in job['steps'] if step.get('conclusion') == 'failure']
                    if failed_steps:
                        print(f"     ❌ 失败步骤: {', '.join([step['name'] for step in failed_steps])}")
                
                print()
        
        # 显示关键指标
        self.show_deployment_metrics(run_id)
    
    def show_deployment_metrics(self, run_id: str):
        """显示部署关键指标"""
        print("📈 关键指标:")
        
        # 这里可以添加更多的指标检查
        # 例如：API响应时间、服务健康状态等
        
        try:
            # 检查是否有测试结果
            result = subprocess.run([
                'gh', 'run', 'download', run_id,
                '--name', 'deployment-artifacts'
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                print("  ✅ 部署报告已生成")
            else:
                print("  ⏳ 部署报告生成中...")
                
        except Exception:
            print("  ❓ 无法获取部署指标")
        
        print()
    
    def download_artifacts(self, run_id: str):
        """下载部署产物"""
        print("📦 下载部署产物...")
        
        try:
            result = subprocess.run([
                'gh', 'run', 'download', run_id
            ], check=True)
            
            print("✅ 部署产物下载完成")
            
        except subprocess.CalledProcessError:
            print("❌ 下载部署产物失败")

def main():
    """主函数"""
    monitor = CloudDeploymentMonitor()
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--help":
            print("用法:")
            print("  python monitor_cloud_deployment.py [run_id] [--no-follow]")
            print("  python monitor_cloud_deployment.py --download [run_id]")
            return
        elif sys.argv[1] == "--download":
            run_id = sys.argv[2] if len(sys.argv) > 2 else None
            if not run_id:
                latest_run = monitor.get_latest_workflow_run()
                run_id = str(latest_run['databaseId']) if latest_run else None
            
            if run_id:
                monitor.download_artifacts(run_id)
            else:
                print("❌ 未找到运行ID")
            return
        else:
            run_id = sys.argv[1]
            follow = "--no-follow" not in sys.argv
            monitor.monitor_deployment(run_id, follow)
    else:
        monitor.monitor_deployment()

if __name__ == "__main__":
    main()
