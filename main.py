import asyncio

import bot
import web_server


async def main():
    await asyncio.gather(
        web_server.run_web_server(),
        bot.run(),
    )


if __name__ == "__main__":
    asyncio.run(main())
