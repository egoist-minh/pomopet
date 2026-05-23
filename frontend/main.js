const { app, BrowserWindow, protocol, ipcMain, screen } = require('electron');
const path = require('path');
const fs = require('fs');

const isDev = false; // Luôn đặt false để ép nó lấy thư mục xuất bản (out)

// 1. NGAY TẠI ĐÂY LÀ QUAN TRỌNG NHẤT: Đăng ký protocol trước khi app ready
protocol.registerSchemesAsPrivileged([
  { scheme: 'app', privileges: { secure: true, standard: true, supportFetchAPI: true } }
]);

let mainWindow = null;

function createWindow() {
  // Lấy kích thước màn hình để phủ toàn bộ desktop
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width, height } = primaryDisplay.bounds;

  mainWindow = new BrowserWindow({
    width: width,
    height: height,
    x: 0,
    y: 0,
    transparent: true,     // Bật nền trong suốt
    frame: false,          // Bỏ viền cửa sổ
    hasShadow: false,      // Bỏ bóng mờ
    alwaysOnTop: true,     // Luôn nổi trên cùng
    skipTaskbar: false,
    resizable: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  // Mặc định click xuyên qua toàn bộ cửa sổ bảo toàn thao tác của người dùng
  mainWindow.setIgnoreMouseEvents(true, { forward: true });

  if (isDev) {
    mainWindow.loadURL('http://localhost:3000');
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    // 3. Load file qua custom protocol (không dùng đường dẫn tĩnh C:\...)
    mainWindow.loadURL('app://-/index.html');
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  // 2. Định nghĩa cách giao thức 'app://' đọc file tĩnh sinh ra từ Next.js
  protocol.registerFileProtocol('app', (request, callback) => {
    let urlPath = request.url.replace(/^app:\/\/-?\//, '');
    let decodedUrl = decodeURI(urlPath);
    
    // Nếu link trống (chỉ gọi 'app://-/') thì nạp trang chủ
    if (decodedUrl === '') {
        decodedUrl = 'index.html';
    } else if (!path.extname(decodedUrl)) {
        // Next.js static export thường bỏ đuôi .html
        if (fs.existsSync(path.join(__dirname, 'out', decodedUrl + '.html'))) {
             decodedUrl += '.html';
        }
    }

    const absolutePath = path.normalize(path.join(__dirname, 'out', decodedUrl));
    callback({ path: absolutePath });
  });

  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

// IPC Header nhận yêu cầu thay đổi thao tác chuột từ giao diện
ipcMain.on('set-ignore-mouse-events', (event, ignore, options) => {
  if (mainWindow) {
    mainWindow.setIgnoreMouseEvents(ignore, options);
  }
});
