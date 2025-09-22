#!/usr/bin/env python3
# Orchestrated Phase 2 validation to avoid shell prompt pollution
# - Starts NATS via docker compose and waits for health
# - Initializes JetStream
# - Starts Collector & Storage
# - Runs quick verify + 5min consumer sampling
# - Checks ClickHouse counts
# - Cleans up processes (keeps NATS running)

import os
import sys
import time
import json
import subprocess
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

REPO_ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
REPORT = os.path.join(REPO_ROOT, 'logs', 'phase2_validation_report.txt')
NATS_URL = os.getenv('MARKETPRISM_NATS_URL', 'nats://localhost:4222')
CLICKHOUSE_HTTP = os.getenv('CLICKHOUSE_HTTP', 'http://localhost:8123')
COMPOSE_FILE = os.path.join(REPO_ROOT, 'services', 'message-broker', 'docker-compose.nats.yml')

COLLECTOR_LOG = os.path.join(REPO_ROOT, 'logs', 'collector_phase2.log')
STORAGE_LOG = os.path.join(REPO_ROOT, 'logs', 'storage_phase2.log')

COLLECTOR_PID = '/tmp/collector_phase2.pid'
STORAGE_PID = '/tmp/storage_phase2.pid'

PYTHON = sys.executable


def writeln(f, line):
    print(line)
    f.write(line + "\n")
    f.flush()


def run(cmd, cwd=REPO_ROOT, timeout=None, env=None):
    proc = subprocess.run(cmd, cwd=cwd, timeout=timeout, env=env or os.environ.copy(),
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return proc.returncode, proc.stdout


def ch_query(sql: str) -> str:
    try:
        data = sql.encode('utf-8')
        with urlopen(Request(CLICKHOUSE_HTTP, data=data), timeout=3) as resp:
            return resp.read().decode('utf-8', errors='ignore').strip()
    except Exception as e:
        return f"ERROR: {e}"


def main():
    os.makedirs(os.path.join(REPO_ROOT, 'logs'), exist_ok=True)
    with open(REPORT, 'w', encoding='utf-8') as f:
        writeln(f, f"=== Phase 2 验证报告（编排）@ {datetime.now(timezone.utc).isoformat()} ===")
        writeln(f, f"NATS_URL={NATS_URL}")
        writeln(f, f"CLICKHOUSE_HTTP={CLICKHOUSE_HTTP}")

        # 1) docker compose up -d
        if not os.path.exists(COMPOSE_FILE):
            writeln(f, f"✗ 缺少 compose 文件: {COMPOSE_FILE}")
            return 1
        rc, out = run(['sudo', 'docker', 'compose', '-f', COMPOSE_FILE, 'up', '-d'])
        writeln(f, f"docker compose up -d rc={rc}")
        if out:
            writeln(f, out.strip())

        # 2) wait for healthz
        ok = False
        for i in range(60):
            try:
                with urlopen('http://localhost:8222/healthz', timeout=2) as resp:
                    if resp.status == 200:
                        ok = True
                        break
            except Exception:
                pass
            time.sleep(2)
        writeln(f, "✅ NATS 健康检查通过" if ok else "✗ NATS 健康检查失败/超时")
        if not ok:
            return 2

        # 3) JetStream init
        env = os.environ.copy()
        env['MARKETPRISM_NATS_URL'] = NATS_URL
        rc, out = run([PYTHON, 'services/message-broker/init_jetstream.py', '--wait', '--config', 'scripts/js_init_market_data.yaml'], env=env)
        writeln(f, f"init_jetstream rc={rc}")
        if out:
            writeln(f, out.strip())
        if rc != 0:
            lower = (out or "").lower()
            if ("overlap with an existing stream" in lower) or ("subjects overlap" in lower):
                writeln(f, "⚠️ JetStream已有同名/重叠Subject的Stream，视为已初始化，继续")
            else:
                return 3

        # 4) start collector & storage
        # 4.0) 删除不符合要求（非 LAST）的历史 durable，以确保本次从 LAST 策略创建
        try:
            import asyncio, nats
            async def reconcile_consumers():
                nc = await nats.connect(NATS_URL)
                jsm = nc.jsm()
                targets = [
                    'simple_hot_storage_realtime_trade',
                    'simple_hot_storage_realtime_orderbook',
                    'simple_hot_storage_realtime_liquidation',
                ]
                for d in targets:
                    try:
                        info = await jsm.consumer_info('MARKET_DATA', d)
                        dp = getattr(getattr(info, 'config', None), 'deliver_policy', None)
                        if str(dp).lower() != 'last':
                            await jsm.delete_consumer('MARKET_DATA', d)
                            writeln(f, f"🧹 已删除旧consumer: {d} (deliver_policy={dp})")
                    except Exception:
                        pass
                await nc.close()
            asyncio.run(reconcile_consumers())
        except Exception as e:
            writeln(f, f"⚠️ 无法对齐历史消费者: {e}")

        # kill if running
        for pidf in (COLLECTOR_PID, STORAGE_PID):
            try:
                if os.path.exists(pidf):
                    with open(pidf) as p:
                        pid = int(p.read().strip())
                    os.kill(pid, 9)
            except Exception:
                pass
        # collector
        with open(COLLECTOR_LOG, 'a') as lf:
            col = subprocess.Popen([PYTHON, '-u', 'services/data-collector/unified_collector_main.py', '--mode', 'launcher'],
                                   cwd=REPO_ROOT, stdout=lf, stderr=subprocess.STDOUT, env=env)
        with open(COLLECTOR_PID, 'w') as p:
            p.write(str(col.pid))
        time.sleep(6)
        # storage
        env2 = env.copy()
        env2['NATS_URL'] = NATS_URL
        env2['CLICKHOUSE_HOST'] = 'localhost'
        env2['CLICKHOUSE_HTTP_PORT'] = '8123'
        env2['CLICKHOUSE_DATABASE'] = 'marketprism_hot'
        with open(STORAGE_LOG, 'a') as lf:
            sto = subprocess.Popen([PYTHON, '-u', 'services/data-storage-service/main.py'],
                                   cwd=REPO_ROOT, stdout=lf, stderr=subprocess.STDOUT, env=env2)
        with open(STORAGE_PID, 'w') as p:
            p.write(str(sto.pid))
        time.sleep(10)

        # 5) quick verify
        rc, out = run([PYTHON, 'scripts/phase2_verify.py'], env=env)
        writeln(f, out.strip())

        # 6) 5min sampling
        writeln(f, "\n--- 5min JetStream消费者指标监控 ---")
        try:
            import asyncio
            import nats
            async def sample():
                nc = await nats.connect(NATS_URL)
                js = nc.jetstream()
                durs = [
                    'simple_hot_storage_realtime_trade',
                    'simple_hot_storage_realtime_orderbook',
                    'simple_hot_storage_realtime_liquidation'
                ]
                for t in range(10):
                    writeln(f, f"采样 {t+1}/10 @ {datetime.now(timezone.utc).isoformat()}")
                    for d in durs:
                        try:
                            info = await js.consumer_info('MARKET_DATA', d)
                            writeln(f, json.dumps({
                                'durable': d,
                                'deliver_policy': getattr(getattr(info, 'config', None), 'deliver_policy', None),
                                'num_pending': getattr(info, 'num_pending', None),
                                'num_waiting': getattr(info, 'num_waiting', None),
                                'num_ack_pending': getattr(info, 'num_ack_pending', None),
                                'num_redelivered': getattr(info, 'num_redelivered', None),
                            }, ensure_ascii=False))
                        except Exception as e:
                            writeln(f, json.dumps({'durable': d, 'error': str(e)}, ensure_ascii=False))
                    await asyncio.sleep(30)
                await nc.close()
            asyncio.run(sample())
        except Exception as e:
            writeln(f, f"✗ 采样异常: {e}")

        # 7) ClickHouse tail counts
        writeln(f, "\n--- ClickHouse 样本计数（收尾） ---")
        for tbl in ['trades','orderbooks','liquidations']:
            writeln(f, f"{tbl}: {ch_query(f'SELECT count() FROM marketprism_hot.{tbl}')}" )

        # 8) final consumer snapshot
        try:
            import asyncio, nats
            async def snap():
                nc = await nats.connect(NATS_URL)
                js = nc.jetstream()
                for d in ['simple_hot_storage_realtime_trade','simple_hot_storage_realtime_orderbook','simple_hot_storage_realtime_liquidation']:
                    try:
                        info = await js.consumer_info('MARKET_DATA', d)
                        writeln(f, f"{d} 结束快照: pending={getattr(info,'num_pending',None)} waiting={getattr(info,'num_waiting',None)}")
                    except Exception as e:
                        writeln(f, f"{d} 结束快照: ERROR {e}")
                await nc.close()
            asyncio.run(snap())
        except Exception as e:
            writeln(f, f"✗ 最终快照异常: {e}")

        # 9) cleanup processes
        try:
            for pidf in (COLLECTOR_PID, STORAGE_PID):
                try:
                    if os.path.exists(pidf):
                        with open(pidf) as p:
                            pid = int(p.read().strip())
                        os.kill(pid, 9)
                        os.remove(pidf)
                except Exception:
                    pass
        finally:
            writeln(f, "\n=== 冒烟验证完成（已清理 Collector/Storage 进程；NATS 容器保留） ===")

    return 0


if __name__ == '__main__':
    sys.exit(main())

