# Olist 智能问数 Agent

用自然语言查询 Olist 巴西电商数据的 AI 数据分析 Agent（秋招简历主力项目）。

## 架构（五层）

```
① UI 层      Streamlit 聊天界面 + 图表 + 数据表格          [M3]
② Agent 编排  LangGraph 状态图：retrieve → gen_sql → validate [M2]
             → execute → explain，校验失败重试 1 次转澄清
③ 工具层      DuckDB 只读连接 / sqlglot AST 校验 / 会话记忆  [M2]（记忆 M3）
④ 知识层      RAG：schema + 指标口径 + 历史问答对            [M2]（问答对 M3）
⑤ 数据层      DuckDB olist.db（9 原始表 + 宽表 + AB 表）     [M1 ✅]
```

## 里程碑状态

- [x] **M1 数据层**（2026-08-03）：olist.db（9 原始表 + user_wide 95,106×32 + ab_test_results），只读连接验证通过
- [x] M1 知识库：`knowledge/schema.md`（数据字典）+ `knowledge/metrics.md`（指标口径 + 7 条 SQL 模板，全部验证可执行）
- [x] **M2 核心链路**（2026-08-03）：LangGraph 状态图（六节点 + 重试/澄清）+ sqlglot AST 校验（14/14 用例）+ 20 问评测集 **EX 95%**（两轮迭代 65% → 95%）+ 安全四道闸（AST 类型 / 12 表白名单 / 自动 LIMIT 200 / 5s 超时）+ RAG 架构预留（ChromaDB 16 块 + qwen embedding，EX 持平）——架构决策见 `docs/adr/2026-08-03-m2-nl2sql-architecture.md`
- [x] **M3 产品化**（2026-08-03）：Streamlit 聊天 UI（`python -m streamlit run app/ui.py`）+ intent 分类（query/explain/unsupported 路由）+ SHAP 归因（TreeExplainer 用户 Top 特征贡献）+ 多轮会话记忆（messages 注入，追问"那圣保罗呢"→SP 流失率 79.22%）；流失模型重训 **PR-AUC 0.9722** —— 面试素材见 `docs/interview/`，决策与踩坑见 `eval/iter_log.md` M3 小节

## 使用

```bash
# 重建数据库（从电商项目 CSV 重新加载）
python scripts/prepare_db.py

# 只读查询示例
python -c "import duckdb; con = duckdb.connect('data/olist.db', read_only=True); print(con.execute('SELECT AVG(is_churned) FROM user_wide').fetchone())"
```

## 演示（30 秒版）

```bash
python -m streamlit run app/ui.py
```

三步话术（面试边演示边讲，详细脚本见 `docs/interview/01-项目介绍.md` 演示叙事段）：

1. **查数**："整体用户流失率是多少？"（intent=query → SQL → 图表，答 81.20%）；"物流延迟率最高的 5 个品类有哪些？"（Top 5 柱状图——图表模板化，LLM 不生成绘图代码）；
2. **归因**："为什么这个用户流失风险高？用户 ID 是 97981245c3257ea9b14befffd560177b"（intent=explain → SHAP 归因卡片：概率 66.7%，avg_delivery_days 贡献 +1.44）；
3. **多轮追问**：追问"那圣保罗呢"（会话记忆 messages 注入生效，答 SP 流失率 79.22%，39,739 用户）。

## 数据资产来源

- 原始 CSV：`C:\Users\10936\Desktop\电商\olist_data\`
- 宽表 + AB 表：`C:\Users\10936\Desktop\电商\olist_analysis\data\`
- 语义层口径出处：`olist_analysis\sql\02_churn_feature_wide.sql` + `report\olist_churn_report.md`

## 环境

- Python 3.14 + duckdb 1.5.3（M2/M3 需安装：sqlglot、langgraph、langchain、chromadb、openai/dashscope、streamlit、xgboost、shap）
- LLM：阿里云百炼 API（DeepSeek-V4 / Qwen3-Plus）
