"""Lightweight non-blocking aiohttp health check web server for Render/cloud deployments."""

from __future__ import annotations

import logging
import os
from typing import Optional
from aiohttp import web

logger = logging.getLogger("clubhub.web")


async def root_handler(request: web.Request) -> web.Response:
    """Respond 200 OK to root keep-alive probes."""
    return web.Response(text="Bot is alive", content_type="text/plain", status=200)


async def health_handler(request: web.Request) -> web.Response:
    """Respond 200 OK to health check probes."""
    return web.Response(text="Bot is alive", content_type="text/plain", status=200)


def create_health_app() -> web.Application:
    """Build the aiohttp web application with root and health routes."""
    app = web.Application()
    app.router.add_get("/", root_handler)
    app.router.add_get("/health", health_handler)
    return app


async def start_web_server(
    host: str = "0.0.0.0", port: Optional[int] = None
) -> web.AppRunner:
    """Start the non-blocking HTTP health check server.

    Listens on 0.0.0.0 and PORT from environment (defaults to 10000 for Render).
    """
    if port is None:
        port = int(os.environ.get("PORT", 10000))

    app = create_health_app()
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    logger.info(f"Health-check HTTP server listening on http://{host}:{port}/ and http://{host}:{port}/health")
    return runner


async def stop_web_server(runner: Optional[web.AppRunner]) -> None:
    """Gracefully cleanup and shut down the HTTP server."""
    if runner is not None:
        try:
            await runner.cleanup()
            logger.info("Health-check HTTP server stopped.")
        except Exception as e:
            logger.warning(f"Error stopping health-check server: {e}")
