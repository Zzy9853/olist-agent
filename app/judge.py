# app/judge.py
"""LLM-as-a-Judge：按 Rubrics 评估 Agent 回答质量（无参考评估）。
三维度：正确性（数值/事实准确）、完整性（答全问题）、洞察（业务解读质量）。
"""
import json

from app.llm import chat_json
from app.prompts import JUDGE_PROMPT, RUBRICS


def judge_answer(question: str, answer: str) -> dict:
    """评估单个问答对，返回 {"correctness", "completeness", "insight", "reasoning"}。"""
    prompt = JUDGE_PROMPT.format(question=question, answer=answer, RUBRICS=RUBRICS)
    out = chat_json([{"role": "system", "content": "你是严谨的数据分析评测官。"},
                     {"role": "user", "content": prompt}])
    return {
        "correctness": int(out.get("correctness", 0)),
        "completeness": int(out.get("completeness", 0)),
        "insight": int(out.get("insight", 0)),
        "reasoning": out.get("reasoning", ""),
    }
