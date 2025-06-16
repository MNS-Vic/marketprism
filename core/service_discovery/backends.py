"""
服务发现后端实现
支持Consul、etcd、NATS、Redis等多种后端
"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Any
import logging

from .registry import ServiceRegistryBackend, ServiceInstance, ServiceStatus

logger = logging.getLogger(__name__)


class ConsulBackend(ServiceRegistryBackend):
    """Consul服务发现后端"""
    
    def __init__(self, consul_url: str = "http://localhost:8500"):
        self.consul_url = consul_url.rstrip('/')
        self.session: Optional[Any] = None
    
    async def __aenter__(self):
        import aiohttp
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def register(self, instance: ServiceInstance) -> bool:
        """注册服务到Consul"""
        try:
            service_data = {
                "ID": instance.instance_id,
                "Name": instance.service_name,
                "Tags": instance.tags,
                "Address": instance.host,
                "Port": instance.port,
                "Meta": instance.metadata,
                "Check": {
                    "HTTP": instance.health_check_url,
                    "Interval": "30s",
                    "Timeout": "10s"
                }
            }
            
            url = f"{self.consul_url}/v1/agent/service/register"
            async with self.session.put(url, json=service_data) as response:
                success = response.status == 200
                if success:
                    logger.info(f"Consul服务注册成功: {instance.service_name}#{instance.instance_id}")
                else:
                    logger.error(f"Consul服务注册失败: {response.status}")
                return success
                
        except Exception as e:
            logger.error(f"Consul注册服务失败: {e}")
            return False
    
    async def deregister(self, service_name: str, instance_id: str) -> bool:
        """从Consul注销服务"""
        try:
            url = f"{self.consul_url}/v1/agent/service/deregister/{instance_id}"
            async with self.session.put(url) as response:
                success = response.status == 200
                if success:
                    logger.info(f"Consul服务注销成功: {service_name}#{instance_id}")
                else:
                    logger.error(f"Consul服务注销失败: {response.status}")
                return success
                
        except Exception as e:
            logger.error(f"Consul注销服务失败: {e}")
            return False
    
    async def discover(self, service_name: str) -> List[ServiceInstance]:
        """从Consul发现服务"""
        try:
            url = f"{self.consul_url}/v1/health/service/{service_name}?passing=true"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    instances = []
                    
                    for item in data:
                        service = item['Service']
                        instance = ServiceInstance(
                            service_name=service['Service'],
                            instance_id=service['ID'],
                            host=service['Address'],
                            port=service['Port'],
                            status=ServiceStatus.HEALTHY,
                            metadata=service.get('Meta', {}),
                            tags=service.get('Tags', [])
                        )
                        instances.append(instance)
                    
                    return instances
                else:
                    logger.error(f"Consul发现服务失败: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Consul发现服务失败: {e}")
            return []
    
    async def list_all(self) -> Dict[str, List[ServiceInstance]]:
        """列出所有服务"""
        try:
            url = f"{self.consul_url}/v1/catalog/services"
            async with self.session.get(url) as response:
                if response.status == 200:
                    services_data = await response.json()
                    all_services = {}
                    
                    for service_name in services_data.keys():
                        instances = await self.discover(service_name)
                        if instances:
                            all_services[service_name] = instances
                    
                    return all_services
                else:
                    return {}
                    
        except Exception as e:
            logger.error(f"Consul列出所有服务失败: {e}")
            return {}
    
    async def update_status(self, service_name: str, instance_id: str, status: ServiceStatus) -> bool:
        """更新服务状态"""
        # Consul通过健康检查自动更新状态
        return True


class EtcdBackend(ServiceRegistryBackend):
    """etcd服务发现后端"""
    
    def __init__(self, etcd_url: str = "http://localhost:2379"):
        self.etcd_url = etcd_url.rstrip('/')
        self.session: Optional[Any] = None
        self.key_prefix = "/marketprism/services"
    
    async def __aenter__(self):
        import aiohttp
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def register(self, instance: ServiceInstance) -> bool:
        """注册服务到etcd"""
        try:
            key = f"{self.key_prefix}/{instance.service_name}/{instance.instance_id}"
            value = json.dumps(instance.to_dict())
            
            # 使用etcd v3 API
            url = f"{self.etcd_url}/v3/kv/put"
            data = {
                "key": self._encode_base64(key),
                "value": self._encode_base64(value)
            }
            
            async with self.session.post(url, json=data) as response:
                success = response.status == 200
                if success:
                    logger.info(f"etcd服务注册成功: {instance.service_name}#{instance.instance_id}")
                else:
                    logger.error(f"etcd服务注册失败: {response.status}")
                return success
                
        except Exception as e:
            logger.error(f"etcd注册服务失败: {e}")
            return False
    
    async def deregister(self, service_name: str, instance_id: str) -> bool:
        """从etcd注销服务"""
        try:
            key = f"{self.key_prefix}/{service_name}/{instance_id}"
            url = f"{self.etcd_url}/v3/kv/deleterange"
            data = {"key": self._encode_base64(key)}
            
            async with self.session.post(url, json=data) as response:
                success = response.status == 200
                if success:
                    logger.info(f"etcd服务注销成功: {service_name}#{instance_id}")
                else:
                    logger.error(f"etcd服务注销失败: {response.status}")
                return success
                
        except Exception as e:
            logger.error(f"etcd注销服务失败: {e}")
            return False
    
    async def discover(self, service_name: str) -> List[ServiceInstance]:
        """从etcd发现服务"""
        try:
            key_prefix = f"{self.key_prefix}/{service_name}/"
            range_end = key_prefix + "z"
            
            url = f"{self.etcd_url}/v3/kv/range"
            data = {
                "key": self._encode_base64(key_prefix),
                "range_end": self._encode_base64(range_end)
            }
            
            async with self.session.post(url, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    instances = []
                    
                    for kv in result.get('kvs', []):
                        value = self._decode_base64(kv['value'])
                        data = json.loads(value)
                        instance = ServiceInstance.from_dict(data)
                        instances.append(instance)
                    
                    return instances
                else:
                    logger.error(f"etcd发现服务失败: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"etcd发现服务失败: {e}")
            return []
    
    async def list_all(self) -> Dict[str, List[ServiceInstance]]:
        """列出所有服务"""
        try:
            url = f"{self.etcd_url}/v3/kv/range"
            data = {
                "key": self._encode_base64(self.key_prefix + "/"),
                "range_end": self._encode_base64(self.key_prefix + "/z")
            }
            
            async with self.session.post(url, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    all_services = {}
                    
                    for kv in result.get('kvs', []):
                        value = self._decode_base64(kv['value'])
                        data = json.loads(value)
                        instance = ServiceInstance.from_dict(data)
                        
                        if instance.service_name not in all_services:
                            all_services[instance.service_name] = []
                        all_services[instance.service_name].append(instance)
                    
                    return all_services
                else:
                    return {}
                    
        except Exception as e:
            logger.error(f"etcd列出所有服务失败: {e}")
            return {}
    
    async def update_status(self, service_name: str, instance_id: str, status: ServiceStatus) -> bool:
        """更新服务状态"""
        # 重新注册实例以更新状态
        try:
            key = f"{self.key_prefix}/{service_name}/{instance_id}"
            url = f"{self.etcd_url}/v3/kv/range"
            data = {"key": self._encode_base64(key)}
            
            async with self.session.post(url, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get('kvs'):
                        value = self._decode_base64(result['kvs'][0]['value'])
                        instance_data = json.loads(value)
                        instance = ServiceInstance.from_dict(instance_data)
                        instance.status = status
                        instance.update_heartbeat()
                        
                        return await self.register(instance)
            
            return False
            
        except Exception as e:
            logger.error(f"etcd更新服务状态失败: {e}")
            return False
    
    def _encode_base64(self, text: str) -> str:
        """Base64编码"""
        import base64
        return base64.b64encode(text.encode()).decode()
    
    def _decode_base64(self, text: str) -> str:
        """Base64解码"""
        import base64
        return base64.b64decode(text.encode()).decode()


class NATSBackend(ServiceRegistryBackend):
    """NATS服务发现后端"""
    
    def __init__(self, nats_url: str = "nats://localhost:4222"):
        self.nats_url = nats_url
        self.nc = None
        self.js = None
        self.services: Dict[str, List[ServiceInstance]] = {}
        self.subject_prefix = "marketprism.services"
    
    async def __aenter__(self):
        try:
            import nats
            from nats.js import JetStreamContext
            
            self.nc = await nats.connect(self.nats_url)
            self.js = self.nc.jetstream()
            
            # 创建服务发现流
            try:
                await self.js.add_stream(
                    name="SERVICES",
                    subjects=[f"{self.subject_prefix}.>"],
                    retention="limits",
                    max_age=3600  # 1小时
                )
            except Exception:
                pass  # 流可能已存在
            
            return self
        except ImportError:
            logger.error("NATS客户端未安装，请运行: pip install nats-py")
            raise
        except Exception as e:
            logger.error(f"连接NATS失败: {e}")
            raise
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.nc:
            await self.nc.close()
    
    async def register(self, instance: ServiceInstance) -> bool:
        """注册服务到NATS"""
        try:
            subject = f"{self.subject_prefix}.{instance.service_name}.{instance.instance_id}"
            data = json.dumps(instance.to_dict()).encode()
            
            await self.js.publish(subject, data)
            
            # 本地缓存
            if instance.service_name not in self.services:
                self.services[instance.service_name] = []
            
            # 更新或添加实例
            existing_index = None
            for i, existing_instance in enumerate(self.services[instance.service_name]):
                if existing_instance.instance_id == instance.instance_id:
                    existing_index = i
                    break
            
            if existing_index is not None:
                self.services[instance.service_name][existing_index] = instance
            else:
                self.services[instance.service_name].append(instance)
            
            logger.info(f"NATS服务注册成功: {instance.service_name}#{instance.instance_id}")
            return True
            
        except Exception as e:
            logger.error(f"NATS注册服务失败: {e}")
            return False
    
    async def deregister(self, service_name: str, instance_id: str) -> bool:
        """从NATS注销服务"""
        try:
            # 发送注销消息
            subject = f"{self.subject_prefix}.{service_name}.{instance_id}.deregister"
            await self.js.publish(subject, b"deregister")
            
            # 从本地缓存移除
            if service_name in self.services:
                self.services[service_name] = [
                    inst for inst in self.services[service_name]
                    if inst.instance_id != instance_id
                ]
                if not self.services[service_name]:
                    del self.services[service_name]
            
            logger.info(f"NATS服务注销成功: {service_name}#{instance_id}")
            return True
            
        except Exception as e:
            logger.error(f"NATS注销服务失败: {e}")
            return False
    
    async def discover(self, service_name: str) -> List[ServiceInstance]:
        """从NATS发现服务"""
        return self.services.get(service_name, [])
    
    async def list_all(self) -> Dict[str, List[ServiceInstance]]:
        """列出所有服务"""
        return self.services.copy()
    
    async def update_status(self, service_name: str, instance_id: str, status: ServiceStatus) -> bool:
        """更新服务状态"""
        if service_name in self.services:
            for instance in self.services[service_name]:
                if instance.instance_id == instance_id:
                    instance.status = status
                    instance.update_heartbeat()
                    # 重新发布更新
                    return await self.register(instance)
        return False


class RedisBackend(ServiceRegistryBackend):
    """Redis服务发现后端"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis = None
        self.key_prefix = "marketprism:services"
    
    async def __aenter__(self):
        try:
            import aioredis
            self.redis = await aioredis.from_url(self.redis_url)
            return self
        except ImportError:
            logger.error("Redis客户端未安装，请运行: pip install aioredis")
            raise
        except Exception as e:
            logger.error(f"连接Redis失败: {e}")
            raise
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.redis:
            await self.redis.close()
    
    async def register(self, instance: ServiceInstance) -> bool:
        """注册服务到Redis"""
        try:
            key = f"{self.key_prefix}:{instance.service_name}:{instance.instance_id}"
            value = json.dumps(instance.to_dict())
            
            # 设置TTL为5分钟
            await self.redis.setex(key, 300, value)
            
            # 添加到服务列表
            list_key = f"{self.key_prefix}:list:{instance.service_name}"
            await self.redis.sadd(list_key, instance.instance_id)
            await self.redis.expire(list_key, 300)
            
            logger.info(f"Redis服务注册成功: {instance.service_name}#{instance.instance_id}")
            return True
            
        except Exception as e:
            logger.error(f"Redis注册服务失败: {e}")
            return False
    
    async def deregister(self, service_name: str, instance_id: str) -> bool:
        """从Redis注销服务"""
        try:
            key = f"{self.key_prefix}:{service_name}:{instance_id}"
            list_key = f"{self.key_prefix}:list:{service_name}"
            
            await self.redis.delete(key)
            await self.redis.srem(list_key, instance_id)
            
            logger.info(f"Redis服务注销成功: {service_name}#{instance_id}")
            return True
            
        except Exception as e:
            logger.error(f"Redis注销服务失败: {e}")
            return False
    
    async def discover(self, service_name: str) -> List[ServiceInstance]:
        """从Redis发现服务"""
        try:
            list_key = f"{self.key_prefix}:list:{service_name}"
            instance_ids = await self.redis.smembers(list_key)
            
            instances = []
            for instance_id in instance_ids:
                key = f"{self.key_prefix}:{service_name}:{instance_id.decode()}"
                value = await self.redis.get(key)
                
                if value:
                    data = json.loads(value.decode())
                    instance = ServiceInstance.from_dict(data)
                    instances.append(instance)
            
            return instances
            
        except Exception as e:
            logger.error(f"Redis发现服务失败: {e}")
            return []
    
    async def list_all(self) -> Dict[str, List[ServiceInstance]]:
        """列出所有服务"""
        try:
            pattern = f"{self.key_prefix}:list:*"
            keys = await self.redis.keys(pattern)
            
            all_services = {}
            for key in keys:
                service_name = key.decode().split(':')[-1]
                instances = await self.discover(service_name)
                if instances:
                    all_services[service_name] = instances
            
            return all_services
            
        except Exception as e:
            logger.error(f"Redis列出所有服务失败: {e}")
            return {}
    
    async def update_status(self, service_name: str, instance_id: str, status: ServiceStatus) -> bool:
        """更新服务状态"""
        try:
            key = f"{self.key_prefix}:{service_name}:{instance_id}"
            value = await self.redis.get(key)
            
            if value:
                data = json.loads(value.decode())
                instance = ServiceInstance.from_dict(data)
                instance.status = status
                instance.update_heartbeat()
                
                return await self.register(instance)
            
            return False
            
        except Exception as e:
            logger.error(f"Redis更新服务状态失败: {e}")
            return False


class InMemoryBackend(ServiceRegistryBackend):
    """内存服务发现后端（用于测试和单机部署）"""
    
    def __init__(self):
        self.services: Dict[str, List[ServiceInstance]] = {}
    
    async def register(self, instance: ServiceInstance) -> bool:
        """注册服务到内存"""
        if instance.service_name not in self.services:
            self.services[instance.service_name] = []
        
        # 更新或添加实例
        existing_index = None
        for i, existing_instance in enumerate(self.services[instance.service_name]):
            if existing_instance.instance_id == instance.instance_id:
                existing_index = i
                break
        
        if existing_index is not None:
            self.services[instance.service_name][existing_index] = instance
        else:
            self.services[instance.service_name].append(instance)
        
        logger.info(f"内存服务注册成功: {instance.service_name}#{instance.instance_id}")
        return True
    
    async def deregister(self, service_name: str, instance_id: str) -> bool:
        """从内存注销服务"""
        if service_name in self.services:
            self.services[service_name] = [
                inst for inst in self.services[service_name]
                if inst.instance_id != instance_id
            ]
            if not self.services[service_name]:
                del self.services[service_name]
            
            logger.info(f"内存服务注销成功: {service_name}#{instance_id}")
            return True
        
        return False
    
    async def discover(self, service_name: str) -> List[ServiceInstance]:
        """从内存发现服务"""
        return self.services.get(service_name, [])
    
    async def list_all(self) -> Dict[str, List[ServiceInstance]]:
        """列出所有服务"""
        return self.services.copy()
    
    async def update_status(self, service_name: str, instance_id: str, status: ServiceStatus) -> bool:
        """更新服务状态"""
        if service_name in self.services:
            for instance in self.services[service_name]:
                if instance.instance_id == instance_id:
                    instance.status = status
                    instance.update_heartbeat()
                    return True
        return False 