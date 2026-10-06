# app/workflow.py
"""诊断工作流（业务套路抽象）：概览 → 对比 → 归因 → 建议。
涵盖流失诊断（churn）与履约诊断（funnel）两条业务套路。
命中 JD"将高频可复用的分析套路抽象为工程化能力"。
"""
from app.attribution import explain_overall
from app.executor import execute_sql
from app.llm import stream_chat
from app.prompts import (WORKFLOW_ADVICE_SYSTEM, WORKFLOW_ADVICE_USER,
                         WORKFLOW_FUNNEL_ADVICE_SYSTEM, WORKFLOW_FUNNEL_ADVICE_USER)

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
        try:
            from langgraph.config import get_stream_writer
            writer = get_stream_writer()
        except Exception:
            writer = None
        advice_chunks = []
        for tk in stream_chat([{"role": "system", "content": WORKFLOW_ADVICE_SYSTEM},
                               {"role": "user", "content": WORKFLOW_ADVICE_USER.format(evidence=evidence)}]):
            advice_chunks.append(tk)
            if writer is not None:
                writer({"tokens": [tk]})
        advice = "".join(advice_chunks)
        steps.append({"name": "建议", "detail": advice})
    except Exception as e:
        return {"steps": steps + [{"name": "建议", "detail": f"失败: {e}"}], "summary": "工作流执行失败"}

    summary = f"流失诊断完成：{steps[0]['detail']}；{steps[2]['detail']}。"
    return {"steps": steps, "summary": summary}


# ═══ 履约诊断（funnel）═══
FUNNEL_STEP_SQL = {
    "overview": ("""SELECT COUNT(*) AS total_orders,
        ROUND(SUM(CASE WHEN order_approved_at IS NOT NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 4) AS approved_rate,
        ROUND(SUM(CASE WHEN order_delivered_carrier_date IS NOT NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 4) AS shipped_rate,
        ROUND(SUM(CASE WHEN order_delivered_customer_date IS NOT NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 4) AS delivered_rate,
        ROUND(SUM(CASE WHEN order_status = 'canceled' THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 4) AS canceled_rate,
        ROUND(SUM(CASE WHEN order_status = 'unavailable' THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 4) AS unavailable_rate
    FROM orders"""),
    "compare": ("""SELECT CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date
                    THEN '延迟' ELSE '准时' END AS group_tag,
        COUNT(*) AS orders,
        ROUND(AVG(DATEDIFF('day', o.order_purchase_timestamp, o.order_delivered_customer_date)), 2) AS avg_delivery_days,
        ROUND(AVG(DATEDIFF('day', o.order_estimated_delivery_date, o.order_delivered_customer_date)), 2) AS avg_vs_estimate,
        ROUND(AVG(r.review_score), 2) AS avg_review_score,
        ROUND(SUM(CASE WHEN r.review_score <= 2 THEN 1 ELSE 0 END) * 1.0 / NULLIF(COUNT(r.review_score), 0), 4) AS low_score_rate
    FROM orders o LEFT JOIN order_reviews r ON o.order_id = r.order_id
    WHERE o.order_delivered_customer_date IS NOT NULL
    GROUP BY 1"""),
    "attribution": ("""SELECT
        ROUND(AVG(DATEDIFF('day', order_purchase_timestamp, order_approved_at)), 2) AS seg_purchase_approved,
        ROUND(AVG(DATEDIFF('day', order_approved_at, order_delivered_carrier_date)), 2) AS seg_approved_carrier,
        ROUND(AVG(DATEDIFF('day', order_delivered_carrier_date, order_delivered_customer_date)), 2) AS seg_carrier_delivered
    FROM orders
    WHERE order_approved_at IS NOT NULL AND order_delivered_carrier_date IS NOT NULL
      AND order_delivered_customer_date IS NOT NULL"""),
}


def run_funnel_diagnosis() -> dict:
    """执行履约诊断四步工作流（概览 → 对比 → 归因 → 建议）。返回 {"steps", "summary"}。"""
    steps = []

    # ① 概览（履约漏斗四段转化）
    ok, df = execute_sql(FUNNEL_STEP_SQL["overview"])
    if not ok:
        return {"steps": [{"name": "概览", "detail": f"失败: {df}"}], "summary": "工作流执行失败"}
    r = df.iloc[0]
    steps.append({"name": "概览",
                  "detail": f"订单 {int(r['total_orders']):,}，审核通过 {r['approved_rate']:.1%} → "
                            f"交承运 {r['shipped_rate']:.1%} → 签收 {r['delivered_rate']:.1%}；"
                            f"取消 {r['canceled_rate']:.1%}、不可用 {r['unavailable_rate']:.1%}"})

    # ② 对比（延迟 vs 准时订单体验画像）
    ok, df = execute_sql(FUNNEL_STEP_SQL["compare"])
    if not ok:
        return {"steps": steps + [{"name": "对比", "detail": f"失败: {df}"}], "summary": "工作流执行失败"}
    detail = []
    for _, row in df.iterrows():
        detail.append(f"{row['group_tag']}: 平均配送 {row['avg_delivery_days']}天/"
                      f"相对预估 {row['avg_vs_estimate']:+.1f}天/均分 {row['avg_review_score']}/"
                      f"差评率 {row['low_score_rate']:.1%}")
    steps.append({"name": "对比", "detail": "；".join(detail)})

    # ③ 归因（环节耗时定位：瓶颈在哪一段）
    ok, df = execute_sql(FUNNEL_STEP_SQL["attribution"])
    if not ok:
        return {"steps": steps + [{"name": "归因", "detail": f"失败: {df}"}], "summary": "工作流执行失败"}
    r = df.iloc[0]
    segs = {"下单→审核": r["seg_purchase_approved"],
            "审核→承运": r["seg_approved_carrier"],
            "承运→签收": r["seg_carrier_delivered"]}
    slowest = max(segs, key=segs.get)
    steps.append({"name": "归因",
                  "detail": ("各环节平均耗时：" + "、".join(f"{k} {v}天" for k, v in segs.items())
                             + f"——瓶颈在「{slowest}」")})

    # ④ 建议（LLM 基于前三步 + 基线生成）
    evidence = "\n".join(f"- {s['name']}: {s['detail']}" for s in steps)
    try:
        try:
            from langgraph.config import get_stream_writer
            writer = get_stream_writer()
        except Exception:
            writer = None
        advice_chunks = []
        for tk in stream_chat([{"role": "system", "content": WORKFLOW_FUNNEL_ADVICE_SYSTEM},
                               {"role": "user", "content": WORKFLOW_FUNNEL_ADVICE_USER.format(evidence=evidence)}]):
            advice_chunks.append(tk)
            if writer is not None:
                writer({"tokens": [tk]})
        advice = "".join(advice_chunks)
        steps.append({"name": "建议", "detail": advice})
    except Exception as e:
        return {"steps": steps + [{"name": "建议", "detail": f"失败: {e}"}], "summary": "工作流执行失败"}

    summary = f"履约诊断完成：{steps[0]['detail']}；{steps[2]['detail']}。"
    return {"steps": steps, "summary": summary}
