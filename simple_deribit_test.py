import asyncio
import aiohttp
import os

async def test():
    print("🟣 开始测试Deribit...")
    proxy = os.getenv("https_proxy")
    print(f"🔧 代理: {proxy}")
    
    try:
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        print("🔗 尝试连接WebSocket...")
        ws = await session.ws_connect(
            "wss://www.deribit.com/ws/api/v2",
            proxy=proxy,
            ssl=False
        )
        print("✅ 连接成功!")
        await ws.close()
        await session.close()
        return True
    except Exception as e:
        print(f"❌ 连接失败: {type(e).__name__}: {e}")
        if "session" in locals():
            await session.close()
        return False

if __name__ == "__main__":
    result = asyncio.run(test())
    print(f"结果: {result}") 