"""HR Bot 配置"""
import os
from dotenv import load_dotenv

# 加载 .env 文件
_env_file = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_file):
    load_dotenv(_env_file)

# DeepSeek
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
LLM_MODEL = "deepseek-chat"

# ChromaDB（使用内置 ONNX embedding 函数，无需额外配置）
CHROMA_DB_DIR = os.path.join(os.path.dirname(__file__), "db")
COLLECTION_NAME = "hr_docs"

# 文档目录
DOCS_DIR = os.path.join(os.path.dirname(__file__), "docs")

# 分块参数
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# 检索参数
TOP_K = 12

# FastAPI
HOST = "0.0.0.0"
PORT = 8000

# 钉钉配置
DINGTALK_APP_KEY = os.getenv("DINGTALK_APP_KEY")
DINGTALK_APP_SECRET = os.getenv("DINGTALK_APP_SECRET")

# ngrok token（可选）
NGROK_AUTH_TOKEN = os.getenv("NGROK_AUTH_TOKEN", "")

# ── 启动时校验必要凭据 ─────────────────────────────────────

_REQUIRED = {"DEEPSEEK_API_KEY": DEEPSEEK_API_KEY}
if DINGTALK_APP_KEY or DINGTALK_APP_SECRET:
    # 只在使用钉钉时才需要
    _REQUIRED["DINGTALK_APP_KEY"] = DINGTALK_APP_KEY
    _REQUIRED["DINGTALK_APP_SECRET"] = DINGTALK_APP_SECRET

_MISSING = [k for k, v in _REQUIRED.items() if not v]
if _MISSING:
    raise RuntimeError(
        f"必要环境变量未设置: {', '.join(_MISSING)}。请在 .env 文件中配置。"
    )
