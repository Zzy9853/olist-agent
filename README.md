# Olist 智能问数 Agent

用自然语言查询 Olist 巴西电商数据的 AI 数据分析 Agent（秋招简历主力项目）。

## 架构（五层）

```
① UI 层      Streamlit 聊天界面 + 图表 + 数据表格          [M3]
② Agent 编排  LangGraph 状态图：intent → retrieve → gen_sql  [M2]
             → validate → execute → explain → respond
③ 工具层      DuckDB 只读连接 / sqlglot AST 校验 / 会话记忆  [M2]
④ 知识层      RAG：schema + 指标口径 + 历史问答对            [M2]
⑤ 数据层      DuckDB olist.db（9 原始表 + 宽表 + AB 表）     [M1 ✅]
```

## 里程碑状态

- [x] **M1 数据层**（2026-08-03）：olist.db（9 原始表 + user_wide 95,106×32 + ab_test_results），只读连接验证通过
- [x] M1 知识库：`knowledge/schema.md`（数据字典）+ `knowledge/metrics.md`（指标口径 + 7 条 SQL 模板，全部验证可执行）
- [ ] M2 核心链路：LangGraph + sqlglot 校验 + 20 问评测集
- [ ] M3 产品化：Streamlit UI + 会话记忆 + SHAP 归因

## 使用

```bash
# 重建数据库（从电商项目 CSV 重新加载）
python scripts/prepare_db.py

# 只读查询示例
python -c "import duckdb; con = duckdb.connect('data/olist.db', read_only=True); print(con.execute('SELECT AVG(is_churned) FROM user_wide').fetchone())"
```

## 数据资产来源

- 原始 CSV：`C:\Users\10936\Desktop\电商\olist_data\`
- 宽表 + AB 表：`C:\Users\10936\Desktop\电商\olist_analysis\data\`
- 语义层口径出处：`olist_analysis\sql\02_churn_feature_wide.sql` + `report\olist_churn_report.md`

## 环境

- Python 3.14 + duckdb 1.5.3（M2 需安装：sqlglot、langgraph、langchain、chromadb、openai/dashscope、streamlit）
- LLM：阿里云百炼 API（DeepSeek-V4 / Qwen3-Plus）
