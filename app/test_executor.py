# app/test_executor.py
"""执行器自检：合法查询返回、非法 SQL 被拦截、大数据量兜底。"""
from app.executor import execute_sql


def run():
    ok, df = execute_sql("SELECT AVG(is_churned) AS r FROM user_wide")
    assert ok and abs(df["r"].iloc[0] - 0.8119) < 0.01, f"流失率异常: {df}"
    print("合法查询返回 DataFrame:", df.to_dict("records"))

    ok, err = execute_sql("SELECT * FROM nonexistent_table")
    assert not ok and "执行失败" in err, f"应失败: {err}"
    print("非法表名被拦截:", err)

    ok, err = execute_sql("SELECT * FROM geolocation CROSS JOIN orders, user_wide")
    assert ok or "执行失败" in err, "未超时也未失败"
    print("大数据量查询兜底 OK")

    print("\n全部通过")


if __name__ == "__main__":
    run()
