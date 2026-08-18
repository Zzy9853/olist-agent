-- ============================================================
-- Olist 用户流失预测分析宽表
-- 从9张表构建用户级特征（基于 customer_unique_id），
-- 含 RFM、支付行为、评论情感、物流体验、品类偏好五大维度
-- ============================================================

WITH
-- 1. 有效订单（排除取消/不可用，关联真实用户ID）
valid_orders AS (
    SELECT
        o.*,
        c.customer_unique_id
    FROM orders o
    JOIN customers c ON o.customer_id = c.customer_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
),

-- 2. 全局时间基准：数据集中最后一天
time_baseline AS (
    SELECT MAX(order_purchase_timestamp::TIMESTAMP) AS latest_date
    FROM valid_orders
),

-- 3. 用户级 RFM 与订单行为特征
user_rfm AS (
    SELECT
        customer_unique_id,
        COUNT(DISTINCT order_id)                            AS order_count,
        COUNT(DISTINCT DATE_TRUNC('month',
            order_purchase_timestamp::TIMESTAMP))            AS active_months,
        SUM(CAST(total_order_value AS DOUBLE))               AS total_revenue,
        AVG(CAST(total_order_value AS DOUBLE))               AS avg_order_value,
        SUM(CAST(total_freight AS DOUBLE))                   AS total_freight,
        COUNT(DISTINCT product_id)                           AS distinct_products,
        COUNT(DISTINCT seller_id)                            AS distinct_sellers,
        MIN(order_purchase_timestamp::TIMESTAMP)             AS first_order_date,
        MAX(order_purchase_timestamp::TIMESTAMP)             AS last_order_date,
        -- 订单间隔（仅对2单以上用户有意义）
        DATEDIFF('day',
            MIN(order_purchase_timestamp::TIMESTAMP),
            MAX(order_purchase_timestamp::TIMESTAMP))
        * 1.0 / NULLIF(COUNT(DISTINCT order_id) - 1, 0)     AS avg_days_between_orders,
        -- 是否复购用户
        CASE WHEN COUNT(DISTINCT order_id) > 1 THEN 1 ELSE 0 END AS is_repeat_buyer
    FROM (
        SELECT
            vo.customer_unique_id,
            vo.order_id,
            vo.order_purchase_timestamp,
            oi.product_id,
            oi.seller_id,
            SUM(CAST(oi.price AS DOUBLE)) AS total_order_value,
            SUM(CAST(oi.freight_value AS DOUBLE)) AS total_freight
        FROM valid_orders vo
        JOIN order_items oi ON vo.order_id = oi.order_id
        GROUP BY vo.customer_unique_id, vo.order_id, vo.order_purchase_timestamp,
                 oi.product_id, oi.seller_id
    ) order_level
    GROUP BY customer_unique_id
),

-- 4. 支付行为特征
user_payments AS (
    SELECT
        vo.customer_unique_id,
        COUNT(DISTINCT op.payment_type)                         AS payment_types_count,
        SUM(CASE WHEN op.payment_type = 'credit_card' THEN 1 ELSE 0 END) AS credit_card_usage,
        SUM(CASE WHEN op.payment_type = 'boleto'      THEN 1 ELSE 0 END) AS boleto_usage,
        SUM(CASE WHEN op.payment_type = 'debit_card'  THEN 1 ELSE 0 END) AS debit_card_usage,
        SUM(CASE WHEN op.payment_type = 'voucher'     THEN 1 ELSE 0 END) AS voucher_usage,
        AVG(CAST(op.payment_installments AS INT))               AS avg_installments,
        MAX(CAST(op.payment_installments AS INT))               AS max_installments,
        SUM(CASE WHEN CAST(op.payment_installments AS INT) > 1 THEN 1 ELSE 0 END)
                                                               AS installment_order_count,
        -- 是否偏好分期
        CASE WHEN SUM(CASE WHEN CAST(op.payment_installments AS INT) > 1 THEN 1 ELSE 0 END)
                  * 1.0 / NULLIF(COUNT(*), 0) > 0.3 THEN 1 ELSE 0 END AS is_installment_user
    FROM valid_orders vo
    JOIN order_payments op ON vo.order_id = op.order_id
    GROUP BY vo.customer_unique_id
),

-- 5. 评论特征
user_reviews AS (
    SELECT
        vo.customer_unique_id,
        AVG(CAST(orv.review_score AS DOUBLE))                   AS avg_review_score,
        COUNT(DISTINCT orv.review_id)                           AS review_count,
        SUM(CASE WHEN CAST(orv.review_score AS INT) <= 2 THEN 1 ELSE 0 END)
        * 1.0 / NULLIF(COUNT(DISTINCT orv.review_id), 0)        AS low_score_rate,
        DATEDIFF('day',
            MIN(orv.review_creation_date::TIMESTAMP),
            MAX(orv.review_creation_date::TIMESTAMP))           AS review_span_days
    FROM valid_orders vo
    JOIN order_reviews orv ON vo.order_id = orv.order_id
    GROUP BY vo.customer_unique_id
),

-- 6. 物流体验特征
user_delivery AS (
    SELECT
        customer_unique_id,
        AVG(DATEDIFF('day',
            order_purchase_timestamp::TIMESTAMP,
            order_delivered_customer_date::TIMESTAMP))          AS avg_delivery_days,
        AVG(DATEDIFF('day',
            order_estimated_delivery_date::TIMESTAMP,
            order_delivered_customer_date::TIMESTAMP))          AS avg_delivery_vs_estimate,
        -- 物流延迟率
        SUM(CASE
            WHEN order_delivered_customer_date::TIMESTAMP
               > order_estimated_delivery_date::TIMESTAMP
            THEN 1 ELSE 0 END
        ) * 1.0 / NULLIF(COUNT(*), 0)                         AS delivery_delay_rate
    FROM valid_orders
    WHERE order_delivered_customer_date IS NOT NULL
    GROUP BY customer_unique_id
),

-- 7. 品类偏好特征
user_categories AS (
    SELECT
        vo.customer_unique_id,
        COUNT(DISTINCT pt.product_category_name_english)        AS category_diversity,
        COUNT(DISTINCT CASE WHEN pt.product_category_name_english IS NOT NULL
              THEN pt.product_category_name_english END)        AS distinct_categories,
        -- 最常购买品类（用 MODE）
        (SELECT pt2.product_category_name_english
         FROM valid_orders vo2
         JOIN order_items oi2 ON vo2.order_id = oi2.order_id
         JOIN products p2 ON oi2.product_id = p2.product_id
         LEFT JOIN product_category_translation pt2
             ON p2.product_category_name = pt2.product_category_name
         WHERE vo2.customer_unique_id = vo.customer_unique_id
           AND pt2.product_category_name_english IS NOT NULL
         GROUP BY pt2.product_category_name_english
         ORDER BY COUNT(*) DESC
         LIMIT 1)                                              AS favorite_category
    FROM valid_orders vo
    JOIN order_items oi ON vo.order_id = oi.order_id
    JOIN products p ON oi.product_id = p.product_id
    LEFT JOIN product_category_translation pt
        ON p.product_category_name = pt.product_category_name
    GROUP BY vo.customer_unique_id
)

-- 8. 合并生成最终宽表
SELECT
    rf.customer_unique_id,
    -- === RFM 特征 ===
    rf.order_count,
    rf.active_months,
    COALESCE(rf.total_revenue, 0)                AS total_revenue,
    COALESCE(rf.avg_order_value, 0)              AS avg_order_value,
    COALESCE(rf.total_freight, 0)                AS total_freight,
    rf.distinct_products,
    rf.distinct_sellers,
    rf.avg_days_between_orders,
    rf.is_repeat_buyer,
    -- Recency
    DATEDIFF('day', rf.last_order_date, tb.latest_date) AS recency_days,
    -- === 支付特征 ===
    COALESCE(up.payment_types_count, 0)          AS payment_types_count,
    COALESCE(up.credit_card_usage, 0)            AS credit_card_usage,
    COALESCE(up.boleto_usage, 0)                 AS boleto_usage,
    COALESCE(up.debit_card_usage, 0)             AS debit_card_usage,
    COALESCE(up.voucher_usage, 0)                AS voucher_usage,
    COALESCE(up.avg_installments, 0)             AS avg_installments,
    COALESCE(up.max_installments, 0)             AS max_installments,
    COALESCE(up.installment_order_count, 0)      AS installment_order_count,
    COALESCE(up.is_installment_user, 0)          AS is_installment_user,
    -- === 评论特征 ===
    COALESCE(ur.avg_review_score, 0)             AS avg_review_score,
    COALESCE(ur.review_count, 0)                 AS review_count,
    COALESCE(ur.low_score_rate, 0)               AS low_score_rate,
    -- === 物流特征 ===
    COALESCE(ud.avg_delivery_days, 0)            AS avg_delivery_days,
    COALESCE(ud.avg_delivery_vs_estimate, 0)     AS avg_delivery_vs_estimate,
    COALESCE(ud.delivery_delay_rate, 0)          AS delivery_delay_rate,
    -- === 品类特征 ===
    COALESCE(uc.category_diversity, 0)           AS category_diversity,
    uc.favorite_category,
    -- === 地域特征 ===
    cust.customer_state,
    cust.customer_city,
    -- === 目标变量：流失标签 (90天阈值) ===
    CASE
        WHEN DATEDIFF('day', rf.last_order_date, tb.latest_date) > 90
        THEN 1
        ELSE 0
    END                                           AS is_churned
FROM user_rfm rf
CROSS JOIN time_baseline tb
JOIN (
    SELECT DISTINCT customer_unique_id, customer_state, customer_city
    FROM customers
) cust ON rf.customer_unique_id = cust.customer_unique_id
LEFT JOIN user_payments up ON rf.customer_unique_id = up.customer_unique_id
LEFT JOIN user_reviews ur ON rf.customer_unique_id = ur.customer_unique_id
LEFT JOIN user_delivery ud ON rf.customer_unique_id = ud.customer_unique_id
LEFT JOIN user_categories uc ON rf.customer_unique_id = uc.customer_unique_id;
