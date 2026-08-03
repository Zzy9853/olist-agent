# scripts/train_model.py
"""训练并保存 XGBoost 流失预测模型（复用电商项目参数，清理后的宽表）。
产物：data/churn_model.json + data/feature_cols.json，供 SHAP 归因使用。
"""
import json
from pathlib import Path

import duckdb
import pandas as pd
from xgboost import XGBClassifier
from sklearn.metrics import average_precision_score

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "olist.db"

FEATURE_COLS = [
    'order_count', 'active_months', 'total_revenue', 'avg_order_value',
    'total_freight', 'distinct_products', 'distinct_sellers',
    'avg_days_between_orders', 'is_repeat_buyer',
    'payment_types_count', 'credit_card_usage', 'boleto_usage',
    'debit_card_usage', 'voucher_usage',
    'avg_installments', 'max_installments', 'installment_order_count',
    'is_installment_user',
    'avg_review_score', 'low_score_rate',
    'avg_delivery_days', 'avg_delivery_vs_estimate', 'delivery_delay_rate',
    'category_diversity',
]


def main():
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute("SELECT * FROM user_wide").df()
    con.close()

    df = df.replace([float('inf'), float('-inf')], float('nan'))
    X = df[FEATURE_COLS].astype(float).fillna(0)
    y = df['is_churned'].astype(int)

    neg, pos = (y == 0).sum(), (y == 1).sum()
    model = XGBClassifier(
        n_estimators=200, max_depth=6, learning_rate=0.05,
        scale_pos_weight=neg / pos, subsample=0.8, colsample_bytree=0.8,
        random_state=42, eval_metric='logloss')
    model.fit(X, y)

    pr_auc = average_precision_score(y, model.predict_proba(X)[:, 1])
    print(f"样本: {len(df):,}  流失率: {y.mean():.2%}  PR-AUC(训练集): {pr_auc:.4f}")

    model.save_model(str(ROOT / "data" / "churn_model.json"))
    (ROOT / "data" / "feature_cols.json").write_text(
        json.dumps(FEATURE_COLS, ensure_ascii=False), encoding="utf-8")
    print("模型与特征列表已保存")


if __name__ == "__main__":
    main()
