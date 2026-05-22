# Hướng Dẫn Biến Ứng Dụng Này Thành Desktop Pet Thật Sự

Do chúng ta đang chạy trên nền tảng web (trình duyệt) của AI Studio nên ứng dụng chỉ có thể mô phỏng một môi trường Desktop ảo (`Mock OS`).

Để có thể thả pet này ra màn hình Windows thật của bạn, chúng ta cần đóng gói code web này vào một phần mềm có khả năng giao tiếp với hệ điều hành, ví dụ như **Electron** hoặc **Tauri**.

Dưới đây là các bước bạn cần thực hiện trên máy tính (Local) của mình:

### 1. Bật chế độ "Pure Transparent"
Vào mục **Config (Thiết lập)** của Pet ở ứng dụng này, bật **Pure Transparent Mode**. Thao tác này sẽ xóa nền desktop ảo, chỉ tập trung vào Pet nổi bồng bềnh và nền sẽ trong suốt hoàn toàn.

### 2. Tải Code về máy (Export)
Sử dụng tuỳ chọn Export (tải Zip hoặc đưa lên Github) từ thanh cài đặt của AI Studio để tải toàn bộ template này về máy tính cá nhân cài sẵn **Node.js**.

### 3. Cài đặt Electron vào dự án Local
Mở terminal tại thư mục vừa tải về, chạy các lệnh sau:
```bash
npm install
npm install --save-dev electron concurrently wait-on
```

### 4. Tạo file `electron.js` tại thư mục gốc
Tạo một file tên là `electron.js` nằm cùng chỗ với `package.json`, sau đó dán nội dung sau để Electron xử lý nền trong suốt (`transparent: true`) và tắt viền cửa sổ (`frame: false`):

```javascript
const { app, BrowserWindow } = require('electron');
const path = require('path');

function createWindow() {
  const mainWindow = new BrowserWindow({
    width: 600,
    height: 800, // Tuỳ chỉnh kích thước nếu cần
    transparent: true, // Xoá nền trắng mặc định của Window
    frame: false,      // Tắt thanh viền có chứa nút X, [-]
    hasShadow: false,
    alwaysOnTop: true, // Pet luôn nổi trên tất cả ứng dụng khác
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    }
  });

  // Tải trang React Next.js đang chạy local
  mainWindow.loadURL('http://localhost:3000');
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
```

### 5. Cập nhật `package.json`
Thêm script chạy Electron vào phần `"scripts"` trong `package.json`:
```json
  "scripts": {
    "dev": "next dev",
    "desktop": "concurrently \"npm run dev\" \"wait-on http://localhost:3000 && electron electron.js\"",
    // ...
  }
```

### 6. Khởi động Desktop Pet
Tại cửa sổ dòng lệnh tại dự án của bạn trên máy tính, gõ:
```bash
npm run desktop
```

Sau ít giây, ứng dụng sẽ khởi động Electron và hiện duy nhất con Pet ngay trên cửa sổ Windows thật của bạn, hoạt động gõ văn bản và bong bóng chat hoàn toàn bình thường giống một Desktop Pet thực thụ!
