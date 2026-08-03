# app/agent.py
"""LangGraph 编排：RAG 检索 → 生成 SQL → 校验 → 执行 → 解读。
失败路径：校验失败重试 1 次（携带错误信息）；仍失败转澄清追问。
"""
import json
import sys
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from app.config import MAX_RETRY, RAG_ENABLED
from app.executor import execute_sql
from app.knowledge import build_system_prompt
from app.llm import chat, chat_json
from app.rag import KnowledgeStore
from app.validator import validate_sql

GEN_PROMPT = """根据上下文生成 DuckDB SQL 回答用户问题。
输出 JSON：{{"sql": "生成的SQL", "reasoning": "一句思路说明"}}。
注意：如果问题无法用 SQL 回答（与数据无关/超范围），输出 {{"sql": null, "reasoning": "说明原因"}}。
"""

EXPLAIN_PROMPT = """查询结果如下（最多 {n} 行）：
{result}

请用 2-4 句中文解读：回答用户的问题、指出值得注意的发现。如结果包含比例/指标，对照常见基线判断是否异常（流失率约 81%、留存用户配送 8.4 天 vs 流失 13.2 天等）。不要编造数据。
"""


class State(TypedDict):
    question: str
    messages: list[dict]      # 对话历史
    system_prompt: str
    attempts: int
    sql: str | None
    result: str               # DataFrame 序列化文本或错误
    answer: str               # 最终回答
    error: str | None
    rag_context: str          # RAG 检索补充上下文（可空，retrieve 节点填充）


_STORE: KnowledgeStore | None = None


def _get_store() -> KnowledgeStore:
    """模块级缓存持久化 store（磁盘连接复用，避免每次查询重建实例）。"""
    global _STORE
    if _STORE is None:
        _STORE = KnowledgeStore()
    return _STORE


def _retrieve(state: State) -> State:
    """RAG 检索：命中块拼为补充上下文，增量追加到 system prompt 末尾。
    检索失败/关闭时 rag_context 为空——RAG 是补充，不影响主链路。
    """
    rag = ""
    if RAG_ENABLED:
        try:
            hits = _get_store().retrieve(state["question"], top_k=3)
        except Exception as e:
            print(f"[rag] 检索失败，降级为无 RAG 上下文: {e}", file=sys.stderr)
            hits = []
        if hits:
            rag = "\n\n## RAG 检索补充上下文\n" + "\n---\n".join(hits)
    state["rag_context"] = rag
    state["system_prompt"] = build_system_prompt(extra_context=rag)
    return state


def _gen_sql(state: State) -> State:
    """生成 SQL（含重试：第二次带校验错误信息）。"""
    retry_info = ""
    if state.get("error"):
        # 重试计数：必须在本节点内递增（节点的返回值才是 state 更新，
        # 路由函数里的修改不会写回状态通道，会导致无限重试）
        state["attempts"] = state.get("attempts", 0) + 1
        retry_info = f"\n上次 SQL 未通过校验，错误：{state['error']}。请修正后重新生成。"
    content = GEN_PROMPT.format() + retry_info + f"\n用户问题：{state['question']}"
    messages = [{"role": "system", "content": state["system_prompt"]}] + state.get("messages", []) + [
        {"role": "user", "content": content}]
    try:
        out = chat_json(messages)
    except Exception as e:
        state["sql"] = None
        state["error"] = f"LLM 调用失败: {e}"
        return state
    if out.get("sql"):
        ok, fixed = validate_sql(out["sql"])
        if ok:
            state["sql"] = fixed
            state["error"] = None
        else:
            state["sql"] = None
            state["error"] = fixed if not retry_info else "重试后仍失败: " + fixed
    else:
        state["sql"] = None
        state["error"] = out.get("reasoning", "LLM 未生成 SQL")
    return state


def _route_sql(state: State) -> str:
    if state["sql"] is not None:
        return "execute"
    if state.get("attempts", 0) < MAX_RETRY:
        return "retry"
    return "clarify"


def _execute(state: State) -> State:
    ok, res = execute_sql(state["sql"])
    if ok:
        state["result"] = res.to_string(index=False, max_rows=20)
    else:
        state["error"] = res
        state["result"] = ""
    return state


def _explain(state: State) -> State:
    if state.get("result"):
        prompt = EXPLAIN_PROMPT.format(n=20, result=state["result"])
        state["answer"] = chat(
            [{"role": "system", "content": "你是严谨的数据分析师，解读必须基于给出的结果。"},
             {"role": "user", "content": f"问题：{state['question']}\n\n{prompt}"}])
    else:
        state["answer"] = f"无法回答：{state.get('error', '生成 SQL 失败')}"
    return state


def _clarify(state: State) -> State:
    state["answer"] = f"这个问题我需要澄清一下：{state.get('error', '')}。请换一种问法，或提供更多信息。"
    return state


def build_graph():
    g = StateGraph(State)
    g.add_node("retrieve", _retrieve)
    g.add_node("gen_sql", _gen_sql)
    g.add_node("execute", _execute)
    g.add_node("explain", _explain)
    g.add_node("clarify", _clarify)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "gen_sql")
    g.add_conditional_edges("gen_sql", _route_sql,
                            {"execute": "execute", "retry": "gen_sql", "clarify": "clarify"})
    g.add_edge("execute", "explain")
    g.add_edge("explain", END)
    g.add_edge("clarify", END)
    return g.compile()


GRAPH = build_graph()


def ask(question: str, messages: list[dict] | None = None) -> dict:
    """入口：传入问题与可选历史消息，返回 {'answer': str, 'sql': str|None}。"""
    init: State = {
        "question": question,
        "messages": messages or [],
        "system_prompt": build_system_prompt(),  # RAG 补充上下文由 retrieve 节点增量注入
        "attempts": 0,
        "sql": None,
        "result": "",
        "answer": "",
        "error": None,
        "rag_context": "",
    }
    out = GRAPH.invoke(init)
    return {"answer": out.get("answer", ""), "sql": out.get("sql")}
