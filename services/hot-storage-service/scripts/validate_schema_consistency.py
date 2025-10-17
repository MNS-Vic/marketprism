#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ClickHouse Schema 一致性检查（权威 schema vs 线上实例）
- 权威 schema: services/hot-storage-service/config/clickhouse_schema.sql
- 检查范围（不比较 TTL）：
  * 列名顺序完全一致
  * 列数据类型（时间列必须为 DateTime64(3, 'UTC')；其它列做合理归一化后比较）
  * 列默认值（created_at 必须为 now64(3)）
  * 排序键/主键（MergeTree 下排序键等同主键）

环境变量（可选）：
- CH_HOST (默认: 127.0.0.1)
- CH_HTTP_PORT (默认: 8123)
- CH_USER (默认: default)
- CH_PASSWORD (默认: 空)

退出码：0 一致；非 0 存在不一致
"""

import os
import re
import sys
import time
import urllib.request
import urllib.parse
from typing import Dict, List, Tuple, Optional

RE_AUTH_CREATE = re.compile(r"^\s*CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+marketprism_hot\.(\w+)\s*\(", re.IGNORECASE)
RE_ORDER_BY = re.compile(r"^\s*ORDER\s+BY\s*\(([^)]*)\)", re.IGNORECASE)
RE_CODEC = re.compile(r"\bCODEC\s*\([^)]*\)")

SCHEMA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "config",
    "clickhouse_schema.sql",
)

CH_HOST = os.getenv("CH_HOST", "127.0.0.1")
CH_PORT = int(os.getenv("CH_HTTP_PORT", "8123"))
CH_USER = os.getenv("CH_USER", "default")
CH_PASSWORD = os.getenv("CH_PASSWORD", "")

DBS = ["marketprism_hot"]
TABLES = [
    "orderbooks",
    "trades",
    "funding_rates",
    "open_interests",
    "liquidations",
    "lsr_top_positions",
    "lsr_all_accounts",
    "volatility_indices",
]

TIME_COLUMNS = {"timestamp", "trade_time", "funding_time", "next_funding_time", "liquidation_time", "created_at"}


def _http_query(sql: str, database: Optional[str] = None) -> str:
    params = {}
    if database:
        params["database"] = database
    url = f"http://{CH_HOST}:{CH_PORT}/"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=sql.encode("utf-8"), method="POST")
    if CH_USER:
        auth_handler = urllib.request.HTTPBasicAuthHandler()
        opener = urllib.request.build_opener(auth_handler)
        urllib.request.install_opener(opener)
        req.add_header("Authorization", "Basic " + (urllib.request.base64.b64encode(f"{CH_USER}:{CH_PASSWORD}".encode()).decode()))
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def _normalize_type(t: str) -> str:
    s = t.strip()
    # 去除 CODEC(...) 片段
    s = RE_CODEC.sub("", s)
    # 统一空白
    s = re.sub(r"\s+", " ", s)
    # 同义归一化
    s = s.replace("Bool", "UInt8")  # Bool 视作 UInt8
    # Decimal64(8) -> Decimal(18, 8)
    s = re.sub(r"Decimal64\((\d+)\)", lambda m: f"Decimal(18, {m.group(1)})", s)
    # 统一大小写/空格
    s = s.replace(") ", ")").replace(" (", "(")
    return s


def _strip_codec_and_default(line: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """从列定义行中提取 (name, type, default_expr)。仅用于解析权威 schema。
    例："timestamp DateTime64(3, 'UTC') CODEC(Delta, ZSTD)," -> (timestamp, DateTime64(3, 'UTC'), None)
        "created_at DateTime64(3, 'UTC') DEFAULT now64(3) CODEC(ZSTD)" -> (..., now64(3))
    """
    raw = line.strip().rstrip(',')
    if not raw or raw.startswith("--"):
        return None, None, None
    if raw.startswith(")"):
        return None, None, None
    # 去掉行尾注释
    raw = raw.split("--", 1)[0].strip()
    if not raw:
        return None, None, None
    parts = raw.split()
    if len(parts) < 2:
        return None, None, None
    name = parts[0]
    # 聚合 type，直到遇到 DEFAULT/CODEC/COMMENT
    type_tokens = []
    i = 1
    while i < len(parts):
        p = parts[i]
        up = p.upper()
        if up.startswith("DEFAULT") or up.startswith("CODEC") or up.startswith("COMMENT"):
            break
        type_tokens.append(p)
        i += 1
    col_type = " ".join(type_tokens)
    default_expr = None
    # 找 DEFAULT 表达式
    m = re.search(r"DEFAULT\s+([^\s,]+(?:\([^)]*\))?)", raw, re.IGNORECASE)
    if m:
        default_expr = m.group(1).strip()
    return name, col_type, default_expr


def parse_authoritative_schema(path: str):
    tables: Dict[str, Dict] = {}
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Authority schema not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i]
        m = RE_AUTH_CREATE.match(line)
        if not m:
            i += 1
            continue
        table = m.group(1)
        i += 1
        cols: List[Tuple[str, str, Optional[str]]] = []
        # 读取列块
        while i < len(lines):
            L = lines[i]
            if L.strip().startswith(")"):
                break
            name, ctype, dflt = _strip_codec_and_default(L)
            if name and ctype:
                cols.append((name, ctype, dflt))
            i += 1
        # 继续向下查找 ORDER BY
        order_by_cols: List[str] = []
        while i < len(lines):
            L = lines[i]
            ob = RE_ORDER_BY.search(L)
            if ob:
                order_by_cols = [c.strip() for c in ob.group(1).split(',') if c.strip()]
                break
            # 终止于下一个 CREATE
            if RE_AUTH_CREATE.match(L):
                i -= 1
                break
            i += 1
        tables[table] = {
            "columns": cols,
            "order_by": order_by_cols,
        }
        i += 1
    return tables



def _norm_key_expr(expr: str) -> List[str]:
    e = expr.strip()
    e = e.replace("(", "").replace(")", "")
    e = e.replace(" ", "")
    return [x for x in e.split(',') if x]


def _is_dt64_utc(t: str) -> bool:
    """接受 DateTime64(3) 或 DateTime64(3, 'UTC') 视为等价。"""
    n = _normalize_type(t)
    return n.startswith("DateTime64(3")




def query_actual_table_schema(database: str, table: str):
    # 列信息
    cols_txt = _http_query(
        f"""
        SELECT name, type, default_expression
        FROM system.columns
        WHERE database = '{database}' AND table = '{table}'
        ORDER BY position
        """
    )
    cols: List[Tuple[str, str, Optional[str]]] = []
    for row in cols_txt.strip().splitlines():
        if not row:
            continue
        parts = [p.strip() for p in row.split('\t')]
        if len(parts) >= 2:
            name = parts[0]
            typ = parts[1]
            dflt = parts[2] if len(parts) >= 3 and parts[2] else None
            cols.append((name, typ, dflt))

    # 排序键 & 主键
    keys_txt = _http_query(
        f"""
        SELECT sorting_key, primary_key
        FROM system.tables
        WHERE database = '{database}' AND name = '{table}'
        """
    )
    sorting_key = ""
    primary_key = ""
    for row in keys_txt.strip().splitlines():
        parts = [p.strip() for p in row.split('\t')]
        if len(parts) >= 1:
            sorting_key = parts[0] or ""
        if len(parts) >= 2:
            primary_key = parts[1] or ""
    return {"columns": cols, "sorting_key": sorting_key, "primary_key": primary_key}


def _norm_key_expr(expr: str) -> List[str]:
    e = expr.strip()
    e = e.replace("(", "").replace(")", "")
    e = e.replace(" ", "")
    return [x for x in e.split(',') if x]


def compare(database: str, table: str, expect: Dict, actual: Dict) -> List[str]:
    diffs: List[str] = []

    exp_cols = expect["columns"]
    act_cols = actual["columns"]
    if len(exp_cols) != len(act_cols):
        diffs.append(f"[{database}.{table}] 列数量不同: 期望 {len(exp_cols)} 实际 {len(act_cols)}")
        # 继续比对较短长度，便于输出更多差异
    n = min(len(exp_cols), len(act_cols))

    for i in range(n):
        en, et, ed = exp_cols[i]
        an, at, ad = act_cols[i]
        if en != an:
            diffs.append(f"[{database}.{table}] 第{i+1}列名不同: 期望 {en} 实际 {an}")
        # 时间列强校验
        if en in TIME_COLUMNS:
            if not _is_dt64_utc(at):
                diffs.append(f"[{database}.{table}] 列 {en} 类型应为 DateTime64(3, 'UTC')，实际 {at}")
            if en == "created_at":
                ad_norm = (ad or "").replace(" ", "").lower()
                if "now64(3)" not in ad_norm:
                    diffs.append(f"[{database}.{table}] 列 created_at 默认值应为 now64(3)，实际 {ad}")
        else:
            # 其它列做类型归一化后比较（放宽同义）
            if _normalize_type(et) != _normalize_type(at):
                diffs.append(f"[{database}.{table}] 列 {en} 类型不一致: 期望 {_normalize_type(et)} 实际 {_normalize_type(at)}")

    # 排序键/主键
    exp_order = _norm_key_expr(','.join(expect.get("order_by") or []))
    act_sort = _norm_key_expr(actual.get("sorting_key") or "")
    act_pk = _norm_key_expr(actual.get("primary_key") or "")
    if exp_order and exp_order != act_sort:
        diffs.append(f"[{database}.{table}] 排序键不一致: 期望 {exp_order} 实际 {act_sort}")
    if exp_order and exp_order != act_pk:
        diffs.append(f"[{database}.{table}] 主键不一致: 期望 {exp_order} 实际 {act_pk}")

    return diffs


def main() -> int:
    print("🔍 开始检查 ClickHouse Schema 一致性 (忽略 TTL)...")

    try:
        expect_all = parse_authoritative_schema(SCHEMA_FILE)
    except Exception as e:
        print(f"❌ 解析权威 schema 失败: {e}")
        return 2

    all_diffs: List[str] = []

    for db in DBS:
        for t in TABLES:
            if t not in expect_all:
                all_diffs.append(f"[AUTH] 缺少表定义: {t}")
                continue
            try:
                actual = query_actual_table_schema(db, t)
            except Exception as e:
                all_diffs.append(f"[{db}.{t}] 查询失败: {e}")
                continue
            diffs = compare(db, t, expect_all[t], actual)
            all_diffs.extend(diffs)

    if all_diffs:
        print("\n❌ 发现不一致: ")
        for d in all_diffs:
            print(" - " + d)
        return 1

    print("\n✅ Schema 一致（已忽略 TTL 差异）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

