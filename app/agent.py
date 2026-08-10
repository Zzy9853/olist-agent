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
from app.llm import chat, chat_json, stream_chat
from app.prompts import EXPLAIN_PROMPT, build_system_prompt
from app.rag import KnowledgeStore
from app.validator import validate_sql


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
    intent: str               # query | explain | workflow | unsupported（gen_sql 节点判定）
    uid: str | None           # 归因目标用户 ID（explain 路径填充）
    attribution: dict | None  # 归因结果（attribution 节点填充）
    workflow_result: dict | None  # 工作流结果（workflow 节点填充）


_STORE: KnowledgeStore | None = None


def _get_store() -> KnowledgeStore:
    """模块级缓存持久化 store（磁盘连接复用，避免每次查询重建实例）。
    首次创建时同步索引：文档 hash 未变则跳过，变了则重建（防静默过期）。
    """
    global _STORE
    if _STORE is None:
        _STORE = KnowledgeStore()
        try:
            from app.knowledge import load_knowledge
            _STORE.ensure_index(load_knowledge())
        except Exception as e:
            print(f"[rag] 索引初始化失败: {e}", file=sys.stderr)
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
    content = retry_info + f"\n用户问题：{state['question']}"
    messages = [{"role": "system", "content": state["system_prompt"]}] + state.get("messages", []) + [
        {"role": "user", "content": content}]
    try:
        out = chat_json(messages)
    except Exception as e:
        state["sql"] = None
        state["error"] = f"LLM 调用失败: {e}"
        return state
    intent = out.get("intent", "query")  # 旧格式兼容：默认 query
    state["intent"] = intent
    if intent == "explain":
        state["uid"] = out.get("uid") or None  # None → 整体归因
        state["sql"] = None  # 归因不走 SQL
        state["error"] = None
        return state
    if intent == "workflow":
        state["sql"] = None
        state["error"] = None
        return state
    if intent == "unsupported":
        state["sql"] = None
        state["error"] = out.get("reasoning", "LLM 判定该问题无法回答")
        return state
    # query：现有 SQL 生成/校验逻辑保持不变
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
    if state.get("intent") == "explain":
        return "attribution"
    if state.get("intent") == "workflow":
        return "workflow"
    if state.get("intent") == "unsupported":
        return "clarify"
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
        try:
            from langgraph.config import get_stream_writer
            writer = get_stream_writer()
        except Exception:
            writer = None
        chunks = []
        for tk in stream_chat(
                [{"role": "system", "content": "你是严谨的数据分析师，解读必须基于给出的结果。"},
                 {"role": "user", "content": f"问题：{state['question']}\n\n{prompt}"}]):
            chunks.append(tk)
            if writer is not None:
                writer({"tokens": [tk]})
        state["answer"] = "".join(chunks)
    else:
        state["answer"] = f"无法回答：{state.get('error', '生成 SQL 失败')}"
    return state


def _attribution(state: State) -> State:
    from app.attribution import explain_overall, explain_user
    try:
        if state.get("uid"):
            result = explain_user(state["uid"])
        else:
            top = explain_overall(top_k=5)
            result = {"uid": None, "churn_prob": None,
                      "features": [{"feature": t["feature"], "shap": t["mean_shap"]}
                                   for t in top],
                      "summary": "整体 Top5 驱动特征：" + "，".join(
                          f"{t['feature']}（SHAP {t['mean_shap']:+.3f}）" for t in top)}
    except Exception as e:
        state["answer"] = f"归因失败：{e}"
        return state
    if result is None:
        state["answer"] = f"未找到用户 {state['uid']}，请确认用户 ID 正确。"
    else:
        state["attribution"] = result
        try:
            from langgraph.config import get_stream_writer
            writer = get_stream_writer()
        except Exception:
            writer = None
        chunks = []
        for tk in stream_chat(
                [{"role": "system", "content": "你是严谨的数据分析师，解读必须基于给出的归因数据。"},
                 {"role": "user", "content": f"用户问题：{state['question']}\n\n归因数据：{result['summary']}\n\n请用 2-3 句中文解读。"}]):
            chunks.append(tk)
            if writer is not None:
                writer({"tokens": [tk]})
        state["answer"] = "".join(chunks)
    return state


def _workflow(state: State) -> State:
    from app.workflow import run_churn_diagnosis
    try:
        result = run_churn_diagnosis()
    except Exception as e:
        state["answer"] = f"工作流执行失败：{e}"
        return state
    lines = [f"**{s['name']}**：{s['detail']}" for s in result["steps"]]
    state["answer"] = "\n\n".join(lines)
    state["workflow_result"] = result
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
    g.add_node("attribution", _attribution)
    g.add_node("workflow", _workflow)
    g.add_node("clarify", _clarify)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "gen_sql")
    g.add_conditional_edges("gen_sql", _route_sql,
                            {"execute": "execute", "retry": "gen_sql", "clarify": "clarify",
                             "attribution": "attribution", "workflow": "workflow"})
    g.add_edge("execute", "explain")
    g.add_edge("explain", END)
    g.add_edge("attribution", END)
    g.add_edge("workflow", END)
    g.add_edge("clarify", END)
    return g.compile()


GRAPH = build_graph()


def ask(question: str, messages: list[dict] | None = None) -> dict:
    """入口：传入问题与可选历史消息，返回 {'answer', 'sql', 'intent', 'attribution', 'workflow_result'}。"""
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
        "intent": "query",
        "uid": None,
        "attribution": None,
        "workflow_result": None,
    }
    out = GRAPH.invoke(init)
    return {"answer": out.get("answer", ""), "sql": out.get("sql"),
            "intent": out.get("intent"), "attribution": out.get("attribution"),
            "workflow_result": out.get("workflow_result")}


_STAGE_NAMES = {"retrieve": "检索知识", "gen_sql": "生成 SQL", "execute": "执行查询",
                "explain": "解读结果", "attribution": "生成归因", "workflow": "执行工作流"}


async def _astream_events(init: State):
    """遍历 astream 双通道事件（langgraph 1.2 多模式产出 (mode, payload) 二元组）；
    按节点累计 updates，供 done 提取完整最终状态。"""
    last_updates = {}
    async for mode, payload in GRAPH.astream(init, stream_mode=["updates", "custom"]):
        if mode == "custom":
            if isinstance(payload, dict) and payload.get("tokens"):
                for tk in payload["tokens"]:
                    yield {"type": "token", "content": tk}
        elif mode == "updates":
            last_updates.update(payload)  # 按节点合并；同一节点重跑（如 retry）覆盖旧值
            for node in payload:
                yield {"type": "stage", "node": node}
    yield {"type": "_last", "updates": last_updates}


def ask_stream(question: str, messages: list[dict] | None = None):
    """流式入口（async 生成器）：yield {"type": "stage"|"token"|"done", ...}。
    UI 专用；评测/MCP 用同步 ask()。done 事件携带完整结果。
    """
    init: State = {
        "question": question,
        "messages": messages or [],
        "system_prompt": build_system_prompt(),
        "attempts": 0,
        "sql": None,
        "result": "",
        "answer": "",
        "error": None,
        "rag_context": "",
        "intent": "query",
        "uid": None,
        "attribution": None,
        "workflow_result": None,
    }

    async def _gen():
        last = {}
        try:
            async for ev in _astream_events(init):
                if ev["type"] == "_last":
                    last = ev["updates"]
                    continue
                if ev["type"] == "stage":
                    yield {"type": "stage", "node": ev["node"],
                           "label": _STAGE_NAMES.get(ev["node"], ev["node"])}
                else:
                    yield ev
        except Exception as e:
            yield {"type": "done", "answer": f"执行失败：{e}", "sql": None,
                   "attribution": None, "workflow_result": None}
            return
        # 从累计 updates 提取最终状态
        final = {}
        for node_update in last.values():
            final.update(node_update)
        if not final.get("answer"):
            # fallback：节点更新不携带 answer 时，同步重跑取结果（仅异常路径触发）
            out = GRAPH.invoke(init)
            final = {"answer": out.get("answer", ""), "sql": out.get("sql"),
                     "attribution": out.get("attribution"),
                     "workflow_result": out.get("workflow_result")}
        yield {"type": "done",
               "answer": final.get("answer", ""),
               "sql": final.get("sql"),
               "attribution": final.get("attribution"),
               "workflow_result": final.get("workflow_result")}

    return _gen()
