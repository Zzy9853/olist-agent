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


if __name__ == "__main__":
    asyncio.run(main())
