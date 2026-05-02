"""
HR Bot - DingTalk Stream Mode（最新应用凭据）
"""
import json
import logging
import logging.handlers
import asyncio
import threading
import traceback
from pathlib import Path

import uvicorn
import httpx
from fastapi import FastAPI, Request
from pydantic import BaseModel

import dingtalk_stream
from dingtalk_stream import AckMessage, CallbackHandler, CallbackMessage
from dingtalk_stream.chatbot import ChatbotMessage

from config import DINGTALK_APP_KEY, DINGTALK_APP_SECRET, HOST, PORT
from rag_engine import ask

# ── 日志配置（文件轮转 + 控制台） ─────────────────────────
_log_dir = Path(__file__).parent / "logs"
_log_dir.mkdir(parents=True, exist_ok=True)

_file_handler = logging.handlers.RotatingFileHandler(
    _log_dir / "server.log",
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=5,
    encoding="utf-8",
)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
))

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
))

logging.basicConfig(
    level=logging.INFO,
    handlers=[_file_handler, _console_handler],
)
logger = logging.getLogger("hr-bot")

app = FastAPI(title="HR Bot")

import time as _time_module

_queue_lock = asyncio.Lock()
_waiting_tasks = []
_loop = None
_start_time = _time_module.time()
_msg_counter = 0


def _increment_msg_counter():
    global _msg_counter
    _msg_counter += 1


async def _process_queue():
    while True:
        task_info = None
        async with _queue_lock:
            if _waiting_tasks:
                task_info = _waiting_tasks.pop(0)
        if not task_info:
            await asyncio.sleep(0.5)
            continue
        future, sender_id, wh, q = task_info
        try:
            logger.info("处理: %s", q)
            r = await asyncio.to_thread(ask, q)
            ans = r["answer"]
            src = r.get("sources", [])
            reply = ans
            if src:
                reply += "\n\n---\n📎 *参考来源*\n" + "\n".join(src)
            if wh:
                async with httpx.AsyncClient(timeout=10) as c:
                    await c.post(wh, json={
                        "msgtype": "markdown",
                        "markdown": {"title": "HR 助手", "text": reply},
                        "at": {"atDingtalkIds": [sender_id]},
                    })
            future.set_result(reply)
        except Exception as e:
            logger.exception("处理异常")
            future.set_exception(e)


class Handler(CallbackHandler):
    async def process(self, msg: CallbackMessage):
        try:
            topic = msg.headers.topic if msg.headers else ""
            logger.info("回调 topic=%s", topic)
            if topic != ChatbotMessage.TOPIC:
                return AckMessage.STATUS_OK, "skip"
            data = msg.data
            if not data:
                return AckMessage.STATUS_OK, "nodata"
            sid = data.get("senderId") or data.get("senderStaffId") or ""
            wh = data.get("sessionWebhook") or ""
            ct = data.get("conversationType", "1")
            txt = data.get("text", {})
            q = txt.get("content", "").strip() if isinstance(txt, dict) else ""
            if ct == "2" and not data.get("isInAtList"):
                return AckMessage.STATUS_OK, "noat"
            if not q:
                return AckMessage.STATUS_OK, "empty"
            logger.info('>>> 消息 from=%s q=%s', sid, q)
            f = _loop.create_future()
            asyncio.run_coroutine_threadsafe(_enqueue(f, sid, wh, q), _loop)
            _increment_msg_counter()
        except Exception as e:
            logger.error('E: %s\n%s', e, traceback.format_exc())
        return AckMessage.STATUS_OK, 'OK'


async def _enqueue(f, sid, wh, q):
    async with _queue_lock:
        _waiting_tasks.append((f, sid, wh, q))
    await f


@app.on_event("startup")
async def startup():
    global _loop
    _loop = asyncio.get_event_loop()
    asyncio.create_task(_process_queue())
    cred = dingtalk_stream.Credential(DINGTALK_APP_KEY, DINGTALK_APP_SECRET)
    client = dingtalk_stream.DingTalkStreamClient(cred)
    client.register_callback_handler(ChatbotMessage.TOPIC, Handler())
    app.state._dingtalk_client = client
    t = threading.Thread(target=lambda: (logger.info("Stream 启动..."), client.start_forever()), daemon=True)
    t.start()
    logger.info("HR Bot 启动（Stream Mode，最新凭据）")


@app.on_event("shutdown")
async def shutdown():
    logger.info("HR Bot 关闭中...")
    client = getattr(app.state, "_dingtalk_client", None)
    if client:
        logger.info("钉钉 Stream 连接已断开")
    logger.info("HR Bot 已停止")


@app.get('/health')
async def health():
    return {'status': 'ok', 'service': 'hr-bot', 'queue_size': len(_waiting_tasks)}


@app.get('/api/stats')
async def get_stats():
    return {
        'uptime_seconds': int(_time_module.time() - _start_time),
        'total_messages': _msg_counter,
        'queue_size': len(_waiting_tasks),
    }


@app.get('/api/config')
async def get_config():
    from config import CHROMA_DB_DIR, COLLECTION_NAME
    return {
        'host': HOST,
        'port': PORT,
        'chroma_db_dir': CHROMA_DB_DIR,
        'collection_name': COLLECTION_NAME,
    }


@app.get("/debug/docs")
async def debug_docs():
    import chromadb
    from config import CHROMA_DB_DIR, COLLECTION_NAME
    try:
        c = chromadb.PersistentClient(path=CHROMA_DB_DIR)
        col = c.get_collection(COLLECTION_NAME)
        m = col.get()["metadatas"]
        return {"docs": list(set(x["source"] for x in m if x)), "total": len(m)}
    except Exception as e:
        return {"error": str(e)}

class AskReq(BaseModel):
    question: str

@app.post("/debug/ask")
async def debug_ask(req: AskReq):
    return await asyncio.to_thread(ask, req.question)

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
