# Handoff ngắn — P1-C Episodic Relationship Memory

**Ngày:** 2026-10-24

**Trạng thái:** P1-A, P1-B và P1-C đã implement; P1-C hoàn tất ngày 2026-10-25.

## Nền tảng hiện có

- Stable local `profile_id`, explicit personal memories và correction audit trong `pomopet.db`.
- Immutable `user_action_events`, `habit_profiles`, initial focus duration và local habit suggestions.
- Conversation checkpoint vẫn nằm riêng trong `pomo_agent_memory.db`, tối đa 20 messages/thread.
- Explicit low-risk context có thể được gửi tới provider theo consent hiện có.
- Inferred behavioral habits chỉ dùng local, chưa được phép gửi tới OpenAI/Gemini.
- Không có vector DB, embeddings, episode, ritual hoặc relational state.

## Scope P1-C

1. Thêm `relationship_episodes` và `shared_rituals` có source reference, salience, confidence, timestamps, active/archive state.
2. Chỉ tạo episode từ sự kiện đáng nhớ có evidence thật: milestone lớn, recovery, explicit shared event hoặc correction quan trọng; không biến mọi task/session thành episode.
3. Consolidation deterministic, giữ source links và không bịa emotional tone/details.
4. Retrieval dùng structured SQL/SQLite FTS trước; chỉ đánh giá vector retrieval khi có benchmark chứng minh cần thiết.
5. Thêm bounded relational state cho familiarity, warmth, playfulness, concern và pride; có version, limits và decay.
6. Persona expression phải tuân explicit preference, không guilt/loneliness/jealousy/dependency và không giả vờ nhớ.
7. UI Settings hiển thị shared moments/rituals, evidence/source và cho archive/delete/never-mention/delete-all.

## Boundary bắt buộc

- Không gửi episode, ritual, relational state hoặc inferred habit tới provider nếu chưa có consent riêng.
- Current instruction > explicit preference > contextual habit > global habit > persona state.
- LLM chỉ đề xuất candidate; backend deterministic quyết định validate/activate.
- Không log raw personal content, episode summary hoặc source message.
- Failure của memory/retrieval không được làm hỏng chat, task, planning, session hay pending action.
- Không dùng completion, silence hoặc app usage như subjective reward/friendship score.

## Trình tự đề xuất

1. Chốt schema, sensitivity/consent policy và threat model.
2. Migration repeatable + CRUD/audit tests.
3. Episode candidate và consolidation policy deterministic.
4. SQLite FTS retrieval benchmark và compact local context builder.
5. Relational-state rules + persona safety tests.
6. UI controls, delete/export và graceful fallback.
7. Chỉ sau consent mới tích hợp phần context cần thiết vào model call.

## Acceptance tối thiểu

- Milestone thật tạo đúng một episode có source; retry không duplicate.
- Episode không đủ salience không được activate.
- Correction/archive/never-mention loại episode khỏi retrieval.
- Retrieval không thêm chi tiết ngoài evidence và không trả dữ liệu stale/suppressed.
- Persona có thể ấm áp nhưng không thao túng hoặc tuyên bố cảm xúc sinh học.
- Delete relationship data giữ nguyên task/session/plan/checkpoint.
- Tắt personalization hoặc lỗi memory vẫn giữ toàn bộ luồng productivity hoạt động.

## Release gate

- Migration repeatability và preservation tests.
- Episode/ritual CRUD, idempotency, consolidation và retrieval tests.
- Consent/privacy, fabricated-memory và persona-safety tests.
- Frontend controls/error-state tests.
- Backend full suite, frontend tests, TypeScript, ESLint, compileall, `pip check` và `git diff --check` pass.

Đọc thêm: `PERSONALIZATION_HANDOFF.md`, `CONTEXT.md`, `personalization-api.md` và section P1 trong `todolist.md`. Không bắt đầu P1-C trước khi user approve milestone này rõ ràng.

## Implementation result

- Structured `relationship_episodes`, `shared_rituals`, `relationship_memory_audits` và versioned `relational_states` nằm trong `pomopet.db`.
- Candidate policy deterministic: monthly milestone có entity thật, explicit shared event/recovery, ritual xác nhận rõ; salience dưới ngưỡng và agent suggestion không activate.
- Retry idempotent, consolidation giữ toàn bộ source references, suppressed record không tự tái kích hoạt; low-salience non-milestone auto-archive sau 180 ngày còn milestone không decay chỉ vì cũ.
- Retrieval dùng SQLite FTS5 + structured active/status filters, fallback SQL khi FTS không khả dụng; chưa có vector dependency.
- Relationship context mặc định local-only và có consent riêng `relationship_context_on`; provider không nhận source/audit/suppressed data.
- Settings hiển thị shared moments, rituals, evidence, bounded expression state; hỗ trợ archive/delete/never-mention/delete-all.
- Persona prompt phân biệt evidence/state và cấm fabricated recall, guilt, loneliness, jealousy, dependency hoặc biological-emotion claims.

### Verification 2026-10-25

```text
Backend full suite       114 passed
Frontend suite           44 passed
Python compileall        passed
pip check                passed
TypeScript --noEmit      passed
ESLint                    passed, 0 errors (26 pre-existing warnings)
git diff --check         passed
```
