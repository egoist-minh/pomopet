# Personalization API — P1-A/P1-B/P1-C

All routes use the existing local runtime-token authentication.

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/relationship/profile` | Get or create the stable local profile. |
| `PATCH` | `/api/relationship/profile` | Toggle `personalization_on`, `memory_prompts_on`, or the separate `relationship_context_on` provider consent. |
| `GET` | `/api/relationship/memories` | List active, non-superseded memories. |
| `PATCH` | `/api/relationship/memories/{id}` | Validate and supersede a memory with an edited value. |
| `DELETE` | `/api/relationship/memories/{id}` | Soft-delete/deactivate or mark a memory `never_mention`; the operation is audited. |
| `DELETE` | `/api/relationship/data` | Hard-delete personal memories, corrections, behavioral events and habits while retaining the stable profile and all productivity data. |
| `GET` | `/api/relationship/habits` | List active inferred habits with confidence, evidence, context and explanation. |
| `DELETE` | `/api/relationship/habits/{id}` | Dismiss an inferred habit so aggregation does not reactivate that scope. |
| `GET` | `/api/relationship/focus-suggestion?view=today&timezone_offset=420` | Get local duration/task-rank suggestions for an editable Start-focus preview. |
| `GET` | `/api/relationship/episodes` | List active evidenced shared moments with source references, confidence and salience. |
| `DELETE` | `/api/relationship/episodes/{id}` | Archive, delete, or mark an episode `never_mention`; the operation is audited. |
| `GET` | `/api/relationship/rituals` | List active, explicitly confirmed shared rituals. |
| `DELETE` | `/api/relationship/rituals/{id}` | Archive, delete, or mark a ritual `never_mention`; the operation is audited. |
| `GET` | `/api/relationship/relational-state` | Read bounded, versioned expression state. This is not a friendship score. |

The client cannot create arbitrary memory JSON. Chat statements pass through the allowlisted extractor and deterministic validation service. Raw personal values and source messages must not be written to application logs.

Session start/extend/cancel and task-complete requests accept optional `source`, `idempotency_key` and allowlisted `action_context`. Unknown context fields are discarded before persistence. `DELETE /relationship/data` also removes action events and habits, but keeps tasks, sessions, plans, conversation checkpoints, and the stable profile.

Inferred habit payloads remain local UI data. Episodes, rituals and relational state also remain local by default. They enter compact turn-specific provider context only when the user explicitly enables `relationship_context_on`; source references and audit data are never sent.

P1-C accepts only deterministic, allowlisted episode/ritual candidates. Verified app events require a real entity link, ordinary tasks/sessions never become episodes, and rituals require explicit confirmation. SQLite FTS5 is a disposable candidate index over active structured records; SQL remains the source of truth and is the fallback when FTS5 is unavailable.
