#!/usr/bin/env bash
# ── HR Bot 健康检查脚本 ────────────────────────────────────
# 检查 /health 端点，失败时重启服务并写入告警
# 被 systemd timer 定时调用（每 5 分钟）
# ──────────────────────────────────────────────────────────
set -euo pipefail

SERVICE="hr-bot"
HEALTH_URL="http://localhost:8000/health"
HEALTH_LOG="/home/admin/hr-bot/logs/healthcheck.log"
ALERT_LOG="/home/admin/hr-bot/logs/alert.log"
MAX_FAILURES=3
FAILURE_COUNTER_FILE="/tmp/hr-bot-health-failures"

mkdir -p "$(dirname "$HEALTH_LOG")"
mkdir -p "$(dirname "$ALERT_LOG")"

timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

log_health() {
    echo "$(timestamp) $*" >> "$HEALTH_LOG"
}

log_alert() {
    echo "$(timestamp) [ALERT] $*" >> "$ALERT_LOG"
    echo "$(timestamp) [ALERT] $*" >> "$HEALTH_LOG"
}

# 请求健康端点
RESPONSE=$(curl -s --max-time 10 "$HEALTH_URL" 2>&1) || true

if echo "$RESPONSE" | grep -q '"status":"ok"'; then
    log_health "OK - 健康检查通过"
    # 重置失败计数
    rm -f "$FAILURE_COUNTER_FILE"
    exit 0
fi

# 健康检查失败
FAILURES=$(( $(cat "$FAILURE_COUNTER_FILE" 2>/dev/null || echo 0) + 1 ))
echo "$FAILURES" > "$FAILURE_COUNTER_FILE"

log_alert "健康检查失败 (第 ${FAILURES}/${MAX_FAILURES} 次) — 响应: ${RESPONSE:0:200}"

if [ "$FAILURES" -ge "$MAX_FAILURES" ]; then
    log_alert "连续 ${MAX_FAILURES} 次失败，正在重启服务..."
    systemctl --user restart "$SERVICE" 2>&1 || {
        log_alert "重启命令执行失败（可能是服务未注册）"
    }
    rm -f "$FAILURE_COUNTER_FILE"
    sleep 3
    # 重启后再检查一次
    RETRY=$(curl -s --max-time 10 "$HEALTH_URL" 2>&1) || true
    if echo "$RETRY" | grep -q '"status":"ok"'; then
        log_alert "服务已成功恢复"
    else
        log_alert "重启后仍未恢复，请手动检查: systemctl --user status $SERVICE"
    fi
fi
