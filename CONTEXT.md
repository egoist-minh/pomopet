# PomoPet

Ứng dụng desktop giúp người dùng tập trung làm việc thông qua kỹ thuật Pomodoro với một AI pet đồng hành.

## Language

**Session** (Pomodoro Session):
Một khoảng thời gian tập trung làm việc trên một Task hoặc Subtask cụ thể. Bắt đầu khi User nhấn start, kết thúc khi hết thời gian hoặc User hủy. Thời gian có thể do User tự chọn hoặc AI đề xuất. Khi sắp kết thúc, hiện xác nhận để User chọn nghỉ hoặc extend Session (thêm thời gian vào Session hiện tại). Khi phát hiện xao nhãng, Session bị pause và Pet áp dụng Penalty. Session có 4 trạng thái: Running (đang chạy), Paused (tạm dừng, có thể resume), Completed (hoàn thành bình thường), Cancelled (bị hủy giữa chừng).
_Avoid_: Focus time, work period

**Task**:
Công việc mà User cần hoàn thành. Có tên Task, độ ưu tiên, và deadline. Task có thể chứa nhiều Subtask để chia nhỏ công việc lớn. Khi bắt đầu Session trên một Task, User mới điền thời gian ước tính cho Session đó. Khi Task hoàn thành, hệ thống xác nhận với User rồi xóa Task.
_Avoid_: Work item, todo

**Subtask**:
Phần việc nhỏ thuộc một Task. Chỉ có tên, không có độ ưu tiên và deadline riêng. Chỉ một cấp Task → Subtask, không nested sâu hơn. Mục đích giữ mọi thứ tối giản để User tập trung.
_Avoid_: Sub-item, child task

**Pet**:
AI agent hiển thị trên desktop với giao diện biểu cảm giống EMO AI desktop pet (màn hình mặt digital với mắt và miệng animated). Pet có tên mặc định "Pomo", User có thể tùy chỉnh tên khi setup. Pet hiển thị qua Pet Widget (floating window nhỏ always-on-top, có thể kéo đến vị trí bất kỳ, có thể minimize xuống system tray). User tương tác với Pet qua Main Window (quản lý Task, xem thống kê, chat). Pet nhắc User: trước Session (nếu có Task deadline gần), trong Session (nếu mất tập trung lâu), sau Break (nếu nghỉ quá lâu). Tần suất và cách nhắc được cá nhân hóa dựa trên tính cách User. Pet có long-term memory để ghi nhớ hành vi, tính cách User nhằm tạo trải nghiệm gần gũi, cá nhân hóa thay vì cứng nhắc. Pet conversation được cung cấp bởi AI service mà User chọn trong settings (OpenAI GPT, Anthropic Claude, hoặc local model qua Ollama). Long-term memory dùng ChromaDB (local vector database). Tất cả dữ liệu (Tasks, Sessions, Statistics, memory) lưu local trên máy User (SQLite + ChromaDB), không có cloud sync trong MVP. Pet trả lời câu hỏi về: kỹ thuật làm việc, Task hiện tại, thói quen productivity, động viên/tư vấn - dựa trên long-term memory và kiến thức về productivity. Pet có các cảm xúc: Happy/Encouraging (Session đang chạy tốt), Excited (hoàn thành Session), Worried/Concerned (pause quá lâu hoặc sắp hết deadline), Sad (cancel Session), Sleepy/Resting (trong Break), Thinking (đang trả lời câu hỏi), Angry (User xác nhận đang xao nhãng). Khi phát hiện User chuyển sang app/website có khả năng gây xao nhãng (YouTube, Facebook, game...), Pet hỏi User xác nhận có đang dùng để làm việc/học tập liên quan Task không.
_Avoid_: Assistant, companion, buddy

**Break**:
Khoảng thời gian nghỉ ngơi sau khi kết thúc Session. Có 2 loại: Short Break (5 phút, sau mỗi Session) và Long Break (15-30 phút, sau 4 Sessions liên tiếp). User có thể tùy chỉnh thời gian hoặc skip Break để tiếp tục làm việc ngay.

**Penalty**:
Hình phạt khi User xao nhãng trong Session. Pet thêm 5 phút vào Session hiện tại và tích vào Distraction Chain.

**Distraction Chain**:
Chuỗi đếm số lần User bị xao nhãng trong một Session, reset về 0 khi Session kết thúc. Được lưu theo tuần để User xem lại tổng số chuỗi distraction trong tuần.
_Avoid_: Distraction streak, distraction count

**Statistics**:
Thống kê hiển thị cho User: số giờ tập trung hàng ngày (tổng và phân bổ theo giờ trong ngày), distraction patterns.
_Avoid_: Analytics, metrics, insights
