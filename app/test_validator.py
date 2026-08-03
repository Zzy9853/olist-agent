# app/test_validator.py
"""SQL 校验器自检：合法通过、危险拦截、白名单拦截。"""
from app.validator import validate_sql

CASES = [
    # (SQL, 期望通过)
    ("SELECT AVG(is_churned) FROM user_wide", True),
    ("SELECT customer_state, COUNT(*) FROM user_wide GROUP BY 1 ORDER BY 2 DESC", True),
    ("SELECT * FROM user_wide LIMIT 5", True),
    ("SELECT * FROM valid_orders LIMIT 3", True),
    ("SELECT customer_state FROM user_wide WHERE is_churned = 1 UNION SELECT customer_state FROM user_wide WHERE is_churned = 0", True),
    ("WITH t AS (SELECT * FROM orders) SELECT COUNT(*) FROM t", True),
    ("DROP TABLE orders", False),
    ("DELETE FROM orders", False),
    ("INSERT INTO orders VALUES (1)", False),
    ("CREATE TABLE x AS SELECT 1", False),
    ("SELECT * FROM secret_table", False),
    ("SELECT * FROM orders; DROP TABLE orders", False),  # 多语句应解析失败或拦截
    ("UPDATE user_wide SET is_churned=0", False),
    ("", False),
]


def run():
    passed = 0
    for sql, expect in CASES:
        ok, msg = validate_sql(sql)
        verdict = (ok == expect)
        passed += verdict
        print(f"{'OK ' if verdict else 'FAIL'} {sql[:50]:<52} -> {ok} (expect {expect})")
    print(f"\n{passed}/{len(CASES)} 通过")
    assert passed == len(CASES), "存在失败用例"
    # LIMIT 兜底验证
    ok, out = validate_sql("SELECT * FROM user_wide")
    assert ok and "LIMIT" in out.upper(), "缺少 LIMIT 兜底"
    print("LIMIT 兜底生效:", out)


if __name__ == "__main__":
    run()
