# Olist 指标口径字典（语义层 —— 所有 SQL 生成必须遵循）

**作用**：这是"指标语义层"。Agent 回答任何业务问题时，指标定义必须与本文档一致。
业务团队内部认可的口径，禁止 LLM 自行发明定义。

---

## 一、核心指标定义（不可更改）

| 指标 | 定义 | 依据 |
|------|------|------|
| **流失用户** | 最后一次购买距今（数据集末日 2018-09-03）超过 **90 天** | 用户平均购买间隔约 30 天，90 天覆盖 3 个周期 |
| **有效订单** | order_status 不在 ('canceled', 'unavailable') | 取消/不可用订单不产生真实交易（共约 1.2%） |
| **差评** | review_score ≤ 2 | 4-5 分满意、3 分中性、1-2 分不满 |
| **物流延迟** | order_delivered_customer_date > order_estimated_delivery_date | 实际送达晚于预估 |
| **物流延迟率** | 延迟订单数 / 有送达记录的订单数 | — |
| **复购用户** | order_count > 1 | — |
| **分期偏好用户** | 分期订单占比 > 30% | 单笔分期不足以代表偏好 |
| **高价值用户** | total_revenue ≥ R$90（全体用户中位数） | AB 实验人群筛选阈值 |
| **可挽救用户** | churn_prob 0.55-0.85 且 total_revenue ≥ R$90 | 中等风险 + 有挽回价值（19,890 人） |
| **履约漏斗环节** | 审核通过 / 交承运 / 签收 = 对应时间戳（order_approved_at / order_delivered_carrier_date / order_delivered_customer_date）非空；取消、不可用按 order_status 单独统计，不计入转化分子 | 时间戳比 order_status（当前状态快照）更准确反映环节到达 |
| **RFM 用户分层** | R = recency_days（≤ 中位数 224 天 = 近期）、F = order_count（>1 = 复购）、M = total_revenue（≥ 中位数 R$90 = 高消费），三维交叉 8 分层 | 全部字段已在 user_wide，可直接计算 |
| **券投放 ROI** | ROI =（增量收入 − 总成本）/ 总成本；增量收入 = 触达人群 × 留存提升率 × 人均 LTV（R$245）；盈亏平衡 uplift = 总成本 ÷（人群基数 × 人均 LTV） | 与 ab_test_results 表及基线表口径一致 |

## 二、关键基线数字（解读查询结果时的参照系）

| 基线 | 数值 |
|------|------|
| 整体流失率 | **81.2%**（94,983 用户中 77,129 流失） |
| 首单复购率 | 仅约 3%（97% 用户只买一次） |
| 留存用户平均配送天数 | 8.4 天 |
| 流失用户平均配送天数 | 13.2 天（高 57%） |
| 留存用户物流延迟率 | 5.7% |
| 流失用户物流延迟率 | 8.5%（高 49%） |
| 留存用户差评率 | 10.4% |
| 流失用户差评率 | 14.7%（高 41%） |
| 模型 Top-4 特征合计权重 | 47%（全是物流维度：avg_delivery_days 16.8%、delivery_delay_rate 11.3%、total_freight 9.8%、avg_delivery_vs_estimate 8.2%） |
| XGBoost 性能 | PR-AUC 0.97、ROC-AUC 0.88、F1 0.86 |
| 可挽救人群基线流失率 | 92.77%，平均 LTV R$245 |
| R$15 券盈亏平衡留存提升率 | **6.6%**（行业常规 5-15% 区间内） |
| R$25 券盈亏平衡 | 11.0% |
| R$50 券盈亏平衡 | 22.0%（不现实，已否决） |
| 流失用户累计贡献收入 | R$1,099 万（约合人民币 1,430 万） |
| 履约漏斗（全部订单 99,441 单） | 审核通过 99.8% → 交承运 98.2% → 签收 97.0%；取消 0.6% / 不可用 0.6% |
| 高价值久未购人群（R>224 天 且 M≥R$90） | **23,448 人**，平均消费 R$237.6 |

## 三、高频问题 → SQL 模板（few-shot 示例，可模仿改写）

```sql
-- Q1 整体流失率
SELECT AVG(is_churned) AS churn_rate, COUNT(*) AS total_users FROM user_wide;

-- Q2 各州流失率排名（Top 10）
SELECT customer_state, COUNT(*) AS users,
       ROUND(AVG(is_churned), 4) AS churn_rate
FROM user_wide
GROUP BY customer_state
ORDER BY churn_rate DESC
LIMIT 10;

-- Q3 流失用户 vs 留存用户画像对比
SELECT is_churned, AVG(avg_delivery_days) AS avg_delivery_days,
       AVG(delivery_delay_rate) AS delay_rate,
       AVG(low_score_rate) AS low_score_rate,
       AVG(total_revenue) AS avg_revenue
FROM user_wide
GROUP BY is_churned;

-- Q4 高流失风险高价值用户数（churn_prob 是模型预测概率，直接当风险分用）
SELECT COUNT(*) AS high_risk_high_value_users
FROM user_wide
WHERE churn_prob > 0.8 AND total_revenue >= 90;

-- Q5 物流延迟率最高的品类 Top 5（多表 JOIN 示例）
SELECT pt.product_category_name_english AS category,
       COUNT(*) AS orders,
       ROUND(AVG(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date
                      THEN 1 ELSE 0 END), 4) AS delay_rate
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
LEFT JOIN product_category_translation pt
       ON p.product_category_name = pt.product_category_name
WHERE o.order_status NOT IN ('canceled', 'unavailable')
  AND o.order_delivered_customer_date IS NOT NULL
GROUP BY pt.product_category_name_english
ORDER BY delay_rate DESC
LIMIT 5;

-- Q6 各品类用户留存率（复购率）
SELECT uf.favorite_category AS category,
       COUNT(*) AS users,
       ROUND(AVG(uf.is_repeat_buyer), 4) AS repeat_rate
FROM user_wide uf
WHERE uf.favorite_category IS NOT NULL
GROUP BY uf.favorite_category
ORDER BY repeat_rate DESC
LIMIT 10;

-- Q7 R$15 券在不同留存提升率下的 ROI
SELECT Coupon, Uplift, "Saved Users", "Incremental Revenue", "Total Cost", ROI
FROM ab_test_results
WHERE Coupon = 15
ORDER BY Uplift;

-- Q8 订单履约漏斗（四段转化率 + 取消/不可用）
SELECT COUNT(*) AS total_orders,
       ROUND(SUM(CASE WHEN order_approved_at IS NOT NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 4) AS approved_rate,
       ROUND(SUM(CASE WHEN order_delivered_carrier_date IS NOT NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 4) AS shipped_rate,
       ROUND(SUM(CASE WHEN order_delivered_customer_date IS NOT NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 4) AS delivered_rate,
       ROUND(SUM(CASE WHEN order_status = 'canceled' THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 4) AS canceled_rate,
       ROUND(SUM(CASE WHEN order_status = 'unavailable' THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 4) AS unavailable_rate
FROM orders;

-- Q9 RFM 用户价值分层（R≤中位数=近期 / F>1=复购 / M≥中位数=高消费）
WITH w AS (SELECT median(recency_days) AS r_med, median(total_revenue) AS m_med FROM user_wide)
SELECT CASE WHEN u.recency_days <= w.r_med THEN 'R近期' ELSE 'R久未购' END AS r_band,
       CASE WHEN u.order_count > 1 THEN 'F复购' ELSE 'F单次' END AS f_band,
       CASE WHEN u.total_revenue >= w.m_med THEN 'M高消费' ELSE 'M低消费' END AS m_band,
       COUNT(*) AS users,
       ROUND(AVG(u.is_churned), 4) AS churn_rate,
       ROUND(AVG(u.total_revenue), 2) AS avg_revenue
FROM user_wide u, w
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

-- Q10 相同留存提升下各券额 ROI 对比（选最优券额；Uplift 为浮点，须 ROUND 后比较）
SELECT ROUND(Uplift, 2) AS uplift, Coupon, ROI
FROM ab_test_results
WHERE ROUND(Uplift, 2) = 0.15
ORDER BY ROI DESC;
```

## 四、SQL 生成规则（Agent 的硬约束）

1. **只允许 SELECT**。禁止 DDL/DML（CREATE/DROP/INSERT/UPDATE/DELETE/ALTER）。
2. **用户级分析用 `customer_unique_id`**，绝不用 `customer_id`（会重复计数）。
3. **订单级金额**：订单含多商品时，先按 order_id 聚合订单金额，再聚合成用户级（避免重复计算）。
4. **查询优先用 `user_wide` 宽表**——流失/画像/风险类问题它都有，避免复杂 JOIN。
5. 需要"有效订单"口径时用视图 `valid_orders`（已排除 canceled/unavailable）。
6. 品类分析优先用 `product_category_name_english`（翻译表 LEFT JOIN，翻译缺失为 NULL 时排除该行）。
7. 计算配送天数/延迟必须过滤 `order_delivered_customer_date IS NOT NULL`。
8. 结果行数多时聚合后返回（TOP N + LIMIT），不要返回全量明细。
9. 时间类比较用 TIMESTAMP 列直接比较，不要转字符串。
10. 列名带空格或大写时用双引号引用（如 "Saved Users"），DuckDB 中双引号是标识符。
11. **特征重要性/特征排名数据来自 XGBoost 模型（feature_importances_/SHAP），数据库中不存在**——禁止用 SQL 查询或硬编码数值（如 0.168 AS importance 是虚构）。此类问题由模型解释路径回答，不走 SQL。
12. **履约类问题用 orders 时间戳字段判断环节**（order_approved_at / order_delivered_carrier_date / order_delivered_customer_date 非空），不要用 order_status 反推转化（它是当前状态快照）；取消/不可用按 order_status 单独口径。
