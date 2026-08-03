# app/test_agent.py
"""Agent 链路冒烟：3 个查询问题 + 1 个归因问题端到端（需真实 API Key）。"""
from app.agent import ask


def run():
    questions = [
        "整体用户流失率是多少？",
        "物流延迟率最高的5个品类有哪些？",
        "流失概率高于80%的高价值用户有多少人？",
        "为什么这个用户流失风险高？用户ID是 97981245c3257ea9b14befffd560177b",
    ]
    passed = 0
    for i, q in enumerate(questions):
        r = ask(q)
        if i == 3:  # 归因问题：走 explain 路径
            ok = (r["intent"] == "explain" and r["attribution"] is not None
                  and len(r["attribution"]["features"]) == 3 and bool(r["answer"]))
        else:       # 查询问题：走 SQL 执行路径
            ok = bool(r["sql"]) and bool(r["answer"])
        passed += ok
        print(f"Q: {q}")
        print(f"   intent: {r['intent']}")
        print(f"   SQL: {r['sql']}")
        print(f"   A: {r['answer'][:120]}")
        print()
    print(f"冒烟结果: {passed}/{len(questions)} 通过")
    assert passed == len(questions), "存在未通过的问题"


if __name__ == "__main__":
    run()


def multi_turn():
    """多轮验证：第二轮追问引用第一轮上下文（如"那圣保罗呢"）。"""
    from app.agent import ask
    r1 = ask("哪些州的用户流失率最高？列出前3。")
    print("第一轮:", r1["answer"][:60])
    history = [{"role": "user", "content": "哪些州的用户流失率最高？列出前3。"},
               {"role": "assistant", "content": r1["answer"]}]
    r2 = ask("那圣保罗的流失率具体是多少？", messages=history)
    print("第二轮:", r2["answer"][:80])
    print("第二轮 SQL:", r2["sql"])
    assert r2["sql"] is not None, "第二轮未生成 SQL"
    assert "圣保罗" in r2["answer"] or "SP" in r2["answer"], "第二轮未答出圣保罗"
    print("多轮验证通过")
