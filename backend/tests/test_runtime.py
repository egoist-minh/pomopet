import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.runtime_config import get_data_dir
from run_backend import require_loopback


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_token_is_required_when_configured(self):
        transport = ASGITransport(app=app)
        with patch.dict(os.environ, {"POMOPET_RUNTIME_TOKEN": "runtime-secret"}):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                unauthorized = await client.get("/health")
                authorized = await client.get(
                    "/health",
                    headers={"X-PomoPet-Token": "runtime-secret"},
                )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(authorized.status_code, 200)
        self.assertEqual(authorized.json(), {"status": "ok"})

    async def test_invalid_runtime_token_is_rejected(self):
        transport = ASGITransport(app=app)
        with patch.dict(os.environ, {"POMOPET_RUNTIME_TOKEN": "runtime-secret"}):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    "/api/tasks/",
                    headers={"X-PomoPet-Token": "wrong"},
                )
        self.assertEqual(response.status_code, 401)

    async def test_cors_preflight_allows_patch_for_planning_updates(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.options(
                "/api/planning/plan-items/item-1",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "PATCH",
                    "Access-Control-Request-Headers": "content-type,x-pomopet-token",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("PATCH", response.headers["access-control-allow-methods"])

    def test_data_directory_supports_spaces(self):
        with tempfile.TemporaryDirectory(prefix="PomoPet Runtime ") as directory:
            with patch.dict(os.environ, {"POMOPET_DATA_DIR": directory}):
                self.assertEqual(get_data_dir(), Path(directory).resolve())

    def test_backend_rejects_non_loopback_bind(self):
        with self.assertRaises(ValueError):
            require_loopback("0.0.0.0")
        require_loopback("127.0.0.1")


if __name__ == "__main__":
    unittest.main()
