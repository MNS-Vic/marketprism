"""
IP级别速率限制演示

完全体现交易所文档中的IP限制特性：
1. Binance: "访问限制是基于IP的，而不是API Key"
2. OKX: "公共未经身份验证的 REST 限速基于 IP 地址"

这个演示展示：
- 同一IP下多个服务共享速率限制
- IP级别的权重计算和管理
- 429/418响应的处理
- 自动IP轮换机制
"""

import asyncio
import aiohttp
import time
import json
from typing import Dict, Any, List
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from core.reliability.ip_aware_rate_limit_coordinator import (
        IPAwareRateLimitCoordinator,
        ExchangeType,
        RequestType,
        create_ip_aware_coordinator,
        IPPoolConfig
    )
except ImportError as e:
    logger.error(f"导入错误: {e}")
    logger.error("请确保在MarketPrism项目根目录下运行此脚本")
    sys.exit(1)


class BinanceIPRateLimitDemo:
    """Binance IP级别速率限制演示"""
    
    def __init__(self):
        self.coordinator = None
        self.session = None
        
        # 模拟的IP池（实际使用中这些应该是真实的不同IP）
        self.ip_pool = [
            "203.0.113.1",    # 主IP
            "203.0.113.2",    # 备用IP1
            "203.0.113.3"     # 备用IP2
        ]
    
    async def initialize(self):
        """初始化演示环境"""
        logger.info("初始化IP感知速率限制演示...")
        
        # 创建IP感知协调器
        self.coordinator = await create_ip_aware_coordinator(
            primary_ip=self.ip_pool[0],
            backup_ips=self.ip_pool[1:],
            redis_db=4  # 使用独立的Redis数据库
        )
        
        # 创建HTTP会话
        self.session = aiohttp.ClientSession()
        
        logger.info(f"协调器已初始化，IP池: {self.ip_pool}")
    
    async def simulate_binance_request(self, endpoint: str, weight: int = 1, request_type: RequestType = RequestType.REST_PUBLIC) -> Dict[str, Any]:
        """
        模拟Binance API请求，体现IP级别的限制检查
        """
        # 1. 首先检查IP级别的速率限制
        permit_result = await self.coordinator.acquire_permit(
            exchange=ExchangeType.BINANCE,
            request_type=request_type,
            weight=weight,
            endpoint=endpoint
        )
        
        if not permit_result["granted"]:
            return {
                "success": False,
                "reason": permit_result["reason"],
                "ip": permit_result["ip_address"],
                "blocked_by_ip_limit": True
            }
        
        # 2. 模拟实际的HTTP请求（这里只是模拟，不发送真实请求）
        current_ip = permit_result["ip_address"]
        
        # 模拟网络延迟
        await asyncio.sleep(0.1)
        
        # 3. 模拟交易所响应
        simulated_response = await self._simulate_exchange_response(endpoint, weight)
        
        # 4. 将响应状态反馈给协调器，更新IP状态
        await self.coordinator.report_exchange_response(
            status_code=simulated_response["status_code"],
            headers=simulated_response["headers"],
            ip=current_ip
        )
        
        return {
            "success": simulated_response["status_code"] == 200,
            "status_code": simulated_response["status_code"],
            "ip": current_ip,
            "weight": weight,
            "endpoint": endpoint,
            "headers": simulated_response["headers"],
            "blocked_by_ip_limit": False
        }
    
    async def _simulate_exchange_response(self, endpoint: str, weight: int) -> Dict[str, Any]:
        """模拟交易所响应，包括速率限制相关的头部"""
        
        # 获取当前IP状态
        status = await self.coordinator.get_system_status()
        current_ip = status["current_ip"]
        ip_details = status["ip_management"]["ip_details"].get(current_ip, {})
        
        current_weight = ip_details.get("current_weight", 0)
        current_requests = ip_details.get("current_requests", 0)
        
        # 模拟不同的响应场景
        if current_weight > 5000:  # 接近Binance的6000权重限制
            # 模拟429响应
            return {
                "status_code": 429,
                "headers": {
                    "X-MBX-USED-WEIGHT-1M": str(current_weight),
                    "Retry-After": "60"
                }
            }
        elif current_weight > 5500:  # 超过限制，可能导致IP封禁
            # 模拟418响应
            return {
                "status_code": 418,
                "headers": {
                    "X-MBX-USED-WEIGHT-1M": str(current_weight),
                    "Retry-After": "3600"  # 1小时封禁
                }
            }
        else:
            # 正常响应
            return {
                "status_code": 200,
                "headers": {
                    "X-MBX-USED-WEIGHT-1M": str(current_weight + weight),
                    "X-MBX-ORDER-COUNT-10S": str(current_requests)
                }
            }
    
    async def run_multi_service_simulation(self):
        """
        模拟多个MarketPrism服务在同一IP下发送请求
        体现"访问限制是基于IP的，而不是API Key"
        """
        logger.info("\n=== 多服务同IP限制演示 ===")
        
        # 定义不同的服务和它们的请求模式
        services = [
            {
                "name": "数据采集器",
                "endpoints": ["/api/v3/ticker/24hr", "/api/v3/depth"],
                "weights": [1, 5],
                "requests_per_minute": 60
            },
            {
                "name": "交易执行器", 
                "endpoints": ["/api/v3/order", "/api/v3/account"],
                "weights": [1, 10],
                "requests_per_minute": 30
            },
            {
                "name": "监控服务",
                "endpoints": ["/api/v3/exchangeInfo", "/api/v3/time"],
                "weights": [10, 1],
                "requests_per_minute": 20
            }
        ]
        
        # 并发运行多个服务
        tasks = []
        for service in services:
            task = asyncio.create_task(
                self._simulate_service_requests(service)
            )
            tasks.append(task)
        
        # 同时启动监控任务
        monitor_task = asyncio.create_task(self._monitor_ip_status())
        tasks.append(monitor_task)
        
        # 运行2分钟的模拟
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=120)
        except asyncio.TimeoutError:
            logger.info("演示时间结束")
        
        # 取消所有任务
        for task in tasks:
            task.cancel()
        
        # 显示最终统计
        await self._show_final_statistics()
    
    async def _simulate_service_requests(self, service_config: Dict[str, Any]):
        """模拟单个服务的请求模式"""
        service_name = service_config["name"]
        endpoints = service_config["endpoints"]
        weights = service_config["weights"]
        rpm = service_config["requests_per_minute"]
        
        interval = 60 / rpm  # 计算请求间隔
        
        logger.info(f"启动服务: {service_name} (每分钟{rpm}个请求)")
        
        request_count = 0
        
        while True:
            try:
                # 随机选择端点和权重
                import random
                endpoint = random.choice(endpoints)
                weight = weights[endpoints.index(endpoint)]
                
                # 发送请求
                result = await self.simulate_binance_request(endpoint, weight)
                request_count += 1
                
                status_emoji = "✓" if result["success"] else "✗"
                logger.info(f"{service_name} 请求#{request_count}: {status_emoji} {endpoint} (权重:{weight}) IP:{result.get('ip', 'N/A')}")
                
                if not result["success"]:
                    logger.warning(f"  失败原因: {result.get('reason', 'Unknown')}")
                
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                logger.info(f"服务 {service_name} 已停止，总请求数: {request_count}")
                break
            except Exception as e:
                logger.error(f"服务 {service_name} 出错: {e}")
                await asyncio.sleep(1)
    
    async def _monitor_ip_status(self):
        """监控IP状态变化"""
        logger.info("启动IP状态监控...")
        
        last_ip = None
        
        while True:
            try:
                status = await self.coordinator.get_system_status()
                current_ip = status["current_ip"]
                ip_availability = status["ip_availability"]
                stats = status["coordinator_info"]["statistics"]
                
                # 检查IP是否发生切换
                if last_ip != current_ip:
                    logger.info(f"🔄 IP切换: {last_ip} -> {current_ip}")
                    last_ip = current_ip
                
                # 每30秒显示一次详细状态
                if int(time.time()) % 30 == 0:
                    logger.info(f"\n📊 IP状态监控:")
                    logger.info(f"  当前IP: {current_ip}")
                    logger.info(f"  IP可用性: 活跃={ip_availability['active']}, 被封={ip_availability['banned']}, 警告={ip_availability['warnings']}")
                    logger.info(f"  请求统计: 总数={stats['total_requests']}, 成功={stats['granted_requests']}, 拒绝={stats['denied_requests']}")
                    logger.info(f"  IP切换次数: {stats['ip_switches']}, 限制命中: {stats['rate_limit_hits']}")
                
                await asyncio.sleep(5)  # 每5秒检查一次
                
            except asyncio.CancelledError:
                logger.info("IP状态监控已停止")
                break
            except Exception as e:
                logger.error(f"监控出错: {e}")
                await asyncio.sleep(5)
    
    async def _show_final_statistics(self):
        """显示最终统计信息"""
        logger.info("\n=== 最终统计报告 ===")
        
        status = await self.coordinator.get_system_status()
        
        # 总体统计
        stats = status["coordinator_info"]["statistics"]
        logger.info(f"总请求数: {stats['total_requests']}")
        logger.info(f"成功请求: {stats['granted_requests']}")
        logger.info(f"拒绝请求: {stats['denied_requests']}")
        logger.info(f"成功率: {stats['granted_requests']/max(stats['total_requests'],1)*100:.1f}%")
        logger.info(f"IP切换次数: {stats['ip_switches']}")
        logger.info(f"速率限制命中: {stats['rate_limit_hits']}")
        logger.info(f"封禁事件: {stats['ban_incidents']}")
        
        # IP详细状态
        logger.info("\n📍 各IP详细状态:")
        ip_details = status["ip_management"]["ip_details"]
        for ip, details in ip_details.items():
            logger.info(f"  {ip}:")
            logger.info(f"    状态: {details['status']}")
            logger.info(f"    请求使用: {details['current_requests']}/{details['max_requests']} ({details['utilization_requests']*100:.1f}%)")
            logger.info(f"    权重使用: {details['current_weight']}/{details['max_weight']} ({details['utilization_weight']*100:.1f}%)")
            logger.info(f"    警告次数: {details['warning_count']}")
            
            if details.get('ban_remaining', 0) > 0:
                logger.info(f"    封禁剩余: {details['ban_remaining']:.1f}秒")
    
    async def cleanup(self):
        """清理资源"""
        if self.session:
            await self.session.close()
        logger.info("资源清理完成")


async def main():
    """主函数：运行IP级别速率限制演示"""
    demo = BinanceIPRateLimitDemo()
    
    try:
        # 初始化
        await demo.initialize()
        
        # 运行演示
        await demo.run_multi_service_simulation()
        
    except KeyboardInterrupt:
        logger.info("用户中断演示")
    except Exception as e:
        logger.error(f"演示出错: {e}")
    finally:
        await demo.cleanup()


if __name__ == "__main__":
    print("""
    =================================================================
    MarketPrism IP级别速率限制演示
    =================================================================
    
    本演示完全体现交易所文档中的核心特性：
    
    1. Binance: "访问限制是基于IP的，而不是API Key"
    2. OKX: "公共未经身份验证的 REST 限速基于 IP 地址"
    
    演示内容：
    ✓ 同一IP下多个服务共享速率限制
    ✓ IP级别的权重计算和监控
    ✓ 429/418响应的自动处理
    ✓ 智能IP轮换机制
    ✓ 实时IP状态监控
    
    按 Ctrl+C 可随时停止演示
    =================================================================
    """)
    
    asyncio.run(main())