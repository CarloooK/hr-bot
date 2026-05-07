"""
文档预处理：将 docs/ 中的 PDF/DOCX 批量转换为 Markdown，输出到 docs_md/

用法：
  python preprocess.py              # 转换所有新增/变更的文件
  python preprocess.py --force      # 强制重新转换所有文件
  python preprocess.py --file xxx.pdf  # 转换单个文件

原理：
  用 MarkItDown 库解析各类文档，输出结构化的 Markdown，
  保留标题、列表、表格等结构信息，供 ingest.py 高效索引。
"""

import os
import sys
import hashlib
import json
import logging
from pathlib import Path

from markitdown import MarkItDown

from config import DOCS_DIR, DOCS_MD_DIR

logger = logging.getLogger(__name__)

MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "db", ".preprocess_manifest.json")


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
        except Exception:
            pass
    return {}


def save_manifest(manifest: dict):
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    logger.info("预处理清单已更新 (%d 个文件)", len(manifest))


SUPPORTED_EXTS = {".pdf", ".PDF", ".docx", ".DOCX", ".pptx", ".PPTX", ".xlsx", ".XLSX"}


def convert_file(src_path: Path, md: MarkItDown) -> bool:
    """将源文件转为 .md，写入 docs_md/"""
    src_name = src_path.name
    stem = src_path.stem
    dst_name = f"{stem}.md"
    dst_path = Path(DOCS_MD_DIR) / dst_name

    try:
        result = md.convert(str(src_path))
        text = result.text_content
    except Exception as e:
        logger.error("  转换失败 %s: %s", src_name, e)
        return False

    if not text or not text.strip():
        logger.warning("  转换结果为空: %s", src_name)
        return False

    os.makedirs(DOCS_MD_DIR, exist_ok=True)
    with open(dst_path, "w", encoding="utf-8") as f:
        f.write(text.strip())

    logger.info("  ✓ %s → %s (%d 字符)", src_name, dst_name, len(text))
    return True


def scan_src_dir() -> dict[str, Path]:
    """扫描 docs/ 下支持的源文件"""
    doc_dir = Path(DOCS_DIR)
    if not doc_dir.exists():
        return {}
    files = {}
    for ext in SUPPORTED_EXTS:
        for fp in doc_dir.glob(f"*{ext}"):
            files[fp.name] = fp
    return files


def run(force: bool = False):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("═" * 50)
    logger.info("  文档预处理：%s → %s", DOCS_DIR, DOCS_MD_DIR)
    if force:
        logger.info("  模式：强制重新转换")
    logger.info("═" * 50)

    current_files = scan_src_dir()
    if not current_files:
        logger.warning("docs/ 目录为空或不存在，无文件可转换")
        return

    manifest = load_manifest()
    new_or_changed: list[tuple[str, Path, str]] = []
    unchanged: list[str] = []

    for fname, fp in current_files.items():
        if force:
            new_or_changed.append((fname, fp, "强制"))
        elif fname not in manifest:
            new_or_changed.append((fname, fp, "新增"))
        else:
            current_hash = compute_file_hash(str(fp))
            if current_hash != manifest[fname].get("hash"):
                new_or_changed.append((fname, fp, "变更"))
            else:
                unchanged.append(fname)

    if not new_or_changed:
        logger.info("✓ 所有文件均无变化，无需转换")
        return

    logger.info("待转换 (%d 个):", len(new_or_changed))
    for fname, _, reason in new_or_changed:
        logger.info("  [%s] %s", reason, fname)

    md = MarkItDown()
    success_count = 0
    for fname, fp, reason in new_or_changed:
        if convert_file(fp, md):
            manifest[fname] = {
                "hash": compute_file_hash(str(fp)),
                "converted_at": __import__("datetime").datetime.now().isoformat(),
            }
            success_count += 1

    save_manifest(manifest)
    logger.info("═" * 50)
    logger.info("  预处理完成！成功 %d / %d", success_count, len(new_or_changed))
    logger.info("═" * 50)


if __name__ == "__main__":
    force = "--force" in sys.argv
    single_file = None
    for i, arg in enumerate(sys.argv[1:]):
        if arg.startswith("--file="):
            single_file = arg.split("=", 1)[1]
        elif arg == "--file" and i + 2 < len(sys.argv):
            single_file = sys.argv[i + 2]

    if single_file:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        fp = Path(single_file)
        if not fp.exists():
            logger.error("文件不存在: %s", single_file)
            sys.exit(1)
        md = MarkItDown()
        convert_file(fp, md)
    else:
        run(force=force)
