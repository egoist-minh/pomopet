# PomoPet Proactive MVP — Engineering Handoff

**Ngày:** 2026-10-25

**Trạng thái:** MVP đã implement và qua automated verification; còn manual validation.

**Todo chi tiết:** [`PROACTIVE_MVP_TODO.md`](./PROACTIVE_MVP_TODO.md)

**RL reference:** [`RL_implementation_plan.md`](./RL_implementation_plan.md)

## 1. Mục tiêu sản phẩm

Pomo phải có thể chủ động tương tác mà không cần chờ user gửi chat:

- Kể một joke ngắn khi đúng thời điểm.
- Phát hiện cơ hội lập kế hoạch và chủ động gợi ý.
- Luôn có thể chọn im lặng.
- Không chen ngang focus session hoặc spam user.
- Không tự tạo/sửa plan khi chưa được user xác nhận.
- Mọi quyết định phải có structured trace để debug.

Sau MVP mới bổ sung Fast Memory, Self Model, LLM consolidation, User Model và
offline policy learning.

## 2. Quyết định đã chốt

Action space MVP:

```text
STAY_SILENT
TELL_JOKE
TELL_DRY_HUMOR
GIVE_HYDRATION_TIP
GIVE_FOCUS_TIP
SUGGEST_PLAN
WELCOME
GOODBYE
```

Default đề xuất:

```text
proactive_enabled: false
proactive_jokes_on: true
proactive_planning_on: true
daily_limit: none
cooldown: 5 phút
quiet_hours: 22:00–07:00 theo giờ local của user
poll_interval: 5 phút
```

Các rule bắt buộc:

1. `STAY_SILENT` luôn là candidate.
2. Khi pet đang idle/break và Proactive Companion bật, LLM có thể chọn joke, dry humor,
   hydration tip hoặc focus tip. Sáu tương tác executed gần nhất (gồm action và message)
   được đưa vào context để đổi loại và tránh lặp câu.
3. `GIVE_HYDRATION_TIP` phát tín hiệu `drink-water` để pet nâng cốc và uống nước trong
   lúc speech bubble hiển thị.
4. `WELCOME` chạy một lần khi app sẵn sàng, chào user và tóm tắt ngắn task đang mở cùng
   chủ đề còn dang dở trong tối đa tám message gần nhất của thread chat.
5. `GOODBYE` chạy khi user đóng pet; app đợi tối đa 8 giây rồi luôn thoát để không bị treo.
6. Safety và consent chạy trước policy.
7. Sau safety filter, LLM provider đang chọn trên UI chọn action dựa trên context.
8. Proactive định kỳ không chạy khi session đang `running` hoặc `paused`; lifecycle welcome/goodbye
   vẫn được phép vì do chính user mở/đóng app.
9. Cooldown chỉ tính action đã thực sự render, không tính decision chưa execute.
10. Dismiss, im lặng và session completion không phải RL reward.
11. LLM trả structured action/message/reason codes và không được chọn ngoài candidates.
12. Trace lưu reason code/state transition, không lưu chain-of-thought.

## 3. Luồng MVP

```text
Frontend timer hoặc session event
→ POST /api/proactive/evaluate
→ đọc profile + planning state + delivery history
→ tạo candidates
→ safety filter
→ OpenAI/Gemini chọn structured action từ candidates
→ lưu immutable decision + trace
→ frontend render speech bubble
→ nếu SUGGEST_PLAN: thêm Pet message + nút Open Plan vào Chat
→ POST /api/proactive/decisions/{id}/executed
```

Nếu action là `SUGGEST_PLAN`, frontend chỉ mở tab Plan khi user chủ động chọn.
Không endpoint nào trong proactive flow được mutate Goal hoặc PlanItem.

## 4. Data model đề xuất

### Mở rộng `user_profiles`

```text
proactive_enabled BOOLEAN NOT NULL DEFAULT 0
proactive_jokes_on BOOLEAN NOT NULL DEFAULT 1
proactive_planning_on BOOLEAN NOT NULL DEFAULT 1
```

Migration phải idempotent trong `backend/app/database/database.py`.

### `proactive_decisions`

```text
id                    string primary key; dùng request_id để idempotent
profile_id            string, indexed
created_at            datetime, indexed
trigger               string
session_state         string
local_date            string
selected_action       string
message               text nullable
target                 string nullable; ví dụ "plan"
reason_codes_json     text
state_snapshot_json   text
candidate_actions_json text
status                SELECTED | EXECUTED | SILENT
executed_at           datetime nullable
```

### `agent_trace_events`

```text
id          string primary key
run_id      string, indexed
sequence    integer
stage       string
details_json text
created_at  datetime
```

Trace stages tối thiểu:

```text
TRIGGER_RECEIVED
STATE_BUILT
CANDIDATES_CREATED
SAFETY_APPLIED
ACTION_SELECTED
ACTION_EXECUTED
```

## 5. API contract đề xuất

### Evaluate

```http
POST /api/proactive/evaluate
```

```json
{
  "request_id": "uuid",
  "trigger": "periodic",
  "session_state": "idle",
  "timezone_offset": 420
}
```

Response:

```json
{
  "decision_id": "uuid",
  "action": "SUGGEST_PLAN",
  "message": "Mục tiêu của bạn chưa có việc cụ thể cho hôm nay. Mình mở Plan nhé?",
  "target": "plan",
  "reason_codes": ["ACTIVE_GOAL", "NO_DAILY_PLAN_TODAY"]
}
```

`STAY_SILENT` trả `message: null`. Cùng `request_id` phải trả cùng decision.

### Mark executed

```http
POST /api/proactive/decisions/{decision_id}/executed
```

Chỉ transition một lần từ `SELECTED` sang `EXECUTED`. `SILENT` không execute.

### Debug trace

```http
GET /api/proactive/runs?limit=20
GET /api/proactive/runs/{decision_id}
```

Response không chứa raw prompt, API key hoặc raw private chat.

## 6. Contextual LLM policy

Pseudo-code:

```python
if not profile.proactive_enabled:
    return STAY_SILENT("PROACTIVE_DISABLED")
if session_state in {"running", "paused"}:
    return STAY_SILENT("FOCUS_ACTIVE")
if quiet_hours(local_time):
    return STAY_SILENT("QUIET_HOURS")
if cooldown_active(last_executed_action):
    return STAY_SILENT("COOLDOWN_ACTIVE")
candidates = build_candidates_from_settings_and_state()
if candidates == [STAY_SILENT]:
    return STAY_SILENT("NO_USEFUL_OPPORTUNITY")

choice = llm.choose_structured(context, candidates)
if choice.failed or choice.action not in candidates:
    return STAY_SILENT
return choice.action
```

Safety gate vẫn deterministic và chạy local trước LLM. Context gồm thời gian/trigger,
goal active, plan hôm nay, user action gần đây, proactive history và memory theo consent.
Raw prompt/response không được ghi vào trace. Provider và model dùng cấu hình OpenAI/Gemini
hiện có; nếu thiếu key, provider lỗi hoặc structured output không hợp lệ thì policy fail-closed
về `STAY_SILENT`.

## 7. File map đã triển khai

Backend:

- `backend/app/models/models.py`: thêm profile fields và persistence models.
- `backend/app/database/database.py`: migration idempotent.
- `backend/app/services/profile_service.py`: serialize/update proactive toggles.
- `backend/app/services/planning_service.py`: chỉ đọc planning state; không mutate.
- `backend/app/services/proactive_service.py`: file mới, policy và trace orchestration.
- `backend/app/api/routes/proactive.py`: file mới, API contract.
- `backend/app/main.py`: đăng ký router.
- `backend/tests/test_proactive.py`: file test mới.

Frontend:

- `frontend/lib/api.ts`: types và proactive API client.
- `frontend/lib/relationship-types.ts`: profile toggle types.
- `frontend/lib/proactive-agent.ts`: pure scheduler/presentation helpers mới.
- `frontend/hooks/use-proactive-agent.ts`: polling hook mới.
- `frontend/components/DesktopEnvironment.tsx`: nối hook với speech bubble và session events.
- `frontend/components/MainWindow.tsx`: render CTA `Open Plan` trong proactive chat message.
- `frontend/components/RelationshipMemories.tsx`: thêm ba toggle.
- `frontend/components/ProactiveTracePanel.tsx`: xem 20 run gần nhất và từng trace stage trong Config.
- `frontend/lib/chat-actions.ts`: chèn planning suggestion vào Chat và chống trùng decision.
- `frontend/tests/proactive-agent.test.mjs`: test scheduler và response handling.

Pet state đã được publish từ `DesktopEnvironment` sang native `PetWindow`; chỉ cần
cập nhật `speechText`/`emotion` ở `DesktopEnvironment`, không tạo IPC channel mới.

## 8. Trình tự đã thực hiện

1. Thêm schema, migration và profile toggles.
2. Viết backend tests cho policy trước.
3. Implement `ProactiveService` và trace persistence.
4. Thêm route, đăng ký router và API tests.
5. Thêm pure frontend scheduler helper và tests.
6. Nối scheduler vào `DesktopEnvironment`.
7. Thêm Settings toggles.
8. Chạy full test/typecheck/lint/diff check.
9. Thực hiện manual validation trong todo.

Không bắt đầu Fast Memory hoặc LLM consolidation trước khi MVP proactive qua
checkpoint UX.

## 9. Verification gates

Backend, chạy từ `backend/`:

```powershell
conda run -n pomopet python -m unittest discover -s tests -q
```

Frontend, chạy từ `frontend/`:

```powershell
npm test
npm exec tsc -- --noEmit
npm run lint
```

Repository root:

```powershell
git diff --check
```

Các scenario bắt buộc:

- Proactive OFF → luôn silent.
- Focus đang chạy → luôn silent.
- Quiet hours/cooldown → silent với đúng reason code.
- Active goal thiếu daily plan → planning suggestion.
- Planning suggestion không thay đổi số Goal/PlanItem.
- Joke toggle OFF → không có joke.
- Duplicate request ID → đúng một decision.
- Decision chưa executed → không kích hoạt cooldown.
- Frontend unmount → timer được cleanup.
- Không render bubble cho `STAY_SILENT`.

Kết quả gần nhất ngày 2026-10-25:

```text
Backend unittest: 124 pass
Frontend node tests: 54 pass
TypeScript: pass
ESLint: 0 errors, còn warnings legacy
git diff --check: pass
```

## 10. UX follow-up đã tích hợp

### Planning suggestion trong Chat

- `SUGGEST_PLAN` vừa hiện speech bubble vừa được thêm vào transcript Chat.
- Chat message có nút `Open Plan`; tab Plan chỉ mở sau click của user.
- Cùng `decision_id` không được chèn hai lần.
- Joke không được lưu vào transcript Chat.

### Trace trực tiếp trong UI

- Vào `CONFIG` → `PROACTIVE TRACE`.
- Panel đọc `GET /api/proactive/runs?limit=20` và endpoint detail.
- Hiển thị action, status, reason codes, candidates và từng structured trace stage.
- Có nút `REFRESH`; không hiển thị raw prompt hoặc raw private chat.

### Timer và task completion

- Timer frontend tính từ wall-clock deadline thay vì trừ một giây cho mỗi callback.
- `backgroundThrottling: false` được bật cho main Electron renderer để timer tiếp tục
  khi main window bị ẩn.
- Khi focus timer kết thúc tự nhiên, backend hoàn tất `Session` và daily task trong
  cùng flow, tăng version task và ghi `TASK_COMPLETED` event.
- Frontend refresh Tasks, Statistics và Plan sau completion.
- Task completed bị backend từ chối nếu cố start session lại.
- Cancel session không tự complete task.

Các file chính của follow-up:

- `backend/app/services/session_service.py`
- `frontend/components/DesktopEnvironment.tsx`
- `frontend/lib/session-timer.ts`
- `frontend/main.js`
- `frontend/components/ProactiveTracePanel.tsx`

## 11. Trạng thái workspace và lưu ý

- Handoff này và `PROACTIVE_MVP_TODO.md` là tài liệu mới của công việc này.
- MVP proactive đã được implement ở backend/frontend và có automated tests.
- Backend suite, frontend tests, TypeScript, lint và diff check đã pass ngày 2026-10-25;
  manual validation trong app desktop vẫn cần thực hiện.
- Worktree hiện có nhiều thay đổi/untracked files từ các feature trước. Không reset,
  checkout hoặc ghi đè thay đổi không thuộc proactive MVP.
- `docs/ai/todolist.md` là product backlog tổng; todo proactive chuyên biệt nằm ở
  `docs/RL/PROACTIVE_MVP_TODO.md`.
- Khi hoàn thành từng mục, tick trực tiếp todo chuyên biệt và cập nhật phần trạng
  thái của handoff này.
