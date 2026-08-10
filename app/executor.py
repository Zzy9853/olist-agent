# app/executor.py
"""DuckDB 只读执行器：超时控制 + 结果上限 + 统一错误返回 + 执行审计。"""
import threading
import time
from pathlib import Path

import duckdb
import pandas as pd

from app.config import DB_PATH, SQL_TIMEOUT_SEC, MAX_ROWS, ROOT

AUDIT_LOG = ROOT / "data" / "audit.log"


def _audit(sql: str, ok: bool, rows: int, elapsed_ms: float, error: str = "") -> None:
    """审计记录：时间/状态/行数/耗时/SQL 摘要。审计失败不影响主流程。"""
    try:
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"status={'ok' if ok else 'err'} rows={rows} "
                    f"elapsed={elapsed_ms:.0f}ms sql={sql.strip()[:100]!r}"
                    f"{f' error={error[:60]!r}' if error else ''}\n")
    except OSError:
        pass


def execute_sql(sql: str) -> tuple[bool, pd.DataFrame | str]:
    """只读执行 SQL。返回 (是否成功, DataFrame 或错误信息)。每次执行写审计日志。"""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    t0 = time.perf_counter()
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
        _audit(sql, True, len(df), (time.perf_counter() - t0) * 1000)
        return True, df
    except Exception as e:
        _audit(sql, False, 0, (time.perf_counter() - t0) * 1000, str(e))
        return False, f"执行失败: {e}"
    finally:
        con.close()
