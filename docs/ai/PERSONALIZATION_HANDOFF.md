# Handoff — User Personalization & Relationship Memory

**Ngày:** 2026-10-24

**Trạng thái:** P1-A, P1-B và P1-C đã được user approve và implement.

**Backlog nguồn:** `docs/ai/todolist.md`, section `P1 — User Personalization & Relationship Memory`.

> Tài liệu này giữ snapshot/thiết kế lịch sử của P1-A/P1-B. Trạng thái P1-C hiện tại nằm tại `P1C_HANDOFF.md`, `CONTEXT.md`, `personalization-api.md` và ADR 0004.

## 0. Snapshot bàn giao hiện tại

P1-A đã hoàn thành release gate. P1-B đã được triển khai trong phiên 2026-10-24; agent tiếp theo nên review hoặc xử lý feedback và chạy lại release gate. Không triển khai P1-C nếu chưa có approval mới.

### Đã triển khai thêm trong P1-B

- Immutable/idempotent `user_action_events` cho task select/complete, session start/extend/cancel và suggestion accept/change.
- Snapshot allowlisted `view`, rank, visible count, sort mode, timezone bucket và entity IDs; không lưu task title/raw screen content.
- `Session.initial_duration` + `initial_duration_source`; legacy backfill dùng `legacy_total`, còn `duration` tiếp tục là tổng sau extension.
- Deterministic Habit Aggregator v1 cho focus duration, task rank, start-time bucket và extension pattern; minimum 3 samples, prefill minimum 5 samples, confidence thresholds 0.55/0.78 và half-life 45 ngày.
- Plan UI mở editable Start-focus preview, dùng explicit preference trước habit, hiện evidence explanation, highlight suggested rank và ghi accept/change.
- Settings hiển thị habit local với confidence/evidence và cho dismiss; delete-all xoá memory/event/habit nhưng giữ productivity data.
- Correction “đừng mặc định/gợi ý … phút” dismiss duration habit đang có; repeated duration overrides làm confidence giảm.
- Inferred habits không được gửi tới OpenAI/Gemini trong P1-B vì consent P1-A chỉ bao phủ explicit low-risk context.
- Không thêm episode, relational state, vector DB hoặc embedding dependency.

### Đã triển khai

- Stable default profile trong business SQLite, độc lập với `thread_id`.
- `user_profiles`, `personal_memories`, `memory_corrections` cùng partial unique index bảo đảm một active
  memory cho mỗi `(profile_id, kind, key, scope)`.
- Typed allowlist cho `preferred_name`, `preferred_address`, `communication_style`,
  `explicit_focus_duration`, `like`, `dislike`, `productivity_preference`.
- Deterministic extractor cho explicit low-risk statement; temporary/sensitive statement không được lưu.
- Same-value write idempotent; correction tạo replacement atomically, deactivate record cũ, gắn
  `superseded_by` và ghi audit `corrected`.
- Forget, delete và never-mention loại memory khỏi retrieval; delete-all chỉ xoá relationship data,
  không xoá task/session/planning hoặc profile identity.
- Mỗi model call chỉ nhận compact active context phù hợp với turn; không gửi source message, correction,
  inactive/superseded/never-mention records. User đã cho phép gửi phần context low-risk này tới provider
  OpenAI/Gemini đang chọn.
- Memory extraction/retrieval lỗi thì rollback phần memory và chat tiếp tục; pending action flow giữ nguyên.
- Settings có màn hình `What Pomo remembers`: list, edit, forget, never-mention, delete-all,
  personalization toggle và memory-capture toggle.
- Feature flag toàn cục: `PERSONALIZATION_ENABLED=false`.
- Không thêm vector DB, embedding dependency, behavioral event hay relational state.

### File chính

```text
backend/app/models/models.py
backend/app/database/database.py
backend/app/services/personal_memory_schemas.py
backend/app/services/profile_service.py
backend/app/services/personal_memory_service.py
backend/app/services/memory_extractor.py
backend/app/services/user_context_builder.py
backend/app/api/routes/relationship.py
backend/app/api/routes/chat.py
backend/app/services/agent_runtime.py
backend/tests/test_personalization.py
frontend/lib/relationship-types.ts
frontend/lib/api.ts
frontend/components/RelationshipMemories.tsx
frontend/components/MainWindow.tsx
frontend/tests/core.test.mjs
```

### Verification cuối

```text
Backend full suite       86 passed
Frontend suite           42 passed
Python compileall        passed
pip check                passed
TypeScript --noEmit      passed
ESLint                   passed, 0 errors (26 warnings có sẵn)
git diff --check         passed
```

### Known limitations cần giữ rõ

- Extraction P1-A là deterministic allowlisted patterns tiếng Việt/Anh, không quét lại lịch sử chat cũ.
- Sensitive/temporary statement bị từ chối lưu; chưa có persisted candidate/confirmation workflow riêng
  cho dữ liệu nhạy cảm.
- UI chỉ quản lý active personal memories; chưa có audit-history viewer hoặc export JSON.
- `like` và `dislike` hiện là single active slot cho mỗi key, nên preference mới cùng key supersede giá trị cũ.
- Khi `AGENT_MODE=false`, single-turn fallback vẫn chạy nhưng không inject long-term context; default
  `AGENT_MODE=true` có đầy đủ personalization.
- Chưa có chat-side task-rank suggestion vì inferred habit không được gửi tới provider; Plan UI đã highlight local.
- Chưa có episodes, rituals, relational state hoặc vector retrieval.
- Workspace đang rất dirty từ Planning MVP và các phiên trước. Không reset/checkout hay ghi đè file ngoài scope.

## 1. Mục tiêu sản phẩm

Pomo cần hiểu người dùng qua nhiều phiên làm việc bằng ba loại thông tin khác nhau:

1. Personal facts và explicit preferences: tên, cách xưng hô, sở thích, tone mong muốn.
2. Behavioral habits: task thường chọn, duration thường dùng và context tương ứng.
3. Shared relationship episodes: milestone, khó khăn đã vượt qua, correction, ritual và inside joke.

Pomo có thể thể hiện warmth, familiarity, concern, pride hoặc playfulness theo persona, nhưng không được:

- giả vờ nhớ điều không có evidence;
- khẳng định có cảm xúc sinh học hoặc ý thức;
- dùng guilt, loneliness, jealousy, pressure hoặc dependency để điều khiển user;
- tự suy diễn/lưu thông tin nhạy cảm khi chưa có consent.

## 2. Quyết định đã chốt

### 2.1 Memory layers

```text
Conversation memory
  └── tối đa 20 messages theo thread_id; đã tồn tại

User profile memory
  └── personal facts và explicit preferences theo profile_id

Behavioral memory
  └── immutable events → deterministic habit profiles

Relationship memory
  └── episodes, rituals, corrections và bounded relational state
```

- `thread_id` không phải user identity.
- Tạo `profile_id` ổn định trong business SQLite; mọi thread local hiện tại dùng default profile này.
- Relationship/profile data thuộc business database `pomopet.db`, không đặt trong LangGraph checkpoint
  `pomo_agent_memory.db`.
- Current instruction > explicit preference > contextual inferred habit > global habit > app default.
- LLM chỉ đề xuất candidate memory. Backend validation/policy quyết định có lưu và activate hay không.

### 2.2 Không dùng Vector DB trong P1-A/P1-B

- SQLite structured tables là source of truth.
- Exact facts, preferences, habits, consent và corrections luôn dùng deterministic SQL lookup.
- P1-A/P1-B không thêm ChromaDB, external vector service hoặc embedding dependency.
- Có thể dùng SQLite full-text search cho episode summary khi tới P1-C.
- Chỉ đánh giá embedding/vector retrieval ở P1-C nếu số episode hoặc paraphrase retrieval chứng minh
  full-text search không đủ.
- Nếu thêm vector sau này, vector index chỉ tìm candidate episode; không quyết định fact nào là đúng.

Quyết định này **supersede** mô tả legacy trong `docs/ai/CONTEXT.md` rằng long-term memory mặc định dùng
ChromaDB. Không sửa `CONTEXT.md` trước khi implementation được approve; khi bắt đầu code phải đồng bộ lại
tài liệu đó.

### 2.3 Approval strategy

Không implement toàn bộ P1 trong một batch. Chia ba milestone độc lập:

```text
P1-A  Memory foundation và explicit personal facts
P1-B  Behavioral events và habit inference
P1-C  Episodic relationship memory và persona expression
```

Mỗi milestone phải qua migration, automated tests và acceptance scenarios trước khi sang milestone tiếp theo.

## 3. Hiện trạng code liên quan sau P1-A

- `backend/app/services/agent_memory.py`
  - Quản lý LangGraph checkpoints và pending actions trong `pomo_agent_memory.db`.
  - Đây là conversation/action state, không phải long-term user profile.
- `backend/app/services/agent_runtime.py`
  - `MAX_MEMORY_MESSAGES = 20`.
  - Inject compact structured explicit preferences qua `UserContextBuilder`.
- `frontend/lib/chat-memory.ts`
  - `thread_id` nằm trong local storage và có thể thay đổi nếu storage bị xoá.
  - Không được dùng ID này làm identity dài hạn của user.
- `backend/app/models/models.py`
  - Đã có `UserProfile`, `PersonalMemory`, `MemoryCorrection`, `UserActionEvent` và `HabitProfile`.
  - Chưa có `RelationshipEpisode`; đây là P1-C.
- `backend/app/services/session_service.py`
  - `extend_session()` vẫn cộng vào `Session.duration` để tương thích ngược.
  - `initial_duration` giữ lựa chọn lúc Start; dữ liệu legacy được đánh dấu `legacy_total`.
- `backend/app/services/task_service.py`
  - Open task legacy vẫn sort theo `created_at.desc()`.
  - Plan UI gửi snapshot rank/context tại thời điểm select/complete; backend không suy ngược sau action.
- `docs/RL/RL_implementation_plan.md`
  - Có thiết kế relationship feedback/RL rộng hơn.
  - P1 personalization không được biến completion, silence hoặc usage duration thành subjective reward.

Workspace hiện có nhiều thay đổi/untracked files từ Planning MVP và agent work. Không reset, checkout hoặc
ghi đè thay đổi ngoài scope. Trước khi sửa file phải kiểm tra diff/status và giữ nguyên work của user.

## 4. Scope đã implement: P1-A

### 4.1 In scope

- Stable local `profile_id` do backend get-or-create trong business SQLite.
- Typed personal memory schema với source, confidence, sensitivity, timestamps và active/superseded state.
- Explicit low-risk facts/preferences:
  - preferred name;
  - preferred form of address;
  - communication tone/style;
  - non-sensitive likes/dislikes;
  - explicit productivity preference.
- Memory candidate extraction từ user statement.
- Backend validation, supersede/correction và delete behavior.
- Context-aware retrieval của một số memory liên quan vào agent call.
- Basic “Pomo nhớ gì về mình” read/edit/delete UI.
- Feature flag để tắt personalization mà không ảnh hưởng task/session/chat.
- Migration và automated tests.

### 4.2 Out of scope P1-A

- Behavioral habit inference.
- Task-rank learning và duration aggregation.
- Episodic/shared-event generation.
- Relational state hoặc dynamic persona emotion.
- Vector DB/embeddings.
- Cloud sync, account system hoặc multi-device identity.
- Background autonomous extraction từ toàn bộ lịch sử chat cũ.

## 5. P1-A data contract đề xuất

Tên bảng cuối cùng có thể điều chỉnh theo convention hiện có, nhưng semantics không được nhập nhằng.

### 5.1 `user_profiles`

```text
id                  TEXT PRIMARY KEY
display_name        TEXT NULL
created_at          DATETIME NOT NULL
updated_at          DATETIME NOT NULL
personalization_on  BOOLEAN NOT NULL DEFAULT true
memory_prompts_on   BOOLEAN NOT NULL DEFAULT true
```

Single-user desktop dùng một row default. Không hardcode identity vào `thread_id`.

### 5.2 `personal_memories`

```text
id                  TEXT PRIMARY KEY
profile_id          TEXT NOT NULL
kind                TEXT NOT NULL
key                 TEXT NOT NULL
value_json          TEXT NOT NULL
source_type         TEXT NOT NULL
source_reference    TEXT NULL
confidence          FLOAT NOT NULL
sensitivity         TEXT NOT NULL
scope               TEXT NOT NULL
active              BOOLEAN NOT NULL
superseded_by       TEXT NULL
created_at          DATETIME NOT NULL
updated_at          DATETIME NOT NULL
last_confirmed_at   DATETIME NULL
```

Constraints/policy:

- Chỉ một active memory cho cùng `(profile_id, kind, key, scope)`.
- `value_json` phải được validate bằng typed schema theo `key`, không nhận arbitrary object.
- Source ban đầu: `explicit_user`, `verified_app_event`, `behavioral_inference`, `agent_suggestion`.
- P1-A chỉ activate `explicit_user`; `agent_suggestion` là candidate, không phải fact.
- Memory mới mâu thuẫn phải supersede record cũ trong cùng transaction.
- Raw personal value, source message và note không được ghi vào application log.

### 5.3 `memory_corrections`

```text
id                  TEXT PRIMARY KEY
profile_id          TEXT NOT NULL
memory_id           TEXT NULL
operation           TEXT NOT NULL
source_reference    TEXT NULL
created_at          DATETIME NOT NULL
```

`operation`: `corrected | deactivated | deleted | never_mention`. Không cần lưu lại raw value trong correction.

## 6. Extraction và write policy

### 6.1 Candidate extraction

Ví dụ có thể tạo candidate:

```text
“Tên mình là An”             → preferred_name = An
“Gọi mình là bro”            → preferred_address = bro
“Nhắc ngắn thôi nhé”         → communication_style = concise
“Mình thích focus 50 phút”   → explicit_focus_duration = 50
```

Không tự lưu thành long-term fact:

```text
“Hôm nay mình mệt”
“Có lẽ mình ghét task này”
“Dạo này ngủ ít”
Thông tin sức khoẻ, tôn giáo, chính trị, quan hệ hoặc trạng thái tâm lý nhạy cảm
```

Extraction output phải dùng structured schema và allowlisted key. Không cho model tự tạo key mới rồi ghi DB.

### 6.2 Confirmation

- Explicit, low-risk, unambiguous statement: có thể lưu và acknowledge ngắn.
- Ambiguous, sensitive hoặc potentially temporary statement: hỏi user trước, không lưu candidate như active fact.
- “Hãy nhớ…”: explicit write intent nhưng vẫn phải qua sensitivity policy.
- “Quên…”, “đừng nhớ…”, “đừng nhắc lại…”: thực thi deactivation/delete/never-mention đúng scope.
- User correction luôn thắng inference/candidate cũ.

### 6.3 Agent usage

Mỗi model call chỉ nhận compact structured context, ví dụ:

```json
{
  "explicit_preferences": [
    {
      "key": "preferred_name",
      "value": "An",
      "source": "explicit_user",
      "confidence": 1.0
    }
  ]
}
```

- Không inject toàn bộ profile hoặc source messages.
- Không inject inactive/superseded/never-mention memory.
- Nếu memory service lỗi, agent tiếp tục không-personalized; không fail toàn bộ chat.
- Model không được nói “Pomo nhớ…” nếu memory không tồn tại trong retrieved context.

## 7. API và service boundaries đề xuất

```text
backend/app/services/profile_service.py
backend/app/services/personal_memory_service.py
backend/app/services/memory_extractor.py
backend/app/api/routes/relationship.py
backend/app/services/user_context_builder.py
```

API tối thiểu:

```text
GET    /api/relationship/profile
PATCH  /api/relationship/profile
GET    /api/relationship/memories
PATCH  /api/relationship/memories/{id}
DELETE /api/relationship/memories/{id}
DELETE /api/relationship/data
```

Không expose generic endpoint cho client ghi arbitrary memory JSON. Create từ chat phải đi qua extraction,
validation và policy service.

Frontend dự kiến:

```text
frontend/components/RelationshipMemories.tsx
frontend/lib/relationship-types.ts
frontend/lib/api.ts
```

UI basic có thể đặt trong Settings hoặc một modal riêng; không cần redesign Main Window trong P1-A.

## 8. Trình tự implementation P1-A

1. Chốt schemas/enums/Pydantic contracts và migration strategy.
2. Thêm `user_profiles`, `personal_memories`, `memory_corrections` và migration tests.
3. Implement profile/memory repository + service; test supersede/delete/never-mention.
4. Implement relationship API; test validation, privacy và failure contracts.
5. Implement allowlisted structured memory extractor; mock provider trong unit tests.
6. Tích hợp extraction sau final user message theo cách không làm write action/pending action bị duplicate.
7. Build compact user context và inject vào agent model call.
8. Thêm basic memory-management UI và API client.
9. Thêm feature flag/fallback, end-to-end test và cập nhật docs.
10. Chạy release gate; dừng để review trước P1-B.

Không bắt đầu bằng prompt changes trước khi schema, policy và tests đã tồn tại.

## 9. Acceptance scenarios P1-A

### AS1 — Nhớ qua conversation mới

```text
User: “Tên mình là An.”
→ explicit low-risk memory được lưu cho default profile
→ tạo thread mới
→ Pomo có thể gọi đúng tên An
```

### AS2 — Correction

```text
User: “Đừng gọi mình là bro nữa, gọi mình là An.”
→ memory cũ inactive/superseded
→ correction được audit
→ turn sau chỉ dùng An
```

### AS3 — Forget

```text
User: “Quên tên mình đi.”
→ memory không còn xuất hiện trong retrieval
→ thread sau Pomo không dùng tên cũ
```

### AS4 — Temporary/sensitive statement

```text
User nói một trạng thái tạm thời hoặc thông tin nhạy cảm
→ không có active long-term memory nếu chưa có explicit consent phù hợp
```

### AS5 — Graceful degradation

```text
Memory DB/extractor lỗi hoặc personalization bị tắt
→ chat/task/session/planning vẫn hoạt động
→ không bịa profile hoặc làm mất pending action
```

## 10. P1-B implementation status

P1-B đã thêm `user_action_events`, `Session.initial_duration`, task view/rank snapshot, `habit_profiles`, editable duration prefill, task-rank highlight và override/correction behavior. Completion chỉ là event productivity; silence/app usage/completion không được dùng để suy diễn user thích personality hoặc reminder của Pet.

Chat-side task-rank suggestion vẫn chưa bật: inferred behavior chỉ được dùng local cho tới khi có consent riêng để đưa loại context này tới provider.

## 11. P1-C handoff boundary

Chỉ bắt đầu sau P1-B review. P1-C sẽ thêm:

- relationship episodes và salience/consolidation;
- shared rituals và inside jokes;
- bounded relational state;
- safe persona expression;
- full-text retrieval trước, evaluation vector retrieval sau nếu có evidence cần thiết.

## 12. Verification bắt buộc

- Migration mới chạy lặp lại an toàn và không mất business/agent data.
- Profile/memory CRUD và isolation tests.
- Supersede/correction/delete/never-mention tests.
- Extraction golden tests cho explicit fact, temporary statement, ambiguity và sensitive content.
- Retrieval tests không trả inactive/superseded/never-mention memory.
- Chat tests chứng minh memory tồn tại qua thread mới và fallback khi memory service lỗi.
- Frontend tests cho list/edit/delete/toggle và error state.
- Không có raw personal memory value trong logs.
- Python compilation, backend full suite, frontend tests, TypeScript, lint và `git diff --check` pass.

Project convention hiện ghi môi trường test là Conda env `pomopet`; dùng đúng environment nếu khả dụng.

## 13. Definition of Done P1-A

P1-A chỉ hoàn thành khi:

1. User có stable local profile độc lập với chat thread.
2. User có thể nói tên/cách xưng hô/preference low-risk và Pomo nhớ qua thread mới.
3. User có thể xem, sửa, xoá hoặc yêu cầu never-mention từng memory.
4. Source, confidence, sensitivity và supersede state được persistence/audit đúng.
5. Memory/retrieval failure không làm hỏng chat, task, session, planning hoặc pending action.
6. Không có Vector DB/embedding dependency trong P1-A.
7. Tests và release gate mục 12 đạt.
8. Tài liệu `CONTEXT.md`, `HANDOFF.md`, `todolist.md` và API/domain docs được cập nhật đồng bộ.

## 14. Lệnh bắt đầu cho agent tiếp theo

1. Đọc snapshot mục 0, `docs/ai/CONTEXT.md`, `docs/ai/personalization-api.md` và section P1 trong
   `docs/ai/todolist.md`.
2. Kiểm tra `git status` trước khi sửa; workspace chứa nhiều thay đổi/untracked file không thuộc P1-A.
3. Nếu nhiệm vụ là review P1-A, tập trung vào privacy, extractor false-positive, transaction semantics,
   migration repeatability và UI error states.
4. Chạy lại release gate mục 12 sau mọi thay đổi.
5. Không bắt đầu P1-B/P1-C, không thêm event/habit/episode/vector schema nếu user chưa approve rõ milestone đó.

## 15. Kết quả implementation P1-A

- Stable default profile và personal memory/correction tables nằm trong `pomopet.db`.
- Allowlisted deterministic extraction hỗ trợ tên, cách xưng hô, reply style, explicit focus duration và low-risk likes/dislikes.
- Correction supersede atomically; forget/never-mention loại memory khỏi retrieval và tạo audit record.
- Mỗi model call chỉ nhận compact active explicit context; source message và inactive memory không được gửi.
- Settings có UI xem, sửa, forget, never-mention, delete-all và hai toggle personalization/capture.
- `PERSONALIZATION_ENABLED=false` tắt capture/retrieval mà không ảnh hưởng productivity/chat.
- API contract được ghi tại `docs/ai/personalization-api.md`; domain contract tại `docs/ai/CONTEXT.md`.
- Không thêm vector DB/embedding dependency. P1-B và P1-C chưa được triển khai.
