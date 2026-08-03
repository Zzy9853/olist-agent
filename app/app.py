# app/app.py
"""Olist 智能问数 Agent — Streamlit 聊天界面。
运行：python -m streamlit run app/app.py
"""
import pandas as pd
import streamlit as st

from app.agent import ask
from app.executor import execute_sql

st.set_page_config(page_title="Olist 智能问数 Agent", page_icon="📊", layout="wide")
st.title("📊 Olist 智能问数 Agent")
st.caption("用中文问 Olist 巴西电商数据。示例：整体流失率？物流延迟率最高的 5 个品类？为什么某个用户流失风险高？")

if "messages" not in st.session_state:
    st.session_state.messages = []  # [{"role": "user"/"assistant", "content": ..., "sql":..., "attribution":...}]


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


def main():
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sql"):
                with st.expander("生成的 SQL"):
                    st.code(msg["sql"], language="sql")
            if msg.get("attribution"):
                a = msg["attribution"]
                st.markdown(f"**流失概率 {a['churn_prob']:.1%}**")
                for f in a["features"]:
                    st.markdown(f"- {f['feature']}: 值 {f['value']}（SHAP {f['shap']:+.3f}）")

    if prompt := st.chat_input("问点什么，例如：各州流失率排名？"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        history = [{"role": m["role"], "content": m["content"]}
                   for m in st.session_state.messages[:-1]]
        with st.chat_message("assistant"):
            with st.spinner("分析中…"):
                r = ask(prompt, messages=history)
            st.markdown(r["answer"])
            if r.get("sql"):
                with st.expander("生成的 SQL"):
                    st.code(r["sql"], language="sql")
                ok, df = execute_sql(r["sql"])
                if ok:
                    render_chart(df)
            attribution = r.get("attribution")
            if attribution:
                st.markdown(f"**流失概率 {attribution['churn_prob']:.1%}**")
                for f in attribution["features"]:
                    st.markdown(f"- {f['feature']}: 值 {f['value']}（SHAP {f['shap']:+.3f}）")
            st.session_state.messages.append({
                "role": "assistant", "content": r["answer"],
                "sql": r.get("sql"), "attribution": attribution})


if __name__ == "__main__":
    main()
