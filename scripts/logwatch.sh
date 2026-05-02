#!/usr/bin/env bash
# ── HR Bot 日志异常监控 ────────────────────────────────────
# 检查 server.log 中最近 15 分钟的 ERROR 日志
# 如果发现连续重复错误，写入告警
# 被 systemd timer 调用（每 15 分钟）
# ──────────────────────────────────────────────────────────
set -euo pipefail

LOG_FILE="/home/admin/hr-bot/logs/server.log"
ALERT_LOG="/home/admin/hr-bot/logs/alert.log"
STAMP_FILE="/tmp/hr-bot-logwatch-stamp"

mkdir -p "$(dirname "$LOG_FILE")"
mkdir -p "$(dirname "$ALERT_LOG")"

if [ ! -f "$LOG_FILE" ]; then
    exit 0
fi

timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

# 上次检查的位置（行号）
LAST_LINE=$(cat "$STAMP_FILE" 2>/dev/null || echo 0)
TOTAL_LINES=$(wc -l < "$LOG_FILE")

if [ "$TOTAL_LINES" -le "$LAST_LINE" ]; then
    # 日志没新增，跳过
    echo "$TOTAL_LINES" > "$STAMP_FILE"
    exit 0
fi

# 检查新日志中的 ERROR / CRITICAL / Traceback
NEW_ERRORS=$(sed -n "${LAST_LINE},${TOTAL_LINES}p" "$LOG_FILE" \
    | grep -i -E '(ERROR|CRITICAL|Traceback|Exception|调用失败)' \
    || true)

if [ -n "$NEW_ERRORS" ]; then
    ERROR_COUNT=$(echo "$NEW_ERRORS" | wc -l)
    echo "$(timestamp) [日志监控] 发现 ${ERROR_COUNT} 条新异常" >> "$ALERT_LOG"
    echo "$NEW_ERRORS" | tail -5 >> "$ALERT_LOG"
    echo "---" >> "$ALERT_LOG"
fi

echo "$TOTAL_LINES" > "$STAMP_FILE"
