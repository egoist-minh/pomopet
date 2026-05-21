# MVP Scope

## Core Features (Version 1.0)

Tính năng cần có trong version đầu tiên để app có thể sử dụng được:

### 1. Pet Widget
- [ ] Floating window nhỏ, always-on-top
- [ ] Hiển thị Pet với biểu cảm cơ bản (3-4 emotions: happy, sad, excited, thinking)
- [ ] Hiển thị timer đang chạy
- [ ] Có thể kéo đến vị trí bất kỳ
- [ ] Minimize xuống system tray

### 2. Session Management
- [ ] Start Session (chọn thời gian)
- [ ] Pause/Resume Session
- [ ] Cancel Session
- [ ] Hiển thị xác nhận khi Session sắp kết thúc (nghỉ hoặc extend)
- [ ] Short Break (5 phút) sau Session

### 3. Task Management (đơn giản)
- [ ] Tạo Task (tên, độ ưu tiên, deadline)
- [ ] Xóa Task
- [ ] Chọn Task để bắt đầu Session
- [ ] Đánh dấu Task hoàn thành (xác nhận rồi xóa)

### 4. Main Window
- [ ] Danh sách Tasks
- [ ] Thống kê cơ bản: tổng giờ tập trung hôm nay
- [ ] Chat đơn giản với Pet

### 5. AI Integration (cơ bản)
- [ ] OpenAI API integration
- [ ] Pet trả lời câu hỏi đơn giản về productivity
- [ ] Settings để nhập API key

### 6. Data Storage
- [ ] SQLite cho Tasks và Sessions
- [ ] Lưu local trên máy user

## Future Features (Post-MVP)

Tính năng để làm sau khi MVP đã hoàn thành và stable:

### Phase 2: Distraction Management
- [ ] App monitoring (detect active window)
- [ ] Distraction detection và confirmation
- [ ] Penalty system (thêm 5 phút)
- [ ] Distraction Chain tracking
- [ ] Angry emotion khi user xao nhãng

### Phase 3: Advanced Memory & Personalization
- [ ] ChromaDB integration cho long-term memory
- [ ] Pet nhớ hành vi và tính cách user
- [ ] Cá nhân hóa cách nhắc nhở
- [ ] AI đề xuất thời gian Session dựa trên history

### Phase 4: Enhanced Features
- [ ] Subtask support
- [ ] Long Break (15-30 phút sau 4 Sessions)
- [ ] Statistics chi tiết (phân bổ theo giờ, patterns)
- [ ] Nhiều AI service options (Claude, Ollama)
- [ ] Pet personality customization
- [ ] Nhiều biểu cảm phức tạp hơn

### Phase 5: Advanced Features
- [ ] Cloud sync (optional)
- [ ] Export/import data
- [ ] Themes cho Pet appearance
- [ ] Sound effects và voice
- [ ] Mobile companion app (xem statistics)

## Development Priority

1. **Tuần 1-2**: Pet Widget + Session timer cơ bản
2. **Tuần 3-4**: Task management + Main Window
3. **Tuần 5-6**: AI chat integration + Statistics
4. **Tuần 7-8**: Polish UI, bug fixes, testing
5. **Release MVP v1.0**
6. Thu thập feedback từ users
7. Phát triển Phase 2, 3, 4, 5 dựa trên feedback
