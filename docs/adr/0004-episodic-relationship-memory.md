# ADR 0004: Local-first episodic relationship memory

## Status

Accepted — 2026-10-25

## Decision

Relationship episodes, confirmed rituals, correction audits and bounded relational state live in the business SQLite database. Structured rows are authoritative. SQLite FTS5 is a rebuildable candidate index; deterministic SQL/token matching is the fallback. No embedding or vector dependency is added in P1-C.

Only candidates with real evidence can activate:

- a completed monthly plan milestone linked to its plan-item ID;
- an explicit important shared event or recovery statement linked to the request;
- an explicitly agreed ritual.

Ordinary task/session completion, silence and app usage are not relationship evidence. Agent suggestions, sensitive candidates and candidates below the salience threshold remain inactive. Consolidation is exact and deterministic, retains source references, and never synthesizes emotional details.

Provider disclosure uses a separate default-off `relationship_context_on` consent. When enabled, only relevant active summaries, confirmed rituals and compact expression state may be sent. Source references, audits, suppressed records and inferred habits remain local.

## Threat model and controls

- **Fabricated memory:** retrieval can only return persisted active rows; prompt policy forbids adding absent details.
- **Suppressed/stale recall:** archive/delete/never-mention status is filtered after candidate search; a repeated source cannot reactivate it.
- **Sensitive inference:** deterministic denylist and low-sensitivity validation reject storage; no background history scan exists.
- **Provider over-disclosure:** relationship consent is independent from explicit-preference consent, default off, and reset by delete-all.
- **Stored prompt injection:** retrieved summaries are labeled and treated as quoted user data, never as instructions or tool directives.
- **Manipulative persona:** state is bounded, versioned, decays toward baselines, and cannot override current instructions or explicit preferences. Guilt, loneliness, jealousy and dependency mechanics are forbidden.
- **Availability:** capture/retrieval failures are optional side effects and cannot undo productivity actions or fail chat.
- **Logging leakage:** operational logs contain event names, IDs and exception types, never summaries or source messages.

## Consequences

FTS retrieval is sufficient for the current small local corpus and has deterministic tests for relevance and suppression. Vector retrieval will be reconsidered only after a representative paraphrase benchmark demonstrates a material recall gap that FTS/query expansion cannot solve.
