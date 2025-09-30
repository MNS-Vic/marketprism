"""
E2E 验证（最小可运行骨架）：
- 检查 NATS/ClickHouse 端点可用性（否则自动 skip）
- 校验 NATS /jsz 存在 MARKET_DATA 与 ORDERBOOK_SNAP 两个流
- 校验 ClickHouse 热端 8 张表最近 5 分钟是否有任一表有数据
"""
import pytest
import requests

NATS_MON = "http://127.0.0.1:8222"
CH_HTTP = "http://127.0.0.1:8123/"

REQUIRED_TABLES = [
    "orderbooks",
    "trades",
    "funding_rates",
    "open_interests",
    "liquidations",
    "lsr_top_positions",
    "lsr_all_accounts",
    "volatility_indices",
]


def _service_up(url: str, timeout=1.0) -> bool:
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


@pytest.mark.e2e
def test_streams_exist_or_skip():
    if not _service_up(NATS_MON + "/healthz"):
        pytest.skip("NATS monitoring is not available")
    # 优先使用带 streams=true 的接口以获取详细流信息
    jsz = requests.get(NATS_MON + "/jsz?streams=true", timeout=5).json()
    stream_names = set()
    if isinstance(jsz, dict):
        # 兼容新版本：account_details[...].stream_detail[...].name
        for acct in jsz.get("account_details", []) or []:
            for sd in acct.get("stream_detail", []) or []:
                name = sd.get("name")
                if name:
                    stream_names.add(name)
        # 兼容旧版本：streams 为列表
        if not stream_names and isinstance(jsz.get("streams"), list):
            for s in jsz.get("streams", []):
                if isinstance(s, dict):
                    name = (s.get("config") or {}).get("name")
                    if name:
                        stream_names.add(name)
    assert {"MARKET_DATA", "ORDERBOOK_SNAP"}.issubset(stream_names)


@pytest.mark.e2e
def test_hot_tables_recent_counts_or_skip():
    # ClickHouse HTTP ping
    try:
        ok = requests.get(CH_HTTP + "?query=SELECT%201", timeout=2).text.strip()
    except Exception:
        pytest.skip("ClickHouse HTTP is not available")
    if ok != "1":
        pytest.skip("ClickHouse ping failed")

    # 最近 5 分钟数据计数
    results = {}
    for table in REQUIRED_TABLES:
        q = f"SELECT count() FROM marketprism_hot.{table} WHERE timestamp > now() - INTERVAL 5 MINUTE"
        try:
            cnt = requests.post(CH_HTTP, data=q, timeout=3).text.strip()
        except Exception:
            cnt = "0"
        results[table] = int(cnt) if cnt.isdigit() else 0

    # 至少有一类数据在最近 5 分钟内写入
    assert any(v > 0 for v in results.values()), f"no recent data in last 5 minutes: {results}"

