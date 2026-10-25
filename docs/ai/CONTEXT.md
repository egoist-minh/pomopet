# PomoPet domain context

## Memory architecture

PomoPet separates memory by responsibility:

- LangGraph checkpoints in `pomo_agent_memory.db` keep at most 20 conversation messages and pending actions by `thread_id`.
- Business data in `pomopet.db` owns a stable local `profile_id`, explicit personal memories, immutable user-action events, deterministic habit profiles, relationship episodes, confirmed rituals, bounded relational state, and correction audit records.
- `thread_id` is never user identity. Deleting browser/local chat storage does not delete the local profile.
- P1-A/P1-B/P1-C use structured SQLite as source of truth. P1-C adds a disposable SQLite FTS5 episode index with deterministic SQL fallback; no ChromaDB, embeddings, or external vector database is used.

Personal memory is allowlisted and typed. P1-A supports preferred name/address, communication style, explicit focus duration, and low-risk likes/dislikes/productivity preferences. Only explicit, low-risk user statements can become active. Temporary or sensitive statements are not stored.

At model-call time, the backend sends the selected OpenAI or Gemini provider a compact list of active explicit preferences. It never sends inactive/superseded memories, correction records, source messages, or the complete profile. Current user instructions override stored preferences. If memory retrieval fails or personalization is disabled, chat continues without personalized context.

Users manage this data in Settings → What Pomo remembers. They can edit, forget, mark never-mention, disable capture/personalization, or delete all relationship data without deleting tasks, sessions, plans, or conversation checkpoints.

P1-B records allowlisted productivity actions (`task_selected`, `task_completed`, session start/extend/cancel, and suggestion accept/change) with idempotency keys. Task actions snapshot view/rank/count/sort context at action time. Sessions keep `initial_duration` separate from the backward-compatible total `duration`; migrated rows are marked `legacy_total` rather than treated as verified selections.

Habit Aggregator v1 deterministically derives focus duration, task rank, focus start bucket, and extension pattern. A habit needs at least three samples and confidence 0.55 to become a suggestion; automatic prefill additionally needs at least five samples and confidence 0.78. Evidence uses a 45-day half-life. Explicit preferences override inferred habits, and repeated user overrides reduce dominance/confidence. Inferred habits stay local: they are shown in Settings and Plan UI but are not added to OpenAI/Gemini model context without separate consent.

P1-C records only high-salience, evidenced moments: completed monthly milestones with real plan-item links, explicitly shared important events, recovery statements, and explicit rituals. Ordinary task/session completion is not relationship evidence. Duplicate sources are idempotent; deterministic consolidation preserves every source reference without inventing details or emotional tone. Archive, delete and never-mention immediately remove records from retrieval. Low-salience non-milestones auto-archive after 180 days; verified milestones are never decayed merely because they are old.

Relational state has five bounded dimensions (`familiarity`, `warmth`, `playfulness`, `concern`, `pride`), a versioned deterministic update rule, and decay toward safe baselines. It changes expression only and is never a reward/friendship score. Completion, silence and app usage do not increase it.

Episodes, rituals and relational state stay local unless the user separately enables `relationship_context_on`. Even after consent, each turn receives only relevant active episode summaries, confirmed rituals and compact expression state—never source references, audits, suppressed records or inferred habits. Current instruction > explicit preference > contextual habit > global habit > persona state. Persona policy forbids guilt, loneliness, jealousy, dependency, biological-emotion claims and fabricated recall.
