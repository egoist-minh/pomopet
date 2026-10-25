from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.personal_memory_schemas import MemoryCandidate
from app.services.personal_memory_service import PersonalMemoryService
from app.services.profile_service import ProfileService
from app.services.habit_service import HabitService


SENSITIVE_MARKERS = {
    "bệnh",
    "sức khỏe",
    "sức khoẻ",
    "trầm cảm",
    "tự tử",
    "tôn giáo",
    "chính trị",
    "tình dục",
    "mang thai",
    "religion",
    "politic",
    "diagnosis",
    "depression",
    "suicide",
    "sexual",
    "pregnant",
}
TEMPORARY_MARKERS = {
    "hôm nay",
    "lúc này",
    "bây giờ",
    "dạo này",
    "có lẽ",
    "today",
    "right now",
    "lately",
    "maybe",
}


@dataclass(frozen=True)
class MemoryRemoval:
    key: str
    operation: str = "deleted"
    expected_value: str | int | None = None


@dataclass
class ExtractionResult:
    candidates: list[MemoryCandidate] = field(default_factory=list)
    removals: list[MemoryRemoval] = field(default_factory=list)


@dataclass
class MemoryProcessingResult:
    remembered_keys: list[str] = field(default_factory=list)
    removed_keys: list[str] = field(default_factory=list)

    def prompt_notice(self) -> str | None:
        parts: list[str] = []
        if self.remembered_keys:
            parts.append("saved explicit preferences: " + ", ".join(self.remembered_keys))
        if self.removed_keys:
            parts.append("forgot preferences: " + ", ".join(self.removed_keys))
        return "; ".join(parts) if parts else None


class MemoryExtractor:
    """Conservative, allowlisted P1-A extractor for explicit low-risk statements."""

    @staticmethod
    def _clean(value: str) -> str:
        return " ".join(value.strip(" \t\r\n.!?;:\"'“”‘’").split())

    def extract(self, message: str) -> ExtractionResult:
        result = ExtractionResult()
        lowered = message.casefold()

        if re.search(r"\b(quên|xóa|xoá)\s+(tên|tên của)\s*mình\b", lowered) or re.search(
            r"\bforget\s+(my\s+)?name\b", lowered
        ):
            result.removals.append(MemoryRemoval("preferred_name"))
        if re.search(r"\bđừng\s+nhắc\s+lại\s+(tên|cách gọi)\b", lowered):
            key = "preferred_name" if "tên" in lowered else "preferred_address"
            result.removals.append(MemoryRemoval(key, "never_mention"))
        if re.search(
            r"(?:đừng|không)\s+(?:mặc định|gợi ý).{0,30}(?:focus|tập trung|phút)|"
            r"(?:don't|do not)\s+(?:default|suggest).{0,30}(?:focus|minutes?)",
            lowered,
        ):
            result.removals.append(MemoryRemoval("explicit_focus_duration", "deactivated"))

        for match in re.finditer(
            r"đừng\s+gọi\s+mình\s+là\s+([^,.!?]+?)(?:\s+nữa)?(?:[,\.!?]|$)",
            message,
            flags=re.IGNORECASE,
        ):
            value = self._clean(re.sub(r"\s+nữa$", "", match.group(1), flags=re.IGNORECASE))
            if value:
                result.removals.append(
                    MemoryRemoval("preferred_address", "deactivated", value)
                )

        blocked_for_storage = any(marker in lowered for marker in SENSITIVE_MARKERS)
        temporary = any(marker in lowered for marker in TEMPORARY_MARKERS)
        if blocked_for_storage or temporary:
            return result

        for segment in re.split(r"[,;\n]+", message):
            normalized_segment = self._clean(segment)
            segment_lower = normalized_segment.casefold()
            if "đừng gọi" in segment_lower or "don't call" in segment_lower:
                continue

            name_match = re.search(
                r"(?:tên\s+(?:của\s+)?mình\s+là|mình\s+tên(?:\s+là)?)\s+(.+)$",
                normalized_segment,
                flags=re.IGNORECASE,
            ) or re.search(r"(?:my\s+name\s+is)\s+(.+)$", normalized_segment, flags=re.IGNORECASE)
            if name_match:
                value = self._clean(name_match.group(1))
                if value:
                    result.candidates.append(MemoryCandidate(key="preferred_name", value=value))
                continue

            address_match = re.search(
                r"(?:hãy\s+)?gọi\s+mình\s+là\s+([^.!?]+)$",
                normalized_segment,
                flags=re.IGNORECASE,
            ) or re.search(r"(?:please\s+)?call\s+me\s+([^.!?]+)$", normalized_segment, flags=re.IGNORECASE)
            if address_match:
                value = self._clean(address_match.group(1))
                if value:
                    result.candidates.append(MemoryCandidate(key="preferred_address", value=value))
                continue

        if re.search(r"(?:nhắc|trả lời|phản hồi).{0,20}\bngắn\b|keep\s+(?:it|replies?)\s+(?:short|concise)", lowered):
            result.candidates.append(
                MemoryCandidate(key="communication_style", value="concise")
            )
        elif re.search(r"(?:trả lời|giải thích).{0,20}\bchi tiết\b|(?:detailed|more detail)\s+(?:replies?|answers?)", lowered):
            result.candidates.append(
                MemoryCandidate(key="communication_style", value="detailed")
            )

        duration_match = re.search(
            r"(?:mình\s+)?(?:thích|muốn|thường)\s+(?:focus|tập trung)\s+(\d{1,3})\s*(?:phút|minutes?|mins?)",
            lowered,
        ) or re.search(r"(?:focus|session)\s+(?:for\s+)?(\d{1,3})\s*(?:minutes?|mins?)", lowered)
        if duration_match:
            minutes = int(duration_match.group(1))
            if 5 <= minutes <= 240:
                result.candidates.append(
                    MemoryCandidate(key="explicit_focus_duration", value=minutes)
                )

        # General likes/dislikes are deliberately narrow and exclude productivity
        # duration/style phrases handled above.
        if not re.search(r"\b(focus|tập trung|nhắc|trả lời|phản hồi)\b", lowered):
            preference_match = re.search(
                r"(?:mình\s+)?(thích|không\s+thích|ghét)\s+([^.!?]{1,200})",
                message,
                flags=re.IGNORECASE,
            ) or re.search(r"\bi\s+(like|dislike|hate)\s+([^.!?]{1,200})", message, flags=re.IGNORECASE)
            if preference_match:
                verb = preference_match.group(1).casefold()
                value = self._clean(preference_match.group(2))
                key = "like" if verb in {"thích", "like"} else "dislike"
                if value:
                    result.candidates.append(MemoryCandidate(key=key, value=value))

        # Keep only the final candidate for each key within one user statement.
        deduplicated: dict[str, MemoryCandidate] = {}
        for candidate in result.candidates:
            deduplicated[candidate.key] = candidate
        result.candidates = list(deduplicated.values())
        return result


def personalization_feature_enabled() -> bool:
    return os.getenv("PERSONALIZATION_ENABLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


async def process_user_memory(
    database: AsyncSession,
    message: str,
    source_reference: str,
) -> MemoryProcessingResult:
    extraction = MemoryExtractor().extract(message)
    lowered = message.casefold()
    suppress_duration_habit = bool(re.search(
        r"(?:đừng|không)\s+(?:mặc định|gợi ý).{0,30}(?:focus|tập trung|phút)|"
        r"(?:don't|do not)\s+(?:default|suggest).{0,30}(?:focus|minutes?)",
        lowered,
    ))
    if not extraction.candidates and not extraction.removals and not suppress_duration_habit:
        return MemoryProcessingResult()
    service = PersonalMemoryService(database)
    processed = MemoryProcessingResult()
    if suppress_duration_habit:
        await HabitService(database).dismiss_key("focus_duration")

    capture_enabled = personalization_feature_enabled()
    if capture_enabled and extraction.candidates:
        profile = await ProfileService(database).get_or_create_default()
        capture_enabled = profile.personalization_on and profile.memory_prompts_on

    candidate_keys = {candidate.key for candidate in extraction.candidates}
    atomic_correction_keys = {
        removal.key
        for removal in extraction.removals
        if capture_enabled
        and removal.operation == "deactivated"
        and removal.key in candidate_keys
    }

    # Forget/correction commands continue to work even while personalization is off.
    for removal in extraction.removals:
        # A same-turn "don't call me X, call me Y" is one replacement. The
        # remember service deactivates X, links superseded_by, audits, and inserts
        # Y in a single transaction.
        if removal.key in atomic_correction_keys:
            continue
        changed = await service.deactivate_key(
            removal.key,
            removal.operation,
            source_reference,
            removal.expected_value,
        )
        if changed:
            processed.removed_keys.append(removal.key)

    if not capture_enabled:
        return processed
    for candidate in extraction.candidates:
        memory = await service.remember(candidate, source_reference)
        if memory is not None:
            processed.remembered_keys.append(candidate.key)
            if candidate.key in atomic_correction_keys:
                processed.removed_keys.append(candidate.key)
    return processed
