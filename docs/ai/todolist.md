# PomoPet — Product Backlog

> Reset ngày 2026-10-23. Toàn bộ backlog cũ đã được xoá theo quyết định sản phẩm mới.
> P0 là Planning MVP đã được approve. P1 là kế hoạch tiếp theo cho User Personalization
> & Relationship Memory và không chặn release Planning MVP.

## Mục tiêu MVP

Giúp người dùng biến một goal kéo dài nhiều ngày hoặc nhiều tháng thành kế hoạch có thể thực thi:

```text
Goal
└── Monthly milestone
    └── Weekly outcome
        └── Daily task
            └── Focus sessions
```

AI tạo bản nháp kế hoạch dựa trên deadline, năng lực hiện tại, nội dung cần học và thời gian
khả dụng. Người dùng luôn được xem, sửa và approve trước khi dữ liệu thật được tạo hoặc thay đổi.

MVP thành công khi người dùng có thể:

1. Tạo goal và nhận AI plan draft trong dưới 3 phút.
2. Biết rõ hôm nay cần làm gì mà không phải nhìn toàn bộ goal.
3. Thực hiện nhiều focus session cho cùng một task qua nhiều ngày.
4. Review tuần và nhận đề xuất replan dựa trên tiến độ thật.
5. Giữ nguyên toàn bộ dữ liệu task/session hiện có sau migration.

## Product rules bắt buộc

- Monthly và weekly item là kết quả cần đạt; chỉ daily task mới có nút `Start focus`.
- Hoàn thành focus session không tự động hoàn thành daily task hoặc goal.
- AI chỉ tạo draft; mọi create, reschedule, drop hoặc replan đều cần user approve.
- AI không được tự thay đổi deadline hoặc definition of done của goal.
- Backend kiểm tra capacity; không tin trực tiếp duration hoặc cấu trúc do model trả về.
- Kế hoạch chi tiết chỉ tạo cho tuần hiện tại. Các tháng sau chỉ giữ ở mức milestone.
- Task chưa hoàn thành không tự động chuyển ngày. User phải chọn reschedule, inbox hoặc drop.
- Xoá parent không được âm thầm xoá children hoặc lịch sử focus session.

## P0 — Domain model và migration

- [x] **Chốt domain contract cho planning hierarchy.**
  - `Goal`: title, definition of done, deadline, importance, status và weekly capacity.
  - `PlanItem`: goal, parent, horizon `month | week | day`, planned period, estimate và status.
  - `FocusSession`: liên kết daily task và roll up về ancestors.
  - Cho phép item trong Inbox chưa có ngày hoặc chưa liên kết goal.
  - Chỉ daily item là executable.

- [x] **Thêm schema và migration không làm mất dữ liệu.**
  - Migration có thể chạy lặp lại an toàn.
  - Task cũ trở thành daily action trong Inbox.
  - Giữ nguyên name, priority, deadline, estimated duration và session history.
  - Không tự gán task cũ vào goal hoặc ngày cụ thể.
  - Có migration test từ schema hiện tại và test database đã migrate.

- [x] **Xây API CRUD cho Goal và PlanItem.**
  - Create, read, update, complete và archive goal.
  - Create, update, move, reschedule, complete, drop và đưa item về Inbox.
  - Validate quan hệ parent-child đúng thứ tự month → week → day.
  - Không cascade delete dữ liệu con nếu chưa có xác nhận rõ ràng.
  - Trả lỗi conflict khi dữ liệu đã thay đổi so với preview.

- [x] **Thêm query progress roll-up.**
  - Tổng planned minutes và actual focus minutes.
  - Số focus session và daily task hoàn thành.
  - Tiến độ roll up từ day → week → month → goal.
  - Không dùng số giờ làm tiêu chí duy nhất để tự hoàn thành goal.

## P0 — Planning UI

- [x] **Thay tab `Tasks` bằng tab `Plan`.**
  - Có bốn view: `Inbox`, `Today`, `Week`, `Month`.
  - Giữ UI phù hợp với cửa sổ desktop hẹp.
  - Week dùng danh sách ngày theo chiều dọc, không dùng calendar bảy cột.
  - Người dùng có thể truy ngược từ daily task về weekly outcome, milestone và goal.

- [x] **Xây Goal creation flow.**
  - Nhập title, deadline và definition of done.
  - Nhập ngày có thể học/làm việc, số phút mỗi ngày và default session duration.
  - Nhập trạng thái hiện tại, điểm yếu và topic/syllabus nếu có.
  - Cho phép chọn `Plan manually` hoặc `Plan with AI`.

- [x] **Xây Inbox.**
  - Quick-add task chưa cần goal hoặc ngày.
  - Có thể assign task vào goal và schedule sang một ngày.
  - Hiển thị rõ task legacy sau migration.

- [x] **Xây Today view.**
  - Hiển thị daily task của ngày hiện tại và một main task nổi bật.
  - Mỗi task có estimate, parent goal và trạng thái focus.
  - Chỉ daily task có nút `Start focus`.
  - Task chưa xong có `Reschedule`, `Back to inbox` và `Drop`.

- [x] **Xây Week view.**
  - Hiển thị weekly outcomes, capacity và planned minutes.
  - Nhóm daily task theo từng ngày theo chiều dọc.
  - Cảnh báo khi kế hoạch vượt capacity.
  - Cho phép move/reschedule nhưng không tự động dời task.

- [x] **Xây Month view.**
  - Hiển thị goal và monthly milestones theo dạng danh sách.
  - Hiển thị deadline, milestone progress, actual focus time và completed tasks.
  - Không triển khai full calendar hoặc Gantt chart trong MVP.

## P0 — Focus execution

- [x] **Cho phép nhiều focus session trên cùng daily task.**
  - Session có thể diễn ra ở nhiều ngày khác nhau.
  - Session completion chỉ cập nhật actual focus time.
  - User chủ động đánh dấu daily task hoàn thành.
  - Khôi phục đúng active session sau khi restart app.

- [x] **Roll up focus history vào planning hierarchy.**
  - Daily task hiển thị số session và actual minutes.
  - Weekly, monthly và goal view hiển thị số liệu tổng hợp.
  - Penalty/distraction time không được tính là focus time.
  - Lịch sử vẫn tồn tại khi task được reschedule, drop hoặc parent được archive.

## P0 — AI plan draft

- [x] **Định nghĩa structured input/output cho AI planner.**
  - Input gồm goal, deadline, definition of done, capacity, default session và topic list.
  - Output gồm assumptions, monthly milestones, weekly outcomes và daily tasks tuần đầu.
  - Output dùng schema có version và được validate trước khi preview.
  - Reject output sai horizon, thiếu parent, duration không hợp lệ hoặc vượt giới hạn số item.

- [x] **Tạo rolling-wave plan draft.**
  - Tạo khung milestone cho toàn bộ khoảng thời gian tới deadline.
  - Chỉ chi tiết hoá 2–4 tuần gần nhất ở mức weekly outcome.
  - Chỉ tạo daily task cho tuần hiện tại.
  - Nếu thiếu syllabus, AI phải hiển thị assumptions thay vì giả định ngầm.

- [x] **Thêm deterministic capacity validation.**
  - Tính capacity từ ngày khả dụng và số phút mỗi ngày.
  - Mặc định chỉ plan tối đa 80% capacity để có buffer; cho phép cấu hình sau.
  - Hiển thị planned so với available minutes.
  - Không cho approve draft vượt capacity cho đến khi user sửa hoặc xác nhận override.

- [x] **Xây preview, edit và approval flow.**
  - Preview toàn bộ hierarchy trước khi ghi database.
  - Cho phép sửa, xoá, thêm item trong draft.
  - Cho phép regenerate riêng một milestone hoặc một tuần.
  - Một approval chỉ tạo dữ liệu đúng một lần; retry không được duplicate plan.
  - Cancel draft không tạo hoặc thay đổi dữ liệu thật.

- [x] **Thêm AI safety và failure states.**
  - Timeout/provider error không làm mất form goal của user.
  - Không ghi prompt nhạy cảm, API key hoặc syllabus đầy đủ vào log.
  - Hiển thị lỗi validation dễ hiểu và cho phép sửa draft thủ công.
  - Manual planning vẫn hoạt động khi không có provider AI.

## P0 — Weekly Review và AI replan

- [ ] **Xây Weekly Review flow.**
  - So sánh planned minutes với actual minutes.
  - Hiển thị completed, unfinished và dropped tasks.
  - User xử lý từng task tồn bằng reschedule, inbox hoặc drop.
  - Thu thập trở ngại và thay đổi capacity của tuần kế tiếp.

- [ ] **Tạo AI replan draft cho tuần kế tiếp.**
  - Dùng tiến độ thật, task còn tồn, deadline và capacity mới.
  - Không tự thay đổi goal hoặc monthly milestone đã approve.
  - Nêu rõ item nào được giữ, đổi, bỏ hoặc tạo mới.
  - Replan phải qua cùng preview/edit/approve flow và idempotency guard.

## P0 — User stories và acceptance tests

- [ ] **US1 — Tạo goal.**
  - Given người dùng có một mục tiêu dài hạn,
  - when nhập goal, deadline, definition of done và capacity,
  - then goal được lưu và có thể plan thủ công hoặc bằng AI.

- [ ] **US2 — AI chia nhỏ goal.**
  - Given goal có đủ deadline và capacity,
  - when người dùng chọn `Plan with AI`,
  - then app trả về draft month/week/day hợp lệ và không ghi database.

- [ ] **US3 — Chỉnh và approve draft.**
  - Given AI draft đang mở,
  - when người dùng sửa rồi approve,
  - then hierarchy được tạo đúng một lần và xuất hiện ở đúng các view.

- [ ] **US4 — Xem theo horizon.**
  - Given goal đã có kế hoạch,
  - when chuyển giữa Today, Week và Month,
  - then mỗi view chỉ hiện mức chi tiết phù hợp và vẫn truy được parent goal.

- [ ] **US5 — Thực hiện nhiều session.**
  - Given một daily task chưa hoàn thành,
  - when hoàn thành nhiều focus session ở các ngày khác nhau,
  - then thời gian được cộng dồn nhưng task vẫn mở cho đến khi user complete.

- [ ] **US6 — Xử lý task chưa hoàn thành.**
  - Given một daily task đã qua ngày,
  - when mở Today hoặc Weekly Review,
  - then app yêu cầu chọn reschedule, inbox hoặc drop và không tự đổi ngày.

- [ ] **US7 — Weekly Review và replan.**
  - Given tuần hiện tại có execution history,
  - when user bắt đầu review,
  - then app hiển thị planned/actual và AI tạo draft tuần mới cần approval.

- [ ] **US8 — Hoạt động khi AI unavailable.**
  - Given provider lỗi hoặc chưa có API key,
  - when user tạo goal,
  - then manual planning và focus session vẫn hoạt động đầy đủ.

## P0 — Verification và release gate

- [x] Backend tests cho models, migration, hierarchy validation, roll-up và conflict handling.
- [x] Contract tests cho AI schema, malformed output, capacity overflow và idempotent approval.
- [ ] Frontend tests cho Inbox/Today/Week/Month và draft editing.
- [ ] End-to-end flow: create goal → AI draft → edit → approve → focus → weekly replan.
- [ ] Regression tests cho session timer, statistics, chat confirmation và desktop restart.
- [x] Test migration trên bản sao database hiện tại trước khi chạy trên dữ liệu thật.
- [x] TypeScript, lint, backend test, Python compilation và `git diff --check` đều đạt.

## P1 — User Personalization & Relationship Memory

### Mục tiêu và nguyên tắc

Giúp Pomo hiểu người dùng qua nhiều phiên làm việc, nhớ các sự kiện có ý nghĩa và phản hồi
như một người bạn quen thuộc mà không giả vờ có ký ức, cảm xúc hoặc thông tin chưa được lưu.

```text
Interaction/event
→ immutable event log
→ memory extraction và deterministic validation
→ User Profile + Habit Profile + Relationship Episodes
→ context-aware retrieval
→ agent response/action
→ user correction hoặc feedback
→ memory được cập nhật, supersede hoặc xoá
```

Product rules bắt buộc:

- `thread_id` chỉ giữ conversation state; `profile_id` mới đại diện người dùng qua nhiều thread.
- Tách `explicit preference` khỏi `inferred habit`; UI và prompt phải cho biết nguồn của memory.
- Chỉ gọi một mẫu hành vi là habit khi đủ evidence, confidence và recency.
- LLM có thể đề xuất memory nhưng service deterministic quyết định validate và persistence.
- Không suy diễn hoặc tự lưu dữ liệu nhạy cảm; yêu cầu consent rõ ràng trước khi lưu.
- Không dùng guilt, loneliness, pressure hoặc cảm xúc của Pet để ép user tương tác/làm task.
- User luôn có thể xem, sửa, xoá từng memory, xoá toàn bộ và tắt adaptive behavior.
- Current instruction > explicit preference > contextual habit > global habit > app default.

### P1.1 — Profile identity và persistence foundation

- [x] **Tạo profile identity độc lập với chat thread.**
  - Tạo local `profile_id` ổn định cho single-user desktop app.
  - Mọi conversation thread, task event và relationship memory liên kết cùng profile.
  - Chuẩn bị schema có `profile_id` để hỗ trợ multi-profile sau này nhưng chưa xây account/cloud sync.
  - Migration giữ nguyên conversation memory, task, session và planning data hiện tại.

- [ ] **Tạo schema memory có source và audit trail.**
  - `personal_memories`: tên, cách xưng hô, sở thích, dislikes, communication style và goals dài hạn.
  - `habit_profiles`: habit theo context, evidence count, confidence và last observed time.
  - `relationship_episodes`: shared event có summary, importance, emotional tone và entity links.
  - `shared_rituals`: câu chào, inside joke, celebration style hoặc routine đã được xác nhận.
  - `memory_corrections`: correction, superseded memory và lý do thay đổi.
  - Không hard-delete audit record trừ flow `delete all relationship data`; memory bị thay thế phải inactive.

- [ ] **Định nghĩa memory contract và sensitivity policy.**
  - Mỗi memory có `kind`, `key`, `value`, `source`, `confidence`, `scope`, `sensitivity`, timestamps và trạng thái.
  - Phân biệt source `explicit_user`, `verified_app_event`, `behavioral_inference` và `agent_suggestion`.
  - `agent_suggestion` không trở thành active memory nếu chưa được deterministic evidence hoặc user xác nhận.
  - Sensitive fields dùng allowlist/denylist và không xuất hiện trong application log.

### P1.2 — Behavioral event capture

- [x] **Tạo immutable `user_action_events`.**
  - Ghi `TASK_SELECTED`, `TASK_COMPLETED`, `SESSION_STARTED`, `SESSION_EXTENDED`,
    `SESSION_CANCELLED`, `SUGGESTION_ACCEPTED` và `SUGGESTION_CHANGED`.
  - Mỗi event có timestamp, profile, source `ui | chat | suggestion`, entity IDs và context JSON.
  - Event capture không làm chậm hoặc thay đổi kết quả của action nghiệp vụ chính.
  - Retry cùng idempotency key không tạo event trùng.

- [x] **Lưu snapshot context cần để học task-order habit.**
  - Khi select/complete task, lưu view `inbox | today | week`, rank, visible task count và sort mode.
  - Không cố suy ra “task đầu tiên” sau khi task đã bị ẩn khỏi danh sách.
  - Không lưu raw screen content hoặc tên ứng dụng ngoài dữ liệu productivity cần thiết.

- [x] **Tách initial focus duration khỏi thời gian sau extension.**
  - Thêm `initial_duration` hoặc session event log tương đương.
  - Giữ `duration` hiện tại cho tổng thời gian sau extension và backward compatibility.
  - Migration backfill an toàn; dữ liệu cũ có source/quality rõ ràng thay vì giả là lựa chọn ban đầu.

### P1.3 — Explicit personal facts và preferences

- [x] **Tạo Memory Extraction pipeline cho user statement.**
  - Nhận diện phát biểu như “Tên mình là An”, “gọi mình là bro”, “mình thích nhắc ngắn”.
  - Structured output chỉ đề xuất candidate memory; backend validate key, type, length và sensitivity.
  - Câu nói tạm thời như “hôm nay mình mệt” không tự trở thành personality hoặc preference dài hạn.
  - Memory cùng key được supersede, không tồn tại hai active facts mâu thuẫn.

- [ ] **Thêm confirmation policy theo độ nhạy và độ chắc chắn.**
  - Fact/preference rõ ràng, ít nhạy cảm có thể lưu và thông báo ngắn.
  - Thông tin nhạy cảm, mơ hồ hoặc có thể chỉ đúng tạm thời phải hỏi trước khi lưu.
  - Hỗ trợ câu lệnh `hãy nhớ`, `đừng nhớ`, `quên điều này` và `đừng nhắc lại`.
  - Correction trực tiếp của user luôn thắng inference hoặc memory cũ.

### P1.4 — Habit inference

- [x] **Xây deterministic Habit Aggregator v1.**
  - Tính các habit đầu tiên: chọn task theo rank, duration thường dùng, giờ bắt đầu focus và extension pattern.
  - Segment theo context vừa đủ: view, time bucket, weekday/weekend và task/goal khi có evidence.
  - Lưu evidence count, matching count/distribution, confidence, last observed và model version.
  - Dùng recency decay để habit cũ tự giảm ảnh hưởng nhưng không âm thầm xoá evidence.

- [x] **Chốt activation/deactivation thresholds.**
  - Không activate habit khi chưa đủ sample tối thiểu.
  - Chỉ auto-prefill khi confidence vượt ngưỡng cao; confidence trung bình chỉ dùng để gợi ý.
  - Repeated override làm giảm confidence hoặc tạo candidate habit mới.
  - Không coi silence, app usage duration hoặc task completion là bằng chứng user thích personality/action của Pet.

- [x] **Áp dụng habit vào trải nghiệm mà vẫn giữ quyền kiểm soát.**
  - Prefill duration phù hợp context nhưng user sửa được trước khi Start.
  - Có thể highlight/suggest task đầu tiên; không tự complete, reorder hoặc start session.
  - Write action từ chat vẫn đi qua preview/Confirm hiện có.
  - Hiển thị giải thích ngắn như “Gợi ý từ 8 phiên gần đây” khi recommendation dựa trên inference.

### P1.5 — Episodic và shared relationship memory

- [x] **Tạo episode candidate từ sự kiện đáng nhớ.**
  - Goal/milestone lớn hoàn thành, recovery sau giai đoạn khó, user chia sẻ sự kiện quan trọng,
    correction quan trọng và ritual lặp lại có thể tạo candidate.
  - Không biến mọi click, task hoặc session thành relationship episode.
  - Episode từ app event phải liên kết entity thật; episode từ chat phải giữ source message reference nội bộ.

- [x] **Tạo salience và consolidation policy.**
  - Chấm relevance, importance, recency, explicitness và shared-relationship value.
  - Gộp các episode trùng chủ đề thành summary mới nhưng giữ source references.
  - Có decay/archive cho episode ít quan trọng; milestone quan trọng không bị decay chỉ vì cũ.
  - Không để model bịa emotional tone hoặc chi tiết không có trong source.

- [x] **Tạo shared rituals và relationship corrections.**
  - Ritual chỉ active sau explicit agreement hoặc lặp lại đủ nhiều lần và được user xác nhận.
  - Ghi nhớ cách celebrate, cách động viên, nickname và inside joke theo scope rõ ràng.
  - Khi Pomo hiểu sai, lưu correction để tránh lặp lại thay vì giảm một “friendship score” mơ hồ.

### P1.6 — Relational state và persona expression

- [x] **Định nghĩa bounded `relational_state`.**
  - Các dimension ban đầu: familiarity, warmth, playfulness, concern và pride.
  - State được cập nhật từ verified event/feedback bằng rule có version, giới hạn và decay phù hợp.
  - Không có anger, jealousy, loneliness hoặc dependency mechanics dùng để tác động user.
  - State điều khiển cách diễn đạt, không được ghi đè facts, safety hoặc quyền tự chủ của user.

- [x] **Tạo persona expression policy.**
  - Cho phép lời nói tự nhiên như “Pomo vui vì bạn quay lại” hoặc “Mình tự hào về tiến độ này”.
  - Không khẳng định có ý thức/cảm xúc sinh học hay giả vờ đã nhớ khi retrieval không có evidence.
  - Không nói user làm Pet buồn/cô đơn khi nghỉ, bỏ task hoặc không tương tác.
  - Tone và mức thân mật phải tuân theo explicit communication preference của user.

### P1.7 — Memory retrieval và agent integration

- [x] **Xây context-aware Memory Retriever.**
  - Mỗi turn chỉ lấy personal facts, habits, episodes và correction liên quan nhất.
  - Ranking gồm semantic relevance, salience, recency, explicitness và context match.
  - Giới hạn token/count; không đưa toàn bộ event log hoặc toàn bộ profile vào prompt.
  - Nếu không có memory đủ tin cậy, agent nói không biết hoặc hỏi thay vì suy đoán.

- [x] **Inject structured User Model vào PomoAgent.**
  - Prompt phân biệt `explicit`, `inferred` và `shared episode` để model diễn đạt đúng độ chắc chắn.
  - Tool đọc memory tách khỏi tool Task/Session/Planning và chỉ trả field cần thiết.
  - Current user request luôn thắng retrieved memory.
  - Chat fallback vẫn hoạt động khi memory database/retrieval lỗi.

- [ ] **Thêm memory write protocol có preview khi cần.**
  - Explicit low-risk fact có thể acknowledge ngắn; sensitive/ambiguous memory cần Confirm.
  - Không cho model gọi generic SQL hoặc ghi arbitrary JSON trực tiếp vào profile.
  - Mọi write có schema validation, audit source và idempotency.

### P1.8 — User control UI

- [ ] **Xây màn hình `Pomo nhớ gì về mình`.**
  - Nhóm Personal facts, Preferences, Habits, Shared moments, Rituals và Corrections.
  - Hiển thị source, confidence/evidence và lần cập nhật gần nhất theo ngôn ngữ dễ hiểu.
  - Cho phép edit, deactivate, delete và `never mention again` từng memory.
  - Inferred habit phải có giải thích vì sao Pomo nghĩ như vậy.

- [ ] **Thêm privacy và adaptive controls.**
  - Toggle adaptive behavior và proactive memory prompts độc lập.
  - `Delete relationship data` không xoá task/session/planning data nếu user không chọn.
  - Có export profile/memories dạng machine-readable để audit local data.
  - Không sync cloud hoặc gửi toàn bộ memory cho provider ngoài context thực sự cần cho turn hiện tại.

### P1.9 — Acceptance scenarios

- [x] **AS1 — Nhớ tên và cách xưng hô.**
  - Given user nói rõ tên/cách gọi,
  - when mở conversation mới với cùng profile,
  - then Pomo dùng đúng cách gọi và user có thể sửa/xoá memory.

- [x] **AS2 — Học duration theo context.**
  - Given user chọn 50 phút trong nhiều buổi sáng và 25 phút buổi chiều,
  - when bắt đầu focus ở từng context,
  - then app prefill đúng duration kèm evidence và vẫn cho sửa trước khi Start.

- [ ] **AS3 — Học task-order habit.**
  - Given user thường chọn task rank 0 trong Today với đủ sample,
  - when user yêu cầu “bắt đầu làm việc”,
  - then Pomo đề xuất đúng task đầu tiên nhưng không tự start nếu chưa Confirm.
  - P1-B hiện highlight đúng task trong Plan UI; chat-side suggestion chưa bật vì inferred habit chưa có consent gửi tới provider.

- [x] **AS4 — Nhắc lại shared episode đúng lúc.**
  - Given user từng vượt qua một giai đoạn khó và hoàn thành milestone,
  - when user gặp context tương tự,
  - then Pomo có thể nhắc episode thật, không thêm chi tiết ngoài source.

- [x] **AS5 — Correction thắng inference.**
  - Given habit đang active nhưng user nói “đừng mặc định 50 phút nữa”,
  - when bắt đầu session tiếp theo,
  - then preference mới được áp dụng và habit cũ không tiếp tục điều khiển UI.

- [x] **AS6 — Persona thân thiện nhưng không thao túng.**
  - Given user quay lại sau thời gian dài hoặc bỏ một task,
  - when Pomo phản hồi,
  - then Pomo có thể thể hiện vui/quan tâm nhưng không tạo guilt, loneliness hoặc dependency.

### P1.10 — Verification và release gate

- [ ] Migration, CRUD và isolation tests cho profile/memory/event schemas.
- [ ] Idempotency tests cho event capture và memory writes.
- [ ] Golden tests cho extraction: explicit fact, temporary state, ambiguity, correction và sensitive data.
- [ ] Habit tests cho minimum sample, confidence, recency decay, context split và repeated override.
- [ ] Retrieval tests cho relevance, token limit, stale memory và contradictory memory.
- [ ] Safety tests cho fabricated memory, guilt language, sensitive inference và delete/export flows.
- [ ] End-to-end: share name → new thread remembers → establish duration habit → override → forget memory.
- [ ] Observability chỉ log event name, IDs và outcome; không log personal memory value hoặc raw note.
- [ ] Có feature flag và rollback về agent không personalization mà không làm mất productivity data.

## Ngoài phạm vi MVP

- AI tự tạo hoặc tự thay đổi lịch mà không có approval.
- Đồng bộ Google Calendar, Outlook hoặc calendar hệ điều hành.
- Collaboration, chia sẻ goal và phân quyền.
- Cloud sync hoặc đồng bộ nhiều thiết bị.
- Gantt chart, dependency graph và critical path.
- Habit tracker và gamification mới.
- AI dạy bài, tạo/chấm đề thi hoặc xác minh kiến thức chuyên ngành.
- Tự đọc syllabus từ website hoặc file ngoài app.
- Spaced-repetition engine thích nghi, Anki integration và mastery model.
- Smart notification, push notification và background autonomous agent.
- Full drag-and-drop calendar.
- Dashboard/report tuỳ biến nâng cao.
- Auto-update, đa nền tảng và thay đổi framework desktop.

## Definition of Done

Một backlog item chỉ được đánh dấu hoàn thành khi:

1. Hành vi và acceptance criteria đã được triển khai đầy đủ.
2. Có automated tests tương xứng với rủi ro.
3. Failure, retry và recovery state đã được kiểm tra.
4. Migration bảo toàn dữ liệu hiện tại và có rollback/backup procedure.
5. Không log secret, API key hoặc dữ liệu nhạy cảm.
6. Tài liệu domain/API liên quan được cập nhật đồng bộ.
7. TypeScript, lint, backend tests, Python compilation và `git diff --check` đều đạt.
