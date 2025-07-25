
# Redis工作示例 (兼容多版本)
import aioredis

async def test_redis():
    try:
        # 新版本API
        redis = aioredis.Redis(host='localhost', port=6379, decode_responses=True)
        await redis.ping()
        return True
    except:
        try:
            # 旧版本API
            redis = await aioredis.create_redis_pool('redis://localhost:6379')
            await redis.ping()
            redis.close()
            await redis.wait_closed()
            return True
        except:
            return False
