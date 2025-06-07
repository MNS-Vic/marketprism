"""
MarketPrism 增强的IP感知速率限制协调器

集成动态权重计算，完全体现Binance文档中的权重特性：
1. "每个请求都有一个特定的权重，它会添加到您的访问限制中"
2. "越消耗资源的接口, 比如查询多个交易对, 权重就会越大"
3. "每一个接口均有一个相应的权重(weight)，有的接口根据参数不同可能拥有不同的权重"
4. "连接到 WebSocket API 会用到2个权重"

增强特性：
- 自动计算每个请求的准确权重
- 支持参数相关的动态权重
- 智能批量操作权重计算
- 实时权重监控和预警
- 权重优化建议
"""

import asyncio
import time
import json
import uuid
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging

from .dynamic_weight_calculator import (
    DynamicWeightCalculator, 
    get_weight_calculator,
    calculate_request_weight,
    validate_request_parameters
)

from .ip_aware_rate_limit_coordinator import (
    ExchangeType,
    RequestType, 
    IPStatus,
    IPRateLimit,
    IPPoolConfig,
    IPManager
)

try:
    import aioredis
    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class SmartRequestInfo:
    """智能请求信息"""
    endpoint: str
    parameters: Dict[str, Any]
    calculated_weight: int
    base_weight: int
    weight_breakdown: Dict[str, Any]
    optimization_suggestions: List[str]
    timestamp: float = field(default_factory=time.time)


class EnhancedIPAwareRateLimitCoordinator:
    """增强的IP感知速率限制协调器，集成动态权重计算"""
    
    def __init__(self, storage, ip_config: IPPoolConfig):
        self.storage = storage
        self.ip_manager = IPManager(ip_config, storage)
        self.weight_calculator = get_weight_calculator()
        self.client_id = str(uuid.uuid4())
        
        # 增强的统计数据
        self.stats = {
            "total_requests": 0,
            "granted_requests": 0,
            "denied_requests": 0,
            "ip_switches": 0,
            "rate_limit_hits": 0,
            "ban_incidents": 0,
            "total_weight_consumed": 0,
            "average_request_weight": 0.0,
            "high_weight_requests": 0,  # 权重>10的请求
            "optimization_opportunities": 0  # 可优化的请求
        }
        
        # 请求历史（用于分析和优化）
        self.recent_requests: List[SmartRequestInfo] = []
        self.max_history_size = 1000
        
        logger.info(f"增强的IP感知速率限制协调器已初始化，客户端ID: {self.client_id}")
    
    async def acquire_smart_permit(
        self, 
        exchange: ExchangeType, 
        endpoint: str,
        parameters: Optional[Dict[str, Any]] = None,
        request_type: RequestType = RequestType.REST_API
    ) -> Dict[str, Any]:
        """
        获取智能API请求许可 - 自动计算准确权重
        
        这个方法完全体现了官方文档中的权重计算规则
        """
        self.stats["total_requests"] += 1
        parameters = parameters or {}
        
        # 1. 动态计算请求权重
        calculated_weight = self.weight_calculator.calculate_weight(
            exchange.value, 
            endpoint, 
            parameters, 
            request_type.value
        )
        
        # 2. 获取权重详细信息
        weight_rule = self.weight_calculator.get_weight_info(exchange.value, endpoint)
        base_weight = weight_rule.base_weight if weight_rule else 1
        
        # 3. 验证参数并获取优化建议
        validation = validate_request_parameters(exchange.value, endpoint, parameters)
        optimization_suggestions = validation.get("warnings", [])
        
        # 4. 创建请求信息记录
        request_info = SmartRequestInfo(
            endpoint=endpoint,
            parameters=parameters,
            calculated_weight=calculated_weight,
            base_weight=base_weight,
            weight_breakdown={
                "base_weight": base_weight,
                "parameter_additions": calculated_weight - base_weight,
                "total_weight": calculated_weight
            },
            optimization_suggestions=optimization_suggestions
        )
        
        # 5. 更新统计
        if calculated_weight > 10:
            self.stats["high_weight_requests"] += 1
        
        if optimization_suggestions:
            self.stats["optimization_opportunities"] += 1
        
        # 6. 检查IP是否可以承受这个权重
        can_request, ip, reason = await self.ip_manager.can_make_request(calculated_weight, exchange)
        
        if not can_request:
            self.stats["denied_requests"] += 1
            
            # 如果是因为权重超限，尝试IP轮换
            if "权重" in reason and self.ip_manager.config.auto_rotation:
                logger.info(f"当前IP {ip} 权重限制，尝试轮换 (需要权重: {calculated_weight})")
                await self.ip_manager._rotate_ip()
                self.stats["ip_switches"] += 1
                
                # 再次检查新IP
                can_request, ip, reason = await self.ip_manager.can_make_request(calculated_weight, exchange)
        
        if can_request:
            # 7. 消费请求权重
            is_order = request_type == RequestType.ORDER
            await self.ip_manager.consume_request(calculated_weight, is_order, ip)
            
            self.stats["granted_requests"] += 1
            self.stats["total_weight_consumed"] += calculated_weight
            self.stats["average_request_weight"] = (
                self.stats["total_weight_consumed"] / self.stats["granted_requests"]
            )
            
            # 8. 记录请求历史
            self._add_request_to_history(request_info)
            
            return {
                "granted": True,
                "ip_address": ip,
                "exchange": exchange.value,
                "endpoint": endpoint,
                "calculated_weight": calculated_weight,
                "weight_breakdown": request_info.weight_breakdown,
                "optimization_suggestions": optimization_suggestions,
                "request_type": request_type.value,
                "parameters": parameters,
                "reason": "Request permitted with calculated weight",
                "timestamp": time.time(),
                "client_id": self.client_id
            }
        else:
            self.stats["denied_requests"] += 1
            self.stats["rate_limit_hits"] += 1
            
            return {
                "granted": False,
                "ip_address": ip,
                "exchange": exchange.value,
                "endpoint": endpoint,
                "calculated_weight": calculated_weight,
                "weight_breakdown": request_info.weight_breakdown,
                "optimization_suggestions": optimization_suggestions,
                "request_type": request_type.value,
                "parameters": parameters,
                "reason": f"Rate limit exceeded: {reason}",
                "timestamp": time.time(),
                "client_id": self.client_id
            }
    
    async def batch_acquire_permits(
        self,
        requests: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        批量获取请求许可，支持智能权重分配
        
        Args:
            requests: 请求列表，每个包含 exchange, endpoint, parameters 等
        """
        results = []
        total_weight_needed = 0
        
        # 1. 预计算所有请求的权重
        for req in requests:
            exchange = ExchangeType(req.get("exchange", "binance"))
            endpoint = req.get("endpoint", "")
            parameters = req.get("parameters", {})
            
            weight = self.weight_calculator.calculate_weight(
                exchange.value, endpoint, parameters
            )
            req["calculated_weight"] = weight
            total_weight_needed += weight
        
        # 2. 检查总权重是否可行
        logger.info(f"批量请求总权重: {total_weight_needed}, 请求数量: {len(requests)}")
        
        # 3. 逐个处理请求
        for req in requests:
            result = await self.acquire_smart_permit(
                exchange=ExchangeType(req.get("exchange", "binance")),
                endpoint=req.get("endpoint", ""),
                parameters=req.get("parameters", {}),
                request_type=RequestType(req.get("request_type", "rest_api"))
            )
            results.append(result)
            
            # 如果某个请求失败，可以选择继续或停止
            if not result["granted"]:
                logger.warning(f"批量请求中的单个请求失败: {req.get('endpoint')}")
        
        return results
    
    async def get_weight_optimization_report(self) -> Dict[str, Any]:
        """生成权重优化报告"""
        if not self.recent_requests:
            return {"message": "暂无请求历史数据"}
        
        # 分析最近的请求
        high_weight_requests = [r for r in self.recent_requests if r.calculated_weight > 10]
        optimizable_requests = [r for r in self.recent_requests if r.optimization_suggestions]
        
        # 权重分布统计
        weight_distribution = {}
        for req in self.recent_requests:
            weight_range = self._get_weight_range(req.calculated_weight)
            weight_distribution[weight_range] = weight_distribution.get(weight_range, 0) + 1
        
        # 端点权重排名
        endpoint_weights = {}
        for req in self.recent_requests:
            endpoint = req.endpoint
            if endpoint not in endpoint_weights:
                endpoint_weights[endpoint] = {"total_weight": 0, "request_count": 0}
            endpoint_weights[endpoint]["total_weight"] += req.calculated_weight
            endpoint_weights[endpoint]["request_count"] += 1
        
        # 计算平均权重并排序
        for endpoint in endpoint_weights:
            data = endpoint_weights[endpoint]
            data["average_weight"] = data["total_weight"] / data["request_count"]
        
        sorted_endpoints = sorted(
            endpoint_weights.items(), 
            key=lambda x: x[1]["average_weight"], 
            reverse=True
        )
        
        # 生成优化建议
        optimization_tips = []
        
        if high_weight_requests:
            optimization_tips.append(
                f"发现 {len(high_weight_requests)} 个高权重请求(>10)，建议优化参数或分批处理"
            )
        
        if optimizable_requests:
            optimization_tips.append(
                f"发现 {len(optimizable_requests)} 个可优化请求，参考具体建议"
            )
        
        # 检查24hr ticker使用
        ticker_24hr_requests = [r for r in self.recent_requests if "/api/v3/ticker/24hr" in r.endpoint]
        no_symbol_requests = [r for r in ticker_24hr_requests if not r.parameters.get("symbol")]
        
        if no_symbol_requests:
            optimization_tips.append(
                f"发现 {len(no_symbol_requests)} 个24hr ticker请求未指定symbol，权重40->1的优化机会"
            )
        
        return {
            "summary": {
                "total_requests": len(self.recent_requests),
                "high_weight_requests": len(high_weight_requests),
                "optimizable_requests": len(optimizable_requests),
                "average_weight": sum(r.calculated_weight for r in self.recent_requests) / len(self.recent_requests)
            },
            "weight_distribution": weight_distribution,
            "top_heavy_endpoints": sorted_endpoints[:10],
            "optimization_opportunities": [
                {
                    "endpoint": req.endpoint,
                    "weight": req.calculated_weight,
                    "suggestions": req.optimization_suggestions,
                    "parameters": req.parameters
                }
                for req in optimizable_requests[:10]
            ],
            "optimization_tips": optimization_tips,
            "timestamp": time.time()
        }
    
    def _get_weight_range(self, weight: int) -> str:
        """获取权重范围标签"""
        if weight == 1:
            return "1 (标准)"
        elif weight <= 5:
            return "2-5 (低)"
        elif weight <= 10:
            return "6-10 (中等)"
        elif weight <= 50:
            return "11-50 (高)"
        else:
            return "50+ (很高)"
    
    def _add_request_to_history(self, request_info: SmartRequestInfo):
        """添加请求到历史记录"""
        self.recent_requests.append(request_info)
        
        # 保持历史记录大小限制
        if len(self.recent_requests) > self.max_history_size:
            self.recent_requests = self.recent_requests[-self.max_history_size:]
    
    async def simulate_request_weight(
        self, 
        exchange: str, 
        endpoint: str, 
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        模拟请求权重计算（不实际消费权重）
        """
        parameters = parameters or {}
        
        calculated_weight = self.weight_calculator.calculate_weight(
            exchange, endpoint, parameters
        )
        
        validation = validate_request_parameters(exchange, endpoint, parameters)
        weight_rule = self.weight_calculator.get_weight_info(exchange, endpoint)
        
        return {
            "endpoint": endpoint,
            "parameters": parameters,
            "calculated_weight": calculated_weight,
            "base_weight": weight_rule.base_weight if weight_rule else 1,
            "max_weight": weight_rule.max_weight if weight_rule else None,
            "validation": validation,
            "weight_breakdown": self._analyze_weight_components(
                exchange, endpoint, parameters, calculated_weight
            )
        }
    
    def _analyze_weight_components(
        self, 
        exchange: str, 
        endpoint: str, 
        parameters: Dict[str, Any], 
        total_weight: int
    ) -> Dict[str, Any]:
        """分析权重组成"""
        weight_rule = self.weight_calculator.get_weight_info(exchange, endpoint)
        if not weight_rule:
            return {"base_weight": total_weight, "parameter_additions": 0}
        
        base_weight = weight_rule.base_weight
        parameter_weight = total_weight - base_weight
        
        breakdown = {
            "base_weight": base_weight,
            "parameter_additions": parameter_weight,
            "total_weight": total_weight
        }
        
        # 分析具体参数贡献
        if parameter_weight > 0 and weight_rule.parameter_weights:
            parameter_contributions = {}
            for param_name, param_value in parameters.items():
                if param_name in weight_rule.parameter_weights:
                    param_rule = weight_rule.parameter_weights[param_name]
                    contribution = self.weight_calculator._calculate_parameter_weight(param_rule, param_value)
                    if contribution > 0:
                        parameter_contributions[param_name] = contribution
            
            breakdown["parameter_contributions"] = parameter_contributions
        
        return breakdown
    
    async def get_enhanced_system_status(self) -> Dict[str, Any]:
        """获取增强的系统状态，包含权重分析"""
        base_status = await self.ip_manager.get_ip_status_summary()
        
        # 添加权重相关统计
        weight_stats = {
            "total_weight_consumed": self.stats["total_weight_consumed"],
            "average_request_weight": self.stats["average_request_weight"],
            "high_weight_requests": self.stats["high_weight_requests"],
            "optimization_opportunities": self.stats["optimization_opportunities"]
        }
        
        # 当前权重利用率
        current_ip = base_status["current_ip"]
        if current_ip in base_status["ip_details"]:
            ip_detail = base_status["ip_details"][current_ip]
            weight_utilization = ip_detail.get("utilization_weight", 0)
            weight_stats["current_weight_utilization"] = weight_utilization
            weight_stats["weight_capacity_remaining"] = 1.0 - weight_utilization
        
        return {
            "coordinator_info": {
                "client_id": self.client_id,
                "mode": "enhanced_ip_aware_with_dynamic_weights",
                "statistics": self.stats.copy(),
                "weight_statistics": weight_stats
            },
            "ip_management": base_status,
            "weight_calculator_info": {
                "supported_exchanges": ["binance", "okx", "deribit"],
                "total_endpoints_configured": len(
                    self.weight_calculator.list_endpoints("binance") +
                    self.weight_calculator.list_endpoints("okx") +
                    self.weight_calculator.list_endpoints("deribit")
                )
            },
            "recent_activity": {
                "requests_in_history": len(self.recent_requests),
                "time_range": {
                    "oldest": min(r.timestamp for r in self.recent_requests) if self.recent_requests else None,
                    "newest": max(r.timestamp for r in self.recent_requests) if self.recent_requests else None
                }
            },
            "timestamp": time.time()
        }


# 工厂函数
async def create_enhanced_ip_coordinator(
    primary_ip: str,
    backup_ips: Optional[List[str]] = None,
    redis_host: str = "localhost",
    redis_port: int = 6379,
    redis_db: int = 3
) -> EnhancedIPAwareRateLimitCoordinator:
    """创建增强的IP感知速率限制协调器"""
    
    # 创建存储
    try:
        if REDIS_AVAILABLE:
            redis_client = aioredis.from_url(f"redis://{redis_host}:{redis_port}/{redis_db}")
            await redis_client.ping()
            from .distributed_rate_limit_coordinator import RedisDistributedStorage
            storage = RedisDistributedStorage(redis_client)
        else:
            from .distributed_rate_limit_coordinator import InMemoryDistributedStorage
            storage = InMemoryDistributedStorage()
    except Exception as e:
        logger.error(f"Redis连接失败: {e}, 使用内存存储")
        from .distributed_rate_limit_coordinator import InMemoryDistributedStorage
        storage = InMemoryDistributedStorage()
    
    # 创建IP配置
    ip_config = IPPoolConfig(
        primary_ip=primary_ip,
        backup_ips=backup_ips or [],
        auto_rotation=True
    )
    
    coordinator = EnhancedIPAwareRateLimitCoordinator(storage, ip_config)
    
    logger.info(f"增强IP感知协调器已创建，主IP: {primary_ip}, 支持动态权重计算")
    return coordinator


# 全局实例
_global_enhanced_coordinator: Optional[EnhancedIPAwareRateLimitCoordinator] = None


async def get_global_enhanced_coordinator() -> EnhancedIPAwareRateLimitCoordinator:
    """获取全局增强协调器"""
    global _global_enhanced_coordinator
    if _global_enhanced_coordinator is None:
        from .ip_aware_rate_limit_coordinator import get_external_ip
        current_ip = await get_external_ip()
        _global_enhanced_coordinator = await create_enhanced_ip_coordinator(current_ip)
    return _global_enhanced_coordinator


# 便利API函数
async def acquire_smart_api_permit(
    exchange: str, 
    endpoint: str,
    parameters: Optional[Dict[str, Any]] = None,
    request_type: str = "rest_api"
) -> Dict[str, Any]:
    """便利函数：获取智能API许可（自动权重计算）"""
    coordinator = await get_global_enhanced_coordinator()
    
    result = await coordinator.acquire_smart_permit(
        exchange=ExchangeType(exchange.lower()),
        endpoint=endpoint,
        parameters=parameters,
        request_type=RequestType(request_type.lower())
    )
    
    return result


async def get_weight_analysis() -> Dict[str, Any]:
    """便利函数：获取权重优化分析"""
    coordinator = await get_global_enhanced_coordinator()
    return await coordinator.get_weight_optimization_report()


if __name__ == "__main__":
    # 演示增强权重计算的使用
    async def demo_enhanced_weight_aware_rate_limiting():
        print("=== 增强的权重感知速率限制演示 ===\n")
        
        coordinator = await create_enhanced_ip_coordinator(
            primary_ip="192.168.1.100",
            backup_ips=["192.168.1.101"]
        )
        
        # 测试不同权重的请求
        test_requests = [
            {
                "name": "简单ping",
                "exchange": ExchangeType.BINANCE,
                "endpoint": "/api/v3/ping",
                "parameters": {}
            },
            {
                "name": "深度数据 (小limit)",
                "exchange": ExchangeType.BINANCE,
                "endpoint": "/api/v3/depth",
                "parameters": {"symbol": "BTCUSDT", "limit": 50}
            },
            {
                "name": "深度数据 (大limit)",
                "exchange": ExchangeType.BINANCE,
                "endpoint": "/api/v3/depth",
                "parameters": {"symbol": "BTCUSDT", "limit": 1000}
            },
            {
                "name": "24hr价格 (单个)",
                "exchange": ExchangeType.BINANCE,
                "endpoint": "/api/v3/ticker/24hr",
                "parameters": {"symbol": "BTCUSDT"}
            },
            {
                "name": "24hr价格 (所有)",
                "exchange": ExchangeType.BINANCE,
                "endpoint": "/api/v3/ticker/24hr",
                "parameters": {}
            },
            {
                "name": "24hr价格 (多个)",
                "exchange": ExchangeType.BINANCE,
                "endpoint": "/api/v3/ticker/24hr",
                "parameters": {"symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT"]}
            },
            {
                "name": "WebSocket连接",
                "exchange": ExchangeType.BINANCE,
                "endpoint": "websocket_connection",
                "parameters": {},
                "request_type": RequestType.WEBSOCKET
            }
        ]
        
        print("权重计算测试:")
        for i, req in enumerate(test_requests, 1):
            request_type = req.get("request_type", RequestType.REST_API)
            
            result = await coordinator.acquire_smart_permit(
                req["exchange"],
                req["endpoint"],
                req["parameters"],
                request_type
            )
            
            status = "✓" if result["granted"] else "✗"
            weight = result["calculated_weight"]
            suggestions = len(result["optimization_suggestions"])
            
            print(f"{i}. {req['name']}:")
            print(f"   状态: {status} | 权重: {weight} | 优化建议: {suggestions}个")
            print(f"   IP: {result['ip_address']}")
            
            if result["optimization_suggestions"]:
                print(f"   建议: {result['optimization_suggestions'][0]}")
            
            print()
        
        # 显示权重优化报告
        print("=== 权重优化报告 ===")
        report = await coordinator.get_weight_optimization_report()
        
        if "summary" in report:
            summary = report["summary"]
            print(f"总请求数: {summary['total_requests']}")
            print(f"高权重请求: {summary['high_weight_requests']}")
            print(f"可优化请求: {summary['optimizable_requests']}")
            print(f"平均权重: {summary['average_weight']:.2f}")
            
            if report["optimization_tips"]:
                print("\n优化建议:")
                for tip in report["optimization_tips"]:
                    print(f"  • {tip}")
        
        # 显示系统状态
        print("\n=== 系统状态 ===")
        status = await coordinator.get_enhanced_system_status()
        weight_stats = status["coordinator_info"]["weight_statistics"]
        
        print(f"总消费权重: {weight_stats['total_weight_consumed']}")
        print(f"平均请求权重: {weight_stats['average_request_weight']:.2f}")
        print(f"当前权重利用率: {weight_stats.get('current_weight_utilization', 0):.1%}")
        
        print("\n=== 演示完成 ===")
    
    # 运行演示
    asyncio.run(demo_enhanced_weight_aware_rate_limiting())