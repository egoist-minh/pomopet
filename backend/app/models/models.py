from sqlalchemy import Column, String, Integer, DateTime, Enum, Boolean, Float, Text, Index, text
from datetime import datetime
import enum
from app.database.database import Base


def enum_values(enum_class):
    """Persist public enum values instead of Python member names."""
    return [member.value for member in enum_class]


class Priority(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class GoalStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class PlanHorizon(str, enum.Enum):
    MONTH = "month"
    WEEK = "week"
    DAY = "day"


class PlanItemStatus(str, enum.Enum):
    OPEN = "open"
    COMPLETED = "completed"
    DROPPED = "dropped"


class PlanDraftStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    CANCELLED = "cancelled"


class MemorySource(str, enum.Enum):
    EXPLICIT_USER = "explicit_user"
    VERIFIED_APP_EVENT = "verified_app_event"
    BEHAVIORAL_INFERENCE = "behavioral_inference"
    AGENT_SUGGESTION = "agent_suggestion"


class MemorySensitivity(str, enum.Enum):
    LOW = "low"
    SENSITIVE = "sensitive"


class MemoryCorrectionOperation(str, enum.Enum):
    CORRECTED = "corrected"
    DEACTIVATED = "deactivated"
    DELETED = "deleted"
    NEVER_MENTION = "never_mention"


class RelationshipMemoryStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"
    NEVER_MENTION = "never_mention"


class RelationshipEpisodeKind(str, enum.Enum):
    MILESTONE = "milestone"
    RECOVERY = "recovery"
    SHARED_EVENT = "shared_event"
    IMPORTANT_CORRECTION = "important_correction"


class UserActionType(str, enum.Enum):
    TASK_SELECTED = "task_selected"
    TASK_COMPLETED = "task_completed"
    SESSION_STARTED = "session_started"
    SESSION_EXTENDED = "session_extended"
    SESSION_CANCELLED = "session_cancelled"
    SUGGESTION_ACCEPTED = "suggestion_accepted"
    SUGGESTION_CHANGED = "suggestion_changed"


class UserActionSource(str, enum.Enum):
    UI = "ui"
    CHAT = "chat"
    SUGGESTION = "suggestion"


class Goal(Base):
    __tablename__ = "goals"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    definition_of_done = Column(String, nullable=False)
    deadline = Column(String, nullable=False)
    importance = Column(Enum(Priority), default=Priority.MEDIUM, nullable=False)
    status = Column(
        Enum(GoalStatus, values_callable=enum_values),
        default=GoalStatus.ACTIVE,
        nullable=False,
    )
    weekly_capacity_minutes = Column(Integer, default=0, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    priority = Column(Enum(Priority), default=Priority.MEDIUM)
    deadline = Column(String)
    completed = Column(Boolean, default=False)
    estimated_duration = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    goal_id = Column(String, nullable=True)
    parent_id = Column(String, nullable=True)
    horizon = Column(
        Enum(PlanHorizon, values_callable=enum_values),
        default=PlanHorizon.DAY,
        nullable=False,
    )
    planned_for = Column(String, nullable=True)
    period_start = Column(String, nullable=True)
    status = Column(
        Enum(PlanItemStatus, values_callable=enum_values),
        default=PlanItemStatus.OPEN,
        nullable=False,
    )
    version = Column(Integer, default=1, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


# The first Planning MVP migration deliberately keeps the existing table name and
# model so legacy task/session integrations continue to work.
PlanItem = Task


class PlanDraft(Base):
    __tablename__ = "plan_drafts"

    id = Column(String, primary_key=True)
    goal_id = Column(String, nullable=False)
    goal_version = Column(Integer, nullable=False)
    schema_version = Column(Integer, nullable=False, default=1)
    input_payload = Column(Text, nullable=False)
    payload = Column(Text, nullable=False)
    status = Column(
        Enum(PlanDraftStatus, values_callable=enum_values),
        default=PlanDraftStatus.DRAFT,
        nullable=False,
    )
    approval_key = Column(String, nullable=True, unique=True)
    approval_result = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    approved_at = Column(DateTime, nullable=True)


class Subtask(Base):
    __tablename__ = "subtasks"

    id = Column(String, primary_key=True)
    task_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    completed = Column(Boolean, default=False)


class SessionState(str, enum.Enum):
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DistractionSource(str, enum.Enum):
    MANUAL = "manual"
    APP_SWITCH = "app_switch"
    IDLE = "idle"


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    task_id = Column(String)
    duration = Column(Integer)  # in seconds
    initial_duration = Column(Integer, nullable=True)  # user-selected seconds before extensions
    initial_duration_source = Column(String, nullable=False, default="selected")
    time_left = Column(Integer)
    state = Column(Enum(SessionState), default=SessionState.RUNNING)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    distraction_count = Column(Integer, default=0)
    penalty_seconds = Column(Integer, default=0)


class DistractionEvent(Base):
    __tablename__ = "distraction_events"

    id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    source = Column(
        Enum(DistractionSource, values_callable=enum_values),
        nullable=False,
    )
    application = Column(String, nullable=True)
    confidence = Column(Float, default=1.0, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, default=0, nullable=False)


class Settings(Base):
    __tablename__ = "settings"

    id = Column(String, primary_key=True)
    pet_name = Column(String, default="Pomo")
    ai_service = Column(String, default="openai")
    session_duration = Column(Integer, default=25)
    short_break = Column(Integer, default=5)
    long_break = Column(Integer, default=15)
    sessions_until_long_break = Column(Integer, default=4)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(String, primary_key=True)
    display_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    personalization_on = Column(Boolean, default=True, nullable=False)
    memory_prompts_on = Column(Boolean, default=True, nullable=False)
    # Relationship episodes/state are more intimate than explicit preferences.
    # They remain local unless the user separately enables this consent flag.
    relationship_context_on = Column(Boolean, default=False, nullable=False)
    proactive_enabled = Column(Boolean, default=False, nullable=False)
    proactive_jokes_on = Column(Boolean, default=True, nullable=False)
    proactive_planning_on = Column(Boolean, default=True, nullable=False)


class ProactiveDecision(Base):
    __tablename__ = "proactive_decisions"
    __table_args__ = (
        Index("ix_proactive_decisions_profile_created", "profile_id", "created_at"),
        Index("ix_proactive_decisions_profile_status", "profile_id", "status"),
    )

    # The caller-generated request id is deliberately the primary key so retries
    # return the immutable decision instead of creating a second action.
    id = Column(String, primary_key=True)
    profile_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    trigger = Column(String, nullable=False)
    session_state = Column(String, nullable=False)
    local_date = Column(String, nullable=False)
    selected_action = Column(String, nullable=False)
    message = Column(Text, nullable=True)
    target = Column(String, nullable=True)
    reason_codes_json = Column(Text, nullable=False, default="[]")
    state_snapshot_json = Column(Text, nullable=False, default="{}")
    candidate_actions_json = Column(Text, nullable=False, default="[]")
    status = Column(String, nullable=False)
    executed_at = Column(DateTime, nullable=True)


class AgentTraceEvent(Base):
    __tablename__ = "agent_trace_events"
    __table_args__ = (
        Index("ix_agent_trace_events_run_sequence", "run_id", "sequence", unique=True),
    )

    id = Column(String, primary_key=True)
    run_id = Column(String, nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    stage = Column(String, nullable=False)
    details_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PersonalMemory(Base):
    __tablename__ = "personal_memories"
    __table_args__ = (
        Index("ix_personal_memories_profile_active", "profile_id", "active"),
        Index(
            "uq_personal_memories_active_key",
            "profile_id",
            "kind",
            "key",
            "scope",
            unique=True,
            sqlite_where=text("active = 1"),
        ),
    )

    id = Column(String, primary_key=True)
    profile_id = Column(String, nullable=False, index=True)
    kind = Column(String, nullable=False)
    key = Column(String, nullable=False)
    value_json = Column(Text, nullable=False)
    source_type = Column(
        Enum(MemorySource, values_callable=enum_values),
        nullable=False,
    )
    source_reference = Column(String, nullable=True)
    confidence = Column(Float, nullable=False)
    sensitivity = Column(
        Enum(MemorySensitivity, values_callable=enum_values),
        nullable=False,
    )
    scope = Column(String, nullable=False, default="global")
    active = Column(Boolean, nullable=False, default=True)
    superseded_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    last_confirmed_at = Column(DateTime, nullable=True)


class MemoryCorrection(Base):
    __tablename__ = "memory_corrections"

    id = Column(String, primary_key=True)
    profile_id = Column(String, nullable=False, index=True)
    memory_id = Column(String, nullable=True, index=True)
    operation = Column(
        Enum(MemoryCorrectionOperation, values_callable=enum_values),
        nullable=False,
    )
    source_reference = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class UserActionEvent(Base):
    __tablename__ = "user_action_events"
    __table_args__ = (
        Index("ix_user_action_events_profile_time", "profile_id", "occurred_at"),
        Index("ix_user_action_events_profile_type", "profile_id", "event_type"),
    )

    id = Column(String, primary_key=True)
    profile_id = Column(String, nullable=False, index=True)
    event_type = Column(
        Enum(UserActionType, values_callable=enum_values),
        nullable=False,
    )
    source = Column(
        Enum(UserActionSource, values_callable=enum_values),
        nullable=False,
    )
    entity_type = Column(String, nullable=True)
    entity_id = Column(String, nullable=True, index=True)
    idempotency_key = Column(String, nullable=False, unique=True)
    context_json = Column(Text, nullable=False, default="{}")
    occurred_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class HabitProfile(Base):
    __tablename__ = "habit_profiles"
    __table_args__ = (
        Index(
            "uq_habit_profiles_scope",
            "profile_id",
            "habit_key",
            "context_key",
            unique=True,
        ),
        Index("ix_habit_profiles_profile_active", "profile_id", "active"),
    )

    id = Column(String, primary_key=True)
    profile_id = Column(String, nullable=False, index=True)
    habit_key = Column(String, nullable=False)
    context_key = Column(String, nullable=False)
    context_json = Column(Text, nullable=False)
    value_json = Column(Text, nullable=False)
    distribution_json = Column(Text, nullable=False)
    evidence_count = Column(Integer, nullable=False, default=0)
    matching_count = Column(Integer, nullable=False, default=0)
    confidence = Column(Float, nullable=False, default=0.0)
    active = Column(Boolean, nullable=False, default=False)
    dismissed = Column(Boolean, nullable=False, default=False)
    model_version = Column(String, nullable=False, default="habit-v1")
    last_observed_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class RelationshipEpisode(Base):
    __tablename__ = "relationship_episodes"
    __table_args__ = (
        Index("ix_relationship_episodes_profile_status", "profile_id", "status"),
        Index("ix_relationship_episodes_profile_salience", "profile_id", "salience"),
        Index(
            "uq_relationship_episodes_source",
            "profile_id",
            "source_reference",
            unique=True,
            sqlite_where=text("source_reference IS NOT NULL"),
        ),
    )

    id = Column(String, primary_key=True)
    profile_id = Column(String, nullable=False, index=True)
    kind = Column(
        Enum(RelationshipEpisodeKind, values_callable=enum_values),
        nullable=False,
    )
    summary = Column(Text, nullable=False)
    source_type = Column(
        Enum(MemorySource, values_callable=enum_values),
        nullable=False,
    )
    source_reference = Column(String, nullable=True)
    source_references_json = Column(Text, nullable=False, default="[]")
    entity_type = Column(String, nullable=True)
    entity_id = Column(String, nullable=True, index=True)
    salience = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    emotional_tone = Column(String, nullable=True)
    sensitivity = Column(
        Enum(MemorySensitivity, values_callable=enum_values),
        nullable=False,
        default=MemorySensitivity.LOW,
    )
    scope = Column(String, nullable=False, default="global")
    status = Column(
        Enum(RelationshipMemoryStatus, values_callable=enum_values),
        nullable=False,
        default=RelationshipMemoryStatus.ACTIVE,
    )
    consolidation_key = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_recalled_at = Column(DateTime, nullable=True)


class SharedRitual(Base):
    __tablename__ = "shared_rituals"
    __table_args__ = (
        Index("ix_shared_rituals_profile_status", "profile_id", "status"),
        Index("uq_shared_rituals_key", "profile_id", "ritual_key", unique=True),
    )

    id = Column(String, primary_key=True)
    profile_id = Column(String, nullable=False, index=True)
    ritual_key = Column(String, nullable=False)
    label = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    source_type = Column(
        Enum(MemorySource, values_callable=enum_values),
        nullable=False,
    )
    source_references_json = Column(Text, nullable=False, default="[]")
    confidence = Column(Float, nullable=False)
    evidence_count = Column(Integer, nullable=False, default=1)
    explicitly_confirmed = Column(Boolean, nullable=False, default=False)
    scope = Column(String, nullable=False, default="global")
    status = Column(
        Enum(RelationshipMemoryStatus, values_callable=enum_values),
        nullable=False,
        default=RelationshipMemoryStatus.ACTIVE,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class RelationshipMemoryAudit(Base):
    __tablename__ = "relationship_memory_audits"
    __table_args__ = (
        Index("ix_relationship_audits_profile_time", "profile_id", "created_at"),
    )

    id = Column(String, primary_key=True)
    profile_id = Column(String, nullable=False, index=True)
    target_type = Column(String, nullable=False)
    target_id = Column(String, nullable=False, index=True)
    operation = Column(String, nullable=False)
    source_reference = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RelationalState(Base):
    __tablename__ = "relational_states"

    profile_id = Column(String, primary_key=True)
    familiarity = Column(Float, nullable=False, default=0.1)
    warmth = Column(Float, nullable=False, default=0.4)
    playfulness = Column(Float, nullable=False, default=0.25)
    concern = Column(Float, nullable=False, default=0.0)
    pride = Column(Float, nullable=False, default=0.0)
    rule_version = Column(String, nullable=False, default="relationship-v1")
    evidence_count = Column(Integer, nullable=False, default=0)
    last_event_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
# End of SQLAlchemy model declarations.
