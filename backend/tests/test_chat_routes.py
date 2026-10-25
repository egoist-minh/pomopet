import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.responses import JSONResponse

from app.api.routes.chat import ActionResolution, ChatMessage, _resolve_action, send_message
from app.services.ai_service import ProviderPermissionError, ProviderRateLimitError
from app.services.agent_memory import agent_memory
from app.services.rate_limiter import RateLimitExceeded


class ChatRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_rate_limit_returns_429_with_retry_after(self):
        with patch("app.api.routes.chat._agent_mode_enabled", return_value=False), patch(
            "app.api.routes.chat.chat_rate_limiter.consume",
            side_effect=RateLimitExceeded(42),
        ):
            response = await send_message(
                ChatMessage(
                    message="Hello",
                    provider="gemini",
                    thread_id="thread-rate-limit",
                    timezone_offset=420,
                ),
                MagicMock(),
            )

        body = json.loads(response.body)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["retry-after"], "42")
        self.assertEqual(body["error_code"], "RATE_LIMITED")

    async def test_feature_flag_falls_back_to_single_turn_chat(self):
        fake_agent = MagicMock()
        fake_agent.chat = AsyncMock(
            return_value={"status": "completed", "message": "Fallback reply"}
        )
        with patch("app.api.routes.chat._agent_mode_enabled", return_value=False), patch(
            "app.api.routes.chat.PomoAgent",
            return_value=fake_agent,
        ) as agent_class:
            response = await send_message(
                ChatMessage(
                    message="Hello",
                    provider="gemini",
                    thread_id="thread-fallback",
                    timezone_offset=420,
                ),
                MagicMock(),
            )

        agent_class.assert_called_once_with("gemini")
        self.assertEqual(response["status"], "completed")
        self.assertEqual(response["message"], "Fallback reply")
        self.assertIn("request_id", response)

    async def test_chat_response_has_status_request_id_and_minimal_action(self):
        fake_agent = MagicMock()
        fake_agent.chat = AsyncMock(
            return_value={
                "status": "confirmation_required",
                "message": "Create task “Release”",
                "action": {
                    "id": "action-1",
                    "type": "create_task",
                    "preview": "Create task “Release”",
                    "expires_at": "2026-10-18T16:00:00+00:00",
                },
            }
        )
        with patch.object(
            agent_memory,
            "get_pending_action_for_thread",
            AsyncMock(return_value=None),
        ), patch("app.api.routes.chat._agent", return_value=fake_agent):
            response = await send_message(
                ChatMessage(
                    message="Create Release",
                    provider="openai",
                    thread_id="thread-contract",
                    timezone_offset=420,
                ),
                MagicMock(),
            )

        self.assertEqual(response["status"], "confirmation_required")
        self.assertEqual(response["pending_action_id"], "action-1")
        self.assertIn("request_id", response)
        self.assertNotIn("arguments", response["action"])

    async def test_provider_permission_error_is_reported_as_forbidden(self):
        fake_agent = MagicMock()
        fake_agent.chat = AsyncMock(
            side_effect=ProviderPermissionError(
                "Gemini access was denied. Check the API key and its project permissions."
            )
        )
        with patch.object(
            agent_memory,
            "get_pending_action_for_thread",
            AsyncMock(return_value=None),
        ), patch("app.api.routes.chat._agent", return_value=fake_agent):
            response = await send_message(
                ChatMessage(
                    message="Hello",
                    provider="gemini",
                    thread_id="thread-permission",
                    timezone_offset=420,
                ),
                MagicMock(),
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            json.loads(response.body)["error_code"],
            "PROVIDER_PERMISSION_DENIED",
        )

    async def test_provider_rate_limit_error_is_reported_as_429(self):
        fake_agent = MagicMock()
        fake_agent.chat = AsyncMock(
            side_effect=ProviderRateLimitError(
                "Gemini quota or rate limit was reached. Try again later."
            )
        )
        with patch.object(
            agent_memory,
            "get_pending_action_for_thread",
            AsyncMock(return_value=None),
        ), patch("app.api.routes.chat._agent", return_value=fake_agent):
            response = await send_message(
                ChatMessage(
                    message="Hello",
                    provider="gemini",
                    thread_id="thread-provider-rate",
                    timezone_offset=420,
                ),
                MagicMock(),
            )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(
            json.loads(response.body)["error_code"],
            "PROVIDER_RATE_LIMITED",
        )

    async def test_action_from_another_thread_is_rejected(self):
        record = {
            "id": "action-1",
            "thread_id": "thread-owner",
            "provider": "openai",
            "status": "pending",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        }
        with patch.object(agent_memory, "get_action", AsyncMock(return_value=record)):
            response = await _resolve_action(
                "action-1",
                "confirm",
                ActionResolution(thread_id="thread-other"),
                MagicMock(),
            )

        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(json.loads(response.body)["error_code"], "ACTION_CONFLICT")

    async def test_expired_action_is_cancelled_without_executing_write(self):
        record = {
            "id": "action-expired",
            "thread_id": "thread-expired",
            "provider": "openai",
            "status": "pending",
            "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        }
        fake_agent = MagicMock()
        fake_agent.resolve_action = AsyncMock(
            return_value={"status": "cancelled", "message": "Cancelled"}
        )
        with patch.object(
            agent_memory,
            "get_action",
            AsyncMock(return_value=record),
        ), patch.object(
            agent_memory,
            "set_action_status",
            AsyncMock(return_value=True),
        ) as set_status, patch("app.api.routes.chat._agent", return_value=fake_agent):
            response = await _resolve_action(
                "action-expired",
                "confirm",
                ActionResolution(thread_id="thread-expired"),
                MagicMock(),
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(json.loads(response.body)["error_code"], "ACTION_EXPIRED")
        set_status.assert_awaited_once_with("action-expired", "expired")
        fake_agent.resolve_action.assert_awaited_once()
        self.assertEqual(fake_agent.resolve_action.await_args.args[1], "cancel")


if __name__ == "__main__":
    unittest.main()
