# app/test_judge.py
"""Judge 自检：高质量回答应得高分、低质量回答应得低分（真实 API）。"""
from app.judge import judge_answer


def run():
    good = judge_answer(
        "整体用户流失率是多少？",
        "整体流失率为 81.2%（77,129/94,983 用户），远高于电商行业 10-30% 的常见基线，属于异常高位。"
        "建议优先排查物流体验（模型 Top 特征为配送时长，流失用户配送 13.2 天 vs 留存 8.4 天）。")
    bad = judge_answer(
        "整体用户流失率是多少？",
        "流失率 50%。")
    print("高质量回答评分:", {k: good[k] for k in ("correctness", "completeness", "insight")})
    print("低质量回答评分:", {k: bad[k] for k in ("correctness", "completeness", "insight")})
    assert good["correctness"] >= 4 and good["insight"] >= 4, "高质量回答评分过低"
    assert bad["correctness"] <= 3, "低质量回答正确性评分过高"
    print("Judge 区分度验证通过")


if __name__ == "__main__":
    run()
