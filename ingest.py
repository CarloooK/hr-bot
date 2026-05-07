"""
文档处理流水线（增量模式）：从 docs_md/ 读取预处理的 Markdown → 分块 → ChromaDB

工作流：
  新增源文件 (PDF/DOCX) → python preprocess.py (转 .md) → python ingest.py (索引)
  ingest 只从 docs_md/ 读取 .md，纯文本解析，极快。

如果 docs_md/ 不存在，自动 fallback 到 docs/ 原始流程（PDF/Word 直接解析）作为兼容。

Embedding 由 embedding_fn.py 的 MiniLMEmbeddingFunction（onnxruntime）自动处理。
"""

import json
import hashlib
import os
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Callable

import chromadb

from embedding_fn import MiniLMEmbeddingFunction
from topic_registry import register_pdf, remove_unregistered

from config import (
    DOCS_DIR, DOCS_MD_DIR, CHROMA_DB_DIR, COLLECTION_NAME,
    CHUNK_SIZE, CHUNK_OVERLAP,
)

logger = logging.getLogger(__name__)

MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "db", ".ingest_manifest.json")


# ── 文本提取器 ─────────────────────────────────────────────

def extract_text_from_md(path: str) -> List[dict]:
    """读取 .md 文件为全文（保留 Markdown 结构文本，清理控制字符）"""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    text = text.strip()
    # 清理不可见控制字符（如 \f 换页符），保留标准空白
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    if text:
        return [{"text": text, "page": 1}]
    return []


def extract_text_from_pdf(path: str) -> List[dict]:
    """提取 PDF 文字（pypdf）—— fallback 模式用"""
    from pypdf import PdfReader
    reader = PdfReader(path)
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text and text.strip():
            pages.append({"text": text.strip(), "page": i + 1})
        else:
            pages.append({"text": "", "page": i + 1})
    return pages


def extract_text_from_docx(path: str) -> List[dict]:
    """提取 Word 文字—— fallback 模式用"""
    from docx import Document
    doc = Document(path)
    full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
    if full_text.strip():
        return [{"text": full_text.strip(), "page": 1}]
    return []


# ── 模式选择 ────────────────────────────────────────────────

def _detect_mode() -> tuple[str, dict[str, Callable], str]:
    """
    自动选择工作模式：
    - docs_md/ 存在 → MODE_MD (只处理 .md)
    - docs_md/ 不存在 → MODE_FALLBACK (docs/ 原始模式)
    """
    if os.path.isdir(DOCS_MD_DIR):
        ext_map = {".md": extract_text_from_md, ".MD": extract_text_from_md}
        return "MODE_MD", ext_map, DOCS_MD_DIR
    else:
        ext_map = {
            ".pdf": extract_text_from_pdf, ".PDF": extract_text_from_pdf,
            ".docx": extract_text_from_docx, ".DOCX": extract_text_from_docx,
            ".md": extract_text_from_md, ".MD": extract_text_from_md,
        }
        return "MODE_FALLBACK", ext_map, DOCS_DIR


# ── 分块 ──────────────────────────────────────────────────

def chunk_text(text: str, page: int, source: str, idx_start: int = 0) -> List[dict]:
    """固定窗口分块（带重叠）"""
    chunks = []
    idx = idx_start
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunks.append({
            "text": text[start:end],
            "metadata": {"source": source, "page": page, "chunk_index": idx},
        })
        idx += 1
        if end >= len(text):
            break
        start = end - CHUNK_OVERLAP
    return chunks


# ── 文件清单管理 ───────────────────────────────────────────

def compute_file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            buf = f.read(65536)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def load_manifest() -> dict:
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("清单文件读取出错，将重新构建: %s", e)
    return {}


def save_manifest(manifest: dict):
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    logger.info("清单已更新 (%d 个文件)", len(manifest))


def scan_doc_dir(mode: str, ext_map: dict, base_dir: str) -> dict[str, Path]:
    """扫描指定目录下的支持文件"""
    doc_dir = Path(base_dir)
    if not doc_dir.exists():
        return {}
    files = {}
    for ext in ext_map:
        for fp in doc_dir.glob(f"*{ext}"):
            files[fp.name] = fp
    return files


# ── ChromaDB 操作 ─────────────────────────────────────────

def get_or_create_collection(client):
    embedding_fn = MiniLMEmbeddingFunction()
    try:
        return client.get_collection(
            COLLECTION_NAME,
            embedding_function=embedding_fn,
        )
    except Exception:
        return client.create_collection(
            COLLECTION_NAME,
            embedding_function=embedding_fn,
        )


def delete_file_chunks(collection, source_name: str) -> bool:
    try:
        result = collection.get(where={"source": source_name})
        ids = result.get("ids", [])
        if ids:
            collection.delete(ids=ids)
            logger.info("  清除旧数据: %s (%d 条)", source_name, len(ids))
        return True
    except Exception as e:
        logger.warning("  清除旧数据 %s 时出错: %s", source_name, e)
        return False


def process_file(fp: Path, collection, ext_map: dict, mode: str) -> int:
    """解析单个文件 → 分块 → 存入 ChromaDB"""
    ext = fp.suffix
    extractor = ext_map.get(ext)
    if not extractor:
        logger.warning("不支持的文件格式: %s", ext)
        return 0

    source_name = fp.name
    pages = extractor(str(fp))
    if not pages:
        logger.info("  文件内容为空: %s", source_name)
        return 0

    # --- MODE_FALLBACK: 截图型 PDF 检测（原始 docs/ 模式） ---
    if mode == "MODE_FALLBACK":
        total_chars = sum(len(p.get("text", "")) for p in pages)
        avg_chars = total_chars / max(len(pages), 1)
        if avg_chars < 80:
            logger.info(
                "  截图型 PDF (avg %.0f 字符/页): %s → 注册主题引用，跳过 ChromaDB 索引",
                avg_chars, source_name,
            )
            register_pdf(source_name, pages, avg_chars)
            return 0

    # --- MODE_MD: 全文作为单页（预处理后的 .md 不分页） ---
    # --- MODE_FALLBACK: 拼接全文本 + 分页映射 ---
    if mode == "MODE_MD":
        text = pages[0]["text"]
        chunks = chunk_text(text, page=1, source=source_name)
    else:
        full_text = ""
        page_map = []
        for p in pages:
            text = p.get("text", "")
            if not text:
                continue
            start = len(full_text)
            if full_text:
                full_text += "\n"
                start = len(full_text)
            full_text += text
            page_map.append((start, len(full_text), p["page"]))

        chunks = chunk_text(full_text, page=0, source=source_name)
        for c in chunks:
            c_start_index = full_text.find(c["text"])
            if c_start_index >= 0:
                for ps, pe, pn in page_map:
                    if ps <= c_start_index < pe:
                        c["metadata"]["page"] = pn
                        break
            else:
                c["metadata"]["page"] = 0

    if not chunks:
        return 0

    total = len(chunks)
    delete_file_chunks(collection, source_name)

    for batch_start in range(0, total, 32):
        batch_end = min(batch_start + 32, total)
        batch = chunks[batch_start:batch_end]

        texts = [c["text"] for c in batch]
        metadatas = [c["metadata"] for c in batch]
        batch_ids = [f"{source_name}_chunk_{c['metadata']['chunk_index']}" for c in batch]

        collection.add(
            documents=texts,
            metadatas=metadatas,
            ids=batch_ids,
        )

    logger.info("  已索引: %s → %d 个片段", source_name, total)
    return total


# ── 主流程 ─────────────────────────────────────────────────

def run():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("═" * 50)
    logger.info("  增量文档处理开始（onnxruntime embedding）")

    mode, ext_map, base_dir = _detect_mode()
    if mode == "MODE_MD":
        logger.info("  模式: Markdown 预处理模式 ← docs_md/")
    else:
        logger.info("  模式: 兼容模式 (直接解析 PDF/Word) ← docs/")
    logger.info("═" * 50)

    manifest = load_manifest()
    current_files = scan_doc_dir(mode, ext_map, base_dir)

    if not current_files:
        logger.warning("%s 目录为空或不存在，请先放入文档", base_dir)
        return

    new_or_changed: list[tuple[str, Path, str]] = []
    unchanged: list[str] = []
    deleted: list[str] = [fname for fname in manifest if fname not in current_files]

    for fname, fp in current_files.items():
        if fname not in manifest:
            new_or_changed.append((fname, fp, "新增"))
        else:
            current_hash = compute_file_hash(str(fp))
            if current_hash != manifest[fname].get("hash"):
                new_or_changed.append((fname, fp, "变更"))
            else:
                unchanged.append(fname)

    if new_or_changed or deleted:
        if new_or_changed:
            logger.info("待处理 — 新增/变更的文件:")
            for fname, _, reason in new_or_changed:
                logger.info("  [%s] %s", reason, fname)
        if deleted:
            logger.info("待清理 — 已删除的文件: %s", ", ".join(deleted))
    else:
        logger.info("✓ 所有文件均无变化，无需处理。")
        return

    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    collection = get_or_create_collection(client)

    for fname in deleted:
        delete_file_chunks(collection, fname)
        del manifest[fname]

    # MODE_FALLBACK: 清理截图型 PDF 注册表中已删除的文件
    if mode == "MODE_FALLBACK":
        remove_unregistered(set(current_files.keys()))

    total_chunks = 0
    for fname, fp, reason in new_or_changed:
        try:
            count = process_file(fp, collection, ext_map, mode)
            if count > 0:
                manifest[fname] = {
                    "hash": compute_file_hash(str(fp)),
                    "chunks": count,
                    "updated_at": datetime.now().isoformat(),
                }
                total_chunks += count
        except Exception as e:
            logger.error("处理文件失败 %s: %s", fname, e)

    save_manifest(manifest)
    logger.info("═" * 50)
    logger.info("  处理完成！本次新增/更新 %d 个片段", total_chunks)
    logger.info("  索引库总计 %d 个文件", len(manifest))
    logger.info("═" * 50)


if __name__ == "__main__":
    run()
