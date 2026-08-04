# ADR：MCP 封装 + Judge 双轨评测架构决策

- **日期**：2026-08-03（MCP 封装）/ 2026-08-04（Judge 双轨评测）
- **主题**：Olist 智能问数 Agent 工程化外延——Agent 能力封装为 MCP Server（对外标准接口）与评测体系升级为 EX + LLM-as-a-Judge 双轨
- **状态**：已实施（MCP 4 工具集成测试全过；Judge 双轨 20 问评测完成，关键发现"自洽错误骗过 Judge"）
- **作者**：Claude Code + 赵洲宇（项目 Owner）

## 背景

M3 完成后，Agent 的核心能力（NL2SQL 问数、SHAP 归因、SQL 安全校验）全部收敛在 `app/agent.py` 与 Streamlit UI 内，存在两个结构性缺口：

1. **能力被 UI 绑定**：`ask()` 只能在自己做的 Streamlit 界面里被调用——Claude Desktop / Claude Code / Cursor 等标准客户端想用这套能力，必须各自适配；
2. **评测只测"结果对不对"**：EX 95% 回答的是"SQL 执行结果与参考是否值等价"，但"解读好不好"（有没有对比基线、指出异常、给建议）没有任何测量手段——两个 Agent 都答对数字，用户价值可能完全不同。

据此形成 2 个决策，逐一记录。

**决策速查**

| # | 决策点 | 决策 | 一句话理由 |
|---|--------|------|-----------|
| A | 能力出口 | MCP Server（FastMCP + stdio，4 工具）而非自定义 API | 协议标准化 + 能力自描述 + 任意 MCP 客户端复用 |
| B | 评测体系 | EX + LLM-as-a-Judge 双轨 | EX 测"结果对不对"，Judge 测"解读好不好"，主观不能替代客观 |

---

## 决策 A：MCP Server 封装 vs 自定义 API

### 背景

外部 AI 客户端（Claude Desktop / Claude Code / Cursor）要调用本项目能力。传统做法是给每个客户端写一套对接；MCP（Model Context Protocol，Anthropic 2024 发布的 AI 应用与外部工具/数据源的开放协议）标准化了"工具发现—调用—返回"的交互，解决 N 个 AI 应用 × M 个工具的 M×N 两两对接问题（统一协议后是 M+N）。

### 方案对比

| 候选 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A：自定义 REST API | 自己定义 HTTP 端点 + 鉴权 + schema | 路由/鉴权完全自控 | 每个客户端要写一套适配（M×N）；schema 自描述要自己维护；LLM 接入还要额外转成函数声明 |
| B：MCP Server | FastMCP 把工具声明为 `@mcp.tool()`，stdio 传输 | 协议标准化（一次实现任意客户端复用）；**能力自描述**（工具 schema 随协议发布，客户端自动发现工具/参数/描述）；结构化 schema 天然适配 LLM 上下文 | 依赖 MCP 生态（主流客户端已原生支持）；stdio 本地传输，远程化需换 HTTP/SSE |

### 决策

**B：MCP Server**（`app/mcp_server.py`，FastMCP + stdio，`python -m app.mcp_server` 启动），4 个工具按**能力域**切分而非按函数切：

| 工具 | 能力 | 切分依据 |
|------|------|---------|
| ask_data | 自然语言问数（内部走完整 Agent 链路：生成→校验→执行→解读，安全校验内置） | 完整链路入口，客户端最小决策单元 |
| explain_user | SHAP 用户流失归因（Top 特征） | 归因是独立客户端意图，与问数并列 |
| list_tables | 数据表清单 | 能力发现——客户端先看"有什么表"再决定问什么 |
| validate_sql | SQL 安全校验（AST + 白名单） | 校验能力可单独复用 |

### 理由

- **协议标准化 > 自建接口**：能力与 UI 解耦是工程化外延——"我把 Agent 封装成了标准协议工具"比"我做了个 UI"有说服力；工具 schema 即函数声明，LLM 客户端靠"工具名 + 描述"决定何时调哪个工具、传什么参数（docstring 原样暴露为 schema 描述）；
- **工具粒度 = 客户端最小决策单元**：太细则调用次数爆炸（一个问数任务被拆成十几次 MCP 往返 + LLM 决策）；太粗则客户端无法单独复用其中一环（如只想校验一段 SQL 也必须走完整链路）——问数/归因/查表/校验是四种独立的客户端意图，每种一个工具；
- **不暴露裸 SQL 执行**：MCP 是安全边界外的标准入口，但不是后门——外部客户端不能拿一段 SQL 直接打数据库；可执行的 SQL 只由 ask_data 内部生成并过四道闸（AST 类型 / 12 表白名单 / 自动 LIMIT 200 / 5s 超时）+ 只读连接，外部传入的 SQL 只能走 validate_sql（只校验、永不执行），MCP 层无注入面；
- **实现代价低**：FastMCP 声明式注册 4 个工具函数即完成封装，内部复用 `app/agent.py` / `app/attribution.py` / `app/validator.py` 同一套代码，不引入第二套能力实现。

### 补充：真实踩坑（MCP 封装的两个边界问题）

1. **工具名遮蔽同名导入**：`from app.attribution import explain_user` + `@mcp.tool() def explain_user` → `def` 在模块命名空间重绑定导入名，函数体内调用自身无限递归（RecursionError）。修复：导入别名 `_explain_user` / `_validate_sql`，工具名保持对外可见（commit ffdfcd9）；
2. **numpy float32 JSON 序列化崩溃**：`round(np.float32, 4)` 仍返回 float32，MCP 层 json.dumps 抛 TypeError（numpy 2.x 收紧隐式转换）。修复：`round(float(s), 4)` 显式类型转换（`app/attribution.py`，同一 commit）。

详细四段式（坑 → 根因 → 修复 → 面试话术）见 `docs/interview/04-踩坑记录.md` 坑 11/12。

---

## 决策 B：双轨评测体系——EX 之外为什么还要 LLM-as-a-Judge

### 背景

EX 95% 证明了"SQL 执行结果正确"，但评测目标不是"SQL 对不对"而是"回答值不值钱"：两个 Agent 都答对数字，一个只说"95 人"、一个给了业务洞察（基线对比/异常指认/行动建议），EX 相同但用户价值不同。解读质量必须有人评——引入 LLM-as-a-Judge（`app/judge.py`，Judge 用 qwen3.7-plus，与主链路同模型，复用 chat_json，不引入新依赖）。

### 方案对比

| 候选 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A：仅 EX 执行对比 | 生成 SQL 执行结果 vs 参考 SQL 结果值等价 | 客观、可复现、零主观性 | 只测"结果对不对"，测不到"解读好不好"；执行错误若回答文本自洽，EX 之外无兜底 |
| B：EX + LLM-as-a-Judge 双轨 | EX 客观对比 + Judge 按 Rubrics 三维度（正确性/完整性/洞察，1-5 分）无参考评估问答对 | 客观正确 + 主观质量两条腿；双轨对账可验证评测可信 | Judge 是受控的主观判断，有偏差风险（位置/自我偏好/长度偏差），需锚点与自检约束 |

### 决策

**B：双轨评测**（`eval/judge_eval.py` 批量 20 问 + EX 双轨对比）——**EX 做客观回归门禁，Judge 分做质量趋势指标**（不做硬门禁，绝对分有尺度漂移风险，趋势比单点可靠）。

### 理由

- **EX 测不到"解读好不好"**：值等价对比判不了"只说数字 vs 有业务洞察"的差异——解读深度、完整性、表达可读性是 EX 的盲区，必须有人评；
- **无参考评估避免泄漏**：Judge 只看"用户问题 + Agent 回答"（不看参考 SQL/答案），评分评的是"回答本身质量"而非"与参考答案的相似度"——参考答案不进入评分上下文，避免评测泄漏（泄漏 = 分数虚高）；
- **关键发现（反预期，最有力的决策证据）**：双轨对比假设"EX 通过组 Judge 分显著高于失败组"——实测 EX 失败组（Q18，n=1）Judge 总分 **15.00 反高于通过组 14.58**：Q18 该轮 EX 失败（执行结果与参考不一致），但回答文本内部自洽（数字、占比、业务解读俱全），无参考 Judge 只评文本、看不到执行结果，给了满分 5/5/5——**"自洽的错误"可以骗过无参考 Judge，主观评分不能替代客观执行验证**，双轨互补才是完整评测：EX 兜住 Judge 测不到的执行错误，Judge 补上 EX 测不到的解读质量；
- **Judge 可信的三重约束**：①Rubrics 锚点（每维度带 1/3/5 定义：1=完全错误/缺失、3=基本正确但无亮点、5=准确且洞察深刻）；②低温度 + json_object 结构化输出（temperature=0.0，实测两次运行完全一致）；③区分度自检（`app/test_judge.py` 高质量回答 5/5/5 vs 低质量回答 1/1/1，Judge 能区分好坏，评分才有意义）；通过组内部仍有区分度（Q07 completeness=3，未列全 Top10），排除无脑满分。

---

## 实施验证（决策回执）

| 决策 | 验证结果 |
|------|---------|
| MCP Server | 4 工具注册 + 真实调用集成测试全过（ask_data 真实 LLM 问数 / explain_user 真实 SHAP / list_tables 12 表 / validate_sql 拦截 DROP）；序列化与命名坑修复后无回归 |
| 双轨评测 | 20 问 EX 95%（唯一失败 Q18）+ Judge 平均 correctness 5.00 / completeness 4.90 / insight 4.70（`eval/judge_run.txt`）；区分度 5/5/5 vs 1/1/1 两次运行一致；失败组 15.00 vs 通过组 14.58 反预期结论复现 |
