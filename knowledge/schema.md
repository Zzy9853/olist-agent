# Olist 数据库 Schema 字典（给 Agent 的 SQL 生成上下文）

数据来源：Olist 巴西电商平台（2016.09-2018.09，约 10 万订单 / 9.6 万真实用户）。
数据库：DuckDB（olist.db，只读连接）。所有表均以 VARCHAR 主键关联。

## 关系概览

```
customers(1) ── orders(N) ── order_items(N) ── products(1)
                │  │   └────── order_payments(N)
                │  └────────── order_reviews(N)
                └───────────── sellers(1)
product_category_translation: 葡语品类名 → 英语
user_wide: 用户级特征宽表（含流失标签和预测概率）
ab_test_results: AB 实验敏感性分析表
```

**⚠️ 最重要陷阱**：`orders.customer_id` 是订单级客户标识（同一真人每次下单可能不同），
真正的用户唯一 ID 是 `customers.customer_unique_id`（仅 96,096 个）。用户级分析必须用 `customer_unique_id`。

---

## orders（订单表，99,441 行）

| 列 | 类型 | 含义 |
|----|------|------|
| order_id | VARCHAR | 订单 ID（主键） |
| customer_id | VARCHAR | 客户 ID（关联 customers，⚠️ 非用户唯一 ID） |
| order_status | VARCHAR | 订单状态：delivered / shipped / canceled / unavailable / invoiced / processing / created / approved |
| order_purchase_timestamp | TIMESTAMP | 下单时间 |
| order_approved_at | TIMESTAMP | 付款审批时间 |
| order_delivered_carrier_date | TIMESTAMP | 交给承运商时间 |
| order_delivered_customer_date | TIMESTAMP | **实际送达时间**（计算配送天数/延迟的关键列，部分 shipped 订单为 NULL） |
| order_estimated_delivery_date | TIMESTAMP | **预估送达时间**（与实达对比计算延迟） |

## customers（客户表，99,441 行）

| 列 | 类型 | 含义 |
|----|------|------|
| customer_id | VARCHAR | 订单级客户标识（与 orders 一一对应） |
| customer_unique_id | VARCHAR | **真实用户唯一 ID**（用户级分析一律用它） |
| customer_zip_code_prefix | VARCHAR | 邮编前缀 |
| customer_city | VARCHAR | 城市 |
| customer_state | VARCHAR | 州（巴西 27 个州，如 SP=圣保罗，RJ=里约） |

## order_items（订单商品明细，112,650 行，1 单可能多商品）

| 列 | 类型 | 含义 |
|----|------|------|
| order_id | VARCHAR | 订单 ID |
| order_item_id | INTEGER | 商品在订单内的序号（从 1 开始） |
| product_id | VARCHAR | 商品 ID（关联 products） |
| seller_id | VARCHAR | 卖家 ID（关联 sellers） |
| shipping_limit_date | TIMESTAMP | 卖家发货截止时间 |
| price | DOUBLE | 商品单价（R$，巴西雷亚尔） |
| freight_value | DOUBLE | 运费（R$） |

**⚠️ 聚合陷阱**：一笔订单含多个商品时，直接 SUM(price) GROUP BY order 会重复计算订单金额——订单级金额需先按 (order_id) 聚合再使用。

## order_payments（订单支付，103,886 行，1 单可能多种支付方式）

| 列 | 类型 | 含义 |
|----|------|------|
| order_id | VARCHAR | 订单 ID |
| payment_sequential | INTEGER | 支付顺序（1 单多支付方式时递增） |
| payment_type | VARCHAR | 支付方式：credit_card / boleto / debit_card / voucher |
| payment_installments | INTEGER | 分期数（>1 表示分期支付） |
| payment_value | DOUBLE | 支付金额（R$） |

## order_reviews（订单评论，99,224 行）

| 列 | 类型 | 含义 |
|----|------|------|
| review_id | VARCHAR | 评论 ID |
| order_id | VARCHAR | 订单 ID |
| review_score | INTEGER | 评分 1-5（**≤2 视为差评**） |
| review_comment_title | VARCHAR | 评论标题（多为空） |
| review_comment_message | VARCHAR | 评论文本（多为空） |
| review_creation_date | TIMESTAMP | 评论创建时间 |
| review_answer_timestamp | TIMESTAMP | 卖家回复时间 |

## products（商品，32,951 行）

| 列 | 类型 | 含义 |
|----|------|------|
| product_id | VARCHAR | 商品 ID |
| product_category_name | VARCHAR | 葡语品类名（需关联翻译表） |
| product_name_lenght | INTEGER | 商品名长度（注意源数据拼写为 lenght） |
| product_description_lenght | INTEGER | 描述长度 |
| product_photos_qty | INTEGER | 图片数量 |
| product_weight_g / product_length_cm / product_height_cm / product_width_cm | INTEGER | 商品物理属性 |

## sellers（卖家，3,095 行）

| 列 | 类型 | 含义 |
|----|------|------|
| seller_id | VARCHAR | 卖家 ID |
| seller_zip_code_prefix | VARCHAR | 邮编前缀 |
| seller_city / seller_state | VARCHAR | 城市 / 州 |

## product_category_translation（品类翻译，71 行）

| 列 | 类型 | 含义 |
|----|------|------|
| product_category_name | VARCHAR | 葡语品类名 |
| product_category_name_english | VARCHAR | **英语品类名（分析时优先用英语列）** |

## geolocation（地理定位，1,000,163 行）

| 列 | 类型 | 含义 |
|----|------|------|
| geolocation_zip_code_prefix | VARCHAR | 邮编前缀（可关联 customers/sellers 的 zip） |
| geolocation_lat / geolocation_lng | DOUBLE | 经纬度 |
| geolocation_city / geolocation_state | VARCHAR | 城市 / 州 |

## user_wide（用户特征宽表，95,106 行 —— 流失分析的核心查询目标）

每行一个真实用户（customer_unique_id）。**绝大多数"流失分析"问题直接查此表，无需 JOIN。**

| 列 | 类型 | 含义 |
|----|------|------|
| customer_unique_id | VARCHAR | 用户唯一 ID |
| order_count | BIGINT | 累计订单数 |
| active_months | BIGINT | 活跃月份数 |
| total_revenue | DOUBLE | 累计消费金额（R$） |
| avg_order_value | DOUBLE | 平均订单金额 |
| total_freight | DOUBLE | 累计运费 |
| distinct_products / distinct_sellers | BIGINT | 购买过的商品数 / 卖家数 |
| avg_days_between_orders | DOUBLE | 平均购买间隔天数 |
| is_repeat_buyer | BIGINT | 是否复购（订单数>1） |
| recency_days | BIGINT | 距最后一次购买天数（相对数据集末日） |
| payment_types_count | BIGINT | 使用过的支付方式数 |
| credit_card_usage / boleto_usage / debit_card_usage / voucher_usage | BIGINT | 各支付方式使用次数 |
| avg_installments / max_installments / installment_order_count | DOUBLE/BIGINT | 分期特征 |
| is_installment_user | BIGINT | 是否偏好分期（分期订单占比>30%） |
| avg_review_score | DOUBLE | 平均评分 |
| review_count | BIGINT | 评论数 |
| low_score_rate | DOUBLE | 差评率（≤2 分评论占比） |
| avg_delivery_days | DOUBLE | 平均配送天数（下单→送达） |
| avg_delivery_vs_estimate | DOUBLE | 实际送达与预估的偏差天数（正=迟到） |
| delivery_delay_rate | DOUBLE | 物流延迟率（延迟订单占比） |
| category_diversity | BIGINT | 购买品类数 |
| favorite_category | VARCHAR | 最常购买品类（英语名） |
| customer_state / customer_city | VARCHAR | 用户州 / 城市 |
| is_churned | BIGINT | **流失标签（1=流失，见口径字典）** |
| churn_prob | DOUBLE | **XGBoost 预测的流失概率（0-1，可直接当风险分用）** |

## ab_test_results（AB 实验敏感性分析，18 行）

| 列 | 类型 | 含义 |
|----|------|------|
| Coupon | DOUBLE | 优惠券面额（R$15/25/50） |
| Uplift | DOUBLE | 假设的留存提升率（5%-30%） |
| Saved Users | BIGINT | 挽回用户数 |
| Incremental Revenue | DOUBLE | 增量收入（R$） |
| Total Cost | DOUBLE | 发券总成本（R$） |
| ROI | DOUBLE | 投入产出比 |

**⚠️ 使用注意**：该表是敏感性分析（假设推演），不是真实实验观测数据。回答"发券 ROI"类问题时引用它，但需说明是假设情景。
