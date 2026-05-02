"""
RAG 问答引擎：ChromaDB 检索 → DeepSeek Chat API 生成回答
Embedding 由 embedding_fn.py 的 MiniLMEmbeddingFunction（onnxruntime）处理。
"""
import logging
import time

import chromadb

from embedding_fn import MiniLMEmbeddingFunction
from config import (
    CHROMA_DB_DIR, COLLECTION_NAME,
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, LLM_MODEL,
    TOP_K,
)
from topic_registry import match_topic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个智能HR助手。请基于提供的文档内容回答员工的问题。

规则：
1. 只基于提供的文档内容回答，不要编造信息
2. 如果文档内容不足以回答，请如实告知
3. 回答时请注明引用来源（文档名 + 页码）
4. 用中文回答，简洁明了，将文档中找到的所有具体信息逐一列出
5. 不要只概括大类——文档中有多少具体细节就列多少（如饭贴发放方式、金额、条件等）
6. 如果来自不同文档的信息互补，合并呈现给用户"""

# ── 单例：ChromaDB collection 缓存（避免每次重建） ──────

_collection = None

def _init_collection():
    """初始化并缓存 ChromaDB collection（仅执行一次）"""
    global _collection
    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    embedding_fn = MiniLMEmbeddingFunction()
    try:
        _collection = client.get_collection(
            COLLECTION_NAME,
            embedding_function=embedding_fn,
        )
    except Exception:
        logger.warning("ChromaDB 中未找到 collection，请先运行 ingest.py")
        _collection = False  # sentinel: 首次失败后不再重试


def get_collection():
    if _collection is None:
        _init_collection()
    if _collection is False:
        return None
    return _collection


# ── 查询扩展（MiniLM 语义覆盖不够时，补充关键词提高匹配精度） ──
_QUERY_EXPANSIONS = {
    "福利": "福利 饭贴 精微币 补贴 薪资 年假 奖金 五险一金 社保 公积金 补充医疗",
    "年假": "年假 带薪年休假 休假 假期 请假",
    "请假": "请假 病假 事假 年假 考勤 休假",
    "薪资": "薪资 工资 薪酬 奖金 加班费 绩效",
    "社保": "社保 公积金 五险一金 社会保障",
    "报销": "报销 差旅 费用 发票 招待费",
    "考勤": "考勤 打卡 迟到 加班 工时",
    "加班": "加班 加班费 调休 工时",
    "住宿": "住宿 宿舍 租房 入住",
    "差旅": "差旅 出差 机票 酒店 交通",
    "培训": "培训 学习 课程 培训平台",
    "入职": "入职 新员工 域账号 账户",
    "晋升": "晋升 涨薪 晋升 职级 升职",
    "离职": "离职 辞职 退工 离职流程",
    "打车": "打车 滴滴 出行 交通",
    "携程": "携程 差旅 机票 酒店 预定",
}

def _expand_query(query: str) -> str:
    """对查询做关键词扩展"""
    expanded = query
    for keyword, expansion in _QUERY_EXPANSIONS.items():
        if keyword in query:
            expanded = f"{query} {expansion}"
            break
    return expanded


def retrieve(query: str, top_k: int = TOP_K) -> str:
    """检索相关文档片段（每个文档单独检索取 N 条，再轮询合并）"""
    collection = get_collection()
    if collection is None:
        return "（暂无已索引的文档）"

    # 查询扩展
    query_text = _expand_query(query)
    if query_text != query:
        logger.info("查询扩展: %s → %s", query, query_text)

    # 获取所有来源文档列表
    try:
        all_data = collection.get()
        sources = sorted(set(m.get("source", "未知") for m in all_data["metadatas"]))
    except Exception:
        sources = []

    if not sources:
        # 兜底：全局查询
        results = collection.query(query_texts=[query_text], n_results=top_k)
        if not results["documents"] or not results["documents"][0]:
            return "（未找到相关文档内容）"
    else:
        # 每个文档独立检索，各取 30 条确保覆盖率（有些文档含饭贴/精微币的 chunk 排名靠后）
        per_source_chunks: dict[str, list[tuple[str, dict]]] = {}
        for source in sources:
            try:
                r = collection.query(
                    query_texts=[query_text],
                    n_results=min(30, collection.count()),
                    where={"source": source},
                )
                if r["documents"] and r["documents"][0]:
                    for doc, meta in zip(r["documents"][0], r["metadatas"][0]):
                        if source not in per_source_chunks:
                            per_source_chunks[source] = []
                        per_source_chunks[source].append((doc, meta))
            except Exception:
                continue

    # 轮询合并
    context_parts = []
    pool = list(per_source_chunks.keys())
    idx = 0
    while len(context_parts) < top_k:
        remaining = [s for s in pool if idx < len(per_source_chunks[s])]
        if not remaining:
            break
        for source in remaining:
            doc, meta = per_source_chunks[source][idx]
            page = meta.get("page", "?")
            context_parts.append(f"[来源：{source} 第{page}页]\n{doc}\n")
            if len(context_parts) >= top_k:
                break
        idx += 1

    # ── 话题增强：为"福利"话题补充 MiniLM 语义覆盖不到的具体内容 ──
    _BOOST_PAGES: dict[str, list[int]] = {
        "福利": [2, 4, 5],
        "薪酬": [2, 4, 5],
        "饭贴": [2],
        "薪资": [4, 5],
    }
    boost_pages = None
    for keyword, pages in _BOOST_PAGES.items():
        if keyword in query:
            boost_pages = pages
            break
    if boost_pages:
        for source in per_source_chunks:
            if "新员工常见问题答疑" in source:
                for doc, meta in per_source_chunks[source]:
                    p = meta.get("page", 0)
                    if p in boost_pages and len(doc) > 50:
                        # 避免注入已在轮询结果或已注入的重复内容
                        label = f"[来源：{source} 第{p}页 - 附]"
                        already_included = any(label in c for c in context_parts)
                        if already_included:
                            continue
                        boost = f"{label}\n{doc}\n"
                        context_parts.append(boost)
                break

    return "\n".join(context_parts)


# ── 答案 TTL 缓存 ──────────────────────────────────────────
_CACHE_TTL = 300  # 5 分钟
_cache: dict[int, tuple[float, dict]] = {}

def _cache_key(question: str, top_k: int) -> int:
    return hash((question, top_k))

def _get_cached(question: str, top_k: int) -> dict | None:
    key = _cache_key(question, top_k)
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, result = entry
    if time.monotonic() - ts > _CACHE_TTL:
        del _cache[key]
        return None
    return result

def _set_cache(question: str, top_k: int, result: dict):
    key = _cache_key(question, top_k)
    _cache[key] = (time.monotonic(), result)


def ask(question: str, top_k: int = TOP_K) -> dict:
    """
    完整 RAG 问答流程
    返回: {"answer": "...", "sources": [...]}
    """
    import httpx

    # 缓存命中直接返回
    cached = _get_cached(question, top_k)
    if cached is not None:
        logger.info("缓存命中: %s", question)
        return cached

    context = retrieve(question, top_k)

    # 截图型 PDF 主题匹配（当检索结果不理想时备用）
    topic_hint = match_topic(question)
    hint_prefix = (topic_hint["hint"] + "\n\n") if topic_hint else ""

    logger.info("调用 DeepSeek LLM API...")
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"相关文档内容：\n{context}\n\n{hint_prefix}员工问：{question}"},
        ],
        "temperature": 0.3,
        "max_tokens": 2000,
    }

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            answer = data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error("DeepSeek API 调用失败: %s", e)
        answer = "抱歉，我暂时无法回答这个问题（API 调用异常）。"

    sources = [line for line in context.split("\n") if line.startswith("[来源：")]
    result = {"answer": answer, "sources": sources}
    if answer != "抱歉，我暂时无法回答这个问题（API 调用异常）。":
        _set_cache(question, top_k, result)
    return result


# ── 启动时 warm up embedding 模型 ──────────────────────────
try:
    _init_collection()
    logger.info("Embedding 模型已预热")
except Exception as e:
    logger.warning("Embedding 预热失败（首次问答时会重试）: %s", e)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    result = ask("公司的年假政策是什么？")
    print("\n=== 回答 ===")
    print(result["answer"])
    if result["sources"]:
        print("\n=== 来源 ===")
        for s in result["sources"]:
            print(s)
