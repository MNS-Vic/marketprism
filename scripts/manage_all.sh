#!/bin/bash
# MarketPrism 系统统一管理脚本
# 用于统一管理所有模块（NATS、数据存储、数据采集器）

set -euo pipefail

# ============================================================================
# 配置常量
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 模块脚本路径
NATS_SCRIPT="$PROJECT_ROOT/services/message-broker/scripts/manage.sh"
STORAGE_SCRIPT="$PROJECT_ROOT/services/data-storage-service/scripts/manage.sh"
COLLECTOR_SCRIPT="$PROJECT_ROOT/services/data-collector/scripts/manage.sh"

# 颜色和符号
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ============================================================================
# 工具函数
# ============================================================================

log_info() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

log_step() {
    echo -e "${BLUE}🔹 $1${NC}"
}

log_section() {
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# 🔧 增强：等待服务启动并校验健康内容
wait_for_service() {
    local service_name="$1"
    local endpoint="$2"
    local timeout="$3"
    local expect_substr="${4:-}"
    local count=0

    log_info "等待 $service_name 启动..."

    while [ $count -lt $timeout ]; do
        local body
        if body=$(curl -sf "$endpoint" 2>/dev/null); then
            if [ -z "$expect_substr" ] || echo "$body" | grep -q "$expect_substr"; then
                log_info "$service_name 启动成功"
                return 0
            fi
        fi

        if [ $((count % 5)) -eq 0 ]; then
            log_info "等待 $service_name 启动... ($count/$timeout 秒)"
        fi

        sleep 1
        ((count++))
    done

    log_error "$service_name 启动超时"
    return 1
}

# 🔧 增强：端到端数据流验证（覆盖8种数据 + 热端/冷端 + 迁移状态）
validate_end_to_end_data_flow() {
    log_info "验证端到端数据流..."

    local validation_passed=1

    # 检测系统运行时间（通过 NATS 进程启动时间判断）
    local system_uptime_minutes=0
    if pgrep -f "nats-server" >/dev/null 2>&1; then
        local nats_pid=$(pgrep -f "nats-server" | head -n1)
        if [ -n "$nats_pid" ]; then
            local start_time=$(ps -p "$nats_pid" -o lstart= 2>/dev/null)
            if [ -n "$start_time" ]; then
                local start_epoch=$(date -d "$start_time" +%s 2>/dev/null || echo "0")
                local now_epoch=$(date +%s)
                system_uptime_minutes=$(( (now_epoch - start_epoch) / 60 ))
            fi
        fi
    fi
    local is_fresh_start=0
    if [ "$system_uptime_minutes" -lt 10 ]; then
        is_fresh_start=1
    fi

    # NATS JetStream 概要
    local js_summary=$(curl -s http://localhost:8222/jsz 2>/dev/null)
    local stream_count=$(echo "$js_summary" | sed -n 's/.*"streams"[[:space:]]*:[[:space:]]*\([0-9]\+\).*/\1/p' | head -n1)
    local consumer_count=$(echo "$js_summary" | sed -n 's/.*"consumers"[[:space:]]*:[[:space:]]*\([0-9]\+\).*/\1/p' | head -n1)
    local message_count=$(echo "$js_summary" | sed -n 's/.*"messages"[[:space:]]*:[[:space:]]*\([0-9]\+\).*/\1/p' | head -n1)
    if [ -z "$stream_count" ] || [ "$stream_count" = "0" ]; then
        local js_detail=$(curl -s 'http://localhost:8222/jsz?streams=true' 2>/dev/null)
        stream_count=$(awk 'BEGIN{c=0}/"name":"MARKET_DATA"|"name":"ORDERBOOK_SNAP"/{c++} END{print c+0}' <<<"$js_detail")
    fi

    echo ""
    if [ -n "$stream_count" ] && [ "$stream_count" -ge 1 ] 2>/dev/null; then
        log_info "JetStream: 正常"
        log_info "  - 流数量: $stream_count"
        log_info "  - 消费者数量: ${consumer_count:-0}"
        log_info "  - 消息数量: ${message_count:-0}"
        # 展示期望的 subjects 数
        if [ -f "$PROJECT_ROOT/scripts/js_init_market_data.yaml" ]; then
            local md_subjects=$(awk '/MARKET_DATA:/{f=1;next}/ORDERBOOK_SNAP:/{f=0} f && $1 ~ /^-/{c++} END{print c+0}' "$PROJECT_ROOT/scripts/js_init_market_data.yaml")
            local ob_subjects=$(awk '/ORDERBOOK_SNAP:/{f=1;next} f && $1 ~ /^-/{c++} END{print c+0}' "$PROJECT_ROOT/scripts/js_init_market_data.yaml")
            log_info "  - MARKET_DATA subjects(期望): ${md_subjects:-7}"
            log_info "  - ORDERBOOK_SNAP subjects(期望): ${ob_subjects:-1}"
        fi
    else
        log_warn "JetStream: 无法获取流信息"
        validation_passed=0
    fi

    # ClickHouse 数据验证
    if ! command -v clickhouse-client &> /dev/null; then
        log_warn "ClickHouse客户端未安装，跳过数据验证"
        return 1
    fi

    # 定义数据类型标签
    declare -A table_labels=(
        [trades]="trades(高频)" [orderbooks]="orderbooks(高频)" \
        [funding_rates]="funding_rates(低频)" [open_interests]="open_interests(低频)" \
        [liquidations]="liquidations(事件)" [lsr_top_positions]="lsr_top_positions(低频)" \
        [lsr_all_accounts]="lsr_all_accounts(低频)" [volatility_indices]="volatility_indices(低频)"
    )
    local tables=(trades orderbooks funding_rates open_interests liquidations lsr_top_positions lsr_all_accounts volatility_indices)

    # 热端数据统计
    echo ""
    log_info "ClickHouse 热端数据统计 (marketprism_hot):"
    declare -A hot_counts
    local hot_total=0
    local hot_high_freq_count=0
    local hot_low_freq_count=0

    for t in "${tables[@]}"; do
        local cnt=$(clickhouse-client --query "SELECT COUNT(*) FROM marketprism_hot.${t}" 2>/dev/null || echo "0")
        hot_counts[$t]=$cnt
        hot_total=$((hot_total + cnt))

        if [ "$cnt" -gt 0 ]; then
            log_info "  - ${table_labels[$t]}: $cnt 条"
            case "$t" in
                trades|orderbooks) hot_high_freq_count=$((hot_high_freq_count + 1)) ;;
                funding_rates|open_interests|lsr_top_positions|lsr_all_accounts) hot_low_freq_count=$((hot_low_freq_count + 1)) ;;
            esac
        else
            case "$t" in
                trades|orderbooks)
                    if [ "$is_fresh_start" -eq 1 ]; then
                        log_info "  - ${table_labels[$t]}: 0 条 (系统刚启动，等待中)"
                    else
                        log_warn "  - ${table_labels[$t]}: 0 条 (高频数据，应该有数据)"
                        validation_passed=0
                    fi
                    ;;
                liquidations|volatility_indices)
                    log_info "  - ${table_labels[$t]}: 0 条 (事件驱动，取决于市场活动)" ;;
                *)
                    log_info "  - ${table_labels[$t]}: 0 条 (低频数据，等待中)" ;;
            esac
        fi
    done

    # 冷端数据统计
    echo ""
    log_info "ClickHouse 冷端数据统计 (marketprism_cold):"
    declare -A cold_counts
    local cold_total=0
    local cold_high_freq_count=0

    for t in "${tables[@]}"; do
        local cnt=$(clickhouse-client --query "SELECT COUNT(*) FROM marketprism_cold.${t}" 2>/dev/null || echo "0")
        cold_counts[$t]=$cnt
        cold_total=$((cold_total + cnt))

        if [ "$cnt" -gt 0 ]; then
            log_info "  - ${table_labels[$t]}: $cnt 条"
            case "$t" in
                trades|orderbooks) cold_high_freq_count=$((cold_high_freq_count + 1)) ;;
            esac
        else
            case "$t" in
                trades|orderbooks)
                    if [ "$is_fresh_start" -eq 1 ]; then
                        log_info "  - ${table_labels[$t]}: 0 条 (系统刚启动，批量复制尚未执行)"
                    elif [ "${hot_counts[$t]}" -gt 0 ]; then
                        log_info "  - ${table_labels[$t]}: 0 条 (热端有数据，等待批量复制)"
                    else
                        log_info "  - ${table_labels[$t]}: 0 条 (热端也无数据)"
                    fi
                    ;;
                *)
                    log_info "  - ${table_labels[$t]}: 0 条" ;;
            esac
        fi
    done

    # 数据迁移状态分析
    echo ""
    if [ "$cold_total" -eq 0 ]; then
        if [ "$is_fresh_start" -eq 1 ]; then
            log_info "数据迁移状态: 系统刚启动（运行 ${system_uptime_minutes} 分钟），冷端为空是正常的"
            log_info "  提示: 采用‘定时批量复制’（默认每 1 分钟），请稍后再检查"
        elif [ "$hot_total" -gt 0 ]; then
            log_warn "数据迁移状态: 热端有 $hot_total 条数据，但冷端为空"
            log_warn "  可能原因: 1) 批量复制延时或未执行 2) 冷端不可用/复制失败"
            # 检查冷端服务是否运行
            if ! curl -sf http://localhost:8086/health >/dev/null 2>&1; then
                log_warn "  检测到冷端存储服务未运行，请启动冷端服务"
                validation_passed=0
            fi
        else
            log_info "数据迁移状态: 热端和冷端都无数据（系统可能刚启动或数据采集异常）"
        fi
    else
        # 计算迁移比例
        local migration_percentage=0
        if [ "$hot_total" -gt 0 ]; then
            migration_percentage=$((cold_total * 100 / hot_total))
        fi

        if [ "$migration_percentage" -gt 0 ]; then
            log_info "数据迁移状态: 正常（冷端数据量为热端的 ${migration_percentage}%）"
        else
            log_info "数据迁移状态: 正常（冷端有 $cold_total 条数据）"
        fi

        # 读取热端清理策略状态（用于调整冷>热提示等级），兼容未安装jq的环境
        local cleanup_enabled="false"
        if command -v jq >/dev/null 2>&1; then
            cleanup_enabled=$(curl -sf http://localhost:8085/health 2>/dev/null | jq -r '.replication.cleanup_enabled // false' 2>/dev/null)
        else
            # 若无 jq，则默认视为启用清理策略，避免因解析失败导致误判
            cleanup_enabled="true"
        fi
        if [ "$cleanup_enabled" != "true" ]; then cleanup_enabled="false"; fi

        # 验证数据一致性：冷端数据量应该 <= 热端数据量
        local inconsistent_tables=()
        for t in "${tables[@]}"; do
            if [ "${cold_counts[$t]}" -gt "${hot_counts[$t]}" ]; then
                inconsistent_tables+=("$t")
            fi
        done

        if [ ${#inconsistent_tables[@]} -gt 0 ]; then
            if [ "$cleanup_enabled" = "true" ]; then
                log_info "信息提示：热端已启用清理策略，冷端保留完整历史数据；以下表出现冷端>热端属正常："
                for t in "${inconsistent_tables[@]}"; do
                    log_info "  - $t: 热端=${hot_counts[$t]}, 冷端=${cold_counts[$t]}"
                done
                # 启用清理策略时，不将此视为健康检查失败
            else
                log_warn "数据一致性警告: 以下表的冷端数据量大于热端（异常）:"
                for t in "${inconsistent_tables[@]}"; do
                    log_warn "  - $t: 热端=${hot_counts[$t]}, 冷端=${cold_counts[$t]}"
                done
                validation_passed=0
            fi
        fi
    fi

    # 低频数据采集状态提示
    if [ "$hot_low_freq_count" -eq 0 ] && [ "$is_fresh_start" -eq 0 ]; then
        echo ""
        log_warn "低频数据提示: 所有低频数据类型都为 0，可能需要等待更长时间"
        log_warn "  低频数据包括: funding_rates, open_interests, lsr_top_positions, lsr_all_accounts"
        log_warn "  这些数据通常每分钟或每小时更新一次"
    fi

    # 复制延迟检测（热端与冷端最大时间戳差异）
    echo ""
    if [ "$is_fresh_start" -eq 1 ]; then
        log_info "复制延迟检测: 系统刚启动，暂不评估复制延迟"
    else
        log_info "复制延迟检测:"
        local REPL_LAG_WARN_MIN=${REPL_LAG_WARN_MIN:-60}
        for t in "${tables[@]}"; do
            local hot_max=$(clickhouse-client --query "SELECT toInt64(max(toUnixTimestamp64Milli(timestamp))) FROM marketprism_hot.${t}" 2>/dev/null || echo "0")
            local cold_max=$(clickhouse-client --query "SELECT toInt64(max(toUnixTimestamp64Milli(timestamp))) FROM marketprism_cold.${t}" 2>/dev/null || echo "0")
            [ -z "$hot_max" ] && hot_max=0
            [ -z "$cold_max" ] && cold_max=0
            if [ "$hot_max" -gt 0 ]; then
                local lag_min
                if [ "$cold_max" -gt 0 ]; then
                    lag_min=$(( (hot_max - cold_max) / 60000 ))
                    [ "$lag_min" -lt 0 ] && lag_min=0
                else
                    lag_min=999999
                fi
                log_info "  - $t: 冷端落后 ${lag_min} 分钟"
                if [ "$lag_min" -gt "$REPL_LAG_WARN_MIN" ]; then
                    log_warn "  - $t: 复制延迟超过阈值(${REPL_LAG_WARN_MIN}分钟)"
                    validation_passed=0
                fi
            fi
        done
    fi

    # 最终验证结果
    echo ""
    if [ "$validation_passed" -eq 1 ] && [ "$hot_total" -gt 0 ]; then
        log_info "端到端数据流: 完整验证通过 ✅"
        log_info "  - JetStream: $stream_count 个流，${message_count:-0} 条消息"
        log_info "  - 热端数据: $hot_total 条（高频: $hot_high_freq_count/2 类型有数据）"
        log_info "  - 冷端数据: $cold_total 条（高频: $cold_high_freq_count/2 类型有数据）"
        return 0
    elif [ "$hot_total" -gt 0 ]; then
        log_warn "端到端数据流: 部分验证通过（有数据但存在警告）⚠️"
        return 0
    else
        log_warn "端到端数据流: 暂无数据，系统可能仍在初始化"
        return 1
    fi
}

# 🔧 新增：系统级数据完整性检查
check_system_data_integrity() {
    log_section "MarketPrism 系统数据完整性检查"

    local overall_exit_code=0

    echo ""
    log_step "1. 检查数据存储服务数据完整性..."
    bash "$STORAGE_SCRIPT" integrity
    local storage_exit=$?
    if [ $storage_exit -eq 0 ]; then
        log_info "数据存储服务数据完整性检查：通过"
    elif [ $storage_exit -eq 1 ]; then
        log_warn "数据存储服务数据完整性检查：存在警告 (exit=$storage_exit)"
        # 视为警告，不直接判定为失败
    else
        log_warn "数据存储服务数据完整性检查：发现问题 (exit=$storage_exit)"
        overall_exit_code=1
    fi

    echo ""
    log_step "2. 检查端到端数据流..."
    validate_end_to_end_data_flow
    local e2e_exit=$?
    if [ $e2e_exit -eq 0 ]; then
        log_info "端到端数据流验证：通过"
    else
        log_warn "端到端数据流验证：发现问题 (exit=$e2e_exit)"
        overall_exit_code=1
    fi

    echo ""
    if [ $overall_exit_code -eq 0 ]; then
        log_info "系统数据完整性检查全部通过"
    else
        log_warn "系统数据完整性检查发现问题，建议运行修复"
        log_warn "💡 建议运行: $0 repair"
    fi

    return $overall_exit_code
}

# 🔧 新增：系统级一键修复
repair_system() {
    log_section "MarketPrism 系统一键修复"

    local overall_exit_code=0

    echo ""
    log_step "1. 修复数据存储服务数据迁移问题..."
    if bash "$STORAGE_SCRIPT" repair; then
        log_info "数据存储服务修复成功"
    else
        log_error "数据存储服务修复失败"
        overall_exit_code=1
    fi

    echo ""
    log_step "2. 重新验证系统数据完整性..."
    if check_system_data_integrity; then
        log_info "修复后验证通过"
    else
        log_warn "修复后仍有问题，可能需要手动处理"
        overall_exit_code=1
    fi

    return $overall_exit_code
}

# ============================================================================
# 初始化函数
# ============================================================================

init_all() {
    log_section "MarketPrism 系统初始化"

    # 🔧 运行增强初始化脚本
    echo ""
    log_step "0. 运行增强初始化（依赖检查、环境准备、配置修复）..."
    if [ -f "$PROJECT_ROOT/scripts/enhanced_init.sh" ]; then
        bash "$PROJECT_ROOT/scripts/enhanced_init.sh" || { log_error "增强初始化失败"; return 1; }
    else
        log_warn "增强初始化脚本不存在，跳过"
    fi

    echo ""
    log_step "1. 安装并初始化NATS消息代理..."
    bash "$NATS_SCRIPT" install-deps || log_warn "NATS依赖安装返回非零，继续尝试初始化"
    bash "$NATS_SCRIPT" init || { log_error "NATS初始化失败"; return 1; }

    echo ""
    log_step "2. 安装并初始化数据存储服务..."
    bash "$STORAGE_SCRIPT" install-deps || log_warn "存储服务依赖安装返回非零，继续尝试初始化"
    bash "$STORAGE_SCRIPT" init || { log_error "数据存储服务初始化失败"; return 1; }

    echo ""
    log_step "3. 安装并初始化数据采集器..."
    bash "$COLLECTOR_SCRIPT" install-deps || log_warn "采集器依赖安装返回非零，继续尝试初始化"
    bash "$COLLECTOR_SCRIPT" init || { log_error "数据采集器初始化失败"; return 1; }

    echo ""
    log_info "MarketPrism 系统初始化完成"
}

# ============================================================================
# 启动函数
# ============================================================================

start_all() {
    log_section "MarketPrism 系统启动"

    echo ""
    log_step "1. 启动NATS消息代理..."
    bash "$NATS_SCRIPT" start || { log_error "NATS启动失败"; return 1; }

    # 🔧 等待NATS完全启动
    echo ""
    log_step "等待NATS完全启动..."
    wait_for_service "NATS" "http://localhost:8222/healthz" 60 "ok"

    echo ""
    log_step "2. 启动热端存储服务..."
    bash "$STORAGE_SCRIPT" start hot || { log_error "热端存储启动失败"; return 1; }

    # 🔧 等待热端存储完全启动
    echo ""
    log_step "等待热端存储完全启动..."
    wait_for_service "热端存储" "http://localhost:8085/health" 60 "healthy"

    echo ""
    log_step "3. 启动数据采集器..."
    bash "$COLLECTOR_SCRIPT" start || { log_error "数据采集器启动失败"; return 1; }

    # 🔧 等待数据采集器完全启动（允许超时，因为健康检查端点可能未实现）
    echo ""
    log_step "等待数据采集器完全启动..."
    wait_for_service "数据采集器" "http://localhost:8087/health" 120 '"status": "healthy"'

    echo ""
    log_step "4. 启动冷端存储服务..."
    bash "$STORAGE_SCRIPT" start cold || { log_error "冷端存储启动失败"; return 1; }

    # 🔧 等待冷端存储完全启动
    echo ""
    log_step "等待冷端存储完全启动..."
    wait_for_service "冷端存储" "http://localhost:8086/health" 60 '"status": "healthy"'

    echo ""
    log_info "MarketPrism 系统启动完成"

    # 🔧 增强的服务状态检查
    echo ""
    log_step "等待10秒后进行完整健康检查..."
    sleep 10
    health_all
}

# ============================================================================
# 停止函数
# ============================================================================

stop_all() {
    log_section "MarketPrism 系统停止"

    echo ""
    log_step "1. 停止数据采集器..."
    bash "$COLLECTOR_SCRIPT" stop || log_warn "数据采集器停止失败"

    echo ""
    log_step "2. 停止冷端存储服务..."
    bash "$STORAGE_SCRIPT" stop cold || log_warn "冷端存储停止失败"

    echo ""
    log_step "3. 停止热端存储服务..."
    bash "$STORAGE_SCRIPT" stop hot || log_warn "热端存储停止失败"

    echo ""
    log_step "4. 停止NATS消息代理..."
    bash "$NATS_SCRIPT" stop || log_warn "NATS停止失败"

    echo ""
    log_info "MarketPrism 系统停止完成"
}

# ============================================================================
# 重启函数
# ============================================================================

restart_all() {
    log_section "MarketPrism 系统重启"

    stop_all

    echo ""
    log_step "等待5秒后重新启动..."
    sleep 5

    start_all
}

# ============================================================================
# 状态检查函数
# ============================================================================

status_all() {
    log_section "MarketPrism 系统状态"

    echo ""
    log_step "NATS消息代理状态:"
    bash "$NATS_SCRIPT" status

    echo ""
    log_step "数据存储服务状态:"
    bash "$STORAGE_SCRIPT" status

    echo ""
    log_step "数据采集器状态:"
    bash "$COLLECTOR_SCRIPT" status
}

# ============================================================================
# 健康检查函数
# ============================================================================

health_all() {
    log_section "MarketPrism 系统健康检查"

    local exit_code=0

    echo ""
    log_step "检查NATS消息代理..."
    if ! bash "$NATS_SCRIPT" health; then
        exit_code=1
    fi

    echo ""
    log_step "检查数据存储服务..."
    if ! bash "$STORAGE_SCRIPT" health; then
        exit_code=1
    fi

    echo ""
    log_step "检查数据采集器..."
    if ! bash "$COLLECTOR_SCRIPT" health; then
        exit_code=1
    fi

    # 🔧 端到端数据流验证
    echo ""
    log_step "端到端数据流验证..."
    validate_end_to_end_data_flow

    echo ""
    if [ $exit_code -eq 0 ]; then
        log_info "所有服务健康检查通过 ✅"
    else
        log_error "部分服务健康检查失败 ❌"
    fi

    return $exit_code
}

# ============================================================================
# 清理函数
# ============================================================================

clean_all() {
    log_section "MarketPrism 系统清理"

    echo ""
    log_step "清理数据采集器..."
    bash "$COLLECTOR_SCRIPT" clean

    echo ""
    log_step "清理数据存储服务..."
    bash "$STORAGE_SCRIPT" clean --force

    echo ""
    log_info "系统清理完成"
}

# ============================================================================
# 快速诊断函数
# ============================================================================

diagnose() {
    log_section "MarketPrism 系统快速诊断"

    echo ""
    log_step "1. 检查端口占用..."
    echo "关键端口监听状态:"
    ss -ltnp | grep -E ':(4222|8222|8123|8085|8086|8087)' || echo "  无相关端口监听"

    echo ""
    log_step "2. 检查进程状态..."
    echo "MarketPrism进程:"
    ps aux | grep -E '(nats-server|main.py|unified_collector_main.py)' | grep -v grep || echo "  无相关进程"

    echo ""
    log_step "3. 检查锁文件..."
    echo "实例锁文件:"
    ls -l /tmp/marketprism_*.lock 2>/dev/null || echo "  无锁文件"

    echo ""
    log_step "4. 检查Docker容器..."
    echo "MarketPrism容器:"
    docker ps --filter "name=marketprism" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" || echo "  无相关容器"

    echo ""
    log_step "5. 执行健康检查..."
    health_all
}

# ============================================================================
# 主函数
# ============================================================================

show_usage() {
    cat << EOF
${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}
${CYAN}  MarketPrism 系统统一管理脚本${NC}
${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}

用法: $0 <command>

基础命令:
    init        初始化整个系统（首次部署使用）
    start       启动所有服务（按正确顺序）
    stop        停止所有服务（按正确顺序）
    restart     重启所有服务
    status      查看所有服务状态
    health      执行完整健康检查
    diagnose    快速诊断系统问题
    clean       清理锁文件和临时数据

🔧 数据完整性命令:
    integrity   检查系统数据完整性
    repair      一键修复数据迁移问题

服务启动顺序:
    1. NATS消息代理 (4222, 8222)
    2. 热端存储服务 (8085)
    3. 数据采集器 (8087)
    4. 冷端存储服务 (8086)

示例:
    $0 init         # 首次部署初始化
    $0 start        # 启动所有服务
    $0 stop         # 停止所有服务
    $0 restart      # 重启所有服务
    $0 status       # 查看状态
    $0 integrity    # 检查数据完整性
    $0 repair       # 修复数据迁移问题
    $0 health       # 健康检查
    $0 diagnose     # 快速诊断
    $0 clean        # 清理系统

${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}
EOF
}

main() {
    local command="${1:-}"

    case "$command" in
        init)
            init_all
            ;;
        start)
            start_all
            ;;
        stop)
            stop_all
            ;;
        restart)
            restart_all
            ;;
        status)
            status_all
            ;;
        health)
            health_all
            ;;
        diagnose)
            diagnose
            ;;
        clean)
            clean_all
            ;;
        integrity)
            check_system_data_integrity
            ;;
        repair)
            repair_system
            ;;
        *)
            show_usage
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"
