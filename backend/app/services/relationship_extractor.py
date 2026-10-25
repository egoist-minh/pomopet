from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.memory_extractor import personalization_feature_enabled
from app.services.profile_service import ProfileService
from app.services.relationship_memory_service import RelationshipMemoryService
from app.services.relationship_schemas import EpisodeCandidate, RitualCandidate


_SENSITIVE_MARKERS = {
    "bệnh", "sức khỏe", "sức khoẻ", "trầm cảm", "tự tử", "tôn giáo", "chính trị",
    "tình dục", "mang thai", "religion", "politic", "diagnosis", "depression",
    "suicide", "sexual", "pregnant",
}


@dataclass
class RelationshipExtractionResult:
    episodes: list[EpisodeCandidate] = field(default_factory=list)
    rituals: list[RitualCandidate] = field(default_factory=list)


@dataclass
class RelationshipProcessingResult:
    episode_saved: bool = False
    ritual_saved: bool = False

    def prompt_notice(self) -> str | None:
        labels = []
        if self.episode_saved:
            labels.append("saved one explicitly shared moment")
        if self.ritual_saved:
            labels.append("saved one explicitly agreed ritual")
        return "; ".join(labels) if labels else None


class RelationshipExtractor:
    """Conservative rules: an explicit cue plus meaningful evidence is required."""

    @staticmethod
    def _clean(value: str) -> str:
        return " ".join(value.strip(" \t\r\n.!?;:\"'“”‘’-").split())[:300]

    def extract(self, message: str, source_reference: str) -> RelationshipExtractionResult:
        result = RelationshipExtractionResult()
        lowered = message.casefold()
        if any(marker in lowered for marker in _SENSITIVE_MARKERS):
            return result

        ritual_patterns = (
            r"(?:nghi\s*thức|ritual)(?:\s+của\s+(?:tụi|chúng)\s*mình|\s+of\s+ours)?\s*(?:là|is|:)\s*(.+)$",
            r"(?:hãy\s+nhớ|remember)(?:\s+rằng|\s+that)?\s+(?:tụi\s*mình|chúng\s*ta|we)\s+(?:luôn|always)\s+(.+)$",
        )
        for pattern in ritual_patterns:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if match:
                description = self._clean(match.group(1))
                if description:
                    result.rituals.append(RitualCandidate(
                        label="Shared ritual",
                        description=description,
                        source_reference=source_reference,
                        explicitly_confirmed=True,
                        confidence=1.0,
                    ))
                return result

        explicit_event = re.search(
            r"(?:hãy\s+)?(?:ghi\s+)?nhớ\s+(?:khoảnh\s*khắc|chuyện|sự\s*kiện)"
            r"(?:\s+(?:chung|này))?\s*[:\-]\s*(.+)$|"
            r"remember\s+(?:this\s+)?(?:shared\s+)?(?:moment|event)\s*[:\-]\s*(.+)$",
            message,
            flags=re.IGNORECASE,
        )
        if explicit_event:
            summary = self._clean(next(group for group in explicit_event.groups() if group))
            if summary:
                result.episodes.append(EpisodeCandidate(
                    kind="shared_event",
                    summary=summary,
                    source_type="explicit_user",
                    source_reference=source_reference,
                    salience=0.82,
                    confidence=1.0,
                ))
            return result

        milestone_markers = (
            ("cuối cùng", "hoàn thành"), ("cuối cùng", "đạt được"),
            ("finally", "completed"), ("finally", "finished"), ("major milestone", "completed"),
        )
        if any(first in lowered and second in lowered for first, second in milestone_markers):
            summary = self._clean(message)
            if summary:
                result.episodes.append(EpisodeCandidate(
                    kind="milestone",
                    summary=summary,
                    source_type="explicit_user",
                    source_reference=source_reference,
                    salience=0.86,
                    confidence=0.95,
                    emotional_tone="positive",
                ))
            return result

        recovery_markers = (
            "vượt qua giai đoạn khó", "vượt qua khó khăn", "quay lại sau giai đoạn khó",
            "recovered after a difficult", "came back after a difficult", "got through a difficult",
        )
        if any(marker in lowered for marker in recovery_markers):
            summary = self._clean(message)
            if summary:
                result.episodes.append(EpisodeCandidate(
                    kind="recovery",
                    summary=summary,
                    source_type="explicit_user",
                    source_reference=source_reference,
                    salience=0.84,
                    confidence=0.95,
                    emotional_tone="difficult",
                ))
        return result


async def process_relationship_memory(
    database: AsyncSession,
    message: str,
    source_reference: str,
) -> RelationshipProcessingResult:
    result = RelationshipProcessingResult()
    if not personalization_feature_enabled():
        return result
    profile = await ProfileService(database).get_or_create_default()
    if not profile.memory_prompts_on:
        return result
    extracted = RelationshipExtractor().extract(message, source_reference)
    service = RelationshipMemoryService(database)
    for candidate in extracted.episodes[:1]:
        episode = await service.create_episode(candidate)
        result.episode_saved = episode is not None and episode.status.value == "active"
    for candidate in extracted.rituals[:1]:
        ritual = await service.create_ritual(candidate)
        result.ritual_saved = ritual is not None and ritual.status.value == "active"
    return result
