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


# ── 话题增强配置 ──────────────────────────────────────────
# 当问及特定关键词时，强制注入来自指定文档指定页的内容
_BOOST_PAGES: dict[str, list[int]] = {
    "福利": [2, 4, 5],
    "薪酬": [2, 4, 5],
    "饭贴": [2],
    "薪资": [4, 5],
}


def _find_boost_chunks(query: str) -> list[str]:
    """话题增强：从指定 PDF 的指定页面强制摘取补充片段"""
    boost_pages = None
    for keyword, pages in _BOOST_PAGES.items():
        if keyword in query:
            boost_pages = pages
            break
    if not boost_pages:
        return []

    collection = get_collection()
    if collection is None:
        return []

    # 先找到目标文档的所有 chunks
    try:
        all_data = collection.get()
    except Exception:
        return []

    sources = set()
    target_source = None
    for meta in (all_data.get("metadatas") or []):
        if meta and "新员工常见问题答疑" in meta.get("source", ""):
            target_source = meta["source"]
            break
    if not target_source:
        return []

    try:
        src_data = collection.get(where={"source": target_source})
    except Exception:
        return []

    extra = []
    for doc, meta in zip(src_data.get("documents") or [], src_data.get("metadatas") or []):
        p = meta.get("page", 0) if meta else 0
        if p in boost_pages and len(doc or "") > 50:
            label = f"[来源：{target_source} 第{p}页 - 附]"
            extra.append(f"{label}\n{doc}\n")
    return extra


# ── 主检索 ────────────────────────────────────────────────

def retrieve(query: str, top_k: int = TOP_K) -> str:
    """
    检索相关文档片段。
    
    策略：一次全局查询取 top_k*3 条 → 按 source 轮询精选 top_k 条
    相比原来的"每个文档独立查30条再轮询"，减少 N-1 次 embedding 推理。
    """
    collection = get_collection()
    if collection is None:
        return "（暂无已索引的文档）"

    # 查询扩展
    query_text = _expand_query(query)
    if query_text != query:
        logger.info("查询扩展: %s → %s", query, query_text)

    # 一次全局查询
    n_results = top_k * 3
    try:
        results = collection.query(
            query_texts=[query_text],
            n_results=n_results,
        )
    except Exception as e:
        logger.warning("全局查询失败: %s，尝试较小结果集", e)
        results = collection.query(
            query_texts=[query_text],
            n_results=top_k,
        )

    if not results.get("documents") or not results["documents"][0]:
        return "（未找到相关文档内容）"

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    distances = results.get("distances", [[]])[0] if results.get("distances") else None

    # 按 source 分组（保留原始排序，即相似度顺序）
    per_source: dict[str, list[tuple[str, dict, float]]] = {}
    for i, doc in enumerate(docs):
        meta = metas[i] if i < len(metas) else {}
        source = meta.get("source", "未知") if meta else "未知"
        dist = distances[i] if distances else 0.0
        if source not in per_source:
            per_source[source] = []
        per_source[source].append((doc, meta, dist))

    # 轮询合并：每个来源轮流出 1 条，按原始相似度排序
    context_parts = []
    pool = list(per_source.keys())
    idx = 0
    while len(context_parts) < top_k:
        remaining = [s for s in pool if idx < len(per_source[s])]
        if not remaining:
            break
        for source in remaining:
            doc, meta, _ = per_source[source][idx]
            page = meta.get("page", "?")
            context_parts.append(f"[来源：{source} 第{page}页]\n{doc}\n")
            if len(context_parts) >= top_k:
                break
        idx += 1

    # 话题增强
    boost_chunks = _find_boost_chunks(query)
    for chunk in boost_chunks:
        label = chunk.split("\n")[0]
        if any(label in c for c in context_parts):
            continue
        # 替换最后一个（如果已达 top_k）
        if len(context_parts) >= top_k:
            context_parts[-1] = chunk
        else:
            context_parts.append(chunk)

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
