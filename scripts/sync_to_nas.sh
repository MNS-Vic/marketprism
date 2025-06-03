#!/bin/bash
# 数据同步到NAS脚本

# 配置
SOURCE_DIR="/app/data"
TARGET_HOST="${NAS_HOST:-nas-server}"
TARGET_USER="${NAS_USER:-datauser}"
TARGET_DIR="${NAS_PATH:-/data/crypto}"
SSH_KEY="${SSH_KEY_FILE:-/app/keys/id_rsa}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

# 日志配置
LOG_FILE="/var/log/marketprism/sync.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# 创建日志函数
log() {
    local level=$1
    local message=$2
    echo "[$TIMESTAMP] [$level] $message" >> $LOG_FILE
    echo "[$TIMESTAMP] [$level] $message"
}

log "INFO" "开始同步数据到NAS: $TARGET_HOST:$TARGET_DIR"

# 检查源目录是否存在
if [ ! -d "$SOURCE_DIR" ]; then
    log "ERROR" "源目录不存在: $SOURCE_DIR"
    exit 1
fi

# 确保目标目录存在
ssh -i $SSH_KEY $TARGET_USER@$TARGET_HOST "mkdir -p $TARGET_DIR" || {
    log "ERROR" "无法在NAS上创建目标目录: $TARGET_DIR"
    exit 1
}

# 使用rsync同步数据
rsync -avz --progress -e "ssh -i $SSH_KEY" \
    $SOURCE_DIR/ $TARGET_USER@$TARGET_HOST:$TARGET_DIR/ || {
    log "ERROR" "rsync同步失败"
    exit 1
}

log "INFO" "数据同步完成"

# 清理本地旧数据
if [ "$RETENTION_DAYS" -gt 0 ]; then
    log "INFO" "清理${RETENTION_DAYS}天前的本地数据"
    find $SOURCE_DIR -type f -mtime +$RETENTION_DAYS -delete
    find $SOURCE_DIR -type d -empty -delete
    log "INFO" "本地数据清理完成"
fi

log "INFO" "同步过程完成"
exit 0 