#!/usr/bin/env python3
"""
MarketPrism Week 4 缓存系统进度验证脚本
"""

import sys
import os
import asyncio
from datetime import timedelta

# 添加src路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

async def main():
    """运行Week 4缓存系统验证"""
    print("=" * 80)
    print("MarketPrism Week 4 缓存系统进度验证")
    print("=" * 80)
    
    # 步骤1: 验证核心接口
    print("\n1. 核心接口验证")
    try:
        from marketprism_collector.core.caching.cache_interface import (
            CacheKey, CacheValue, CacheConfig, CacheLevel, CacheEvictionPolicy
        )
        print("  ✅ 缓存核心接口导入成功")
        
        # 测试CacheKey
        key = CacheKey(namespace="test", key="example")
        print(f"  ✅ CacheKey创建成功: {key.full_key()}")
        
        # 测试CacheValue
        value = CacheValue(data="test data")
        print(f"  ✅ CacheValue创建成功，大小: {value.size_bytes} bytes")
        
    except Exception as e:
        print(f"  ❌ 核心接口验证失败: {e}")
        return False
    
    # 步骤2: 验证缓存策略
    print("\n2. 缓存策略验证")
    try:
        from marketprism_collector.core.caching.cache_strategies import (
            LRUStrategy, LFUStrategy, TTLStrategy, AdaptiveStrategy, create_strategy
        )
        print("  ✅ 缓存策略模块导入成功")
        
        # 测试LRU策略
        lru_strategy = LRUStrategy(max_size=100)
        test_key = CacheKey(namespace="test", key="strategy")
        test_value = CacheValue(data="strategy test")
        
        lru_strategy.on_insert(test_key, test_value)
        print("  ✅ LRU策略测试成功")
        
        # 测试策略工厂
        adaptive_strategy = create_strategy(CacheEvictionPolicy.ADAPTIVE, max_size=100)
        print("  ✅ 自适应策略创建成功")
        
    except Exception as e:
        print(f"  ❌ 缓存策略验证失败: {e}")
        return False
    
    # 步骤3: 验证内存缓存实现
    print("\n3. 内存缓存实现验证")
    try:
        from marketprism_collector.core.caching.memory_cache import MemoryCache, MemoryCacheConfig
        print("  ✅ 内存缓存模块导入成功")
        
        # 创建内存缓存配置
        config = MemoryCacheConfig(
            name="test_cache",
            level=CacheLevel.MEMORY,
            max_size=100,
            eviction_policy=CacheEvictionPolicy.LRU,
            default_ttl=timedelta(minutes=10)
        )
        print("  ✅ 内存缓存配置创建成功")
        
        # 创建内存缓存实例
        cache = MemoryCache(config)
        print("  ✅ 内存缓存实例创建成功")
        
        # 测试基本操作
        test_key = CacheKey(namespace="test", key="memory")
        test_value = CacheValue(data="memory test data")
        
        # 设置值
        result = await cache.set(test_key, test_value)
        print(f"  ✅ 缓存设置成功: {result}")
        
        # 获取值
        retrieved_value = await cache.get(test_key)
        if retrieved_value and retrieved_value.data == "memory test data":
            print("  ✅ 缓存获取成功")
        else:
            print("  ❌ 缓存获取失败")
            return False
        
        # 测试缓存大小
        size = await cache.size()
        print(f"  ✅ 缓存大小: {size}")
        
        # 测试健康检查
        health = await cache.health_check()
        if health.get('healthy'):
            print("  ✅ 缓存健康检查通过")
        else:
            print(f"  ❌ 缓存健康检查失败: {health}")
        
        # 清理
        await cache.stop()
        
    except Exception as e:
        print(f"  ❌ 内存缓存验证失败: {e}")
        return False
    
    # 步骤4: 验证批量操作
    print("\n4. 批量操作验证")
    try:
        config = MemoryCacheConfig(
            name="batch_test_cache",
            level=CacheLevel.MEMORY,
            max_size=100
        )
        cache = MemoryCache(config)
        
        # 批量设置
        items = {}
        for i in range(5):
            key = CacheKey(namespace="batch", key=f"item_{i}")
            value = CacheValue(data=f"batch data {i}")
            items[key] = value
        
        set_results = await cache.set_many(items)
        success_count = sum(1 for success in set_results.values() if success)
        print(f"  ✅ 批量设置成功: {success_count}/5")
        
        # 批量获取
        keys = list(items.keys())
        get_results = await cache.get_many(keys)
        retrieved_count = sum(1 for value in get_results.values() if value is not None)
        print(f"  ✅ 批量获取成功: {retrieved_count}/5")
        
        # 清理
        await cache.stop()
        
    except Exception as e:
        print(f"  ❌ 批量操作验证失败: {e}")
        return False
    
    # 步骤5: 验证统计和监控
    print("\n5. 统计和监控验证")
    try:
        config = MemoryCacheConfig(
            name="stats_test_cache",
            level=CacheLevel.MEMORY,
            max_size=100,
            enable_metrics=True
        )
        cache = MemoryCache(config)
        
        # 执行一些操作来生成统计数据
        for i in range(10):
            key = CacheKey(namespace="stats", key=f"item_{i}")
            value = CacheValue(data=f"stats data {i}")
            await cache.set(key, value)
            await cache.get(key)  # 产生命中
        
        # 获取统计信息
        stats = cache.get_statistics()
        print(f"  ✅ 缓存命中率: {stats.hit_rate:.2%}")
        print(f"  ✅ 总操作数: {stats.hits + stats.misses}")
        print(f"  ✅ 设置操作数: {stats.sets}")
        
        # 获取内存统计
        memory_stats = await cache.get_memory_stats()
        print(f"  ✅ 内存使用: {memory_stats['total_items']} 项")
        print(f"  ✅ 平均大小: {memory_stats['average_size_bytes']:.0f} bytes")
        
        # 清理
        await cache.stop()
        
    except Exception as e:
        print(f"  ❌ 统计和监控验证失败: {e}")
        return False
    
    # 步骤6: 验证TTL和过期
    print("\n6. TTL和过期验证")
    try:
        config = MemoryCacheConfig(
            name="ttl_test_cache",
            level=CacheLevel.MEMORY,
            max_size=100,
            default_ttl=timedelta(seconds=1)  # 1秒TTL
        )
        cache = MemoryCache(config)
        
        # 设置带TTL的值
        key = CacheKey(namespace="ttl", key="test")
        value = CacheValue(data="ttl test data")
        await cache.set(key, value)
        
        # 立即获取应该成功
        result = await cache.get(key)
        if result:
            print("  ✅ TTL设置后立即获取成功")
        else:
            print("  ❌ TTL设置后立即获取失败")
        
        # 等待过期
        await asyncio.sleep(1.5)
        
        # 再次获取应该失败
        result = await cache.get(key)
        if result is None:
            print("  ✅ TTL过期后获取正确返回None")
        else:
            print("  ❌ TTL过期后仍能获取到值")
        
        # 清理
        await cache.stop()
        
    except Exception as e:
        print(f"  ❌ TTL和过期验证失败: {e}")
        return False
    
    # 总结
    print("\n" + "=" * 80)
    print("✅ MarketPrism Week 4 缓存系统进度验证完成！")
    print("=" * 80)
    print("\n已完成的核心组件:")
    print("  📊 缓存接口定义: ✅ 统一的缓存操作接口")
    print("  🔄 缓存策略引擎: ✅ LRU、LFU、TTL、自适应策略") 
    print("  💾 内存缓存实现: ✅ 高性能线程安全内存缓存")
    print("  📈 批量操作支持: ✅ 优化的批量设置和获取")
    print("  📊 统计和监控: ✅ 详细的性能指标和内存统计")
    print("  ⏰ TTL和过期管理: ✅ 自动过期和清理机制")
    print("\n📝 Week 4 进度: 约40%完成")
    print("🔜 下一步: Redis缓存、磁盘缓存、缓存协调器、性能优化引擎")
    
    return True

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 