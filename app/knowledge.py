# app/knowledge.py
"""知识库加载：schema.md + metrics.md → 提示词组装的输入。"""
from pathlib import Path

from app.config import KNOWLEDGE_DIR


def load_knowledge() -> dict:
    """读取两份知识库文档，返回 {'schema': str, 'metrics': str}。"""
    schema = (KNOWLEDGE_DIR / "schema.md").read_text(encoding="utf-8")
    metrics = (KNOWLEDGE_DIR / "metrics.md").read_text(encoding="utf-8")
    return {"schema": schema, "metrics": metrics}
