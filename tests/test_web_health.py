"""Unit tests for the Render HTTP health-check web server."""

import pytest
from aiohttp.test_utils import TestServer, TestClient
import aiohttp

from clubhub.web_health import create_health_app, start_web_server, stop_web_server


@pytest.mark.asyncio
async def test_health_routes():
    """Verify that both GET / and GET /health respond with 200 OK."""
    app = create_health_app()
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        # 1. Root route GET /
        resp_root = await client.get("/")
        assert resp_root.status == 200
        text_root = await resp_root.text()
        assert "Bot is alive" in text_root

        # 2. Health check route GET /health
        resp_health = await client.get("/health")
        assert resp_health.status == 200
        text_health = await resp_health.text()
        assert "Bot is alive" in text_health

        # 3. Nonexistent route
        resp_404 = await client.get("/invalid_path")
        assert resp_404.status == 404
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_start_and_stop_web_server():
    """Verify live web server lifecycle on a specific port."""
    test_port = 10099
    runner = await start_web_server(host="127.0.0.1", port=test_port)
    assert runner is not None

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{test_port}/health") as resp:
                assert resp.status == 200
                text = await resp.text()
                assert "Bot is alive" in text
            async with session.get(f"http://127.0.0.1:{test_port}/") as resp:
                assert resp.status == 200
                text = await resp.text()
                assert "Bot is alive" in text
    finally:
        await stop_web_server(runner)
