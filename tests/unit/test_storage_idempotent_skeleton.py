"""
存储幂等性（idempotent）插入的最小单元测试骨架：
- 首次插入（按唯一键 trade_id+exchange+symbol）计数=1
- 重复插入相同记录应返回0（不再新增）
说明：这里使用简化的 FakeCH 来模拟去重行为，仅作为TDD骨架。
"""
import pytest

class FakeCH:
    def __init__(self):
        self._seen = set()
    async def insert(self, table: str, rows):
        inserted = 0
        for r in rows:
            key = (table, r.get("trade_id"), r.get("exchange"), r.get("symbol"))
            if key not in self._seen:
                self._seen.add(key)
                inserted += 1
        return inserted

@pytest.mark.unit
@pytest.mark.asyncio
async def test_batch_insert_idempotent():
    ch = FakeCH()
    row = {"trade_id": "1", "exchange": "binance_spot", "symbol": "BTCUSDT"}
    assert await ch.insert("trades", [row]) == 1
    # 第二次插入相同记录应幂等
    assert await ch.insert("trades", [row]) == 0

