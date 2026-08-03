# app/rag.py
"""RAG 检索：知识库文档切块 → qwen3.7-text-embedding 向量化 → ChromaDB 检索。
文档量小阶段：切块粒度=按标题分节；检索命中 top-k 注入 few-shot 上下文。
"""
import chromadb
from chromadb.utils import embedding_functions

from app.config import KNOWLEDGE_DIR, EMBED_MODEL
from app.llm import embed_texts

COLLECTION_NAME = "olist_knowledge"


@embedding_functions.register_embedding_function
class _QwenEmbeddingFunction(embedding_functions.EmbeddingFunction):
    """qwen3.7-text-embedding 适配 ChromaDB 1.5.x。

    chroma 1.0 起移除 CustomEmbeddingFunction，改为 EmbeddingFunction 协议 +
    register_embedding_function 注册：name() 作为 config key 随集合持久化，
    跨进程加载时按 build_from_config 重建同一 EF（不注册则加载报
    "Unsupported embedding function"）。
    """

    @staticmethod
    def name() -> str:
        return EMBED_MODEL

    def get_config(self) -> dict:
        return {}

    @staticmethod
    def build_from_config(config: dict) -> "_QwenEmbeddingFunction":
        return _QwenEmbeddingFunction()

    def __call__(self, input):
        return embed_texts(list(input))


def _chunk_md(text: str, base_title: str) -> list[dict]:
    """按 ## / ### 标题切块，返回 [{id, title, text}]。"""
    chunks, cur_title, buf = [], None, []
    for line in text.splitlines():
        if line.startswith(("## ", "### ")):
            if buf and cur_title:
                chunks.append({"id": f"{base_title}:{cur_title}", "title": cur_title,
                               "text": "\n".join(buf)})
            cur_title = line.lstrip("# ").strip()
            buf = [line]
        else:
            buf.append(line)
    if buf and cur_title:
        chunks.append({"id": f"{base_title}:{cur_title}", "title": cur_title,
                       "text": "\n".join(buf)})
    return chunks


class KnowledgeStore:
    def __init__(self, persist_dir: str | None = None):
        client = chromadb.PersistentClient(path=persist_dir or str(KNOWLEDGE_DIR.parent / "data" / "chroma"))
        self.col = client.get_or_create_collection(
            COLLECTION_NAME,
            embedding_function=_QwenEmbeddingFunction())

    def index(self, knowledge: dict) -> int:
        """重建索引（幂等：清空后重建）。返回块数。"""
        if self.col.count():
            self.col.delete(where=None)
        chunks = []
        chunks += _chunk_md(knowledge["schema"], "schema")
        chunks += _chunk_md(knowledge["metrics"], "metrics")
        self.col.add(ids=[c["id"] for c in chunks],
                     documents=[c["text"] for c in chunks],
                     metadatas=[{"title": c["title"]} for c in chunks])
        return len(chunks)

    def retrieve(self, question: str, top_k: int = 3) -> list[str]:
        res = self.col.query(query_texts=[question], n_results=top_k)
        return res["documents"][0] if res["documents"] else []
