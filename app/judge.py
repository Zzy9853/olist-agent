# app/judge.py
"""LLM-as-a-Judge：按 Rubrics 评估 Agent 回答质量（无参考评估）。
三维度：正确性（数值/事实准确）、完整性（答全问题）、洞察（业务解读质量）。
"""
import json

from app.llm import chat_json
from app.prompts import JUDGE_PROMPT, RUBRICS


def judge_answer(question: str, answer: str, double: bool = False) -> dict:
    """评估单个问答对。double=True 时双评（temperature 0.0 与 0.3）取各维度均值（降低单次波动）。"""
    def _single(temp: float) -> dict:
        prompt = JUDGE_PROMPT.format(question=question, answer=answer, RUBRICS=RUBRICS)
        out = chat_json([{"role": "system", "content": "你是严谨的数据分析评测官。"},
                         {"role": "user", "content": prompt}], temperature=temp)
        return {"correctness": int(out.get("correctness", 0)),
                "completeness": int(out.get("completeness", 0)),
                "insight": int(out.get("insight", 0)),
                "reasoning": out.get("reasoning", "")}

    r1 = _single(0.0)
    if not double:
        return r1
    r2 = _single(0.3)
    return {k: round((r1[k] + r2[k]) / 2, 1) if k != "reasoning" else r1["reasoning"]
            for k in r1}
