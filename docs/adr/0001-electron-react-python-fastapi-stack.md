# Electron + React frontend với Python FastAPI backend

Chọn kiến trúc hybrid: Electron + React cho UI (Pet Widget và Main Window), Python FastAPI cho backend (business logic, AI, database, app monitoring).

## Context

- Maintainer chỉ thành thạo Python, muốn giữ backend logic bằng Python để dễ quản lý dự án
- Maintainer sẵn sàng học frontend tech để giao diện chạy tốt hơn
- Pet cần có biểu cảm phong phú giống EMO Robot - cần animation support tốt
- Dự án open source, cần cross-platform (Windows/Mac/Linux)
- Dự án được "vibe code" - cần tech stack dễ prototype và iterate

## Decision

**Frontend:**
- Electron + React
- Lottie animations cho Pet biểu cảm (có thể dùng free assets từ LottieFiles để prototype)
- Hoặc sprite animations nếu Lottie quá phức tạp

**Backend:**
- Python FastAPI
- SQLite cho local data
- ChromaDB cho long-term memory (vector database)
- `psutil` cho app monitoring

**Communication:**
- REST API cho CRUD operations (Task, Session)
- WebSocket cho real-time updates (timer, notifications, Pet state changes)

## Considered Options

1. **PyQt6/PySide6** - Pure Python desktop app
   - ✅ Toàn bộ Python, dễ maintain
   - ❌ Animation support hạn chế hơn web tech
   - ❌ UI design khó hơn, ít flexible

2. **Tauri + Python backend**
   - ✅ Nhẹ hơn Electron
   - ❌ Ít tài liệu hơn, community nhỏ hơn
   - ❌ Rust backend mặc định (phải setup Python riêng)

3. **Kivy** - Pure Python với animation tốt
   - ✅ Toàn bộ Python
   - ❌ Community nhỏ, ít tài liệu
   - ❌ Ít phổ biến cho desktop app, khó tìm contributors

## Consequences

**Ưu điểm:**
- Backend Python giúp maintainer quản lý logic dễ dàng
- Electron + React có ecosystem lớn, nhiều thư viện cho desktop features (system tray, notifications, always-on-top)
- Animation support tốt (Lottie, CSS animations, React Spring)
- Dễ tìm contributors biết React
- Tách biệt UI và logic - dễ test và maintain
- Cross-platform mà không cần viết code riêng cho từng OS

**Nhược điểm:**
- Electron tốn RAM hơn native app (trade-off chấp nhận được cho UX tốt hơn)
- Kiến trúc phức tạp hơn pure Python (2 processes: Electron + Python backend)
- Maintainer cần học React và JavaScript/TypeScript
- Cần setup communication giữa frontend và backend (REST API + WebSocket)

**Mitigation:**
- Dùng free Lottie animations để prototype nhanh, không cần vẽ từ đầu
- Dùng React component libraries (Ant Design, Material-UI) để giảm công việc frontend
- Backend Python giữ phần logic phức tạp (AI, monitoring) - phần maintainer thành thạo nhất
