# eval/eval_set.py
"""21 问评测集：5 类问题 + 1 工作流用例，参考 SQL 已人工验证可执行。
EX 判定：生成 SQL 与参考 SQL 执行结果对比（列名归一 + 数值容差 + 行序归一）。
工作流用例（Q21）：结构断言（四步报告），不走 SQL 对比。
"""
from app.executor import execute_sql

CASES = [
    # ---- 1. 单表简单查询 ----
    {"id": "Q01", "q": "整体用户流失率是多少？",
     "ref": "SELECT ROUND(AVG(is_churned),4) AS churn_rate FROM user_wide"},
    {"id": "Q02", "q": "一共有多少用户？",
     "ref": "SELECT COUNT(*) AS total_users FROM user_wide"},
    {"id": "Q03", "q": "流失用户有多少人？",
     "ref": "SELECT COUNT(*) AS churned FROM user_wide WHERE is_churned = 1"},
    {"id": "Q04", "q": "用户的平均订单金额是多少？",
     "ref": "SELECT AVG(avg_order_value) AS avg_aov FROM user_wide"},
    # ---- 2. 多表 JOIN ----
    {"id": "Q05", "q": "哪些州的用户流失率最高？列出前10。",
     "ref": "SELECT customer_state, COUNT(*) AS users, ROUND(AVG(is_churned),4) AS churn_rate FROM user_wide GROUP BY customer_state ORDER BY churn_rate DESC LIMIT 10"},
    {"id": "Q06", "q": "物流延迟率最高的5个品类是哪些？",
     "ref": "SELECT pt.product_category_name_english AS category, COUNT(*) AS orders, ROUND(AVG(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN 1 ELSE 0 END),4) AS delay_rate FROM orders o JOIN order_items oi ON o.order_id = oi.order_id JOIN products p ON oi.product_id = p.product_id LEFT JOIN product_category_translation pt ON p.product_category_name = pt.product_category_name WHERE o.order_status NOT IN ('canceled','unavailable') AND o.order_delivered_customer_date IS NOT NULL GROUP BY pt.product_category_name_english ORDER BY delay_rate DESC LIMIT 5"},
    {"id": "Q07", "q": "各品类的复购率是多少？列出复购率最高的10个品类。",
     "ref": "SELECT favorite_category AS category, COUNT(*) AS users, ROUND(AVG(is_repeat_buyer),4) AS repeat_rate FROM user_wide WHERE favorite_category IS NOT NULL GROUP BY favorite_category ORDER BY repeat_rate DESC LIMIT 10"},
    {"id": "Q08", "q": "哪个州的用户最集中（用户数最多）？",
     "ref": "SELECT customer_state, COUNT(*) AS users FROM user_wide GROUP BY customer_state ORDER BY users DESC LIMIT 1"},
    # ---- 3. 口径敏感 ----
    {"id": "Q09", "q": "用户的差评率整体是多少？",
     "ref": "SELECT ROUND(AVG(low_score_rate),4) AS avg_low_score_rate FROM user_wide"},
    {"id": "Q10", "q": "物流延迟率超过30%的用户占比多少？",
     "ref": "SELECT ROUND(COUNT(*) * 1.0 / (SELECT COUNT(*) FROM user_wide),4) AS pct FROM user_wide WHERE delivery_delay_rate > 0.3"},
    {"id": "Q11", "q": "可挽救用户（流失概率0.55到0.85之间且消费不少于90）有多少人？",
     "ref": "SELECT COUNT(*) AS savable FROM user_wide WHERE churn_prob BETWEEN 0.55 AND 0.85 AND total_revenue >= 90"},
    {"id": "Q12", "q": "R$15 优惠券在 10% 留存提升率下的 ROI 是多少？",
     "ref": "SELECT ROI FROM ab_test_results WHERE Coupon = 15 AND ROUND(Uplift,2) = 0.1"},
    # ---- 4. 预测/风险类 ----
    {"id": "Q13", "q": "流失概率高于80%的用户有多少？",
     "ref": "SELECT COUNT(*) AS high_risk FROM user_wide WHERE churn_prob > 0.8"},
    {"id": "Q14", "q": "流失概率高于80%的用户平均消费是多少？",
     "ref": "SELECT AVG(total_revenue) AS avg_rev FROM user_wide WHERE churn_prob > 0.8"},
    {"id": "Q15", "q": "高流失风险且高价值的用户（概率>0.8 且消费>=90）有多少？",
     "ref": "SELECT COUNT(*) AS cnt FROM user_wide WHERE churn_prob > 0.8 AND total_revenue >= 90"},
    {"id": "Q16", "q": "用户整体的平均流失概率是多少？",
     "ref": "SELECT ROUND(AVG(churn_prob),4) AS avg_prob FROM user_wide"},
    # ---- 5. 聚合与排序 ----
    {"id": "Q17", "q": "2018年各月的订单量趋势如何？",
     "ref": "SELECT DATE_TRUNC('month', order_purchase_timestamp) AS month, COUNT(DISTINCT order_id) AS orders FROM valid_orders WHERE order_purchase_timestamp >= DATE '2018-01-01' GROUP BY 1 ORDER BY 1"},
    {"id": "Q18", "q": "不同支付方式的订单量分布？",
     "ref": "SELECT payment_type, COUNT(DISTINCT order_id) AS cnt FROM order_payments WHERE order_id IN (SELECT order_id FROM valid_orders) GROUP BY payment_type ORDER BY cnt DESC"},
    {"id": "Q19", "q": "平均配送时长超过15天的用户占比多少？",
     "ref": "SELECT ROUND(COUNT(*) * 1.0 / (SELECT COUNT(*) FROM user_wide),4) AS pct FROM user_wide WHERE avg_delivery_days > 15"},
    {"id": "Q20", "q": "各州流失用户的平均消费，列出前5（口径陷阱题：问的是流失用户的消费，不是全部用户）",
     "ref": "SELECT customer_state, AVG(total_revenue) AS avg_rev FROM user_wide WHERE is_churned = 1 GROUP BY customer_state ORDER BY avg_rev DESC LIMIT 5"},
    # ---- 6. 工作流用例（结构断言） ----
    {"id": "Q21", "q": "运行流失诊断",
     "ref": "",  # workflow 用例：结构断言，不走 SQL 对比
     "wf": True},
    # ---- 7. 模型解释用例（结构断言，不走 SQL） ----
    {"id": "Q22", "q": "哪些特征对流失预测最重要？",
     "ref": "",  # 模型解释用例：结构断言（intent=explain + attribution）
     "att": True},
]
