"""Tests for preprocess + ingest pipeline (unittest-compatible, no pytest dependency)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DEEPSEEK_API_KEY", "test-skip")
os.environ.setdefault("DINGTALK_APP_KEY", "test-skip")
os.environ.setdefault("DINGTALK_APP_SECRET", "test-skip")

from pathlib import Path
from config import CHUNK_SIZE


class TestChunkText(unittest.TestCase):
    """测试分块逻辑"""

    def setUp(self):
        from ingest import chunk_text
        self.chunk_text = chunk_text

    def test_short_text_single_chunk(self):
        text = "你好，这是一段很短的文字。"
        chunks = self.chunk_text(text, page=1, source="test.md")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["text"], text)
        self.assertEqual(chunks[0]["metadata"]["page"], 1)

    def test_long_text_multiple_chunks(self):
        text = "A" * (CHUNK_SIZE * 3 + 100)
        chunks = self.chunk_text(text, page=1, source="test.md")
        self.assertGreaterEqual(len(chunks), 3)

    def test_chunk_index_sequential(self):
        text = "B" * (CHUNK_SIZE * 4)
        chunks = self.chunk_text(text, page=1, source="test.md")
        indices = [c["metadata"]["chunk_index"] for c in chunks]
        self.assertEqual(indices, list(range(len(chunks))))

    def test_chunk_metadata(self):
        text = "测试元数据"
        chunks = self.chunk_text(text, page=2, source="doc.md")
        self.assertEqual(chunks[0]["metadata"]["source"], "doc.md")
        self.assertEqual(chunks[0]["metadata"]["page"], 2)
        self.assertEqual(chunks[0]["metadata"]["chunk_index"], 0)


class TestExtractMd(unittest.TestCase):
    """测试 .md 文件提取"""

    def setUp(self):
        from ingest import extract_text_from_md
        self.extract = extract_text_from_md

    def _write_tmp(self, content, suffix=".md"):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8")
        f.write(content)
        f.close()
        return f.name

    def test_basic_text(self):
        tmp = self._write_tmp("Hello world")
        try:
            result = self.extract(tmp)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["text"], "Hello world")
        finally:
            os.unlink(tmp)

    def test_control_chars_removed(self):
        tmp = self._write_tmp("Hello\fworld\x00test\nline2")
        try:
            result = self.extract(tmp)
            text = result[0]["text"]
            self.assertNotIn("\f", text)
            self.assertNotIn("\x00", text)
            self.assertIn("Helloworld", text)
            self.assertIn("line2", text)
        finally:
            os.unlink(tmp)

    def test_empty_file(self):
        tmp = self._write_tmp("   ")
        try:
            result = self.extract(tmp)
            self.assertEqual(result, [])
        finally:
            os.unlink(tmp)

    def test_trailing_newline(self):
        tmp = self._write_tmp("content\n")
        try:
            result = self.extract(tmp)
            self.assertEqual(result[0]["text"], "content")
        finally:
            os.unlink(tmp)


class TestComputeHash(unittest.TestCase):
    """测试文件哈希一致性"""

    def test_content_change_changes_hash(self):
        from preprocess import compute_file_hash
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
        f.write("hello")
        f.close()
        tmp = f.name
        try:
            h1 = compute_file_hash(tmp)
            with open(tmp, "w") as fh:
                fh.write("world")
            h2 = compute_file_hash(tmp)
            self.assertNotEqual(h1, h2)
        finally:
            os.unlink(tmp)

    def test_same_content_same_hash(self):
        from preprocess import compute_file_hash
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
        f.write("same content")
        f.close()
        tmp = f.name
        try:
            h1 = compute_file_hash(tmp)
            h2 = compute_file_hash(tmp)
            self.assertEqual(h1, h2)
        finally:
            os.unlink(tmp)


class TestQueryExpansion(unittest.TestCase):
    """测试查询关键词扩展"""

    def test_hit_expands(self):
        from rag_engine import _expand_query
        expanded = _expand_query("公司的福利政策")
        self.assertIn("福利", expanded)
        self.assertIn("饭贴", expanded)

    def test_miss_unchanged(self):
        from rag_engine import _expand_query
        expanded = _expand_query("今天天气怎么样")
        self.assertEqual(expanded, "今天天气怎么样")

    def test_multiple_keywords_first_match(self):
        from rag_engine import _expand_query
        expanded = _expand_query("差旅报销")
        # matched "报销" because 报销 appears first in the query
        self.assertIn("报销", expanded)
        self.assertIn("费用", expanded)


class TestCacheKey(unittest.TestCase):
    """测试缓存键一致性"""

    def test_same_input_same_key(self):
        from rag_engine import _cache_key
        k1 = _cache_key("年假怎么休？", 12)
        k2 = _cache_key("年假怎么休？", 12)
        self.assertEqual(k1, k2)

    def test_different_top_k_different_key(self):
        from rag_engine import _cache_key
        k1 = _cache_key("年假怎么休？", 12)
        k2 = _cache_key("年假怎么休？", 5)
        self.assertNotEqual(k1, k2)

    def test_different_question_different_key(self):
        from rag_engine import _cache_key
        k1 = _cache_key("A", 12)
        k2 = _cache_key("B", 12)
        self.assertNotEqual(k1, k2)


class TestBoostPagesConfig(unittest.TestCase):
    """测试话题增强配置"""

    def test_expected_keys_present(self):
        from rag_engine import _BOOST_PAGES
        for key in ("福利", "薪酬", "饭贴", "薪资"):
            self.assertIn(key, _BOOST_PAGES)
        for pages in _BOOST_PAGES.values():
            self.assertIsInstance(pages, list)
            self.assertTrue(all(isinstance(p, int) for p in pages))


if __name__ == "__main__":
    unittest.main()
