# app/config.py
"""全局配置：路径与 LLM 参数。API Key 只从 .env 读取。"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "olist.db"
KNOWLEDGE_DIR = ROOT / "knowledge"
ENV_PATH = ROOT / ".env"

def load_api_key() -> str:
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key and ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith("DASHSCOPE_API_KEY="):
                # 兼容裸值/引号包裹/export 前缀三种常见格式
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if not key:
        raise RuntimeError("DASHSCOPE_API_KEY 未配置（.env 或环境变量）")
    return key

# LLM 参数
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
CHAT_MODEL = "qwen3.7-plus"
EMBED_MODEL = "qwen3.7-text-embedding"
SQL_TIMEOUT_SEC = 5          # DuckDB 执行超时
MAX_RETRY = 1                # SQL 校验失败重试次数
MAX_ROWS = 200               # 查询结果行数上限（自动 LIMIT 兜底）
ALLOWED_TABLES = {"orders", "customers", "order_items", "order_payments",
                  "order_reviews", "products", "sellers",
                  "product_category_translation", "geolocation",
                  "user_wide", "ab_test_results", "valid_orders"}
