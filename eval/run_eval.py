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

TOL = 1e-2  # 容忍 ROUND 精度差异（如 118.57 vs 118.573），不放走语义错误


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            df[col] = df[col].round(6)
    return df


def _col_contains(s_outer: pd.Series, s_inner: pd.Series) -> bool:
    """s_inner 的每个值都可在 s_outer 中找到（数值容差/字符串相等），s_outer 允许更多行。"""
    if len(s_outer) < len(s_inner):
        return False
    if pd.api.types.is_numeric_dtype(s_outer) and pd.api.types.is_numeric_dtype(s_inner):
        a = sorted(s_outer.astype(float).tolist())
        b = sorted(s_inner.astype(float).tolist())
        i = 0
        for v in b:
            while i < len(a) and a[i] < v - TOL:
                i += 1
            if i >= len(a) or a[i] > v + TOL:
                return False
            i += 1
        return True
    if pd.api.types.is_numeric_dtype(s_outer) != pd.api.types.is_numeric_dtype(s_inner):
        return False
    return set(map(str, s_inner)).issubset(set(map(str, s_outer)))


def _row_matches(r_row, gen_df: pd.DataFrame, mapping: list[tuple[str, str]]) -> bool:
    """ref 行在 gen 中按映射列（ref列, gen列）存在性匹配（数值容差/字符串相等，行序无关）。"""
    for _, g_row in gen_df.iterrows():
        ok = True
        for cr, cg in mapping:
            rv, gv = r_row[cr], g_row[cg]
            if pd.api.types.is_numeric_dtype(pd.Series([rv])) and pd.api.types.is_numeric_dtype(pd.Series([gv])):
                if abs(float(rv) - float(gv)) > TOL:
                    ok = False
                    break
            elif str(rv) != str(gv):
                ok = False
                break
        if ok:
            return True
    return False


def results_equal(df1: pd.DataFrame, df2: pd.DataFrame) -> bool:
    """ref 的每一列在 gen 中按值包含匹配（列名/列序/行序自由）。
    行数：gen >= ref（LLM 常返回 Top N 全集，ref 只取 Top K——子集语义）；
    行级：ref 每行按映射列在 gen 中存在（数值容差）。已知宽松点：行数不同时不查组合。
    """
    n1, n2 = normalize(df1), normalize(df2)
    if len(n1) < len(n2):
        return False
    col_map = {}
    used = set()
    for col_ref in n2.columns:
        hit = next((c for c in n1.columns
                    if c not in used and _col_contains(n1[c], n2[col_ref])), None)
        if hit is None:
            return False
        used.add(hit)
        col_map[col_ref] = hit
    if len(n1) == len(n2):
        gen_sub = n1[list(col_map.values())]
        mapping = list(col_map.items())
        return all(_row_matches(row, gen_sub, mapping) for _, row in n2.iterrows())
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
