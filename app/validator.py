# app/validator.py
"""SQL 安全校验：AST 解析 → 只允许 SELECT → 表白名单 → 自动 LIMIT。"""
import sqlglot
from sqlglot import exp

from app.config import ALLOWED_TABLES, MAX_ROWS


def validate_sql(sql: str) -> tuple[bool, str]:
    """校验 SQL。返回 (是否通过, 错误信息或修正后的 SQL)。
    通过时返回修正后的 SQL（自动加 LIMIT 兜底）。
    """
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        return False, "SQL 为空"

    try:
        tree = sqlglot.parse_one(sql, read="duckdb")
    except Exception as e:
        return False, f"SQL 解析失败: {e}"

    # 允许 SELECT 及其集合操作（UNION/INTERSECT/EXCEPT，sqlglot 解析为 SetOperation 子类）
    if not isinstance(tree, (exp.Select, exp.SetOperation)):
        return False, f"只允许 SELECT 语句，收到: {type(tree).__name__}"

    # WITH 定义的 CTE 名是查询内临时表，不属于物理白名单
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}

    # 收集所有物理表名，检查白名单
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if name not in ALLOWED_TABLES and name not in cte_names:
            return False, f"表 {name} 不在白名单中"

    # 自动 LIMIT 兜底（已有 LIMIT 则不动）
    if tree.args.get("limit") is None:
        tree = tree.limit(MAX_ROWS)

    return True, tree.sql(dialect="duckdb")
