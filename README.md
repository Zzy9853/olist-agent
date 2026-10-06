# Olist 智能问数 Agent

用自然语言查询 Olist 巴西电商数据的 AI 数据分析 Agent。

## 功能矩阵

| 能力 | 状态 | 说明 |
|------|:---:|------|
| Text2SQL 自然语言问数 | ✅ | LangGraph 编排，EX 95%（22 问开发集） |
| 安全 | ✅ | sqlglot AST 校验 + 12 表白名单 + LIMIT 兜底 + 5s 超时（四道闸） |
| 评测 | ✅ | 双轨：EX 客观执行对比 + LLM-as-a-Judge 主观评分（Rubrics 三维度） |
| 成本优化 | ✅ | 上下文缓存（固定前缀命中：~92% 输入走缓存，输入成本降至约 26%） |
| RAG | ✅ | ChromaDB + qwen embedding（架构预留，文档量增长后启用） |
| MCP | ✅ | MCP Server（stdio）：4 个工具 |
| UI | ✅ | Streamlit 聊天界面（多会话/懒创建 + 流式输出）+ 图表 + 归因卡片 + 工作流按钮 |
| 归因 | ✅ | SHAP 用户级与整体级解释 |
| 工作流 | ✅ | 流失诊断 / 履约诊断四步模板（概览/对比/归因/建议） |
| 经营分析模板 | ✅ | 履约漏斗 / RFM 用户分层 / 券投放 ROI 的口径与 SQL 模板（metrics.md 内置） |

## 快速开始

1. 克隆仓库并安装依赖：`git clone <repo-url> && cd olist-agent && pip install -r requirements.txt`
2. 准备数据（二选一）：
   - **方式 A（开箱即用）**：从 [最新 Release](https://github.com/Zzy9853/olist-agent/releases/latest) 下载 `olist-data.zip`，解压得 `olist.db` 放到 `data/`；
   - **方式 B（自行构建）**：下载 [Olist 数据集](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)（9 张 CSV），配置 `OLIST_DATA_DIR` 后运行 `python scripts/prepare_db.py`
3. 在 `.env` 配置 `DASHSCOPE_API_KEY`（方式 B 还需 `OLIST_DATA_DIR`）
4. 启动应用：`python -m streamlit run app/ui.py`
5. 评测（本地门禁）：`python -m eval.run_eval && python -m eval.judge_eval`

## 架构（五层）

```
① UI 层      Streamlit 聊天界面 + 图表 + 数据表格
② Agent 编排  LangGraph 状态图：retrieve → gen_sql → validate
             → execute → explain，校验失败重试 1 次转澄清
③ 工具层      DuckDB 只读连接 / sqlglot AST 校验 / 会话记忆
④ 知识层      RAG：schema + 指标口径 + 历史问答对
⑤ 数据层      DuckDB olist.db（9 原始表 + 宽表 + AB 表）
```

## MCP Server

以 stdio 传输暴露以下工具：

```bash
python -m app.mcp_server        # stdio 传输启动
```

| 工具 | 能力 |
|------|------|
| ask_data | 自然语言问数（完整 Agent 链路，安全校验内置） |
| explain_user | 用户流失归因（SHAP Top 特征） |
| list_tables | 数据表清单（能力发现） |
| validate_sql | SQL 安全校验（AST+白名单） |

**设计要点**：不暴露裸 SQL 执行——所有查询仍走四道闸 + 只读，MCP 是安全边界外的标准入口。

## 数据准备

本仓库不含原始数据，两种方式备齐：
- **方式 A**：下载 [olist-data.zip](https://github.com/Zzy9853/olist-agent/releases/latest)（已构建的完整数据库，约 45MB），解压得 `olist.db` 放入 `data/`；
- **方式 B**：从 [Olist 数据集](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)（9 张 CSV）自行构建——宽表与 AB 表由 `scripts/prepare_db.py` 自动构建（宽表特征 SQL：`sql/feature_wide.sql`，`churn_prob` 由仓库内 `data/churn_model.json` 打分）。

在项目 `.env` 配置：

```
DASHSCOPE_API_KEY=<阿里云百炼 API Key>
OLIST_DATA_DIR=<Olist 原始 CSV 目录>  # 方式 B 必需
```

> 数据许可：Olist 数据集来自 Kaggle，许可为 **CC BY-NC-SA 4.0**（非商业使用）。

## 使用

```bash
# 重建数据库（从配置的数据目录重新加载）
python scripts/prepare_db.py

# 只读查询示例
python -c "import duckdb; con = duckdb.connect('data/olist.db', read_only=True); print(con.execute('SELECT AVG(is_churned) FROM user_wide').fetchone())"
```

## 数据资产来源

- 原始数据：Olist 巴西电商公开数据集（Kaggle，9 张 CSV，见「数据准备」方式 B）
- 宽表特征 SQL：`sql/feature_wide.sql`（构建时自动从 9 张表生成 user_wide）
- 指标口径：`knowledge/metrics.md`（流失 / 复购 / 延迟等定义与基线）

## 环境

- Python 3.14 + duckdb 1.5.3；完整依赖见 `requirements.txt`（sqlglot、langgraph、langchain、chromadb、openai/dashscope、streamlit、xgboost、shap 等）
- LLM：阿里云百炼 API（DeepSeek-V4 / qwen3.7-plus）
