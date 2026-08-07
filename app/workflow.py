# app/workflow.py
"""流失诊断工作流（业务套路抽象）：概览 → 对比 → 归因 → 建议。
命中 JD"将高频可复用的分析套路抽象为工程化能力"。
"""
from app.attribution import explain_overall
from app.executor import execute_sql
from app.llm import chat
from app.prompts import WORKFLOW_ADVICE_SYSTEM, WORKFLOW_ADVICE_USER

STEP_SQL = {
    "overview": ("SELECT ROUND(AVG(is_churned), 4) AS churn_rate, "
                 "COUNT(*) AS total_users, SUM(is_churned) AS churned FROM user_wide"),
    "compare": ("""SELECT is_churned,
        ROUND(AVG(avg_delivery_days), 2) AS avg_delivery_days,
        ROUND(AVG(delivery_delay_rate), 4) AS delay_rate,
        ROUND(AVG(low_score_rate), 4) AS low_score_rate,
        ROUND(AVG(avg_review_score), 2) AS avg_review_score,
        ROUND(AVG(total_revenue), 2) AS avg_revenue
    FROM user_wide GROUP BY is_churned"""),
}


def run_churn_diagnosis() -> dict:
    """执行流失诊断四步工作流。返回 {"steps": [{"name", "detail"}...], "summary"}。"""
    steps = []

    # ① 概览
    ok, df = execute_sql(STEP_SQL["overview"])
    if not ok:
        return {"steps": [{"name": "概览", "detail": f"失败: {df}"}], "summary": "工作流执行失败"}
    r = df.iloc[0]
    steps.append({"name": "概览",
                  "detail": f"用户 {int(r['total_users']):,}，流失率 {r['churn_rate']:.1%}，"
                            f"流失 {int(r['churned']):,} 人"})

    # ② 对比（流失 vs 留存画像）
    ok, df = execute_sql(STEP_SQL["compare"])
    if not ok:
        return {"steps": steps + [{"name": "对比", "detail": f"失败: {df}"}], "summary": "工作流执行失败"}
    detail = []
    for _, row in df.iterrows():
        tag = "流失" if row["is_churned"] == 1 else "留存"
        detail.append(f"{tag}: 配送 {row['avg_delivery_days']}天/延迟率 {row['delay_rate']:.1%}/"
                      f"差评率 {row['low_score_rate']:.1%}/均消 R\\${row['avg_revenue']:.0f}")
    steps.append({"name": "对比", "detail": "；".join(detail)})

    # ③ 归因（整体 Top 特征）
    try:
        top = explain_overall(top_k=3)
        steps.append({"name": "归因",
                      "detail": "Top3 驱动特征：" + "，".join(
                          f"{t['feature']}（SHAP {t['mean_shap']:+.3f}）" for t in top)})
    except Exception as e:
        return {"steps": steps + [{"name": "归因", "detail": f"失败: {e}"}], "summary": "工作流执行失败"}

    # ④ 建议（LLM 基于前三步 + 基线生成）
    evidence = "\n".join(f"- {s['name']}: {s['detail']}" for s in steps)
    try:
        advice = chat([{"role": "system", "content": WORKFLOW_ADVICE_SYSTEM},
                       {"role": "user", "content": WORKFLOW_ADVICE_USER.format(evidence=evidence)}])
        steps.append({"name": "建议", "detail": advice})
    except Exception as e:
        return {"steps": steps + [{"name": "建议", "detail": f"失败: {e}"}], "summary": "工作流执行失败"}

    summary = f"流失诊断完成：{steps[0]['detail']}；{steps[2]['detail']}。"
    return {"steps": steps, "summary": summary}
