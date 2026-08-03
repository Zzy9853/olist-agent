# scripts/test_train_model.py
"""模型保存产物自检：模型可加载、特征列表一致、预测可用。"""
import json
from pathlib import Path

import duckdb
import pandas as pd
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "olist.db"


def run():
    model_bytes = (ROOT / "data" / "churn_model.json").read_bytes()
    model = XGBClassifier()
    model.load_model(bytearray(model_bytes))
    feats = json.loads((ROOT / "data" / "feature_cols.json").read_text(encoding="utf-8"))
    assert len(feats) == 24, f"特征数异常: {len(feats)}"

    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute("SELECT * FROM user_wide LIMIT 5").df()
    con.close()
    X = df[feats].astype(float).fillna(0)
    prob = model.predict_proba(X)[:, 1]
    assert all(0 <= p <= 1 for p in prob), "概率越界"
    print(f"模型加载 OK，5 个用户预测概率: {[round(p, 3) for p in prob]}")
    print("特征列表 OK（24 个）")


if __name__ == "__main__":
    run()
