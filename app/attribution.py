# app/attribution.py
"""用户流失归因：加载模型 + TreeExplainer，对指定用户输出 Top 特征贡献。"""
import json
from pathlib import Path

import duckdb
import pandas as pd
import shap
from xgboost import XGBClassifier

from app.config import DB_PATH

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "data" / "churn_model.json"
FEATS_PATH = ROOT / "data" / "feature_cols.json"

_model = None
_explainer = None
_feats = None


def _load():
    global _model, _explainer, _feats
    if _model is None:
        _feats = json.loads(FEATS_PATH.read_text(encoding="utf-8"))
        _model = XGBClassifier()
        _model.load_model(bytearray(MODEL_PATH.read_bytes()))
        _explainer = shap.TreeExplainer(_model)
    return _model, _explainer, _feats


def explain_user(uid: str, top_k: int = 3) -> dict | None:
    """对用户输出流失归因：Top_k 特征贡献（SHAP 值，正=推高流失风险）。
    返回 {"uid", "churn_prob", "features": [{"feature", "value", "shap"}], "summary"}；
    用户不存在返回 None。
    """
    model, explainer, feats = _load()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    row = con.execute(
        "SELECT * FROM user_wide WHERE customer_unique_id = ?", [uid]).fetchdf()
    con.close()
    if row.empty:
        return None
    X = row[feats].astype(float).fillna(0)
    prob = float(model.predict_proba(X)[:, 1][0])
    sv = explainer.shap_values(X)[0]
    contrib = sorted(zip(feats, X.iloc[0].tolist(), sv),
                     key=lambda t: abs(t[2]), reverse=True)
    top = [{"feature": f, "value": round(v, 2), "shap": round(float(s), 4)}
           for f, v, s in contrib[:top_k]]
    summary = f"该用户流失概率 {prob:.1%}。主要驱动因素：" + \
              "，".join(f"{f}（贡献 {s:+.2f}）" for f, v, s in contrib[:top_k])
    return {"uid": uid, "churn_prob": round(prob, 4),
            "features": top, "summary": summary}


def explain_overall(top_k: int = 3, sample_size: int = 5000) -> list[dict]:
    """整体流失归因：采样用户 SHAP 均值贡献 Top_k。返回 [{"feature", "mean_shap"}]。"""
    model, explainer, feats = _load()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute(
        f"SELECT {', '.join(feats)} FROM user_wide USING SAMPLE {sample_size} ROWS").df()
    con.close()
    X = df[feats].astype(float).fillna(0)
    sv = explainer.shap_values(X)
    mean_shap = abs(sv).mean(axis=0)
    ranked = sorted(zip(feats, mean_shap), key=lambda t: t[1], reverse=True)
    return [{"feature": f, "mean_shap": round(float(v), 4)} for f, v in ranked[:top_k]]
