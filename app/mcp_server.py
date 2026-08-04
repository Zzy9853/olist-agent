# app/mcp_server.py
"""Olist 智能问数 Agent — MCP Server。
把 Agent 能力标准化为 MCP 工具，任何 MCP 客户端（Claude/Cursor 等）可调用。
运行：python -m app.mcp_server（stdio 传输）
"""
import json

import duckdb
from mcp.server.fastmcp import FastMCP

from app.agent import ask
from app.attribution import explain_user
from app.config import DB_PATH
from app.validator import validate_sql

mcp = FastMCP("olist-agent")


@mcp.tool()
def ask_data(question: str, messages: str | None = None) -> str:
    """自然语言问数 Olist 电商数据。question：中文业务问题；
    messages（可选）：多轮对话历史 JSON 字符串（[{"role":"user"/"assistant","content":"..."}]）。
    返回 JSON：{"answer", "sql", "intent", "attribution"}。
    所有 SQL 自动经过 AST 校验 + 表白名单 + 只读执行，无需调用方关心安全。
    """
    history = json.loads(messages) if messages else None
    r = ask(question, messages=history)
    return json.dumps(r, ensure_ascii=False)


@mcp.tool()
def explain_user(uid: str) -> str:
    """解释指定用户（32 位十六进制 customer_unique_id）的流失风险归因。
    返回 JSON：{"uid", "churn_prob", "features": [{"feature","value","shap"}], "summary"}。
    """
    r = explain_user(uid)
    return json.dumps(r, ensure_ascii=False) if r else json.dumps({"error": "用户不存在"}, ensure_ascii=False)


@mcp.tool()
def list_tables() -> str:
    """列出可查询的数据表清单（表名 + 行数）。用于能力发现。"""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main' ORDER BY table_name").fetchall()
    con.close()
    return json.dumps([r[0] for r in rows], ensure_ascii=False)


@mcp.tool()
def validate_sql(sql: str) -> str:
    """SQL 安全校验（AST 类型 + 表白名单 + LIMIT 兜底）。返回 JSON：{"ok": bool, "message": str}。"""
    ok, msg = validate_sql(sql)
    return json.dumps({"ok": ok, "message": msg}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
