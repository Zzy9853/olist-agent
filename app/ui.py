# app/ui.py
"""Olist 智能问数 Agent — Streamlit 聊天界面（多会话 + 磁盘持久化）。
运行：python -m streamlit run app/ui.py
"""
import pandas as pd
import streamlit as st

from app.agent import ask
from app.conversations import (
    load_conversations, save_conversations, new_conversation,
    set_title, delete_conversation)
from app.executor import execute_sql

st.set_page_config(page_title="Olist 智能问数 Agent", page_icon="📊", layout="wide")

_CSS = """
<style>
.stApp { max-width: 1100px; margin: 0 auto; }
[data-testid="stSidebar"] { background: #f8f9fb; }
h1 { color: #1f6feb; }
[data-testid="stChatMessage"] { border-radius: 12px; padding: 12px 16px; margin: 8px 0; }
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)
st.title("📊 Olist 智能问数 Agent")
st.caption("用中文问 Olist 巴西电商数据——自由问答、流失诊断、归因解释，历史会话自动保存。")


def _safe_md(text: str) -> str:
    """转义裸美元符号，防止 Markdown 数学公式渲染（如 R$142 中的 $ 触发 KaTeX）。"""
    return text.replace("$", "\\$")


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


def _render_messages(messages: list[dict]):
    """渲染会话消息列表（含 SQL 展开与归因卡片）。"""
    for msg in messages:
        with st.chat_message(msg["role"]):
            st.markdown(_safe_md(msg["content"]))
            if msg.get("sql"):
                with st.expander("生成的 SQL"):
                    st.code(msg["sql"], language="sql")
            if msg.get("attribution"):
                a = msg["attribution"]
                if a.get("churn_prob") is not None:
                    st.markdown(f"**流失概率 {a['churn_prob']:.1%}**")
                if a.get("features"):
                    fdf = pd.DataFrame(a["features"])
                    st.bar_chart(fdf.set_index("feature")[["shap"]])
                for f in a["features"]:
                    st.markdown(f"- {f['feature']}: 值 {f.get('value', '—')}（SHAP {f['shap']:+.3f}）")


def _handle_prompt(prompt: str, conv: dict):
    """处理一条用户输入：渲染 → 调 agent → 渲染回答 → 写入会话。"""
    conv["messages"].append({"role": "user", "content": prompt})
    if len(conv["messages"]) == 1:
        set_title(conv, prompt)
    with st.chat_message("user"):
        st.markdown(_safe_md(prompt))
    history = [{"role": m["role"], "content": m["content"]}
               for m in conv["messages"][:-1]]
    with st.chat_message("assistant"):
        with st.spinner("分析中…"):
            r = ask(prompt, messages=history)
        st.markdown(_safe_md(r["answer"]))
        if r.get("sql"):
            with st.expander("生成的 SQL"):
                st.code(r["sql"], language="sql")
            ok, df = execute_sql(r["sql"])
            if ok:
                render_chart(df)
        attribution = r.get("attribution")
        if attribution:
            if attribution.get("churn_prob") is not None:
                st.markdown(f"**流失概率 {attribution['churn_prob']:.1%}**")
            if attribution.get("features"):
                fdf = pd.DataFrame(attribution["features"])
                st.bar_chart(fdf.set_index("feature")[["shap"]])
            for f in attribution["features"]:
                st.markdown(f"- {f['feature']}: 值 {f.get('value', '—')}（SHAP {f['shap']:+.3f}）")
    conv["messages"].append({"role": "assistant", "content": r["answer"],
                             "sql": r.get("sql"), "attribution": attribution})
    save_conversations(st.session_state.conversations)


def main():
    # 会话状态初始化
    if "conversations" not in st.session_state:
        st.session_state.conversations = load_conversations()
        st.session_state.current_id = None  # 草稿态：显示欢迎页，提问后创建

    # 侧边栏：新会话 + 历史列表 + 预置分析
    with st.sidebar:
        st.markdown("### 会话")
        if st.button("＋ 新会话", use_container_width=True):
            st.session_state.current_id = None
            st.session_state.conv_radio = None  # radio 不选中
            st.rerun()
        convs = st.session_state.conversations
        titles = {cid: conv["title"] for cid, conv in convs.items()}
        if convs:
            selected = st.radio("历史会话", list(titles.keys()),
                                format_func=lambda cid: titles[cid],
                                label_visibility="collapsed",
                                key="conv_radio",
                                index=None)  # 允许无选中（草稿态）
            if selected is not None and selected != st.session_state.current_id:
                st.session_state.current_id = selected
                st.rerun()
            if st.button("🗑 删除当前会话", use_container_width=True):
                if st.session_state.current_id is not None:
                    delete_conversation(st.session_state.conversations, st.session_state.current_id)
                st.session_state.current_id = None if not st.session_state.conversations else next(iter(st.session_state.conversations))
                st.session_state.conv_radio = st.session_state.current_id
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
                    if st.session_state.current_id is None:
                        cid, _ = new_conversation(st.session_state.conversations)
                        st.session_state.current_id = cid
                        st.session_state.conv_radio = cid
                    _handle_prompt(q, st.session_state.conversations[st.session_state.current_id])
                    st.rerun()

    # 历史消息渲染
    _render_messages(messages)

    # 工作流按钮消费（渲染循环后，与 chat_input 对称）
    if st.session_state.get("pending_workflow"):
        st.session_state.pending_workflow = False
        if st.session_state.current_id is None:
            cid, _ = new_conversation(st.session_state.conversations)
            st.session_state.current_id = cid
            st.session_state.conv_radio = cid
        _handle_prompt("运行流失诊断", st.session_state.conversations[st.session_state.current_id])
        st.rerun()

    # 输入框
    if prompt := st.chat_input("问点什么，例如：各州流失率排名？"):
        if st.session_state.current_id is None:
            cid, _ = new_conversation(st.session_state.conversations)
            st.session_state.current_id = cid
            st.session_state.conv_radio = cid
        _handle_prompt(prompt, st.session_state.conversations[st.session_state.current_id])
        st.rerun()


if __name__ == "__main__":
    main()
