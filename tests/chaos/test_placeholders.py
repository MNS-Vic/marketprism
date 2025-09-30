"""
Chaos/故障恢复测试占位：默认跳过，除非设置环境变量 RUN_CHAOS_TESTS=1
- 自愈重启（需真实进程控制与时间窗口）
- NATS 断连重连（需真实 NATS）
- ClickHouse TCP → HTTP 回退（需真实服务与可控网络）
"""
import os
import pytest

RUN_CHAOS = os.environ.get("RUN_CHAOS_TESTS") == "1"

@pytest.mark.chaos
def test_self_heal_restart_placeholder():
    if not RUN_CHAOS:
        pytest.skip("set RUN_CHAOS_TESTS=1 to run chaos tests")
    assert True  # TODO: 实现真实自愈重启验证

@pytest.mark.chaos
def test_nats_disconnect_recover_placeholder():
    if not RUN_CHAOS:
        pytest.skip("set RUN_CHAOS_TESTS=1 to run chaos tests")
    assert True  # TODO: 实现真实NATS断连-重连验证

@pytest.mark.chaos
def test_clickhouse_tcp_fallback_placeholder():
    if not RUN_CHAOS:
        pytest.skip("set RUN_CHAOS_TESTS=1 to run chaos tests")
    assert True  # TODO: 实现TCP→HTTP回退验证

