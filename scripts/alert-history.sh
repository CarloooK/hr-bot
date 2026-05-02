#!/usr/bin/env bash
# ── HR Bot 最近告警/异常摘要 ──────────────────────────────
# 用法: bash scripts/alert-history.sh [小时数]
# 默认显示过去 24 小时的异常
# ──────────────────────────────────────────────────────────
set -euo pipefail

HOURS="${1:-24}"
LOG_DIR="/home/admin/hr-bot/logs"
FILES=("$LOG_DIR/alert.log" "$LOG_DIR/healthcheck.log" "$LOG_DIR/server.log")

SINCE=$(date -d "$HOURS hours ago" '+%Y-%m-%d %H:%M:%S')
echo "═══════════════════════════════════════════════════════════"
echo " HR Bot 异常摘要 — 最近 ${HOURS} 小时 (从 ${SINCE} 起)"
echo "═══════════════════════════════════════════════════════════"
echo ""

for f in "${FILES[@]}"; do
    if [ -f "$f" ]; then
        echo "─── $(basename "$f") ───"
        # 筛选包含 ERROR / ALERT / FAIL / WARNING 的行（忽略 INFO / OK）
        grep -h -i -E '(ERROR|ALERT|FAIL|WARNING|异常|失败|告警)' "$f" 2>/dev/null \
            | grep -v -E '(INFO|OK - 健康检查通过)' \
            | awk "\$0 >= \"$SINCE\"" \
            | tail -20 \
            || echo "(无)"
        echo ""
    else
        echo "─── $(basename "$f") ─── (文件不存在)"
        echo ""
    fi
done

echo "─── systemctl 状态 ───"
systemctl --user status hr-bot.service 2>&1 | head -15
