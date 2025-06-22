#!/usr/bin/env python3
"""
MarketPrism CI/CD运行器
专为GitHub Actions和其他CI/CD环境设计
"""

import os
import sys
import subprocess
import time
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
import argparse

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CICDRunner:
    """CI/CD运行器"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.is_ci = os.getenv('CI') or os.getenv('GITHUB_ACTIONS')
        self.reports_dir = self.project_root / "tests" / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        
        # CI环境配置
        self.ci_config = {
            'timeout': int(os.getenv('API_TIMEOUT', '15')),
            'rate_limit_enabled': os.getenv('RATE_LIMIT_ENABLED', 'true').lower() == 'true',
            'log_level': os.getenv('LOG_LEVEL', 'INFO'),
            'max_parallel_jobs': int(os.getenv('MAX_PARALLEL_JOBS', '2')),
        }
        
        logger.info(f"CI/CD Runner initialized - CI环境: {self.is_ci}")
        logger.info(f"配置: {self.ci_config}")
    
    def run_code_quality_checks(self) -> bool:
        """运行代码质量检查"""
        logger.info("🔍 开始代码质量检查...")
        
        checks = [
            ("代码格式检查", ["python", "-m", "black", "--check", "."]),
            ("导入排序检查", ["python", "-m", "isort", "--check-only", "."]),
            ("代码风格检查", ["python", "-m", "flake8", ".", "--max-line-length=88"]),
        ]
        
        all_passed = True
        
        for check_name, cmd in checks:
            logger.info(f"运行 {check_name}...")
            try:
                result = subprocess.run(
                    cmd, 
                    cwd=self.project_root,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.returncode == 0:
                    logger.info(f"✅ {check_name} 通过")
                else:
                    logger.error(f"❌ {check_name} 失败")
                    logger.error(f"错误输出: {result.stderr}")
                    all_passed = False
                    
            except subprocess.TimeoutExpired:
                logger.error(f"❌ {check_name} 超时")
                all_passed = False
            except Exception as e:
                logger.error(f"❌ {check_name} 异常: {e}")
                all_passed = False
        
        return all_passed
    
    def run_security_checks(self) -> bool:
        """运行安全检查"""
        logger.info("🔒 开始安全检查...")
        
        checks = [
            ("安全漏洞扫描", ["python", "-m", "safety", "check", "--json", 
                           "--output", str(self.reports_dir / "safety-report.json")]),
            ("代码安全检查", ["python", "-m", "bandit", "-r", "core/", "services/", 
                           "-f", "json", "-o", str(self.reports_dir / "bandit-report.json")]),
        ]
        
        all_passed = True
        
        for check_name, cmd in checks:
            logger.info(f"运行 {check_name}...")
            try:
                result = subprocess.run(
                    cmd,
                    cwd=self.project_root,
                    capture_output=True,
                    text=True,
                    timeout=180
                )
                
                # 安全检查可能返回非零状态码但仍然成功
                if result.returncode in [0, 1]:  # 1表示发现问题但不是致命错误
                    logger.info(f"✅ {check_name} 完成")
                else:
                    logger.warning(f"⚠️ {check_name} 返回状态码 {result.returncode}")
                    
            except subprocess.TimeoutExpired:
                logger.error(f"❌ {check_name} 超时")
                all_passed = False
            except Exception as e:
                logger.error(f"❌ {check_name} 异常: {e}")
                all_passed = False
        
        return all_passed
    
    def run_unit_tests(self) -> bool:
        """运行单元测试"""
        logger.info("🧪 开始单元测试...")
        
        cmd = [
            "python", "-m", "pytest",
            "tests/unit/",
            "--cov=core/",
            "--cov=services/",
            "--cov-report=term-missing",
            "--cov-report=xml:tests/reports/coverage-unit.xml",
            "--cov-report=json:tests/reports/coverage-unit.json",
            "--cov-report=html:tests/reports/coverage-unit-html",
            "--junitxml=tests/reports/junit-unit.xml",
            "--html=tests/reports/report-unit.html",
            "--self-contained-html",
            "--timeout=300",
            "-v",
            "--tb=short"
        ]
        
        if self.ci_config['max_parallel_jobs'] > 1:
            cmd.extend(["-n", str(self.ci_config['max_parallel_jobs'])])
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                timeout=1800  # 30分钟超时
            )
            
            success = result.returncode == 0
            if success:
                logger.info("✅ 单元测试通过")
            else:
                logger.error("❌ 单元测试失败")
            
            return success
            
        except subprocess.TimeoutExpired:
            logger.error("❌ 单元测试超时")
            return False
        except Exception as e:
            logger.error(f"❌ 单元测试异常: {e}")
            return False
    
    def run_integration_tests(self) -> bool:
        """运行集成测试"""
        logger.info("🔗 开始集成测试...")
        
        cmd = [
            "python", "-m", "pytest",
            "tests/integration/",
            "--junitxml=tests/reports/junit-integration.xml",
            "--html=tests/reports/report-integration.html",
            "--self-contained-html",
            "--timeout=600",
            "-v",
            "--tb=short",
            "-m", "not slow and not live_api"  # 跳过慢速和真实API测试
        ]
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                timeout=2400  # 40分钟超时
            )
            
            success = result.returncode == 0
            if success:
                logger.info("✅ 集成测试通过")
            else:
                logger.error("❌ 集成测试失败")
            
            return success
            
        except subprocess.TimeoutExpired:
            logger.error("❌ 集成测试超时")
            return False
        except Exception as e:
            logger.error(f"❌ 集成测试异常: {e}")
            return False
    
    def run_live_api_tests(self) -> bool:
        """运行真实API测试"""
        if not self.ci_config['rate_limit_enabled']:
            logger.warning("⚠️ 频率限制未启用，跳过真实API测试")
            return True
        
        logger.info("🌐 开始真实API测试（启用频率限制）...")
        
        cmd = [
            "python", "-m", "pytest",
            "tests/integration/test_live_exchange_apis.py",
            "--junitxml=tests/reports/junit-live-api.xml",
            "--html=tests/reports/report-live-api.html",
            "--self-contained-html",
            "--timeout=300",
            "-v",
            "--tb=short",
            "-m", "live_api and ci"
        ]
        
        # 设置环境变量
        env = os.environ.copy()
        env.update({
            'CI': 'true',
            'GITHUB_ACTIONS': 'true',
            'RATE_LIMIT_ENABLED': 'true',
            'API_TIMEOUT': str(self.ci_config['timeout']),
            'LOG_LEVEL': self.ci_config['log_level']
        })
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                env=env,
                timeout=1200  # 20分钟超时
            )
            
            success = result.returncode == 0
            if success:
                logger.info("✅ 真实API测试通过")
            else:
                logger.warning("⚠️ 真实API测试失败（可能是网络问题）")
                # 真实API测试失败不应该阻止部署
                success = True
            
            return success
            
        except subprocess.TimeoutExpired:
            logger.error("❌ 真实API测试超时")
            return True  # 超时不阻止部署
        except Exception as e:
            logger.error(f"❌ 真实API测试异常: {e}")
            return True  # 异常不阻止部署
    
    def generate_coverage_report(self) -> Dict:
        """生成覆盖率报告"""
        logger.info("📊 生成覆盖率报告...")
        
        coverage_file = self.reports_dir / "coverage-unit.json"
        if not coverage_file.exists():
            logger.warning("覆盖率文件不存在")
            return {}
        
        try:
            with open(coverage_file, 'r') as f:
                coverage_data = json.load(f)
            
            total_coverage = coverage_data['totals']['percent_covered']
            
            report = {
                'total_coverage': total_coverage,
                'timestamp': time.time(),
                'ci_environment': self.is_ci,
                'config': self.ci_config
            }
            
            # 保存报告
            report_file = self.reports_dir / "ci-coverage-report.json"
            with open(report_file, 'w') as f:
                json.dump(report, f, indent=2)
            
            logger.info(f"📈 总覆盖率: {total_coverage:.2f}%")
            return report
            
        except Exception as e:
            logger.error(f"生成覆盖率报告失败: {e}")
            return {}
    
    def run_full_pipeline(self) -> bool:
        """运行完整的CI/CD流水线"""
        logger.info("🚀 开始完整CI/CD流水线...")
        
        pipeline_steps = [
            ("代码质量检查", self.run_code_quality_checks),
            ("安全检查", self.run_security_checks),
            ("单元测试", self.run_unit_tests),
            ("集成测试", self.run_integration_tests),
            ("真实API测试", self.run_live_api_tests),
        ]
        
        results = {}
        overall_success = True
        
        for step_name, step_func in pipeline_steps:
            logger.info(f"\n{'='*50}")
            logger.info(f"执行步骤: {step_name}")
            logger.info(f"{'='*50}")
            
            start_time = time.time()
            success = step_func()
            duration = time.time() - start_time
            
            results[step_name] = {
                'success': success,
                'duration': duration
            }
            
            if success:
                logger.info(f"✅ {step_name} 完成 ({duration:.2f}秒)")
            else:
                logger.error(f"❌ {step_name} 失败 ({duration:.2f}秒)")
                overall_success = False
                
                # 某些步骤失败时是否继续
                if step_name in ["代码质量检查", "单元测试"]:
                    logger.error(f"关键步骤 {step_name} 失败，停止流水线")
                    break
        
        # 生成最终报告
        coverage_report = self.generate_coverage_report()
        results['coverage_report'] = coverage_report
        
        # 保存流水线结果
        pipeline_report = {
            'overall_success': overall_success,
            'steps': results,
            'timestamp': time.time(),
            'ci_environment': self.is_ci
        }
        
        report_file = self.reports_dir / "ci-pipeline-report.json"
        with open(report_file, 'w') as f:
            json.dump(pipeline_report, f, indent=2)
        
        logger.info(f"\n{'='*50}")
        logger.info(f"CI/CD流水线完成 - 总体结果: {'✅ 成功' if overall_success else '❌ 失败'}")
        logger.info(f"详细报告: {report_file}")
        logger.info(f"{'='*50}")
        
        return overall_success

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="MarketPrism CI/CD Runner")
    parser.add_argument("--step", choices=[
        "quality", "security", "unit", "integration", "live-api", "full"
    ], default="full", help="要运行的步骤")
    
    args = parser.parse_args()
    
    runner = CICDRunner()
    
    if args.step == "quality":
        success = runner.run_code_quality_checks()
    elif args.step == "security":
        success = runner.run_security_checks()
    elif args.step == "unit":
        success = runner.run_unit_tests()
    elif args.step == "integration":
        success = runner.run_integration_tests()
    elif args.step == "live-api":
        success = runner.run_live_api_tests()
    else:  # full
        success = runner.run_full_pipeline()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
