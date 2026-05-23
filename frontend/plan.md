# Kế hoạch phát triển Desktop App thực tế

Dự án hiện tại đang là một Web App chạy trên trình duyệt mô phỏng một môi trường Desktop. Để đưa ứng dụng này thành một ứng dụng Desktop thực sự (Pet ảo trôi nổi trên màn hình máy tính của bạn), chúng ta cần đóng gói nó bằng các framework phù hợp.

Dưới đây là kế hoạch từng bước để biến ứng dụng này thành Desktop App thực tế.

## Lựa chọn Công nghệ

Chúng ta sẽ sử dụng **Tauri** hoặc **Electron**. 
- **Electron**: Phổ biến, dễ tích hợp với Node.js/Next.js, hỗ trợ cửa sổ trong suốt (transparent window) cực tốt - điều bắt buộc để biến Pet thành một nhân vật trôi nổi.
- **Tauri**: Nhẹ hơn, sử dụng Rust làm backend, cũng hỗ trợ cửa sổ trong suốt.

*(Kế hoạch dưới đây sẽ hướng dẫn sử dụng **Electron** vì nó rất dễ tích hợp với Next.js hiện tại).*

---

## Các bước thực hiện (Electron + Next.js)

### Bước 1: Chuyển đổi Next.js sang chế độ Static Export
Electron cần chạy các file HTML tĩnh từ local thay vì chạy một server Node.js.
1. Mở file `next.config.ts`.
2. Thêm cấu hình: `output: 'export'`.
3. Chạy `npm run build` để sinh ra thư mục `out/` chứa các file tĩnh.

### Bước 2: Khởi tạo Electron
1. Cài đặt Electron vào dự án:
   ```bash
   npm install --save-dev electron
   npm install electron-is-dev
   ```
2. Tạo file `main.js` (hoặc `main.ts` nếu custom cấu hình) ở thư mục gốc:
   - File này đóng vai trò khởi tạo cửa sổ (BrowserWindow).
   - **Đặc biệt lưu ý cấu hình quan trọng để cửa sổ trong suốt:**
     ```javascript
     const { app, BrowserWindow } = require('electron');
     
     function createWindow() {
       const win = new BrowserWindow({
         width: 800,
         height: 600,
         transparent: true,     // Bật chế độ trong suốt
         frame: false,          // Bỏ khung viền của cửa sổ
         hasShadow: false,      // Bỏ bóng để pet trông tự nhiên
         alwaysOnTop: true,     // Luôn hiển thị trên cùng
         webPreferences: {
           nodeIntegration: true,
           contextIsolation: false
         }
       });
       
       win.loadFile('out/index.html'); // Load file từ Next.js export
     }
     
     app.whenReady().then(createWindow);
     ```

### Bước 3: Cấu hình package.json
Thêm thuộc tính `"main": "main.js"` và lệnh chạy vào `package.json`:
```json
"main": "main.js",
"scripts": {
  "build:native": "next build",
  "start:native": "electron ."
}
```

### Bước 4: Điều chỉnh UI của Pet cho Desktop
- **Bỏ nền Desktop mô phỏng**: Xóa toàn bộ giao diện mô phỏng Taskbar và Wallpaper trong `components/DesktopEnvironment.tsx` hiện tại. App của bạn chỉ nên render ra DUY NHẤT component `FloatingPet` cùng với các menu/chat phụ trợ của nó.
- **Thêm tính năng kéo thả cửa sổ**: Cửa sổ Electron không có viền (`frame: false`), nên bạn cần dùng CSS `app-region: drag;` lên component của Pet để người dùng có thể nhấp vào Pet và kéo di chuyển trên màn hình máy tính.
- **Nhấp xuyên qua background**: Những vùng "trong suốt" (không phải con pet) cần được cấu hình `win.setIgnoreMouseEvents(true, { forward: true })` trong Electron để người dùng có thể thao tác với các ứng dụng khác đang nằm bên dưới.

## Tổng kết
Sau khi chạy `npm run start:native`, code UI React/Next.js của chúng ta sẽ được "nhúng" vào một khung cửa sổ ẩn của hệ điều hành. Floating Pet sẽ thực sự tương tác và hiển thị trên màn hình Desktop thật của bạn thay vì bị bó hẹp trong một không gian trình duyệt web.
