
# ClickHouse工作示例
import aiohttp

async def test_clickhouse():
    async with aiohttp.ClientSession() as session:
        # 简单查询
        async with session.post("http://localhost:8123/", 
                               data="SELECT 1",
                               timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status == 200:
                result = await resp.text()
                print(f"ClickHouse查询结果: {result.strip()}")
                return True
    return False
