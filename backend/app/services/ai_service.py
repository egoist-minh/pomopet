import os
from pathlib import Path
import re
import traceback

from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

load_dotenv()


class ProviderError(RuntimeError):
    """A provider failure whose message is safe to return to the user."""


class ProviderPermissionError(ProviderError):
    """The provider rejected the configured credential or project access."""


class ProviderRateLimitError(ProviderError):
    """The provider rejected a request because its quota or rate limit was reached."""


def provider_failure_diagnostics(error: BaseException) -> dict[str, str]:
    """Return provider diagnostics without logging messages, prompts, or credentials."""
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and len(chain) < 6 and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__

    error_types = ">".join(
        f"{type(item).__module__}.{type(item).__name__}" for item in chain
    ) or "unknown"
    searchable = " ".join(
        f"{type(item).__name__} {item}".lower() for item in chain
    )
    if any(token in searchable for token in ("resourceexhausted", "quota", "rate limit", "429")):
        category = "quota_or_rate_limit"
    elif any(token in searchable for token in ("permissiondenied", "unauthenticated", "api key not valid", "401", "403")):
        category = "permission_or_api_key"
    elif "notfound" in searchable or ("model" in searchable and "not found" in searchable):
        category = "model_not_found"
    elif any(token in searchable for token in ("timeout", "deadlineexceeded", "deadline exceeded")):
        category = "timeout"
    elif any(token in searchable for token in ("validationerror", "outputparser", "structured output", "schema")):
        category = "invalid_structured_output"
    elif any(token in searchable for token in ("invalidargument", "bad request", "400")):
        category = "invalid_request"
    elif "api key is not configured" in searchable:
        category = "missing_configuration"
    else:
        category = "provider_unavailable"

    def safe_attribute(name: str) -> str:
        for item in chain:
            value = getattr(item, name, None)
            if callable(value):
                continue
            if isinstance(value, (int, str)):
                candidate = str(value)
            elif value is not None and hasattr(value, "name"):
                candidate = str(value.name)
            else:
                continue
            if re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", candidate):
                return candidate
        return "unknown"

    frames: list[str] = []
    for item in chain:
        if item.__traceback__ is None:
            continue
        for frame in traceback.extract_tb(item.__traceback__)[-4:]:
            frames.append(f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}")
    status = safe_attribute("status_code")
    if status == "unknown":
        status = safe_attribute("code")
    return {
        "error_types": error_types,
        "category": category,
        "status": status,
        "reason": safe_attribute("reason"),
        "domain": safe_attribute("domain"),
        "trace": ">".join(frames[-8:]) or "unavailable",
    }


def provider_model_name(provider: str) -> str:
    if provider == "gemini":
        return os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


class ModelFactory:
    _runtime_api_keys: dict[str, str] = {}

    @classmethod
    def configure_api_key(cls, provider: str, api_key: str) -> None:
        if provider not in {"openai", "gemini"}:
            raise ValueError(f"Unsupported AI provider: {provider}")
        cls._runtime_api_keys[provider] = api_key

    @classmethod
    def configured_providers(cls) -> dict[str, bool]:
        return {
            "openai": bool(cls._runtime_api_keys.get("openai") or os.getenv("OPENAI_API_KEY")),
            "gemini": bool(cls._runtime_api_keys.get("gemini") or os.getenv("GEMINI_API_KEY")),
        }

    @classmethod
    def create(
        cls,
        provider: str = "openai",
        model: str | None = None,
        max_tokens: int = 200,
        temperature: float = 0.7,
    ) -> BaseChatModel:
        providers = {
            "openai": {
                "api_key": cls._runtime_api_keys.get("openai") or os.getenv("OPENAI_API_KEY"),
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            },
            "gemini": {
                "api_key": cls._runtime_api_keys.get("gemini") or os.getenv("GEMINI_API_KEY"),
                "model": os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"),
            },
        }
        if provider not in providers:
            raise ValueError(f"Unsupported AI provider: {provider}")

        config = providers[provider]
        if model:
            config = {**config, "model": model}
        api_key = config["api_key"]
        if not api_key:
            raise ProviderError(f"{provider.title()} API key is not configured")

        try:
            if provider == "openai":
                return ChatOpenAI(
                    api_key=api_key,
                    model=config["model"],
                    temperature=temperature,
                    max_completion_tokens=max_tokens,
                    timeout=30,
                    max_retries=0,
                )

            return ChatGoogleGenerativeAI(
                api_key=api_key,
                model=config["model"],
                temperature=temperature,
                max_tokens=max_tokens,
                request_timeout=30,
                retries=0,
            )
        except Exception as error:
            raise ProviderError(f"{provider.title()} chat is unavailable") from error
