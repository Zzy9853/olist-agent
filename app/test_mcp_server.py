# app/test_mcp_server.py
"""MCP Server 集成测试：4 工具注册 + 真实调用（需真实 API Key）。"""
import asyncio
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(command="python", args=["-m", "app.mcp_server"], cwd=".")
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. 工具注册完整性
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print("注册工具:", names)
            assert {"ask_data", "explain_user", "list_tables", "validate_sql"} <= set(names), "工具缺失"

            # 2. list_tables：能力发现
            r1 = await session.call_tool("list_tables", {})
            tables = json.loads(r1.content[0].text)
            assert "user_wide" in tables and "orders" in tables, f"表清单异常: {tables}"
            print("list_tables:", tables)

            # 3. ask_data：NL2SQL 全链路（真实 API）
            r2 = await session.call_tool("ask_data", {"question": "整体用户流失率是多少？"})
            out = json.loads(r2.content[0].text)
            assert out["sql"] and "流失" in out["answer"], f"ask_data 异常: {out}"
            print("ask_data answer:", out["answer"][:60])

            # 4. explain_user：SHAP 归因（真实模型）
            r3 = await session.call_tool("explain_user", {"uid": "97981245c3257ea9b14befffd560177b"})
            att = json.loads(r3.content[0].text)
            assert att["churn_prob"] > 0 and len(att["features"]) == 3, f"explain_user 异常: {att}"
            print("explain_user:", att["summary"][:60])

            # 5. validate_sql：安全校验（拦截 DROP）
            r4 = await session.call_tool("validate_sql", {"sql": "DROP TABLE orders"})
            v = json.loads(r4.content[0].text)
            assert v["ok"] is False, "DROP 应被拦截"
            print("validate_sql 拦截 DROP:", v)

            print("\n✅ MCP 集成测试 4/4 工具全部通过")


if __name__ == "__main__":
    asyncio.run(main())
