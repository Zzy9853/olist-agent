# app/test_rag.py
"""RAG 自检：索引构建 → 检索命中相关块。"""
from app.knowledge import load_knowledge
from app.rag import KnowledgeStore


def run():
    k = load_knowledge()
    store = KnowledgeStore()
    n = store.index(k)
    print(f"索引块数: {n}")
    hits = store.retrieve("物流延迟率最高的品类", top_k=2)
    for h in hits:
        print("命中:", h[:80].replace("\n", " "))
    assert hits, "检索无结果"
    assert any("物流" in h or "延迟" in h or "品类" in h for h in hits), "检索不相关"
    print("RAG 自检通过")


if __name__ == "__main__":
    run()
