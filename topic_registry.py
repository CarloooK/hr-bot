"""
截图型 PDF 主题注册表

对于文字稀疏（全截图）的 PDF，不索引到 ChromaDB，
而是把页面标题存到注册表中。问答时如果问句关键词匹配到
注册表的页面标题，直接告知用户查阅对应 PDF。
"""
import json
import logging
import os
import re
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# 注册表路径
REGISTRY_PATH = Path(__file__).parent / "db" / "topic_registry.json"

# 判定为截图型 PDF 的阈值：平均每页字符数低于此值
IMAGE_PDF_THRESHOLD = 80

# ── 注册表读写 ─────────────────────────────────────────────

def _load() -> dict:
    if REGISTRY_PATH.exists():
        try:
            return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("主题注册表读取失败: %s", e)
    return {}

def _save(registry: dict):
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

# ── 注册 ────────────────────────────────────────────────────

# ── 已知截图型 PDF 的关键词别名 ──────────────────────────
# 当页面标题的 bigram 匹配不到时，用这些别名做模糊匹配
_KNOWN_KEYWORDS: dict[str, list[str]] = {
    "差旅&滴滴打车使用说明书.pdf": [
        "打车", "滴滴", "差旅", "出差", "携程", "机票", "酒店",
        "预定", "出行", "交通", "企业版", "打车报销",
    ],
}


def register_pdf(filename: str, pages: List[dict], avg_chars: float) -> bool:
    """
    注册 PDF 到主题注册表。

    Args:
        filename: 文件名
        pages: pypdf 提取的页面列表 [{text, page}, ...]
        avg_chars: 平均每页字符数

    Returns:
        True 表示这是截图型 PDF 已注册，False 表示正常 PDF 无需注册
    """
    if avg_chars >= IMAGE_PDF_THRESHOLD:
        return False  # 正常 PDF，不用注册

    # 提取有内容的页面标题（取每页前 80 字符作为标识）
    titles = []
    for p in pages:
        text = p.get("text", "").strip()
        if text:
            title = text[:80].strip()
            titles.append(f"第{p['page']}页: {title}")
        else:
            titles.append(f"第{p['page']}页: (无文字，全截图)")

    registry = _load()
    registry[filename] = {
        "pages": titles,
        "avg_chars": round(avg_chars, 1),
    }
    _save(registry)
    logger.info(
        "  截图型 PDF 已注册: %s (%d 页, avg %.0f 字符/页)",
        filename, len(pages), avg_chars,
    )
    return True

# ── 匹配查询 ────────────────────────────────────────────────

def _tokenize(text: str) -> set:
    """将文本拆成特征词（中文 2-gram + 英文单词），过滤通用停用词"""
    _STOP_BIGRAMS = {"步骤", "路径", "流程", "申请", "方法", "操作",
                      "信息", "方式", "内容", "选择", "使用", "提交",
                      "填写", "添加", "注意", "相关", "需要", "可以",
                      "根据", "基础", "说明", "按照", "进入", "进行"}
    words = set()
    chinese_seqs = re.findall(r'[\u4e00-\u9fff]{2,}', text)
    for seq in chinese_seqs:
        for i in range(len(seq) - 1):
            bg = seq[i:i+2]
            if bg not in _STOP_BIGRAMS:
                words.add(bg)
    for seg in re.findall(r'[a-zA-Z]{3,}', text):
        words.add(seg.lower())
    return words


def match_topic(question: str) -> Optional[dict]:
    """
    检查问题是否匹配注册表中的截图型 PDF。

    Returns:
        {"filename": "...", "hint": "请查阅《...》...", "matched_keywords": [...]} 或 None
    """
    registry = _load()
    if not registry:
        return None

    q_words = _tokenize(question)
    if not q_words:
        return None

    best_match = None
    best_score = 0

    # 策略 1：bigram 匹配页面标题
    for filename, info in registry.items():
        for page_title in info.get("pages", []):
            title_words = _tokenize(page_title)
            overlap = q_words & title_words
            if len(overlap) > best_score:
                best_score = len(overlap)
                best_match = {
                    "filename": filename,
                    "matched_keywords": list(overlap),
                }

    # 策略 2：关键词别名匹配（补充 bigram 覆盖不到的词汇）
    for filename, keywords in _KNOWN_KEYWORDS.items():
        if filename not in registry:
            continue
        matched = [kw for kw in keywords if kw in question]
        if matched and not best_match:
            best_match = {
                "filename": filename,
                "matched_keywords": matched,
            }
            best_score = 1

    # 截图型 PDF：匹配 1 个 bigram 即可提示（提示是让用户查原文档，不是给假答案）
    if best_match and best_score >= 1:
        best_match["hint"] = (
            f"💡 您的问题涉及 **《{best_match['filename']}》** 的内容（匹配关键词: {', '.join(best_match['matched_keywords'])}）。\n"
            f"该文档为操作截图指南，详细步骤请直接查阅该 PDF 文件，或咨询 HR/IT 部门获取具体操作指引。"
        )
        return best_match

    return None


def remove_unregistered(known_filenames: set):
    """清理注册表中已不存在的文件"""
    registry = _load()
    removed = [k for k in registry if k not in known_filenames]
    if removed:
        for k in removed:
            del registry[k]
        _save(registry)
        logger.info("  主题注册表已清理: %s", ", ".join(removed))
