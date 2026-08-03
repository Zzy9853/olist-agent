# app/test_attribution.py
"""归因自检：有效用户返回 Top 特征；无效用户返回 None。"""
from app.attribution import explain_user
from app.executor import execute_sql


def run():
    ok, df = execute_sql("SELECT customer_unique_id, is_churned FROM user_wide LIMIT 3")
    for _, row in df.iterrows():
        r = explain_user(row["customer_unique_id"])
        assert r is not None and len(r["features"]) == 3, "归因结构异常"
        print(f"用户 {row['customer_unique_id'][:12]}... 流失={row['is_churned']} "
              f"概率={r['churn_prob']} Top1={r['features'][0]['feature']}")
    assert explain_user("nonexistent_user_000") is None, "无效用户应返回 None"
    print("归因自检通过")


if __name__ == "__main__":
    run()
