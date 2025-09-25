#!/usr/bin/env bash
set -euo pipefail
# Ensure venv (ops are OS-level; activation for compliance)
if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate || true
fi

keep_and_cleanup() {
  local pattern_py="$1"; shift
  local pattern_subj="$1"; shift
  local pidfile="$1"; shift
  local pids keep to_kill
  mapfile -t pids < <(ps -eo pid,cmd --no-headers | grep -F -- "$pattern_py" | grep -F -- "$pattern_subj" | awk '{print $1}' | sort -n)
  if (( ${#pids[@]} == 0 )); then
    echo "[WARN] not found: $pattern_py $pattern_subj" >&2
    return 0
  fi
  keep="${pids[0]}"
  if (( ${#pids[@]} > 1 )); then
    to_kill=("${pids[@]:1}")
    echo "[CLEANUP] kill duplicates: ${to_kill[*]} for ($pattern_py $pattern_subj)"
    for k in "${to_kill[@]}"; do kill -TERM "$k" 2>/dev/null || true; done
    sleep 1
    for k in "${to_kill[@]}"; do kill -KILL "$k" 2>/dev/null || true; done
  fi
  echo "$keep" > "$pidfile"
}

keep_and_cleanup "synthetic_core_mirror_publisher.py" "--subject trade.binance_spot.spot.BTCUSDT" "/tmp/ab_synth_trade.pid"
keep_and_cleanup "synthetic_core_mirror_publisher.py" "--subject orderbook.binance_spot.spot.BTCUSDT" "/tmp/ab_synth_ob.pid"
keep_and_cleanup "ab_latency_compare.py" "--subject trade.binance_spot.spot.BTCUSDT" "/tmp/ab_compare_trade.pid"
keep_and_cleanup "ab_latency_compare.py" "--subject orderbook.binance_spot.spot.BTCUSDT" "/tmp/ab_compare_ob.pid"

printf "\n=== Final processes (should be 4) ===\n"
for f in /tmp/ab_synth_trade.pid /tmp/ab_synth_ob.pid /tmp/ab_compare_trade.pid /tmp/ab_compare_ob.pid; do
  if [ -f "$f" ]; then
    pid=$(cat "$f")
    ps -o pid,etimes,cmd -p "$pid" --no-headers || echo "[WARN] process not found for $f ($pid)"
  else
    echo "[ERROR] missing pidfile: $f"
  fi
done

printf "\n=== PID files ===\n"
ls -l /tmp/ab_*.pid 2>/dev/null || true
for f in /tmp/ab_synth_trade.pid /tmp/ab_synth_ob.pid /tmp/ab_compare_trade.pid /tmp/ab_compare_ob.pid; do
  echo -n "$f: "; cat "$f" 2>/dev/null || echo MISSING
done

printf "\n=== NATS subsz snapshot (filtered) ===\n"
curl -sS 'http://localhost:8222/subsz?subs=1&limit=4096' | egrep 'core\.trade\.binance_spot\.spot\.BTCUSDT|trade\.binance_spot\.spot\.BTCUSDT|core\.orderbook\.binance_spot\.spot\.BTCUSDT|orderbook\.binance_spot\.spot\.BTCUSDT' || true

