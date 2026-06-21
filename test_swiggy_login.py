import asyncio
from swiggy_auth import create_oauth_provider
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

async def main():
    oauth_provider = create_oauth_provider("https://mcp.swiggy.com/food")

    async with streamablehttp_client(
        "https://mcp.swiggy.com/food", auth=oauth_provider
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("Connected! Available tools:")
            for t in tools.tools:
                print("-", t.name)

if __name__ == "__main__":
    asyncio.run(main())