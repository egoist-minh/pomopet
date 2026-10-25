import os
import inspect
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from app.services.ai_service import (
    ModelFactory,
    ProviderError,
    ProviderPermissionError,
    ProviderRateLimitError,
)
from app.services.pomo_agent import ModelTimeoutError, PomoAgent
from app.services.agent_memory import agent_memory
from app.services.productivity_actions import (
    ActionConflictError,
    ActionExecutionError,
    ActionTimeoutError,
    InvalidActionError,
)
from app.services.productivity_tools import ProductivityToolError, ProductivityToolTimeoutError
from app.services.rate_limiter import RateLimitExceeded, chat_rate_limiter
from app.services.memory_extractor import process_user_memory
from app.services.relationship_extractor import process_relationship_memory
from app.database.database import get_db
from app.utils.logger import app_logger
from pydantic import BaseModel, Field, SecretStr, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

class ChatMessage(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    provider: Literal["openai", "gemini"] = "openai"
    thread_id: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    timezone_offset: int = Field(ge=-720, le=840)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message must not be blank")
        return value


class ProviderKey(BaseModel):
    api_key: SecretStr = Field(min_length=8, max_length=500)


class ActionResolution(BaseModel):
    thread_id: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )


def _agent_mode_enabled() -> bool:
    return os.getenv("AGENT_MODE", "true").strip().lower() in {"1", "true", "yes", "on"}


def _error_response(
    status_code: int,
    message: str,
    error_code: str,
    request_id: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    app_logger.warning(
        "chat_error request_id=%s error_code=%s status=%s",
        request_id,
        error_code,
        status_code,
    )
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "error",
            "message": message,
            "error_code": error_code,
            "request_id": request_id,
        },
        headers=headers,
    )


def _apply_chat_rate_limit(provider: str, thread_id: str, request_id: str) -> JSONResponse | None:
    try:
        chat_rate_limiter.consume(f"{provider}:{thread_id}")
    except RateLimitExceeded as error:
        return _error_response(
            429,
            f"Too many chat requests. Try again in {error.retry_after_seconds} seconds.",
            "RATE_LIMITED",
            request_id,
            headers={"Retry-After": str(error.retry_after_seconds)},
        )
    return None


def _is_expired(expires_at: str) -> bool:
    return datetime.fromisoformat(expires_at) <= datetime.now(timezone.utc)


def _agent(provider: str, db: AsyncSession) -> PomoAgent:
    return PomoAgent(
        provider,
        database=db,
        checkpointer=agent_memory.checkpointer,
        action_store=agent_memory,
    )


async def _process_memory_safely(
    db: AsyncSession,
    message: str,
    request_id: str,
) -> str | None:
    notices: list[str] = []
    for phase, processor in (
        ("explicit", process_user_memory),
        ("relationship", process_relationship_memory),
    ):
        try:
            result = await processor(db, message, request_id)
            notice = result.prompt_notice()
            if notice:
                notices.append(notice)
        except Exception as error:
            # Each personalization layer is optional and isolated. Never log
            # the message, candidate value, episode summary, or provider text.
            rollback_result = db.rollback()
            if inspect.isawaitable(rollback_result):
                await rollback_result
            app_logger.warning(
                "memory_processing_failed request_id=%s phase=%s type=%s",
                request_id,
                phase,
                type(error).__name__,
            )
    return "; ".join(notices) if notices else None


@router.get("/providers")
async def get_providers():
    return JSONResponse(
        content=ModelFactory.configured_providers(),
        headers={"Cache-Control": "no-store"},
    )


@router.put("/providers/{provider}/key")
async def configure_provider_key(
    provider: Literal["openai", "gemini"],
    data: ProviderKey,
):
    ModelFactory.configure_api_key(provider, data.api_key.get_secret_value())
    return JSONResponse(
        content={"provider": provider, "configured": True},
        headers={"Cache-Control": "no-store"},
    )

@router.post("/")
async def send_message(data: ChatMessage, db: AsyncSession = Depends(get_db)):
    request_id = str(uuid4())
    try:
        if not _agent_mode_enabled():
            rate_limit_response = _apply_chat_rate_limit(data.provider, data.thread_id, request_id)
            if rate_limit_response is not None:
                return rate_limit_response
            memory_notice = await _process_memory_safely(db, data.message, request_id)
            result = await PomoAgent(data.provider).chat(
                data.message,
                timezone_offset=data.timezone_offset,
                request_id=request_id,
                memory_notice=memory_notice,
            )
            return {**result, "request_id": request_id}

        pending = await agent_memory.get_pending_action_for_thread(data.thread_id)
        if pending is not None and not _is_expired(pending["expires_at"]):
            return _error_response(
                409,
                "Resolve the pending action before sending another message.",
                "ACTION_PENDING",
                request_id,
            )
        if pending is not None:
            if await agent_memory.set_action_status(pending["id"], "expired"):
                try:
                    await _agent(pending["provider"], db).resolve_action(
                        pending["id"], "cancel", data.thread_id, request_id
                    )
                except Exception:
                    app_logger.warning(
                        "agent_event request_id=%s node=expire_cleanup outcome=error",
                        request_id,
                    )

        rate_limit_response = _apply_chat_rate_limit(data.provider, data.thread_id, request_id)
        if rate_limit_response is not None:
            return rate_limit_response
        memory_notice = await _process_memory_safely(db, data.message, request_id)
        result = await _agent(data.provider, db).chat(
            data.message,
            thread_id=data.thread_id,
            timezone_offset=data.timezone_offset,
            request_id=request_id,
            memory_notice=memory_notice,
        )
        if result["status"] == "confirmation_required":
            result["pending_action_id"] = result["action"]["id"]
        return {**result, "request_id": request_id}
    except ModelTimeoutError as error:
        return _error_response(504, str(error), "MODEL_TIMEOUT", request_id)
    except ProviderPermissionError as error:
        return _error_response(403, str(error), "PROVIDER_PERMISSION_DENIED", request_id)
    except ProviderRateLimitError as error:
        return _error_response(429, str(error), "PROVIDER_RATE_LIMITED", request_id)
    except ProviderError as error:
        return _error_response(503, str(error), "PROVIDER_UNAVAILABLE", request_id)
    except ProductivityToolTimeoutError as error:
        return _error_response(504, str(error), "TOOL_TIMEOUT", request_id)
    except ProductivityToolError as error:
        return _error_response(503, str(error), "TOOL_UNAVAILABLE", request_id)
    except InvalidActionError as error:
        return _error_response(422, str(error), "INVALID_ACTION", request_id)
    except ActionConflictError as error:
        return _error_response(409, str(error), "ACTION_CONFLICT", request_id)


async def _resolve_action(
    action_id: str,
    decision: Literal["confirm", "cancel"],
    data: ActionResolution,
    db: AsyncSession,
):
    request_id = str(uuid4())
    record = await agent_memory.get_action(action_id)
    if record is None:
        return _error_response(404, "Pending action was not found.", "ACTION_NOT_FOUND", request_id)
    if record["thread_id"] != data.thread_id:
        return _error_response(409, "Pending action belongs to another conversation.", "ACTION_CONFLICT", request_id)
    if record["status"] != "pending":
        return _error_response(409, "Pending action has already been resolved.", "ACTION_CONFLICT", request_id)
    if _is_expired(record["expires_at"]):
        if await agent_memory.set_action_status(action_id, "expired"):
            try:
                await _agent(record["provider"], db).resolve_action(
                    action_id, "cancel", data.thread_id, request_id
                )
            except Exception:
                app_logger.warning(
                    "agent_event request_id=%s node=expire_cleanup outcome=error",
                    request_id,
                )
        return _error_response(409, "Pending action has expired.", "ACTION_EXPIRED", request_id)

    rate_limit_response = _apply_chat_rate_limit(record["provider"], data.thread_id, request_id)
    if rate_limit_response is not None:
        return rate_limit_response

    claimed = await agent_memory.set_action_status(
        action_id,
        "confirmed" if decision == "confirm" else "cancelled",
    )
    if not claimed:
        return _error_response(409, "Pending action has already been resolved.", "ACTION_CONFLICT", request_id)

    try:
        result = await _agent(record["provider"], db).resolve_action(
            action_id,
            decision,
            data.thread_id,
            request_id,
        )
        if decision == "confirm":
            await agent_memory.set_action_status(action_id, "completed", "confirmed")
        return {**result, "request_id": request_id}
    except ModelTimeoutError as error:
        await agent_memory.set_action_status(action_id, "failed", "confirmed")
        return _error_response(504, str(error), "MODEL_TIMEOUT", request_id)
    except ProviderPermissionError as error:
        await agent_memory.set_action_status(action_id, "failed", "confirmed")
        return _error_response(403, str(error), "PROVIDER_PERMISSION_DENIED", request_id)
    except ProviderRateLimitError as error:
        await agent_memory.set_action_status(action_id, "failed", "confirmed")
        return _error_response(429, str(error), "PROVIDER_RATE_LIMITED", request_id)
    except ActionConflictError as error:
        await agent_memory.set_action_status(action_id, "failed", "confirmed")
        return _error_response(409, str(error), "ACTION_CONFLICT", request_id)
    except InvalidActionError as error:
        await agent_memory.set_action_status(action_id, "failed", "confirmed")
        return _error_response(422, str(error), "INVALID_ACTION", request_id)
    except ActionTimeoutError as error:
        await agent_memory.set_action_status(action_id, "failed", "confirmed")
        return _error_response(504, str(error), "ACTION_TIMEOUT", request_id)
    except (ActionExecutionError, ProductivityToolError) as error:
        await agent_memory.set_action_status(action_id, "failed", "confirmed")
        return _error_response(503, str(error), "ACTION_FAILED", request_id)
    except ProviderError as error:
        await agent_memory.set_action_status(action_id, "failed", "confirmed")
        return _error_response(503, str(error), "PROVIDER_UNAVAILABLE", request_id)


@router.post("/actions/{action_id}/confirm")
async def confirm_action(
    action_id: str,
    data: ActionResolution,
    db: AsyncSession = Depends(get_db),
):
    return await _resolve_action(action_id, "confirm", data, db)


@router.post("/actions/{action_id}/cancel")
async def cancel_action(
    action_id: str,
    data: ActionResolution,
    db: AsyncSession = Depends(get_db),
):
    return await _resolve_action(action_id, "cancel", data, db)
