#!/bin/bash
# HR Bot 启动脚本
# 使用方式:
#   ./run.sh          # 普通启动
#   ./run.sh dev      # 开发模式 + ngrok 隧道
#   ./run.sh ingest   # 仅重新索引文档

set -e

cd "$(dirname "$0")"
VENV_DIR="venv"

# 自动创建/激活虚拟环境
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

# 加载 .env 中的环境变量
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

_ensure_index() {
    # 如果有 preprocess.py，先预处理再索引
    if [ -f preprocess.py ]; then
        echo "🔄 预处理源文档 (PDF/DOCX → Markdown)..."
        python preprocess.py
    fi
    echo "📄 索引文档..."
    python ingest.py
}

case "${1:-}" in
    preprocess)
        echo "🔄 预处理源文档 (PDF/DOCX → Markdown)..."
        python preprocess.py
        ;;
    ingest)
        _ensure_index
        ;;
    dev)
        _ensure_index
        echo "🚀 启动服务（开发模式 + ngrok）..."
        python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
        SERVER_PID=$!
        sleep 2
        echo "🔗 启动 ngrok 隧道..."
        NGROK_ARGS="http 8000 --log=stdout"
        if [ -n "$NGROK_AUTH_TOKEN" ]; then
            NGROK_ARGS="$NGROK_ARGS --authtoken $NGROK_AUTH_TOKEN"
        fi
        ngrok $NGROK_ARGS 2>/dev/null &
        NGROK_PID=$!
        echo "PID: server=$SERVER_PID  ngrok=$NGROK_PID"
        echo "按 Ctrl+C 停止"
        wait
        ;;
    *)
        _ensure_index
        echo "🚀 启动服务..."
        python -m uvicorn main:app --host 0.0.0.0 --port 8000
        ;;
esac
