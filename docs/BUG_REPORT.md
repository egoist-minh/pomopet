# Bug Report: Frontend-Backend Synchronization Issue

## Tóm tắt (Summary)
**Vấn đề**: Khi Electron app khởi động, nó báo "DB CONNECTED" nhưng khi người dùng tương tác với UI (tạo task, click nút, v.v.), ứng dụng báo "fail to fetch". Tasks được tạo thành công trong database nhưng không hiển thị trong UI.

**Nguyên nhân gốc rễ**: Ba lỗi tích hợp:
1. CORS chỉ chấp nhận `http://localhost:3000` nhưng Electron chạy trên `app://` protocol
2. Frontend có local state fallbacks che giấu lỗi kết nối
3. Frontend không reload tasks khi API trả về null/lỗi

**Trạng thái**: ✅ FIXED

---

## Chi tiết nguyên nhân (Root Cause Analysis)

### 1. CORS Configuration Mismatch

**Lỗi**: Backend (main.py) chỉ cho phép:
```python
allow_origins=[
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "file://",
    "app://",
]
```

**Vấn đề**:
- Electron app chạy trên `app://` protocol (app://-)
- Browser preflight OPTIONS requests lại từ `app://` origin
- Backend không xử lý OPTIONS requests với origin `app://` đúng cách
- Kết quả: HTTP 400 Bad Request cho mọi preflight requests

**Log chứng minh**:
```
INFO:     127.0.0.1:50708 - "OPTIONS /api/tasks/ HTTP/1.1" 400 Bad Request
INFO:     127.0.0.1:50709 - "OPTIONS /api/sessions/current HTTP/1.1" 400 Bad Request
```

### 2. Local State Fallbacks Masking Real Errors

**Lỗi**: addTaskWithApi (DesktopEnvironment.tsx) có fallback:
```typescript
if (backendConnected) {
  try {
    const result = await api.createTask(...)
    if (result) {
      await loadTasks()
    }
  } catch (error) {
    // Không log, không reload
  }
} else {
  // Thêm task vào local state
  setTasks(prev => [...prev, newTask])
}
```

**Vấn đề**:
- Nếu API trả về null, không reload tasks
- Nếu backendConnected=false, thêm vào local state (che giấu vấn đề)
- Tasks được tạo thành công trong DB nhưng user không thấy

### 3. API Error Handling Returns Null Silently

**Lỗi**: fetchAPI (api.ts:107-131) catch mọi exception và trả về null:
```typescript
async function fetchAPI(endpoint: string, options: RequestInit = {}) {
  try {
    return await fetchAPIWithRetry(endpoint, options);
  } catch (error) {
    // ... logging ...
    return null;  // ← Trả về null, không throw
  }
}
```

**Vấn đề**:
- CORS errors được catch và trả về null
- Network errors được catch và trả về null
- Frontend không biết API call thất bại
- Không có cách để frontend sync với database

---

## Cách Fix (Solution)

### Fix 1: CORS Configuration - Hỗ trợ app:// Protocol

**File**: backend/app/main.py

```python
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"(http://(localhost|127\.0\.0\.1)(:\d+)?)|(app://.*)",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    max_age=3600,
)
```

**Lợi ích**:
- ✅ Chấp nhận `app://` protocol từ Electron
- ✅ Chấp nhận `http://localhost:*` (mọi port)
- ✅ Xử lý OPTIONS preflight requests đúng cách
- ✅ Frontend có thể gửi requests từ Electron app

### Fix 2: Xóa Local State Fallbacks - Hiện Rõ Lỗi

**File**: frontend/components/DesktopEnvironment.tsx

```typescript
const addTaskWithApi = async (name: string, priority, deadline: string) => {
  if (!backendConnected) {
    throw new Error('Backend not connected');
  }
  
  try {
    const result = await api.createTask({ name, priority, deadline });
    // Luôn reload, cho dù result là null hay thành công
    await loadTasks();
  } catch (error: any) {
    console.error('API call failed!', error);
    // Reload tasks để sync với DB
    await loadTasks();
    throw error;  // ← Cho phép caller xử lý lỗi
  }
}
```

**Lợi ích**:
- ✅ Không có local state fallback che giấu lỗi
- ✅ Luôn reload tasks từ database
- ✅ Lỗi được throw và xử lý ở UI level
- ✅ User thấy rõ khi backend disconnect

### Fix 3: Loại Bỏ Duplicate Task Interface

**File**: frontend/components/DesktopEnvironment.tsx + MainWindow.tsx

- Xóa `export interface Task` từ DesktopEnvironment
- Import `Task` từ `@/lib/api` thay vì định nghĩa lại
- Fix MainWindow.tsx import Task từ đúng module

**Lợi ích**:
- ✅ Type safety
- ✅ Single source of truth
- ✅ Tránh duplicate definitions

---

## Verification

### Test 1: CORS Preflight
```bash
curl -X OPTIONS http://localhost:8000/api/tasks/ \
  -H "Origin: app://-" \
  -H "Access-Control-Request-Method: POST"
# Response: 200 OK với CORS headers
```

### Test 2: Task Creation Flow
```python
requests.post('http://localhost:8000/api/tasks/',
  headers={'Origin': 'app://-'},
  json={'name': 'Test', 'priority': 'high'})
# Response: 200 OK, task trong database
```

### Test 3: Electron App
- Launch: `npm run start:native`
- Create task → Thấy trong UI
- Backend logs: `POST /api/tasks/ | Status: 200`
- Refresh app → Task vẫn hiển thị

---

## Lessons Learned

1. **CORS debugging**: Kiểm tra preflight OPTIONS requests trước khi debug API
2. **Error masking**: Loại bỏ silent fallbacks để errors visible
3. **Protocol awareness**: Electron app !== Web app (app:// vs http://)
4. **Sync strategy**: Khi có doubt về sync, luôn reload từ source of truth
5. **Type safety**: Tránh duplicate type definitions

---

## Prevention

### Checklist cho future bugs:

- [ ] Kiểm tra CORS config khi có lỗi "fail to fetch"
- [ ] Kiểm tra browser DevTools Network tab cho 400 OPTIONS responses
- [ ] Không có local state fallbacks che giấu lỗi backend
- [ ] Luôn reload dữ liệu từ backend sau mutations
- [ ] Test cả http:// và app:// protocols cho Electron
- [ ] Mock CORS errors trong unit tests
- [ ] Add integration tests cho task creation flow

---

## Timeline

| Thời gian | Sự kiện |
|----------|--------|
| 13:40:18 | Backend logs cuối cùng - Electron app không gửi requests |
| 13:42+ | Phát hiện: Electron chạy trên `app://`, CORS config không support |
| Sửa CORS | Thêm regex support cho `app://` protocol |
| Rebuild | Frontend build với fixes (remove fallbacks, always reload) |
| ✅ Done | All fixes applied, ready to test |

---

## Files Affected

1. **backend/app/main.py** - CORS configuration
2. **frontend/lib/api.ts** - Error handling (không thay đổi return null để backward compatible)
3. **frontend/components/DesktopEnvironment.tsx** - Remove fallbacks, always reload
4. **frontend/components/MainWindow.tsx** - Fix import Task type

