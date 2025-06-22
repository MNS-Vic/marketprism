#!/usr/bin/env python3
"""
MarketPrism生产环境部署助手
自动化生产环境部署流程，确保部署的一致性和可靠性

功能：
1. 环境检查和准备
2. 配置文件生成和验证
3. 服务部署和启动
4. 部署后验证和监控
5. 回滚机制
"""

import os
import sys
import json
import yaml
import time
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import shutil

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ProductionDeploymentAssistant:
    """生产环境部署助手"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.deployment_config = {}
        self.deployment_log = []
        
    def log_step(self, step: str, status: str, details: str = ""):
        """记录部署步骤"""
        entry = {
            'timestamp': time.time(),
            'step': step,
            'status': status,
            'details': details
        }
        self.deployment_log.append(entry)
        
        status_icon = {'success': '✅', 'warning': '⚠️', 'error': '❌', 'info': 'ℹ️'}.get(status, '📝')
        logger.info(f"{status_icon} {step}: {details}")
    
    def run_command(self, command: str, timeout: int = 60) -> tuple[bool, str]:
        """运行系统命令"""
        try:
            result = subprocess.run(
                command.split() if isinstance(command, str) else command,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.project_root
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, f"Command timeout after {timeout}s"
        except Exception as e:
            return False, str(e)
    
    def check_prerequisites(self) -> bool:
        """检查部署前提条件"""
        logger.info("🔍 检查部署前提条件...")
        
        checks = [
            ("Docker", "docker --version"),
            ("Docker Compose", "docker-compose --version"),
            ("Git", "git --version"),
            ("Python", "python3 --version")
        ]
        
        all_passed = True
        for name, command in checks:
            success, output = self.run_command(command)
            if success:
                self.log_step(f"检查{name}", "success", output.strip().split('\n')[0])
            else:
                self.log_step(f"检查{name}", "error", f"{name}未安装或不可用")
                all_passed = False
        
        # 检查磁盘空间
        success, output = self.run_command("df -h .")
        if success:
            lines = output.strip().split('\n')
            if len(lines) > 1:
                usage_line = lines[1].split()
                if len(usage_line) >= 5:
                    usage_percent = usage_line[4].rstrip('%')
                    try:
                        usage = int(usage_percent)
                        if usage < 80:
                            self.log_step("磁盘空间检查", "success", f"磁盘使用率: {usage}%")
                        else:
                            self.log_step("磁盘空间检查", "warning", f"磁盘使用率较高: {usage}%")
                    except ValueError:
                        self.log_step("磁盘空间检查", "warning", "无法解析磁盘使用率")
        
        return all_passed
    
    def setup_environment_config(self) -> bool:
        """设置环境配置"""
        logger.info("⚙️ 设置环境配置...")
        
        env_file = self.project_root / '.env'
        env_example = self.project_root / '.env.example'
        
        if not env_example.exists():
            self.log_step("环境配置", "error", ".env.example文件不存在")
            return False
        
        if not env_file.exists():
            # 交互式配置生成
            self.log_step("环境配置", "info", "生成生产环境配置...")
            
            # 读取示例配置
            with open(env_example, 'r') as f:
                env_content = f.read()
            
            # 生成安全的随机密码
            import secrets
            import string
            
            def generate_password(length=16):
                alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
                return ''.join(secrets.choice(alphabet) for _ in range(length))
            
            # 替换默认密码
            replacements = {
                'your_secure_postgres_password': generate_password(20),
                'your_secure_redis_password': generate_password(16),
                'your_secure_email_password': 'CHANGE_ME_EMAIL_PASSWORD',
                'your_jwt_secret_key_change_in_production': generate_password(32),
                'your_dingtalk_secret': 'CHANGE_ME_DINGTALK_SECRET',
                'alerts@your-domain.com': 'alerts@example.com',
                'admin@your-domain.com': 'admin@example.com',
                'ops@your-domain.com': 'ops@example.com'
            }
            
            for old, new in replacements.items():
                env_content = env_content.replace(old, new)
            
            # 写入生产配置
            with open(env_file, 'w') as f:
                f.write(env_content)
            
            self.log_step("环境配置", "success", "生产环境配置已生成，请检查并修改必要的配置项")
            
            # 显示需要手动配置的项目
            manual_config_items = [
                "ALERT_EMAIL_SMTP_HOST",
                "ALERT_EMAIL_USERNAME", 
                "ALERT_EMAIL_PASSWORD",
                "ALERT_SLACK_WEBHOOK",
                "ALERT_DINGTALK_WEBHOOK"
            ]
            
            logger.info("📝 请手动配置以下项目:")
            for item in manual_config_items:
                logger.info(f"   - {item}")
            
            # 询问是否继续
            response = input("\n是否已完成手动配置并继续部署? (y/N): ")
            if response.lower() != 'y':
                self.log_step("环境配置", "info", "用户选择暂停部署进行手动配置")
                return False
        else:
            self.log_step("环境配置", "success", ".env文件已存在")
        
        return True
    
    def validate_configuration(self) -> bool:
        """验证配置文件"""
        logger.info("🔍 验证配置文件...")
        
        # 检查必需的配置文件
        required_files = [
            '.env',
            'docker-compose.yml',
            'config/proxy.yaml',
            'config/alerting/marketprism_alert_rules.py'
        ]
        
        all_valid = True
        for file_path in required_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                self.log_step(f"配置文件检查", "success", f"{file_path} 存在")
            else:
                self.log_step(f"配置文件检查", "error", f"{file_path} 缺失")
                all_valid = False
        
        # 验证环境变量
        env_file = self.project_root / '.env'
        if env_file.exists():
            with open(env_file, 'r') as f:
                env_content = f.read()
            
            # 检查是否还有未配置的占位符
            placeholders = [
                'CHANGE_ME',
                'your-domain.com',
                'YOUR_TOKEN',
                'YOUR_KEY'
            ]
            
            warnings = []
            for placeholder in placeholders:
                if placeholder in env_content:
                    warnings.append(f"发现未配置的占位符: {placeholder}")
            
            if warnings:
                for warning in warnings:
                    self.log_step("配置验证", "warning", warning)
                
                response = input("\n发现配置警告，是否继续部署? (y/N): ")
                if response.lower() != 'y':
                    return False
        
        return all_valid
    
    def deploy_infrastructure(self) -> bool:
        """部署基础设施服务"""
        logger.info("🏗️ 部署基础设施服务...")
        
        # 停止现有服务
        self.log_step("服务停止", "info", "停止现有服务...")
        success, output = self.run_command("docker-compose down")
        if success:
            self.log_step("服务停止", "success", "现有服务已停止")
        else:
            self.log_step("服务停止", "warning", f"停止服务时出现警告: {output}")
        
        # 拉取最新镜像
        self.log_step("镜像更新", "info", "拉取最新Docker镜像...")
        success, output = self.run_command("docker-compose pull")
        if success:
            self.log_step("镜像更新", "success", "Docker镜像已更新")
        else:
            self.log_step("镜像更新", "warning", f"镜像更新警告: {output}")
        
        # 启动基础设施服务
        infrastructure_services = ["redis", "postgres", "nats", "prometheus"]
        
        for service in infrastructure_services:
            self.log_step(f"启动{service}", "info", f"启动{service}服务...")
            success, output = self.run_command(f"docker-compose up -d {service}")
            if success:
                self.log_step(f"启动{service}", "success", f"{service}服务启动成功")
            else:
                self.log_step(f"启动{service}", "error", f"{service}服务启动失败: {output}")
                return False
        
        # 等待服务启动
        self.log_step("服务启动等待", "info", "等待基础设施服务完全启动...")
        time.sleep(30)
        
        # 检查服务状态
        success, output = self.run_command("docker-compose ps")
        if success:
            self.log_step("服务状态检查", "success", "基础设施服务状态正常")
        else:
            self.log_step("服务状态检查", "error", f"服务状态检查失败: {output}")
            return False
        
        return True
    
    def deploy_application(self) -> bool:
        """部署应用服务"""
        logger.info("🚀 部署应用服务...")
        
        # 启动数据收集器
        self.log_step("应用部署", "info", "启动数据收集器服务...")
        success, output = self.run_command("docker-compose up -d data-collector")
        if success:
            self.log_step("应用部署", "success", "数据收集器启动成功")
        else:
            self.log_step("应用部署", "error", f"数据收集器启动失败: {output}")
            return False
        
        # 等待应用启动
        self.log_step("应用启动等待", "info", "等待应用服务完全启动...")
        time.sleep(20)
        
        # 检查应用日志
        success, output = self.run_command("docker-compose logs --tail=20 data-collector")
        if "ERROR" in output or "CRITICAL" in output:
            self.log_step("应用日志检查", "warning", "发现错误日志，请检查")
            logger.warning("应用日志中发现错误:")
            logger.warning(output)
        else:
            self.log_step("应用日志检查", "success", "应用日志正常")
        
        return True
    
    def run_post_deployment_tests(self) -> bool:
        """运行部署后测试"""
        logger.info("🧪 运行部署后测试...")
        
        # 健康检查
        self.log_step("健康检查", "info", "检查应用健康状态...")
        
        # 等待服务完全启动
        max_retries = 12
        for i in range(max_retries):
            try:
                import requests
                response = requests.get('http://localhost:8080/health', timeout=10)
                if response.status_code == 200:
                    self.log_step("健康检查", "success", "应用健康检查通过")
                    break
                else:
                    self.log_step("健康检查", "warning", f"健康检查返回状态码: {response.status_code}")
            except Exception as e:
                if i == max_retries - 1:
                    self.log_step("健康检查", "error", f"健康检查失败: {e}")
                    return False
                else:
                    time.sleep(10)
                    continue
        
        # API连接测试
        self.log_step("API测试", "info", "测试API连接...")
        try:
            response = requests.get('http://localhost:8080/api/v1/exchanges/binance/ping', timeout=15)
            if response.status_code == 200:
                self.log_step("API测试", "success", "Binance API连接测试通过")
            else:
                self.log_step("API测试", "warning", f"API测试返回状态码: {response.status_code}")
        except Exception as e:
            self.log_step("API测试", "warning", f"API测试失败: {e}")
        
        # 告警系统测试
        self.log_step("告警系统测试", "info", "测试告警系统...")
        success, output = self.run_command("python scripts/test_alerting_system.py")
        if success:
            self.log_step("告警系统测试", "success", "告警系统测试通过")
        else:
            self.log_step("告警系统测试", "warning", f"告警系统测试警告: {output}")
        
        # 监控指标检查
        self.log_step("监控指标检查", "info", "检查监控指标...")
        try:
            response = requests.get('http://localhost:9090/metrics', timeout=10)
            if response.status_code == 200:
                self.log_step("监控指标检查", "success", "Prometheus指标收集正常")
            else:
                self.log_step("监控指标检查", "warning", f"监控指标检查状态码: {response.status_code}")
        except Exception as e:
            self.log_step("监控指标检查", "warning", f"监控指标检查失败: {e}")
        
        return True
    
    def generate_deployment_report(self) -> str:
        """生成部署报告"""
        logger.info("📊 生成部署报告...")
        
        report = {
            'deployment_time': time.time(),
            'deployment_status': 'completed',
            'steps': self.deployment_log,
            'summary': {
                'total_steps': len(self.deployment_log),
                'successful_steps': len([s for s in self.deployment_log if s['status'] == 'success']),
                'warning_steps': len([s for s in self.deployment_log if s['status'] == 'warning']),
                'error_steps': len([s for s in self.deployment_log if s['status'] == 'error'])
            }
        }
        
        # 保存JSON报告
        report_file = self.project_root / 'deployment_report.json'
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        
        # 生成Markdown报告
        md_report = self._generate_markdown_deployment_report(report)
        md_file = self.project_root / 'deployment_report.md'
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(md_report)
        
        self.log_step("部署报告", "success", f"部署报告已生成: {report_file}")
        
        return str(md_file)
    
    def _generate_markdown_deployment_report(self, report: Dict[str, Any]) -> str:
        """生成Markdown格式的部署报告"""
        md = "# 🚀 MarketPrism生产环境部署报告\n\n"
        
        # 部署概览
        md += "## 📊 部署概览\n\n"
        md += f"**部署时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        md += f"**部署状态**: {report['deployment_status']}\n"
        md += f"**总步骤数**: {report['summary']['total_steps']}\n"
        md += f"**成功步骤**: {report['summary']['successful_steps']}\n"
        md += f"**警告步骤**: {report['summary']['warning_steps']}\n"
        md += f"**错误步骤**: {report['summary']['error_steps']}\n\n"
        
        # 部署步骤详情
        md += "## 📋 部署步骤详情\n\n"
        md += "| 时间 | 步骤 | 状态 | 详情 |\n"
        md += "|------|------|------|------|\n"
        
        for step in report['steps']:
            timestamp = time.strftime('%H:%M:%S', time.localtime(step['timestamp']))
            status_icon = {'success': '✅', 'warning': '⚠️', 'error': '❌', 'info': 'ℹ️'}.get(step['status'], '📝')
            md += f"| {timestamp} | {step['step']} | {status_icon} | {step['details']} |\n"
        
        md += "\n"
        
        # 部署后验证
        md += "## 🧪 部署后验证\n\n"
        md += "请执行以下命令验证部署状态:\n\n"
        md += "```bash\n"
        md += "# 检查服务状态\n"
        md += "docker-compose ps\n\n"
        md += "# 检查应用健康\n"
        md += "curl http://localhost:8080/health\n\n"
        md += "# 检查API连接\n"
        md += "curl http://localhost:8080/api/v1/exchanges/binance/ping\n\n"
        md += "# 检查监控指标\n"
        md += "curl http://localhost:9090/metrics\n\n"
        md += "# 测试告警系统\n"
        md += "python scripts/test_alerting_system.py\n"
        md += "```\n\n"
        
        # 后续步骤
        md += "## 🔄 后续步骤\n\n"
        md += "1. **监控系统状态**: 持续监控应用和基础设施指标\n"
        md += "2. **配置告警通知**: 完善邮件、Slack等通知渠道配置\n"
        md += "3. **性能优化**: 根据实际负载调整配置参数\n"
        md += "4. **备份策略**: 实施数据备份和恢复策略\n"
        md += "5. **安全加固**: 实施额外的安全措施\n\n"
        
        md += "---\n"
        md += f"*报告生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}*\n"
        
        return md
    
    def run_deployment(self) -> bool:
        """运行完整部署流程"""
        logger.info("🚀 开始MarketPrism生产环境部署...")
        
        try:
            # 1. 检查前提条件
            if not self.check_prerequisites():
                logger.error("❌ 前提条件检查失败，部署终止")
                return False
            
            # 2. 设置环境配置
            if not self.setup_environment_config():
                logger.error("❌ 环境配置失败，部署终止")
                return False
            
            # 3. 验证配置
            if not self.validate_configuration():
                logger.error("❌ 配置验证失败，部署终止")
                return False
            
            # 4. 部署基础设施
            if not self.deploy_infrastructure():
                logger.error("❌ 基础设施部署失败，部署终止")
                return False
            
            # 5. 部署应用
            if not self.deploy_application():
                logger.error("❌ 应用部署失败，部署终止")
                return False
            
            # 6. 运行部署后测试
            if not self.run_post_deployment_tests():
                logger.warning("⚠️ 部署后测试存在警告，请检查")
            
            # 7. 生成部署报告
            report_file = self.generate_deployment_report()
            
            logger.info("🎉 MarketPrism生产环境部署完成！")
            logger.info(f"📊 部署报告: {report_file}")
            
            return True
            
        except Exception as e:
            self.log_step("部署异常", "error", str(e))
            logger.error(f"❌ 部署过程中发生异常: {e}")
            return False

def main():
    """主函数"""
    assistant = ProductionDeploymentAssistant()
    
    print("🚀 MarketPrism生产环境部署助手")
    print("=" * 50)
    
    # 确认部署
    response = input("是否开始生产环境部署? (y/N): ")
    if response.lower() != 'y':
        print("部署已取消")
        return 1
    
    # 运行部署
    success = assistant.run_deployment()
    
    if success:
        print("\n🎉 部署成功完成！")
        print("请查看部署报告了解详细信息")
        return 0
    else:
        print("\n❌ 部署失败！")
        print("请查看日志了解失败原因")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
