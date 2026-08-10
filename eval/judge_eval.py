# eval/judge_eval.py
"""LLM-as-a-Judge 批量评测：对 20 问跑 Judge 评分 + 与 EX 双轨对比。
用法：python -m eval.judge_eval [limit]
"""
import sys
import pandas as pd

from app.agent import ask
from app.executor import execute_sql
from app.judge import judge_answer
from eval.eval_set import CASES
from eval.run_eval import results_equal


def main(limit: int | None = None):
    cases = CASES if limit is None else CASES[:limit]
    rows = []
    for c in cases:
        r = ask(c["q"])
        # EX 判定（客观）
        ex_pass = False
        if r.get("sql"):
            ok, gen = execute_sql(r["sql"])
            ok2, ref = execute_sql(c["ref"])
            ex_pass = ok and ok2 and results_equal(gen, ref)
        # Judge 评分（主观）
        j = judge_answer(c["q"], r["answer"], double=True)
        rows.append({"id": c["id"], "ex": ex_pass, **j})

    df = pd.DataFrame(rows)
    print("\n=== 双轨评测结果 ===")
    print(df[["id", "ex", "correctness", "completeness", "insight"]].to_string(index=False))
    print(f"\nEX 通过率: {df['ex'].mean():.0%}")
    print(f"Judge 平均分: correctness {df['correctness'].mean():.2f} / "
          f"completeness {df['completeness'].mean():.2f} / "
          f"insight {df['insight'].mean():.2f}")
    ex_pass_group = df[df["ex"]]
    ex_fail_group = df[~df["ex"]]
    if len(ex_fail_group) > 0:
        print(f"\nEX 通过组 Judge 总分均值: {ex_pass_group[['correctness','completeness','insight']].sum(axis=1).mean():.2f}")
        print(f"EX 失败组 Judge 总分均值: {ex_fail_group[['correctness','completeness','insight']].sum(axis=1).mean():.2f}")
        print("（预期：通过组显著高于失败组——Judge 与 EX 一致性验证）")
    else:
        print("\n全部通过 EX——无法做分组对比，记录整体分数即可")
    return df


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    df = main(limit)
    df.to_csv("eval/judge_results.csv", index=False)
    print("\n结果已保存 eval/judge_results.csv")
