# app/test_mcp_server.py
"""MCP Server 冒烟：进程启动 + 工具注册清单（用 mcp.client 连接验证）。"""
import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(command="python", args=["-m", "app.mcp_server"], cwd=".")
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print("注册工具:", names)
            assert {"ask_data", "explain_user", "list_tables", "validate_sql"} <= set(names), "工具缺失"
            print("✅ 工具注册完整")

            # 调用级验证：validate_sql（防名字遮蔽回归）
            r4 = await session.call_tool("validate_sql", {"sql": "DROP TABLE orders"})
            import json as _json
            v = _json.loads(r4.content[0].text)
            assert v["ok"] is False, "DROP 应被拦截"
            print("validate_sql 拦截 DROP:", v)

            # 调用级验证：explain_user（防名字遮蔽回归）
            r5 = await session.call_tool("explain_user", {"uid": "97981245c3257ea9b14befffd560177b"})
            att = _json.loads(r5.content[0].text)
            assert att["churn_prob"] > 0, f"explain_user 异常: {att}"
            print("explain_user OK:", att["summary"][:50])


if __name__ == "__main__":
    asyncio.run(main())
