from aiohttp import web

from config import PORT


async def handle_ping(request):
    return web.Response(text="OK, бот жив")


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)
    return app


async def run_web_server():
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    # держим таск живым вечно, сам сервер работает в фоне aiohttp
    import asyncio
    while True:
        await asyncio.sleep(3600)
