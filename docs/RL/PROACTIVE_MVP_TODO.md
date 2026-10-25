# PomoPet Proactive MVP — Todo List

Mục tiêu của MVP: kiểm chứng Pomo có thể chủ động kể joke hoặc gợi ý plan đúng lúc,
không cần chờ user nhắn và không gây phiền.

## 0. Phạm vi đã chốt

- [x] Hỗ trợ `STAY_SILENT`, joke, dry humor, hydration tip, focus tip và `SUGGEST_PLAN`.
- [x] Hydration tip chạy animation uống nước; recent proactive copy giúp LLM tránh lặp.
- [x] Không tự tạo, sửa hoặc xóa plan; chỉ đưa ra đề xuất.
- [x] Không dùng im lặng, dismiss hoặc session completion làm RL reward.
- [x] Chưa triển khai LLM memory consolidation hoặc policy training trong MVP.

Default đề xuất:

- Proactive mặc định `OFF` cho user hiện tại.
- Tối đa 3 proactive message mỗi ngày.
- Cooldown 60 phút giữa hai message.
- Quiet hours từ 22:00 đến 07:00.
- Frontend kiểm tra mỗi 5 phút và tại các session transition quan trọng.

## 1. Persistence và consent

- [x] Thêm các profile setting:
  - [x] `proactive_enabled`.
  - [x] `proactive_jokes_on`.
  - [x] `proactive_planning_on`.
- [x] Viết migration an toàn cho database hiện tại.
- [x] Mở rộng profile API để đọc/cập nhật các setting mới.
- [x] Thêm bảng `proactive_decisions` lưu decision snapshot.
- [x] Thêm bảng `agent_trace_events` lưu structured debug trace.
- [x] Bảo đảm xóa relationship data sẽ xóa proactive history liên quan.

## 2. Backend proactive engine

- [x] Tạo request/response schema cho proactive check.
- [x] Implement `ProactiveService`.
- [x] Luôn đưa `STAY_SILENT` vào candidate actions.
- [x] Implement planning opportunity:
  - [x] Có active goal.
  - [x] Hôm nay chưa có daily plan phù hợp.
  - [x] Chỉ trả suggestion, không mutate plan.
- [x] Implement joke opportunity:
  - [x] Chỉ khi idle hoặc break.
  - [x] Dùng joke catalog an toàn, không cần gọi LLM liên tục.
  - [x] Chọn joke ổn định và tránh lặp gần nhau.
- [x] Planning suggestion có ưu tiên cao hơn joke.
- [x] Implement Safety Guard:
  - [x] Chặn khi proactive đang tắt.
  - [x] Chặn trong focus session.
  - [x] Chặn trong quiet hours.
  - [x] Chặn khi cooldown đang active.
  - [x] Không áp daily limit; cooldown vẫn giới hạn tần suất liên tiếp.
  - [x] Tôn trọng toggle riêng cho joke và planning.
- [x] Implement idempotency theo `request_id`.

## 3. Trace và API

- [x] Ghi trace cho các bước:
  - [x] Trigger nhận được.
  - [x] State/context được đọc.
  - [x] Candidate actions được tạo.
  - [x] Safety rule được áp dụng.
  - [x] Action được chọn.
  - [x] Action thực sự được hiển thị.
- [x] Trace chỉ chứa dữ liệu có cấu trúc; không lưu chain-of-thought.
- [x] Không đưa raw chat hoặc dữ liệu nhạy cảm vào application log.
- [x] Thêm `POST /api/proactive/evaluate`.
- [x] Thêm `POST /api/proactive/decisions/{id}/executed`.
- [x] Thêm `GET /api/proactive/runs`.
- [x] Thêm `GET /api/proactive/runs/{id}`.

## 4. Frontend integration

- [x] Thêm type và API client cho proactive decision.
- [x] Tạo `useProactiveAgent` scheduler.
- [x] Không tạo request song song nếu check trước chưa hoàn thành.
- [x] Không check khi backend chưa sẵn sàng hoặc setup chưa hoàn tất.
- [x] Gọi proactive check mỗi 5 phút.
- [x] Gọi check sau khi focus hoặc break kết thúc.
- [x] Hiển thị joke/plan suggestion trong speech bubble.
- [x] Báo `executed` chỉ sau khi bubble đã được render.
- [x] Với `SUGGEST_PLAN`, cho phép user mở tab Tasks.
- [x] Không tự thay đổi plan từ proactive response.
- [x] Thêm settings UI:
  - [x] Proactive master toggle.
  - [x] Joke toggle.
  - [x] Planning suggestion toggle.

## 5. Automated verification

### Backend tests

- [x] Proactive `OFF` luôn trả `STAY_SILENT`.
- [x] Focus session luôn trả `STAY_SILENT`.
- [x] Quiet hours luôn trả `STAY_SILENT`.
- [x] Cooldown ngăn message liên tiếp.
- [x] Daily limit ngăn message vượt giới hạn.
- [x] Active goal thiếu daily plan tạo `SUGGEST_PLAN`.
- [x] Plan suggestion không tạo hoặc sửa database plan item.
- [x] Joke chỉ xuất hiện khi được bật và context phù hợp.
- [x] Cùng `request_id` không tạo hai decision.
- [x] Cooldown chỉ tính action đã được đánh dấu `executed`.
- [x] Mỗi decision có trace và reason codes kiểm tra được.
- [x] Migration chạy lặp lại an toàn.

### Frontend tests

- [x] Scheduler chạy đúng interval.
- [x] Scheduler cleanup timer khi component unmount.
- [x] Không gửi hai request proactive đồng thời.
- [x] Không render bubble cho `STAY_SILENT`.
- [x] Render đúng joke và planning suggestion.
- [x] Gọi `executed` đúng một lần cho mỗi decision.

## 6. Manual validation

- [ ] Bật proactive trong Settings.
- [ ] Tạo một active goal nhưng không tạo daily task hôm nay.
- [ ] Xác nhận Pomo chủ động đề nghị mở planning.
- [ ] Xác nhận không có plan item nào được tự tạo.
- [ ] Bắt đầu focus session và chờ/check trigger.
- [ ] Xác nhận Pomo không joke hoặc gợi ý plan trong lúc focus.
- [ ] Kết thúc session và xác nhận Pomo có thể chủ động tương tác.
- [ ] Tắt joke và xác nhận chỉ còn planning suggestion.
- [ ] Tắt master toggle và xác nhận mọi check đều `STAY_SILENT`.
- [ ] Mở trace theo `run_id` và kiểm tra được lý do chọn action.

## 6.1 UX follow-up đã hoàn thành

- [x] Hiển thị `SUGGEST_PLAN` trong transcript Chat.
- [x] Thêm CTA `Open Plan` trong chat message; không tự chuyển tab.
- [x] Chống chèn trùng cùng một proactive decision vào Chat.
- [x] Thêm panel xem proactive trace trực tiếp trong `CONFIG`.
- [x] Sửa timer bị throttle khi main Electron window bị ẩn.
- [x] Timer bám wall-clock deadline và bắt kịp callback bị trễ.
- [x] Focus hoàn tất tự complete daily task và refresh Plan.
- [x] Task completed không thể start focus lại.

## 7. Tiêu chí hoàn thành MVP

- [x] Pomo chủ động được mà không cần user gửi chat trước.
- [x] Không chen ngang focus và không vượt rate limit.
- [x] Planning suggestion không mutate dữ liệu khi chưa được xác nhận.
- [x] User kiểm soát được từng loại proactive behavior.
- [x] Mọi quyết định đều có trace dễ đọc để debug.
- [x] Backend và frontend test suite đều pass.
- [ ] Manual validation không phát hiện proactive message lặp hoặc sai thời điểm.

## Sau MVP

- [ ] Thu thập feedback explicit về proactive message.
- [ ] Fast Memory cho interaction gần đây.
- [ ] Self Model với affect state và decay.
- [ ] LLM consolidation sang Slow Memory.
- [ ] User Model và Self Model projection có evidence.
- [ ] Offline preference learning và policy versioning.
