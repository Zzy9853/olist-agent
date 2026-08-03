# eval/run_eval.py
"""评测：对 20 问逐个调用 agent，EX = 执行结果与参考一致的占比。
结果对比规则（值等价匹配）：行数一致 → ref 每列在 gen 中按值匹配（列名/列序/行序自由）→ 数值容差 1e-6。
放宽原因：LLM 自由起别名/增减列是正常行为，按列名严格对比会误报（如 churned_users vs churned）。
"""
import sys
import pandas as pd

from app.agent import ask
from app.executor import execute_sql
from eval.eval_set import CASES

TOL = 1e-6


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            df[col] = df[col].round(6)
    return df


def _values_equal(s1: pd.Series, s2: pd.Series) -> bool:
    """两列值等价：数值列按排序后逐值容差比较；字符串列按集合比较。"""
    if len(s1) != len(s2):
        return False
    if pd.api.types.is_numeric_dtype(s1) and pd.api.types.is_numeric_dtype(s2):
        a = s1.astype(float).sort_values().reset_index(drop=True)
        b = s2.astype(float).sort_values().reset_index(drop=True)
        return bool(((a - b).abs() <= TOL).all())
    if pd.api.types.is_numeric_dtype(s1) != pd.api.types.is_numeric_dtype(s2):
        return False
    return bool(sorted(map(str, s1)) == sorted(map(str, s2)))


def results_equal(df1: pd.DataFrame, df2: pd.DataFrame) -> bool:
    """ref 的每一列必须在 gen 的结果中按值匹配（列名/列序/行序自由）。"""
    n1, n2 = normalize(df1), normalize(df2)
    if len(n1) != len(n2):
        return False
    used = set()
    for col_ref in n2.columns:
        hit = next((c for c in n1.columns
                    if c not in used and _values_equal(n1[c], n2[col_ref])), None)
        if hit is None:
            return False
        used.add(hit)
    return True


def main(limit: int | None = None):
    cases = CASES if limit is None else CASES[:limit]
    passed, fails = [], []
    for c in cases:
        r = ask(c["q"])
        if not r.get("sql"):
            fails.append((c["id"], "无 SQL", r["answer"]))
            continue
        ok, gen = execute_sql(r["sql"])
        if not ok:
            fails.append((c["id"], f"执行失败: {gen}", r["sql"]))
            continue
        ok2, ref = execute_sql(c["ref"])
        if results_equal(gen, ref):
            passed.append(c["id"])
        else:
            fails.append((c["id"], "结果不一致", f"gen={r['sql']}\nref={c['ref']}"))
    ex = len(passed) / len(cases)
    print(f"\nEX = {len(passed)}/{len(cases)} = {ex:.0%}")
    for fid, reason, extra in fails:
        print(f"\n❌ {fid}: {reason}\n  {extra[:200]}")
    return ex


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    sys.exit(0 if main(limit) >= 0.75 else 1)
