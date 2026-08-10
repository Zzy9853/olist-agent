# app/ui.py
"""Olist 智能问数 Agent — Streamlit 聊天界面（多会话 + 磁盘持久化）。
运行：python -m streamlit run app/ui.py
"""
import time

import pandas as pd
import streamlit as st

from app.agent import ask_stream
from app.conversations import (
    load_conversations, save_conversations, new_conversation,
    set_title, delete_conversation)
from app.executor import execute_sql

st.set_page_config(page_title="Olist 智能问数 Agent", page_icon="📊", layout="wide")

_CSS = """
<style>
.stApp { max-width: 1100px; margin: 0 auto; background: #faf8f3; }
[data-testid="stSidebar"] { background: #f4efe7; }
h1 { color: #4a6b5a; }
[data-testid="stChatMessage"] { background: #fff; border: 1px solid #eae3d8; border-radius: 12px; padding: 12px 16px; margin: 8px 0; }
[data-testid="stCaptionContainer"] { color: #8f8578; }
.stButton > button { background: #fff; border: 1px solid #eae3d8; border-radius: 12px; color: #4a443c; }
.stButton > button:hover { border-color: #b08968; color: #b08968; }
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"],
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"]:hover:enabled { background-color: #4a6b5a; border-color: #4a6b5a; color: #fff; }
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)
st.title("📊 Olist 智能问数 Agent")
st.caption("用中文问 Olist 巴西电商数据——自由问答、流失诊断、归因解释，历史会话自动保存。")


def _group_label(ts: float) -> str:
    """会话时间分组标题：今天/昨天/前 7 天/前 30 天/更早（YYYY-MM，如 2026-07）。"""
    today0 = time.mktime(time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d"))
    if ts >= today0:
        return "今天"
    if ts >= today0 - 86400:
        return "昨天"
    if ts >= today0 - 7 * 86400:
        return "前 7 天"
    if ts >= today0 - 30 * 86400:
        return "前 30 天"
    return time.strftime("%Y-%m", time.localtime(ts))


def _conv_label(conv: dict, selected: bool) -> str:
    """会话按钮 label：未选中 = 问题标题一行；选中 = 问题 + 最后提问时间两行（last_ts → MM-DD HH:MM）。"""
    question = conv["title"].split(" · ", 1)[0]
    if not selected:
        return question
    ts = conv.get("last_ts") or conv.get("created_ts") or time.time()
    return f"{question}\n{time.strftime('%m-%d %H:%M', time.localtime(ts))}"


def _safe_md(text: str) -> str:
    """转义裸美元符号，防止 Markdown 数学公式渲染（如 R$142 中的 $ 触发 KaTeX）。
    只转义未被转义的 $（已是 \\$ 的不动）——避免双重转义破坏已有转义。
    """
    import re
    return re.sub(r"(?<!\\)\$", r"\\$", text)


def render_chart(result_df: pd.DataFrame | None):
    """预置图表模板：日期列→折线；Top N→横向柱状；其余数值→柱状。"""
    if result_df is None or result_df.empty:
        return
    df = result_df.copy()
    date_cols = [c for c in df.columns if "date" in str(c).lower() or "month" in str(c).lower()]
    if date_cols:
        st.line_chart(df.set_index(date_cols[0]))
        return
    num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if len(num_cols) >= 1 and len(df) > 1:
        if len(df) <= 20:
            st.bar_chart(df.set_index(df.columns[0]))
        else:
            st.dataframe(df, height=300)


def _render_attribution_chart(features: list[dict]):
    """归因横向条形图（plotly）：特征名在 y 轴，长名可读。"""
    import plotly.graph_objects as go
    feats = [f["feature"] for f in features]
    shaps = [f.get("shap", 0) for f in features]
    fig = go.Figure(go.Bar(x=shaps, y=feats, orientation="h"))
    fig.update_layout(height=min(320, 44 * len(features) + 90),
                      margin=dict(l=110, r=20, t=10, b=10),
                      xaxis_title="SHAP 值", showlegend=False)
    st.plotly_chart(fig, use_container_width=True)


def _render_messages(messages: list[dict]):
    """渲染会话消息列表（含 SQL 展开、图表与归因卡片）。"""
    for msg in messages:
        with st.chat_message(msg["role"]):
            st.markdown(_safe_md(msg["content"]))
            if msg.get("sql"):
                with st.expander("生成的 SQL"):
                    st.code(msg["sql"], language="sql")
                ok, df = execute_sql(msg["sql"])
                if ok:
                    render_chart(df)
            if msg.get("attribution"):
                a = msg["attribution"]
                if a.get("churn_prob") is not None:
                    st.markdown(f"**流失概率 {a['churn_prob']:.1%}**")
                if a.get("features"):
                    _render_attribution_chart(a["features"])
                for f in a["features"]:
                    st.markdown(f"- {f['feature']}: 值 {f.get('value', '—')}（SHAP {f['shap']:+.3f}）")


def _handle_prompt(prompt: str, conv: dict):
    """处理一条用户输入：流式渲染 → 写入会话。"""
    conv["messages"].append({"role": "user", "content": prompt})
    if len(conv["messages"]) == 1:
        set_title(conv, prompt)
    with st.chat_message("user"):
        st.markdown(_safe_md(prompt))
    history = [{"role": m["role"], "content": m["content"]}
               for m in conv["messages"][:-1]]

    with st.chat_message("assistant"):
        with st.spinner("分析中…"):
            done = {}

            async def _tokens():
                nonlocal done
                async for ev in ask_stream(prompt, messages=history):
                    if ev["type"] == "stage":
                        continue
                    if ev["type"] == "token":
                        yield _safe_md(ev["content"])  # 逐 token 转义防 R$ 公式
                    elif ev["type"] == "done":
                        done = ev

            text = st.write_stream(_tokens())
        if not text and done.get("answer"):
            text = done["answer"]
        st.markdown(_safe_md(text))

        if done.get("sql"):
            with st.expander("生成的 SQL"):
                st.code(done["sql"], language="sql")
            ok, df = execute_sql(done["sql"])
            if ok:
                render_chart(df)
        attribution = done.get("attribution")
        if attribution:
            if attribution.get("churn_prob") is not None:
                st.markdown(f"**流失概率 {attribution['churn_prob']:.1%}**")
            if attribution.get("features"):
                _render_attribution_chart(attribution["features"])
            for f in attribution["features"]:
                st.markdown(f"- {f['feature']}: 值 {f.get('value', '—')}（SHAP {f['shap']:+.3f}）")

    conv["messages"].append({"role": "assistant", "content": done.get("answer") or text,
                             "sql": done.get("sql"), "attribution": done.get("attribution")})
    conv["last_ts"] = time.time()  # 最后提问时间（分组与选中显示用）
    save_conversations(st.session_state.conversations)


def main():
    # 会话状态初始化
    if "conversations" not in st.session_state:
        st.session_state.conversations = load_conversations()
        st.session_state.current_id = None  # 草稿态：显示欢迎页，提问后创建

    # 侧边栏：新会话 + 历史列表 + 预置分析
    with st.sidebar:
        st.markdown("### 会话")
        if st.button("＋ 新对话", use_container_width=True, type="primary"):
            st.session_state.current_id = None
            st.rerun()
        convs = st.session_state.conversations
        if convs:
            st.markdown("##### 历史会话")
            # 按最后提问时间分组：今天/昨天/前7天/前30天固定序，更早（YYYY-MM）倒序
            groups: dict[str, list[str]] = {}
            for cid, conv in convs.items():
                ts = conv.get("last_ts") or conv.get("created_ts") or time.time()
                groups.setdefault(_group_label(ts), []).append(cid)
            fixed = ("今天", "昨天", "前 7 天", "前 30 天")
            order = [g for g in fixed if g in groups]
            order += sorted(set(groups) - set(fixed), reverse=True)
            for g in order:
                st.markdown(f"**{g}**")
                for cid in groups[g]:
                    is_current = cid == st.session_state.current_id
                    if st.button(_conv_label(convs[cid], is_current), use_container_width=True,
                                 type="primary" if is_current else "secondary",
                                 key=f"conv_btn_{cid}"):
                        st.session_state.current_id = cid
                        st.rerun()
            if st.button("🗑 删除当前会话", use_container_width=True, type="secondary"):
                if st.session_state.current_id is not None:
                    delete_conversation(st.session_state.conversations, st.session_state.current_id)
                st.session_state.current_id = None
                save_conversations(st.session_state.conversations)
                st.rerun()
        st.markdown("---")
        st.markdown("### 预置分析")
        if st.button("📊 运行流失诊断", use_container_width=True):
            st.session_state.pending_workflow = True

    current_id = st.session_state.current_id
    conv = (st.session_state.conversations.get(current_id)
            if current_id is not None else None)
    messages = conv["messages"] if conv else []

    # 空状态欢迎页
    if not messages:
        st.markdown("#### 试试这些问题：")
        c1, c2, c3, c4 = st.columns(4)
        examples = [
            ("整体流失率", "整体用户流失率是多少？"),
            ("Top5 品类", "物流延迟率最高的 5 个品类有哪些？"),
            ("流失诊断", "运行流失诊断"),
            ("用户归因", "为什么这个用户流失风险高？用户ID是 97981245c3257ea9b14befffd560177b"),
        ]
        cols = [c1, c2, c3, c4]
        for col, (label, q) in zip(cols, examples):
            with col:
                if st.button(label, use_container_width=True):
                    st.session_state.pending_prompt = q
                    st.rerun()

    # 历史消息渲染
    _render_messages(messages)

    # 欢迎页示例按钮消费（pending 模式：点击只置 pending + rerun，在此主区域消费，
    # 避免在 columns 内流式渲染被约束列宽）
    if st.session_state.get("pending_prompt"):
        q = st.session_state.pop("pending_prompt")
        if st.session_state.current_id is None:
            cid, _ = new_conversation(st.session_state.conversations)
            st.session_state.current_id = cid
        _handle_prompt(q, st.session_state.conversations[st.session_state.current_id])
        st.rerun()

    # 工作流按钮消费（渲染循环后，与 chat_input 对称）
    if st.session_state.get("pending_workflow"):
        st.session_state.pending_workflow = False
        if st.session_state.current_id is None:
            cid, _ = new_conversation(st.session_state.conversations)
            st.session_state.current_id = cid
        _handle_prompt("运行流失诊断", st.session_state.conversations[st.session_state.current_id])
        st.rerun()

    # 输入框
    if prompt := st.chat_input("问点什么，例如：各州流失率排名？"):
        if st.session_state.current_id is None:
            cid, _ = new_conversation(st.session_state.conversations)
            st.session_state.current_id = cid
        _handle_prompt(prompt, st.session_state.conversations[st.session_state.current_id])
        st.rerun()


if __name__ == "__main__":
    main()
