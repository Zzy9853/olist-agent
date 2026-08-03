# app/executor.py
"""DuckDB 只读执行器：超时控制 + 结果上限 + 统一错误返回。"""
import threading

import duckdb
import pandas as pd

from app.config import DB_PATH, SQL_TIMEOUT_SEC, MAX_ROWS


def execute_sql(sql: str) -> tuple[bool, pd.DataFrame | str]:
    """只读执行 SQL。返回 (是否成功, DataFrame 或错误信息)。"""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        # DuckDB 1.5.x 无 SET timeout，用 watchdog 线程 interrupt 实现超时
        timer = threading.Timer(SQL_TIMEOUT_SEC, con.interrupt)
        timer.start()
        try:
            df = con.execute(sql).fetchdf()
        finally:
            timer.cancel()
        if len(df) > MAX_ROWS:
            df = df.head(MAX_ROWS)
        return True, df
    except Exception as e:
        return False, f"执行失败: {e}"
    finally:
        con.close()
