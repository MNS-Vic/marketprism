#!/bin/bash

################################################################################
# MarketPrism 增强初始化脚本
#
# 基于端到端验证过程中发现的问题，提供完整的一键初始化功能
# 包括：依赖检查、环境准备、配置修复、服务初始化
################################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 颜色和符号
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 默认开启APT自动安装（可通过环境变量覆盖）
export ALLOW_APT="${ALLOW_APT:-1}"

log_info() { echo -e "${GREEN}✅ $1${NC}"; }
log_warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error() { echo -e "${RED}❌ $1${NC}"; }
log_step() { echo -e "${BLUE}🔹 $1${NC}"; }
log_section() {
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# 固定 Python 版本（强约束）
REQUIRED_PYTHON="python3.11"
PY_BIN=""
# 仅允许 Python 3.11；可选自动安装（需 ALLOW_INSTALL=1）
try_install_python311() {
    # 尽量根据发行版选择安装方式；默认仅支持 Debian/Ubuntu（其他发行版建议人工或使用 pyenv）
    local os_id os_like os_ver
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        os_id="${ID:-}"
        os_like="${ID_LIKE:-}"
        os_ver="${VERSION_ID:-}"
    fi

    if command -v apt-get >/dev/null 2>&1; then
        # Debian/Ubuntu 系
        if [ "$os_id" = "ubuntu" ] || echo "$os_like" | grep -qi debian; then
            # Ubuntu 24.04 官方源无 3.11，添加 deadsnakes
            if [ "$os_id" = "ubuntu" ]; then
                if command -v sudo >/dev/null 2>&1; then
                    sudo -n apt-get update -y >/dev/null 2>&1 || true
                    sudo -n apt-get install -y software-properties-common >/dev/null 2>&1 || true
                    sudo -n add-apt-repository -y ppa:deadsnakes/ppa >/dev/null 2>&1 || true
                    sudo -n apt-get update -y >/dev/null 2>&1 || true
                    sudo -n apt-get install -y python3.11 python3.11-venv >/dev/null 2>&1 || true
                else
                    apt-get update -y >/dev/null 2>&1 || true
                    apt-get install -y software-properties-common >/dev/null 2>&1 || true
                    add-apt-repository -y ppa:deadsnakes/ppa >/dev/null 2>&1 || true
                    apt-get update -y >/dev/null 2>&1 || true
                    apt-get install -y python3.11 python3.11-venv >/dev/null 2>&1 || true
                fi
            else
                # Debian 等：直接尝试
                if command -v sudo >/dev/null 2>&1; then
                    sudo -n apt-get update -y >/dev/null 2>&1 || true
                    sudo -n apt-get install -y python3.11 python3.11-venv >/dev/null 2>&1 || true
                else
                    apt-get update -y >/dev/null 2>&1 || true
                    apt-get install -y python3.11 python3.11-venv >/dev/null 2>&1 || true
                fi
            fi
        fi
    elif command -v dnf >/dev/null 2>&1; then
        # Fedora/CentOS Stream
        if command -v sudo >/dev/null 2>&1; then
            sudo -n dnf install -y python3.11 python3.11-venv >/dev/null 2>&1 || true
        else
            dnf install -y python3.11 python3.11-venv >/dev/null 2>&1 || true
        fi
    elif command -v yum >/dev/null 2>&1; then
        # RHEL/CentOS 旧系（可能需要 EPEL/IUS，用户需自行准备）
        if command -v sudo >/dev/null 2>&1; then
            sudo -n yum install -y python3.11 >/dev/null 2>&1 || true
        else
            yum install -y python3.11 >/dev/null 2>&1 || true
        fi
    elif command -v zypper >/dev/null 2>&1; then
        # openSUSE（包名通常为 python311）
        if command -v sudo >/dev/null 2>&1; then
            sudo -n zypper -n install python311 >/dev/null 2>&1 || true
        else
            zypper -n install python311 >/dev/null 2>&1 || true
        fi
    elif command -v apk >/dev/null 2>&1; then
        # Alpine 通常只提供 python3 主版本，严格 3.11 需自编译或 pyenv；此处仅尝试
        apk add --no-cache python3 >/dev/null 2>&1 || true
    fi

    if command -v python3.11 >/dev/null 2>&1; then
        PY_BIN="python3.11"
        return 0
    fi
    return 1
}

ensure_required_python() {
    # 强制使用 python3.11；不接受 3.12
    if command -v "$REQUIRED_PYTHON" >/dev/null 2>&1; then
        PY_BIN="$REQUIRED_PYTHON"
        return 0
    fi
    log_warn "未检测到 $REQUIRED_PYTHON"

    if [ "${ALLOW_INSTALL:-0}" = "1" ]; then
        log_step "ALLOW_INSTALL=1 已启用，尝试自动安装 $REQUIRED_PYTHON..."
        if try_install_python311; then
            log_info "已安装 $REQUIRED_PYTHON"
            return 0
        fi
        log_error "自动安装 $REQUIRED_PYTHON 失败，请检查权限或网络，或手动安装后重试"
        return 1
    else
        log_error "缺少 $REQUIRED_PYTHON，未设置 ALLOW_INSTALL=1，无法自动安装。请先安装或设置 ALLOW_INSTALL=1 后重试。"
        return 1
    fi
}

# 检查系统依赖
check_system_dependencies() {
    log_section "检查系统依赖"

    # 固定 Python 版本：确保 REQUIRED_PYTHON 存在
    if ! ensure_required_python; then
        exit 1
    fi
    # 打印所用 Python 版本
    local PY_VER
    PY_VER=$($PY_BIN --version 2>/dev/null || echo "unknown")
    log_info "Python: ${PY_VER} (${PY_BIN})"

    # 检查curl
    if ! command -v curl &> /dev/null; then
        log_error "curl 未安装"
        exit 1
    fi
    log_info "curl: 已安装"

    # 检查Docker（可选）
    if command -v docker &> /dev/null; then
        log_info "Docker: $(docker --version)"
    else
        log_warn "Docker 未安装（可选）"

    fi
}

# 创建统一虚拟环境
# 在需要时为venv注入pip（避免ensurepip故障）
install_pip_into_venv() {
    local venv_path="$1"
    local py_bin="$venv_path/bin/python"
    local pip_bin="$venv_path/bin/pip"
    if [ -x "$pip_bin" ]; then
        return 0
    fi
    log_step "为虚拟环境安装pip（get-pip.py）..."
    local tmp_gp="/tmp/get-pip.py"
    curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "$tmp_gp" || {
        log_warn "下载get-pip.py失败，尝试备用URL"
        curl -fsSL https://bootstrap.pypa.io/pip/get-pip.py -o "$tmp_gp" || return 1
    }
    "$py_bin" "$tmp_gp" || return 1
    "$pip_bin" --version >/dev/null 2>&1
}

create_unified_venv() {
    log_section "创建统一虚拟环境"

    local venv_path="$PROJECT_ROOT/venv-unified"

    # 先确保系统具备 venv 能力（Debian/Ubuntu 常见缺失）
    if ! $PY_BIN -c "import ensurepip" >/dev/null 2>&1; then
        log_step "安装 python venv/ensurepip 组件..."
        if command -v apt-get >/dev/null 2>&1 && [ "${ALLOW_APT:-1}" = "1" ]; then
            if command -v sudo >/dev/null 2>&1; then
                sudo -n apt-get update -y >/dev/null 2>&1 || true
                sudo -n apt-get install -y python3-venv python3.11-venv >/dev/null 2>&1 || true
            else
                apt-get update -y >/dev/null 2>&1 || true
                apt-get install -y python3-venv python3.11-venv >/dev/null 2>&1 || true
            fi
        else
            log_warn "系统无apt或未授权，跳过apt安装，将使用virtualenv/get-pip回退方案"
        fi
    fi

    # 创建或修复统一虚拟环境
    if [ ! -d "$venv_path" ]; then
        log_step "创建统一虚拟环境..."
        if ! $PY_BIN -m venv --without-pip "$venv_path"; then
            log_warn "使用 $PY_BIN 创建虚拟环境失败，尝试备用解释器..."

            for cand in python3.11; do
                if command -v "$cand" >/dev/null 2>&1 && "$cand" --version >/dev/null 2>&1; then
                    if "$cand" -m venv "$venv_path"; then
                        PY_BIN="$cand"
                        log_info "已使用备用解释器创建虚拟环境: $PY_BIN"
                        break

                    fi
                fi
            done
            if [ ! -f "$venv_path/bin/activate" ]; then
                log_error "虚拟环境创建失败"
                return 1
            fi
        fi
    fi
    if [ ! -f "$venv_path/bin/activate" ]; then

        # 确保在venv中安装pip
        if ! install_pip_into_venv "$venv_path"; then
            log_warn "get-pip 失败，继续但pip可能不可用"
        fi

        # 尝试修复：重新创建
        log_step "修复虚拟环境激活脚本..."
        rm -rf "$venv_path"
        if ! $PY_BIN -m venv --without-pip "$venv_path"; then
            log_warn "使用 $PY_BIN 重新创建虚拟环境失败，尝试备用解释器..."
            for cand in python3.11; do
                if command -v "$cand" >/dev/null 2>&1 && "$cand" --version >/dev/null 2>&1; then
                    if "$cand" -m venv "$venv_path"; then
                        PY_BIN="$cand"
                        log_info "已使用备用解释器重新创建虚拟环境: $PY_BIN"
                        break
                    fi
                fi
            done
            if [ ! -f "$venv_path/bin/activate" ]; then
                log_error "虚拟环境创建失败"
                return 1
            fi
        fi
        # 确保重新创建后在venv中安装pip
        if ! install_pip_into_venv "$venv_path"; then
            log_warn "get-pip 失败（重建后）"
        fi

    fi

    # 确保 pip 存在于 venv 内（若缺失则强制注入）
    if [ ! -x "$venv_path/bin/pip" ]; then
        log_step "为虚拟环境强制注入pip（get-pip.py）..."
        curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py || { log_error "下载 get-pip.py 失败"; return 1; }
        "$venv_path/bin/python" /tmp/get-pip.py || { log_error "get-pip 安装失败"; return 1; }
    fi

    # 激活并校验指向（fail fast，避免依赖被装到 ~/.local）
    source "$venv_path/bin/activate"
    local WHICH_PIP
    local WHICH_PY
    WHICH_PIP="$(command -v pip || true)"
    WHICH_PY="$(command -v python || true)"
    if [[ "$WHICH_PIP" != "$venv_path/bin/pip" ]] || [[ "$WHICH_PY" != "$venv_path/bin/python" ]]; then
        log_error "虚拟环境未正确激活: which pip=$WHICH_PIP, which python=$WHICH_PY（期望在 $venv_path/bin 下）。"
        return 1
    fi

    # 升级pip后按项目要求安装依赖（严格安装到 venv）
    pip install -q --upgrade pip || true
    if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
        log_step "按 requirements.txt 安装依赖..."
        pip install -q -r "$PROJECT_ROOT/requirements.txt" || { log_error "requirements 依赖安装失败"; return 1; }
    else
        log_warn "未发现 requirements.txt，跳过集中安装"
    fi

    # 健康校验：确认统一虚拟环境可用
    if ! "$venv_path/bin/python3" --version >/dev/null 2>&1; then
        log_warn "统一虚拟环境损坏，自动重建: $venv_path"
        rm -rf "$venv_path"
        $PY_BIN -m venv "$venv_path" || { log_error "虚拟环境创建失败"; return 1; }
    fi
    if ! "$venv_path/bin/pip" --version >/dev/null 2>&1; then
        log_warn "统一虚拟环境pip异常，尝试修复..."
        "$venv_path/bin/python3" -m ensurepip --upgrade >/dev/null 2>&1 || true
        "$venv_path/bin/pip" install --upgrade pip -q || true
    fi

    log_info "统一虚拟环境创建完成: $venv_path"

    # 为每个模块创建/修复符号链接（若已存在但目标错误则纠正）
    for module in "message-broker" "data-storage-service" "data-collector"; do
        local module_venv="$PROJECT_ROOT/services/$module/venv"
        if [ -L "$module_venv" ]; then
            local target=$(readlink -f "$module_venv" || echo "")
            if [ "$target" != "$venv_path" ]; then
                rm -f "$module_venv"
                ln -sf "$venv_path" "$module_venv"
                log_info "修复 $module 虚拟环境链接 -> $venv_path"
            fi
        elif [ ! -e "$module_venv" ]; then
            ln -sf "$venv_path" "$module_venv"
            log_info "创建 $module 虚拟环境链接"
        else
            # 存在非符号链接实体，保守处理：提示人工确认
            log_warn "$module 的 venv 存在非符号链接目录/文件，请确认是否需要改为链接到统一环境"
        fi
    done
}

# 检查和修复ClickHouse Schema
fix_clickhouse_schema() {
    log_section "检查和修复ClickHouse Schema"

    local schema_file="$PROJECT_ROOT/services/data-storage-service/config/clickhouse_schema.sql"

    if [ -f "$schema_file" ]; then
        log_info "已检测到权威 Schema 文件: $schema_file"
        log_info "无需再创建简化 schema；后续均以权威 schema 为准（忽略 TTL 差异）"
    else
        log_error "缺少权威 Schema 文件: $schema_file"
    fi
}

# 检查端口冲突
check_port_conflicts() {
    log_section "检查端口冲突"

    local ports=(4222 8222 8123 8085 8086 8087 9093)
    local conflicts=()

    for port in "${ports[@]}"; do
        if ss -ltn | grep -q ":$port "; then
            conflicts+=("$port")
        fi
    done

    if [ ${#conflicts[@]} -gt 0 ]; then
        log_warn "发现端口冲突: ${conflicts[*]}"
        log_step "尝试清理冲突进程..."

        for port in "${conflicts[@]}"; do
            local pid=$(ss -ltnp | grep ":$port " | grep -o 'pid=[0-9]*' | cut -d= -f2 | head -1)
            if [ -n "$pid" ]; then
                log_info "终止占用端口 $port 的进程 (PID: $pid)"
                kill "$pid" 2>/dev/null || true
                sleep 1
            fi
        done
    else
        log_info "所有端口空闲"
    fi
}

# 预检查配置文件
precheck_configs() {
    log_section "预检查配置文件"

    local configs=(
        "$PROJECT_ROOT/services/message-broker/config/unified_message_broker.yaml"
        "$PROJECT_ROOT/services/hot-storage-service/config/hot_storage_config.yaml"
        "$PROJECT_ROOT/services/data-collector/config/collector/unified_data_collection.yaml"
    )

    for config in "${configs[@]}"; do
        if [ -f "$config" ]; then
            log_info "配置文件存在: $(basename "$config")"
        else
            log_warn "配置文件缺失: $config"
        fi
    done
}

# 🔧 新增：自动问题检测和修复
auto_detect_and_fix_issues() {
    log_section "自动问题检测和修复"

    # 检查ClickHouse状态
    check_clickhouse_status

    # 检查虚拟环境
    check_virtual_environments

    # 检查配置文件完整性
    check_configuration_integrity

    log_info "自动问题检测和修复完成"
}

# 🔧 新增：检查ClickHouse状态
check_clickhouse_status() {
    log_info "检查ClickHouse状态..."

    if ! command -v clickhouse-client &> /dev/null; then
        log_warn "ClickHouse客户端未安装"
        return 0  # 在init阶段不强制安装
    fi

    # 检查ClickHouse服务状态
    if ! pgrep -f "clickhouse-server" > /dev/null; then
        log_info "ClickHouse服务未运行，尝试启动..."
        sudo clickhouse start 2>/dev/null || true
        sleep 3
    fi

    # 验证连接
    if clickhouse-client --query "SELECT 1" >/dev/null 2>&1; then
        log_info "ClickHouse状态正常"
    else
        log_warn "ClickHouse连接失败，将在服务初始化时处理"
    fi
}

# 🔧 新增：检查虚拟环境
check_virtual_environments() {
    log_info "检查虚拟环境..."

    local services=("data-collector" "data-storage-service" "message-broker")

    for service in "${services[@]}"; do
        local venv_path="$PROJECT_ROOT/services/$service/venv"
        if [ ! -d "$venv_path" ]; then
            log_warn "服务 $service 的虚拟环境不存在，将在初始化时创建"
        else
            log_info "服务 $service 的虚拟环境存在"
        fi
    done
}

# 🔧 新增：检查配置文件完整性
check_configuration_integrity() {
    log_info "检查配置文件完整性..."

    # 检查关键配置文件
    local config_files=(
        "services/hot-storage-service/config/hot_storage_config.yaml"
        "services/data-collector/config/collector/unified_data_collection.yaml"
    )

    for config_file in "${config_files[@]}"; do
        local full_path="$PROJECT_ROOT/$config_file"
        if [ ! -f "$full_path" ]; then
            log_warn "配置文件不存在: $config_file"
        else
            log_info "配置文件存在: $config_file"
        fi
    done
}
# 配置日志轮转（自动检测 sudo，可回退到用户级 cron）
setup_logrotate() {
    log_section "配置日志轮转"

    # 构造基于当前项目路径的动态配置，避免硬编码 /home/ubuntu/marketprism
    local cfg_content="${PROJECT_ROOT}/services/data-collector/logs/*.log\n${PROJECT_ROOT}/services/message-broker/logs/*.log\n${PROJECT_ROOT}/services/data-storage-service/logs/*.log {\n    daily\n    rotate 7\n    compress\n    missingok\n    notifempty\n    copytruncate\n    dateext\n    dateformat -%Y%m%d\n}"

    # 尝试确保 logrotate 可用
    local logrotate_bin
    logrotate_bin=$(command -v logrotate || echo "")
    if [ -z "$logrotate_bin" ]; then
        log_step "logrotate 未安装，尝试自动安装..."
        if command -v sudo >/dev/null 2>&1; then
            # 无交互尝试，失败则静默跳过


            sudo -n apt-get update -y >/dev/null 2>&1 || true
            sudo -n apt-get install -y logrotate >/dev/null 2>&1 || true
            logrotate_bin=$(command -v logrotate || echo "")
        fi
    fi

    # 优先使用系统级安装（需要免密 sudo），否则退回用户级 cron
    if command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
        echo -e "$cfg_content" | sudo tee /etc/logrotate.d/marketprism >/dev/null
        if [ -n "$logrotate_bin" ]; then
            sudo "$logrotate_bin" -d /etc/logrotate.d/marketprism >/dev/null 2>&1 || true
        fi
        log_info "系统级日志轮转已配置: /etc/logrotate.d/marketprism"
    else
        mkdir -p "$HOME/.marketprism"
        local user_cfg="$HOME/.marketprism/marketprism.logrotate"
        echo -e "$cfg_content" > "$user_cfg"
        local state_file="$HOME/.marketprism/logrotate.status"
        # 确定 logrotate 路径（cron 下 PATH 精简，使用绝对路径更稳妥）
        local lb
        lb=$(command -v logrotate || echo "/usr/sbin/logrotate")
        # 若条目不存在则追加到 crontab（每10分钟）
        local cron_line="*/10 * * * * ${lb} -s ${state_file} ${user_cfg} >/dev/null 2>&1"
        (crontab -l 2>/dev/null | grep -Fv "marketprism.logrotate"; echo "$cron_line") | crontab -
        log_info "用户级日志轮转已配置（cron 每10分钟执行）: $user_cfg"
    fi
}


# 主函数
main() {
    log_section "MarketPrism 增强初始化"

    check_system_dependencies
    check_port_conflicts
    create_unified_venv
    fix_clickhouse_schema
    precheck_configs

    # 🔧 新增：自动问题检测和修复
    auto_detect_and_fix_issues

    # 配置日志轮转
    setup_logrotate

    log_section "初始化完成"
    log_info "现在可以运行以下命令启动系统："
    log_info "  ./scripts/manage_all.sh init"
    log_info "  ./scripts/manage_all.sh start"
    log_info "  ./scripts/manage_all.sh health"
}

main "$@"
