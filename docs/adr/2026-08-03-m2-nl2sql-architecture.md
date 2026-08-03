# ADR：M2 NL2SQL 核心链路架构决策

- **日期**：2026-08-03
- **主题**：Olist 智能问数 Agent M2——NL2SQL 核心链路（编排 / 知识注入 / LLM 选型 / SQL 安全校验）的技术选型
- **状态**：已实施（LangGraph 五节点状态图——validate 内联于 gen_sql，EX 95%；面试叙事口径为"六节点"将校验单列，见 docs/interview/01）
- **作者**：Claude Code + 赵洲宇（项目 Owner）

## 背景

M2 的目标是把自然语言问题转成 DuckDB SQL 并执行解读。这条链路有三个结构性特征，直接决定编排选型：

1. **失败必然发生**：LLM 生成的 SQL 可能语法错误、越权（非白名单表）、执行超时——必须有重试与澄清分支；
2. **状态需要跨节点传播**：错误信息要回灌下一次生成、attempts 要计数、结果要传往解读节点；
3. **安全不可妥协**：生成侧（校验）与执行侧（只读 + 超时）都要有防线。

据此形成 4 个决策点，逐一记录。

**决策速查**

| # | 决策点 | 决策 | 一句话理由 |
|---|--------|------|-----------|
| 1 | 编排框架 | LangGraph StateGraph（非 Chain） | 分支/重试/澄清声明式表达，状态显式化可观测 |
| 2 | 知识注入 | 全量注入优先，RAG 架构预留 | 文档仅 16KB，全量最可靠；RAG 为扩展性预留 |
| 3 | LLM 选型 | qwen3.7-plus + OpenAI 兼容协议 | JSON 结构化输出 + 生态兼容 + 不绑死厂商 |
| 4 | SQL 校验 | sqlglot AST 校验（非正则黑名单） | 语法级理解，多语句/变体天然拦截 |

---

## 决策 1：LangGraph StateGraph vs 简单 Chain 调用

### 背景

初始方案是最朴素的函数串联：生成 → 校验 → 执行 → 解读。但需求里有重试（校验失败带错误回灌重试 1 次）、分支（仍失败转澄清）、以及后续 M3 的 intent 分类——控制流不是一条直线。

### 方案对比

| 候选 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A：Chain 顺序调用 | `gen_sql() → validate() → execute() → explain()` 写成函数串联，重试用 if-else | 零依赖、上手快 | 分支逻辑散落在业务代码里；错误上下文靠函数返回值传递，回灌不自然；链路不可观测；M3 加 intent 分类要改调用方 |
| B：LangGraph StateGraph | 显式 State（TypedDict）+ 节点 + 条件边路由 | 分支声明式；状态走通道集中传播；checkpoint 可观测；扩展只加节点和边 | 引入框架依赖与学习成本 |

### 决策

**B：LangGraph StateGraph**（`app/agent.py`，五节点：retrieve → gen_sql → execute → explain + clarify，条件边三出口；SQL 校验是 gen_sql 节点的内联步骤，叙事口径可单列为"校验闸门"）。

### 理由

- **条件路由**：`_route_sql` 条件边按 `sql/attempts/error` 三出口路由（execute / retry / clarify），重试与澄清是图上的声明，不是业务代码里的 if-else——面试叙事上这是"Agent 编排"与"硬编码流程"的分水岭；
- **状态显式化**：`error`、`sql`、`result`、`attempts`、`rag_context` 都在 State 通道传播。重试天然支持"错误信息回灌下一次生成"（gen_sql 节点读 state["error"] 拼进 prompt），不用额外设计返回值协议；
- **checkpoint 可观测性**：每一步的 state 可落盘回放，调试能精确回答"哪一步失败、为什么"，评测失败也能定位到具体节点；
- **扩展叙事**：M3 的 intent 分类只需加节点 + 连边，不重写调用链。

### 补充：真实踩坑（langgraph 1.2.10）

条件边的**路由函数只读 state、返回边名，返回值不写回状态通道**。曾把 `attempts += 1` 写在 `_route_sql` 里——attempts 恒为 0，永远走 retry，触发 GraphRecursionError 无限循环。修复：attempts 必须在 gen_sql 节点内递增（commit 453ba30，节点返回值才是 state 更新）。这是对"图执行语义"理解的实锤证据，面试必讲。

---

## 决策 2：知识库全量注入优先 + RAG 后置

### 背景

`knowledge/` 只有两份文档：schema.md（7.7KB）+ metrics.md（5.5KB），合计约 13KB ≈ 4k token。M2 第一版需要决定知识怎么进 system prompt。

### 方案对比

| 候选 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A：全量注入 system prompt | build_system_prompt 把两份文档整体拼入 | 信息零丢失、不依赖检索质量、实现最简单 | 文档量增长后 token 成本线性增长 |
| B：RAG 检索注入 | 切块 → 向量化 → top-k 检索拼入 prompt | token 成本与文档量解耦 | 检索质量影响信息完整度（检索不到 = 口径缺失）；多一层系统复杂度 |

### 决策

**A 优先实施；B 作为架构预留**（`RAG_ENABLED` 开关 + retrieve 节点已实现，默认开）。

### 理由

- **16KB ≈ 4k token 全量注入可靠性最高**：文档量小到可以全量塞进 prompt，任何问题都保证带着完整口径字典——不会出现"检索不到导致口径缺失"的失败模式；口径一致性是问数 Agent 的命根，宁可多花 token 不冒检索风险；
- **RAG 是扩展性预留**：文档量增长后（历史问答对、更多业务文档），全量注入的 token 成本线性上涨；按问题检索 top-k 注入则成本与文档量解耦。检索 → 注入链路已打通，届时只换切块粒度/检索策略；
- **T8 实测佐证**：RAG 前 EX 95%（19/20）→ RAG 后 EX 95%（19/20）——持平。16 块文档全量已覆盖全部信息，top-k=3 是冗余增量；无增益（EX 不变）也无干扰（未破坏任何已过题）。持平 → 不回退开关，保留为架构预留（详细对比见 `eval/iter_log.md`）。

### RAG 实现要点（T8，供扩展参考）

- **存储**：ChromaDB 持久化（`data/chroma`），跨进程复用磁盘集合；
- **嵌入**：qwen3.7-text-embedding（百炼 OpenAI 兼容 embeddings 端点）；
- **切块**：按 `## / ###` 标题切块，共 16 块（schema 12 + metrics 4），块 id = `文档名:标题`；
- **幂等索引**：collection metadata 存文档 hash（`doc_hash`），hash 未变则跳过重建，防静默过期；
- **注入方式**：每问 retrieve top_k=3，拼为 `state["rag_context"]` 增量追加到 system prompt 末尾——不改变原 prompt 结构，系统头铁律始终全量注入。

---

## 决策 3：qwen3.7-plus + OpenAI 兼容协议

### 背景

核心链路要求：中文业务理解 + 可约束的 JSON 结构化输出（gen_sql 需要 `{"sql", "reasoning"}`）+ 便宜可迭代。

### 方案对比

| 候选 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A：百炼 qwen3.7-plus（OpenAI 兼容端点） | `base_url = https://dashscope.aliyuncs.com/compatible-mode/v1` | 支持 response_format 结构化输出；openai SDK 生态通用；中文电商语义理解好；成本低 | 依赖阿里云账号（.env 配 Key） |
| B：deepseek-v4-pro | 推理强 | 对话/推理模型强项在复杂推理，NL2SQL 中文业务场景无显著优势；成本更高 | JSON 结构化输出稳定性与 qwen 无代差优势 |
| C：本地 7B | 本地部署 | 数据不出域、无 API 成本 | 中文 SQL 生成质量与 JSON 输出稳定性不足，迭代评测会拖后腿 |

### 决策

**A：qwen3.7-plus + OpenAI 兼容协议**（`app/config.py`：`CHAT_MODEL = "qwen3.7-plus"`、`BASE_URL = dashscope compatible-mode`）。

### 理由

- **JSON 结构化输出**：`response_format={"type": "json_object"}` 约束模型输出合法 JSON，gen_sql 节点解析 `{"sql", "reasoning"}` 直给；chat_json 再兜一层容错（剥离 markdown 围栏、首尾非 JSON 文本），双保险；
- **生态兼容**：chat / chat_json / embeddings 走同一 openai SDK 客户端，RAG 的 embedding 复用同一 base_url，无第二套 SDK；
- **成本低**：评测要反复全量跑 20 问，模型成本敏感；
- **不绑死厂商**：base_url / model 名都是 `app/config.py` 常量，换模型只改配置——这是 OpenAI 兼容协议的核心价值（协议标准化 > 厂商绑定）。

---

## 决策 4：sqlglot AST 校验 vs 正则匹配

### 背景

LLM 生成的 SQL 是注入面：可能被诱导生成 DROP/DELETE、访问非白名单表、或超长查询拖垮执行。这是安全红线（项目硬规则第 3 条），校验方案必须经得起绕过尝试。

### 方案对比

| 候选 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A：正则黑名单 | 拦截 DROP/DELETE 等关键词 | 实现 10 行内 | 变体可绕过：大小写、注释混淆、换行、子查询嵌套、缩写；误杀率也高（列名/字符串里含关键词） |
| B：sqlglot AST 解析 + 类型/白名单检查 | 解析成语法树 → 类型检查 → 表名白名单 → 自动 LIMIT | 语法级理解，结构与意图一眼看穿；大小写无关；别名/CTE 正确处理 | 引入 sqlglot 依赖 |

### 决策

**B：sqlglot AST 校验**（`app/validator.py`）。

### 理由

- **AST 是语法级理解**：多语句 `SELECT ...; DROP TABLE ...` 被解析为 **Block 容器**——不是 Select/SetOperation，类型检查天然拦截（正则会被分号拆分/注释变体绕过）；大小写、别名、CTE 由解析器统一处理，无字符串匹配的绕过空间；
- **实测 14/14**：`app/test_validator.py` 覆盖合法通过（单表/聚合/UNION/CTE）与危险拦截（DROP/DELETE/INSERT/CREATE/UPDATE/多语句/非白名单表/空 SQL），全绿；
- **安全侧误杀修复（也是测试的价值）**：初始只放行 `exp.Select`，UNION 查询被误杀——sqlglot 把 UNION/INTERSECT/EXCEPT 解析为 **SetOperation 子类**，补白名单后放行；`WITH t AS (...)` 的 CTE 名是查询内临时表，不属于物理白名单，做 CTE 名豁免。两个误杀都是测试用例先暴露再修复的。

### 安全四道闸（纵深防御，面试叙事主线）

| # | 闸 | 实现 | 防什么 |
|---|-----|------|--------|
| 1 | AST 类型检查 | `isinstance(tree, (exp.Select, exp.SetOperation))`，Block/DDL/DML 全拦截 | 多语句注入、写操作 |
| 2 | 表名白名单 | `find_all(exp.Table)` 遍历，12 个白名单对象（9 原始表 + user_wide 宽表 + ab_test_results + valid_orders 视图），CTE 名豁免 | 访问非白名单数据 |
| 3 | 自动 LIMIT 200 兜底 | 无 LIMIT 时 `tree.limit(200)`，已有则不动 | 超大结果集拖垮内存 |
| 4 | 5s 执行超时 | watchdog 线程 `threading.Timer(5, con.interrupt)`——DuckDB 1.5.x 无 SET timeout，用协作式中断 | 恶意/病态慢查询 |

执行侧再叠两层：数据库**只读连接**（`read_only=True`，写操作物理不可能）+ 结果超 200 行截断。校验器在生成侧、执行器在运行侧，闸门分开，单一防线被绕仍有兜底。

---

## 实施验证（决策回执）

| 决策 | 验证结果 |
|------|---------|
| LangGraph 编排 | 20 问评测全链路跑通；重试 1 次 + 澄清路径测试通过；EX 65% → 95% |
| 全量注入 + RAG | RAG 前后 EX 均 95%（19/20，`eval/rag_run.txt`），无回退 |
| qwen3.7-plus | chat_json 结构化输出全链路可用；20 问无一次 JSON 解析失败导致的失败 |
| sqlglot 校验 | 14/14 用例通过；评测期未发生任何越权 SQL 进入执行器 |
