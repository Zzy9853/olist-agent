# app/judge.py
"""LLM-as-a-Judge：按 Rubrics 评估 Agent 回答质量（无参考评估）。
三维度：正确性（数值/事实准确）、完整性（答全问题）、洞察（业务解读质量）。
"""
import json

from app.llm import chat_json

RUBRICS = """评分维度（每维度 1-5 分）：
1. correctness 正确性：回答中的数值/事实是否准确、口径是否与业务定义一致（如流失=90天无购买）。
2. completeness 完整性：是否完整回答了问题的所有部分（如问 Top5 是否给出 5 个）。
3. insight 洞察：是否提供业务解读（对比基线、指出异常、给出建议），而非罗列数字。
评分要求：独立评估，不与其他题目比较；1=完全错误/缺失，3=基本正确但无亮点，5=准确且洞察深刻。
"""

JUDGE_PROMPT = """你是严谨的数据分析评测官。请按评分标准评估 AI 数据分析助手对用户问题的回答质量。

用户问题：{question}

AI 回答：
{answer}

{RUBRICS}
输出 JSON：{{"correctness": 1-5, "completeness": 1-5, "insight": 1-5, "reasoning": "一句话评分依据"}}
"""


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
