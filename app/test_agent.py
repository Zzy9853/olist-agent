# app/test_agent.py
"""Agent 链路冒烟：3 个典型问题端到端（需真实 API Key）。"""
from app.agent import ask


def run():
    questions = [
        "整体用户流失率是多少？",
        "物流延迟率最高的5个品类有哪些？",
        "流失概率高于80%的高价值用户有多少人？",
    ]
    passed = 0
    for q in questions:
        r = ask(q)
        has_sql = bool(r["sql"])
        has_answer = bool(r["answer"])
        passed += has_sql and has_answer
        print(f"Q: {q}")
        print(f"   SQL: {r['sql']}")
        print(f"   A: {r['answer'][:120]}")
        print()
    print(f"冒烟结果: {passed}/{len(questions)} 返回 SQL 与解读")
    assert passed == len(questions), "存在未返回 SQL 或解读的问题"


if __name__ == "__main__":
    run()
