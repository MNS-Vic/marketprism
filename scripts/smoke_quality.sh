#!/usr/bin/env bash
# MarketPrism 一键端到端质量烟测脚本（默认180s，覆盖+质量+错误监控）
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
cd "$ROOT_DIR"

# 启用虚拟环境（如存在）
if [ -d "venv" ]; then
  source venv/bin/activate
elif [ -d ".venv" ]; then
  source .venv/bin/activate
fi

# 选择 docker compose 命令（兼容 docker-compose 与 docker compose）
DC="docker-compose"
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  DC="docker compose"
fi

START_TS=$(date +%s)

cleanup() {
  echo "\n[cleanup] 开始清理..."
  set +e
  # 先停止 Storage 与 Collector，避免清理阶段 NATS 连接报错
  pkill -f "services/data-storage-service/main.py" 2>/dev/null || true
  pkill -f "services/data-collector/unified_collector_main.py" 2>/dev/null || true

  if [ "${KEEP_RUNNING:-0}" != "1" ]; then
    $DC -f services/message-broker/docker-compose.nats.yml down -v || true
    if [ "${KEEP_CH:-0}" != "1" ]; then
      $DC -f services/data-storage-service/docker-compose.hot-storage.yml down || true
    fi
  fi
  set -e
  echo "[cleanup] 完成"
}
trap cleanup EXIT

# 0) 预清理可能存在的同名容器，避免 container_name 冲突
(docker rm -f marketprism-nats >/dev/null 2>&1) || true

# ClickHouse 查询助手
ch() {
  curl -s "http://localhost:8123/" --data "$1"
}

# 1) 启动 NATS
$DC -f services/message-broker/docker-compose.nats.yml up -d
# 等待 NATS 就绪
for i in {1..45}; do
  if curl -sf http://localhost:8222/healthz >/dev/null; then
    echo "[nats] healthz ok"; break
  fi
  echo "[nats] waiting ($i) ..."; sleep 1
  if [ "$i" = "45" ]; then echo "[nats] health check timeout"; exit 1; fi
done

# 2) 启动 ClickHouse（仅热点库）
$DC -f services/data-storage-service/docker-compose.hot-storage.yml up -d clickhouse-hot

# 等待 ClickHouse HTTP 就绪
for i in {1..60}; do
  if curl -sf http://localhost:8123/ping >/dev/null; then
    echo "[clickhouse] ping ok"; break
  fi
  echo "[clickhouse] waiting ($i) ..."; sleep 1
  if [ "$i" = "60" ]; then echo "[clickhouse] health check timeout"; exit 1; fi
done

# 迁移：确保 volatility_indices 存在 maturity_date 列
ch "ALTER TABLE marketprism_hot.volatility_indices ADD COLUMN IF NOT EXISTS maturity_date Date" || true


# 3) 启动 Collector（launcher）
nohup python3 services/data-collector/unified_collector_main.py --mode launcher \
  > services/data-collector/collector.log 2>&1 &
# 给 Collector 3 秒创建 JetStream 流
sleep 3

# 4) 启动简化热存储（simple_hot_storage）
nohup env NATS_URL="${NATS_URL:-nats://localhost:4222}" \
  CLICKHOUSE_HOST="${CLICKHOUSE_HOST:-localhost}" \
  CLICKHOUSE_HTTP_PORT="${CLICKHOUSE_HTTP_PORT:-8123}" \
  CLICKHOUSE_DATABASE="${CLICKHOUSE_DATABASE:-marketprism_hot}" \
  python3 services/data-storage-service/main.py \
  > services/data-storage-service/production.log 2>&1 &

# 5) 等待服务稳定并收集数据
DURATION=${DURATION_SECONDS:-180}
echo "[wait] 等待服务稳定（30s）..."
sleep 30

# 验证数据流是否正常启动
echo "[verify] 验证数据流启动状态..."
for i in {1..10}; do
  RECENT_COUNT=$(ch "SELECT count() FROM marketprism_hot.trades WHERE timestamp > now() - INTERVAL 1 MINUTE" 2>/dev/null || echo "0")
  if [ "$RECENT_COUNT" -gt "0" ]; then
    echo "[verify] ✅ 数据流已启动，最近1分钟有 $RECENT_COUNT 条 trade 记录"
    break
  fi
  echo "[verify] 等待数据流启动... ($i/10)"
  sleep 6
  if [ "$i" = "10" ]; then
    echo "[verify] ⚠️ 数据流启动缓慢，继续等待..."
  fi
done

echo "[wait] 继续等待 ${DURATION}s 收集充分数据..."
sleep "$DURATION"

# 6) 统计与质量校验（最近2分钟为主，部分低频10分钟）
# 表 -> 窗口（分钟）映射：
# 高频 2m: orderbooks, trades, liquidations
# 中频 10m: funding_rates, open_interests, lsr_top_positions, lsr_all_accounts, volatility_indices

printf "\n=== 覆盖性检查（各表 exchange/market_type 计数） ===\n"
for entry in \
  "orderbooks 2" \
  "trades 2" \
  "liquidations 2" \
  "funding_rates 10" \
  "open_interests 10" \
  "lsr_top_positions 10" \
  "lsr_all_accounts 10" \
  "volatility_indices 10"; do
  set -- $entry; table=$1; win=$2
  echo "\n-- $table (last ${win}m) --"
  ch "SELECT exchange, market_type, count() AS cnt FROM marketprism_hot.${table} WHERE timestamp > now() - INTERVAL ${win} MINUTE GROUP BY exchange, market_type ORDER BY cnt DESC FORMAT TabSeparatedWithNames"
done

printf "\n=== 各表样本数据（格式示例，最新1条） ===\n"
# 为可读性仅选取关键字段
ch "SELECT toString(timestamp) AS ts, exchange, market_type, symbol, best_bid_price, best_ask_price FROM marketprism_hot.orderbooks WHERE timestamp > now() - INTERVAL 10 MINUTE ORDER BY timestamp DESC LIMIT 1 FORMAT TabSeparatedWithNames" || true
ch "SELECT toString(timestamp) AS ts, exchange, market_type, symbol, price, quantity, side, is_maker FROM marketprism_hot.trades WHERE timestamp > now() - INTERVAL 10 MINUTE ORDER BY timestamp DESC LIMIT 1 FORMAT TabSeparatedWithNames" || true
ch "SELECT toString(timestamp) AS ts, exchange, market_type, symbol, funding_rate, toString(funding_time) AS funding_time FROM marketprism_hot.funding_rates WHERE timestamp > now() - INTERVAL 24 HOUR ORDER BY timestamp DESC LIMIT 1 FORMAT TabSeparatedWithNames" || true
ch "SELECT toString(timestamp) AS ts, exchange, market_type, symbol, open_interest, open_interest_value FROM marketprism_hot.open_interests WHERE timestamp > now() - INTERVAL 24 HOUR ORDER BY timestamp DESC LIMIT 1 FORMAT TabSeparatedWithNames" || true
ch "SELECT toString(timestamp) AS ts, exchange, market_type, symbol, side, price, quantity FROM marketprism_hot.liquidations WHERE timestamp > now() - INTERVAL 24 HOUR ORDER BY timestamp DESC LIMIT 1 FORMAT TabSeparatedWithNames" || true
ch "SELECT toString(timestamp) AS ts, exchange, market_type, symbol, long_position_ratio, short_position_ratio, period FROM marketprism_hot.lsr_top_positions WHERE timestamp > now() - INTERVAL 24 HOUR ORDER BY timestamp DESC LIMIT 1 FORMAT TabSeparatedWithNames" || true
ch "SELECT toString(timestamp) AS ts, exchange, market_type, symbol, long_account_ratio, short_account_ratio, period FROM marketprism_hot.lsr_all_accounts WHERE timestamp > now() - INTERVAL 24 HOUR ORDER BY timestamp DESC LIMIT 1 FORMAT TabSeparatedWithNames" || true
ch "SELECT toString(timestamp) AS ts, exchange, market_type, symbol, index_value, underlying_asset, toString(maturity_date) AS maturity_date FROM marketprism_hot.volatility_indices WHERE timestamp > now() - INTERVAL 24 HOUR ORDER BY timestamp DESC LIMIT 1 FORMAT TabSeparatedWithNames" || true

printf "\n=== 数据质量检查（异常计数） ===\n"
# 关键字段完整性与数值范围
ch "SELECT 'trades' AS table, count() AS anomalies FROM marketprism_hot.trades WHERE timestamp > now() - INTERVAL 10 MINUTE AND (price <= 0 OR quantity <= 0 OR length(symbol)=0 OR length(exchange)=0 OR length(market_type)=0 OR timestamp > now() + INTERVAL 2 MINUTE) FORMAT TabSeparatedWithNames"
ch "SELECT 'orderbooks' AS table, count() AS anomalies FROM marketprism_hot.orderbooks WHERE timestamp > now() - INTERVAL 10 MINUTE AND (length(symbol)=0 OR length(exchange)=0 OR length(market_type)=0 OR length(bids) < 2 OR length(asks) < 2 OR timestamp > now() + INTERVAL 2 MINUTE) FORMAT TabSeparatedWithNames"
ch "SELECT 'funding_rates' AS table, count() AS anomalies FROM marketprism_hot.funding_rates WHERE timestamp > now() - INTERVAL 24 HOUR AND (length(symbol)=0 OR length(exchange)=0 OR length(market_type)=0 OR timestamp > now() + INTERVAL 2 MINUTE) FORMAT TabSeparatedWithNames"
ch "SELECT 'open_interests' AS table, count() AS anomalies FROM marketprism_hot.open_interests WHERE timestamp > now() - INTERVAL 24 HOUR AND (open_interest < 0 OR length(symbol)=0 OR length(exchange)=0 OR length(market_type)=0 OR timestamp > now() + INTERVAL 2 MINUTE) FORMAT TabSeparatedWithNames"
ch "SELECT 'liquidations' AS table, count() AS anomalies FROM marketprism_hot.liquidations WHERE timestamp > now() - INTERVAL 24 HOUR AND (price <= 0 OR quantity <= 0 OR length(symbol)=0 OR length(exchange)=0 OR length(market_type)=0 OR timestamp > now() + INTERVAL 2 MINUTE) FORMAT TabSeparatedWithNames"
ch "SELECT 'lsr_top_positions' AS table, count() AS anomalies FROM marketprism_hot.lsr_top_positions WHERE timestamp > now() - INTERVAL 24 HOUR AND (long_position_ratio < 0 OR short_position_ratio < 0 OR length(symbol)=0 OR length(exchange)=0 OR length(market_type)=0 OR timestamp > now() + INTERVAL 2 MINUTE) FORMAT TabSeparatedWithNames"
ch "SELECT 'lsr_all_accounts' AS table, count() AS anomalies FROM marketprism_hot.lsr_all_accounts WHERE timestamp > now() - INTERVAL 24 HOUR AND (long_account_ratio < 0 OR short_account_ratio < 0 OR length(symbol)=0 OR length(exchange)=0 OR length(market_type)=0 OR timestamp > now() + INTERVAL 2 MINUTE) FORMAT TabSeparatedWithNames"
ch "SELECT 'volatility_indices' AS table, count() AS anomalies FROM marketprism_hot.volatility_indices WHERE timestamp > now() - INTERVAL 24 HOUR AND (index_value < 0 OR length(symbol)=0 OR length(exchange)=0 OR length(market_type)=0 OR timestamp > now() + INTERVAL 2 MINUTE) FORMAT TabSeparatedWithNames"

printf "\n=== 错误监控（运行期间日志扫描） ===\n"
# 在清理前检查日志错误关键词（排除清理阶段典型的 NATS 连接错误）
COL_ERRORS=$(grep -E "ERROR|Exception|Traceback|ClickHouse插入失败|存储到ClickHouse异常|nats: timeout|Connect call failed" -i services/data-collector/collector.log | wc -l || true)
STO_ERRORS=$(grep -E "ERROR|Exception|Traceback|ClickHouse插入失败|存储到ClickHouse异常|nats: timeout|Connect call failed" -i services/data-storage-service/production.log | wc -l || true)

echo "collector.log error_lines=$COL_ERRORS"
echo "production.log error_lines=$STO_ERRORS"

# 汇总：按交易所与数据类型统计（最近2分钟/10分钟窗口）
printf "\n=== 汇总统计（按交易所+数据类型） ===\n"
# trades/orderbooks/liquidations 2m；其余10m
ch "SELECT 'trades' AS data_type, exchange, market_type, count() AS cnt FROM marketprism_hot.trades WHERE timestamp > now() - INTERVAL 2 MINUTE GROUP BY exchange, market_type ORDER BY cnt DESC FORMAT TabSeparatedWithNames"
ch "SELECT 'orderbooks' AS data_type, exchange, market_type, count() AS cnt FROM marketprism_hot.orderbooks WHERE timestamp > now() - INTERVAL 2 MINUTE GROUP BY exchange, market_type ORDER BY cnt DESC FORMAT TabSeparatedWithNames"
ch "SELECT 'liquidations' AS data_type, exchange, market_type, count() AS cnt FROM marketprism_hot.liquidations WHERE timestamp > now() - INTERVAL 2 MINUTE GROUP BY exchange, market_type ORDER BY cnt DESC FORMAT TabSeparatedWithNames"
ch "SELECT 'funding_rates' AS data_type, exchange, market_type, count() AS cnt FROM marketprism_hot.funding_rates WHERE timestamp > now() - INTERVAL 10 MINUTE GROUP BY exchange, market_type ORDER BY cnt DESC FORMAT TabSeparatedWithNames"
ch "SELECT 'open_interests' AS data_type, exchange, market_type, count() AS cnt FROM marketprism_hot.open_interests WHERE timestamp > now() - INTERVAL 10 MINUTE GROUP BY exchange, market_type ORDER BY cnt DESC FORMAT TabSeparatedWithNames"
ch "SELECT 'lsr_top_positions' AS data_type, exchange, market_type, count() AS cnt FROM marketprism_hot.lsr_top_positions WHERE timestamp > now() - INTERVAL 10 MINUTE GROUP BY exchange, market_type ORDER BY cnt DESC FORMAT TabSeparatedWithNames"
ch "SELECT 'lsr_all_accounts' AS data_type, exchange, market_type, count() AS cnt FROM marketprism_hot.lsr_all_accounts WHERE timestamp > now() - INTERVAL 10 MINUTE GROUP BY exchange, market_type ORDER BY cnt DESC FORMAT TabSeparatedWithNames"
ch "SELECT 'volatility_indices' AS data_type, exchange, market_type, count() AS cnt FROM marketprism_hot.volatility_indices WHERE timestamp > now() - INTERVAL 10 MINUTE GROUP BY exchange, market_type ORDER BY cnt DESC FORMAT TabSeparatedWithNames"

END_TS=$(date +%s)
RUNTIME=$((END_TS-START_TS))
echo "\n[summary] 运行时长=${RUNTIME}s (目标>=180s)"

# 正常结束时由 trap 进行清理

