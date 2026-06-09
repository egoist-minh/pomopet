# Bug Fix Report

## Thông tin Bug
- Bug ID: BUG-001
- Tên: Backend Connectivity/Fallback Logic
- Severity: CRITICAL
- Status: FIXED
- Ngày fix: 2026-05-31

## Mô tả
Khi backend không chạy (port 8000), frontend tự động fallback sang dummy tasks, khiến task không lưu vào database.

## Nguyên nhân gốc rễ
Logic fallback trong DesktopEnvironment.tsx (dòng 136-144) được trigger bất kể khi nào API call ném exception, không phân biệt "backend không chạy" với "lỗi tạm thời".

## Giải pháp
- Thêm retry logic (3 lần thử) trước khi fallback
- Cải thiện error handling để log rõ ràng hơn

## Test Results
| Test Case | Result |
|-----------|--------|
| TC-001 | PASS - Fallback hoạt động đúng |
| TC-002 | PASS - Task lưu vào DB khi backend ON |
| TC-005 | PASS - Task lưu local khi backend OFF |

## Ghi chú
Logic fallback vẫn cần thiết cho trường hợp backend thực sự không chạy.

---

# Bug Fix Report - BUG-004

## Thông tin Bug
- Bug ID: BUG-004
- Tên: Statistics Endpoint Error Handling
- Severity: HIGH
- Status: FIXED
- Ngày fix: 2026-05-31

## Mô tả
Khi getStatistics() trả về null, hệ thống hiểu nhầm là mất kết nối, set backendConnected=false, khiến task chỉ lưu local.

## Nguyên nhân gốc rễ
Code chỉ xử lý exception trong catch block, không xử lý trường hợp stats === null. Khi null, không set backendConnected=true nên các operation save vào local thay vì database.

## Giải pháp
Thêm else block để xử lý trường hợp stats === null:
- Vẫn set backendConnected = true
- Load tasks từ backend
- Statistics sẽ dùng giá trị mặc định (0)

## Test Results
| Test Case | Result |
|-----------|--------|
| TC-007 | PASS - Task vẫn save vào DB khi stats null |

## Ghi chú
Cần đảm bảo backend trả về response hợp lệ cho cả trường hợp không có data.