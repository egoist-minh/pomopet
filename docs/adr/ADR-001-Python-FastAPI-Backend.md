# ADR 001: Lựa chọn Python (FastAPI) làm Local Backend cho Electron Desktop App

## 1. Bối cảnh (Context)
- **Kiến trúc hiện tại**: Dự án PomoPet đang sử dụng **Electron** làm vỏ bọc Desktop và **Next.js** (Static Export) làm hệ thống giao diện (Renderer Process).
- **Nhu cầu mở rộng**: Ứng dụng cần phát triển thêm phần xử lý logic phức tạp, gọi API AI, thao tác với database cục bộ (SQLite) và xử lý dữ liệu.
- **Năng lực cốt lõi**: Nguồn lực phát triển (Developer) là một chuyên gia về **Python**, có nhiều kinh nghiệm sử dụng các framework Python thay vì hệ sinh thái Node.js của Electron (Main Process).
- **Vấn đề**: Việc cố gắng dùng Node.js/ipcMain để viết backend sẽ gây kéo dài thời gian phát triển, rủi ro lỗi cao, và không tận dụng được sức mạnh của các thư viện hệ sinh thái Python (đặc biệt là AI/Data sci).

## 2. Quyết định (Decision)
Chúng ta thiết lập một mô hình **Kiến trúc Đa Tiến trình (Multi-Process Architecture)**:
1. **Frontend (UI)**: Next.js + Tailwind (HTML/JS/CSS tĩnh) chạy trên giao diện của Electron.
2. **Local Backend**: Một Restful API Server viết bằng **Python (FastAPI)** chạy ẩn ngầm (background) ở môi trường localhost (VD: `http://localhost:8000`).
3. **Bridge/Manager**: Electron Main Process (Node.js) chỉ đóng một vai trò duy nhất: Quản lý vòng đời (Lifecycle) - khởi động FastAPI khi mở app và "giết" (kill) tiến trình FastAPI khi tắt app.

Việc đóng gói cuối cùng sẽ sử dụng **PyInstaller** để biến code Python thành file chạy độc lập (.exe), sau đó được electron-builder đính kèm và gọi khi user cài đặt phần mềm.

## 3. Hệ quả (Consequences)

### Tích cực (Positives)
- **Tốc độ phát triển cực nhanh**: Phát huy tối đa thế mạnh của developer. Code Python/FastAPI ngắn gọn, dễ bảo trì.
- **Tích hợp phần mềm dễ dàng**: Cực kỳ thuật lợi nếu sau này PomoPet cần dùng các thư viện LLM, Langchain, Computer Vision, v.v., vốn là thế mạnh áp đảo của Python.
- **Độc lập hoàn toàn**: Frontend (Next.js) giao tiếp với Backend (Python) thông qua HTTP(s) standard. Hai bên hoàn toàn không dính líu đến nhau ngoài contract API (Swagger do FastAPI tự động gen).

### Tiêu cực (Negatives)
- **Dung lượng file lớn hơn**: Đóng gói app sẽ nặng hơn (Thêm một môi trường Python build bằng PyInstaller vào bên trong app phân phối).
- **Độ phức tạp trong đóng gói**: Lúc build release cần setup 2 luồng: Build Python ra .exe -> Copy vào thư mục rễ của Electron -> Phân phối.
- **Rủi ro Zombie Process**: Nếu Electron crash đột ngột mà không kịp kill tiến trình Python, backend Python có thể vẫn chạy dưới nền gây tốn RAM và kẹt Port.

## 4. Phương án giảm thiểu rủi ro (Mitigation)
- **Về Port Control**: Tránh dùng tĩnh `8000`, lúc Electron khởi động có thể cấp cho Python một random port trống để đảm bảo không đụng độ với app khác trên máy user.
- **Về Zombie Process**: Truyền `PID` (Process Identifier) của tiến trình gốc sang Python hoặc thiết lập một endpoint `/health-check`, nếu Python không thấy Electron Ping trong 10 giây -> tự động Shutdown. Lắng nghe cẩn thận sự kiện `app.on("will-quit")` bên Electron.
