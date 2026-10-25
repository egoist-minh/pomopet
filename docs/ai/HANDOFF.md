# Latest handoff — 2026-10-24

## Personalization implementation handoff

- Kế hoạch `P1 — User Personalization & Relationship Memory` đã được thêm vào `docs/ai/todolist.md`.
- Handoff triển khai chi tiết nằm tại `docs/ai/PERSONALIZATION_HANDOFF.md`.
- Trạng thái hiện tại: **P1-A đã được user approve và implement**; P1-B/P1-C chưa được approve.
- P1-A gồm stable profile, explicit personal memories, compact retrieval, user-control UI và tests.
- P1-A dùng SQLite, không thêm Vector DB. Kiến trúc hiện hành đã được đồng bộ tại `docs/ai/CONTEXT.md`.
- API và privacy contract nằm tại `docs/ai/personalization-api.md`.
- Snapshot bàn giao, file map, known limitations và lệnh cho agent tiếp theo nằm ở mục 0 và mục 14 của
  `docs/ai/PERSONALIZATION_HANDOFF.md`.
- Release gate gần nhất: backend 86 tests, frontend 42 tests, compile/typecheck/lint/pip/diff check đều pass.
- Không bắt đầu P1-B/P1-C nếu chưa có approval mới từ user.

## Trạng thái hiện tại

- User đang chạy PomoPet bằng `run.bat` ở chế độ dev/hot reload; chưa cần package lại trong lúc tiếp tục phát triển.
- `run.bat` đã được sửa để dev và bản đóng gói dùng chung dữ liệu tại
  `%APPDATA%\ai-studio-applet` qua `POMOPET_DATA_DIR` và `POMOPET_USER_DATA_DIR`.
- Nguyên nhân dữ liệu từng “biến mất”: dev trước đây mặc định đọc `backend/pomopet.db`, còn bản đóng gói đọc
  `%APPDATA%\ai-studio-applet\pomopet.db`. File DB dev cũ vẫn được giữ nguyên, không xoá và không merge tự động.
- Sau khi chạy lại bằng `run.bat`, API đã xác nhận đọc đúng DB dùng chung: 6 open task và 6 active Goal
  (NLP, RL, Data Mining, DL, Kinh tế chính trị, IELTS).
- Quy ước hình ảnh của user vẫn là `ponytail` cho mọi thiết kế nhân vật/minh hoạ mới.

## Chức năng đã triển khai sau handoff cũ

- Provider chat/planner hiện dùng Gemini; lỗi LLM được chuẩn hoá và log kèm request reference để debug.
- Goal có thể xoá; daily task/history được giữ theo lifecycle contract.
- Inbox cho phép chọn Goal, weekly outcome và ngày trước khi schedule task.
- Goal, Monthly milestone và Weekly outcome có nút bút chì để chỉnh trực tiếp trong Plan UI.
  Goal sửa được title, definition of done, deadline, importance và weekly capacity. Month/Week sửa được title,
  period và importance.
- Backend chặn đổi tháng/tuần nếu làm child item rơi ra ngoài parent period; user phải dời child trước.
- Pomo chat đã có hướng dẫn sử dụng Plan; mọi write action vẫn có Confirm/Cancel.
- Action chat `update_plan_item` mới cho phép chỉnh một Monthly milestone, Weekly outcome hoặc Daily task theo
  yêu cầu tự nhiên. Các trường hỗ trợ:
  - Month/Week: `title`, `importance`, `period_start`.
  - Day: `title`, `importance`, `planned_for`, `estimate_minutes`.
- Pomo luôn gọi `get_planning_context` để resolve ID; không đoán ID. Tên/tuần mơ hồ thì phải hỏi lại.
- Agent có thể tự đề xuất nhiều plan write trong cùng một lượt (tối đa 20 tool call), gom thành một preview
  và chỉ ghi database sau một lần Confirm: sửa Goal/plan item, dời hoặc thêm daily task, và regenerate tuần.
  Agent vẫn phải đọc planning context, resolve đúng ID, hỏi lại khi mơ hồ và không được thay đổi ngoài phạm vi user yêu cầu.

Ví dụ chat đã được hỗ trợ:

- `Đổi deadline Goal IELTS sang 30/12.`
- `Đổi milestone tháng 10 thành Hoàn thành Writing.`
- `Dời weekly outcome Mock test sang tuần 26/10.`
- `Đổi task Speaking sang 25/10, thời lượng 45 phút.`
- `Xóa Goal học React.`
- `Thêm daily task vào tuần này.`
- `Regenerate kế hoạch tuần này.`

## Verification mới nhất

- Backend full suite: **70/70 tests pass**.
- Hai nhóm test trực tiếp cho agent actions/productivity tools: **19/19 pass**.
- Python `py_compile`: pass.
- `git diff --check` trên các file vừa sửa: pass.
- Frontend suite gần nhất: **34/34 tests pass**; TypeScript pass; lint 0 errors (còn warning cũ).
- `run.bat` đã được chạy thực tế; Next.js ở port 3000, FastAPI ở port 8000, Electron mở thành công và API trả
  đúng 6 open task từ DB dùng chung.

## Files chính của thay đổi gần nhất

- `run.bat` — ép dev dùng chung Electron user-data/database với bản đóng gói.
- `backend/app/services/productivity_actions.py` — schema, validation, preview và execute `update_plan_item`.
- `backend/app/services/agent_runtime.py` — prompt/tool registry/success message cho sửa Plan qua chat.
- `backend/app/services/productivity_tools.py` — planning context có thêm importance.
- `backend/tests/test_agent_actions.py` — test Confirm/execute và horizon-field validation.
- `backend/tests/test_productivity_tools.py` — expected tool registry.
- `frontend/components/PlanPanel.tsx` — editor trực tiếp cho Goal/Monthly/Weekly.
- `backend/app/services/planning_service.py` — bảo vệ parent/child khi đổi period.

## Việc còn lại / lưu ý cho phiên sau

- Weekly Review/replan đầy đủ (Slice 4) vẫn chưa triển khai.
- Bản `dist/win-unpacked/PomoPet.exe` không chứa thay đổi source mới nhất; chỉ package khi user muốn tạo bản chạy độc lập.
- Khi phát triển, khởi động bằng `run.bat`. Không chạy thêm một backend riêng nếu port 8000 đang được dùng.
- Không copy đè DB khi app/backend đang chạy. Nếu cần import dữ liệu từ `backend/pomopet.db`, phải backup cả hai DB
  và thiết kế merge theo ID trước; hiện chưa cần vì dữ liệu user cần đã nằm trong AppData DB.
- Dev process hiện được khởi động từ `run.bat`; đóng terminal hoặc nhấn Ctrl+C để dừng cả API/Next/Electron.

---

# Session Handoff — Planning MVP approved — 2026-10-23

## Trạng thái bàn giao

Planning MVP đã được người dùng approve ở mức sản phẩm. Slice 1 — Domain foundation/migration,
Slice 2 — Manual Planning UI và Slice 3 — AI plan draft đã được triển khai; Weekly Review chưa triển khai.

Implementation update ngày 2026-10-23:

- Đã thêm ADR `docs/adr/0003-planning-domain-foundation.md`.
- Đã thêm model Goal và mở rộng bảng `tasks` thành PlanItem store.
- Đã thêm migration additive/repeatable, backfill legacy task và kiểm thử trên bản sao database thật.
- Đã thêm CRUD/lifecycle API tại `/api/planning/goals` và `/api/planning/plan-items`.
- Đã thêm hierarchy/date validation, optimistic version conflict và progress roll-up.
- Backend chỉ cho open daily item thuộc active goal bắt đầu focus session.
- Legacy delete API hiện soft-drop record thay vì hard-delete.
- Đã thêm `backend/tests/test_planning.py`; toàn bộ backend/frontend verification pass tại thời điểm bàn giao.
- Đã thêm frontend API types/client và `PlanPanel` với Inbox, Today, Week, Month, manual goal,
  milestone/outcome/task creation, reschedule, Inbox, drop, complete và daily-only Start focus.
- Tab vẫn giữ ID `tasks` để tương thích Electron IPC nhưng label đã đổi thành `Plan`.
- Slice 2 đã feature-complete ở mức code và typecheck; cần visual/runtime acceptance trước khi đánh dấu
  toàn bộ Planning UI backlog là done.
- Quy ước hình ảnh do user chốt: mọi thiết kế nhân vật/minh hoạ mới luôn dùng phong cách tóc đuôi
  ngựa (`ponytail`). Các slice backend/Planning UI hiện tại không tạo hoặc sửa asset nhân vật.
- User đã visual-test Manual Planning UI và xác nhận khá ổn.
- Slice 3 backend/frontend hiện có versioned AI draft schema, rolling-wave/date validation,
  deterministic 80% capacity gate, editable preview, cancel và transactional/idempotent approval.
- Preview hỗ trợ regenerate toàn draft hoặc riêng một milestone/tuần. Regenerate nhánh giữ nguyên các
  chỉnh sửa local khác trong cùng một request và backend từ chối branch bị ngắt hoặc đụng ID ngoài nhánh.
- Verification sau Slice 3: 55 backend tests và 34 frontend tests pass; TypeScript, Python compile,
  lint (0 errors, còn warning cũ) và `git diff --check` đều đạt.

Thay đổi tài liệu trong phiên gần nhất:

- `docs/ai/todolist.md` đã được reset hoàn toàn và thay bằng Planning MVP backlog.
- Backlog cũ đã bị xoá theo yêu cầu.
- Không xoá task/session thật trong SQLite.
- Không có thay đổi schema hoặc behavior của app trong phiên planning này.

Nguồn sự thật cho scope và acceptance criteria:

- `docs/ai/todolist.md`

## Mục tiêu sản phẩm

PomoPet phải hỗ trợ goal dài hạn như một kỳ thi hoặc mục tiêu học tập, thay vì coi toàn bộ goal
là một task đơn lẻ:

```text
Goal
└── Monthly milestone
    └── Weekly outcome
        └── Daily task
            └── Focus sessions
```

AI được đưa vào MVP với vai trò tạo plan draft. AI không tự ghi dữ liệu hoặc tự thay đổi lịch.
Mọi plan và replan đều phải đi qua preview, edit và explicit approval.

## Quyết định sản phẩm đã chốt

### Planning hierarchy

- Goal là kết quả dài hạn, ví dụ `Thi IELTS ngày 20/12 và đạt 7.0`.
- Monthly milestone mô tả outcome của tháng, không phải action để bấm Start.
- Weekly outcome mô tả kết quả cam kết trong tuần, không phải action để bấm Start.
- Daily task là next action cụ thể và là cấp duy nhất có thể chạy focus session.
- Một daily task có thể nhận nhiều focus session qua nhiều ngày.
- Hoàn thành session không tự động hoàn thành task, milestone hoặc goal.

### Planning views

Tab `Tasks` sẽ trở thành `Plan`, gồm:

- `Inbox`: action chưa xếp lịch hoặc chưa liên kết goal.
- `Today`: daily tasks có thể thực thi.
- `Week`: weekly outcomes, capacity và daily tasks nhóm theo ngày.
- `Month`: goals và monthly milestones.

Main Window hiện khá hẹp. Week view phải dùng danh sách ngày theo chiều dọc; không triển khai
calendar bảy cột trong MVP.

### AI planning

- Input: goal, deadline, definition of done, current state, weaknesses, topics/syllabus,
  available weekdays, minutes per day và default session duration.
- Output: assumptions, monthly milestones, weekly outcomes và daily tasks tuần hiện tại.
- Dùng rolling-wave planning: không tạo chi tiết từng ngày cho toàn bộ thời gian tới deadline.
- Chỉ chi tiết hoá 2–4 tuần gần nhất ở mức weekly outcome.
- Chỉ tuần hiện tại có daily tasks.
- Nếu thiếu syllabus, AI phải nêu assumptions thay vì giả định ngầm.
- Manual planning phải hoạt động đầy đủ khi provider AI lỗi hoặc chưa được cấu hình.

### Approval và capacity

- AI chỉ trả draft có cấu trúc; không gọi CRUD trực tiếp để tạo hierarchy.
- Draft phải được validate bằng code trước khi preview.
- User có thể sửa, xoá, thêm hoặc regenerate một phần draft.
- Approve phải idempotent; retry không được tạo duplicate plan.
- Cancel draft không được ghi database.
- Backend tính capacity từ lịch khả dụng và mặc định plan tối đa 80% capacity.
- Draft vượt capacity không được approve cho đến khi user sửa hoặc explicit override.
- 80% là product default, không phải quy luật khoa học cố định.

### Reschedule và lifecycle

- Task quá ngày không tự động chuyển sang hôm sau.
- User phải chọn `Reschedule`, `Back to inbox` hoặc `Drop`.
- Drop giữ record và focus history; không phải hard delete.
- Goal/parent nên archive thay vì cascade-delete.
- Không được âm thầm xoá children hoặc session history.

## In scope MVP

1. Goal và planning hierarchy month/week/day.
2. Inbox, Today, Week và Month views.
3. Manual planning.
4. AI plan draft có structured schema, validation, preview/edit/approval.
5. Nhiều focus session cho một daily task.
6. Progress roll-up từ session lên day/week/month/goal.
7. Weekly Review và AI replan draft.
8. Migration bảo toàn task/session hiện tại.
9. Manual fallback khi AI unavailable.

## Out of scope MVP

- AI tự thay đổi lịch không cần approval.
- Google/Outlook Calendar integration.
- Collaboration, cloud sync hoặc multi-device sync.
- Gantt, dependency graph hoặc full drag-and-drop calendar.
- Habit tracker hoặc gamification mới.
- AI dạy bài, sinh/chấm đề hoặc xác minh nội dung chuyên ngành.
- Adaptive spaced-repetition engine hoặc Anki integration.
- Smart notification hoặc autonomous background agent.
- Dashboard/report nâng cao.
- Release work như auto-update, đa nền tảng hoặc đổi framework desktop.

## Hiện trạng code liên quan

### Backend

- `Task` hiện nằm trong `backend/app/models/models.py`.
- `Task` có name, priority, deadline, completed và estimated duration.
- `Session.task_id` hiện liên kết session với task bằng string ID.
- `TaskService` chỉ trả open tasks và chưa có planning hierarchy.
- Migration additive hiện chạy trong `backend/app/database/database.py::_migrate_schema`.
- REST routes hiện dùng `/api/tasks` và `/api/sessions`.
- Chat agent đã có read/write tools và confirmation flow.
- AI providers hiện hỗ trợ OpenAI và Gemini; API key không được log.

### Frontend

- `frontend/components/MainWindow.tsx` chứa toàn bộ Tasks UI hiện tại.
- `frontend/components/DesktopEnvironment.tsx` điều phối task/session state và API calls.
- `frontend/lib/api.ts` chứa types và REST client.
- Tab ID hiện vẫn là `tasks`; đổi label/route cần giữ tương thích IPC trong slice đầu.
- Pet Widget và Main Window đã là hai Electron windows riêng, đồng bộ qua preload/IPC.

## Chiến lược migration khuyến nghị

Ưu tiên migration additive, không drop hoặc rename bảng cũ trong slice đầu.

Phương án ít rủi ro nhất:

1. Thêm bảng `goals`.
2. Mở rộng bảng `tasks` để đóng vai trò `PlanItem` bằng các cột nullable:
   - `goal_id`
   - `parent_id`
   - `horizon`: `month | week | day`
   - `planned_for`
   - `period_start`
   - `status`
3. Task cũ được backfill thành:
   - `horizon = day`
   - `planned_for = NULL`
   - `goal_id = NULL`
   - `status = open` hoặc completed theo dữ liệu hiện có
4. Vì ID task không đổi, `sessions.task_id` và lịch sử session được giữ nguyên.
5. Python/TypeScript có thể dùng tên `PlanItem` ở layer mới trong khi table vẫn là `tasks`.
6. Chỉ cân nhắc rename table sau MVP; không đưa rename vào migration đầu.

Không hard-delete legacy task. Câu “clear task cũ trong todolist” của user chỉ nói về file
`docs/ai/todolist.md`, không phải dữ liệu ứng dụng.

## Domain defaults cần dùng trong MVP

- Goal deadline là bắt buộc đối với `Plan with AI`.
- Inbox item có thể không có goal và không có planned date.
- ISO week bắt đầu vào thứ Hai.
- `planned_for` là local calendar date, không phải UTC timestamp.
- Các timestamp audit/session vẫn lưu UTC.
- `importance` tiếp tục dùng `high | medium | low` để tương thích dữ liệu hiện có.
- `status` của plan item tối thiểu gồm `open | completed | dropped`.
- Goal status tối thiểu gồm `active | completed | archived`.
- Default session duration vẫn giới hạn 5–120 phút.
- Weekly capacity là tổng phút từ cấu hình từng weekday.

Nếu cần thay đổi một default ảnh hưởng schema hoặc behavior, ghi ADR trước khi code.

## Implementation slices

### Slice 1 — Domain foundation và migration — hoàn thành

Mục tiêu: thêm planning hierarchy thủ công mà chưa phụ thuộc AI hoặc UI mới hoàn chỉnh.

Thứ tự:

1. Viết domain contract/ADR ngắn cho Goal, PlanItem, statuses và date semantics.
2. Thêm SQLAlchemy model/cột và migration additive, repeatable.
3. Backfill task cũ thành Inbox daily action mà giữ nguyên IDs.
4. Thêm service/API CRUD cho goal và plan item.
5. Validate parent chain `month → week → day`.
6. Chặn focus session trên month/week item ở backend.
7. Thêm progress aggregation query.
8. Viết backend tests trước khi nối UI.

Slice 1 đã đạt các điều kiện:

- Database hiện tại migrate được mà không mất task/session.
- API tạo được goal, monthly milestone, weekly outcome và daily task.
- Legacy task xuất hiện như Inbox item.
- Chỉ daily item start được session.
- Roll-up trả đúng actual focus minutes và completed task counts.
- Migration chạy lần hai không thay đổi dữ liệu hoặc lỗi.

### Slice 2 — Manual Planning UI — implemented, pending visual acceptance

Không đổi tab ID `tasks` trong bước QA; Pet Window vẫn gửi action theo contract cũ.

1. Thêm API types/client.
2. Đổi Tasks UI thành Plan shell.
3. Xây Inbox và Today trước.
4. Sau đó thêm Week và Month.
5. Giữ tab ID `tasks` tạm thời nếu đổi ID làm vỡ Electron IPC; đổi label trước.
6. Thêm manual Goal creation và reschedule/drop flows.

### Slice 3 — AI plan draft

1. Tạo Pydantic schema versioned cho planner input/output.
2. Tạo planner service chỉ trả validated draft, không ghi database.
3. Thêm deterministic capacity validator.
4. Thêm preview/edit UI.
5. Thêm transactional + idempotent approval endpoint.
6. Reuse provider selection/error normalization hiện có.

Không nên nhét toàn bộ hierarchy vào một chat tool call không kiểm soát. Planner cần endpoint/service
riêng và payload có schema; chat có thể gọi planner sau khi core flow ổn định.

### Slice 4 — Weekly Review và replan

1. Planned-versus-actual summary.
2. Xử lý unfinished tasks.
3. Thu thập obstacle/capacity mới.
4. Tạo replan draft.
5. Reuse preview/edit/approve pipeline của initial plan.

## AI draft contract gợi ý

Draft nên dùng temporary client IDs để biểu diễn parent-child trước khi ghi database:

```json
{
  "schema_version": 1,
  "assumptions": [],
  "items": [
    {
      "client_id": "month-1",
      "parent_client_id": null,
      "horizon": "month",
      "title": "...",
      "period_start": "2026-11-01",
      "estimate_minutes": null
    },
    {
      "client_id": "week-1",
      "parent_client_id": "month-1",
      "horizon": "week",
      "title": "...",
      "period_start": "2026-11-02",
      "estimate_minutes": null
    },
    {
      "client_id": "day-1",
      "parent_client_id": "week-1",
      "horizon": "day",
      "title": "...",
      "planned_for": "2026-11-02",
      "estimate_minutes": 30
    }
  ]
}
```

Backend phải validate lại toàn bộ IDs, hierarchy, dates, item count, duration và capacity. Không dùng
ID do model tạo làm database ID.

## Critical edge cases

- Deadline nằm giữa tuần hoặc giữa tháng.
- Goal chỉ còn ít ngày nhưng AI tạo milestone dài hơn deadline.
- Một daily task cần nhiều session.
- Session hoàn thành sau nửa đêm local time.
- User đổi timezone sau khi đã plan.
- Parent completed/archive trong khi còn child open.
- Reschedule task có active session.
- Draft approval bị retry sau network timeout.
- Provider trả JSON hợp lệ về cú pháp nhưng sai parent chain.
- Capacity bằng 0 hoặc nhỏ hơn default session duration.
- Task cũ đã completed nhưng vẫn có session history.

## Verification

Chạy kiểm tra liên quan sau mỗi slice; trước handoff tiếp theo chạy toàn bộ:

```powershell
Push-Location backend
conda run -n pomopet python -m unittest discover -s tests -q
conda run -n pomopet python -m compileall -q app
conda run -n pomopet python -m pip check
Pop-Location

Push-Location frontend
npm test
npm exec tsc -- --noEmit
npm run lint
Pop-Location

git diff --check
```

Các test mới tối thiểu phải bao phủ:

- Repeatable migration và legacy backfill.
- Parent-chain validation.
- Daily-only session start.
- Roll-up không tính penalty time.
- Capacity overflow và explicit override.
- Malformed AI output.
- Cancel không ghi dữ liệu.
- Approval idempotency.
- AI unavailable nhưng manual planning vẫn hoạt động.

## Files nên đọc trước khi code

- `docs/ai/todolist.md` — scope và acceptance criteria chính thức.
- `backend/app/models/models.py` — schema Task/Session hiện tại.
- `backend/app/database/database.py` — migration runtime hiện tại.
- `backend/app/services/task_service.py` — CRUD và task serialization.
- `backend/app/services/session_service.py` — start/complete session.
- `backend/app/api/routes/tasks.py` — REST contract hiện tại.
- `backend/app/services/productivity_actions.py` — validation/confirmation/idempotency patterns.
- `backend/app/services/pomo_agent.py` — provider/tool integration.
- `frontend/components/MainWindow.tsx` — Tasks UI hiện tại.
- `frontend/components/DesktopEnvironment.tsx` — application state và API orchestration.
- `frontend/lib/api.ts` — frontend types và REST client.
- `frontend/lib/desktop-ipc.ts` — tab/action contract giữa hai windows.

## Worktree safety

- Worktree đang có nhiều thay đổi và file untracked từ các phiên trước.
- Không dùng `git reset --hard`, `git checkout --` hoặc xoá hàng loạt.
- Không sửa generated files trong `frontend/out` bằng tay.
- Kiểm tra diff theo từng file trước khi edit để tránh ghi đè công việc hiện có.
- Giữ mỗi implementation slice nhỏ, có migration/test riêng và dễ review.
- Không quay lại backlog release/installer cũ trừ khi user yêu cầu rõ.
