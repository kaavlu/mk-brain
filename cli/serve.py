import asyncio

from brain.mcp_server.server import run


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
